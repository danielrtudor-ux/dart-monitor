#!/usr/bin/env python3
"""
AGM parser — v0.3 test

Reads:
  governance/agm_filings_test.json

Writes:
  governance/agm_votes_test.json

Purpose:
  Parse DART's AGM-result "주주총회 안건 세부내역" table into
  resolution-level voting history for activist/governance research.

Important:
  - This is a research parser, not a legal conclusion engine.
  - It preserves the source table text for auditability.
  - It is designed around the newer DART format that reports:
      * support as % of eligible voting shares
      * support as % of shares actually voting
      * oppose/abstain %
"""

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent
IN_FILE = ROOT / "governance" / "agm_filings_test.json"
OUT_FILE = ROOT / "governance" / "agm_votes_test.json"

HEADER = "【주주총회 안건 세부내역】"

# A resolution row begins with an agenda number, then 보통결의/특별결의.
ROW_START = re.compile(
    r"(?<!\S)(\d+(?:-\d+)*(?:-\d+)?)\s+(보통결의|특별결의)\s+"
)

# The tail of each row in the newer DART format.
VOTE_TAIL = re.compile(
    r"\s+(가결|부결)\s+"
    r"(\d+(?:\.\d+)?)\s+"
    r"(\d+(?:\.\d+)?)\s+"
    r"(\d+(?:\.\d+)?)"
    r"(?:\s+(.*))?$",
    re.S,
)

def normalize(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()

def get_document_text(filing):
    """
    agm_filings_test.json stores snippets rather than the complete document.
    The first 찬성/반대/기권 snippet generally contains the entire agenda table.
    Choose the longest snippet containing the table header.
    """
    # v0.3 collector preserves full filing text. Prefer it because snippets
    # can truncate long agenda tables. Retain snippet fallback for older files.
    full_candidates = []
    for doc in filing.get("documents", []):
        full = normalize(doc.get("full_text"))
        if HEADER in full:
            full_candidates.append(full)
    if full_candidates:
        return max(full_candidates, key=len)

    candidates = []
    for doc in filing.get("documents", []):
        for item in doc.get("snippets", []):
            s = normalize(item.get("snippet"))
            if HEADER in s:
                candidates.append(s)
    return max(candidates, key=len) if candidates else None

def isolate_table(text):
    if not text or HEADER not in text:
        return None
    table = text.split(HEADER, 1)[1]

    # Stop before director-detail appendices where possible.
    stops = [
        "[이사선임 세부내역]",
        "【이사선임 세부내역】",
        "[사외이사선임 세부내역]",
        "【사외이사선임 세부내역】",
        "[감사위원선임 세부내역]",
        "【감사위원선임 세부내역】",
    ]
    cut = len(table)
    for marker in stops:
        pos = table.find(marker)
        if pos >= 0:
            cut = min(cut, pos)
    return table[:cut].strip()

def parse_meeting_date(text, fallback):
    if text:
        m = re.search(r"주주총회일자\s+(\d{4}-\d{2}-\d{2})", text)
        if m:
            return m.group(1)
    if fallback and len(fallback) == 8:
        return f"{fallback[:4]}-{fallback[4:6]}-{fallback[6:]}"
    return None

def classify_subject(subject, note):
    blob = normalize(f"{subject} {note}")

    if "감사위원회 위원이 되는" in blob or "감사위원" in blob:
        category = "audit_committee"
    elif "사외이사" in blob or "독립이사" in blob:
        category = "outside_director"
    elif "사내이사" in blob or "이사 선임" in blob or "이사선임" in blob:
        category = "director"
    elif "자기주식" in blob or "자사주" in blob:
        category = "treasury_shares"
    elif "배당" in blob:
        category = "dividend"
    elif "집중투표" in blob:
        category = "cumulative_voting"
    elif "정관" in blob:
        category = "articles"
    elif "재무제표" in blob:
        category = "financial_statements"
    elif "보수한도" in blob:
        category = "director_compensation"
    else:
        category = "other"

    return category

def threshold_for(resolution_type):
    # Approximate statutory voting threshold expressed as share of votes cast.
    # Special resolutions have additional issued-share requirements that are
    # NOT fully captured by this simple percentage.
    if resolution_type == "특별결의":
        return 66.6667
    return 50.0

def parse_rows(table):
    if not table:
        return []

    starts = list(ROW_START.finditer(table))
    rows = []

    for i, match in enumerate(starts):
        start = match.start()
        end = starts[i + 1].start() if i + 1 < len(starts) else len(table)
        raw_row = normalize(table[start:end])

        agenda_no = match.group(1)
        resolution_type = match.group(2)

        after_prefix = raw_row[match.end() - match.start():].strip()
        tail = VOTE_TAIL.search(after_prefix)
        if not tail:
            rows.append({
                "agenda_no": agenda_no,
                "resolution_type": resolution_type,
                "parse_status": "row_found_vote_tail_not_parsed",
                "raw_row": raw_row,
            })
            continue

        subject = normalize(after_prefix[:tail.start()])
        result = tail.group(1)
        eligible_support = float(tail.group(2))
        cast_support = float(tail.group(3))
        oppose_abstain = float(tail.group(4))
        note = normalize(tail.group(5))

        shareholder_proposal = "주주제안" in subject or "주주제안" in note
        advisory = "권고적" in subject or "권고적" in note
        three_pct = (
            "3%" in note
            or "3％" in note
            or "3% 초과 의결권 제한" in raw_row
            or "3%초과 의결권 제한" in raw_row
        )

        threshold = threshold_for(resolution_type)
        margin_to_simple_threshold = round(cast_support - threshold, 3)

        # Near-miss is most meaningful for ordinary elections where 50% of
        # votes cast is the visible threshold in the disclosed table.
        near_miss = (
            result == "부결"
            and resolution_type == "보통결의"
            and cast_support >= 45.0
        )
        close_management_win = (
            result == "가결"
            and resolution_type == "보통결의"
            and cast_support <= 55.0
        )

        rows.append({
            "agenda_no": agenda_no,
            "resolution_type": resolution_type,
            "subject": subject,
            "result": result,
            "support_pct_eligible_voting_shares": eligible_support,
            "support_pct_votes_cast": cast_support,
            "oppose_abstain_pct_votes_cast": oppose_abstain,
            "note": note or None,
            "shareholder_proposal": shareholder_proposal,
            "advisory_proposal": advisory,
            "three_percent_voting_limit_flag": three_pct,
            "category": classify_subject(subject, note),
            "simple_votes_cast_threshold_pct": threshold,
            "margin_vs_simple_votes_cast_threshold_pp": margin_to_simple_threshold,
            "activist_near_miss_flag": near_miss,
            "close_management_win_flag": close_management_win,
            "parse_status": "parsed",
            "raw_row": raw_row,
        })

    return rows

def summarize_company(meetings):
    resolutions = [
        r
        for m in meetings
        for r in m.get("resolutions", [])
        if r.get("parse_status") == "parsed"
    ]
    shareholder = [r for r in resolutions if r.get("shareholder_proposal")]
    three_pct = [r for r in resolutions if r.get("three_percent_voting_limit_flag")]
    near = [r for r in resolutions if r.get("activist_near_miss_flag")]
    close = [r for r in resolutions if r.get("close_management_win_flag")]

    max_shareholder_support = None
    if shareholder:
        max_shareholder_support = max(
            r["support_pct_votes_cast"] for r in shareholder
        )

    # Simple transparent research score. This is deliberately NOT the final
    # company activist score; it measures demonstrated AGM contestability.
    score = 0
    score += min(len(shareholder) * 3, 20)
    score += min(len(three_pct) * 4, 20)
    score += min(len(near) * 20, 40)
    score += min(len(close) * 10, 20)
    score = min(score, 100)

    return {
        "parsed_resolution_count": len(resolutions),
        "shareholder_proposal_count": len(shareholder),
        "three_percent_rule_resolution_count": len(three_pct),
        "activist_near_miss_count": len(near),
        "close_management_win_count": len(close),
        "max_shareholder_proposal_support_pct_votes_cast": max_shareholder_support,
        "demonstrated_agm_contestability_score": score,
        "interpretation": (
            "Research signal based on observed AGM voting history only; "
            "not a prediction of future activist success."
        ),
    }

def main():
    if not IN_FILE.exists():
        raise SystemExit(f"Missing input file: {IN_FILE}")

    raw = json.loads(IN_FILE.read_text(encoding="utf-8"))
    companies = []

    for company in raw.get("companies", []):
        meetings = []

        for filing in company.get("agm_result_filings", []):
            text = get_document_text(filing)
            table = isolate_table(text)
            resolutions = parse_rows(table)

            meetings.append({
                "rcept_no": filing.get("rcept_no"),
                "rcept_dt": filing.get("rcept_dt"),
                "report_nm": normalize(filing.get("report_nm")),
                "meeting_date": parse_meeting_date(text, filing.get("rcept_dt")),
                "resolution_count": len(resolutions),
                "parsed_resolution_count": sum(
                    1 for r in resolutions if r.get("parse_status") == "parsed"
                ),
                "resolutions": resolutions,
                "source_table_text": table,
            })

        summary = summarize_company(meetings)

        companies.append({
            "security_ticker": company.get("security_ticker"),
            "dart_ticker": company.get("dart_ticker"),
            "company": company.get("company"),
            "corp_code": company.get("corp_code"),
            "agm_summary": summary,
            "meetings": meetings,
        })

        print(
            company.get("security_ticker"),
            company.get("company"),
            summary["parsed_resolution_count"],
            "near_misses=", summary["activist_near_miss_count"],
            "score=", summary["demonstrated_agm_contestability_score"],
        )

    output = {
        "agm_parser_version": "0.3-test",
        "generated_at_kst": datetime.now(KST).isoformat(),
        "purpose": (
            "Resolution-level AGM voting history for governance and activist "
            "contestability research."
        ),
        "method_note": (
            "The parser uses the DART AGM-result agenda table preserved by "
            "agm_collector.py. Percentages and pass/fail results are taken from "
            "that table. Special-resolution legal thresholds require additional "
            "company-specific legal analysis."
        ),
        "company_count": len(companies),
        "companies": companies,
    }

    OUT_FILE.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUT_FILE}")

if __name__ == "__main__":
    main()
