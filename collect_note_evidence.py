"""Save readable, receipt-pinned DART original filings for account-note review."""
import io
import json
import os
import re
import zipfile
import urllib.parse
import urllib.request
from pathlib import Path
from html.parser import HTMLParser
from concurrent.futures import ThreadPoolExecutor

ROOT=Path(__file__).parent
OUT=ROOT/'docs'/'diligence'

class Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag in ('tr','p','title','section-1','section-2','table','br'):
            self.parts.append('\n')
        if tag in ('td','th','te','tu'):
            self.parts.append(' | ')
    def handle_endtag(self,tag):
        if tag in ('tr','p','title','table'):
            self.parts.append('\n')
    def handle_data(self,data):
        self.parts.append(re.sub(r'\s+',' ',data))
    def text(self):
        return '\n'.join(x.strip() for x in ''.join(self.parts).splitlines() if x.strip())+'\n'


def collect(item):
    ticker,receipt=item
    path=OUT/f'{ticker}_{receipt}.txt'
    if path.exists():
        return {'ticker':ticker,'receipt':receipt,'path':str(path.relative_to(ROOT)),'cached':True}
    params=urllib.parse.urlencode({'crtfc_key':os.environ['DART_API_KEY'],'rcept_no':receipt})
    request=urllib.request.Request('https://opendart.fss.or.kr/api/document.xml?'+params,headers={'User-Agent':'dart-monitor note review'})
    with urllib.request.urlopen(request,timeout=60) as response:
        raw=response.read()
    archive=zipfile.ZipFile(io.BytesIO(raw))
    texts=[]
    for name in archive.namelist():
        if not name.lower().endswith(('.xml','.html','.htm')):continue
        raw=archive.read(name)
        for encoding in ('utf-8','cp949','euc-kr'):
            try:body=raw.decode(encoding);break
            except UnicodeDecodeError:continue
        else:body=raw.decode('utf-8',errors='replace')
        parser=Text();parser.feed(body)
        texts.append('ARCHIVE MEMBER: '+name+'\n'+parser.text())
    if not texts:raise RuntimeError('No textual filing members')
    path.write_text(f'DART receipt {receipt}\nSource: https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}\n\n'+'\n'.join(texts))
    return {'ticker':ticker,'receipt':receipt,'path':str(path.relative_to(ROOT)),'characters':len(path.read_text())}


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    targets=json.loads((ROOT/'note_review_targets.json').read_text())
    items=[]
    for t in targets:
        items.append((t['ticker'],t['current_receipt']))
        if t['ticker'] in ('055550','003960','323410'):
            items.append((t['ticker'],t['annual_receipt']))
    def safe(item):
        try:return collect(item)
        except Exception as e:return {'ticker':item[0],'receipt':item[1],'error':type(e).__name__}
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(safe,items))
    (OUT/'manifest.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(results,ensure_ascii=False))
    if any('error' in r for r in results):raise SystemExit('Some receipt downloads failed; inspect manifest')

if __name__=='__main__':main()
