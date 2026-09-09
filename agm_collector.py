#!/usr/bin/env python3
"""
AGM collector — v0.1 test

Reads:
  governance/governance_companies_test.json

Writes:
  governance/agm_filings_test.json

Purpose:
  Search OpenDART for AGM-result disclosures for the five-company test set,
  download the original filing packages, and extract candidate text/snippets
  needed for later voting-turnout analysis.

This version is intentionally a collector, not a final parser. It preserves
receipt numbers, titles and candidate AGM text so we can validate DART's
document formats before calculating voting vulnerability.
"""

import io
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from html import unescape

BASE = "https://opendart.fss.or.kr/api"
KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent
RAW_FILE = ROOT / "governance" / "governance_companies_test.json"
OUT_FILE = ROOT / "governance" / "agm_filings_test.json"

AGM_TITLE_TERMS = (
    "정기주주총회결과",
    "주주총회결과",
    "정기주주총회 결과",
)

KEY_TERMS = (
    "의결권 있는 발행주식총수",
    "의결권있는 발행주식총수",
    "출석주식수",
    "출석 주식수",
    "출석률",
    "찬성",
    "반대",
    "기권",
    "감사위원",
    "사외이사",
    "독립이사",
    "이사선임",
    "이사 선임",
)

def get_bytes(url, params):
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"{url}?{qs}",
        headers={"User-Agent": "dart-governance-agm-monitor/0.1"},
    )
    with urllib.request.urlopen(req, timeout=40) as resp:
        return resp.read()

def get_json(endpoint, params):
    raw = get_bytes(f"{BASE}/{endpoint}", params)
    return json.loads(raw.decode("utf-8"))

def strip_markup(text):
    text = unescape(text)
    text = re.sub(r"(?is)<script.*?</script>", " ", text)
    text = re.sub(r"(?is)<style.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;?", " ", text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()

def decode_document(raw):
    for enc in ("utf-8", "cp949", "euc-kr"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", errors="replace")

def search_filings(api_key, corp_code, begin, end):
    found = []
    page = 1
    while page <= 10:
        data = get_json(
            "list.json",
            {
                "crtfc_key": api_key,
                "corp_code": corp_code,
                "bgn_de": begin,
                "end_de": end,
                "page_no": page,
                "page_count": 100,
            },
        )
        if data.get("status") == "013":
            break
        if data.get("status") != "000":
            return {"status": data.get("status"), "message": data.get("message"), "list": found}

        items = data.get("list", [])
        found.extend(items)

        total_page = int(data.get("total_page") or 1)
        if page >= total_page:
            break
        page += 1

    return {"status": "000", "message": "OK", "list": found}

def is_agm_result_title(title):
    title = re.sub(r"\s+", "", str(title or ""))
    return any(re.sub(r"\s+", "", term) in title for term in AGM_TITLE_TERMS)

def download_original(api_key, rcept_no):
    return get_bytes(
        f"{BASE}/document.xml",
        {"crtfc_key": api_key, "rcept_no": rcept_no},
    )

def extract_zip_text(blob):
    docs = []
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            for name in zf.namelist():
                if name.endswith("/"):
                    continue
                raw = zf.read(name)
                decoded = decode_document(raw)
                plain = strip_markup(decoded)
                if plain:
                    docs.append({"filename": name, "text": plain})
    except zipfile.BadZipFile:
        decoded = decode_document(blob)
        plain = strip_markup(decoded)
        if plain:
            docs.append({"filename": "document", "text": plain})
    return docs

def candidate_snippets(text, radius=700):
    snippets = []
    compact = re.sub(r"\s+", " ", text)
    for term in KEY_TERMS:
        start = 0
        while True:
            idx = compact.find(term, start)
            if idx < 0:
                break
            lo = max(0, idx - radius)
            hi = min(len(compact), idx + len(term) + radius)
            snippet = compact[lo:hi].strip()
            snippets.append({"matched_term": term, "snippet": snippet})
            start = idx + len(term)
            if len(snippets) >= 40:
                return snippets
    return snippets

def extract_simple_metrics(text):
    """
    Conservative first-pass regexes. These are candidate values only.
    The raw snippets remain in the output for manual verification.
    """
    compact = re.sub(r"\s+", " ", text)
    metrics = {}

    patterns = {
        "voting_shares_candidate": [
            r"의결권\s*있는\s*발행주식총수[^0-9]{0,80}([0-9][0-9,]*)",
            r"의결권있는\s*발행주식총수[^0-9]{0,80}([0-9][0-9,]*)",
        ],
        "attending_shares_candidate": [
            r"출석\s*주식수[^0-9]{0,80}([0-9][0-9,]*)",
            r"출석주식수[^0-9]{0,80}([0-9][0-9,]*)",
        ],
        "attendance_rate_candidate": [
            r"출석률[^0-9]{0,40}([0-9]+(?:\.[0-9]+)?)\s*%",
        ],
    }

    for key, pats in patterns.items():
        for pat in pats:
            m = re.search(pat, compact)
            if m:
                val = m.group(1).replace(",", "")
                metrics[key] = float(val) if "." in val else int(val)
                break

    if (
        "attendance_rate_candidate" not in metrics
        and metrics.get("voting_shares_candidate")
        and metrics.get("attending_shares_candidate")
    ):
        voting = metrics["voting_shares_candidate"]
        attending = metrics["attending_shares_candidate"]
        if voting > 0 and attending <= voting:
            metrics["attendance_rate_calculated_candidate"] = round(attending / voting * 100, 3)

    return metrics

def main():
    api_key = os.environ.get("DART_API_KEY")
    if not api_key:
        print("Missing DART_API_KEY environment variable", file=sys.stderr)
        sys.exit(2)

    if not RAW_FILE.exists():
        raise SystemExit(f"Missing {RAW_FILE}")

    raw = json.loads(RAW_FILE.read_text(encoding="utf-8"))
    now = datetime.now(KST)

    # Cover the 2024, 2025 and 2026 AGM seasons, with some buffer.
    begin = "20240101"
    end = now.strftime("%Y%m%d")

    companies_out = []

    for company in raw.get("companies", []):
        corp_code = company["corp_code"]
        search = search_filings(api_key, corp_code, begin, end)

        agm_items = []
        for item in search.get("list", []):
            title = item.get("report_nm", "")
            if not is_agm_result_title(title):
                continue

            rcept_no = item.get("rcept_no")
            filing = {
                "rcept_no": rcept_no,
                "report_nm": title,
                "rcept_dt": item.get("rcept_dt"),
                "flr_nm": item.get("flr_nm"),
                "rm": item.get("rm"),
                "document_status": None,
                "documents": [],
                "candidate_metrics": {},
            }

            if rcept_no:
                try:
                    blob = download_original(api_key, rcept_no)
                    docs = extract_zip_text(blob)
                    filing["document_status"] = "downloaded"
                    all_text = "\n".join(d["text"] for d in docs)
                    filing["candidate_metrics"] = extract_simple_metrics(all_text)

                    for d in docs:
                        snippets = candidate_snippets(d["text"])
                        if snippets:
                            filing["documents"].append(
                                {
                                    "filename": d["filename"],
                                    "text_length": len(d["text"]),
                                    "snippets": snippets,
                                }
                            )
                except Exception as exc:
                    filing["document_status"] = f"error: {exc}"

            agm_items.append(filing)

        companies_out.append(
            {
                "security_ticker": company.get("security_ticker"),
                "dart_ticker": company.get("dart_ticker"),
                "company": company.get("company"),
                "corp_code": corp_code,
                "search_status": search.get("status"),
                "search_message": search.get("message"),
                "agm_result_filing_count": len(agm_items),
                "agm_result_filings": agm_items,
            }
        )
        print(company.get("security_ticker"), company.get("company"), len(agm_items))

    payload = {
        "agm_collector_version": "0.1-test",
        "generated_at_kst": now.isoformat(),
        "search_period": {"begin": begin, "end": end},
        "purpose": "Validate extraction of historical AGM-result filings and candidate turnout/voting fields before building AGM contestability scores.",
        "important_note": "candidate_metrics are regex-extracted research candidates, not verified voting figures. Verify against preserved filing snippets before using them in investment analysis.",
        "company_count": len(companies_out),
        "companies": companies_out,
    }

    OUT_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUT_FILE}")

if __name__ == "__main__":
    main()
