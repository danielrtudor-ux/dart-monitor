#!/usr/bin/env python3
import argparse,json,os,re
from datetime import datetime,timedelta,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parent; KST=timezone(timedelta(hours=9))
def clean(v):
 v=str(v or '').strip().upper()
 if not re.fullmatch(r'[0-9A-Z]{6}',v): raise SystemExit(f'Invalid ticker: {v!r}')
 return v
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('ticker',nargs='?'); ap.add_argument('--dart-ticker'); a=ap.parse_args()
 ticker=clean(a.ticker or os.environ.get('COMPANY_TICKER')); explicit=a.dart_ticker or os.environ.get('DART_TICKER'); explicit=clean(explicit) if explicit else None
 import governance_collector as gc, governance_analyzer as ga, agm_collector as ac, agm_parser as agp, activist_ranker as ar
 dart=explicit or gc.DART_TICKER_OVERRIDES.get(ticker,ticker)
 work=ROOT/'governance'/'ad_hoc'/ticker; work.mkdir(parents=True,exist_ok=True)
 raw=work/'governance_company.json'; prof=work/'governance_profile.json'; filings=work/'agm_filings.json'; votes=work/'agm_votes.json'; rank=work/'governance_ranking.json'
 print(f'Ad-hoc governance analysis: security={ticker}, DART ticker={dart}')
 gc.OUT_DIR=work; gc.OUT_FILE=raw; gc.load_securities=lambda:[{'ticker':ticker,'dart_ticker':dart,'label':f'ad-hoc:{ticker}'}]; gc.main()
 r=json.loads(raw.read_text(encoding='utf-8'))
 if not r.get('companies'):
  hint='' if explicit else ' If this is a preferred/share-class security, rerun with its underlying ordinary-share ticker in the DART ticker field.'
  raise SystemExit(f'OpenDART could not resolve {ticker} (DART ticker {dart}).{hint}')
 ga.RAW_FILE=raw; ga.OUT_FILE=prof; ga.main()
 ac.RAW_FILE=raw; ac.OUT_FILE=filings; ac.main()
 agp.IN_FILE=filings; agp.OUT_FILE=votes; agp.main()
 ar.GOV=prof; ar.AGM=votes; ar.OUT=rank; ar.main()
 pj=json.loads(prof.read_text(encoding='utf-8')); vj=json.loads(votes.read_text(encoding='utf-8')); rj=json.loads(rank.read_text(encoding='utf-8'))
 profile=(pj.get('profiles') or [None])[0]; agm=(vj.get('companies') or [None])[0]; rr=(rj.get('rankings') or [None])[0]
 payload={'ad_hoc_report_version':'1.0','generated_at_kst':datetime.now(KST).isoformat(),'security_ticker':ticker,'dart_ticker':dart,'company':(profile or {}).get('company'),'purpose':'Single-company governance / activist-opportunity research using the same DART framework as the monitored universe.','governance_profile':profile,'agm_analysis':agm,'provisional_opportunity_assessment':rr,'caveats':['Investment-research screen; not investment advice or a legal opinion.','Governance/value-unlock score is a DART-derived governance proxy, not a valuation model.','High-priority companies still require manual review of valuation, articles, friendly blocks, NPS/institutional ownership, current law and case law.']}
 pub=ROOT/'docs'/'governance'; pub.mkdir(parents=True,exist_ok=True)
 for f in (pub/f'{ticker}.json',pub/'latest.json'): f.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(f'Wrote {pub/f"{ticker}.json"}')
 if rr: print('Overall provisional activist opportunity:',rr.get('scores',{}).get('overall_provisional_activist_opportunity'),'|',rr.get('review_band'))
if __name__=='__main__': main()
