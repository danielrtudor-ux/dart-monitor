#!/usr/bin/env python3
"""
OpenDART governance collector — v0.1 test

Purpose:
  Collect raw governance/ownership data for a SMALL test universe before
  scaling to the full portfolio.

Output:
  governance/governance_companies_test.json

Uses the same DART_API_KEY GitHub secret as monitor.py.
"""

import io
import json
import os
import sys
import urllib.parse
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = "https://opendart.fss.or.kr/api"
KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "governance"
OUT_FILE = OUT_DIR / "governance_companies_test.json"

# Deliberately small and varied first test.
# Preferred shares are mapped to the underlying company's ordinary-share code.
TEST_SECURITIES = [
    {"ticker": "003240", "dart_ticker": "003240", "label": "Taekwang Industrial"},
    {"ticker": "035720", "dart_ticker": "035720", "label": "Kakao"},
    {"ticker": "055550", "dart_ticker": "055550", "label": "Shinhan Financial Group"},
    {"ticker": "000155", "dart_ticker": "000150", "label": "Doosan preferred / Doosan underlying"},
    {"ticker": "004365", "dart_ticker": "004360", "label": "Sebang preferred / Sebang underlying"},
]

REPORT_CODES = [
    ("11014", "Q3"),
    ("11012", "H1"),
    ("11013", "Q1"),
    ("11011", "Annual"),
]

def get_bytes(url, params):
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"{url}?{qs}",
        headers={"User-Agent": "dart-governance-monitor/0.1"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()

def get_json(endpoint, params):
    raw = get_bytes(f"{BASE}/{endpoint}", params)
    return json.loads(raw.decode("utf-8"))

def load_corp_map(api_key):
    raw = get_bytes(f"{BASE}/corpCode.xml", {"crtfc_key": api_key})
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        xml_data = zf.read("CORPCODE.xml")
    root = ET.fromstring(xml_data)
    mapping = {}
    for item in root.findall("list"):
        stock_code = (item.findtext("stock_code") or "").strip()
        if stock_code:
            mapping[stock_code] = {
                "corp_code": (item.findtext("corp_code") or "").strip(),
                "corp_name": (item.findtext("corp_name") or "").strip(),
            }
    return mapping

def dart_call(endpoint, api_key, corp_code, extra=None):
    params = {"crtfc_key": api_key, "corp_code": corp_code}
    if extra:
        params.update(extra)
    try:
        data = get_json(endpoint, params)
    except Exception as exc:
        return {"status": "LOCAL_ERROR", "message": str(exc), "list": []}

    status = data.get("status")
    if status == "000":
        return {
            "status": status,
            "message": data.get("message"),
            "list": data.get("list", []),
        }
    if status in ("013", "014"):
        return {"status": status, "message": data.get("message"), "list": []}
    return {
        "status": status,
        "message": data.get("message"),
        "list": data.get("list", []),
    }

def find_latest_periodic_report(api_key, corp_code, now):
    """
    Try current year and previous year, newest report type first.
    We use the first period for which the largest-shareholder endpoint returns data.
    The same year/report code is then used for other periodic-report endpoints.
    """
    for year in (now.year, now.year - 1):
        for reprt_code, label in REPORT_CODES:
            probe = dart_call(
                "hyslrSttus.json",
                api_key,
                corp_code,
                {"bsns_year": str(year), "reprt_code": reprt_code},
            )
            if probe["status"] == "000" and probe["list"]:
                return {
                    "bsns_year": str(year),
                    "reprt_code": reprt_code,
                    "report_label": label,
                    "largest_shareholder_probe": probe,
                }
    return None

def periodic(endpoint, api_key, corp_code, period):
    if not period:
        return {"status": "NO_PERIOD", "message": "No recent periodic report found", "list": []}
    return dart_call(
        endpoint,
        api_key,
        corp_code,
        {
            "bsns_year": period["bsns_year"],
            "reprt_code": period["reprt_code"],
        },
    )

def company_overview(api_key, corp_code):
    try:
        data = get_json(
            "company.json",
            {"crtfc_key": api_key, "corp_code": corp_code},
        )
        # company.json returns fields at top level, not list.
        return data
    except Exception as exc:
        return {"status": "LOCAL_ERROR", "message": str(exc)}

def main():
    api_key = os.environ.get("DART_API_KEY")
    if not api_key:
        print("Missing DART_API_KEY environment variable", file=sys.stderr)
        sys.exit(2)

    now = datetime.now(KST)
    corp_map = load_corp_map(api_key)
    companies = []
    unresolved = []

    for security in TEST_SECURITIES:
        ticker = security["ticker"]
        dart_ticker = security["dart_ticker"]
        info = corp_map.get(dart_ticker)

        if not info:
            unresolved.append(security)
            continue

        corp_code = info["corp_code"]
        period = find_latest_periodic_report(api_key, corp_code, now)

        # Reuse the probe result so we do not make the largest-shareholder call twice.
        largest_shareholders = (
            period.pop("largest_shareholder_probe")
            if period and "largest_shareholder_probe" in period
            else {"status": "NO_PERIOD", "message": "No recent periodic report found", "list": []}
        )

        company = {
            "security_ticker": ticker,
            "dart_ticker": dart_ticker,
            "company": info["corp_name"],
            "corp_code": corp_code,
            "test_label": security["label"],
            "period_used": period,
            "company_overview": company_overview(api_key, corp_code),

            # Periodic-report structured data
            "largest_shareholders": largest_shareholders,
            "minority_shareholders": periodic("mrhlSttus.json", api_key, corp_code, period),
            "total_shares": periodic("stockTotqySttus.json", api_key, corp_code, period),
            "treasury_share_activity": periodic("tesstkAcqsDspsSttus.json", api_key, corp_code, period),
            "executives": periodic("exctvSttus.json", api_key, corp_code, period),

            # Ownership filings are not tied to a periodic-report year/code.
            "major_5pct_filings": dart_call("majorstock.json", api_key, corp_code),
            "executive_major_shareholder_filings": dart_call("elestock.json", api_key, corp_code),
        }

        # Basic diagnostics only. No activist score yet.
        company["diagnostics"] = {
            "has_largest_shareholder_data": bool(company["largest_shareholders"]["list"]),
            "has_minority_shareholder_data": bool(company["minority_shareholders"]["list"]),
            "has_total_share_data": bool(company["total_shares"]["list"]),
            "has_treasury_share_data": bool(company["treasury_share_activity"]["list"]),
            "has_executive_data": bool(company["executives"]["list"]),
            "has_5pct_filings": bool(company["major_5pct_filings"]["list"]),
            "has_exec_major_holder_filings": bool(company["executive_major_shareholder_filings"]["list"]),
        }
        companies.append(company)
        print(f"Collected {ticker} -> {info['corp_name']}")

    payload = {
        "collector_version": "0.1-test",
        "generated_at_kst": now.isoformat(),
        "purpose": "Raw governance data validation only; no activist or legal score yet.",
        "test_company_count": len(TEST_SECURITIES),
        "resolved_company_count": len(companies),
        "unresolved": unresolved,
        "companies": companies,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUT_FILE}")

if __name__ == "__main__":
    main()
