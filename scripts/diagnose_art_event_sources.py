#!/usr/bin/env python3
"""Read-only NYPL event-source investigation. No repository files are written."""
import re
import urllib.request
import urllib.error
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

PAGES = [
    'https://www.nypl.org/events',
    'https://www.nypl.org/events/calendar',
    'https://www.nypl.org/events/calendar/classes-workshops',
    'https://www.nypl.org/events/exhibitions/current',
]

class Inspector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = []
        self.links = []
        self.forms = []
        self.data_attrs = []
    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == 'script' and d.get('src'):
            self.scripts.append(d['src'])
        if tag == 'a' and d.get('href'):
            self.links.append(d['href'])
        if tag == 'form':
            self.forms.append((d.get('action', ''), d.get('method', 'GET')))
        for k, v in attrs:
            if k and (k.startswith('data-') and re.search(r'event|calendar|api|endpoint|view', k, re.I)):
                self.data_attrs.append((k, str(v)[:120]))

def inspect(page):
    print('\n===', page, '===', flush=True)
    req = urllib.request.Request(page, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; EverythingArtEventCollector/1.1; +https://alexreynosoart.com)',
        'Accept': 'text/html',
    })
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            final = response.url
            raw = response.read(2_000_000).decode('utf-8', 'replace')
            print('HTTP:', response.status, 'HTML chars:', len(raw))
    except (urllib.error.URLError, TimeoutError) as exc:
        print('Request failed:', type(exc).__name__, str(exc)[:180])
        return
    p = Inspector()
    p.feed(raw)
    print('External script count:', len(p.scripts), 'forms:', len(p.forms), 'links:', len(p.links))
    for action, method in p.forms[:8]:
        print('FORM:', method, urljoin(final, action)[:220])
    for k, v in p.data_attrs[:12]:
        print('DATA ATTRIBUTE:', k, v)
    # Show candidate script names only; don't fetch JavaScript bundles or print page contents.
    for src in p.scripts:
        if re.search(r'event|calendar|search|drupal|main|app|bundle', src, re.I):
            print('SCRIPT:', urljoin(final, src)[:240])
    seen = set()
    for href in p.links:
        u = urljoin(final, href)
        path = urlparse(u).path
        if urlparse(u).hostname not in ('nypl.org', 'www.nypl.org'):
            continue
        if re.search(r'/events/(?:[^/]+/)?(?:[^/]+/)?\d+|/events/[^/]+/[^/]+|/events/calendar\?', u, re.I):
            if u not in seen and len(seen) < 15:
                seen.add(u)
                print('POSSIBLE EVENT LINK:', u[:220])
    # Print bounded context around API-related terms, with possible secrets masked.
    terms = ['drupalSettings', 'views/ajax', 'jsonapi', 'graphql', '/api/', 'calendar-event', 'event-card', 'event-list', 'event_date']
    for term in terms:
        matches = list(re.finditer(re.escape(term), raw, re.I))
        print('HINT', term, 'count:', len(matches))
        for m in matches[:2]:
            sample = re.sub(r'\s+', ' ', raw[max(0, m.start()-100):m.end()+140])
            sample = re.sub(r'(?i)(token|api[_-]?key|authorization|password|secret)(["\s:=]+)[^\s"<>]{4,}', r'\1\2[REDACTED]', sample)
            print('  CONTEXT:', sample[:280])

if __name__ == '__main__':
    for page in PAGES:
        inspect(page)
    print('\nRead-only NYPL investigation complete. No files changed.')
