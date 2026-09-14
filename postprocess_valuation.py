#!/usr/bin/env python3
import json
from pathlib import Path
from accounting import company_type
ROOT=Path(__file__).parent
P=ROOT/'docs'/'valuation-latest.json'


def process(d):
    for r in d.get('results',[]):
        ctype, source = company_type(r.get('dart_ticker') or r.get('ticker'), r.get('company') or '', r.get('industry_code'))
        r['company_type'] = ctype
        r['classification_source'] = source
        x=r.get('fundamentals') or {}; q=r.get('ratios') or {}; w=r.get('wacc'); m=r.get('market') or {}
        warnings = r.setdefault('warnings', [])
        status = x.get('debt_status')
        if status in ('no_standard_accounts_found', 'unknown', 'unrecognized_accounts') or x.get('debt_latest') is None:
            x['debt_latest']=None
            x['net_cash_latest']=None
            for k in ('ev_to_ebit','net_cash_per_share','net_cash_pct_market_cap','ex_net_cash_pe'):
                q[k]=None
            r['dcf']=None
            r['wacc']=None
        elif x.get('debt_latest') == 0 and w:
            w['pre_tax_cost_of_debt']=None
            w['cost_of_debt_source']='not_applicable'
        elif w:
            w['cost_of_debt_source']='calculated_or_fallback'
        if ctype=='financial':
            r['dcf']=None; r['wacc']=None
            x['net_cash_latest']=None
            x['debt_status']='sector_not_applicable'
            for k in ('ev_to_ebit','net_cash_per_share','net_cash_pct_market_cap','ex_net_cash_pe'):
                q[k]=None
            warnings.append('Financial company: use P/B, ROE and sector-specific analysis; FCFF DCF suppressed')
        elif ctype=='holding':
            r['dcf']=None
            warnings.append('Holding company: NAV/SOTP preferred; FCFF DCF suppressed')
        dc=r.get('dcf')
        if dc and m.get('price'):
            base=((dc.get('scenarios') or {}).get('base') or {}).get('value_per_share')
            if base and abs(base/m['price']-1)>2:
                r['dcf']=None
                warnings.append('DCF suppressed: mechanical value differed from market price by more than 200%')
        if q.get('ex_net_cash_pe') is not None and q['ex_net_cash_pe']<0:
            q['ex_net_cash_pe']=0.0
            warnings.append('Net cash exceeds market cap; ex-net-cash P/E floored at zero and should be read as a balance-sheet flag')
        r['warnings'] = list(dict.fromkeys(warnings))
    return d


def main():
    d=process(json.loads(P.read_text()))
    P.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
    print('Postprocessed',P)
if __name__=='__main__':main()
