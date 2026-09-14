#!/usr/bin/env python3
import io,json,math,os,re,statistics,sys,urllib.parse,urllib.request,zipfile
import xml.etree.ElementTree as ET
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
from accounting import ttm_income, income, debt_accounts, company_type, evidence
from postprocess_valuation import process
from valuation_adjustments import fetch_fx, currency_rate, applicable_review, apply_note_balance, owner_accounts
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
@lru_cache(maxsize=4096)
def dart(key,ep,**p):
    d=js(f'{BASE}/{ep}',{'crtfc_key':key,**p})
    if d.get('status')=='013':return []
    if d.get('status')!='000':raise RuntimeError(f"DART {d.get('status')}: {d.get('message')}")
    return d.get('list',[])
def corpmap(key):
    raw=get(f'{BASE}/corpCode.xml',{'crtfc_key':key}); z=zipfile.ZipFile(io.BytesIO(raw)); root=ET.fromstring(z.read('CORPCODE.xml'))
    return {(x.findtext('stock_code') or '').strip():{'corp_code':(x.findtext('corp_code') or '').strip(),'corp_name':(x.findtext('corp_name') or '').strip()} for x in root.findall('list') if (x.findtext('stock_code') or '').strip()}
@lru_cache(maxsize=2048)
def stmt(key,corp,year,code,fs_div=None):
    if fs_div:
        return dart(key,'fnlttSinglAcntAll.json',corp_code=corp,bsns_year=str(year),reprt_code=code,fs_div=fs_div),fs_div
    r=dart(key,'fnlttSinglAcntAll.json',corp_code=corp,bsns_year=str(year),reprt_code=code,fs_div='CFS')
    if r:return r,'CFS'
    return dart(key,'fnlttSinglAcntAll.json',corp_code=corp,bsns_year=str(year),reprt_code=code,fs_div='OFS'),'OFS'
def latest(key,corp,year):
    for label,code in REPORTS:
        if year == datetime.now(KST).year and datetime.now(KST).month <= {'Q3':9,'H1':6,'Q1':3}[label]:continue
        r,f=stmt(key,corp,year,code)
        if r:return year,label,code,r,f
    r,f=stmt(key,corp,year-1,'11011');return (year-1,'FY','11011',r,f) if r else None
def annuals(key,corp,year,fs_div=None):
    out=[]
    for y in range(year-1,year-5,-1):
        r,f=stmt(key,corp,y,'11011',fs_div)
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
    m={k:val(rows,*spec,'BS' if k in ('eq','peq','assets','liab','cash') else None,annual) for k,spec in S.items()};m['ni_used']=m['pni'] if m['pni'] is not None else m['ni'];m['eq_used']=m['peq'] if m['peq'] is not None else m['eq'];m['debt_evidence']=debt_accounts(rows);m['debt']=m['debt_evidence']['value'];st=sumvals(rows,[(('단기금융상품',),('ifrs-full_ShorttermDepositsNotClassifiedAsCashEquivalents',))],annual);m['cash_like']=(m['cash'] or 0)+(st or 0) if m['cash'] is not None or st is not None else None;m['net_cash']=m['cash_like']-m['debt'] if m['cash_like'] is not None and m['debt'] is not None else None;cp=[abs(x) for x in (val(rows,*z,'CF',annual) for z in CAPEX) if x is not None];m['capex']=sum(cp) if cp else None
    for k,v in income(rows,'thstrm_amount' if annual else 'thstrm_add_amount').items():m[k]=v['value']
    m['ni_used']=m['pni'] if m['pni'] is not None else m['ni']
    return m
def shares(key,corp,year,code):
    r=dart(key,'stockTotqySttus.json',corp_code=corp,bsns_year=str(year),reprt_code=code)
    for s in ('보통주','합계'):
        for x in r:
            if s in str(x.get('se') or ''):
                v=n(x.get('distb_stock_co'))
                if v is None:
                    issued,treasury=n(x.get('istc_totqy')),n(x.get('tesstk_co'))
                    v=issued-treasury if issued is not None and treasury is not None else None
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
def dcf(hist,cur,sh,wi,cfg,nci_proxy=0):
    fs=[fcff(x['m']) for x in hist];fs=[x for x in fs if x and x>0]
    if not fs or not wi or not sh:return None
    start=statistics.median(fs[:3]);revs=[(x['y'],x['m'].get('revenue')) for x in reversed(hist) if x['m'].get('revenue')];g=.03
    if len(revs)>=3 and revs[0][1]>0 and revs[-1][1]>0:g=(revs[-1][1]/revs[0][1])**(1/max(1,revs[-1][0]-revs[0][0]))-1
    g=clamp(g,cfg['growth_floor'],cfg['growth_ceiling']);nc=cur.get('net_cash') or 0;sets={'bear':(g-.02,wi['wacc']+cfg['wacc_spread_bear'],cfg['terminal_growth_bear']),'base':(g,wi['wacc'],cfg['terminal_growth_base']),'bull':(g+.02,max(.04,wi['wacc']+cfg['wacc_spread_bull']),cfg['terminal_growth_bull'])};out={}
    for name,(gg,wa,tg) in sets.items():
        gg=clamp(gg,cfg['growth_floor'],cfg['growth_ceiling']);f=start;pv=0
        if wa<=tg+.005:out[name]=None;continue
        for y in range(1,cfg['forecast_years']+1):f*=1+(gg+(tg-gg)*y/cfg['forecast_years']);pv+=f/(1+wa)**y
        ev=pv+(f*(1+tg)/(wa-tg))/(1+wa)**cfg['forecast_years'];out[name]={'value_per_share':rnd((ev+nc-nci_proxy)/sh,0),'enterprise_value':rnd(ev,0),'wacc':rnd(wa),'initial_growth':rnd(gg),'terminal_growth':rnd(tg)}
    return {'method':'5-year FCFF proxy DCF','scenarios':out}


VALIDATION_TICKERS = {'003240','066620','003960','053700','103140','029530','024830','000590','323410','055550'}


def calculate(t, key, cmap, now, idx, cfg):
    dt = ALIASES.get(t,t)
    ci = cmap.get(dt)
    if not ci:
        raise RuntimeError('not in DART')
    la = latest(key,ci['corp_code'],now.year)
    if not la:
        raise RuntimeError('no current statements')
    y,label,code,rows,fsdiv = la
    cur = metrics(rows,label=='FY')
    reviews=json.loads((ROOT/'note_review_facts.json').read_text())
    review=applicable_review(dt,rows,fsdiv,reviews)
    cur=apply_note_balance(cur,review)
    ownership=owner_accounts(rows,fsdiv,review)
    ahs = annuals(key,ci['corp_code'],now.year,fsdiv)
    hist = [{'y':yy,'m':metrics(rr,True)} for yy,rr,_ in ahs]
    if not hist:
        raise RuntimeError('no annual statements on matching statement basis')
    ay,arows,afs = ahs[0]
    bridge = ttm_income(rows,arows,y,label,fsdiv,ay,afs)
    used = {k:bridge[k]['used'] for k in ('revenue','op','pretax','ni','pni')}
    earnings_key = bridge['earnings_key']
    earn = used[earnings_key]
    if review.get('hybrid_distribution_ttm') is not None and earn is not None:
        earn -= review['hybrid_distribution_ttm']
    op,rev,pretax = used['op'],used['revenue'],used['pretax']
    warnings = []
    try:
        profile = js(f'{BASE}/company.json',{'crtfc_key':key,'corp_code':ci['corp_code']})
        if profile.get('status') != '000':
            raise RuntimeError('company profile unavailable')
    except Exception:
        profile = {}
        warnings.append('DART industry profile unavailable; classification uses ticker/name rules')
    ctype,classification_source = company_type(dt,ci['corp_name'],profile.get('induty_code'))
    currencies = {r.get('currency') for r in rows if r.get('currency')}
    accounting_currency = next(iter(currencies)) if len(currencies)==1 else 'unknown_or_mixed'
    fx=fetch_fx(get,now.date()) if accounting_currency=='USD' else None
    rate=currency_rate(accounting_currency,fx)
    currency_supported = rate is not None
    sh = shares(key,ci['corp_code'],y,code)
    share_rows = dart(key,'stockTotqySttus.json',corp_code=ci['corp_code'],bsns_year=str(y),reprt_code=code)
    preferred_shares = sum(n(x.get('distb_stock_co')) or 0 for x in share_rows if '우선주' in (x.get('se') or ''))
    if preferred_shares:
        warnings.append('Multiple share classes: market cap uses common shares excluding treasury; P/E and P/B are issuer-income/equity proxies and EV excludes unpriced preferred equity')
    p,ex,qd = quote(t)
    alias = t != dt
    mc = p*sh if p and sh and not alias else None
    mc_native=mc/rate if mc is not None and rate else None
    bench = 'KOSDAQ' if 'KOSDAQ' in ex.upper() else 'KOSPI'
    bb = {'raw':None,'adjusted':None,'used':1.0,'observations':0,'reliable':False}
    try:
        bb = beta(history('stock',t),idx[bench],cfg)
    except Exception:
        warnings.append('Market history unavailable for beta')
    a0 = hist[0]['m']
    a1 = hist[1]['m'] if len(hist)>1 else None
    debt_known = cur['debt'] is not None
    nci_proxy=ownership['nci_ev_proxy']
    wi = wacc(mc_native+(nci_proxy or 0),cur,a0,a1,bb,cfg) if mc_native and debt_known and nci_proxy is not None and ctype != 'financial' else None
    cash_unresolved=review.get('cash_status')=='restricted_short_term_deposit_amount_unresolved'
    dc = dcf(hist,cur,sh,wi,cfg,nci_proxy) if mc_native and cur['net_cash'] is not None and ctype == 'operating' and nci_proxy is not None and not preferred_shares and not cash_unresolved else None
    if dc and rate!=1:
        for scenario in dc['scenarios'].values():
            if scenario and scenario['value_per_share'] is not None:scenario['value_per_share']=rnd(scenario['value_per_share']*rate,0)
        dc['share_value_currency']='KRW';dc['enterprise_value_currency']=accounting_currency
    eq,nc = cur.get('eq_used'),cur.get('net_cash')
    if ownership['hybrid_parent_book'] is not None and eq is not None:eq-=ownership['hybrid_parent_book']
    ev = mc_native-nc+nci_proxy if mc_native is not None and nc is not None and nci_proxy is not None and ctype != 'financial' and not preferred_shares and not cash_unresolved else None
    financial = ctype == 'financial'
    same_margin_basis = lambda k: bridge[k]['basis'] == bridge['revenue']['basis']
    if alias:
        warnings.append('Preferred/security-class ticker: issuer-wide valuation omitted')
    for k in ('revenue','op','pretax',earnings_key):
        if bridge[k]['reason']:
            warnings.append(f'{k}: {bridge[k]["basis"]}; {bridge[k]["reason"]}')
    if bridge['net_income_basis'] == 'total_including_noncontrolling_interests':
        warnings.append('Parent earnings unavailable: P/E uses total income including noncontrolling interests')
    if not debt_known and not financial:
        warnings.append('Debt is unknown or accounts are unrecognized; net-cash, EV and DCF suppressed')
    if not review and dt in reviews:warnings.append('Filing receipt or statement basis changed; prior note review was not applied')
    if review.get('cash_status')=='restricted_short_term_deposit_amount_unresolved':
        warnings.append('Restricted short-term deposits are disclosed without an amount; cash-dependent valuation remains provisional')
    if nci_proxy and not financial:warnings.append('Enterprise value and DCF subtract noncontrolling interest at book value as a proxy')
    if ownership['hybrid_status']=='unreviewed':warnings.append('Hybrid equity identified but distributions and common-equity allocation remain unreviewed')
    result = {
        'ticker':t,'dart_ticker':dt,'company':ci['corp_name'],
        'company_type':ctype,'classification_source':classification_source,'industry_code':profile.get('induty_code'),
        'security_class_valuation_supported':not alias,
        'market':{'price':p,'exchange':ex,'benchmark_index':bench,'shares_used':rnd(sh,0),'market_cap':rnd(mc,0),'market_cap_accounting_currency':rnd(mc_native,0),'traded_at':qd.get('localTradedAt')},
        'financial_basis':{'latest_balance_sheet':f'{y} {label}','latest_earnings':bridge[earnings_key]['basis'],'fs_div':fsdiv,'net_income_basis':bridge['net_income_basis'],'accounting_currency':accounting_currency,'market_currency':'KRW','currency_conversion_supported':currency_supported,'fx':fx,'preferred_shares_outstanding':preferred_shares,'share_basis':'common outstanding, excluding treasury; aggregate fallback if class not labelled',
                           'ratio_earnings':{'pe':bridge[earnings_key]['basis'],'ev_to_ebit':bridge['op']['basis'],'revenue':bridge['revenue']['basis'],'pretax':bridge['pretax']['basis']}},
        'fundamentals':{'revenue_fy':rnd(a0.get('revenue'),0),'operating_profit_fy':rnd(a0.get('op'),0),'pretax_income_fy':rnd(a0.get('pretax'),0),'net_income_fy':rnd(a0.get('ni_used'),0),
                        'revenue_ttm':rnd(bridge['revenue']['ttm'],0),'operating_profit_ttm':rnd(bridge['op']['ttm'],0),'pretax_income_ttm':rnd(bridge['pretax']['ttm'],0),
                        'parent_net_income_ttm':rnd(bridge['pni']['ttm'],0),'total_net_income_ttm':rnd(bridge['ni']['ttm'],0),'net_income_ttm':rnd(bridge[earnings_key]['ttm'],0),'common_net_income_ttm':rnd(earn,0),'hybrid_distribution_ttm':review.get('hybrid_distribution_ttm'),
                        'equity_latest':rnd(eq,0),'cash_like_latest':rnd(cur.get('cash_like'),0),'debt_latest':rnd(cur.get('debt'),0),'net_cash_latest':rnd(nc,0) if not financial else None,
                        'debt_status':cur['debt_evidence']['status'] if not financial else 'sector_not_applicable', 'identified_debt_sum':cur['debt_evidence']['identified_sum'],
                        'restricted_cash_in_cash_like':rnd(cur.get('restricted_cash'),0),'usable_net_cash_latest':rnd(cur.get('usable_net_cash'),0),'cash_review_status':cur.get('cash_review_status')},
        'ratios':{'pe':rnd(div(mc_native,earn),2) if earn and earn>0 and not preferred_shares else None,'pb':rnd(div(mc_native,eq),2) if eq and eq>0 and not preferred_shares else None,
                  'ev_to_ebit':rnd(div(ev,op),2) if op and op>0 else None,'eps':rnd(div(earn*rate,sh),0) if not alias and rate and not preferred_shares else None,'bvps':rnd(div(eq*rate,sh),0) if not alias and rate and not preferred_shares and eq is not None else None,
                  'net_cash_per_share':rnd(div(nc*rate,sh),0) if not financial and not alias and nc is not None and rate and not cash_unresolved else None,'net_cash_pct_market_cap':rnd(div(nc,mc_native),4) if not financial and not cash_unresolved else None,
                  'ex_net_cash_pe':rnd(div(mc_native-max(0,nc)+nci_proxy,earn),2) if mc_native and nc is not None and nci_proxy is not None and earn and earn>0 and not financial and not preferred_shares and not cash_unresolved else None,
                  'operating_margin':rnd(div(op,rev),4) if same_margin_basis('op') else None,
                  'pretax_margin':rnd(div(pretax,rev),4) if same_margin_basis('pretax') else None,
                  'net_margin':rnd(div(used['ni'],rev),4) if same_margin_basis('ni') else None,
                  'roe_simple':rnd(div(earn,eq),4)},
        'ttm_bridge':bridge,'debt_evidence':cur['debt_evidence'],'note_review':review,'ownership':ownership,
        'beta':bb,'wacc':wi,'dcf':dc,'warnings':warnings,
    }
    if dt in VALIDATION_TICKERS:
        result['validation_accounts'] = {
            'current':{'year':y,'report_code':code,'fs_div':fsdiv,'rows':[r for r in rows if r.get('sj_div') in ('BS','IS','CIS')]},
            'annual':{'year':ay,'report_code':'11011','fs_div':afs,'rows':[r for r in arows if r.get('sj_div') in ('BS','IS','CIS')]},
            'shares':share_rows,
        }
    print('OK',t,ci['corp_name'],bridge[earnings_key]['basis'],flush=True)
    return result


def main():
    key = os.getenv('DART_API_KEY')
    if not key:
        sys.exit('Missing DART_API_KEY')
    cfg = json.loads(CFG.read_text())
    cmap = corpmap(key)
    now = datetime.now(KST)
    idx = {}
    for benchmark in ('KOSPI','KOSDAQ'):
        try:idx[benchmark] = history('index',benchmark)
        except Exception:idx[benchmark] = []
    tickers = list(dict.fromkeys(x.strip() for x in TICKERS.read_text().splitlines() if x.strip() and not x.strip().startswith('#')))
    def run(t):
        try:return calculate(t,key,cmap,now,idx,cfg),None
        except Exception as e:
            print('ERROR',t,type(e).__name__,str(e),file=sys.stderr,flush=True)
            return None,{'ticker':t,'error':str(e)}
    with ThreadPoolExecutor(max_workers=6) as executor:
        completed = list(executor.map(run,tickers))
    results = [r for r,e in completed if r is not None]
    errors = [e for r,e in completed if e is not None]
    payload = {'generated_at_kst':now.isoformat(),'engine_version':'1.2-ttm','sources':{'accounting':'OpenDART','market':'Naver Finance public endpoints'},'assumptions':cfg,
               'methodology_notes':['TTM = prior full year + current interim cumulative - prior-comparable cumulative from the current filing, on matching CFS/OFS and currency bases.',
                                    'Missing TTM components use explicitly labelled annual fallback; income is selected only from IS/CIS.',
                                    'Debt includes identified borrowings, bonds and lease liabilities; unrecognized accounts remain unknown, not zero.',
                                    'Cash-like assets include cash equivalents and explicit short-term deposits, not all investments; restrictions require note review.',
                                    'Beta uses monthly returns; FCFF DCF remains a mechanical scenario tool with annual cash-flow inputs.'],
               'ticker_count':len(tickers),'company_count':len(results),'error_count':len(errors),'results':results,'errors':errors}
    OUT.parent.mkdir(exist_ok=True)
    payload = process(payload)
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
    print('Wrote',OUT,flush=True)
    if not results:
        sys.exit('No companies valued')


if __name__=='__main__':
    main()
