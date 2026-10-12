#!/usr/bin/env python3
"""Everything Art: READ-ONLY New York Live Arts event-link/date diagnostic.
Replace scripts/diagnose_art_event_sources.py with this file to test via GitHub Actions.
Does not write files, alter the collector, or publish events.
"""
import datetime as dt
import html
import re
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

BASE = 'https://newyorklivearts.org/'
PAGES = [BASE, BASE + 'event/toi-moi-tituba/']
MONTHS = r'January|February|March|April|May|June|July|August|September|October|November|December'
DATE_RE = re.compile(r'\b(?:' + MONTHS + r')\s+\d{1,2}(?:\s*[-–&]\s*\d{1,2})?(?:\s*,?\s*20\d{2})?\b', re.I)
EVENT_PATH = re.compile(r'^/event/[^/]+/?$')

class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.text = []
        self._anchor = None
        self._hidden = 0
        self._title = False
        self.title = ''
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('script', 'style', 'noscript'):
            self._hidden += 1
        if tag == 'title':
            self._title = True
        if tag == 'a':
            self._anchor = {'href': a.get('href', ''), 'text': []}
    def handle_data(self, data):
        if self._title:
            self.title += data
        if not self._hidden:
            self.text.append(data)
            if self._anchor is not None:
                self._anchor['text'].append(data)
    def handle_endtag(self, tag):
        if tag == 'a' and self._anchor is not None:
            self.links.append((self._anchor['href'], ' '.join(self._anchor['text'])))
            self._anchor = None
        if tag == 'title':
            self._title = False
        if tag in ('script', 'style', 'noscript'):
            self._hidden = max(0, self._hidden - 1)

def compact(value):
    return re.sub(r'\s+', ' ', html.unescape(value)).strip()

def get(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; EverythingArtDiagnostic/1.0; +https://alexreynosoart.com)',
        'Accept': 'text/html'})
    with urllib.request.urlopen(req, timeout=25) as response:
        raw = response.read(2_500_000)
        final = response.geturl()
        status = response.status
    page = Page()
    page.feed(raw.decode('utf-8', 'replace'))
    return page, final, status, len(raw)

print('Everything Art | READ-ONLY New York Live Arts performance diagnostic')
print('Date:', dt.date.today(), '| No files written or published')
found = {}
for url in PAGES:
    print('\n' + '=' * 72)
    print('PAGE:', url)
    try:
        page, final, status, size = get(url)
    except Exception as exc:
        print('ERROR:', type(exc).__name__, str(exc)[:250])
        continue
    print('HTTP:', status, '| bytes:', size, '| final:', final)
    print('TITLE:', compact(page.title)[:160])
    visible = compact(' '.join(page.text))
    dates = list(dict.fromkeys(DATE_RE.findall(visible)))
    print('VISIBLE DATE PHRASES:', dates[:30])
    for phrase in dates[:12]:
        match = re.search(re.escape(phrase), visible, re.I)
        if match:
            print(' DATE CONTEXT:', visible[max(0, match.start()-115):match.end()+135])
    event_links = []
    for href, label in page.links:
        full = urljoin(final, href).split('#', 1)[0].split('?', 1)[0]
        parsed = urlparse(full)
        if parsed.scheme == 'https' and parsed.netloc in ('newyorklivearts.org', 'www.newyorklivearts.org') and EVENT_PATH.fullmatch(parsed.path):
            event_links.append((full, compact(label)))
            found.setdefault(full, compact(label))
    event_links = list(dict.fromkeys(event_links))
    print('EVENT DETAIL LINKS:', len(event_links))
    for link, label in event_links[:35]:
        print(' EVENT:', repr(label[:100]), '|', link)

print('\n' + '=' * 72)
print('UNIQUE EVENT LINKS DISCOVERED:', len(found))
print('INSPECTING UP TO 8 DISCOVERED EVENT PAGES (READ-ONLY)')
for url in list(found)[:8]:
    if url in PAGES:
        continue
    try:
        page, final, status, size = get(url)
        visible = compact(' '.join(page.text))
        dates = list(dict.fromkeys(DATE_RE.findall(visible)))
        print('\nEVENT:', url)
        print(' HTTP:', status, '| TITLE:', compact(page.title)[:120])
        print(' DATE PHRASES:', dates[:15])
        for phrase in dates[:4]:
            match = re.search(re.escape(phrase), visible, re.I)
            if match:
                print(' CONTEXT:', visible[max(0, match.start()-100):match.end()+115])
    except Exception as exc:
        print(' EVENT ERROR:', url, type(exc).__name__, str(exc)[:180])
print('\nDiagnostic complete. No event files changed.')
