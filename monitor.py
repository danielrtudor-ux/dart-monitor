#!/usr/bin/env python3
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import zipfile
import io
import html
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

# Filing titles that are especially likely to matter for valuation.
VALUATION_KEYWORDS = [
    "단일판매", "공급계약", "신규시설투자", "시설투자", "금전대여",
    "타법인주식", "타법인증권", "유형자산", "영업양수", "영업양도",
    "합병", "분할", "주식교환", "주식이전", "유상증자", "무상증자",
    "전환사채", "신주인수권", "교환사채", "조건부자본", "채무증권",
    "자기주식", "배당", "감자", "회생", "파산", "소송", "횡령",
    "배임", "최대주주", "대량보유", "임원", "주요주주",
    "매출액", "손익구조", "영업이익", "분기보고서", "반기보고서",
    "사업보고서", "기재정정", "풍문", "보도에대한해명",
]

# Terms around which we preserve text from the original filing.
FOCUS_TERMS = [
    "계약금액", "계약기간", "계약상대", "최근매출액", "매출액대비",
    "투자금액", "자기자본", "자기자본대비", "투자기간", "투자목적",
    "대여금액", "대여기간", "이율", "담보", "채무자",
    "취득금액", "처분금액", "취득목적", "처분목적",
    "발행금액", "발행총액", "발행가액", "이자율", "만기",
    "전환가액", "행사가액", "희석", "배당금", "배당성향",
    "취득주식수", "처분주식수", "보유주식수", "보유비율",
    "변동전", "변동후", "지분율", "최대주주",
    "정정사유", "정정전", "정정후",
    "매출액", "영업이익", "당기순이익", "자산총계", "부채총계",
]

def get_bytes(url, params):
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"{url}?{qs}",
        headers={"User-Agent": "dart-monitor/2.0"}
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
        if status == "013":
            return []
        if status != "000":
            raise RuntimeError(f"DART error {status}: {data.get('message')}")
        filings.extend(data.get("list", []))
        total_page = int(data.get("total_page", 1))
        if page_no >= total_page:
            break
        page_no += 1
    return filings

def is_valuation_relevant_title(report_name):
    name = report_name or ""
    return any(k in name for k in VALUATION_KEYWORDS)

def strip_markup(raw_text):
    # Remove scripts/styles and tags while preserving table cell separation reasonably well.
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw_text)
    text = re.sub(r"(?i)</?(tr|p|div|br|li|table|h[1-6])[^>]*>", "\n", text)
    text = re.sub(r"(?i)</?(td|th)[^>]*>", " | ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()

def decode_document_bytes(data):
    for enc in ("utf-8", "euc-kr", "cp949"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace")

def fetch_original_document_text(api_key, rcept_no):
    raw = get_bytes(
        f"{BASE}/document.xml",
        {"crtfc_key": api_key, "rcept_no": rcept_no},
    )
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        return ""

    texts = []
    # Prefer XML/HTML/TXT documents and ignore images/binaries.
    candidates = [
        n for n in zf.namelist()
        if n.lower().endswith((".xml", ".html", ".htm", ".txt"))
    ]
    # Put likely main document files first.
    candidates.sort(key=lambda n: (
        0 if ("main" in n.lower() or "document" in n.lower()) else 1,
        len(n)
    ))

    for name in candidates[:8]:
        try:
            decoded = decode_document_bytes(zf.read(name))
            cleaned = strip_markup(decoded)
            if cleaned:
                texts.append(cleaned)
        except Exception:
            continue

    return "\n".join(texts)

def make_focused_excerpt(text, max_chars=12000):
    if not text:
        return None

    hits = []
    lower = text.lower()
    for term in FOCUS_TERMS:
        pos = lower.find(term.lower())
        if pos >= 0:
            start = max(0, pos - 600)
            end = min(len(text), pos + 1800)
            hits.append(text[start:end])

    if hits:
        # Deduplicate overlapping/repeated windows.
        unique = []
        seen = set()
        for h in hits:
            key = h[:250]
            if key not in seen:
                seen.add(key)
                unique.append(h)
        excerpt = "\n---\n".join(unique)
    else:
        excerpt = text[:max_chars]

    return excerpt[:max_chars]

def extract_number_lines(excerpt, max_items=30):
    if not excerpt:
        return []

    interesting = []
    amount_pattern = re.compile(
        r"(?:₩|원|억원|백만원|천만원|조원|%|퍼센트|주|개월|년|bp|bps|배)"
    )
    for line in excerpt.splitlines():
        line = line.strip(" |")
        if len(line) < 5 or len(line) > 500:
            continue
        if not re.search(r"\d", line):
            continue
        if (
            amount_pattern.search(line)
            or any(term in line for term in FOCUS_TERMS)
        ):
            interesting.append(line)

    # preserve order and remove duplicates
    out = []
    seen = set()
    for item in interesting:
        if item not in seen:
            seen.add(item)
            out.append(item)
        if len(out) >= max_items:
            break
    return out

def main():
    api_key = os.environ.get("DART_API_KEY")
    if not api_key:
        print("Missing DART_API_KEY environment variable", file=sys.stderr)
        sys.exit(2)

    now = datetime.now(KST)
    # Three-day lookback protects against weekends, holidays, delayed Actions runs.
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
                "dart_ticker": dart_ticker,
                "company": info["corp_name"],
                "corp_code": info["corp_code"],
                "error": str(exc),
                "filings": [],
            })
            continue

        cleaned = []

        for f in filings:
            rcept_no = f.get("rcept_no", "")
            report_nm = (f.get("report_nm") or "").strip()
            filing = {
                "rcept_no": rcept_no,
                "report_nm": report_nm,
                "rcept_dt": f.get("rcept_dt"),
                "flr_nm": f.get("flr_nm"),
                "corp_cls": f.get("corp_cls"),
                "rm": f.get("rm"),
                "dart_url": (
                    f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
                    if rcept_no else None
                ),
                "valuation_relevant_title": is_valuation_relevant_title(report_nm),
            }

            # For likely valuation-relevant filings, fetch the underlying filing text.
            if rcept_no and filing["valuation_relevant_title"]:
                try:
                    doc_text = fetch_original_document_text(api_key, rcept_no)
                    excerpt = make_focused_excerpt(doc_text)
                    filing["document_excerpt"] = excerpt
                    filing["number_lines"] = extract_number_lines(excerpt)
                except Exception as exc:
                    filing["document_error"] = str(exc)

            cleaned.append(filing)

        if cleaned:
            results.append({
                "ticker": ticker,
                "dart_ticker": dart_ticker,
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
        "collector_version": "2.0-original-doc-extraction",
        "results": results,
    }

    OUT_DIR.mkdir(exist_ok=True)
    OUT_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUT_FILE}")
    print(
        f"Tickers: {len(tickers)} | unresolved: {len(unresolved)} | "
        f"companies with filings: {payload['companies_with_filings']}"
    )

if __name__ == "__main__":
    main()
