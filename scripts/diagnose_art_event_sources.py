#!/usr/bin/env python3
"""Everything Art: READ-ONLY Lincoln Center repeat-date and event-card diagnostic.
Replace scripts/diagnose_art_event_sources.py and run the diagnostic Action.
No collector changes, JSON writes, or publication.
"""
import collections
import datetime as dt
import html
import re
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

URL = 'https://www.lincolncenter.org/series/lincoln-center-presents/v/calendar'
PREFIX = '/series/lincoln-center-presents/'
MONTH = r'(?:January|February|March|April|May|June|July|August|September|October|November|December)'
DATE = re.compile(r'\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+(' + MONTH + r')\s+(\d{1,2})(?:\s+at\s+(\d{1,2}:\d{2}\s*[ap]m)|\s*-\s*(Multiple times))?', re.I)

class Calendar(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tokens, self.links, self.anchor, self.hidden = [], [], None, 0
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('script', 'style', 'noscript'):
            self.hidden += 1
        if tag == 'a' and not self.hidden:
            self.anchor = {'href': attrs.get('href', ''), 'start': len(self.tokens), 'text': []}
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

def compact(s):
    return re.sub(r'\s+', ' ', s).strip()

def detail(url):
    p = urlparse(url)
    tail = p.path[len(PREFIX):].strip('/') if p.path.startswith(PREFIX) else ''
    return p.netloc in ('www.lincolncenter.org', 'lincolncenter.org') and bool(tail) and '/' not in tail

def get_date(match, today):
    month = dt.datetime.strptime(match.group(2), '%B').month
    day = int(match.group(3))
    for year in (today.year, today.year + 1):
        try:
            date = dt.date(year, month, day)
        except ValueError:
            continue
        if today <= date <= today + dt.timedelta(days=400) and date.strftime('%A').lower() == match.group(1).lower():
            return date.isoformat()
    return None

print('Everything Art | READ-ONLY Lincoln Center REPEAT-DATE diagnostic')
print('No event files written or modified.')
today = dt.date.today()
req = urllib.request.Request(URL, headers={'User-Agent': 'Mozilla/5.0 (compatible; EverythingArtDiagnostic/1.0; +https://alexreynosoart.com)', 'Accept': 'text/html'})
with urllib.request.urlopen(req, timeout=40) as response:
    raw = response.read(6_000_000)
    print('HTTP:', response.status, '| bytes:', len(raw))
page = Calendar()
page.feed(raw.decode('utf-8', 'replace'))
records = collections.defaultdict(list)
seen = set()
for a in page.links:
    url = urljoin(URL, a['href']).split('#')[0].split('?')[0]
    if not detail(url):
        continue
    # The calendar repeats each card's URL in its image, title and Learn More links.
    # Deduplicate those repetitions within one date/time, but keep other dates.
    before = compact(' '.join(page.tokens[max(0, a['start'] - 90):a['start']]))
    matches = list(DATE.finditer(before))
    if not matches:
        continue
    match = matches[-1]
    date = get_date(match, today)
    if not date:
        continue
    time = compact(match.group(4) or match.group(5) or 'unspecified')
    key = (url, date, time)
    if key in seen:
        continue
    seen.add(key)
    after = compact(' '.join(page.tokens[a['end']:a['end'] + 28]))
    records[url].append((date, time, after[:135]))

print('Unique production URLs with plausible dates:', len(records))
print('Unique URL + date + time combinations:', sum(map(len, records.values())))
repeats = [(url, items) for url, items in records.items() if len(items) > 1]
print('Production URLs with multiple date/time combinations:', len(repeats))
print('\nFIRST 12 REPEATED PRODUCTIONS:')
for url, items in repeats[:12]:
    print('\nPRODUCTION:', url)
    for date, time, context in items[:12]:
        print(' ', date, '|', time, '|', context)
print('\nFIRST 12 SINGLE-DATE PRODUCTIONS:')
for url, items in [(u, x) for u, x in records.items() if len(x) == 1][:12]:
    date, time, context = items[0]
    print(date, '|', time, '|', url)
    print(' CONTEXT:', context)
print('\nWARNING: These are candidate associations. Review repeats for accidental carry-over from nearby cards.')
print('Diagnostic complete. No event files changed.')
