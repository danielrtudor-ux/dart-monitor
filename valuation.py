#!/usr/bin/env python3
import io,json,math,os,re,statistics,sys,urllib.parse,urllib.request,zipfile
import xml.etree.ElementTree as ET
from datetime import datetime,timedelta,timezone
from pathlib import Path
BASE='https://opendart.fss.or.kr/api'; KST=timezone(timedelta(hours=9)); ROOT=Path(__file__).parent
OUT=ROOT/'docs'/'valuation-latest.json'; CFG=ROOT/'valuation_config.json'; TICKERS=ROOT/'tickers.txt'
ALIASES={'004365':'004360','002355':'002350','00088K':'000880','37550K':'375500','006405':'006400','000215':'000210','000155':'000150','005387':'005380','011785':'011780','145995':'145990','005725':'005720'}
REPORTS=[('Q3','11014'),('H1','11012'),('Q1','11013')]
def get(url,params=None):
    if params:url+='?'+urllib.parse.urlencode(params)
    r=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 dart-monitor/valuation','Referer':'https://finance.naver.com/'})
    with urllib.request.urlopen(r,timeout=30) as x:return x.read()
def js(url,params=None):return json.loads(get(url,params).decode())
def n(v):
    if v is None:return None
    try:return float(re.sub(r'[^0-9.\-]','',str(v).replace(',','').replace('(','-').replace(')','')))
    except:return None
def div(a,b):return None if a is None or not b else a/b
def rnd(x,d=4):return None if x is None or not math.isfinite(x) else round(x,d)
def clamp(x,a,b):return max(a,min(b,x))
def norm(s):return re.sub(r'[\s·ㆍ,()\-_/]','',(s or '').lower())
def dart(key,ep,**p):
    d=js(f'{BASE}/{ep}',{'crtfc_key':key,**p})
    if d.get('status')=='013':return []
    if d.get('status')!='000':raise RuntimeError(f"DART {d.get('status')}: {d.get('message')}")
    return d.get('list',[])
def corpmap(key):
    raw=get(f'{BASE}/corpCode.xml',{'crtfc_key':key}); z=zipfile.ZipFile(io.BytesIO(raw)); root=ET.fromstring(z.read('CORPCODE.xml'))
    return {(x.findtext('stock_code') or '').strip():{'corp_code':(x.findtext('corp_code') or '').strip(),'corp_name':(x.findtext('corp_name') or '').strip()} for x in root.findall('list') if (x.findtext('stock_code') or '').strip()}
def stmt(key,corp,year,code):
    r=dart(key,'fnlttSinglAcntAll.json',corp_code=corp,bsns_year=str(year),reprt_code=code,fs_div='CFS')
    if r:return r,'CFS'
    return dart(key,'fnlttSinglAcntAll.json',corp_code=corp,bsns_year=str(year),reprt_code=code,fs_div='OFS'),'OFS'
def latest(key,corp,year):
    for label,code in REPORTS:
        r,f=stmt(key,corp,year,code)
        if r:return year,label,code,r,f
    r,f=stmt(key,corp,year-1,'11011');return (year-1,'FY','11011',r,f) if r else None
def annuals(key,corp,year):
    out=[]
    for y in range(year-1,year-5,-1):
        r,f=stmt(key,corp,y,'11011')
        if r:out.append((y,r,f))
    return out
def amount(r,annual):
    if annual or r.get('sj_div')=='BS':return n(r.get('thstrm_amount'))
    v=n(r.get('thstrm_add_amount'));return v if v is not None else n(r.get('thstrm_amount'))
def val(rows,names=(),ids=(),sj=None,annual=False):
    names={norm(x) for x in names};ids={x.lower() for x in ids}
    for r in rows:
        if sj and r.get('sj_div')!=sj:continue
        a=(r.get('account_id') or '').lower()
        if any(a==x or a.endswith(x) for x in ids):
            v=amount(r,annual)
            if v is not None:return v
    for r in rows:
        if sj and r.get('sj_div')!=sj:continue
        if norm(r.get('account_nm')) in names:
            v=amount(r,annual)
            if v is not None:return v
    return None
def sumvals(rows,specs,annual=False,sj='BS'):
    vals=[]
    for names,ids in specs:
        v=val(rows,names,ids,sj,annual)
        if v is not None:vals.append(v)
    return sum(vals) if vals else None
S={'revenue':(('매출액','영업수익','수익(매출액)'),('ifrs-full_Revenue',)),'op':(('영업이익','영업이익(손실)'),('dart_OperatingIncomeLoss',)),'pretax':(('법인세비용차감전순이익','법인세비용차감전이익'),('ifrs-full_ProfitLossBeforeTax',)),'ni':(('당기순이익','당기순이익(손실)','반기순이익','분기순이익'),('ifrs-full_ProfitLoss',)),'pni':(('지배기업의소유주에게귀속되는당기순이익','지배기업소유주지분순이익'),('ifrs-full_ProfitLossAttributableToOwnersOfParent',)),'eq':(('자본총계',),('ifrs-full_Equity',)),'peq':(('지배기업의소유주에게귀속되는자본','지배기업소유주지분'),('ifrs-full_EquityAttributableToOwnersOfParent',)),'assets':(('자산총계',),('ifrs-full_Assets',)),'liab':(('부채총계',),('ifrs-full_Liabilities',)),'cash':(('현금및현금성자산',),('ifrs-full_CashAndCashEquivalents',)),'tax':(('법인세비용','법인세비용(수익)'),('ifrs-full_IncomeTaxExpenseContinuingOperations',)),'interest':(('이자비용',),('ifrs-full_InterestExpense',)),'cfo':(('영업활동현금흐름','영업활동으로인한현금흐름'),('ifrs-full_CashFlowsFromUsedInOperatingActivities',))}
DEBT=[(('단기차입금',),('ifrs-full_ShorttermBorrowings',)),(('유동성장기차입금',),('ifrs-full_CurrentPortionOfLongtermBorrowings',)),(('장기차입금',),('ifrs-full_LongtermBorrowings',)),(('사채',),('ifrs-full_BondsIssued',)),(('유동성사채',),('ifrs-full_CurrentPortionOfBondsIssued',))]
CAPEX=[(('유형자산의취득','유형자산취득'),('ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities',)),(('무형자산의취득','무형자산취득'),('ifrs-full_PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities',))]
def metrics(rows,annual=False):
    m={k:val(rows,*spec,'BS' if k in ('eq','peq','assets','liab','cash') else None,annual) for k,spec in S.items()};m['ni_used']=m['pni'] if m['pni'] is not None else m['ni'];m['eq_used']=m['peq'] if m['peq'] is not None else m['eq'];m['debt']=sumvals(rows,DEBT,annual);st=sumvals(rows,[(('단기금융상품',),('ifrs-full_ShorttermDepositsNotClassifiedAsCashEquivalents',))],annual);m['cash_like']=(m['cash'] or 0)+(st or 0) if m['cash'] is not None or st is not None else None;m['net_cash']=m['cash_like']-m['debt'] if m['cash_like'] is not None and m['debt'] is not None else None;cp=[abs(x) for x in (val(rows,*z,'CF',annual) for z in CAPEX) if x is not None];m['capex']=sum(cp) if cp else None;return m
def shares(key,corp,year,code):
    r=dart(key,'stockTotqySttus.json',corp_code=corp,bsns_year=str(year),reprt_code=code)
    for s in ('합계','보통주'):
        for x in r:
            if s in str(x.get('se') or ''):
                v=n(x.get('distb_stock_co')) or n(x.get('istc_totqy'))
                if v:return v
    vs=[n(x.get('distb_stock_co')) for x in r];vs=[x for x in vs if x];return max(vs) if vs else None
def quote(t):
    d=js(f'https://m.stock.naver.com/api/stock/{t}/basic');return n(d.get('closePrice')),((d.get('stockExchangeType') or {}).get('name') or ''),d
def history(kind,code):
    url=f'https://api.stock.naver.com/chart/domestic/{"item" if kind=="stock" else "index"}/{code}';end=datetime.now(KST).date();start=end-timedelta(days=1830);d=js(url,{'periodType':'monthCandle','startDateTime':start.strftime('%Y%m%d'),'endDateTime':end.strftime('%Y%m%d')});r=d.get('priceInfos',[]) if isinstance(d,dict) else d;return sorted([(str(x.get('localDate')),n(x.get('closePrice'))) for x in r if n(x.get('closePrice'))])
def beta(sh,mh,cfg):
    def rr(h):return {h[i][0][:6]:h[i][1]/h[i-1][1]-1 for i in range(1,len(h)) if h[i-1][1]}
    a,b=rr(sh),rr(mh);ks=sorted(set(a)&set(b))
    if len(ks)<18:return {'raw':None,'adjusted':None,'used':1.0,'observations':len(ks),'reliable':False}
    x=[b[k] for k in ks];y=[a[k] for k in ks];xm,ym=statistics.mean(x),statistics.mean(y);vv=sum((z-xm)**2 for z in x);raw=sum((xx-xm)*(yy-ym) for xx,yy in zip(x,y))/vv if vv else None;adj=.67*raw+.33 if raw is not None else None;used=clamp(adj,cfg['beta_floor'],cfg['beta_ceiling']) if adj is not None else 1;return {'raw':rnd(raw,3),'adjusted':rnd(adj,3),'used':rnd(used,3),'observations':len(ks),'reliable':len(ks)>=36}
def wacc(mc,cur,a0,a1,b,cfg):
    d=max(0,cur.get('debt') or 0);ke=cfg['risk_free_rate']+(b.get('used') or 1)*cfg['equity_risk_premium'];avd=((a0.get('debt') or 0)+(a1.get('debt') or 0))/2 if a1 else a0.get('debt');kd=div(abs(a0.get('interest')) if a0.get('interest') is not None else None,avd);kd=kd if kd and 0<kd<.2 else cfg['fallback_cost_of_debt'];tr=div(abs(a0.get('tax')) if a0.get('tax') is not None else None,a0.get('pretax'));tr=tr if tr is not None and 0<=tr<=.45 else cfg['fallback_tax_rate'];tot=mc+d;return {'wacc':rnd(mc/tot*ke+d/tot*kd*(1-tr)),'cost_of_equity':rnd(ke),'pre_tax_cost_of_debt':rnd(kd),'tax_rate':rnd(tr),'risk_free_rate':cfg['risk_free_rate'],'equity_risk_premium':cfg['equity_risk_premium']}
def fcff(m):
    if m.get('cfo') is None or m.get('capex') is None:return None
    tr=div(abs(m.get('tax')) if m.get('tax') is not None else None,m.get('pretax'));tr=tr if tr is not None and 0<=tr<=.45 else .24;return m['cfo']-m['capex']+(abs(m.get('interest') or 0)*(1-tr))
def dcf(hist,cur,sh,wi,cfg):
    fs=[fcff(x['m']) for x in hist];fs=[x for x in fs if x and x>0]
    if not fs or not wi or not sh:return None
    start=statistics.median(fs[:3]);revs=[(x['y'],x['m'].get('revenue')) for x in reversed(hist) if x['m'].get('revenue')];g=.03
    if len(revs)>=3 and revs[0][1]>0 and revs[-1][1]>0:g=(revs[-1][1]/revs[0][1])**(1/max(1,revs[-1][0]-revs[0][0]))-1
    g=clamp(g,cfg['growth_floor'],cfg['growth_ceiling']);nc=cur.get('net_cash') or 0;sets={'bear':(g-.02,wi['wacc']+cfg['wacc_spread_bear'],cfg['terminal_growth_bear']),'base':(g,wi['wacc'],cfg['terminal_growth_base']),'bull':(g+.02,max(.04,wi['wacc']+cfg['wacc_spread_bull']),cfg['terminal_growth_bull'])};out={}
    for name,(gg,wa,tg) in sets.items():
        gg=clamp(gg,cfg['growth_floor'],cfg['growth_ceiling']);f=start;pv=0
        if wa<=tg+.005:out[name]=None;continue
        for y in range(1,cfg['forecast_years']+1):f*=1+(gg+(tg-gg)*y/cfg['forecast_years']);pv+=f/(1+wa)**y
        ev=pv+(f*(1+tg)/(wa-tg))/(1+wa)**cfg['forecast_years'];out[name]={'value_per_share':rnd((ev+nc)/sh,0),'enterprise_value':rnd(ev,0),'wacc':rnd(wa),'initial_growth':rnd(gg),'terminal_growth':rnd(tg)}
    return {'method':'5-year FCFF proxy DCF','scenarios':out}
def main():
    key=os.getenv('DART_API_KEY');
    if not key:sys.exit('Missing DART_API_KEY')
    cfg=json.loads(CFG.read_text()) if CFG.exists() else {};cmap=corpmap(key);now=datetime.now(KST);idx={};results=[];errors=[];ts=[];seen=set()
    for x in TICKERS.read_text().splitlines():
        x=x.strip()
        if x and not x.startswith('#') and x not in seen:seen.add(x);ts.append(x)
    for t in ts:
        dt=ALIASES.get(t,t);ci=cmap.get(dt)
        if not ci:errors.append({'ticker':t,'error':'not in DART'});continue
        try:
            la=latest(key,ci['corp_code'],now.year);y,label,code,rows,fsdiv=la;cur=metrics(rows,label=='FY');ahs=annuals(key,ci['corp_code'],now.year);hist=[{'y':yy,'m':metrics(rr,True)} for yy,rr,_ in ahs]
            if not hist:raise RuntimeError('no annual statements')
            sh=shares(key,ci['corp_code'],y,code);p,ex,qd=quote(t);alias=t!=dt;mc=p*sh if p and sh and not alias else None;bench='KOSDAQ' if 'KOSDAQ' in ex.upper() else 'KOSPI';bb={'raw':None,'adjusted':None,'used':1.0,'observations':0,'reliable':False}
            try:
                if bench not in idx:idx[bench]=history('index',bench)
                bb=beta(history('stock',t),idx[bench],cfg)
            except Exception:pass
            a0=hist[0]['m'];a1=hist[1]['m'] if len(hist)>1 else None;wi=wacc(mc,cur,a0,a1,bb,cfg) if mc else None;dc=dcf(hist,cur,sh,wi,cfg) if mc else None;earn=a0.get('ni_used');eq=cur.get('eq_used');nc=cur.get('net_cash');op=a0.get('op');rev=a0.get('revenue');ev=mc-nc if mc is not None and nc is not None else None
            results.append({'ticker':t,'dart_ticker':dt,'company':ci['corp_name'],'security_class_valuation_supported':not alias,'market':{'price':p,'exchange':ex,'benchmark_index':bench,'shares_used':rnd(sh,0),'market_cap':rnd(mc,0),'traded_at':qd.get('localTradedAt')},'financial_basis':{'latest_balance_sheet':f'{y} {label}','latest_earnings':f'FY{hist[0]["y"]}','fs_div':fsdiv},'fundamentals':{'revenue_fy':rnd(rev,0),'operating_profit_fy':rnd(op,0),'net_income_fy':rnd(earn,0),'equity_latest':rnd(eq,0),'cash_like_latest':rnd(cur.get('cash_like'),0),'debt_latest':rnd(cur.get('debt'),0),'net_cash_latest':rnd(nc,0)},'ratios':{'pe':rnd(div(mc,earn),2) if earn and earn>0 else None,'pb':rnd(div(mc,eq),2) if eq and eq>0 else None,'ev_to_ebit':rnd(div(ev,op),2) if op and op>0 else None,'eps':rnd(div(earn,sh),0),'bvps':rnd(div(eq,sh),0),'net_cash_per_share':rnd(div(nc,sh),0),'net_cash_pct_market_cap':rnd(div(nc,mc),4),'ex_net_cash_pe':rnd(div(mc-max(0,nc or 0),earn),2) if mc and earn and earn>0 else None,'operating_margin':rnd(div(op,rev),4),'roe_simple':rnd(div(earn,eq),4)},'beta':bb,'wacc':wi,'dcf':dc,'warnings':['Preferred/security-class ticker: issuer-wide valuation omitted'] if alias else []});print('OK',t,ci['corp_name'])
        except Exception as e:errors.append({'ticker':t,'company':ci['corp_name'],'error':str(e)});print('ERROR',t,e,file=sys.stderr)
    payload={'generated_at_kst':now.isoformat(),'engine_version':'1.0','sources':{'accounting':'OpenDART','market':'Naver Finance public endpoints'},'assumptions':cfg,'methodology_notes':['P/E uses latest completed fiscal-year earnings; balance-sheet ratios use latest filing.','Net cash includes cash equivalents and explicitly disclosed short-term financial products minus identified interest-bearing debt.','Beta uses up to five years of monthly returns vs KOSPI/KOSDAQ, Blume adjusted and bounded for WACC.','DCF is a mechanical scenario tool, not a target price.'],'ticker_count':len(ts),'company_count':len(results),'error_count':len(errors),'results':results,'errors':errors};OUT.parent.mkdir(exist_ok=True);OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n');print('Wrote',OUT)
if __name__=='__main__':main()
