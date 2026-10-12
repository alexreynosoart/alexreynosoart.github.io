#!/usr/bin/env python3
"""Read-only diagnostics for three official NYC arts calendars.
No data files are read or written. Standard library only.
"""
from html.parser import HTMLParser
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
import re

SOURCES = [
    ("Wave Hill", "https://www.wavehill.org/calendar"),
    ("Staten Island Museum", "https://www.statenislandmuseum.org/events/list/"),
    ("Bronx Council on the Arts", "https://www.bronxarts.org/events/"),
]
LIMIT = 4_000_000
DATE_RE = re.compile(r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+\d{1,2}(?:,?\s+20\d{2})?\b|\b20\d{2}-\d{2}-\d{2}\b', re.I)
EVENT_HINT = re.compile(r'event|calendar|exhibit|workshop|gallery|tour|program|talk|art|festival', re.I)

class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.text = []
        self.links = []
        self.anchor = None
        self.times = []
        self.jsonld = 0
        self.script_count = 0
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('script', 'style', 'noscript'):
            self.hidden += 1
            if tag == 'script':
                self.script_count += 1
                if 'ld+json' in a.get('type', '').lower():
                    self.jsonld += 1
        if tag == 'a' and self.hidden == 0:
            self.anchor = [a.get('href', ''), []]
        if tag == 'time' and a.get('datetime'):
            self.times.append(a['datetime'])
    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript'):
            self.hidden = max(0, self.hidden - 1)
        if tag == 'a' and self.anchor:
            href, labels = self.anchor
            label = ' '.join(' '.join(labels).split())
            if href and label:
                self.links.append((href, label))
            self.anchor = None
    def handle_data(self, data):
        if not self.hidden:
            s = ' '.join(data.split())
            if s:
                self.text.append(s)
                if self.anchor:
                    self.anchor[1].append(s)

def inspect(name, url):
    print(f'\n=== {name} ===', flush=True)
    print(f'Official URL: {url}', flush=True)
    request = Request(url, headers={
        'User-Agent': 'EverythingArtEventCollector/1.0 (+public calendar preview)',
        'Accept': 'text/html,application/xhtml+xml;q=0.9,*/*;q=0.5',
    })
    try:
        with urlopen(request, timeout=35) as response:
            status = response.status
            final = response.url
            content_type = response.headers.get('Content-Type', '')
            raw = response.read(LIMIT + 1)
    except HTTPError as exc:
        print(f'HTTP: {exc.code} | blocked/unavailable; no events extracted')
        return
    except (URLError, TimeoutError, OSError) as exc:
        print(f'Fetch failed: {type(exc).__name__}: {exc}')
        return
    print(f'HTTP: {status} | bytes: {len(raw)} | content-type: {content_type}')
    print(f'Final URL: {final}')
    if urlparse(final).hostname != urlparse(url).hostname:
        print('Redirected to another host; skipping extraction for safety.')
        return
    if len(raw) > LIMIT:
        print('Response exceeded 4 MB cap; skipping extraction.')
        return
    if 'html' not in content_type.lower():
        print('Not HTML; skipping extraction.')
        return
    html = raw.decode('utf-8', errors='replace')
    parser = PageParser()
    parser.feed(html)
    visible = ' '.join(parser.text)
    dates = list(dict.fromkeys(DATE_RE.findall(visible)))
    candidates = []
    seen = set()
    for href, label in parser.links:
        absolute = urljoin(final, href)
        if urlparse(absolute).hostname == urlparse(final).hostname and EVENT_HINT.search(absolute + ' ' + label):
            if absolute not in seen:
                seen.add(absolute)
                candidates.append((label[:110], absolute))
    print(f'Visible text chars: {len(visible)} | script tags: {parser.script_count} | JSON-LD tags: {parser.jsonld}')
    print(f'Date strings in visible text: {len(dates)} | <time datetime> values: {len(parser.times)}')
    print(f'Date examples: {dates[:8]}')
    print(f'Time values: {parser.times[:8]}')
    print(f'Possible same-site event links: {len(candidates)}')
    for label, href in candidates[:10]:
        print(f'  - {label} | {href}')
    print('Assessment: ' + ('PROMISING: dated HTML and links; needs event-level validation' if (dates or parser.times) and candidates else 'NOT YET USABLE: no clear dated linked records'))

if __name__ == '__main__':
    print('RULE OF THREE: OFFICIAL CALENDAR READ-ONLY PREVIEW')
    for name, url in SOURCES:
        inspect(name, url)
    print('\nPREVIEW ONLY: no events published; data/art-events.json untouched.')
