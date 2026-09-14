"""Conservative DART income/debt extraction with field-level provenance."""
import re


def number(value):
    if value is None or str(value).strip() in ('', '-', '—'):
        return None
    try:
        return float(str(value).replace(',', '').replace('(', '-').replace(')', ''))
    except (ValueError, TypeError):
        return None


def normalized(value):
    return re.sub(r'[\s·ㆍ,()\-_/]', '', (value or '').lower())


INCOME = {
    'revenue': (('ifrs-full_Revenue',), ('매출액', '영업수익', '수익(매출액)')),
    'op': (('dart_OperatingIncomeLoss', 'ifrs-full_ProfitLossFromOperatingActivities'), ('영업이익', '영업이익(손실)')),
    'pretax': (('ifrs-full_ProfitLossBeforeTax',), ('법인세비용차감전순이익', '법인세비용차감전순이익(손실)', '법인세비용차감전이익', '법인세비용차감전이익(손실)', '법인세비용차감전계속영업이익')),
    'ni': (('ifrs-full_ProfitLoss',), ('당기순이익', '당기순이익(손실)', '반기순이익', '반기순이익(손실)', '분기순이익', '분기순이익(손실)')),
    'pni': (('ifrs-full_ProfitLossAttributableToOwnersOfParent',), ('지배기업의소유주에게귀속되는당기순이익', '지배기업소유주지분순이익', '지배기업의소유주에게귀속되는당기순이익(손실)', '지배기업의소유주에게귀속되는반기순이익(손실)', '지배기업의소유주에게귀속되는분기순이익(손실)')),
}


def evidence(row, field):
    if row is None:
        return None
    keys = ('rcept_no', 'bsns_year', 'reprt_code', 'sj_div', 'account_id', 'account_nm', 'currency', 'thstrm_nm', 'frmtrm_nm', 'frmtrm_q_nm')
    out = {k: row.get(k) for k in keys}
    out.update(field=field, raw=row.get(field), value=number(row.get(field)))
    if row.get('rcept_no'):
        out['filing_url'] = 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=' + row['rcept_no']
    return out


def select(rows, ids, names, sections, field):
    """Prefer standard IDs and reject conflicting matches, including duplicate contexts."""
    pool = [r for r in rows if r.get('sj_div') in sections]
    ids = {i.lower() for i in ids}
    names = {normalized(n) for n in names}
    hits = [r for r in pool if (r.get('account_id') or '').lower() in ids]
    if not hits:
        hits = [r for r in pool if normalized(r.get('account_nm')) in names]
    usable = [r for r in hits if number(r.get(field)) is not None]
    if len({(number(r.get(field)), r.get('currency', 'KRW')) for r in usable}) > 1:
        return None, 'ambiguous_accounts'
    return (usable[0], None) if usable else (None, 'missing_amount' if hits else 'account_not_found')


def income(rows, field):
    out = {}
    for key, (ids, names) in INCOME.items():
        row, error = select(rows, ids, names, ('IS', 'CIS'), field)
        out[key] = {'value': number(row.get(field)) if row else None, 'source': evidence(row, field), 'error': error}
    return out


def ttm_income(current, annual, year, label, fs_div, annual_year, annual_fs_div):
    """Never substitute a three-month column for H1/Q3 accumulated earnings."""
    fy = income(annual, 'thstrm_amount')
    current_field = 'thstrm_amount' if label == 'FY' else 'thstrm_add_amount'
    cy = income(current, current_field)
    py = income(current, 'frmtrm_add_amount')
    out = {}
    for key in INCOME:
        a, c, p = fy[key], cy[key], py[key]
        reason = None
        if label == 'FY':
            value = c['value']
            basis = f'FY{year}'
        else:
            if annual_year != year - 1 or fs_div != annual_fs_div:
                reason = 'annual_year_or_statement_basis_mismatch'
            elif any(x['value'] is None for x in (a, c, p)):
                reason = 'missing_or_ambiguous_ttm_component'
            elif len({(x['source'] or {}).get('currency') or 'KRW' for x in (a, c, p)}) != 1:
                reason = 'currency_mismatch'
            value = a['value'] + c['value'] - p['value'] if reason is None else None
            basis = f'TTM {year} {label}' if value is not None else None
        fallback = a['value'] if annual_fs_div == fs_div else None
        out[key] = {'ttm': value, 'used': value if value is not None else fallback,
                    'basis': basis if value is not None else (f'FY{annual_year} fallback' if fallback is not None else 'unavailable'),
                    'reason': reason, 'annual': a, 'current_cumulative': c, 'prior_comparable_cumulative': p}
    # Parent income is never mixed with consolidated total income in the bridge.
    chosen = 'pni' if out['pni']['ttm'] is not None else ('ni' if fs_div == 'OFS' and out['ni']['ttm'] is not None else ('pni' if out['pni']['used'] is not None else 'ni'))
    out['earnings_key'] = chosen
    out['net_income_basis'] = 'parent' if chosen == 'pni' else ('standalone' if fs_div == 'OFS' else 'total_including_noncontrolling_interests')
    return out


FINANCIAL_TICKERS = {'323410', '055550', '316140', '139130'}


def company_type(ticker, name, industry=None):
    if ticker in FINANCIAL_TICKERS:
        return 'financial', 'ticker_override'
    if any(s in name for s in ('은행', '뱅크', '금융', '보험', '증권', '캐피탈', '생명', '손해')):
        return 'financial', 'company_name'
    if str(industry or '') in ('64992','71520','71600'):
        return 'holding', 'DART_holding_industry_code'
    if str(industry or '')[:2] in ('64', '65', '66'):
        return 'financial', 'DART_industry_code'
    if any(s in name for s in ('홀딩스', '지주')):
        return 'holding', 'company_name'
    return 'operating', 'default'


# Each aggregate replaces its children; lease liabilities are included separately.
DEBT_GROUPS = {
    'total_borrowings': (('ifrs-full_Borrowings', 'dart_Borrowings'), ('차입금', '총차입금')),
    'total_loans': (('ifrs-full_LoansReceived',), ('차입부채',)),
    'current_borrowings': (('ifrs-full_CurrentBorrowings', 'dart_CurrentBorrowings', 'ifrs-full_CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings'), ('유동차입금',)),
    'noncurrent_borrowings': (('ifrs-full_NoncurrentBorrowings', 'dart_NoncurrentBorrowings'), ('비유동차입금',)),
    'current_loans': (('ifrs-full_CurrentLoansReceivedAndCurrentPortionOfNoncurrentLoansReceived',), ('유동성 금융기관 차입금(사채 제외)',)),
    'short_borrowings': (('ifrs-full_ShorttermBorrowings', 'dart_ShortTermBorrowings', 'dart_CurrentLoansReceived'), ('단기차입금',)),
    'current_long_borrowings': (('ifrs-full_CurrentPortionOfLongtermBorrowings', 'dart_CurrentPortionOfLongTermBorrowings', 'dart_CurrentPortionOfNoncurrentLoansReceived'), ('유동성장기차입금', '유동성장기부채', '비유동 금융기관 차입금(사채 제외)의 유동성 대체 부분')),
    'long_borrowings': (('ifrs-full_LongtermBorrowings', 'dart_LongTermBorrowingsGross', 'dart_NoncurrentLoansReceived', 'ifrs-full_NoncurrentPortionOfNoncurrentLoansReceived'), ('장기차입금',)),
    'other_current_borrowings': (('ifrs-full_OtherCurrentBorrowingsAndCurrentPortionOfOtherNoncurrentBorrowings',), ('유동성장기유동화채무',)),
    'other_noncurrent_borrowings': (('ifrs-full_NoncurrentPortionOfOtherNoncurrentBorrowings',), ('장기유동화채무',)),
    'short_bonds': (('dart_CurrentBondsIssued',), ('단기사채',)),
    'current_bonds': (('ifrs-full_CurrentPortionOfBondsIssued', 'dart_CurrentPortionOfBonds', 'dart_CurrentPortionOfNoncurrentBondsIssued'), ('유동성사채', '유동사채', '유동성회사채')),
    'noncurrent_bonds': (('ifrs-full_BondsIssued', 'dart_BondsIssued', 'ifrs-full_NoncurrentPortionOfNoncurrentBondsIssued'), ('사채', '비유동사채', '회사채')),
    'current_convertible_bonds': (('dart_CurrentPortionOfConvertibleBonds',), ('유동성전환사채',)),
    'noncurrent_convertible_bonds': (('dart_ConvertibleBonds',), ('전환사채', '비유동전환사채')),
    'current_exchangeable_bonds': (('dart_CurrentPortionOfExchangeableBond',), ('유동성교환사채',)),
    'noncurrent_exchangeable_bonds': (('dart_ExchangeableBonds',), ('교환사채', '비유동교환사채')),
    'total_leases': (('ifrs-full_LeaseLiabilities',), ('리스부채',)),
    'current_leases': (('ifrs-full_LeaseLiabilitiesCurrent', 'dart_CurrentLeaseLiabilities', 'ifrs-full_CurrentLeaseLiabilities'), ('유동리스부채', '유동성리스부채', '단기리스부채')),
    'noncurrent_leases': (('ifrs-full_LeaseLiabilitiesNoncurrent', 'dart_NonCurrentLeaseLiabilities', 'ifrs-full_NoncurrentLeaseLiabilities'), ('비유동리스부채', '장기리스부채')),
}

# Exclude child rows only where the XBRL aggregate has the same coverage.
CHILDREN = {
    'total_borrowings': ('total_loans','current_borrowings','noncurrent_borrowings','current_loans','short_borrowings','current_long_borrowings','long_borrowings','other_current_borrowings','other_noncurrent_borrowings','short_bonds','current_bonds','noncurrent_bonds','current_convertible_bonds','noncurrent_convertible_bonds','current_exchangeable_bonds','noncurrent_exchangeable_bonds'),
    'total_loans': ('current_loans','short_borrowings','current_long_borrowings','long_borrowings'),
    'current_borrowings': ('current_loans','short_borrowings','current_long_borrowings','other_current_borrowings','short_bonds','current_bonds','current_convertible_bonds','current_exchangeable_bonds'),
    'noncurrent_borrowings': ('long_borrowings','other_noncurrent_borrowings','noncurrent_bonds','noncurrent_convertible_bonds','noncurrent_exchangeable_bonds'),
    'current_loans': ('short_borrowings','current_long_borrowings'),
    'total_leases': ('current_leases','noncurrent_leases'),
}


def debt_accounts(rows):
    found, issues = {}, []
    all_ids = {i.lower() for ids,names in DEBT_GROUPS.values() for i in ids}
    for key, (ids, names) in DEBT_GROUPS.items():
        # A generic label must not override another group's precise standard ID.
        other_ids = all_ids - {i.lower() for i in ids}
        pool = [r for r in rows if (r.get('account_id') or '').lower() not in other_ids]
        row, error = select(pool, ids, names, ('BS',), 'thstrm_amount')
        if row is not None:
            found[key] = row
        elif error == 'ambiguous_accounts':
            issues.append(key + ': ambiguous_accounts')
    recognized = set()
    for ids, names in DEBT_GROUPS.values():
        recognized.update(id(r) for r in rows if (r.get('account_id') or '').lower() in {i.lower() for i in ids} or normalized(r.get('account_nm')) in {normalized(n) for n in names})
    candidates = [r for r in rows if r.get('sj_div') == 'BS' and (
        any(s in normalized(r.get('account_nm')) for s in ('차입', '사채', '리스부채', '금융리스부채', '전환부채')) or
        any(s in (r.get('account_id') or '').lower() for s in ('borrowings', 'bondsissued', 'leaseliabilit')))]
    unmatched = [r for r in candidates if id(r) not in recognized]
    if any(number(r.get('thstrm_amount')) is None for r in candidates):
        issues.append('missing_debt_amount')
    if unmatched:
        issues.append('unrecognized_debt_accounts')
    selected = dict(found)
    for aggregate, children in CHILDREN.items():
        if aggregate in selected:
            for child in children:
                selected.pop(child, None)
    values = [number(r.get('thstrm_amount')) for r in selected.values()]
    if any(v < 0 for v in values):
        issues.append('negative_debt_amount')
    identified_sum = sum(values) if values else None
    status = 'unrecognized_accounts' if issues else ('identified' if identified_sum is not None and identified_sum > 0 else 'unknown')
    # A zero lease or single zero borrowing line is not proof of zero total debt.
    if not issues and identified_sum == 0 and ('total_borrowings' in selected or all(k in selected for k in ('current_borrowings', 'noncurrent_borrowings'))):
        status = 'explicit_zero'
    total = identified_sum if status in ('identified', 'explicit_zero') else None
    return {'value': total, 'identified_sum': identified_sum, 'status': status, 'issues': issues,
            'selected': {k: evidence(r, 'thstrm_amount') for k, r in selected.items()},
            'candidates': [evidence(r, 'thstrm_amount') for r in candidates],
            'unrecognized': [evidence(r, 'thstrm_amount') for r in unmatched]}
