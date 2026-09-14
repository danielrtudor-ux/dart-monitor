"""Currency and ownership adjustments, with receipt-bound note evidence."""
import csv
import io
import json
import math
from datetime import date, timedelta
from pathlib import Path
from accounting import number, normalized, select, evidence

ROOT=Path(__file__).parent
FX_SOURCE='https://fred.stlouisfed.org/series/DEXKOUS'
FX_URL='https://fred.stlouisfed.org/graph/fredgraph.csv'


def parse_fx_csv(text, as_of, max_age=14):
    observations=[]
    for row in csv.DictReader(io.StringIO(text)):
        day=row.get('observation_date') or row.get('DATE')
        value=number(row.get('DEXKOUS'))
        if not day or value is None or not math.isfinite(value) or value<=0:continue
        observed=date.fromisoformat(day)
        if observed<=as_of:observations.append((observed,value))
    if not observations:return {'supported':False,'reason':'no_published_observation','source':FX_SOURCE}
    observed,value=max(observations)
    age=(as_of-observed).days
    return {'supported':age<=max_age,'rate_krw_per_usd':value,'observation_date':observed.isoformat(),'as_of':as_of.isoformat(),'age_days':age,'max_age_days':max_age,'source':FX_SOURCE,'reason':None if age<=max_age else 'stale_rate','method':'latest published FRED spot; valuation translation, not historical IFRS translation'}


def fetch_fx(get, as_of):
    try:
        raw=get(FX_URL,{'id':'DEXKOUS','cosd':(as_of-timedelta(days=40)).isoformat(),'coed':as_of.isoformat()})
        result=parse_fx_csv(raw.decode('utf-8-sig'),as_of)
        if result['supported']:return result
    except Exception:
        result={'supported':False,'reason':'source_unavailable','source':FX_SOURCE}
    # A documented observation is usable only within the same freshness limit.
    cached=ROOT/'fx_reference.json'
    if cached.exists():
        data=json.loads(cached.read_text())
        text='observation_date,DEXKOUS\n'+data['observation_date']+','+str(data['rate_krw_per_usd'])+'\n'
        fallback=parse_fx_csv(text,as_of)
        fallback['fallback_reason']=result['reason']
        fallback['retrieval']='reviewed_reference_observation'
        return fallback
    return result


def currency_rate(currency,fx):
    if currency=='KRW':return 1.0
    if currency=='USD' and fx and fx.get('supported'):return fx['rate_krw_per_usd']
    return None


def current_receipt(rows):
    receipts={r.get('rcept_no') for r in rows if r.get('rcept_no')}
    return next(iter(receipts)) if len(receipts)==1 else None


def applicable_review(ticker,rows,fs_div,reviews):
    review=reviews.get(ticker) or {}
    if review.get('receipt')!=current_receipt(rows) or review.get('fs_div')!=fs_div:
        return {}
    return review


def owner_accounts(rows,fs_div,review=None):
    review=review or {}
    nci_row,error=select(rows,('ifrs-full_NoncontrollingInterests',),('비지배지분',),('BS',),'thstrm_amount')
    nci=number(nci_row.get('thstrm_amount')) if nci_row else (0.0 if fs_div=='OFS' else None)
    if nci is None:
        total,_=select(rows,('ifrs-full_Equity',),('자본총계',),('BS',),'thstrm_amount')
        parent,_=select(rows,('ifrs-full_EquityAttributableToOwnersOfParent',),(),('BS',),'thstrm_amount')
        if total and parent:nci=number(total['thstrm_amount'])-number(parent['thstrm_amount'])
    hybrid_rows=[r for r in rows if r.get('sj_div')=='BS' and (any(x in normalized(r.get('account_nm')) for x in ('신종자본증권','영구채','기타자본증권')) or (r.get('account_id') or '') in ('dart_HybridBonds','ifrs-full_OtherEquityInstruments'))]
    hybrid=review.get('hybrid_parent_book') if hybrid_rows else 0.0
    if 'hybrid_parent_book' in review:hybrid=review['hybrid_parent_book']
    return {'nci_book':nci,'nci_ev_proxy':max(0,nci) if nci is not None else None,'nci_method':'nonnegative book-value proxy; market value unavailable' if nci else 'zero or standalone',
            'nci_source':evidence(nci_row,'thstrm_amount'),'hybrid_parent_book':hybrid,'hybrid_status':'reviewed' if 'hybrid_parent_book' in review else ('unreviewed' if hybrid_rows else 'no_hybrid_account'),
            'hybrid_candidates':[evidence(r,'thstrm_amount') for r in hybrid_rows]}


def reviewed_common_income(bridge,review):
    parts=review.get('common_income_components')
    if not parts:return None
    source=bridge[bridge['earnings_key']]
    if parts.get('annual_receipt')!=(source['annual'].get('source') or {}).get('rcept_no'):
        return None
    values=[parts.get(k) for k in ('annual','current_ytd','prior_ytd')]
    return values[0]+values[1]-values[2] if all(v is not None for v in values) else None


def apply_note_balance(cur,review):
    out=dict(cur)
    if 'debt_total' in review:
        out['debt']=review['debt_total']
        out['debt_evidence']=dict(cur['debt_evidence'],value=review['debt_total'],status='reviewed_zero' if review['debt_total']==0 else 'note_verified',note_review=review.get('debt_evidence'))
    restricted=review.get('restricted_cash_in_cash_like')
    out['restricted_cash']=restricted
    out['cash_review_status']=review.get('cash_status','unreviewed')
    out['usable_cash']=out.get('cash_like')-restricted if out.get('cash_like') is not None and restricted is not None else None
    # Retain the face-statement view separately; usable net cash requires note evidence.
    out['face_net_cash']=out['cash_like']-out['debt'] if out.get('cash_like') is not None and out.get('debt') is not None else None
    out['usable_net_cash']=out['usable_cash']-out['debt'] if out.get('usable_cash') is not None and out.get('debt') is not None else None
    out['net_cash']=out['usable_net_cash'] if out['usable_net_cash'] is not None else out['face_net_cash']
    return out
