"""READ-ONLY Everything Art source diagnostic: BRIC, Lincoln Center, Film at Lincoln Center, New York Live Arts.
Paste into scripts/diagnose_art_event_sources.py and run the existing diagnostic GitHub Action.
Does not write files or change published events.
"""
import re
import json
import urllib.request
import urllib.error
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

SOURCES = {
    'BRIC': 'https://bricartsmedia.org/events/',
    'Lincoln Center': 'https://www.lincolncenter.org/series/lincoln-center-presents/v/calendar',
    'Film at Lincoln Center': 'https://www.filmlinc.org/',
    'New York Live Arts': 'https://newyorklivearts.org/',
}
MONTH = r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
DATE_PATTERNS = [
    re.compile(r'\b' + MONTH + r'\s+\d{1,2}(?:\s*[-–]\s*\d{1,2})?,?\s+20\d{2}\b', re.I),
    re.compile(r'\b20\d{2}-\d{2}-\d{2}\b'),
    re.compile(r'\b\d{1,2}/\d{1,2}/20\d{2}\b'),
]
class Scan(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self.text=[]; self.scripts=[]; self._jsonld=False; self._script=[]
    def handle_starttag(self, tag, attrs):
        d=dict(attrs)
        if tag=='a' and d.get('href'): self.links.append(d['href'])
        if tag=='script' and 'ld+json' in d.get('type','').lower(): self._jsonld=True; self._script=[]
    def handle_endtag(self, tag):
        if tag=='script' and self._jsonld: self.scripts.append(''.join(self._script)); self._jsonld=False
    def handle_data(self, data):
        if self._jsonld: self._script.append(data)
        else: self.text.append(data)

def jsonld_events(obj):
    if isinstance(obj, list): return sum(jsonld_events(x) for x in obj)
    if isinstance(obj, dict):
        typ=obj.get('@type',[]); typ=[typ] if isinstance(typ,str) else typ
        n=1 if any(str(t).lower().endswith('event') for t in typ) and obj.get('startDate') else 0
        return n+sum(jsonld_events(v) for v in obj.values() if isinstance(v,(list,dict)))
    return 0

def inspect(name,url):
    print('\n'+'='*70+'\n'+name+' | '+url,flush=True)
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; EverythingArtDiagnostic/1.0)','Accept':'text/html,application/xhtml+xml'})
    try:
        with urllib.request.urlopen(req,timeout=22) as resp:
            body=resp.read(1_500_000); final=resp.geturl(); status=resp.status; ctype=resp.headers.get('Content-Type','')
    except Exception as e:
        print('FETCH FAILED:',type(e).__name__,str(e)[:220],flush=True); return
    print('HTTP:',status,'| final URL:',final,'| bytes:',len(body),'| content type:',ctype,flush=True)
    html=body.decode('utf-8','replace'); p=Scan()
    try: p.feed(html)
    except Exception as e: print('HTML parse warning:',str(e)[:150])
    plain=' '.join(p.text); plain=re.sub(r'\s+',' ',plain)
    dates=[]
    for pat in DATE_PATTERNS:
        for m in pat.finditer(plain):
            s=m.group(0)
            if s not in dates: dates.append(s)
    print('Visible date examples:',dates[:12],flush=True)
    print('JSON-LD blocks:',len(p.scripts),flush=True)
    count=0
    for s in p.scripts:
        try: count+=jsonld_events(json.loads(s))
        except (ValueError,TypeError): pass
    print('JSON-LD dated Event objects:',count,flush=True)
    host=urlparse(final).netloc.replace('www.','')
    links=[]
    for href in p.links:
        full=urljoin(final,href)
        if urlparse(full).netloc.replace('www.','')!=host: continue
        if not re.search(r'event|calendar|program|screen|film|performance|show|dance|festival',full,re.I): continue
        if full not in links: links.append(full)
    print('Relevant same-site links:',len(links),flush=True)
    for item in links[:10]: print(' LINK',item,flush=True)
    if not dates and not count: print('NOTE: No dated events verified from this landing page; needs deeper inspection.',flush=True)

if __name__=='__main__':
    print('Everything Art | READ-ONLY mixed-discipline source diagnostic',flush=True)
    for name,url in SOURCES.items(): inspect(name,url)
    print('\nDiagnostic finished. No event files changed.',flush=True)
