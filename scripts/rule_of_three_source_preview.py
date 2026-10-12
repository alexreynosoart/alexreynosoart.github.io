#!/usr/bin/env python3
"""Read-only event-level investigation of three NYC arts calendars.
No event-cache writes. Python standard library only.
"""
import json
import re
from datetime import date, datetime
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

SOURCES = [
    ('Wave Hill', 'https://www.wavehill.org/calendar'),
    ('Staten Island Museum', 'https://www.statenislandmuseum.org/events/list/'),
    ('Bronx Council on the Arts', 'https://www.bronxarts.org/events/'),
]
DATE = re.compile(r'\b20\d{2}-\d{2}-\d{2}\b|\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+\d{1,2}(?:,?\s+20\d{2})?\b', re.I)
BLOCK = re.compile(r'event|calendar|listing|program|exhibition|tribe|card|schedule', re.I)
BAD = re.compile(r'^(?:home|events?|calendar|learn more|read more|view all|more info|details|menu|skip to|next|previous|visit|about|discover|education|support|exhibitions?)$', re.I)
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

def candidates(tree, base, name):
    host = urlparse(base).hostname
    results = []
    seen = set()
    for script in tree.jsonld:
        try:
            objects = list(event_json(json.loads(script)))
        except (ValueError, TypeError):
            continue
        for item in objects:
            title, rawdate, link = item.get('name', ''), item.get('startDate', ''), item.get('url', '')
            if isinstance(link, dict):
                link = link.get('@id', '')
            if isinstance(title, str) and isinstance(link, str) and title and rawdate and link:
                absolute = urljoin(base, link)
                if urlparse(absolute).hostname == host and absolute not in seen:
                    seen.add(absolute)
                    results.append(('JSON-LD', title[:110], str(rawdate)[:35], absolute))
    for n in walk(tree.root):
        if n.tag != 'a' or not n.attrs.get('href'):
            continue
        link = urljoin(base, n.attrs['href']).split('#')[0]
        path = urlparse(link).path.rstrip('/')
        if urlparse(link).hostname != host or link in seen:
            continue
        if path in ('', '/calendar', '/events', '/events/list'):
            continue
        label = n.text()[:140]
        if not label or BAD.match(label.strip()):
            continue
        if name == 'Wave Hill' and not path.startswith('/calendar/'):
            continue
        if name == 'Staten Island Museum' and '/event/' not in path:
            continue
        if name == 'Bronx Council on the Arts' and not (re.search(r'event|calendar|exhibit|workshop|program', path, re.I) or BLOCK.search(' '.join(str(x.attrs.get('class','')) for x in (n.parent, n.parent.parent if n.parent else None) if x))):
            continue
        context = n.parent
        best = None
        for _ in range(5):
            if not context:
                break
            text = context.text()[:2500]
            dates = DATE.findall(text)
            times = [x.attrs['datetime'] for x in walk(context) if x.tag == 'time' and x.attrs.get('datetime')]
            if dates or times:
                best = (dates[:3], times[:3], text[:180])
                break
            context = context.parent
        if not best:
            continue
        seen.add(link)
        rawdate = (best[1] or best[0])[0]
        results.append(('HTML', label, rawdate, link))
    return results

def inspect(name, url):
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
    found = candidates(tree, final, name)
    print(f'JSON-LD blocks: {len(tree.jsonld)} | event-level candidate links: {len(found)}')
    for origin, title, rawdate, link in found[:12]:
        parsed = event_date(rawdate)
        print(f'  [{origin}] title={title!r} | date={rawdate!r} | ISO-date={parsed} | url={link}')
    print('PREVIEW ONLY. Candidate records require date/title/link review before publication.')

if __name__ == '__main__':
    print('RULE OF THREE: EVENT-LEVEL VALIDATION, READ-ONLY')
    for name, url in SOURCES:
        inspect(name, url)
    print('\nNo event cache read or written; production collector unchanged.')
