#!/usr/bin/env python3
"""
Governance analyzer — v0.2 test

Reads:
  governance/governance_companies_test.json
  governance/governance_rules.json

Writes:
  governance/governance_profiles_test.json

Purpose:
  Convert the raw OpenDART governance dump into compact, transparent
  company-level governance profiles for the five-company test set.

Important:
  This first version does NOT make legal conclusions.
  Scores are heuristic research indicators only.
"""

import json
import math
import re
from pathlib import Path
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent
RAW_FILE = ROOT / "governance" / "governance_companies_test.json"
RULES_FILE = ROOT / "governance" / "governance_rules.json"
OUT_FILE = ROOT / "governance" / "governance_profiles_test.json"


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def clean_number(value):
    """Convert Korean/English numeric strings to float when possible."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    s = str(value).strip()
    if not s or s in ("-", "null", "None"):
        return None

    s = s.replace(",", "").replace("%", "").replace(" ", "")
    # Parentheses sometimes denote negatives.
    negative = s.startswith("(") and s.endswith(")")
    if negative:
        s = s[1:-1]

    m = re.search(r"-?\d+(?:\.\d+)?", s)
    if not m:
        return None

    try:
        num = float(m.group())
        return -num if negative and num > 0 else num
    except ValueError:
        return None


def get_any(row, keys):
    """Return first non-empty value among candidate DART field names."""
    if not isinstance(row, dict):
        return None
    for key in keys:
        val = row.get(key)
        if val not in (None, "", "-", " "):
            return val
    return None


def rows(section):
    if not isinstance(section, dict):
        return []
    val = section.get("list", [])
    return val if isinstance(val, list) else []


def first_numeric(row, keys):
    return clean_number(get_any(row, keys))


def parse_percent(row):
    return first_numeric(
        row,
        [
            "trmend_posesn_stock_qota_rt",
            "posesn_stock_qota_rt",
            "stock_qota_rt",
            "hold_stock_rate",
            "hold_stock_rate_now",
            "hold_stock_rate_prev",
            "qota_rt",
            "rate",
            "rt",
        ],
    )


def parse_share_count(row):
    return first_numeric(
        row,
        [
            "trmend_posesn_stock_co",
            "posesn_stock_co",
            "stock_co",
            "hold_stock_count",
            "hold_stock_count_now",
            "shares",
            "qy",
        ],
    )


def extract_largest_shareholder(company):
    data = rows(company.get("largest_shareholders"))
    holders = []
    for r in data:
        name = get_any(
            r,
            [
                "nm",
                "name",
                "shrhldr_nm",
                "stockholder_nm",
                "hyslr_nm",
                "holder_name",
            ],
        )
        relation = get_any(
            r,
            [
                "relate",
                "relate_nm",
                "relatn",
                "relation",
                "largest_shareholder_relation",
            ],
        )
        pct = parse_percent(r)
        shares = parse_share_count(r)

        if name or pct is not None or shares is not None:
            holders.append(
                {
                    "name": name,
                    "relation": relation,
                    "pct": pct,
                    "shares": shares,
                    "raw": r,
                }
            )

    # DART's largest-shareholder table often contains a 합계/total row.
    total_candidates = []
    for h in holders:
        n = str(h.get("name") or "")
        if any(x in n for x in ("합계", "계", "총계", "Total", "TOTAL")) and h["pct"] is not None:
            total_candidates.append(h["pct"])

    explicit_total = max(total_candidates) if total_candidates else None

    # Otherwise sum rows carefully only when percentages look like individual positions.
    pcts = [h["pct"] for h in holders if h["pct"] is not None and h["pct"] <= 100]
    calculated_sum = sum(pcts) if pcts else None

    # Prefer an explicit total. If not, use the largest plausible aggregate measure.
    controller_block = explicit_total
    if controller_block is None and calculated_sum is not None:
        controller_block = calculated_sum if calculated_sum <= 100 else None

    return {
        "rows": [{k: v for k, v in h.items() if k != "raw"} for h in holders],
        "controller_related_block_pct_estimate": controller_block,
        "note": "Estimate from latest periodic-report largest-shareholder table; verify manually for high-scoring companies.",
    }


def extract_5pct_holders(company):
    out = []
    for r in rows(company.get("major_5pct_filings")):
        name = get_any(
            r,
            [
                "repror",
                "repror_nm",
                "reporter",
                "reporter_name",
                "nm",
            ],
        )
        pct = first_numeric(
            r,
            [
                "stkrt",
                "stock_rate",
                "hold_stock_rate",
                "hold_stock_rate_now",
                "qota_rt",
            ],
        )
        purpose = get_any(
            r,
            [
                "report_resn",
                "report_reason",
                "hold_purpose",
                "purpose",
            ],
        )
        date = get_any(r, ["rcept_dt", "report_date"])
        out.append(
            {
                "holder": name,
                "reported_pct": pct,
                "purpose_or_reason": purpose,
                "date": date,
            }
        )

    # De-duplicate repeated filings by holder, preserving latest occurrence first if API already sorts that way.
    seen = set()
    unique = []
    for item in out:
        key = item["holder"] or json.dumps(item, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    return unique[:20]


def extract_minority_shareholders(company):
    data = rows(company.get("minority_shareholders"))
    result = {"minority_shareholder_count": None, "minority_share_pct": None, "raw_row_count": len(data)}

    # Prefer the most recent/summary-looking row with populated values.
    for r in reversed(data):
        count = first_numeric(
            r,
            [
                "minor_shrhldr_co",
                "minority_shareholder_count",
                "shrhldr_co",
            ],
        )
        pct = first_numeric(
            r,
            [
                "minor_shrhldr_stck_qota_rt",
                "minority_share_pct",
                "stock_qota_rt",
            ],
        )
        if count is not None or pct is not None:
            result["minority_shareholder_count"] = count
            result["minority_share_pct"] = pct
            break
    return result


def extract_total_shares(company):
    data = rows(company.get("total_shares"))
    issued = None
    treasury = None
    voting = None

    for r in data:
        kind = str(get_any(r, ["se", "stock_knd", "stock_kind", "kind"]) or "")
        qty = first_numeric(
            r,
            [
                "istc_totqy",
                "issued_total",
                "issued_shares",
                "stock_co",
                "qty",
            ],
        )
        treasury_qty = first_numeric(
            r,
            [
                "tesstk_co",
                "treasury_shares",
                "self_stock",
            ],
        )

        if issued is None and qty is not None and ("합계" in kind or "계" == kind.strip() or not kind):
            issued = qty
        if treasury is None and treasury_qty is not None:
            treasury = treasury_qty

    if issued is None:
        candidates = []
        for r in data:
            q = first_numeric(r, ["istc_totqy", "issued_total", "issued_shares", "stock_co", "qty"])
            if q is not None:
                candidates.append(q)
        if candidates:
            issued = max(candidates)

    if issued is not None and treasury is not None:
        voting = max(issued - treasury, 0)

    return {
        "issued_shares_estimate": issued,
        "treasury_shares_estimate": treasury,
        "voting_shares_estimate": voting,
    }


def extract_treasury_activity(company, total_shares):
    data = rows(company.get("treasury_share_activity"))
    items = []

    for r in data:
        item = {
            "type": get_any(r, ["acqs_mth1", "se", "method", "type"]),
            "period_start": get_any(r, ["bgnde", "start_date"]),
            "period_end": get_any(r, ["endde", "end_date"]),
            "shares": first_numeric(
                r,
                [
                    "acqs_qy",
                    "hold_qy",
                    "qty",
                    "stock_co",
                    "treasury_shares",
                ],
            ),
            "amount": first_numeric(
                r,
                [
                    "acqs_amount",
                    "amount",
                    "prc",
                ],
            ),
        }
        if any(v is not None for v in item.values()):
            items.append(item)

    issued = total_shares.get("issued_shares_estimate")
    treasury = total_shares.get("treasury_shares_estimate")
    pct = None
    if issued and treasury is not None and issued > 0:
        pct = treasury / issued * 100.0

    return {
        "treasury_share_pct_estimate": pct,
        "activity_rows": items[:30],
        "note": "Treasury percentage is calculated only if the total-share endpoint exposes both issued and treasury shares cleanly.",
    }


def normalize_role_text(value):
    """Normalize DART role/status text so line breaks and spacing do not break matching."""
    if value is None:
        return ""
    return re.sub(r"\s+", "", str(value)).lower()


def extract_board(company):
    data = rows(company.get("executives"))
    directors = []
    outside_count = 0
    registered_count = 0
    terms = []

    # DART's executive endpoint is not perfectly consistent across issuers.
    # In particular, an outside director may appear as 사외이사, 독립이사,
    # or with embedded whitespace/newlines such as 독립\n이사.
    outside_markers = (
        "사외이사",
        "독립이사",
        "independentdirector",
        "outsidedirector",
    )
    registered_markers = (
        "등기임원",
        "등기이사",
        "사내이사",
        "사외이사",
        "독립이사",
        "대표이사",
    )
    unregistered_markers = (
        "미등기",
        "미등기임원",
        "unregistered",
    )

    for r in data:
        name = get_any(r, ["nm", "name", "exctv_nm"])
        registered = str(get_any(r, ["rgist_exctv_at", "registered", "rgist_at"]) or "")
        position = get_any(r, ["ofcps", "position", "chrg_job"])
        relation = get_any(r, ["mxmm_shrholdr_relate", "relate", "relation"])
        term_end = get_any(r, ["tenure_end_on", "term_end", "mandt_endde"])
        career = get_any(r, ["main_career", "career"])

        registered_norm = normalize_role_text(registered)
        position_norm = normalize_role_text(position)
        text_norm = registered_norm + position_norm

        explicit_unregistered = any(x in registered_norm for x in unregistered_markers)

        is_outside = (
            not explicit_unregistered
            and any(x in text_norm for x in outside_markers)
        )

        # Prefer explicit DART registration status. Also treat recognised board
        # titles as registered directors when the endpoint uses the title itself
        # (e.g. 독립이사) instead of the literal string 등기임원.
        is_registered = (
            not explicit_unregistered
            and (
                registered_norm in ("y", "true", "1")
                or any(x in registered_norm for x in registered_markers)
                or any(x in position_norm for x in ("사내이사", "사외이사", "독립이사", "대표이사"))
            )
        )

        if is_registered:
            registered_count += 1
            if is_outside:
                outside_count += 1

        if name or position:
            directors.append(
                {
                    "name": name,
                    "position": position,
                    "registered_status": registered or None,
                    "is_registered_director_estimate": is_registered,
                    "is_outside_director_estimate": is_outside,
                    "relation_to_largest_shareholder": relation,
                    "term_end": term_end,
                    "career": career,
                }
            )

            # Keep term information for board directors only. This prevents
            # ordinary unregistered executives' employment terms from being
            # mistaken for director-election dates.
            if term_end and is_registered:
                terms.append(
                    {
                        "name": name,
                        "term_end": term_end,
                        "position": position,
                    }
                )

    outside_pct = (
        outside_count / registered_count * 100.0
        if registered_count
        else None
    )

    return {
        "director_rows": directors,
        "registered_director_count_estimate": registered_count or None,
        "outside_director_count_estimate": outside_count,
        "outside_director_pct_estimate": outside_pct,
        "term_expiries": terms,
        "board_parser_note": (
            "Normalizes whitespace and recognises both 사외이사 and 독립이사 as "
            "outside directors; excludes explicitly 미등기 executives from the denominator."
        ),
    }



def score_controller_vulnerability(controller_pct):
    """
    Higher score = controller looks more vulnerable on raw ownership arithmetic.
    This ignores friendly blocks and turnout, so it is explicitly preliminary.
    """
    if controller_pct is None:
        return None
    if controller_pct >= 50:
        return 10
    if controller_pct >= 40:
        return 25
    if controller_pct >= 30:
        return 45
    if controller_pct >= 20:
        return 65
    if controller_pct >= 10:
        return 80
    return 90


def score_treasury_leverage(treasury_pct):
    if treasury_pct is None:
        return None
    if treasury_pct >= 15:
        return 95
    if treasury_pct >= 10:
        return 85
    if treasury_pct >= 5:
        return 70
    if treasury_pct >= 2:
        return 45
    if treasury_pct > 0:
        return 20
    return 0


def score_outside_director_weakness(outside_pct):
    # Research flag only, not a legal compliance conclusion.
    if outside_pct is None:
        return None
    if outside_pct < 33.3:
        return 90
    if outside_pct < 40:
        return 70
    if outside_pct < 50:
        return 50
    return 20


def build_flags(profile):
    flags = []

    ctrl = profile["ownership"]["controller_related_block_pct_estimate"]
    if ctrl is not None:
        if ctrl < 20:
            flags.append("controller_block_below_20pct")
        elif ctrl < 30:
            flags.append("controller_block_below_30pct")
        elif ctrl < 40:
            flags.append("controller_block_below_40pct")

    treasury = profile["treasury_shares"]["treasury_share_pct_estimate"]
    if treasury is not None:
        if treasury >= 10:
            flags.append("large_treasury_share_position_10pct_plus")
        elif treasury >= 5:
            flags.append("meaningful_treasury_share_position_5pct_plus")

    outside = profile["board"]["outside_director_pct_estimate"]
    if outside is not None and outside < 50:
        flags.append("board_not_majority_outside_directors_estimate")

    if profile["ownership"]["five_percent_holders"]:
        flags.append("outside_5pct_holder_filings_present")

    if profile["board"]["term_expiries"]:
        flags.append("director_term_data_available")

    return flags


def main():
    if not RAW_FILE.exists():
        raise SystemExit(f"Missing raw file: {RAW_FILE}")
    if not RULES_FILE.exists():
        raise SystemExit(f"Missing rules file: {RULES_FILE}")

    raw = load_json(RAW_FILE)
    rules = load_json(RULES_FILE)
    profiles = []

    for company in raw.get("companies", []):
        ownership = extract_largest_shareholder(company)
        five_pct = extract_5pct_holders(company)
        minority = extract_minority_shareholders(company)
        total = extract_total_shares(company)
        treasury = extract_treasury_activity(company, total)
        board = extract_board(company)

        ctrl_score = score_controller_vulnerability(
            ownership["controller_related_block_pct_estimate"]
        )
        treasury_score = score_treasury_leverage(
            treasury["treasury_share_pct_estimate"]
        )
        board_weakness = score_outside_director_weakness(
            board["outside_director_pct_estimate"]
        )

        preliminary_components = [
            x for x in (ctrl_score, treasury_score, board_weakness) if x is not None
        ]
        preliminary_vulnerability = (
            round(sum(preliminary_components) / len(preliminary_components), 1)
            if preliminary_components
            else None
        )

        profile = {
            "security_ticker": company.get("security_ticker"),
            "dart_ticker": company.get("dart_ticker"),
            "company": company.get("company"),
            "corp_code": company.get("corp_code"),
            "period_used": company.get("period_used"),

            "ownership": {
                **ownership,
                "five_percent_holders": five_pct,
                "minority": minority,
            },

            "share_structure": total,
            "treasury_shares": treasury,
            "board": board,

            "preliminary_research_scores": {
                "controller_vulnerability_raw_ownership": ctrl_score,
                "treasury_share_legal_leverage": treasury_score,
                "board_independence_weakness": board_weakness,
                "preliminary_activist_vulnerability": preliminary_vulnerability,
            },

            "legal_mechanisms_to_test": {
                "article_382_3_director_duty": True,
                "article_341_4_treasury_cancellation": (
                    treasury["treasury_share_pct_estimate"] is not None
                    and treasury["treasury_share_pct_estimate"] > 0
                ),
                "listed_shareholder_proposal_right": True,
                "books_and_records_right": True,
                "derivative_suit_right": True,
                "audit_committee_3pct_rule": "needs_company_specific_applicability_check",
                "cumulative_voting": "needs_asset_threshold_and_articles_check",
            },

            "flags": [],
            "caveats": [
                "Scores are screening heuristics, not legal conclusions.",
                "Controller percentage is an estimate from structured DART data and may omit friendly blocks or duplicate total rows.",
                "No AGM turnout, proxy voting history, valuation, NPS voting, articles-of-incorporation analysis or case-law analysis is included yet.",
                "High-scoring companies require manual verification of the underlying filing tables.",
            ],
        }

        profile["flags"] = build_flags(profile)
        profiles.append(profile)

    payload = {
        "analyzer_version": "0.2-test",
        "generated_at_kst": datetime.now(KST).isoformat(),
        "raw_collector_version": raw.get("collector_version"),
        "legal_rules_snapshot_date": rules.get("snapshot_date"),
        "purpose": "Compact governance profiles and preliminary activist-vulnerability screening for the five-company test set.",
        "company_count": len(profiles),
        "profiles": profiles,
    }

    OUT_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUT_FILE}")
    for p in profiles:
        print(
            p["security_ticker"],
            p["company"],
            p["preliminary_research_scores"]["preliminary_activist_vulnerability"],
            p["flags"],
        )


if __name__ == "__main__":
    main()
