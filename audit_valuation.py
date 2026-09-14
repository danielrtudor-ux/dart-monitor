#!/usr/bin/env python3
import json
from pathlib import Path

ROOT=Path(__file__).parent
SRC=ROOT/'docs'/'valuation-latest.json'
OUT=ROOT/'docs'/'valuation-audit.json'

def add(flags,level,code,msg): flags.append({'level':level,'code':code,'message':msg})

def main():
    d=json.loads(SRC.read_text())
    audited=[]; counts={'high':0,'medium':0,'low':0}
    for r in d.get('results',[]):
        f=[]; m=r.get('market') or {}; x=r.get('fundamentals') or {}; q=r.get('ratios') or {}; w=r.get('wacc') or {}; dc=r.get('dcf')
        mc=m.get('market_cap'); cash=x.get('cash_like_latest'); debt=x.get('debt_latest'); nc=x.get('net_cash_latest')
        if r.get('security_class_valuation_supported') is False:
            add(f,'low','security_class','Preferred/security-class ticker: issuer-wide valuation intentionally suppressed.')
        if debt is None:
            add(f,'high','debt_missing','Interest-bearing debt was not identified; net-cash and EV-based metrics should not be trusted.')
        if cash is None:
            add(f,'high','cash_missing','Cash-like assets were not identified; net-cash and EV-based metrics should not be trusted.')
        if mc and nc is not None and nc > mc:
            add(f,'medium','net_cash_over_market_cap','Net cash exceeds market cap; plausible for deep-value stocks but requires manual account verification.')
        if debt == 0 and w and w.get('pre_tax_cost_of_debt') not in (None,0):
            add(f,'medium','cost_of_debt_with_zero_debt','Cost of debt is shown despite zero latest identified debt; WACC is equity-only but debt-cost display is not meaningful.')
        if q.get('ex_net_cash_pe') is not None and q.get('ex_net_cash_pe') < 0:
            add(f,'medium','negative_ex_cash_pe','Net cash exceeds equity value, making ex-net-cash P/E negative; treat as a balance-sheet flag, not a conventional multiple.')
        if dc:
            scenarios=(dc.get('scenarios') or {})
            base=scenarios.get('base') or {}
            if m.get('price') and base.get('value_per_share'):
                upside=base['value_per_share']/m['price']-1
                if abs(upside)>2:
                    add(f,'high','extreme_dcf','Base DCF differs from market price by more than 200%; cash-flow normalization should be manually reviewed.')
        if (r.get('beta') or {}).get('reliable') is False:
            add(f,'medium','beta_unreliable','Beta has too few observations; WACC relies on a weak beta estimate.')
        for z in f: counts[z['level']]+=1
        audited.append({'ticker':r.get('ticker'),'company':r.get('company'),'flags':f,'quality':'review' if any(z['level']=='high' for z in f) else ('caution' if f else 'clean')})
    out={'generated_from':d.get('generated_at_kst'),'companies':len(audited),'flag_counts':counts,'results':audited}
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print('Wrote',OUT,counts)
if __name__=='__main__': main()
