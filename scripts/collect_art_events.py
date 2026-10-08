#!/usr/bin/env python3
"""Everything Art scheduled collector: NYC Parks + Whitney, stdlib only."""
import datetime as dt, html, json, re, urllib.request, pathlib, sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'data'/'art-events.json'
TODAY=dt.date.today()
ART_TITLE=re.compile(r'\b(art|arts|artist|artmaking|painting|paint|drawing|draw|sketch|sculpture|sculpting|ceramic|ceramics|pottery|photography|photo walk|printmaking|mural|craft|crafts|collage|watercolor|illustration|gallery|exhibition|exhibit|weaving|textile|origami|puppet|puppetry|creative writing|film screening|film festival|museum)\b',re.I)
ART_DESC=re.compile(r'\b(painting|drawing|sketching|sculpture|sculpting|ceramics|pottery|photography|printmaking|mural|collage|watercolor|illustration|artmaking|arts and crafts|art workshop|art class|artist talk|gallery tour|exhibition|exhibit|weaving|textile art|origami|puppet making|film screening|art installation|public art|art exhibit|face.painting|pumpkin decorating)\b',re.I)
RECREATION=re.compile(r'\b(kids in motion|fitness|yoga|zumba|pilates|boot camp|workout|exercise|basketball|soccer|football|baseball|tennis|pickleball|swimming|swim lessons|sports|playground|nature walk|birdwatching|bird watching|community board meeting|volunteer cleanup|clean.up)\b',re.I)
FALSE_ART=re.compile(r'\b(martial arts|artificial|heart|culinary arts)\b',re.I)
def clean(v):
    return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]*>',' ',str(v or '')))).strip()
def date(v):
    s=str(v or '')[:10]
    try: return dt.date.fromisoformat(s)
    except ValueError: return None
def url(v):
    if isinstance(v,dict): v=v.get('url','')
    return v if isinstance(v,str) and v.startswith(('https://','http://')) else ''
def fetch(u):
    req=urllib.request.Request(u,headers={'Accept':'application/json','User-Agent':'EverythingArtEventCollector/1.0 (alexreynosoart.com)'})
    with urllib.request.urlopen(req,timeout=25) as response: return json.load(response)
def art_event(t,d):
    t=FALSE_ART.sub('',t);d=FALSE_ART.sub('',d)
    return not (RECREATION.search(t) and not ART_TITLE.search(t)) and bool(ART_TITLE.search(t) or ART_DESC.search(d))
def park_kind(t,d,c):
    s=FALSE_ART.sub('',t+' '+d+' '+c)
    for pat,kind in [(r'\b(exhibition|exhibit|gallery|sculpture display)\b','exhibition'),(r'\b(opening|reception)\b','opening'),(r'\b(talk|lecture|discussion)\b','talk'),(r'\b(kids|children|family|families)\b','family workshop')]:
        if re.search(pat,s,re.I):return kind
    return 'workshop'
def whitney_kind(t,d):
    s=(t+' '+d).lower();tl=t.lower()
    if re.search(r'opening|reception',tl):return 'opening'
    if re.search(r'workshop|artmaking|drawing|painting|craft|family|families|kids|children|teens',s):return 'family workshop'
    if re.search(r'lecture|talk|conversation|discussion|reading|panel',tl):return 'talk'
    if 'exhibition' in tl:return 'exhibition'
    if re.search(r'tour|gallery|artist|art|museum|biennial|film|performance',s):return 'exhibition'
    return ''
def canonical(v):return re.sub(r'[^a-z0-9]+',' ',v.lower()).strip()
def key(e):
    # Include venue and date to avoid collapsing different performances/days.
    return (canonical(e['title']),e['date'],canonical(e['venue']))
def load_existing():
    if not OUTPUT.exists():return []
    try:return json.loads(OUTPUT.read_text()).get('events',[])
    except (ValueError,OSError):return []
def parks():
    records=fetch('https://data.cityofnewyork.us/resource/w3wp-dpdi.json?$limit=2000')
    if not isinstance(records,list):raise ValueError('Unexpected NYC Parks payload')
    seen=set();result=[]
    for item in records:
        t=clean(item.get('title'));d=clean(item.get('description'));c=clean(item.get('categories'))
        if not t or not art_event(t,d):continue
        start=date(item.get('starttime'));end=date(item.get('endtime')) or start
        link=url(item.get('link'))
        if not start or end<TODAY or not link:continue
        venue=clean(item.get('parknames')) or 'NYC Parks';location=clean(item.get('location'))
        # Preserve previous feed's collapsing of recurring park programs.
        repeat=(canonical(t),canonical(venue),canonical(location))
        if repeat in seen:continue
        seen.add(repeat)
        free=bool(re.search(r'\bfree\b',t+' '+d+' '+c,re.I))
        result.append(dict(title=t,description=d[:360],date=start.isoformat(),endDate=end.isoformat(),venue=venue,location=location,type=park_kind(t,d,c),features='nyc us'+(' free' if free else ''),country='United States',url=link,source='NYC Parks',free=free))
    return result
def whitney():
    result=[];visited=set();next_url='https://whitney.org/api/events'
    for _ in range(4):
        if not next_url or next_url in visited:break
        visited.add(next_url);payload=fetch(next_url)
        if not isinstance(payload.get('data'),list):raise ValueError('Unexpected Whitney payload')
        for item in payload['data']:
            a=item.get('attributes') or {};t=clean(a.get('title'));d=clean(a.get('description'))
            start=date(a.get('start_time'));end=date(a.get('end_time')) or start
            if not t or not start or end<TODAY:continue
            kind=whitney_kind(t,d)
            if not kind:continue
            link=a.get('url') or ''
            if isinstance(link,str) and link.startswith('/'):link='https://whitney.org'+link
            link=url(link)
            if not link.startswith('https://whitney.org/'):continue
            free=bool(re.search(r'\bfree\b',t+' '+d,re.I))
            result.append(dict(title=t,description=d[:360],date=start.isoformat(),endDate=end.isoformat(),venue='Whitney Museum of American Art',location='Manhattan, NY',type=kind,features='nyc us'+(' free' if free else ''),country='United States',url=link,source='Whitney',free=free))
        nxt=(payload.get('links') or {}).get('next')
        if isinstance(nxt,str) and nxt.startswith('/'):nxt='https://whitney.org'+nxt
        next_url=nxt if isinstance(nxt,str) and nxt.startswith('https://whitney.org/') else None
    return result

# Additional public-calendar adapters. Only publish dated, linked Event/Exhibition
# structured data; never invent dates from collection objects or page headings.
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

class StructuredDataParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_json=False
        self.blocks=[]
        self.buffer=[]
    def handle_starttag(self, tag, attrs):
        if tag=='script' and dict(attrs).get('type','').lower()=='application/ld+json':
            self.in_json=True
            self.buffer=[]
    def handle_data(self, data):
        if self.in_json:self.buffer.append(data)
    def handle_endtag(self, tag):
        if tag=='script' and self.in_json:
            self.blocks.append(''.join(self.buffer))
            self.in_json=False

def structured_events(name, page, venue, location, country, features):
    request=urllib.request.Request(page,headers={
        'User-Agent':'Mozilla/5.0 (compatible; EverythingArtEventCollector/1.1; +https://alexreynosoart.com)',
        'Accept':'text/html'})
    with urllib.request.urlopen(request,timeout=25) as response:
        raw=response.read(3_000_000).decode('utf-8','replace')
    parser=StructuredDataParser()
    parser.feed(raw)
    result=[]
    def visit(node):
        if isinstance(node,list):
            for value in node:visit(value)
            return
        if not isinstance(node,dict):return
        kinds=node.get('@type',[])
        if isinstance(kinds,str):kinds=[kinds]
        accepted={'Event','ExhibitionEvent','VisualArtsEvent','EducationEvent','Festival','ChildrensEvent'}
        if any(str(k).split('/')[-1] in accepted for k in kinds):
            title=clean(node.get('name'))
            start=date(node.get('startDate'))
            end=date(node.get('endDate')) or start
            link=node.get('url') or node.get('@id') or ''
            if isinstance(link,dict):link=link.get('@id','')
            link=urljoin(page,link) if isinstance(link,str) else ''
            if title and start and end>=TODAY and url(link) and urlparse(link).netloc==urlparse(page).netloc:
                desc=clean(node.get('description'))
                typ='exhibition' if ('ExhibitionEvent' in kinds or re.search(r'exhibit|gallery',title,re.I)) else 'workshop'
                if re.search(r'\b(talk|lecture|conversation)\b',title,re.I):typ='talk'
                if re.search(r'\b(opening|reception)\b',title,re.I):typ='opening'
                free=node.get('isAccessibleForFree') is True
                result.append(dict(title=title,description=desc[:360],date=start.isoformat(),
                    endDate=end.isoformat(),venue=venue,location=location,type=typ,
                    features=features+(' free' if free else ''),country=country,
                    url=link,source=name,free=free))
        for k in ('@graph','itemListElement','event','subEvent','mainEntity'):
            if k in node:visit(node[k])
    for block in parser.blocks:
        try:visit(json.loads(block))
        except ValueError:continue
    return list({key(e):e for e in result}.values())

def moma():
    return structured_events('MoMA','https://www.moma.org/calendar/exhibitions',
        'Museum of Modern Art','Manhattan, NY','United States','nyc us')

def guggenheim():
    return structured_events('Guggenheim','https://www.guggenheim.org/',
        'Solomon R. Guggenheim Museum','Manhattan, NY','United States','nyc us')

def nypl():
    return structured_events('NYPL','https://www.nypl.org/events',
        'New York Public Library','New York, NY','United States','nyc us')

def main():
    existing=load_existing();sources={'NYC Parks':parks,'Whitney':whitney,'MoMA':moma,'Guggenheim':guggenheim,'NYPL':nypl};results={};failures=[]
    for name,fn in sources.items():
        try:
            results[name]=fn();print(f'{name}: {len(results[name])} events')
            if not results[name] and name in ('MoMA','Guggenheim','NYPL'):
                print(f'{name}: no verified dated structured events found; skipping safely')
        except Exception as exc:
            failures.append(name);print(f'{name}: ERROR {exc}',file=sys.stderr)
            results[name]=[e for e in existing if e.get('source')==name and (date(e.get('endDate')) or date(e.get('date')) or TODAY)>=TODAY]
            print(f'{name}: retaining {len(results[name])} previously cached events')
    # Avoid overwriting a previously good cache if every upstream source fails.
    if len(failures)==len(sources):
        print('All sources failed; leaving cache unchanged.',file=sys.stderr)
        return 1
    merged={}
    for name in sources:
        for e in results[name]:
            k=key(e)
            if k not in merged:merged[k]=e
    events=sorted(merged.values(),key=lambda e:(e['date'],e['title']))
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    payload={'updatedAt':dt.datetime.now(dt.timezone.utc).isoformat(),'sources':{k:len(v) for k,v in results.items()},'events':events}
    new=json.dumps(payload,ensure_ascii=False,indent=2)+'\n'
    OUTPUT.write_text(new,encoding='utf-8')
    print(f'Published {len(events)} unique events. Failed sources: {failures}')
    return 0
if __name__=='__main__':sys.exit(main())
