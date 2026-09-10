#!/usr/bin/env python3
"""
AGM parser — v1.1 historical fallback

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
IN_FILE = ROOT / "governance" / "agm_filings.json"
OUT_FILE = ROOT / "governance" / "agm_votes.json"

HEADER = "【주주총회 안건 세부내역】"

# A resolution row begins with an agenda number, then 보통결의/특별결의.
ROW_START = re.compile(
    r"(?<!\S)(?:제)?(\d+(?:-\d+)*)(?:호)?\s+(보통결의|특별결의)\s+"
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
    Prefer complete document text. v1.1 collector preserves it for old and new
    AGM formats alike. Fall back to snippets only for files produced by older
    collector versions.
    """
    full_candidates = []
    for doc in filing.get("documents", []):
        full = normalize(doc.get("full_text"))
        if full:
            full_candidates.append(full)
    if full_candidates:
        return max(full_candidates, key=len)

    candidates = []
    for doc in filing.get("documents", []):
        for item in doc.get("snippets", []):
            s = normalize(item.get("snippet"))
            if s:
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


LEGACY_AGENDA_START = re.compile(
    r"(?:○\s*)?제\s*(\d+(?:-\d+)*)\s*호\s*의안\s*[:：]?\s*",
    re.I,
)

def parse_legacy_agenda(text):
    """
    Parse older Korean AGM-result disclosures that list agenda items and
    outcomes in prose but do not publish resolution-level vote percentages.

    These rows are useful as governance history, but must NOT be scored as
    demonstrated voting contestability because support/oppose percentages are
    unavailable.
    """
    if not text:
        return []

    compact = normalize(text)

    # Focus on the "기타 결의내용" / meeting-purpose section when present.
    for marker in ("4. 기타 결의내용", "기타 결의내용", "회의 목적사항"):
        pos = compact.find(marker)
        if pos >= 0:
            compact = compact[pos:]
            break

    matches = list(LEGACY_AGENDA_START.finditer(compact))
    rows = []

    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(compact)
        chunk = normalize(compact[m.end():end])
        if not chunk:
            continue

        # Strip later appendix sections from the final agenda item.
        for stop in (
            "[이사선임 세부내역]", "【이사선임 세부내역】",
            "[사외이사선임 세부내역]", "【사외이사선임 세부내역】",
            "[감사위원선임 세부내역]", "【감사위원선임 세부내역】",
            "※ 관련공시",
        ):
            p = chunk.find(stop)
            if p >= 0:
                chunk = chunk[:p].strip()

        # Older filings typically use phrases such as 원안대로 승인, 가결,
        # 원안대로 가결, 승인. Be conservative on failures.
        if re.search(r"(부결|否決|미승인|승인되지\s*않)", chunk):
            result = "부결"
        elif re.search(r"(가결|원안대로\s*승인|원안대로\s*가결|승인)", chunk):
            result = "가결"
        else:
            result = None

        # Split obvious result phrase away from the subject.
        subject = re.split(
            r"\s*(?:→|⇒|:)?\s*(?:원안대로\s*(?:승인|가결)|가결|부결|승인)\b",
            chunk,
            maxsplit=1,
        )[0].strip(" -:：")

        if len(subject) < 2:
            subject = chunk[:300]

        shareholder_proposal = "주주제안" in chunk
        advisory = "권고적" in chunk

        rows.append({
            "agenda_no": m.group(1),
            "resolution_type": None,
            "subject": subject,
            "result": result,
            "support_pct_eligible_voting_shares": None,
            "support_pct_votes_cast": None,
            "oppose_abstain_pct_votes_cast": None,
            "note": "Legacy AGM format: agenda/result recovered; vote percentages not disclosed in parsed text.",
            "shareholder_proposal": shareholder_proposal,
            "advisory_proposal": advisory,
            "three_percent_voting_limit_flag": ("3%" in chunk or "3％" in chunk),
            "category": classify_subject(subject, chunk),
            "simple_votes_cast_threshold_pct": None,
            "margin_vs_simple_votes_cast_threshold_pp": None,
            "activist_near_miss_flag": False,
            "close_management_win_flag": False,
            "parse_status": "parsed_agenda_only",
            "raw_row": chunk,
        })

    return rows

def summarize_company(meetings):
    voting_meetings = [m for m in meetings if m.get("data_status") == "parsed"]
    agenda_only_meetings = [m for m in meetings if m.get("data_status") == "agenda_only_no_vote_percentages"]
    unavailable_meetings = [
        m for m in meetings
        if m.get("data_status") not in ("parsed", "agenda_only_no_vote_percentages")
    ]

    voting_resolutions = [
        r for m in voting_meetings for r in m.get("resolutions", [])
        if r.get("parse_status") == "parsed"
    ]
    agenda_only_resolutions = [
        r for m in agenda_only_meetings for r in m.get("resolutions", [])
        if r.get("parse_status") == "parsed_agenda_only"
    ]

    if not voting_resolutions:
        return {
            "data_status": (
                "agenda_history_only_no_vote_percentages"
                if agenda_only_resolutions
                else "not_scored_no_resolution_level_voting_data"
            ),
            "meetings_found": len(meetings),
            "meetings_with_parsed_voting_data": 0,
            "meetings_with_agenda_only_history": len(agenda_only_meetings),
            "meetings_without_parseable_data": len(unavailable_meetings),
            "meeting_history_coverage_pct": round(
                (len(agenda_only_meetings) / len(meetings) * 100), 1
            ) if meetings else 0.0,
            "voting_data_coverage_pct": 0.0,
            "parsed_resolution_count": 0,
            "agenda_only_resolution_count": len(agenda_only_resolutions),
            "shareholder_proposal_count": None,
            "three_percent_rule_resolution_count": None,
            "activist_near_miss_count": None,
            "close_management_win_count": None,
            "max_shareholder_proposal_support_pct_votes_cast": None,
            "demonstrated_agm_contestability_score": None,
            "interpretation": (
                "Historical AGM agenda/results were recovered, but vote percentages "
                "were unavailable. No voting-contestability score is inferred."
            ),
        }

    shareholder = [r for r in voting_resolutions if r.get("shareholder_proposal")]
    three_pct = [r for r in voting_resolutions if r.get("three_percent_voting_limit_flag")]
    near = [r for r in voting_resolutions if r.get("activist_near_miss_flag")]
    close = [r for r in voting_resolutions if r.get("close_management_win_flag")]
    max_support = max((r["support_pct_votes_cast"] for r in shareholder), default=None)

    score = min(
        min(len(shareholder) * 3, 20)
        + min(len(three_pct) * 4, 20)
        + min(len(near) * 20, 40)
        + min(len(close) * 10, 20),
        100,
    )

    history_covered = len(voting_meetings) + len(agenda_only_meetings)
    return {
        "data_status": (
            "scored_with_partial_voting_history"
            if len(voting_meetings) < len(meetings)
            else "scored"
        ),
        "meetings_found": len(meetings),
        "meetings_with_parsed_voting_data": len(voting_meetings),
        "meetings_with_agenda_only_history": len(agenda_only_meetings),
        "meetings_without_parseable_data": len(unavailable_meetings),
        "meeting_history_coverage_pct": round(history_covered / len(meetings) * 100, 1) if meetings else 0.0,
        "voting_data_coverage_pct": round(len(voting_meetings) / len(meetings) * 100, 1) if meetings else 0.0,
        "parsed_resolution_count": len(voting_resolutions),
        "agenda_only_resolution_count": len(agenda_only_resolutions),
        "shareholder_proposal_count": len(shareholder),
        "three_percent_rule_resolution_count": len(three_pct),
        "activist_near_miss_count": len(near),
        "close_management_win_count": len(close),
        "max_shareholder_proposal_support_pct_votes_cast": max_support,
        "demonstrated_agm_contestability_score": score,
        "interpretation": (
            "Contestability score uses only meetings with vote percentages. "
            "Older agenda-only meetings are preserved as governance history but do not add zeroes."
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

            parsed_count = sum(
                1 for r in resolutions if r.get("parse_status") == "parsed"
            )

            # Older filings may have agenda/result prose but no vote-percentage table.
            # Recover that history without pretending we know voting margins.
            if not parsed_count and text and not table:
                resolutions = parse_legacy_agenda(text)

            agenda_only_count = sum(
                1 for r in resolutions if r.get("parse_status") == "parsed_agenda_only"
            )

            if parsed_count:
                data_status = "parsed"
            elif agenda_only_count:
                data_status = "agenda_only_no_vote_percentages"
            elif table:
                data_status = "table_found_but_rows_unparseable"
            elif text:
                data_status = "filing_text_found_no_resolution_voting_table"
            else:
                data_status = "no_usable_document_text"

            meetings.append({
                "rcept_no": filing.get("rcept_no"),
                "rcept_dt": filing.get("rcept_dt"),
                "report_nm": normalize(filing.get("report_nm")),
                "meeting_date": parse_meeting_date(text, filing.get("rcept_dt")),
                "data_status": data_status,
                "resolution_count": len(resolutions),
                "parsed_resolution_count": parsed_count,
                "agenda_only_resolution_count": agenda_only_count,
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
        "agm_parser_version": "1.1-full",
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
