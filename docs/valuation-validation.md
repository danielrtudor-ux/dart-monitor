# DART valuation: TTM implementation and ten-company validation

Data generated: 2026-09-14T15:47:20.739227+09:00. Engine: 1.2-ttm.

The final audit covers 72 companies with 0 collection errors. Flags: 0 high, 34 medium, 29 low. A clean parser audit does not establish normalized earnings, unrestricted cash, or a complete enterprise-value adjustment.

Workflow: [final verification run](https://github.com/danielrtudor-ux/dart-monitor/actions/runs/34814331236). Implementation: [aa738fd](https://github.com/danielrtudor-ux/dart-monitor/commit/aa738fdef82612e3b7c4b7deae86d97249700825).

Final valuation step: **11 minutes 45 seconds**, versus **45 minutes 27 seconds** for the earlier sequential engine. The complete final workflow passed, including collection, 30 tests, valuation, audit and saving the feeds. [Immutable final source dataset](https://github.com/danielrtudor-ux/dart-monitor/blob/caf537f24272e11b834e5ec9bcec9b3fe9f33c94/docs/valuation-latest.json).

## What changed

- TTM revenue, operating profit, pretax income, total net income and parent net income use FY2025 + 2026 H1 cumulative − 2025 H1 comparable cumulative. Sources and the exact field used are saved beside every result.
- Income extraction is limited to income/comprehensive-income statements. Quarterly-only columns, cash-flow rows and equity-movement rows cannot substitute for cumulative earnings. Missing or conflicting components have labelled annual fallback; CFS and OFS are kept separate.
- P/E, EV/EBIT, EPS and simple ROE use the selected TTM earnings where available. Margins require matching earnings/revenue periods. Losses suppress positive-profit multiples.
- Unknown debt stays unknown. Borrowings, bonds and leases have separate account mappings with aggregate/child handling. Financial institutions suppress industrial EV/net-cash/DCF metrics; KSIC 64992 alone identifies a holding company, not necessarily a financial institution.
- Market-linked ratios are suppressed for USD statements until FX conversion is implemented. Common shares are preferred over a common-plus-preferred aggregate.

DART specifies that interim `thstrm_amount` can be a three-month income-statement amount; the bridge uses `thstrm_add_amount` and `frmtrm_add_amount`. [OpenDART financial-statement field definitions](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS003&apiId=2019020).

## TTM results checked against the filing rows

Amounts below are KRW billions. The linked company names open the 2026 H1 source filing. Parent net income is used for consolidated companies; standalone net income is used for 세원물산 and 카카오뱅크.

| Company / H1 source | Revenue | Operating profit | Pretax income | Parent / standalone net income |
|---|---:|---:|---:|---:|
| [003240 태광산업](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260814003951) | 1,990.303 | -44.241 | 102.710 | 118.699 |
| [066620 국보디자인](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260814002471) | 425.473 | 40.004 | 146.389 | 110.627 |
| [024830 세원물산](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260814003225) | 202.400 | -0.926 | 15.410 | 13.611 |
| [000590 CS홀딩스](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260814002146) | 137.239 | 20.814 | 36.736 | 23.487 |
| [029530 신도리코](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260814001143) | 323.499 | -1.258 | 54.700 | 38.831 |
| [003960 사조대림](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260814003430) | 3,551.162 | 92.022 | -186.168 | -205.696 |
| [053700 삼보모터스](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260814003733) | 1,731.885 | 37.851 | 29.187 | 9.171 |
| [323410 카카오뱅크](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260814002834) | 3,172.012 | 647.796 | 730.841 | 544.655 |
| [055550 신한지주](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260814003306) | — | 7,695.620 | 7,588.684 | 5,376.891 |
| [103140 풍산](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260814004203) | 5,339.890 | 349.504 | 310.419 | 201.886 |

Shinhan’s generic revenue line is unavailable, so revenue and revenue-based margins remain blank; operating, pretax and parent income TTM are available.

## Balance sheet and valuation changes

Cash and debt are KRW billions. Debt includes leases. The last column holds the old market value constant, isolating the earnings change; it is not a fresh market quote.

| Company | Cash-like | Old debt | Corrected debt | Old FY P/E | TTM P/E at old market value |
|---|---:|---:|---:|---:|---:|
| 003240 태광산업 | 805.418 | 0.000 | 5.884 | 9.48× | 6.45× |
| 066620 국보디자인 | 152.649 | 3.246 | 4.052 | 4.32× | 1.55× |
| 024830 세원물산 | 185.076 | 0.000 | — | 3.80× | 5.20× |
| 000590 CS홀딩스 | 112.151 | 0.685 | 1.077 | 3.96× | 2.91× |
| 029530 신도리코 | 419.354 | 3.993 | 4.919 | 16.44× | 8.50× |
| 003960 사조대림 | 149.085 | 651.564 | 717.894 | — | — |
| 053700 삼보모터스 | 188.627 | 487.916 | 546.647 | 5.22× | 11.54× |
| 323410 카카오뱅크 | — | 0.000 | N/A (financial) | 21.43× | 18.90× |
| 055550 신한지주 | — | 90,848.181 | N/A (financial) | 10.76× | 9.94× |
| 103140 풍산 | 254.148 | 1,258.737 | 1,265.189 | 14.59× | 10.63× |

## Findings that matter before a dashboard

**태광산업:** the old zero debt figure omitted KRW 5.884bn of lease liabilities (1.416bn current + 4.467bn noncurrent). Cash-like assets reconcile to 318.221bn cash + 487.196bn short-term deposits. The resulting 799.534bn net-cash figure remains slightly above the screen’s ex-treasury equity value. Its TTM operating loss is 44.241bn despite positive parent profit; the low P/E is not evidence of profitable core operations.

**국보디자인:** cash-like assets reconcile to 120.916bn cash + 31.733bn short-term deposits. Debt is 4.052bn including leases, versus 3.246bn previously. TTM parent profit rises from FY2025’s 39.695bn to 110.627bn, but TTM operating profit falls to 40.004bn. H1 financial income is 114.114bn and financial expense is 19.405bn: much of the earnings increase is outside operating profit. A roughly 1.55× P/E must not be presented as normalized operating cheapness.

**사조대림:** lease liabilities add 66.330bn to the old 651.564bn debt total, producing 717.894bn. TTM parent loss widens to 205.696bn; H1 other losses of 123.147bn warrant note-level investigation. P/E appropriately remains unavailable. The share table contains 8,940,461 common shares and 3,780 preferred shares; the engine now uses the common count rather than 8,944,241 combined shares. Preferred-equity value and preferred distributions are still not separately valued.

**삼보모터스:** the old debt total omitted 13.537bn current convertible bonds, 29.946bn noncurrent bonds, and 15.248bn leases. Correct debt is 546.647bn versus 487.916bn previously. Parent TTM profit falls to 9.171bn from 20.266bn, taking P/E from about 5.22× to 11.54× at the old market value. This is a materially less cheap result than the annual screen suggested.

**풍산:** both current and noncurrent leases must be included, adding 6.452bn and bringing debt to 1,265.189bn. TTM parent profit rises to 201.886bn from 147.164bn. Its TTM operating profit, 349.504bn, is stronger than FY2025’s 297.427bn.

**신도리코:** debt rises from 3.993bn to 4.919bn with leases. Cash-like assets reconcile to 122.357bn cash + 296.998bn short-term deposits; net cash is 414.435bn. TTM operating profit becomes a 1.258bn loss while parent profit increases to 38.831bn. The screen therefore suppresses EV/EBIT despite its lower P/E.

**CS홀딩스:** KSIC 64992 must not classify this industrial holding company as a bank. Debt is 1.077bn, including 0.392bn current leases, versus 0.685bn before. Cash-like assets include 112.151bn cash; 126.303bn of “other current financial assets” is excluded pending composition review. Parent equity is 344.650bn, while consolidated noncontrolling interests are 65.320bn; the distinction matters for EV and cash attribution.

**세원물산:** 5.976bn cash + 179.100bn short-term deposits reconcile to 185.076bn cash-like assets. No explicit borrowing/lease rows establish total debt. The balance sheet includes 0.020bn other current financial liabilities and other payables requiring notes. The old zero debt and net-cash assertion are not validated; current debt, net cash and EV metrics remain unknown. TTM operating profit is a 0.926bn loss.

**카카오뱅크:** the filing reports 2,116.249bn “cash and due from banks,” rather than industrial cash equivalents. This is not a missing-bank-cash error. Standalone TTM net income is 544.655bn. Bank EV, net cash and FCFF DCF remain intentionally unavailable.

**신한지주:** parent TTM profit is 5,376.891bn. Financial-company classification is corrected and industrial cash/EV metrics are suppressed. Parent equity contains 4,163.879bn hybrid securities; common-equity P/B and common-share earnings need hybrid-capital/distribution adjustments before being treated as sector-specific bank valuation.

**Outside the sample — 두산밥캣:** the raw statements are in USD, whereas market value is KRW. P/E, P/B and other market-linked ratios are now suppressed until a documented FX conversion is added. Margins within the same statement currency remain usable.

## Remaining audit exceptions

Debt remains unresolved for **신영와코루 (005800), 세원물산 (024830), 두산밥캣 (241560), 지어소프트 (051160), and 동양이엔피 (079960)**. Four have no explicit recognized debt rows establishing a total; 두산밥캣 has unrecognized sale-and-leaseback liabilities as well as USD reporting. These are not presented as zero debt.

The 34 medium flags comprise seven net-cash-over-equity-value cases, five unresolved-debt cases, eleven share-class cases, eight missing TTM-component flags, two weak-beta flags, and one currency-conversion flag. The 29 low flags are financial/holding-company methodology and preferred-security cautions.

## Remaining scope and limitations

- Cash values above reconcile to face-statement accounts, not unrestricted cash proven from every note. Deposit pledges, restrictions, cash held in partly owned subsidiaries and broader investments still require note-level checks.
- The current EV formula remains equity value + debt − cash. It does not add noncontrolling interests or separately priced preferred equity. This affects consolidated EBIT comparisons, especially CS홀딩스 and 사조대림. Treat the EV/EBIT output as provisional until those adjustments are implemented.
- The share denominator is the latest filing’s outstanding common shares excluding treasury. It is not weighted-average diluted shares, and may not reflect post-H1 buybacks, cancellation or issuance. [OpenDART share-count definitions](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS002&apiId=2020002).
- Annual fallback is still explicit for companies whose cumulative components cannot be matched. Missing financial-company revenue is not filled with an invented industrial equivalent.
- DCF continues to use historical annual FCFF proxies. Passing extraction tests or suppressing extreme DCF outputs does not validate that valuation method.

## Traceability and verification

Thirty tests cover cumulative-vs-quarterly fields, missing and zero amounts, losses, CFS/OFS and currency mismatches, parent-versus-total profit, debt aggregates, lease/convertible-bond mappings, financial-versus-industrial holdings, currency suppression, idempotent postprocessing, and filing-based regressions. An independent Decimal-based check verifies every available TTM bridge in the ten-company sample directly from the saved raw fields. Cash/debt rows, parent equity and share classes were inspected separately.

| Company | Annual source | H1 source | Shares used in final run |
|---|---|---|---:|
| 003240 태광산업 | [FY2025](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260323001584) | [H1 2026](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260814003951) | 841,631 |
| 066620 국보디자인 | [FY2025](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260814002240) | [H1 2026](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260814002471) | 6,766,661 |
| 024830 세원물산 | [FY2025](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260323001247) | [H1 2026](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260814003225) | 8,350,000 |
| 000590 CS홀딩스 | [FY2025](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260814002107) | [H1 2026](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260814002146) | 1,029,631 |
| 029530 신도리코 | [FY2025](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260311003722) | [H1 2026](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260814001143) | 8,426,349 |
| 003960 사조대림 | [FY2025](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260318001283) | [H1 2026](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260814003430) | 8,940,461 |
| 053700 삼보모터스 | [FY2025](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260323000719) | [H1 2026](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260814003733) | 26,715,757 |
| 323410 카카오뱅크 | [FY2025](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260318000884) | [H1 2026](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260814002834) | 476,588,103 |
| 055550 신한지주 | [FY2025](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260318000826) | [H1 2026](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260814003306) | 469,450,238 |
| 103140 풍산 | [FY2025](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260312001327) | [H1 2026](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260814004203) | 27,314,278 |

The dashboard has not been built. The next accounting priorities are note-level verification of unresolved debt/cash, currency conversion for USD reporters, and NCI/preferred/hybrid adjustments to enterprise and common-equity valuation.
