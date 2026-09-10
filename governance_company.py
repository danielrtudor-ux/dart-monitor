#!/usr/bin/env python3
"""
Ad-hoc single-company governance runner — v1.2

Adds stale/legacy ticker recovery:
If the requested ticker resolves to a DART corporate record but has no recent
periodic-report governance data, the runner looks for another currently listed
stock code with the exact same corporate name and verifies that it has a recent
periodic report. This is useful for legacy codes after mergers/relistings.

Usage:
  python governance_company.py 005930
  python governance_company.py 000830
  python governance_company.py 005935 --dart-ticker 005930
"""
import argparse
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KST = timezone(timedelta(hours=9))


def clean(v):
    v = str(v or "").strip().upper()
    if not re.fullmatch(r"[0-9A-Z]{6}", v):
        raise SystemExit(f"Invalid ticker: {v!r}")
    return v


def norm_company_name(name):
    """Conservative exact-name normalizer for legacy-ticker recovery."""
    s = re.sub(r"\s+", "", str(name or ""))
    s = s.replace("주식회사", "").replace("(주)", "").replace("㈜", "")
    return s.strip()


def run_raw_collector(gc, ticker, dart_ticker, raw_file, work):
    gc.OUT_DIR = work
    gc.OUT_FILE = raw_file
    gc.load_securities = lambda: [{
        "ticker": ticker,
        "dart_ticker": dart_ticker,
        "label": f"ad-hoc:{ticker}",
    }]
    gc.main()
    return json.loads(raw_file.read_text(encoding="utf-8"))


def recover_legacy_ticker(gc, requested_ticker, initial_company, explicit_dart):
    """
    If the resolved entity has no recent periodic data, look for an exact-name
    listed-company match under another stock code and verify it actually has
    recent structured periodic-report data.

    Never overrides an explicitly supplied --dart-ticker.
    """
    if explicit_dart:
        return None

    overview = initial_company.get("company_overview") or {}
    company_name = overview.get("corp_name") or initial_company.get("company")
    target = norm_company_name(company_name)
    if not target:
        return None

    print(
        f"No recent periodic governance data for {requested_ticker}; "
        f"checking for a current listed code for {company_name}..."
    )

    api_key = os.environ.get("DART_API_KEY")
    corp_map = gc.load_corp_map(api_key)
    now = datetime.now(KST)

    candidates = []
    for stock_code, info in corp_map.items():
        if stock_code == requested_ticker:
            continue
        if norm_company_name(info.get("corp_name")) != target:
            continue

        period = gc.find_latest_periodic_report(api_key, info["corp_code"], now)
        if period:
            # Drop the embedded probe before storing diagnostic metadata.
            period_meta = {
                k: v for k, v in period.items()
                if k != "largest_shareholder_probe"
            }
            candidates.append({
                "stock_code": stock_code,
                "corp_code": info["corp_code"],
                "corp_name": info.get("corp_name"),
                "period": period_meta,
            })

    # Only auto-recover when there is exactly one verified current candidate.
    if len(candidates) == 1:
        return candidates[0]

    if candidates:
        print(
            "Found multiple same-name listed candidates; refusing to guess: "
            + ", ".join(c["stock_code"] for c in candidates)
        )
    return None



def esc(value):
    import html
    return html.escape("" if value is None else str(value))

def render_html(payload):
    profile = payload.get("governance_profile") or {}
    ownership = profile.get("ownership") or {}
    board = profile.get("board") or {}
    scores = (payload.get("provisional_opportunity_assessment") or {}).get("scores") or {}
    agm = (payload.get("agm_analysis") or {}).get("agm_summary") or {}
    signals = (payload.get("provisional_opportunity_assessment") or {}).get("signals") or []
    warnings = payload.get("warnings") or []

    holder_rows = []
    for h in ownership.get("five_percent_holders") or []:
        holder_rows.append(
            f"<tr><td>{esc(h.get('holder'))}</td>"
            f"<td>{esc(h.get('reported_pct'))}</td>"
            f"<td>{esc(h.get('date'))}</td></tr>"
        )
    holders_html = "".join(holder_rows) or "<tr><td colspan='3'>None found</td></tr>"

    signal_html = "".join(f"<li>{esc(x)}</li>" for x in signals) or "<li>None</li>"
    warning_html = "".join(f"<li>{esc(x)}</li>" for x in warnings)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(payload.get('company'))} governance analysis</title>
<style>
body {{ font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; max-width: 980px; margin: 40px auto; padding: 0 20px; line-height: 1.45; }}
h1,h2 {{ margin-top: 1.4em; }}
.grid {{ display:grid; grid-template-columns: repeat(auto-fit,minmax(220px,1fr)); gap:12px; }}
.card {{ border:1px solid #ddd; border-radius:10px; padding:14px; }}
.big {{ font-size:1.5rem; font-weight:700; }}
table {{ border-collapse:collapse; width:100%; }}
th,td {{ border-bottom:1px solid #ddd; padding:8px; text-align:left; }}
code {{ background:#f4f4f4; padding:2px 4px; border-radius:4px; }}
.small {{ color:#666; font-size:.92rem; }}
</style>
</head>
<body>
<h1>{esc(payload.get('company'))}</h1>
<p class="small">Requested ticker: <code>{esc(payload.get('requested_security_ticker'))}</code> ·
Resolved DART ticker: <code>{esc(payload.get('resolved_dart_ticker'))}</code> ·
Generated: {esc(payload.get('generated_at_kst'))}</p>

<div class="grid">
  <div class="card"><div>Overall provisional activist opportunity</div><div class="big">{esc(scores.get('overall_provisional_activist_opportunity'))}</div></div>
  <div class="card"><div>Governance/value-unlock proxy</div><div class="big">{esc(scores.get('governance_value_unlock_proxy'))}</div></div>
  <div class="card"><div>Activist contestability</div><div class="big">{esc(scores.get('activist_contestability'))}</div></div>
  <div class="card"><div>Legal leverage</div><div class="big">{esc(scores.get('legal_leverage'))}</div></div>
</div>

<h2>Ownership</h2>
<p>Controller-related block estimate: <strong>{esc(ownership.get('controller_related_block_pct_estimate'))}%</strong></p>
<table>
<thead><tr><th>5%+ holder</th><th>Reported %</th><th>Date</th></tr></thead>
<tbody>{holders_html}</tbody>
</table>

<h2>Board</h2>
<p>Registered directors: <strong>{esc(board.get('registered_director_count_estimate'))}</strong> ·
Outside/independent directors: <strong>{esc(board.get('outside_director_count_estimate'))}</strong> ·
Outside-director share: <strong>{esc(board.get('outside_director_pct_estimate'))}%</strong></p>

<h2>AGM history</h2>
<p>Meetings found: <strong>{esc(agm.get('meetings_found'))}</strong> ·
Voting-data coverage: <strong>{esc(agm.get('voting_data_coverage_pct'))}%</strong> ·
Historical shareholder proposals: <strong>{esc(agm.get('shareholder_proposal_count'))}</strong> ·
Near-miss votes: <strong>{esc(agm.get('activist_near_miss_count'))}</strong></p>

<h2>Signals</h2>
<ul>{signal_html}</ul>

{("<h2>Warnings</h2><ul>"+warning_html+"</ul>") if warning_html else ""}

<h2>Machine-readable source</h2>
<p><a href="./{esc(payload.get('requested_security_ticker'))}.json">Open JSON</a></p>
<p class="small">This page is a research screen, not investment advice or a legal opinion.</p>
</body>
</html>"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker", nargs="?")
    ap.add_argument("--dart-ticker")
    a = ap.parse_args()

    ticker = clean(a.ticker or os.environ.get("COMPANY_TICKER"))
    explicit = a.dart_ticker or os.environ.get("DART_TICKER")
    explicit = clean(explicit) if explicit else None

    import governance_collector as gc
    import governance_analyzer as ga
    import agm_collector as ac
    import agm_parser as agp
    import activist_ranker as ar

    initial_dart = explicit or gc.DART_TICKER_OVERRIDES.get(ticker, ticker)
    resolved_dart = initial_dart
    recovery = None

    work = ROOT / "governance" / "ad_hoc" / ticker
    work.mkdir(parents=True, exist_ok=True)

    raw = work / "governance_company.json"
    prof = work / "governance_profile.json"
    filings = work / "agm_filings.json"
    votes = work / "agm_votes.json"
    rank = work / "governance_ranking.json"

    print(f"Ad-hoc governance analysis: security={ticker}, DART ticker={initial_dart}")

    r = run_raw_collector(gc, ticker, initial_dart, raw, work)
    if not r.get("companies"):
        hint = "" if explicit else (
            " If this is a preferred/share-class security, rerun with its "
            "underlying ordinary-share ticker in the DART ticker field."
        )
        raise SystemExit(
            f"OpenDART could not resolve {ticker} (DART ticker {initial_dart}).{hint}"
        )

    company = r["companies"][0]

    # A legacy ticker can still resolve to an old DART entity, but all periodic
    # endpoints will return NO_PERIOD. Recover to a verified current listed code.
    if company.get("period_used") is None:
        recovery = recover_legacy_ticker(gc, ticker, company, explicit)
        if recovery:
            resolved_dart = recovery["stock_code"]
            print(
                f"Legacy/stale ticker recovery: {ticker} -> current DART stock code "
                f"{resolved_dart} ({recovery['corp_name']})"
            )
            r = run_raw_collector(gc, ticker, resolved_dart, raw, work)
            company = r["companies"][0]

    ga.RAW_FILE = raw
    ga.OUT_FILE = prof
    ga.main()

    ac.RAW_FILE = raw
    ac.OUT_FILE = filings
    ac.main()

    agp.IN_FILE = filings
    agp.OUT_FILE = votes
    agp.main()

    ar.GOV = prof
    ar.AGM = votes
    ar.OUT = rank
    ar.main()

    pj = json.loads(prof.read_text(encoding="utf-8"))
    vj = json.loads(votes.read_text(encoding="utf-8"))
    rj = json.loads(rank.read_text(encoding="utf-8"))

    profile = (pj.get("profiles") or [None])[0]
    agm = (vj.get("companies") or [None])[0]
    rr = (rj.get("rankings") or [None])[0]

    warnings = []
    if recovery:
        warnings.append(
            f"Requested ticker {ticker} appears to be a legacy/stale code. "
            f"Analysis was run against verified current DART stock code "
            f"{resolved_dart} for the same corporate name."
        )
    elif company.get("period_used") is None:
        warnings.append(
            "The company resolved in DART but no recent structured periodic-report "
            "governance data was found. Scores may therefore remain N/A."
        )

    payload = {
        "ad_hoc_report_version": "1.2",
        "generated_at_kst": datetime.now(KST).isoformat(),
        "requested_security_ticker": ticker,
        "resolved_dart_ticker": resolved_dart,
        "legacy_ticker_recovery": recovery,
        "company": (profile or {}).get("company"),
        "warnings": warnings,
        "purpose": (
            "Single-company governance / activist-opportunity research using the "
            "same DART framework as the monitored universe."
        ),
        "governance_profile": profile,
        "agm_analysis": agm,
        "provisional_opportunity_assessment": rr,
        "caveats": [
            "Investment-research screen; not investment advice or a legal opinion.",
            "Governance/value-unlock score is a DART-derived governance proxy, not a valuation model.",
            "High-priority companies still require manual review of valuation, articles, friendly blocks, NPS/institutional ownership, current law and case law.",
        ],
    }

    pub = ROOT / "docs" / "governance"
    pub.mkdir(parents=True, exist_ok=True)

    for f in (pub / f"{ticker}.json", pub / "latest.json"):
        f.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    html_text = render_html(payload)
    (pub / f"{ticker}.html").write_text(html_text, encoding="utf-8")
    (pub / "latest.html").write_text(html_text, encoding="utf-8")

    print(f"Wrote {pub / f'{ticker}.json'}")
    print(f"Wrote {pub / f'{ticker}.html'}")
    if rr:
        print(
            "Overall provisional activist opportunity:",
            rr.get("scores", {}).get("overall_provisional_activist_opportunity"),
            "|",
            rr.get("review_band"),
        )


if __name__ == "__main__":
    main()
