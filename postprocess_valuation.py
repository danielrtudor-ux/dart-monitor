#!/usr/bin/env python3
import json
from pathlib import Path
ROOT=Path(__file__).parent
P=ROOT/'docs'/'valuation-latest.json'
FIN=('은행','금융지주','보험','증권','캐피탈')
HOLD=('홀딩스','지주')

def main():
    d=json.loads(P.read_text())
    d['engine_version']='1.1-quality'
    d['methodology_notes']=(d.get('methodology_notes') or [])+[
      'Financial companies suppress EV/net-debt/FCFF DCF because those methods are not appropriate for banks/insurers.',
      'Holding companies suppress FCFF DCF; NAV/SOTP is preferred.',
      'Zero or unidentified standard debt accounts no longer show a synthetic cost of debt.',
      'Extreme DCF outputs are suppressed rather than presented as valuation signals.'
    ]
    for r in d.get('results',[]):
        name=r.get('company') or ''; f=any(x in name for x in FIN); h=any(x in name for x in HOLD)
        r['company_type']='financial' if f else ('holding' if h else 'operating')
        x=r.get('fundamentals') or {}; q=r.get('ratios') or {}; w=r.get('wacc') or {}; m=r.get('market') or {}
        debt=x.get('debt_latest')
        x['debt_status']='identified' if debt is not None else 'no_standard_accounts_found'
        if debt is None:
            x['debt_latest']=0.0
            if x.get('cash_like_latest') is not None:x['net_cash_latest']=x['cash_like_latest']
        if (x.get('debt_latest') or 0)==0 and w:
            w['pre_tax_cost_of_debt']=None; w['cost_of_debt_source']='not_applicable'
        elif w:
            w['cost_of_debt_source']='calculated_or_fallback'
        if f:
            r['dcf']=None; r['wacc']=None
            q['ev_to_ebit']=None; q['net_cash_per_share']=None; q['net_cash_pct_market_cap']=None; q['ex_net_cash_pe']=None
            r.setdefault('warnings',[]).append('Financial company: use P/B, ROE and sector-specific analysis; FCFF DCF suppressed')
        elif h:
            r['dcf']=None
            r.setdefault('warnings',[]).append('Holding company: NAV/SOTP preferred; FCFF DCF suppressed')
        dc=r.get('dcf')
        if dc and m.get('price'):
            base=((dc.get('scenarios') or {}).get('base') or {}).get('value_per_share')
            if base and abs(base/m['price']-1)>2:
                r['dcf']=None
                r.setdefault('warnings',[]).append('DCF suppressed: mechanical value differed from market price by more than 200%')
        if q.get('ex_net_cash_pe') is not None and q['ex_net_cash_pe']<0:
            q['ex_net_cash_pe']=0.0
            r.setdefault('warnings',[]).append('Net cash exceeds market cap; ex-net-cash P/E floored at zero and should be read as a balance-sheet flag')
    P.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
    print('Postprocessed',P)
if __name__=='__main__':main()
