#!/usr/bin/env python3
"""Everything Art: READ-ONLY performing-arts source investigation.
Run through the existing Diagnose Everything Art Event Sources workflow.
No files are written, and the live event collector is not invoked.
"""
import datetime as dt
import html
from html.parser import HTMLParser
import json
import re
import urllib.error
import urllib.parse
import urllib.request

SOURCES = [
    ("Lincoln Center calendar", "https://www.lincolncenter.org/series/lincoln-center-presents/v/calendar", "lincolncenter.org"),
    ("Lincoln Center featured performances", "https://www.lincolncenter.org/series/lincoln-center-presents/s/Featured%20Performances", "lincolncenter.org"),
    ("New York Live Arts home", "https://newyorklivearts.org/", "newyorklivearts.org"),
    ("New York Live Arts programs", "https://newyorklivearts.org/programs/", "newyorklivearts.org"),
]
DATE_PATTERNS = [
    re.compile(r'\b20\d{2}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2})?)?\b'),
    re.compile(r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:,?\s+20\d{2})?\b', re.I),
    re.compile(r'\b(?:Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+\d{1,2}(?:,?\s+20\d{2})?\b', re.I),
]

class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = []
        self.headings = []
        self.links = []
        self.times = []
        self.meta = {}
        self.jsonld = []
        self.text = []
        self._title = False
        self._heading = None
        self._script = False
        self._script_buffer = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'title': self._title = True
        if tag in ('h1', 'h2', 'h3'): self._heading = [tag, []]
        if tag == 'a' and a.get('href'): self.links.append(a['href'])
        if tag == 'time': self.times.append(a.get('datetime', ''))
        if tag == 'meta':
            key = a.get('property') or a.get('name')
            if key in ('og:title', 'description', 'og:description'): self.meta[key] = a.get('content', '')
        if tag == 'script':
            self._skip += 1
            if a.get('type', '').lower() == 'application/ld+json':
                self._script = True
                self._script_buffer = []
        elif tag in ('style', 'noscript'): self._skip += 1

    def handle_endtag(self, tag):
        if tag == 'title': self._title = False
        if self._heading and tag == self._heading[0]:
            value = re.sub(r'\s+', ' ', ''.join(self._heading[1])).strip()
            if value: self.headings.append(value)
            self._heading = None
        if tag == 'script':
            if self._script:
                self.jsonld.append(''.join(self._script_buffer))
                self._script = False
            self._skip = max(0, self._skip - 1)
        elif tag in ('style', 'noscript'): self._skip = max(0, self._skip - 1)

    def handle_data(self, data):
        if self._title: self.title.append(data)
        if self._heading: self._heading[1].append(data)
        if self._script: self._script_buffer.append(data)
        if not self._skip: self.text.append(data)


def dates(value, limit=15):
    found = []
    for pattern in DATE_PATTERNS:
        for match in pattern.finditer(value):
            candidate = match.group(0)
            if candidate not in found: found.append(candidate)
            if len(found) >= limit: return found
    return found


def fetch(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; EverythingArtSourceDiagnostic/1.0; +https://alexreynosoart.com)',
        'Accept': 'text/html,application/xhtml+xml',
    })
    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read(2_000_000)
        return raw.decode('utf-8', 'replace'), response.status, response.geturl(), len(raw)


def event_objects(blocks):
    events = []
    def visit(node):
        if isinstance(node, list):
            for child in node: visit(child)
        elif isinstance(node, dict):
            types = node.get('@type', [])
            if isinstance(types, str): types = [types]
            if any('Event' in str(t) for t in types) and node.get('startDate'):
                events.append((str(node.get('name', ''))[:90], str(node.get('startDate', ''))[:40]))
            for child in node.values():
                if isinstance(child, (list, dict)): visit(child)
    for block in blocks:
        try: visit(json.loads(block))
        except (ValueError, TypeError): pass
    return events


def inspect(name, url, domain, follow=False):
    print('\n' + '=' * 74)
    print(name, '|', url)
    try:
        raw, status, final, size = fetch(url)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        print('FETCH ERROR:', str(exc)[:250])
        return []
    page = Page()
    page.feed(raw)
    visible = re.sub(r'\s+', ' ', html.unescape(' '.join(page.text))).strip()
    print('HTTP:', status, '| bytes:', size, '| final:', final)
    print('TITLE:', ' '.join(page.title)[:160])
    print('HEADINGS:', page.headings[:10])
    print('META:', page.meta)
    print('TIME datetime samples:', [x for x in page.times if x][:12])
    print('VISIBLE date samples:', dates(visible))
    print('RAW ISO date samples:', dates(raw, 12))
    events = event_objects(page.jsonld)
    print('JSON-LD blocks:', len(page.jsonld), '| dated Event objects:', len(events))
    print('JSON-LD Event examples:', events[:5])
    candidates = []
    seen = set()
    for href in page.links:
        target = urllib.parse.urljoin(final, href).split('#', 1)[0]
        parsed = urllib.parse.urlparse(target)
        if not parsed.hostname or not (parsed.hostname == domain or parsed.hostname.endswith('.' + domain)):
            continue
        path = parsed.path.lower()
        if not re.search(r'/event[s]?/|/series/|/program[s]?/|/calendar|/performance|/show/', path):
            continue
        if target not in seen:
            seen.add(target)
            candidates.append(target)
    print('Candidate same-site links:', len(candidates))
    for target in candidates[:12]: print(' LINK', target)
    for sample in dates(visible, 3):
        match = visible.find(sample)
        print(' DATE CONTEXT:', visible[max(0, match - 85):match + 125])
    return candidates


if __name__ == '__main__':
    print('Everything Art | READ-ONLY Lincoln Center + New York Live Arts diagnostic')
    print('Date:', dt.date.today(), '| No files written, no publication')
    collected = {}
    for name, url, domain in SOURCES:
        collected[name] = inspect(name, url, domain)
    # Test a small sample of actual detail links, if discoverable.
    for name, domain in [('Lincoln Center calendar', 'lincolncenter.org'),
                         ('New York Live Arts home', 'newyorklivearts.org')]:
        links = collected.get(name, [])
        detail = [u for u in links if re.search(r'/event/|/series/[^/]+/[^/]+', urllib.parse.urlparse(u).path, re.I)]
        print('\nDETAIL SAMPLE:', name, '|', len(detail), 'candidate detail links')
        for index, target in enumerate(detail[:2], 1):
            inspect(name + ' detail ' + str(index), target, domain)
    print('\nDiagnostic complete. No event files changed.')
