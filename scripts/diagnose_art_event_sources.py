#!/usr/bin/env python3
"""Read-only diagnostic for Everything Art's three zero-result event sources.
Run via GitHub Actions or locally: python scripts/diagnose_art_event_sources.py
Does not write files or alter the event cache.
"""
import json
import re
import urllib.error
import urllib.request
from collections import Counter
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

SOURCES = {
    'MoMA': 'https://www.moma.org/calendar/exhibitions',
    'Guggenheim': 'https://www.guggenheim.org/',
    'NYPL': 'https://www.nypl.org/events',
    'NYPL Calendar': 'https://www.nypl.org/events/calendar',
}

class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_ld = False
        self.parts = []
        self.blocks = []
        self.links = []
    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            attrs_dict = dict(attrs)
            href = attrs_dict.get('href', '')
            if href and len(self.links) < 5000:
                self.links.append(href)
        if tag == 'script' and dict(attrs).get('type', '').lower().split(';')[0].strip() == 'application/ld+json':
            self.in_ld = True
            self.parts = []
    def handle_data(self, data):
        if self.in_ld:
            self.parts.append(data)
    def handle_endtag(self, tag):
        if tag == 'script' and self.in_ld:
            self.blocks.append(''.join(self.parts))
            self.in_ld = False

def walk(node, counts, samples):
    if isinstance(node, list):
        for item in node:
            walk(item, counts, samples)
    elif isinstance(node, dict):
        types = node.get('@type', [])
        if isinstance(types, str):
            types = [types]
        for typ in types:
            typ = str(typ).split('/')[-1]
            counts[typ] += 1
            if re.search(r'event|exhibition|festival', typ, re.I) and len(samples) < 5:
                samples.append({'type': typ, 'name': str(node.get('name', ''))[:90],
                                'startDate': str(node.get('startDate', ''))[:40],
                                'urlPresent': bool(node.get('url') or node.get('@id'))})
        for value in node.values():
            if isinstance(value, (dict, list)):
                walk(value, counts, samples)

def inspect(name, url):
    print(f'\n=== {name} ===\nRequested: {url}', flush=True)
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; EverythingArtEventCollector/1.1; +https://alexreynosoart.com)',
        'Accept': 'text/html',
    })
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            status = response.status
            final_url = response.url
            content_type = response.headers.get('Content-Type', '')
            raw = response.read(3_000_000).decode('utf-8', 'replace')
        print(f'HTTP: {status}; final URL: {final_url}')
        print(f'Content-Type: {content_type}; HTML characters read: {len(raw)}')
        parser = PageParser()
        parser.feed(raw)
        print(f'JSON-LD script blocks: {len(parser.blocks)}')
        if name.startswith('NYPL'):
            event_links = []
            for href in parser.links:
                absolute = urljoin(final_url, href)
                parsed = urlparse(absolute)
                if parsed.hostname in ('nypl.org', 'www.nypl.org') and re.search(r'/events?/|/calendar/|/programs?/', parsed.path, re.I):
                    if absolute not in event_links:
                        event_links.append(absolute)
            print(f'NYPL event-like anchors: {len(event_links)} (first 12 shown)')
            for link in event_links[:12]:
                print('  LINK:', link)
            for label, pattern in [('datetime attributes', r'datetime=[\"\'][^\"\']+'), ('ISO dates', r'20\d{2}-\d{2}-\d{2}'), ('calendar API hints', r'(?:api|graphql|drupalSettings|__NEXT_DATA__)')]:
                print(f'{label}: {len(re.findall(pattern, raw, re.I))}')
        counts = Counter()
        samples = []
        errors = 0
        for block in parser.blocks:
            try:
                walk(json.loads(block), counts, samples)
            except (ValueError, TypeError):
                errors += 1
        print('Structured-data types: ' + (', '.join(f'{k}={v}' for k, v in counts.most_common(12)) or '(none)'))
        print(f'Unparseable JSON-LD blocks: {errors}')
        print('Event-like samples (metadata only): ' + json.dumps(samples, ensure_ascii=False))
        if not samples:
            print('Diagnosis: No event-like JSON-LD found on this page. Current adapter cannot extract events here.')
        else:
            print('Diagnosis: Event-like JSON-LD exists; inspect dates/URLs and collector filters next.')
    except urllib.error.HTTPError as exc:
        print(f'HTTP error: {exc.code} {exc.reason}; source not accessible from runner')
    except Exception as exc:
        print(f'Request/parse error: {type(exc).__name__}: {exc}')

if __name__ == '__main__':
    for source, page in SOURCES.items():
        inspect(source, page)
    print('\nRead-only diagnosis complete. No files changed.')
