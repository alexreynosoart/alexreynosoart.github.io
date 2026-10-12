#!/usr/bin/env python3
"""Everything Art: read-only Lincoln Center Presents event-detail diagnostic.
Replace scripts/diagnose_art_event_sources.py and run the existing diagnostic action.
No event JSON, collector, or website files are changed.
"""
import datetime as dt
import html
import json
import re
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

ROOT = 'https://www.lincolncenter.org'
CALENDAR = ROOT + '/series/lincoln-center-presents/v/calendar'
PREFIX = '/series/lincoln-center-presents/'
MONTH = r'(?:January|February|March|April|May|June|July|August|September|October|November|December)'
DATE = re.compile(r'\b' + MONTH + r'\s+\d{1,2}(?:\s*[-–]\s*\d{1,2})?(?:,?\s*20\d{2})?\b', re.I)
ISO = re.compile(r'\b20\d{2}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2})?)?\b')
SAMPLES = [
    PREFIX + 'plaza-374',
    PREFIX + 'sophia-club-live-philosophy',
    PREFIX + 'over-my-head-i-hear-freedom-in-the-air-604',
    PREFIX + 'mei-semones-849',
]

class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.text = []
        self.headings = []
        self.title = ''
        self._ignore = 0
        self._anchor = None
        self._heading = None
        self._title = False
        self._ld = False
        self._script_text = []
        self.jsonld = []
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'script':
            self._ld = a.get('type', '').lower() == 'application/ld+json'
            self._script_text = []
        if tag in ('script', 'style', 'noscript'):
            self._ignore += 1
        if tag == 'title':
            self._title = True
        if tag == 'a':
            self._anchor = [a.get('href', ''), []]
        if tag in ('h1', 'h2', 'h3'):
            self._heading = [tag, []]
    def handle_data(self, data):
        if self._ld:
            self._script_text.append(data)
        if self._title:
            self.title += data
        if not self._ignore:
            self.text.append(data)
            if self._anchor is not None:
                self._anchor[1].append(data)
            if self._heading is not None:
                self._heading[1].append(data)
    def handle_endtag(self, tag):
        if tag == 'a' and self._anchor is not None:
            self.links.append((self._anchor[0], ' '.join(self._anchor[1])))
            self._anchor = None
        if tag in ('h1', 'h2', 'h3') and self._heading is not None:
            self.headings.append((self._heading[0], ' '.join(self._heading[1])))
            self._heading = None
        if tag == 'title':
            self._title = False
        if tag == 'script':
            if self._ld and self._script_text:
                self.jsonld.append(''.join(self._script_text))
            self._ld = False
        if tag in ('script', 'style', 'noscript'):
            self._ignore = max(0, self._ignore - 1)

def clean(value):
    return re.sub(r'\s+', ' ', html.unescape(str(value or ''))).strip()

def fetch(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; EverythingArtDiagnostic/1.0; +https://alexreynosoart.com)',
        'Accept': 'text/html'})
    with urllib.request.urlopen(req, timeout=25) as response:
        raw = response.read(3_000_000)
        status = response.status
        final = response.geturl()
    page = Page()
    page.feed(raw.decode('utf-8', 'replace'))
    return page, status, final, len(raw)

def is_detail(url):
    p = urlparse(url)
    if p.netloc not in ('lincolncenter.org', 'www.lincolncenter.org'):
        return False
    if not p.path.startswith(PREFIX):
        return False
    slug = p.path[len(PREFIX):].strip('/')
    return bool(slug and '/' not in slug and slug.lower() not in ('calendar', 'events'))

def structured(page):
    out = []
    def walk(item):
        if isinstance(item, list):
            for x in item:
                walk(x)
        elif isinstance(item, dict):
            kinds = item.get('@type', [])
            kinds = kinds if isinstance(kinds, list) else [kinds]
            if any('Event' in str(k) for k in kinds):
                out.append((clean(item.get('name'))[:100], clean(item.get('startDate'))[:40]))
            for value in item.values():
                if isinstance(value, (dict, list)):
                    walk(value)
    for raw in page.jsonld:
        try:
            walk(json.loads(raw))
        except (ValueError, TypeError):
            pass
    return out[:8]

print('Everything Art | READ-ONLY Lincoln Center INDIVIDUAL EVENT diagnostic')
print('Date:', dt.date.today(), '| No files written or published')
try:
    calendar, status, final, size = fetch(CALENDAR)
    print('\nCALENDAR HTTP:', status, '| bytes:', size)
    details = {}
    for href, label in calendar.links:
        url = urljoin(final, href).split('#', 1)[0].split('?', 1)[0]
        if is_detail(url):
            details.setdefault(url, clean(label))
    print('REAL DETAIL URL CANDIDATES:', len(details))
    for url, label in list(details.items())[:18]:
        print(' DETAIL LINK:', repr(label[:65]), '|', url)
except Exception as exc:
    print('CALENDAR ERROR:', type(exc).__name__, str(exc)[:220])
    details = {}

urls = list(dict.fromkeys([ROOT + path for path in SAMPLES] + list(details)[:4]))[:8]
for url in urls:
    print('\n' + '=' * 70)
    print('DETAIL PAGE:', url)
    try:
        page, status, final, size = fetch(url)
    except Exception as exc:
        print('ERROR:', type(exc).__name__, str(exc)[:220])
        continue
    visible = clean(' '.join(page.text))
    print('HTTP:', status, '| bytes:', size, '| final:', final)
    print('TITLE:', clean(page.title)[:120])
    print('HEADINGS:', [(tag, clean(t)[:95]) for tag, t in page.headings[:14]])
    print('STRUCTURED EVENTS:', structured(page))
    print('DATE PHRASES FOUND:', len(DATE.findall(visible)))
    print('ISO DATES:', list(dict.fromkeys(ISO.findall(visible)))[:8])
    # First dates are often repeated site-wide navigation. Show all distinct
    # matches plus their context to distinguish site-wide from page-specific.
    matches = list(DATE.finditer(visible))
    print('FIRST DATE CONTEXTS:')
    for m in matches[:3]:
        print(' ', visible[max(0, m.start()-65):m.end()+125])
    print('LAST DATE CONTEXTS:')
    for m in matches[-5:]:
        print(' ', visible[max(0, m.start()-100):m.end()+150])
    print('END OF PAGE TEXT:', visible[-550:])
print('\nDiagnostic complete. No event files changed.')
