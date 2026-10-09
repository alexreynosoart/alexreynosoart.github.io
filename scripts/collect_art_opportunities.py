#!/usr/bin/env python3
"""Everything Art opportunities collector. Standard-library only.

Reads existing data/art-opportunities.json, checks configured RSS/Atom feeds,
retains current opportunities, and expires dated entries. Never fabricates
application deadlines or assumes that an undated article is an open call.
"""
import datetime as dt
import email.utils
import html
import json
import os
from pathlib import Path
import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'art-opportunities.json'
SOURCES = ROOT / 'data' / 'opportunity-feeds.json'
TODAY = dt.datetime.now(dt.timezone.utc).date()
KEYWORDS = re.compile(r'\b(open call|call for (artists|entries|applications|proposals)|apply now|applications? open|artist residency|artist fellowship|art grant|funding opportunity|artist award|submission deadline|competition)\b', re.I)
TYPES = [('residency',r'\bresiden'),('fellowship',r'\bfellowship'),('grant',r'\bgrant|\bfunding'),('open-call',r'open call|call for'),('competition',r'award|prize|competition'),('exhibition',r'exhibition')]
DISCIPLINES = [('photo',r'photograph'),('film',r'film|cinema'),('music',r'music|compos'),('dance',r'dance|choreograph'),('writing',r'writer|poetry|literary'),('design',r'design'),('digital',r'digital|media art')]
DATE = re.compile(r'\b(?:deadline|apply by|applications? (?:close|due)|closing date)\s*[:\-]?\s*((?:20\d\d[-/]\d\d[-/]\d\d)|(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+20\d\d))',re.I)

def text(node):
    if node is None: return ''
    return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]+>',' ',''.join(node.itertext())))).strip()

def child(node,names):
    for el in node:
        if el.tag.rsplit('}',1)[-1].lower() in names:return el
    return None

def deadline_from(body):
    match=DATE.search(body)
    if not match:return ''
    value=match.group(1).replace('/','-').replace(',','')
    try:
        if re.match(r'^20\d\d-',value):return dt.date.fromisoformat(value).isoformat()
        return dt.datetime.strptime(value,'%B %d %Y').date().isoformat()
    except ValueError:
        try:return dt.datetime.strptime(value,'%b %d %Y').date().isoformat()
        except ValueError:return ''

def key(item):return (item.get('title','').strip().lower(),item.get('url','').split('?')[0].rstrip('/'))

def load_json(path,default):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):return default

def collect_feed(source):
    url=source.get('url','')
    if not url.startswith('https://'):return []
    req=urllib.request.Request(url,headers={'User-Agent':'EverythingArtOpportunityCollector/1.0 (+https://alexreynosoart.com)','Accept':'application/rss+xml, application/atom+xml, application/xml, text/xml'})
    with urllib.request.urlopen(req,timeout=18) as response:
        body=response.read(2_000_000)
    root=ET.fromstring(body)
    entries=[e for e in root.iter() if e.tag.rsplit('}',1)[-1].lower() in ('item','entry')]
    found=[]
    for entry in entries[:100]:
        title=text(child(entry,{'title'}))
        desc=text(child(entry,{'description','summary','content','encoded'}))
        linknode=child(entry,{'link'})
        link=(linknode.get('href','') if linknode is not None else '') or text(linknode)
        if not link.startswith('https://') and not link.startswith('http://'):continue
        if not title or not KEYWORDS.search(title+' '+desc):continue
        deadline=deadline_from(title+' '+desc)
        # Without a clear deadline, RSS news cannot be assumed to be a live application.
        if not deadline or deadline<TODAY:continue
        combined=title+' '+desc
        types=[t for t,pattern in TYPES if re.search(pattern,combined,re.I)]
        disciplines=[d for d,pattern in DISCIPLINES if re.search(pattern,combined,re.I)]
        found.append({'title':title[:180],'organization':source.get('name',''),'description':desc[:550],'url':link,'deadline':deadline,'discipline':' '.join(disciplines or ['interdisciplinary']),'type':' '.join(types or ['open-call']),'features':'','country':'','source':source.get('name','RSS source'),'status':'Automatically discovered; confirm with organizer'})
    return found

def main():
    old=load_json(OUT,{'opportunities':[]})
    items={}
    for entry in old.get('opportunities',[]):
        if not isinstance(entry,dict):continue
        deadline=entry.get('deadline','')
        if deadline:
            try:
                if dt.date.fromisoformat(deadline)<TODAY:continue
            except ValueError:continue
        if entry.get('title') and entry.get('url'):items[key(entry)]=entry
    config=load_json(SOURCES,{'feeds':[]})
    for source in config.get('feeds',[]):
        try:
            found=collect_feed(source)
            for entry in found:items[key(entry)]=entry
            print(f"{source.get('name','Feed')}: {len(found)} qualified opportunities")
        except Exception as exc:
            print(f"{source.get('name','Feed')}: unavailable ({exc})")
    records=sorted(items.values(),key=lambda x:(x.get('deadline') or '9999-12-31',x.get('title','').lower()))
    counts={}
    for record in records:counts[record.get('source','Unknown')]=counts.get(record.get('source','Unknown'),0)+1
    OUT.parent.mkdir(parents=True,exist_ok=True)
    # Avoid committing changes every six hours when no listings change.
    prior=old.get('opportunities',[])
    if prior==records:
        print(f'No changes: {len(records)} opportunities');return
    payload={'updatedAt':dt.datetime.now(dt.timezone.utc).isoformat(),'sources':counts,'opportunities':records}
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Saved {len(records)} opportunities')

if __name__=='__main__':main()
