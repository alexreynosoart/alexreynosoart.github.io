#!/usr/bin/env python3
"""Everything Art | READ-ONLY Lincoln Center Presents event/date diagnostic.
Replace scripts/diagnose_art_event_sources.py with this file.
No files are written, no events are published, and the live collector is untouched.
"""
import datetime as dt
import html
import json
import re
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

BASE = 'https://www.lincolncenter.org'
PAGES = [
    BASE + '/series/lincoln-center-presents/v/calendar',
    BASE + '/series/lincoln-center-presents',
]
MONTHS = r'January|February|March|April|May|June|July|August|September|October|November|December'
DATE_RE = re.compile(r'\b(?:' + MONTHS + r')\s+\d{1,2}(?:\s*[-–&]\s*\d{1,2})?(?:\s*,?\s*20\d{2})?\b', re.I)
ISO_RE = re.compile(r'\b20\d{2}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2})?)?\b')
BAD_PATH = re.compile(r'(getting-here|directions|accessibility|visit|about|contact|support|donate|privacy|terms|faq|newsletter|calendar/?$|/v/calendar|/search|/tickets/?$)', re.I)

class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.text = []
        self.title = ''
        self._title = False
        self._hidden = 0
        self._anchor = None
        self.jsonld = []
        self._ld = False
        self._ld_buffer = []
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'script':
            self._ld = a.get('type', '').lower() == 'application/ld+json'
            self._ld_buffer = []
        if tag in ('script', 'style', 'noscript'):
            self._hidden += 1
        if tag == 'title':
            self._title = True
        if tag == 'a':
            self._anchor = {'href': a.get('href', ''), 'text': []}
    def handle_data(self, data):
        if self._ld:
            self._ld_buffer.append(data)
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
        if tag == 'script':
            if self._ld and self._ld_buffer:
                self.jsonld.append(''.join(self._ld_buffer))
            self._ld = False
            self._ld_buffer = []
        if tag in ('script', 'style', 'noscript'):
            self._hidden = max(0, self._hidden - 1)

def compact(value):
    return re.sub(r'\s+', ' ', html.unescape(str(value or ''))).strip()

def get(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; EverythingArtDiagnostic/1.0; +https://alexreynosoart.com)',
        'Accept': 'text/html,application/xhtml+xml'})
    with urllib.request.urlopen(req, timeout=25) as response:
        raw = response.read(3_000_000)
        final = response.geturl()
        status = response.status
    page = Page()
    page.feed(raw.decode('utf-8', 'replace'))
    return page, final, status, len(raw)

def candidate_url(href, parent):
    full = urljoin(parent, href).split('#', 1)[0].split('?', 1)[0]
    p = urlparse(full)
    if p.scheme != 'https' or p.netloc not in ('lincolncenter.org', 'www.lincolncenter.org'):
        return ''
    path = p.path.rstrip('/')
    if BAD_PATH.search(path):
        return ''
    # Favor Lincoln Center Presents individual event pages; keep other deep
    # event-like paths for inspection, but exclude generic navigation links.
    if len([x for x in path.split('/') if x]) < 3:
        return ''
    if not (re.search(r'/series/|/event/|/events/|/show/|/performance/', path, re.I)):
        return ''
    return full

def structured_events(page):
    found = []
    def walk(obj):
        if isinstance(obj, list):
            for item in obj:
                walk(item)
        elif isinstance(obj, dict):
            typ = obj.get('@type', '')
            types = typ if isinstance(typ, list) else [typ]
            if any('Event' in str(t) for t in types):
                found.append((compact(obj.get('name'))[:110], str(obj.get('startDate', ''))[:50], str(obj.get('url', ''))[:160]))
            for v in obj.values():
                if isinstance(v, (list, dict)):
                    walk(v)
    for raw in page.jsonld:
        try:
            walk(json.loads(raw))
        except (ValueError, TypeError):
            pass
    return found

print('Everything Art | READ-ONLY Lincoln Center Presents diagnostic')
print('Date:', dt.date.today(), '| No files written or published')
found = {}
for url in PAGES:
    print('\n' + '=' * 72)
    print('CALENDAR:', url)
    try:
        page, final, status, size = get(url)
    except Exception as exc:
        print('ERROR:', type(exc).__name__, str(exc)[:250])
        continue
    print('HTTP:', status, '| bytes:', size, '| final:', final)
    print('TITLE:', compact(page.title)[:160])
    visible = compact(' '.join(page.text))
    dates = list(dict.fromkeys(DATE_RE.findall(visible)))
    print('VISIBLE DATE PHRASES:', dates[:25])
    print('ISO DATE PHRASES:', list(dict.fromkeys(ISO_RE.findall(visible)))[:15])
    for phrase in dates[:8]:
        m = re.search(re.escape(phrase), visible, re.I)
        if m:
            print(' DATE CONTEXT:', visible[max(0, m.start()-100):m.end()+130])
    print('JSON-LD EVENT RECORDS:', structured_events(page)[:12])
    candidates = []
    for href, label in page.links:
        full = candidate_url(href, final)
        if full:
            item = (full, compact(label))
            if item not in candidates:
                candidates.append(item)
            found.setdefault(full, compact(label))
    print('POTENTIAL EVENT LINKS:', len(candidates))
    for link, label in candidates[:35]:
        print(' LINK:', repr(label[:100]), '|', link)

print('\n' + '=' * 72)
print('UNIQUE POTENTIAL EVENT LINKS:', len(found))
print('INSPECTING UP TO 8 CANDIDATE DETAIL PAGES (READ-ONLY)')
for url in list(found)[:8]:
    try:
        page, final, status, size = get(url)
        visible = compact(' '.join(page.text))
        dates = list(dict.fromkeys(DATE_RE.findall(visible)))
        print('\nCANDIDATE:', url)
        print(' HTTP:', status, '| TITLE:', compact(page.title)[:130])
        print(' VISIBLE DATES:', dates[:12])
        print(' STRUCTURED EVENTS:', structured_events(page)[:8])
        for phrase in dates[:3]:
            m = re.search(re.escape(phrase), visible, re.I)
            if m:
                print(' CONTEXT:', visible[max(0, m.start()-95):m.end()+120])
    except Exception as exc:
        print(' DETAIL ERROR:', url, type(exc).__name__, str(exc)[:180])
print('\nDiagnostic complete. No event files changed.')
