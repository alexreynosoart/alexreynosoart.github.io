#!/usr/bin/env python3
"""Read-only diagnostic for 3 prospective Everything Art Events sources.
Does not touch data/art-events.json or other site files.
Run in GitHub Actions: python scripts/diagnose_new_art_event_sources.py
"""
import re
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

SOURCES = {
    'Queens Museum': 'https://queensmuseum.org/calendar/',
    'Bronx Museum': 'https://bronxmuseum.org/exhibitions/',
    'Creative Time': 'https://creativetime.org/projects/',
}
DATE_PATTERNS = [
    r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+20\d{2}\b',
    r'\b\d{1,2}\.\d{1,2}\.\d{2,4}\b',
    r'\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}\b',
]
class Page(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.links=[]; self.skip=0; self.anchor=None
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if tag in ('script','style','noscript'): self.skip+=1
        if tag=='a': self.anchor={'href':a.get('href',''),'text':''}
    def handle_data(self, data):
        if not self.skip:
            t=' '.join(data.split())
            if t:
                self.parts.append(t)
                if self.anchor is not None: self.anchor['text']+=' '+t
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript'): self.skip=max(0,self.skip-1)
        if tag=='a' and self.anchor is not None:
            self.links.append(self.anchor); self.anchor=None

def main():
    for name,url in SOURCES.items():
        print('\n=== '+name+' ===',flush=True)
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; EverythingArtDiagnostic/1.0)','Accept':'text/html'})
            with urllib.request.urlopen(req,timeout=20) as resp:
                html=resp.read(2000000).decode('utf-8','replace')
                print('HTTP:',resp.status,'bytes:',len(html),flush=True)
            p=Page();p.feed(html)
            print('Visible text samples containing dates:',flush=True)
            snippets=[]
            for i,part in enumerate(p.parts):
                if any(re.search(pattern,part,re.I) for pattern in DATE_PATTERNS):
                    snippets.append(' '.join(p.parts[max(0,i-4):min(len(p.parts),i+3)]))
            for s in snippets[:12]: print('  -',s[:240],flush=True)
            print('Date-bearing snippets:',len(snippets),flush=True)
            print('Candidate internal links:',flush=True)
            seen=set(); count=0
            for link in p.links:
                target=urljoin(url,link['href']); parsed=urlparse(target)
                if parsed.netloc!=urlparse(url).netloc or target in seen: continue
                seen.add(target)
                if any(x in parsed.path.lower() for x in ('event','exhibit','calendar','project')) and parsed.path.rstrip('/')!=urlparse(url).path.rstrip('/'):
                    print('  -',link['text'].strip()[:90],target,flush=True)
                    count+=1
                    if count>=12: break
            print('JSON-LD blocks:',len(re.findall(r'<script[^>]+application/ld\+json',html,re.I)),flush=True)
        except Exception as e:
            print('ERROR:',type(e).__name__,str(e)[:300],flush=True)
    print('\nREAD-ONLY diagnostic complete. No site files changed.',flush=True)
if __name__=='__main__': main()
