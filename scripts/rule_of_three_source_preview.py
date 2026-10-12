#!/usr/bin/env python3
"""Read-only preview of NYC and ONLINE art-event sources.
No event-cache writes. Python standard library only.
Usage: python scripts/rule_of_three_source_preview.py --online
       python scripts/rule_of_three_source_preview.py --nyc
       python scripts/rule_of_three_source_preview.py --all
"""
import argparse
import json
import re
from datetime import date, datetime
from html import unescape
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

NYC_SOURCES = [
    ('Wave Hill', 'https://www.wavehill.org/calendar'),
    ('Staten Island Museum', 'https://www.statenislandmuseum.org/events/list/'),
    ('Bronx Council on the Arts', 'https://www.bronxarts.org/events/'),
]
ONLINE_SOURCES = [
    ('Smithsonian Associates', 'https://smithsonianassociates.org/ticketing/online/'),
    ('National Gallery of Art (DC)', 'https://www.nga.gov/calendar'),
    ('National Gallery (London)', 'https://www.nationalgallery.org.uk/learning/courses'),
]
DATE = re.compile(r'\b20\d{2}-\d{2}-\d{2}\b|\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+\d{1,2}(?:,?\s+20\d{2})?\b', re.I)
BAD = re.compile(r'^(?:home|events?|calendar|learn more|read more|view all|more info|details|menu|skip to|next|previous|visit|about|discover|education|support|exhibitions?)$', re.I)
ONLINE_WORDS = re.compile(r'\b(?:online|virtual|webinar|livestream|live.stream|zoom|webcast|remote)\b', re.I)
MAX_BYTES = 4_000_000

class Node:
    def __init__(self, tag='', attrs=None, parent=None):
        self.tag, self.attrs, self.parent = tag, dict(attrs or []), parent
        self.children, self.bits = [], []
    def text(self):
        return ' '.join(' '.join(self.bits).split())

class Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node('root')
        self.stack = [self.root]
        self.jsonld = []
        self.in_ld = False
        self.ld_bits = []
    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.stack[-1])
        self.stack[-1].children.append(node)
        if tag == 'script' and 'ld+json' in node.attrs.get('type', '').lower():
            self.in_ld, self.ld_bits = True, []
        if tag not in ('meta', 'link', 'img', 'br', 'hr', 'input', 'source', 'area', 'embed', 'wbr'):
            self.stack.append(node)
    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if self.stack[-1].tag == tag:
            self.stack.pop()
    def handle_endtag(self, tag):
        if tag == 'script' and self.in_ld:
            self.jsonld.append(''.join(self.ld_bits))
            self.in_ld = False
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return
    def handle_data(self, data):
        if self.in_ld:
            self.ld_bits.append(data)
        if any(n.tag in ('script', 'style', 'noscript') for n in self.stack):
            return
        for n in self.stack:
            n.bits.append(data)

def walk(node):
    yield node
    for child in node.children:
        yield from walk(child)

def event_json(obj):
    if isinstance(obj, list):
        for item in obj:
            yield from event_json(item)
    elif isinstance(obj, dict):
        types = obj.get('@type', [])
        if isinstance(types, str):
            types = [types]
        if any(t.lower().endswith('event') for t in types if isinstance(t, str)):
            yield obj
        for value in obj.values():
            if isinstance(value, (dict, list)):
                yield from event_json(value)

def event_date(raw):
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace('Z', '+00:00')).date()
    except ValueError:
        pass
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None

def human_date(raw):
    parsed = event_date(raw)
    if parsed:
        return parsed
    for fmt in ('%b %d %Y', '%B %d %Y', '%b %d, %Y', '%B %d, %Y'):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            pass
    return None

def clean_title(label, name, link):
    label = unescape(label).replace('\xa0', ' ').strip()
    if name == 'Bronx Council on the Arts':
        slug = urlparse(link).path.rsplit('/', 1)[-1].removesuffix('.html')
        slug = re.sub(r'(?:-20\d{2}-\d{2}-\d{2})+$', '', slug)
        return slug.replace('-', ' ').strip().title(), 'URL-SLUG (unverified)'
    if name == 'Wave Hill':
        label = re.sub(r'\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+20\d{2}.*$', '', label, flags=re.I).strip()
        for prefix in ('Art Talks + Tours ', 'Families Family Art Project: ', 'Families Nature Talks + Tours ', 'Nature Talks + Tours Wellness + Cooking ', 'Gardens Talks + Tours ', 'Special Events ', 'Wellness + Cooking ', 'Talks + Tours '):
            if label.startswith(prefix):
                label = label[len(prefix):]
                break
    return label, 'VISIBLE-HTML'

def candidates(tree, base, name, online=False):
    host = urlparse(base).hostname
    today = date.today()
    results, seen = [], set()
    for script in tree.jsonld:
        try:
            objects = list(event_json(json.loads(script)))
        except (ValueError, TypeError):
            continue
        for item in objects:
            title, rawdate, link = item.get('name', ''), item.get('startDate', ''), item.get('url', '')
            if isinstance(link, dict):
                link = link.get('@id', '')
            if not all(isinstance(v, str) and v for v in (title, rawdate, link)):
                continue
            absolute = urljoin(base, link)
            start = human_date(rawdate)
            if urlparse(absolute).hostname != host or not start or start < today or absolute in seen:
                continue
            confidence = 'VERIFIED-STRUCTURE'
            if online:
                loc = item.get('location', '')
                signal = json.dumps(loc, ensure_ascii=False) + ' ' + str(item.get('eventAttendanceMode', '')) + ' ' + str(item.get('description', '')) + ' ' + title
                if not (ONLINE_WORDS.search(signal) or 'OnlineEventAttendanceMode' in signal):
                    continue
                confidence = 'ONLINE-SIGNAL / VERIFY ATTENDANCE'
            seen.add(absolute)
            results.append((unescape(title), start, absolute, 'JSON-LD', confidence))
    for n in walk(tree.root):
        if n.tag != 'a' or not n.attrs.get('href'):
            continue
        link = urljoin(base, n.attrs['href']).split('#')[0]
        path = urlparse(link).path.rstrip('/')
        if urlparse(link).hostname != host or link in seen:
            continue
        if name == 'Wave Hill' and not path.startswith('/calendar/'):
            continue
        if name == 'Staten Island Museum' and '/event/' not in path:
            continue
        if name == 'Bronx Council on the Arts' and not (path.startswith('/events/') and path.endswith('.html')):
            continue
        label = n.text()[:220].strip()
        if not label or BAD.match(label) or label.lower() == 'submit an event':
            continue
        context = n.parent
        best = None
        signal = ''
        for _ in range(5):
            if context is None:
                break
            times = [x.attrs['datetime'] for x in walk(context) if x.tag == 'time' and x.attrs.get('datetime')]
            dates = DATE.findall(context.text()[:2500])
            if times or dates:
                best = (times or dates)[0]
                signal = context.text()[:2500]
                break
            context = context.parent
        if not best:
            continue
        start = human_date(best)
        if not start or start < today:
            continue
        title, confidence = clean_title(label, name, link)
        if not title or DATE.fullmatch(title):
            continue
        if online:
            # Page-level words alone are not sufficient: require a signal near the link.
            if not ONLINE_WORDS.search(signal):
                continue
            confidence = 'NEARBY ONLINE WORD / UNVERIFIED'
        seen.add(link)
        results.append((title, start, link, 'HTML', confidence))
    return sorted(results, key=lambda row: (row[1], row[0]))

def inspect(name, url, online=False):
    print(f'\n=== {name} ===', flush=True)
    req = Request(url, headers={'User-Agent': 'EverythingArtEventCollector/1.0 (+public calendar preview)', 'Accept': 'text/html,application/xhtml+xml'})
    try:
        with urlopen(req, timeout=35) as response:
            final, status = response.url, response.status
            kind = response.headers.get('Content-Type', '')
            raw = response.read(MAX_BYTES+1)
    except HTTPError as e:
        print(f'HTTP {e.code}: unavailable; 0 records approved')
        return
    except (URLError, TimeoutError, OSError) as e:
        print(f'Fetch failed: {type(e).__name__}: {e}')
        return
    print(f'HTTP {status} | bytes {len(raw)} | {kind}')
    if urlparse(final).hostname != urlparse(url).hostname or len(raw) > MAX_BYTES or 'html' not in kind.lower():
        print('Safety guard: unexpected response; skipping')
        return
    tree = Tree()
    tree.feed(raw.decode('utf-8', 'replace'))
    found = candidates(tree, final, name, online=online)
    print(f'JSON-LD blocks: {len(tree.jsonld)} | event-level candidate links: {len(found)}')
    for title, start, link, origin, confidence in found[:15]:
        print(f'  [{origin} / {confidence}] title={title!r} | date={start.isoformat()} | url={link}')
    print(f'Preview count: {len(found)} future candidates; no publication approval implied')
    if online:
        print('ONLINE CAUTION: Nearby labels are clues, not verified attendance. Check each official event page.')
    print('PREVIEW ONLY. Candidate records require date/title/link review before publication.')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Read-only Rule of Three calendar investigation')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--online', action='store_true', help='Test three online art calendars')
    group.add_argument('--nyc', action='store_true', help='Test original three NYC calendars')
    group.add_argument('--all', action='store_true', help='Test all six calendars')
    args = parser.parse_args()
    print('RULE OF THREE: CLEAN FUTURE-EVENT CANDIDATES, READ-ONLY')
    sources = (NYC_SOURCES + ONLINE_SOURCES) if args.all else (ONLINE_SOURCES if args.online else NYC_SOURCES)
    for name, url in sources:
        inspect(name, url, online=(name in {n for n, _ in ONLINE_SOURCES}))
    print('\nNo event cache read or written; production collector unchanged.')
