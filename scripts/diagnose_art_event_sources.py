#!/usr/bin/env python3
"""READ ONLY Film at Lincoln Center screening extraction diagnostic. Stdlib only."""
import re, html, json, urllib.request
from html.parser import HTMLParser
from datetime import datetime, date
from zoneinfo import ZoneInfo

URLS = [
 'https://www.filmlinc.org/films/once-upon-a-time-in-harlem/',
 'https://www.filmlinc.org/films/fatherland/',
 'https://www.filmlinc.org/films/the-devils/',
]
class Reader(HTMLParser):
 def __init__(self):
  super().__init__(); self.parts=[]; self.skip=0; self.title=''; self.in_title=False
 def handle_starttag(self, tag, attrs):
  if tag in ('script','style','noscript'): self.skip+=1
  if tag=='title': self.in_title=True
  if tag in ('h1','h2','h3','h4','p','div','section','li','br'): self.parts.append('\n')
 def handle_endtag(self,tag):
  if tag in ('script','style','noscript'): self.skip=max(0,self.skip-1)
  if tag=='title': self.in_title=False
  if tag in ('h1','h2','h3','h4','p','div','section','li'): self.parts.append('\n')
 def handle_data(self,data):
  if self.in_title: self.title+=data
  if not self.skip and data.strip(): self.parts.append(data.strip()+' ')

def main():
 today=datetime.now(ZoneInfo('America/New_York')).date()
 print('Everything Art | READ-ONLY film screening extraction test')
 print('Today in NYC:',today,'| No files written')
 for url in URLS:
  print('\n'+'='*70+'\n',url)
  try:
   req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; EverythingArtDiagnostic/1.0)'})
   with urllib.request.urlopen(req,timeout=25) as r: raw=r.read(2000000).decode('utf-8','replace'); status=r.status
   p=Reader();p.feed(raw)
   lines=[re.sub(r'\s+',' ',s).strip() for s in ''.join(p.parts).splitlines()]
   lines=[s for s in lines if s]
   heading=re.search(r'<h1[^>]*>(.*?)</h1>',raw,re.I|re.S)
   name=re.sub('<[^>]+>','',heading.group(1)).strip() if heading else p.title.strip()
   print('HTTP:',status,'| Film:',html.unescape(name),'| HTML bytes:',len(raw))
   # Restrict to the first Showtimes section, stopping at More Showtimes or film metadata.
   text='\n'.join(lines)
   match=re.search(r'(?m)^Showtimes\s*$',text,re.I)
   if not match:
    print('NO VERIFIED SHOWTIMES SECTION. No events extracted.');continue
   after=text[match.end():]
   stop=re.search(r'(?m)^(?:More Showtimes|DIRECTOR|YEAR|COUNTRY|RUNTIME|Read More)\s*$',after,re.I)
   section=after[:stop.start()] if stop else after[:12000]
   blocks=re.split(r'(?m)^(?=(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s+[A-Z][a-z]{2}\s+\d{1,2}\s*$)',section)
   screenings=[]; dates=[]
   for block in blocks:
    m=re.match(r'\s*(Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s+([A-Z][a-z]{2})\s+(\d{1,2})\s*$',block.splitlines()[0]) if block.strip() else None
    if not m: continue
    try:
     d=datetime.strptime(f'{m.group(2)} {m.group(3)} {today.year}','%b %d %Y').date()
     if d<today and (today-d).days>180: d=d.replace(year=today.year+1)
    except ValueError:continue
    times=re.findall(r'(?m)^\s*(\d{1,2}:\d{2}\s*[AP]M)\s*$',block,re.I)
    unique=list(dict.fromkeys(times))
    if d>=today and unique:
     dates.append(d.isoformat());screenings.append((d.isoformat(),unique))
   print('Future dates from Showtimes section:',len(screenings),'| Film cards:',1 if screenings else 0)
   for d,times in screenings[:8]: print(' ',d,'|',', '.join(times[:12]))
   qa=re.search(r'(?i)Screening\s*\+\s*Q\s*&\s*A',text)
   print('Q&A mentioned:',bool(qa),'(not assigned to a screening without separate validation)')
   print('CAUTION: text-only parsing; compare extracted times against official page before production.')
  except Exception as e: print('FETCH ERROR:',type(e).__name__,str(e)[:250])
 print('\nDiagnostic finished. No event files changed.')
if __name__=='__main__': main()
