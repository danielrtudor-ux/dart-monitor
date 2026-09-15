# DART valuation: filing-note and ownership review

Reviewed run: 2026-09-15 07:52 KST. Workflow: [successful run 34902472934](https://github.com/danielrtudor-ux/dart-monitor/actions/runs/34902472934). Implementation: [commit 6290937](https://github.com/danielrtudor-ux/dart-monitor/commit/6290937da676c61938fe4b5e4e0968bbef6115de).

The run processed all 72 companies with zero collection errors. The audit found **0 high, 34 medium and 74 low** flags. The increase in low flags is intentional: enterprise values now disclose when noncontrolling interest (NCI) uses book value as a proxy.

## Resolved debt cases

| Ticker | Finding from 2026 H1 filing notes | Engine treatment |
|---|---|---|
| 005800 신영와코루 | Lease liabilities are KRW 4.266bn; no other drawn borrowing was identified in the reviewed liability disclosures. | Debt changed from unknown to KRW 4.266bn. |
| 024830 세원물산 | The lending facility shows zero drawn debt. A KRW 35.300bn short-term deposit is pledged. | Debt is receipt-bound `reviewed_zero`; pledged cash is removed, leaving KRW 149.776bn usable net cash. |
| 241560 두산밥캣 | USD 984.600m borrowings, 49.859m current bonds, 38.488m sale-and-leaseback liabilities and 110.639m lease liabilities. | Debt changed from unknown to USD 1,183.586m. |
| 051160 지어소프트 | Current leases are KRW 12.058bn and noncurrent leases KRW 21.319bn; the prior convertible bond was fully repaid in October 2025. | Debt changed from unknown to KRW 33.376bn. |
| 079960 동양이엔피 | The current liability maturity table contains payables and other financial liabilities, with no drawn borrowings or leases. | Debt is receipt-bound `reviewed_zero`. KRW 0.700bn restricted deposits sit outside the engine’s cash-like balance. |

The review facts are tied to both the DART receipt number and CFS/OFS basis. If either changes, the engine discards the prior conclusion and returns the item to review rather than carrying a stale zero or adjustment forward.

## Currency and ownership corrections

- **두산밥캣:** KRW market value is converted to the USD accounting basis using the latest available Federal Reserve DEXKOUS observation, KRW 1,346.51 per USD on 2026-09-04. P/E and P/B are now 12.65× and 0.85×. The filing says restricted deposits are included in short-term deposits but does not quantify the restricted portion, so EV/EBIT, ex-net-cash P/E, net-cash ratios and DCF remain suppressed. [Federal Reserve/FRED series](https://fred.stlouisfed.org/series/DEXKOUS).
- **NCI:** consolidated operating-company EV now adds noncontrolling interest using a nonnegative book-value proxy, and DCF equity value subtracts the same claim. Forty-four companies carry a low-severity proxy warning because a market value is unavailable. This materially affects 태광산업 (KRW 33.388bn), 사조대림 (KRW 120.530bn), 지어소프트 (KRW 86.632bn) and CS홀딩스 (KRW 65.320bn).
- **신한지주:** common equity now excludes KRW 4,163.879bn of parent hybrid securities. TTM common earnings deduct KRW 197.338bn of hybrid distributions (FY2025 + 2026 H1 − 2025 H1). The resulting common-share P/E is 10.42× and P/B is 0.97×. Industrial EV/net-debt/DCF remain suppressed for the bank.
- **사조대림:** 3,780 preferred shares remain unpriced. P/E, P/B, EV/EBIT, ex-net-cash P/E and DCF are therefore suppressed instead of comparing common market value with claims belonging to all equity classes.

## Cash restrictions found in the representative review

| Company | Filing-note result | Valuation effect |
|---|---|---|
| 국보디자인 | KRW 4.991m attached account | Deducted from cash-like assets. |
| 세원물산 | KRW 35.300bn pledged short-term deposit | Deducted from cash-like assets. |
| CS홀딩스 | KRW 71.609m restricted short-term financial product | Deducted from cash-like assets. |
| 신도리코 | KRW 21.755m restriction is in long-term products | No deduction; long-term products were never included in cash-like assets. |
| 동양이엔피 | KRW 700m restriction is in other financial assets | No deduction; it was outside cash-like assets. |
| 두산밥캣 | Restricted deposits disclosed without a separable amount | Cash-dependent ratios suppressed. |

For companies without a quantified note adjustment, the output labels the balance as a face-statement cash view rather than claiming that every deposit is unrestricted.

## Representative valuation output after corrections

| Company | TTM P/E | P/B | EV/EBIT | Main interpretation |
|---|---:|---:|---:|---|
| 태광산업 | 6.44× | 0.18× | — | TTM operating loss; positive parent profit is not core operating profit. |
| 국보디자인 | 1.55× | 0.35× | 0.58× | Very low P/E is driven heavily by non-operating income. |
| 세원물산 | 5.22× | 0.18× | — | Debt is verified zero, but TTM operating profit is negative. |
| 사조대림 | — | — | — | TTM loss and unpriced preferred equity make common multiples unsuitable. |
| 삼보모터스 | 11.54× | 0.23× | 12.25× | Corrected debt and weaker TTM profit make it less cheap than the FY screen implied. |
| 풍산 | 10.50× | 0.87× | 8.96× | TTM operating and parent profit remain stronger than FY2025. |
| 두산밥캣 | 12.65× | 0.85× | — | Currency-adjusted earnings ratios available; cash-dependent metrics withheld. |
| 신한지주 | 10.42× | 0.97× | — | Common-equity figures now reflect parent hybrids and their distributions. |

## Remaining discrepancies before the dashboard

The debt-parser exceptions are resolved. The remaining 34 medium flags are mostly deliberate methodology warnings: nine net-cash-over-market-value cases, eleven multiple-share-class cases, eight unavailable TTM components, three unreviewed hybrid-equity cases outside Shinhan, two weak betas and Doosan Bobcat’s unquantified restricted deposits.

Three financial companies—000370, 139130 and 316140—still have hybrid capital that needs the same instrument/distribution review performed for Shinhan. Several companies with preferred classes still lack a reliable preferred market value or distribution allocation. These values remain suppressed where common-share valuation would otherwise mix incompatible claims.

The dashboard has not been built. The current data is suitable for a review screen with visible warnings, but hybrid and preferred-class cases should remain excluded from clean rankings until their claim values are resolved.
