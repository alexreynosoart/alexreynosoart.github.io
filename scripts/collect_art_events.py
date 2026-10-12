#!/usr/bin/env python3
"""Everything Art scheduled multi-source event collector, stdlib only."""
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
def event_kind(title, description='', categories='', family_default=False):
    """Classify by event title first; description is only supporting evidence."""
    t=title.lower(); c=categories.lower()
    if re.search(r'\b(opening|opening reception|reception|vernissage)\b',t):return 'opening'
    if re.search(r'\b(film festival|festival|festivities|fiesta|fair|celebration|parade)\b',t):return 'festival workshop'
    if re.search(r'\b(concert|performance|performances|theatre|theater|dance recital|screening|film showing)\b',t):return 'performance workshop'
    if re.search(r'\b(talk|lecture|panel|conversation|discussion|artist\s? talk|reading)\b',t):return 'talk'
    if re.search(r'\b(tour|guided tour|gallery tour)\b',t):return 'tour exhibition'
    if re.search(r'\b(exhibition|exhibit|gallery|installation|open hours|museum exhibit)\b',t):return 'exhibition'
    if re.search(r'\b(family|families|kids|children|all ages|tots|youth)\b',t):return 'family workshop'
    if re.search(r'\b(workshop|artmaking|craft|crafts|drawing|painting|sketch|studio|class)\b',t):return 'workshop'
    if re.search(r'\b(family|children|kids)\b',c):return 'family workshop'
    if family_default and re.search(r'\b(family|kids|children|all ages)\b',description,re.I):return 'family workshop'
    return 'workshop'

def park_kind(t,d,c):return event_kind(t,d,c)
def whitney_kind(t,d):return event_kind(t,d,family_default=True)

def explicitly_free(title, description='', categories=''):
    """Only mark free when the text affirmatively describes free admission/activity."""
    s=' '.join((title,description,categories))
    if re.search(r'\b(not free|not a free|no free admission|free for members only|free with paid admission|free with museum admission)\b',s,re.I):return False
    return bool(re.search(r'\b(free admission|admission is free|free entry|free event|free workshop|free program|free artmaking|free to all|activities are free|free and open|free of charge|all activities are free|free fall festivities|program is free|\bFREE\b)\b',s,re.I))
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
        free=explicitly_free(t,d,c)
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
            free=explicitly_free(t,d)
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
                typ=event_kind(title,desc)
                if 'ExhibitionEvent' in kinds and typ=='workshop':typ='exhibition'
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

# NYPL uses visible exhibition detail pages, not JSON-LD.
# Keep this adapter separate from the other working source adapters.
class NYPLPage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.title = ''
        self.description = ''
        self.text = []
        self._capture_title = False
        self._hidden = 0
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('script', 'style', 'noscript'):
            self._hidden += 1
        if tag == 'title':
            self._capture_title = True
        if tag == 'a' and a.get('href'):
            self.links.append(a['href'])
        if tag == 'meta':
            if a.get('name', '').lower() == 'description' or a.get('property', '').lower() == 'og:description':
                self.description = self.description or clean(a.get('content'))
    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript'):
            self._hidden = max(0, self._hidden - 1)
        if tag == 'title':
            self._capture_title = False
    def handle_data(self, value):
        if self._capture_title:
            self.title += value
        elif not self._hidden:
            self.text.append(value)

NYPL_ROOT = 'https://www.nypl.org'
NYPL_INDEX = NYPL_ROOT + '/events/exhibitions/current'
NYPL_MONTHS = ('January February March April May June July August '
               'September October November December').split()
NYPL_END = re.compile(
    r'\bThrough\s+(' + '|'.join(NYPL_MONTHS) +
    r')\s+(\d{1,2}),?\s+(20\d{2})\b', re.I)

def nypl_html(page):
    req = urllib.request.Request(page, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; EverythingArtEventCollector/1.1; +https://alexreynosoart.com)',
        'Accept': 'text/html,application/xhtml+xml'})
    with urllib.request.urlopen(req, timeout=25) as response:
        raw = response.read(2_000_000).decode('utf-8', 'replace')
    parser = NYPLPage()
    parser.feed(raw)
    return parser

def nypl():
    index = nypl_html(NYPL_INDEX)
    links = set()
    for href in index.links:
        absolute = urljoin(NYPL_INDEX, href).split('#', 1)[0].split('?', 1)[0].rstrip('/')
        path = urlparse(absolute)
        if (path.scheme == 'https' and path.netloc == 'www.nypl.org'
                and path.path.startswith('/events/exhibitions/')
                and path.path.count('/') == 3
                and path.path.rsplit('/', 1)[-1] not in ('current', 'past', 'online', 'treasures')):
            links.add(absolute)
    if not links:
        raise ValueError('NYPL index yielded no exhibition detail links; preserving cache')
    results = []
    failures = 0
    for link in sorted(links)[:60]:
        try:
            page = nypl_html(link)
            title = clean(page.title.split(' | The New York Public Library')[0])
            visible = clean(' '.join(page.text))
            # The heading/date banner says "Through November 30, 2026".
            # Do not treat unrelated historical dates in the article as event dates.
            match = NYPL_END.search(visible[:5000])
            if not title or not match:
                continue
            month, day, year = match.groups()
            end = dt.date(int(year), NYPL_MONTHS.index(month.capitalize()) + 1, int(day))
            if end < TODAY:
                continue
            # The listing begins today if the actual opening date is unknown.
            # This is an availability/listing date, NOT a claimed exhibition opening.
            desc = page.description or 'Current exhibition at The New York Public Library.'
            desc = ('On view through ' + end.strftime('%B %d, %Y') + '. ' + desc)[:360]
            results.append(dict(
                title=title, description=desc, date=TODAY.isoformat(),
                endDate=end.isoformat(), venue='New York Public Library',
                location='New York, NY', type='exhibition',
                features='nyc us', country='United States',
                url=link, source='NYPL', free=False))
        except (OSError, ValueError) as exc:
            failures += 1
            print('NYPL detail error:', link, str(exc)[:150], file=sys.stderr)
    if failures == min(len(links), 60):
        raise ValueError('All NYPL detail requests failed; preserving cache')
    print(f'NYPL: inspected {min(len(links), 60)} exhibition links; {failures} detail errors')
    return results


# Bronx Museum: exhibition detail pages with explicit "On View" date ranges.
# Do not infer openings or turn reception dates into exhibition dates.
BRONX_INDEX = 'https://bronxmuseum.org/exhibitions/'
BRONX_MONTH = {m.lower(): i for i, m in enumerate(NYPL_MONTHS, 1)}
BRONX_DATE = re.compile(r'\b(' + '|'.join(NYPL_MONTHS) + r')\s+(\d{1,2})(?:,?\s+(20\d{2}))?\b', re.I)
BRONX_RANGE = re.compile(
    r'\bOn\s+View\s*:?\s*(' + '|'.join(NYPL_MONTHS) + r')\s+(\d{1,2})\s*'
    r'(?:,?\s+(20\d{2}))?\s*[–—-]\s*(' + '|'.join(NYPL_MONTHS) + r')\s+'
    r'(\d{1,2})\s*,?\s*(20\d{2})', re.I)

def bronx_museum():
    index = nypl_html(BRONX_INDEX)
    links = set()
    for href in index.links:
        target = urljoin(BRONX_INDEX, href).split('#', 1)[0].split('?', 1)[0].rstrip('/') + '/'
        parsed = urlparse(target)
        if parsed.scheme == 'https' and parsed.netloc == 'bronxmuseum.org' and re.fullmatch(r'/exhibition/[^/]+/', parsed.path):
            links.add(target)
    if not links:
        raise ValueError('Bronx Museum: no exhibition links; preserve cache')
    results = []
    failures = 0
    for link in sorted(links)[:50]:
        try:
            page = nypl_html(link)
            title = clean(page.title.split(' - The Bronx Museum')[0].split(' – The Bronx Museum')[0])
            visible = clean(' '.join(page.text))
            # Limit to an explicit exhibition On View label, not unrelated dates.
            match = BRONX_RANGE.search(visible[:9000])
            if not match or not title:
                print('Bronx Museum: skipping undated exhibition', link)
                continue
            sm, sd, sy, em, ed, ey = match.groups()
            end = dt.date(int(ey), BRONX_MONTH[em.lower()], int(ed))
            start_year = int(sy) if sy else int(ey)
            start = dt.date(start_year, BRONX_MONTH[sm.lower()], int(sd))
            if not sy and start > end:
                start = start.replace(year=start.year - 1)
            if end < TODAY or start > end:
                continue
            # Use today's date for already-open exhibitions, as a listing date.
            listing_date = max(start, TODAY)
            description = ('On view ' + start.strftime('%B %d, %Y') + ' through '
                           + end.strftime('%B %d, %Y') + '. ' + (page.description or ''))[:360]
            results.append(dict(title=title, description=description,
                date=listing_date.isoformat(), endDate=end.isoformat(),
                venue='The Bronx Museum', location='Bronx, NY',
                type='exhibition', features='nyc us', country='United States',
                url=link, source='Bronx Museum', free=False))
        except (OSError, ValueError) as exc:
            failures += 1
            print('Bronx Museum detail error:', link, str(exc)[:150], file=sys.stderr)
    if failures == min(len(links), 50):
        raise ValueError('All Bronx Museum detail requests failed; preserve cache')
    if not results:
        raise ValueError('No verified Bronx Museum exhibition dates; preserve cache')
    print(f'Bronx Museum: checked {min(len(links), 50)} detail pages, {len(results)} verified exhibitions')
    return results

# Film at Lincoln Center: one card per film, only verified future date headings.
# A date is accepted only when it appears in that film's own Showtimes section,
# has a weekday consistent with the calendar, and has at least one displayed time.
FILM_ROOT = 'https://www.filmlinc.org'
FILM_INDEX = FILM_ROOT + '/'
FILM_LINK = re.compile(r'^/films/[^/]+/$')
FILM_DAY = re.compile(r'^(Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s+([A-Z][a-z]{2})\s+(\d{1,2})$', re.I)
FILM_TIME = re.compile(r'^\d{1,2}:\d{2}\s*[AP]M$', re.I)

class FilmPage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.lines = []
        self.title = ''
        self.heading = ''
        self._in_title = False
        self._in_h1 = False
        self._skip = 0
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('script', 'style', 'noscript'):
            self._skip += 1
        if tag == 'title': self._in_title = True
        if tag == 'h1': self._in_h1 = True
        if tag == 'a' and a.get('href'): self.links.append(a['href'])
        if tag in ('h1', 'h2', 'h3', 'h4', 'p', 'div', 'section', 'li', 'br'):
            self.lines.append('\n')
    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript'):
            self._skip = max(0, self._skip - 1)
        if tag == 'title': self._in_title = False
        if tag == 'h1': self._in_h1 = False
        if tag in ('h1', 'h2', 'h3', 'h4', 'p', 'div', 'section', 'li'):
            self.lines.append('\n')
    def handle_data(self, value):
        if self._in_title: self.title += value
        if self._in_h1: self.heading += value
        if not self._skip and value.strip(): self.lines.append(value.strip() + ' ')

def film_html(page):
    req = urllib.request.Request(page, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; EverythingArtEventCollector/1.1; +https://alexreynosoart.com)',
        'Accept': 'text/html,application/xhtml+xml'})
    with urllib.request.urlopen(req, timeout=25) as response:
        raw = response.read(2_000_000).decode('utf-8', 'replace')
    parsed = FilmPage()
    parsed.feed(raw)
    return parsed

def film_dates(page):
    lines = [clean(line) for line in ''.join(page.lines).splitlines()]
    lines = [line for line in lines if line]
    try:
        start = next(i for i, line in enumerate(lines) if line.lower() == 'showtimes') + 1
    except StopIteration:
        return []
    section = []
    for line in lines[start:start + 250]:
        if line.lower() in ('more showtimes', 'director', 'year', 'country', 'runtime', 'read more'):
            break
        section.append(line)
    found = set()
    for i, line in enumerate(section):
        match = FILM_DAY.fullmatch(line)
        if not match: continue
        weekday, month, day = match.groups()
        # The official film pages list current-year screening dates.
        # Never infer a future year across December/January without evidence.
        try:
            d = dt.datetime.strptime(f'{month} {day} {TODAY.year}', '%b %d %Y').date()
        except ValueError:
            continue
        if d < TODAY or d.strftime('%a').lower() != weekday[:3].lower():
            continue
        next_heading = next((j for j in range(i+1, len(section)) if FILM_DAY.fullmatch(section[j])), len(section))
        if any(FILM_TIME.fullmatch(t) for t in section[i+1:next_heading]):
            found.add(d)
    return sorted(found)

def film_at_lincoln_center():
    index = film_html(FILM_INDEX)
    links = set()
    for href in index.links:
        target = urljoin(FILM_INDEX, href).split('#', 1)[0].split('?', 1)[0]
        parsed = urlparse(target)
        if parsed.scheme == 'https' and parsed.netloc == 'www.filmlinc.org' and FILM_LINK.fullmatch(parsed.path):
            links.add(target)
    if not links:
        raise ValueError('Film at Lincoln Center: no film detail links; preserving cache')
    results = []
    failures = 0
    for link in sorted(links)[:35]:
        try:
            page = film_html(link)
            title = clean(page.heading) or clean(page.title)
            dates = film_dates(page)
            if not title or not dates:
                continue
            start, end = dates[0], dates[-1]
            date_text = ', '.join(d.strftime('%b %d') for d in dates[:12])
            description = ('Upcoming screening dates: ' + date_text +
                           ('. See official film page for verified showtimes and tickets.'))[:360]
            results.append(dict(title=title, description=description,
                date=start.isoformat(), endDate=end.isoformat(),
                venue='Film at Lincoln Center', location='Manhattan, NY',
                type='film', features='nyc us', country='United States',
                url=link, source='Film at Lincoln Center', free=False))
        except (OSError, ValueError) as exc:
            failures += 1
            print('Film detail error:', link, str(exc)[:150], file=sys.stderr)
    if failures == min(len(links), 35) or not results:
        raise ValueError('Film at Lincoln Center: no verified future screenings; preserving cache')
    print(f'Film at Lincoln Center: checked {min(len(links), 35)} films, '
          f'{len(results)} with future screening dates; {failures} detail errors')
    return results


# New York Live Arts: inspect individual event pages, not the shared season menu.
NYLA_ROOT = 'https://newyorklivearts.org'
NYLA_INDEX = NYLA_ROOT + '/'
NYLA_MONTHS = {m.lower(): i for i, m in enumerate(NYPL_MONTHS, 1)}
NYLA_MONTH_PATTERN = '|'.join(NYPL_MONTHS)
NYLA_DATE_START = re.compile(r'\b(' + NYLA_MONTH_PATTERN + r')\s+(\d{1,2})(?:\s*[-–]\s*(\d{1,2}))?(?:\s*&\s*(\d{1,2})(?:\s*[-–]\s*(\d{1,2}))?)?(?:,?\s+(20\d{2}))?\b', re.I)
NYLA_MONTH_END = re.compile(r'\b(' + NYLA_MONTH_PATTERN + r')\s+(20\d{2})\b', re.I)

class NYLAPage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.text = []
        self.title = ''
        self.description = ''
        self._title = False
        self._skip = 0
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('script', 'style', 'noscript'): self._skip += 1
        if tag == 'title': self._title = True
        if tag == 'a' and a.get('href'): self.links.append(a['href'])
        if tag == 'meta' and a.get('name', '').lower() == 'description':
            self.description = self.description or clean(a.get('content'))
        if tag in ('div', 'section', 'p', 'h1', 'h2', 'h3', 'li', 'br'):
            self.text.append(' ')
    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript'): self._skip = max(0, self._skip - 1)
        if tag == 'title': self._title = False
        if tag in ('div', 'section', 'p', 'h1', 'h2', 'h3', 'li'): self.text.append(' ')
    def handle_data(self, value):
        if self._title: self.title += value
        if not self._skip and value.strip(): self.text.append(value + ' ')

def nyla_html(page):
    req = urllib.request.Request(page, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; EverythingArtEventCollector/1.1; +https://alexreynosoart.com)',
        'Accept': 'text/html,application/xhtml+xml'})
    with urllib.request.urlopen(req, timeout=25) as response:
        raw = response.read(1_500_000).decode('utf-8', 'replace')
    parsed = NYLAPage()
    parsed.feed(raw)
    return parsed

def nyla_detail_dates(visible, title):
    # The season navigation repeats dates for OTHER events. Ignore everything
    # before the unique detail-page breadcrumb, "Home ➔ Events ➔ <title>".
    breadcrumb = re.search(r'Home\s*[➔›>]\s*Events\s*[➔›>]', visible, re.I)
    if not breadcrumb:
        return None
    detail = visible[breadcrumb.end():breadcrumb.end() + 1100]
    # The first local date must appear close to the detail heading/venue.
    match = NYLA_DATE_START.search(detail[:340])
    if not match:
        return None
    month, first, range_end, and_start, and_end, explicit_year = match.groups()
    month_number = NYLA_MONTHS[month.lower()]
    year = int(explicit_year) if explicit_year else TODAY.year
    if not explicit_year and month_number < TODAY.month:
        year += 1
    day_numbers = [int(x) for x in (first, range_end, and_start, and_end) if x]
    try:
        start = dt.date(year, month_number, min(day_numbers))
        end = dt.date(year, month_number, max(day_numbers))
    except ValueError:
        return None
    # "On View: September 16, 2026 – January 2027" is an exhibition range.
    if re.search(r'\bOn View\s*:', detail[:340], re.I):
        end_match = NYLA_MONTH_END.search(detail[match.end():match.end()+80])
        if not end_match: return None
        end = dt.date(int(end_match.group(2)), NYLA_MONTHS[end_match.group(1).lower()], 1)
        # Month-only end dates are ambiguous: conservatively use first of month.
        kind = 'exhibition'
    else:
        kind = 'performance'
    if end < TODAY: return None
    return start, end, kind, detail

def new_york_live_arts():
    index = nyla_html(NYLA_INDEX)
    links = set()
    for href in index.links:
        target = urljoin(NYLA_INDEX, href).split('#', 1)[0].split('?', 1)[0]
        parsed = urlparse(target)
        if (parsed.scheme == 'https' and parsed.netloc in ('newyorklivearts.org', 'www.newyorklivearts.org')
                and re.fullmatch(r'/event/[^/]+/?', parsed.path)):
            links.add(target.rstrip('/') + '/')
    if not links:
        raise ValueError('New York Live Arts: no detail links; preserving cache')
    results = []
    failures = 0
    for link in sorted(links)[:45]:
        try:
            page = nyla_html(link)
            title = clean(re.split(r'\s+[-–]\s+New York Live Arts', page.title)[0])
            visible = clean(' '.join(page.text))
            extracted = nyla_detail_dates(visible, title)
            if not title or not extracted: continue
            start, end, kind, detail = extracted
            # Some productions tour: use the detail page's venue, not the site name.
            boston = bool(re.search(r'Institute of Contemporary Art\s*[|]\s*Boston|Boston,\s*MA', detail[:340], re.I))
            venue = 'Institute of Contemporary Art' if boston else 'New York Live Arts'
            location = 'Boston, MA' if boston else 'Manhattan, NY'
            features = 'us' if boston else 'nyc us'
            # The detail date is verified, but time/ticket information remains on official page.
            description = ('On view through ' if kind == 'exhibition' else 'Performance dates: ')
            description += (start.strftime('%b %d, %Y') + ' – ' + end.strftime('%b %d, %Y')
                            + '. Confirm exact showtimes and tickets with the organizer.')
            results.append(dict(title=title, description=description[:360],
                date=max(start, TODAY).isoformat() if kind == 'exhibition' else start.isoformat(),
                endDate=end.isoformat(), venue=venue, location=location, type=kind,
                features=features, country='United States', url=link,
                source='New York Live Arts', free=False))
        except (OSError, ValueError) as exc:
            failures += 1
            print('New York Live Arts detail error:', link, str(exc)[:150], file=sys.stderr)
    if failures == min(len(links), 45) or not results:
        raise ValueError('New York Live Arts: no verified upcoming performances; preserving cache')
    print(f'New York Live Arts: checked {min(len(links), 45)} pages, '
          f'{len(results)} dated listings; {failures} detail errors')
    return results


# Lincoln Center Presents: dry-run by default; live publication requires
# the explicit --publish-lincoln-center flag in the publishing workflow.
LC_CALENDAR = 'https://www.lincolncenter.org/series/lincoln-center-presents/v/calendar'
LC_PREFIX = '/series/lincoln-center-presents/'
LC_DATE = re.compile(
    r'\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+'
    r'(January|February|March|April|May|June|July|August|September|October|November|December)'
    r'\s+(\d{1,2})(?:\s+at\s+(\d{1,2}:\d{2}\s*[ap]m)|\s*-\s*(Multiple times))?', re.I)

class LCCalendar(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tokens = []
        self.links = []
        self.anchor = None
        self.hidden = 0
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('script', 'style', 'noscript'):
            self.hidden += 1
        if tag == 'a' and not self.hidden:
            self.anchor = {'href': attrs.get('href', ''), 'start': len(self.tokens), 'text': []}
    def handle_data(self, value):
        if not self.hidden:
            self.tokens.append(html.unescape(value))
            if self.anchor is not None:
                self.anchor['text'].append(html.unescape(value))
    def handle_endtag(self, tag):
        if tag == 'a' and self.anchor is not None:
            self.anchor['end'] = len(self.tokens)
            self.links.append(self.anchor)
            self.anchor = None
        if tag in ('script', 'style', 'noscript'):
            self.hidden = max(0, self.hidden - 1)

def lc_date(match):
    month = dt.datetime.strptime(match.group(2), '%B').month
    day = int(match.group(3))
    for year in (TODAY.year, TODAY.year + 1):
        try:
            value = dt.date(year, month, day)
        except ValueError:
            continue
        if (TODAY <= value <= TODAY + dt.timedelta(days=400)
                and value.strftime('%A').lower() == match.group(1).lower()):
            return value
    return None

# Read titles from calendar links first, not from URL slugs.
# A slug is only a fallback and is never treated as a verified official title.
LC_GENERIC_LINK = re.compile(r'^(learn more|read more|details|tickets|buy tickets|view event|image|more info|register|rsvp)$', re.I)
LC_CATEGORIES = (
    'Festival of Firsts', 'Legacies of San Juan Hill Festival',
    'Kids, Teens, and Families', 'Lincoln Center Immersive',
    'Lincoln Center Presents', 'Unsound New York',
)

def lc_slug_title(target):
    slug = urlparse(target).path.rstrip('/').rsplit('/', 1)[-1]
    slug = re.sub(r'-\d+$', '', slug)
    # Lincoln Center slugs contain literal entity names such as "andamp".
    slug = re.sub(r'-and(?:amp|rsquo|ndash|mdash|quot)-',
        lambda m: {'-andamp-':' & ', '-andrsquo-': '’', '-andndash-':' – ',
                   '-andmdash-':' — ', '-andquot-':' " '}.get(m.group(0), ' '), slug)
    return html.unescape(slug.replace('-', ' ')).strip().title()

def lc_title_candidate(value):
    value = clean(value)
    value = re.sub(r'\s+', ' ', value).strip(' |–-')
    if not value or len(value) > 180 or LC_GENERIC_LINK.fullmatch(value):
        return ''
    if value in LC_CATEGORIES or value.lower() in ('calendar', 'lincoln center', 'events'):
        return ''
    return value

def lc_calendar_title(anchor, context, target):
    # Some card anchors wrap the event title; other anchors wrap only an image.
    direct = lc_title_candidate(' '.join(anchor.get('text', [])))
    if direct and not re.search(r'\b(learn more|buy tickets|view details)\b', direct, re.I):
        return direct, 'calendar link'
    # The text immediately after a card's image link often contains
    # "Category Event Title Lincoln Center Presents ...".
    segment = re.split(r'\bLincoln Center Presents\b', context, maxsplit=1, flags=re.I)[0]
    for category in sorted(LC_CATEGORIES, key=len, reverse=True):
        segment = re.sub(r'^' + re.escape(category) + r'\s+', '', segment, flags=re.I)
    inferred = lc_title_candidate(segment)
    if inferred and len(inferred.split()) <= 22:
        return inferred, 'calendar card text'
    return lc_slug_title(target), 'slug fallback (needs review)'

def lincoln_center_preview():
    req = urllib.request.Request(LC_CALENDAR, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; EverythingArtEventCollector/1.1; +https://alexreynosoart.com)',
        'Accept': 'text/html,application/xhtml+xml'})
    with urllib.request.urlopen(req, timeout=40) as response:
        raw = response.read(6_000_000)
        print('Lincoln Center calendar HTTP:', response.status, '| bytes:', len(raw))
    page = LCCalendar()
    page.feed(raw.decode('utf-8', 'replace'))
    candidates = {}
    skipped = {'no_date': 0, 'weak_title': 0, 'date_too_far': 0}
    for anchor in page.links:
        target = urljoin(LC_CALENDAR, anchor['href']).split('#', 1)[0].split('?', 1)[0]
        parsed = urlparse(target)
        tail = parsed.path[len(LC_PREFIX):].strip('/') if parsed.path.startswith(LC_PREFIX) else ''
        if parsed.scheme != 'https' or parsed.netloc not in ('www.lincolncenter.org', 'lincolncenter.org') or not tail or '/' in tail:
            continue
        before = clean(' '.join(page.tokens[max(0, anchor['start'] - 90):anchor['start']]))
        matches = list(LC_DATE.finditer(before))
        if not matches:
            skipped['no_date'] += 1
            continue
        match = matches[-1]
        when = lc_date(match)
        if when is None or when > TODAY + dt.timedelta(days=365):
            skipped['date_too_far'] += 1
            continue
        time = clean(match.group(4) or match.group(5) or 'unspecified')
        # This is a candidate association, not an independently verified showtime.
        # Avoid duplicate image/title/learn-more links for the same calendar card.
        context = clean(' '.join(page.tokens[anchor['end']:anchor['end'] + 28]))[:250]
        proposed_title, title_source = lc_calendar_title(anchor, context, target)
        # Publication requires a title explicitly attached to a calendar link.
        # Reject guessed titles from adjacent card text or URL slugs.
        if title_source != 'calendar link' or not proposed_title:
            skipped['weak_title'] += 1
            continue
        candidate_key = (target, when.isoformat(), time)
        # Prefer a verified calendar-link title over a contextual guess.
        prior = candidates.get(candidate_key)
        rank = {'calendar link': 3, 'calendar card text': 2, 'slug fallback (needs review)': 1}
        if prior is None or rank[title_source] > rank[prior[2]]:
            candidates[candidate_key] = (context, proposed_title, title_source)
    # One card per production per day: existing site dedupe does not include time.
    by_day = {}
    for (target, day, time), (context, proposed_title, title_source) in candidates.items():
        item = by_day.setdefault((target, day), {'times': set(), 'context': context,
            'title': proposed_title, 'title_source': title_source})
        item['times'].add(time)
        rank = {'calendar link': 3, 'calendar card text': 2, 'slug fallback (needs review)': 1}
        if rank[title_source] > rank[item['title_source']]:
            item['title'], item['title_source'] = proposed_title, title_source
    results = []
    for (target, day), item in sorted(by_day.items(), key=lambda x: (x[0][1], x[0][0])):
        title = item['title']
        times = ', '.join(sorted(item['times']))
        description = ('Listed showtime(s): ' + times + '. ' if times != 'unspecified' else '') + 'Check the official Lincoln Center event page for current details and tickets.'
        # Only mark admission free when the official event page was reviewed.
        # Unknown admission stays unmarked; choose-what-you-pay is not free.
        slug = urlparse(target).path.rsplit('/', 1)[-1]
        confirmed_free = slug in {
            'plaza-374', 'lol-laughing-out-lonely-701',
        }
        if slug == 'plaza-374':
            kind, venue = 'installation', 'Josie Robertson Plaza, Lincoln Center'
            description = 'Interactive outdoor artwork by Andrew Schneider. Free admission; registration encouraged. ' + description
        elif slug == 'over-my-head-i-hear-freedom-in-the-air-604':
            kind, venue = 'performance', 'Lincoln Center Presents'
            description = 'Choose-What-You-Pay admission. ' + description
        else:
            kind, venue = 'performance', 'Lincoln Center Presents'
        results.append(dict(title=title, description=description,
            date=day, endDate=day, venue=venue,
            location='Manhattan, NY', type=kind,
            features='nyc us' + (' free' if confirmed_free else ''),
            country='United States', url=target, source='Lincoln Center Presents', free=confirmed_free))
    print('Lincoln Center skipped associations:', skipped)
    print('Lincoln Center candidate URL/date/time combinations:', len(candidates))
    print('Lincoln Center candidate URL/date cards after same-day grouping:', len(results))
    from collections import Counter
    print('Lincoln Center title extraction methods:', dict(Counter(x['title_source'] for x in by_day.values())))
    for item in results[:25]:
        print(' PREVIEW:', item['date'], '|', item['title'], '|', item['description'][:85], '|', item['url'])
    if not (10 <= len(results) <= 400):
        raise ValueError(f'Lincoln Center unexpected candidate count {len(results)}; review before publishing')
    print('Lincoln Center: calendar-derived dates; spot-check official event pages before enabling live publication.')
    return results


# Rule of Three: read-only discovery of official museum calendars.
# These candidates never enter the published event feed until independently verified.
def three_museum_preview():
    """Read-only investigation of official public feeds; never adds museum events."""
    from html.parser import HTMLParser
    from urllib.parse import urljoin, urlparse
    from urllib.error import HTTPError, URLError
    import xml.etree.ElementTree as ET

    class Reader(HTMLParser):
        def __init__(self):
            super().__init__(); self.links=[]; self.href=None; self.label=[]
        def handle_starttag(self, tag, attrs):
            if tag=='a':
                self.href=dict(attrs).get('href'); self.label=[]
        def handle_data(self, value):
            if self.href is not None: self.label.append(value)
        def handle_endtag(self, tag):
            if tag=='a' and self.href is not None:
                self.links.append((self.href, clean(' '.join(self.label))))
                self.href=None; self.label=[]

    # Official endpoints only. No third-party mirrors or attempts to evade blocks.
    targets={
      'The Met': [
        ('Exhibitions calendar','https://www.metmuseum.org/exhibitions?location=main','html'),
        ('Exhibitions RSS discovery','https://www.metmuseum.org/exhibitions/rss','xml'),
      ],
      'Brooklyn Museum': [
        ('Exhibitions calendar','https://www.brooklynmuseum.org/exhibitions','html'),
        ('Public WordPress events endpoint','https://www.brooklynmuseum.org/wp-json/wp/v2/events?per_page=10','json'),
      ],
      'Queens Museum': [
        ('Events-only calendar','https://queensmuseum.org/calendar/?filter=event&sort=date','html'),
        ('Exhibitions-only calendar','https://queensmuseum.org/calendar/?filter=exhibition&sort=date','html'),
        ('Public WordPress events endpoint','https://queensmuseum.org/wp-json/wp/v2/events?per_page=10','json'),
      ],
    }
    print('RULE OF THREE ROUND TWO: official feed discovery only; no museum events published')
    for name, probes in targets.items():
        print(f'{name}: investigating {len(probes)} official endpoints')
        for label, address, kind in probes:
            try:
                req=urllib.request.Request(address,headers={
                    'User-Agent':'EverythingArtEventCollector/1.0 (alexreynosoart.com)',
                    'Accept':'application/json, application/rss+xml, application/xml, text/html',
                })
                with urllib.request.urlopen(req,timeout=20) as resp:
                    final=resp.geturl();status=resp.status
                    content=resp.read(2_000_000)
                    ctype=resp.headers.get('Content-Type','')
                allowed=urlparse(address).hostname
                final_host=urlparse(final).hostname or ''
                if final_host != allowed and not final_host.endswith('.'+allowed):
                    raise ValueError('unexpected external redirect')
                raw=content.decode('utf-8','replace')
                if 'json' in ctype.lower() or kind=='json':
                    data=json.loads(raw)
                    items=data if isinstance(data,list) else data.get('events',data.get('items',[])) if isinstance(data,dict) else []
                    print(f'  {label}: HTTP {status}; JSON; {len(items) if isinstance(items,list) else 0} records')
                    for item in (items[:3] if isinstance(items,list) else []):
                        if isinstance(item,dict):
                            print('   SAMPLE:',clean(str(item.get('title',item.get('name',''))))[:90], '|',str(item.get('date',item.get('start_date','')))[:35])
                elif 'xml' in ctype.lower() or kind=='xml':
                    root=ET.fromstring(raw)
                    items=root.findall('.//item') or root.findall('.//{http://www.w3.org/2005/Atom}entry')
                    print(f'  {label}: HTTP {status}; XML; {len(items)} entries')
                    for item in items[:3]:print('   SAMPLE:',clean(item.findtext('title',''))[:100])
                else:
                    parser=Reader();parser.feed(raw)
                    seen=set();links=[]
                    for href,title in parser.links:
                        link=urljoin(final,href or '')
                        host=urlparse(link).hostname or ''
                        path=urlparse(link).path.lower()
                        if not title or len(title)>170 or link in seen:continue
                        if host != allowed and not host.endswith('.'+allowed):continue
                        if name=='The Met' and '/exhibitions/' not in path:continue
                        if name=='Brooklyn Museum' and not any(k in path for k in ('/exhibitions/','/events/','/calendar/')):continue
                        if name=='Queens Museum' and not any(k in path for k in ('/exhibition/','/event/','/events/','/calendar/')):continue
                        seen.add(link);links.append((title,link))
                    dates=re.findall(r'\b(?:0?[1-9]|1[0-2])[./-](?:[0-2]?[0-9]|3[01])[./-](?:20)?2[6-9]\b',raw)
                    print(f'  {label}: HTTP {status}; HTML; {len(links)} possible links; {len(dates)} date strings')
                    for title,link in links[:5]:print('   SAMPLE:',title[:85],'|',link)
            except HTTPError as exc:
                retry=exc.headers.get('Retry-After','') if exc.headers else ''
                print(f'  {label}: HTTP {exc.code}; not retrying'+(f'; Retry-After: {retry}' if retry else ''))
            except (URLError,ValueError,ET.ParseError,TimeoutError) as exc:
                print(f'  {label}: unavailable ({type(exc).__name__}: {str(exc)[:100]})')
            except Exception as exc:
                print(f'  {label}: unavailable ({type(exc).__name__}: {str(exc)[:100]})')
    print('RULE OF THREE ROUND TWO: discovery complete; 0 new museum events published')

def main():
    dry_run = '--dry-run' in sys.argv
    if '--three-museum-preview' in sys.argv:
        if not dry_run:
            print('Three-museum preview requires --dry-run; refusing to publish.',file=sys.stderr)
            return 2
        three_museum_preview()
        print('DRY RUN: no event file written, no existing data modified')
        return 0
    # Read-only isolated source preview. No other adapters run and no JSON is written.
    if '--lincoln-preview' in sys.argv:
        if not dry_run:
            print('Lincoln Center preview requires --dry-run; refusing to run.', file=sys.stderr)
            return 2
        try:
            lincoln_center_preview()
        except Exception as exc:
            print(f'Lincoln Center preview ERROR: {exc}', file=sys.stderr)
            return 1
        print('DRY RUN: no event file written, no existing data modified')
        return 0
    # Lincoln Center is enabled for regular publishing after three spot checks.
    # Emergency rollback: pass --no-lincoln-center to disable this adapter.
    include_lc = '--no-lincoln-center' not in sys.argv
    existing=load_existing();sources={'NYC Parks':parks,'Whitney':whitney,'MoMA':moma,'Guggenheim':guggenheim,'NYPL':nypl,'Bronx Museum':bronx_museum,'Film at Lincoln Center':film_at_lincoln_center,'New York Live Arts':new_york_live_arts};results={};failures=[]
    if include_lc:
        sources['Lincoln Center Presents'] = lincoln_center_preview
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
    # Abort publishing if the Lincoln Center feed fails or changes unexpectedly.
    if not dry_run and include_lc and 'Lincoln Center Presents' in failures:
        print('Lincoln Center fetch failed: aborting opt-in publication; cache unchanged.',file=sys.stderr)
        return 1
    if not dry_run and include_lc and not (10 <= len(results['Lincoln Center Presents']) <= 400):
        print('Lincoln Center count outside safety bounds; cache unchanged.',file=sys.stderr)
        return 1
    merged={}
    for name in sources:
        for e in results[name]:
            k=key(e)
            if k not in merged:merged[k]=e
    events=sorted(merged.values(),key=lambda e:(e['date'],e['title']))
    if dry_run:
        if include_lc:
            print(f'DRY RUN: {len(results.get("Lincoln Center Presents", []))} Lincoln Center candidate cards included in simulated total')
        else:
            try:
                lc_candidates = lincoln_center_preview()
                print(f'DRY RUN: {len(lc_candidates)} Lincoln Center candidate cards excluded from publication')
            except Exception as exc:
                print(f'DRY RUN: Lincoln Center preview ERROR: {exc}', file=sys.stderr)
        three_museum_preview()
        print(f'DRY RUN: {len(events)} unique events would be published; failures: {failures}')
        print('DRY RUN: no event file written, no existing data modified')
        return 0
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    payload={'updatedAt':dt.datetime.now(dt.timezone.utc).isoformat(),'sources':{k:len(v) for k,v in results.items()},'events':events}
    new=json.dumps(payload,ensure_ascii=False,indent=2)+'\n'
    # Keep the prior timestamp and avoid commits when the event data is unchanged.
    if OUTPUT.exists():
        try:
            old=json.loads(OUTPUT.read_text(encoding='utf-8'))
            if old.get('events')==events and old.get('sources')==payload['sources']:
                print('Event cache unchanged; no write needed.')
                return 0
        except (ValueError,OSError):pass
    OUTPUT.write_text(new,encoding='utf-8')
    print(f'Published {len(events)} unique events. Failed sources: {failures}')
    return 0
if __name__=='__main__':sys.exit(main())
