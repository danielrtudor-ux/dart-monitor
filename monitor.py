#!/usr/bin/env python3
import json
import os
import sys
import urllib.parse
import urllib.request
import zipfile
import io
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = "https://opendart.fss.or.kr/api"
KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent
TICKER_FILE = ROOT / "tickers.txt"
OUT_DIR = ROOT / "docs"
OUT_FILE = OUT_DIR / "dart-latest.json"
# Preferred-share / security-class ticker -> underlying ordinary-share ticker
DART_TICKER_ALIASES = {
    "004365": "004360",
    "002355": "002350",
    "00088K": "000880",
    "37550K": "375500",
    "006405": "006400",
    "000215": "000210",
    "000155": "000150",
    "005387": "005380",
    "011785": "011780",
    "145995": "145990",
    "005725": "005720",
}

def get_bytes(url, params):
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"{url}?{qs}",
        headers={"User-Agent": "dart-monitor/1.0"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()

def get_json(url, params):
    return json.loads(get_bytes(url, params).decode("utf-8"))

def load_corp_map(api_key):
    raw = get_bytes(f"{BASE}/corpCode.xml", {"crtfc_key": api_key})
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        xml_data = zf.read("CORPCODE.xml")
    root = ET.fromstring(xml_data)
    mapping = {}
    for item in root.findall("list"):
        stock_code = (item.findtext("stock_code") or "").strip()
        if not stock_code:
            continue
        mapping[stock_code] = {
            "corp_code": (item.findtext("corp_code") or "").strip(),
            "corp_name": (item.findtext("corp_name") or "").strip(),
            "modify_date": (item.findtext("modify_date") or "").strip(),
        }
    return mapping

def load_tickers():
    vals = []
    seen = set()
    for line in TICKER_FILE.read_text(encoding="utf-8").splitlines():
        t = line.strip()
        if not t or t.startswith("#") or t in seen:
            continue
        seen.add(t)
        vals.append(t)
    return vals

def fetch_filings(api_key, corp_code, start_date, end_date):
    filings = []
    page_no = 1
    while True:
        data = get_json(
            f"{BASE}/list.json",
            {
                "crtfc_key": api_key,
                "corp_code": corp_code,
                "bgn_de": start_date,
                "end_de": end_date,
                "page_no": page_no,
                "page_count": 100,
            },
        )
        status = data.get("status")
        if status == "013":  # no data
            return []
        if status != "000":
            raise RuntimeError(f"DART error {status}: {data.get('message')}")
        filings.extend(data.get("list", []))
        total_page = int(data.get("total_page", 1))
        if page_no >= total_page:
            break
        page_no += 1
    return filings

def main():
    api_key = os.environ.get("DART_API_KEY")
    if not api_key:
        print("Missing DART_API_KEY environment variable", file=sys.stderr)
        sys.exit(2)

    now = datetime.now(KST)
    # A 3-day lookback makes the feed resilient to weekends, holidays,
    # delayed GitHub Actions runs and an occasional failed run.
    start = (now.date() - timedelta(days=3)).strftime("%Y%m%d")
    end = now.date().strftime("%Y%m%d")

    tickers = load_tickers()
    corp_map = load_corp_map(api_key)

    results = []
    unresolved = []

   for ticker in tickers:
    dart_ticker = DART_TICKER_ALIASES.get(ticker, ticker)
    info = corp_map.get(dart_ticker)

    if not info:
        unresolved.append(ticker)
        continue
        try:
            filings = fetch_filings(api_key, info["corp_code"], start, end)
        except Exception as exc:
            results.append({
                "ticker": ticker,
                "company": info["corp_name"],
                "corp_code": info["corp_code"],
                "error": str(exc),
                "filings": [],
            })
            continue

        cleaned = []
        for f in filings:
            rcept_no = f.get("rcept_no", "")
            cleaned.append({
                "rcept_no": rcept_no,
                "report_nm": f.get("report_nm"),
                "rcept_dt": f.get("rcept_dt"),
                "flr_nm": f.get("flr_nm"),
                "corp_cls": f.get("corp_cls"),
                "rm": f.get("rm"),
                "dart_url": (
                    f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
                    if rcept_no else None
                ),
            })

        if cleaned:
            results.append({
                "ticker": ticker,
                "company": info["corp_name"],
                "corp_code": info["corp_code"],
                "filings": cleaned,
            })

    payload = {
        "generated_at_kst": now.isoformat(),
        "window": {"start": start, "end": end},
        "ticker_count": len(tickers),
        "companies_with_filings": len([x for x in results if x.get("filings")]),
        "unresolved_tickers": unresolved,
        "results": results,
    }

    OUT_DIR.mkdir(exist_ok=True)
    OUT_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUT_FILE}")
    print(f"Tickers: {len(tickers)} | unresolved: {len(unresolved)} | companies with filings: {payload['companies_with_filings']}")

if __name__ == "__main__":
    main()
