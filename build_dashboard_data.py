#!/usr/bin/env python3
"""Build the small, browser-facing valuation feed from the full audit dataset."""
import json
from pathlib import Path

ROOT = Path(__file__).parent
DOCS = ROOT / "docs"


def build(valuation, audit):
    audited = {row["ticker"]: row for row in audit.get("results", [])}
    rows = []
    for result in valuation.get("results", []):
        market = result.get("market") or {}
        basis = result.get("financial_basis") or {}
        fundamentals = result.get("fundamentals") or {}
        ratios = result.get("ratios") or {}
        ownership = result.get("ownership") or {}
        audit_row = audited.get(result.get("ticker"), {})
        flags = audit_row.get("flags", [])
        bridge = result.get("ttm_bridge") or {}
        earnings = bridge.get(bridge.get("earnings_key", "pni"), {})
        source = ((earnings.get("current_cumulative") or {}).get("source") or {})
        dcf_base = (((result.get("dcf") or {}).get("scenarios") or {}).get("base") or {}).get("value_per_share")
        price = market.get("price")
        rows.append({
            "ticker": result.get("ticker"),
            "company": result.get("company"),
            "type": result.get("company_type"),
            "exchange": market.get("exchange"),
            "price": price,
            "market_cap": market.get("market_cap"),
            "traded_at": market.get("traded_at"),
            "basis": basis.get("latest_earnings"),
            "balance_sheet": basis.get("latest_balance_sheet"),
            "fs_div": basis.get("fs_div"),
            "currency": basis.get("accounting_currency"),
            "revenue_ttm": fundamentals.get("revenue_ttm"),
            "operating_profit_ttm": fundamentals.get("operating_profit_ttm"),
            "pretax_income_ttm": fundamentals.get("pretax_income_ttm"),
            "common_income_ttm": fundamentals.get("common_net_income_ttm"),
            "equity": fundamentals.get("equity_latest"),
            "cash_like": fundamentals.get("cash_like_latest"),
            "debt": fundamentals.get("debt_latest"),
            "net_cash": fundamentals.get("usable_net_cash_latest") if fundamentals.get("usable_net_cash_latest") is not None else fundamentals.get("net_cash_latest"),
            "cash_review": fundamentals.get("cash_review_status"),
            "debt_status": fundamentals.get("debt_status"),
            "pe": ratios.get("pe"),
            "pb": ratios.get("pb"),
            "ev_ebit": ratios.get("ev_to_ebit"),
            "ex_cash_pe": ratios.get("ex_net_cash_pe"),
            "roe": ratios.get("roe_simple"),
            "operating_margin": ratios.get("operating_margin"),
            "net_cash_pct": ratios.get("net_cash_pct_market_cap"),
            "dcf_value": dcf_base,
            "dcf_upside": (dcf_base / price - 1) if dcf_base is not None and price else None,
            "quality": audit_row.get("quality", "review"),
            "flags": flags,
            "warnings": result.get("warnings", []),
            "nci_proxy": ownership.get("nci_ev_proxy"),
            "preferred_shares": basis.get("preferred_shares_outstanding"),
            "filing_url": source.get("filing_url"),
        })
    return {
        "generated_at_kst": valuation.get("generated_at_kst"),
        "engine_version": valuation.get("engine_version"),
        "company_count": len(rows),
        "error_count": valuation.get("error_count"),
        "flag_counts": audit.get("flag_counts", {}),
        "results": rows,
    }


def main():
    result = build(
        json.loads((DOCS / "valuation-latest.json").read_text()),
        json.loads((DOCS / "valuation-audit.json").read_text()),
    )
    (DOCS / "dashboard-data.json").write_text(
        json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n"
    )
    print("Wrote", DOCS / "dashboard-data.json", len(result["results"]), "companies")


if __name__ == "__main__":
    main()
