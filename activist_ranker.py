#!/usr/bin/env python3
"""
Provisional activist-opportunity ranker — v0.1

Combines:
  governance/governance_profiles.json
  governance/agm_votes.json

Writes:
  governance/governance_rankings.json

This is an investment-research SCREEN, not investment advice or a legal opinion.
It intentionally keeps component scores separate and marks unavailable data N/A.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GOV = ROOT / "governance" / "governance_profiles.json"
AGM = ROOT / "governance" / "agm_votes.json"
OUT = ROOT / "governance" / "governance_rankings.json"
KST = timezone(timedelta(hours=9))

def clamp(x):
    return None if x is None else round(max(0.0, min(100.0, float(x))), 1)

def weighted(parts):
    usable=[(v,w) for v,w in parts if v is not None]
    if not usable:
        return None
    return round(sum(v*w for v,w in usable)/sum(w for _,w in usable),1)

def band(score):
    if score is None: return "N/A"
    if score >= 70: return "high-priority review"
    if score >= 55: return "promising"
    if score >= 40: return "watchlist"
    return "lower demonstrated opportunity"

def main():
    gov=json.loads(GOV.read_text(encoding="utf-8"))
    agm=json.loads(AGM.read_text(encoding="utf-8"))
    agm_by={(x.get("security_ticker"),x.get("corp_code")):x for x in agm.get("companies",[])}

    rows=[]
    for g in gov.get("profiles",[]):
        key=(g.get("security_ticker"),g.get("corp_code"))
        av=agm_by.get(key,{})
        asum=av.get("agm_summary",{})
        ps=g.get("preliminary_research_scores",{})

        controller=ps.get("controller_vulnerability_raw_ownership")
        treasury=ps.get("treasury_share_legal_leverage")
        board=ps.get("board_independence_weakness")
        agm_score=asum.get("demonstrated_agm_contestability_score")

        # Proxy for governance/value-unlock potential from DART-observable governance
        # structure. It is NOT a valuation score: valuation/fundamentals come later.
        value_unlock_proxy=weighted([
            (treasury,0.50),
            (board,0.30),
            (controller,0.20),
        ])

        activist_contestability=weighted([
            (agm_score,0.60),
            (controller,0.40),
        ])

        three_pct=asum.get("three_percent_rule_resolution_count")
        legal_leverage=weighted([
            (treasury,0.55),
            (100 if (three_pct or 0)>0 else (0 if three_pct is not None else None),0.45),
        ])

        overall=weighted([
            (value_unlock_proxy,0.35),
            (activist_contestability,0.40),
            (legal_leverage,0.25),
        ])

        flags=[]
        if (asum.get("activist_near_miss_count") or 0)>0:
            flags.append("historical activist/outsider near-miss vote")
        if (asum.get("close_management_win_count") or 0)>0:
            flags.append("close management AGM win")
        if (asum.get("shareholder_proposal_count") or 0)>0:
            flags.append("shareholder proposals observed")
        if (three_pct or 0)>0:
            flags.append("3% voting-limit resolutions observed")
        treasury_pct=(g.get("treasury_shares") or {}).get("treasury_share_pct_estimate")
        if treasury_pct is not None and treasury_pct>=10:
            flags.append("large treasury-share position")
        if controller is not None and controller>=70:
            flags.append("weak/dispersed controller signal")

        rows.append({
            "security_ticker":g.get("security_ticker"),
            "dart_ticker":g.get("dart_ticker"),
            "company":g.get("company"),
            "corp_code":g.get("corp_code"),
            "scores":{
                "governance_value_unlock_proxy":clamp(value_unlock_proxy),
                "activist_contestability":clamp(activist_contestability),
                "legal_leverage":clamp(legal_leverage),
                "overall_provisional_activist_opportunity":clamp(overall),
            },
            "agm_data_status":asum.get("data_status","not_available"),
            "agm_history_coverage_pct":asum.get("meeting_coverage_pct"),
            "signals":flags,
            "review_band":band(overall),
            "important_caveat":"Governance/value-unlock is a DART governance proxy, not a valuation estimate. Manual valuation, articles, NPS/institutional ownership, friendly blocks and current law/case analysis are still required."
        })

    rows.sort(key=lambda r:(r["scores"]["overall_provisional_activist_opportunity"] is not None,
                            r["scores"]["overall_provisional_activist_opportunity"] or -1), reverse=True)
    for i,r in enumerate(rows,1):
        r["provisional_rank"]=i if r["scores"]["overall_provisional_activist_opportunity"] is not None else None

    payload={
        "ranker_version":"0.1-full-provisional",
        "generated_at_kst":datetime.now(KST).isoformat(),
        "company_count":len(rows),
        "method":"Separate DART-derived governance/value-unlock proxy, AGM contestability and legal-leverage scores; weighted provisional overall ranking. Missing AGM data remains N/A rather than being treated as zero.",
        "rankings":rows,
    }
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Wrote {OUT}")
    for r in rows[:20]:
        print(r["provisional_rank"],r["security_ticker"],r["company"],r["scores"]["overall_provisional_activist_opportunity"],r["review_band"])

if __name__=="__main__":
    main()
