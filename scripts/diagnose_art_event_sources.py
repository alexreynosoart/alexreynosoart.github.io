#!/usr/bin/env python3
"""Everything Art: READ-ONLY Lincoln Center calendar date-to-event mapping diagnostic.
Replace scripts/diagnose_art_event_sources.py; run existing diagnostic workflow.
Does not modify collector, event JSON, or website.
"""
import datetime as dt
import html
import re
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

URL = 'https://www.lincolncenter.org/series/lincoln-center-presents/v/calendar'
PREFIX = '/series/lincoln-center-presents/'
MONTHS = r'(?:January|February|March|April|May|June|July|August|September|October|November|December)'
DATE = re.compile(r'\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+' + MONTHS + r'\s+\d{1,2}(?:\s+at\s+\d{1,2}:\d{2}\s*[ap]m|\s*-\s*Multiple times)?', re.I)

class Calendar(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tokens = []
        self.anchor = None
        self.hidden = 0
        self.links = []
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('script', 'style', 'noscript'):
            self.hidden += 1
        if tag == 'a' and not self.hidden:
            self.anchor = {'href': a.get('href', ''), 'start': len(self.tokens), 'text': []}
    def handle_data(self, data):
        if not self.hidden:
            value = html.unescape(data)
            self.tokens.append(value)
            if self.anchor is not None:
                self.anchor['text'].append(value)
    def handle_endtag(self, tag):
        if tag == 'a' and self.anchor is not None:
            self.anchor['end'] = len(self.tokens)
            self.links.append(self.anchor)
            self.anchor = None
        if tag in ('script', 'style', 'noscript'):
            self.hidden = max(0, self.hidden - 1)

def compact(value):
    return re.sub(r'\s+', ' ', value).strip()

def is_detail(link):
    p = urlparse(link)
    if p.netloc not in ('www.lincolncenter.org', 'lincolncenter.org'):
        return False
    if not p.path.startswith(PREFIX):
        return False
    tail = p.path[len(PREFIX):].strip('/')
    return bool(tail and '/' not in tail and tail not in ('calendar', 'ticketing'))

print('Everything Art | READ-ONLY Lincoln Center CALENDAR MAPPING diagnostic')
print('Date:', dt.date.today(), '| No files written or published')
try:
    req = urllib.request.Request(URL, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; EverythingArtDiagnostic/1.0; +https://alexreynosoart.com)',
        'Accept': 'text/html'})
    with urllib.request.urlopen(req, timeout=35) as response:
        raw = response.read(4_500_000)
        print('HTTP:', response.status, '| bytes:', len(raw), '| final:', response.geturl())
    page = Calendar()
    page.feed(raw.decode('utf-8', 'replace'))
    links = []
    seen = set()
    for a in page.links:
        full = urljoin(URL, a['href']).split('#')[0].split('?')[0]
        if not is_detail(full) or full in seen:
            continue
        seen.add(full)
        links.append((full, a))
    print('UNIQUE DETAIL LINKS:', len(links))
    print('INSPECTING FIRST 18 LINKS IN DOCUMENT ORDER')
    for index, (link, a) in enumerate(links[:18], 1):
        # Read only text BEFORE the link, never assume a date belongs to it.
        before = compact(' '.join(page.tokens[max(0, a['start'] - 90):a['start']]))
        after = compact(' '.join(page.tokens[a['end']:a['end'] + 25]))
        matches = list(DATE.finditer(before))
        nearest = matches[-1].group(0) if matches else '(none found in preceding text)'
        print('\nEVENT', index)
        print(' URL:', link)
        print(' ANCHOR:', repr(compact(' '.join(a['text']))[:110]))
        print(' NEAREST PRECEDING DATE (UNVERIFIED):', nearest)
        print(' BEFORE:', before[-420:])
        print(' AFTER:', after[:160])
    print('\nNOTE: Preceding dates are candidate associations only, NOT verified event dates.')
    print('Look for a consistent date -> event title -> detail link pattern before collecting.')
except Exception as exc:
    print('DIAGNOSTIC ERROR:', type(exc).__name__, str(exc)[:400])
    raise
print('\nDiagnostic complete. No event files changed.')
