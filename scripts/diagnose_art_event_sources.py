#!/usr/bin/env python3
"""Everything Art | Lincoln Center read-only collector PREVIEW.
Replace scripts/diagnose_art_event_sources.py, run diagnostic workflow.
No writes, no JSON changes, no publishing. Dates are candidates, not verified.
"""
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
EXCLUDE = {'calendar', 'ticketing', 'fast track', 'choose-what-you-pay'}

class Calendar(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tokens = []
        self.links = []
        self.anchor = None
        self.hidden = 0
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
            self.hidden = max(0, self.hidden - 1
            )

def compact(value):
    return re.sub(r'\s+', ' ', value).strip()

def detail(url):
    p = urlparse(url)
    if p.netloc not in ('www.lincolncenter.org', 'lincolncenter.org') or not p.path.startswith(PREFIX):
        return False
    tail = p.path[len(PREFIX):].strip('/')
    return bool(tail and '/' not in tail and tail.lower() not in EXCLUDE)

def parse_date(match, today):
    month = dt.datetime.strptime(match.group(2), '%B').month
    day = int(match.group(3))
    options = []
    for year in (today.year, today.year + 1):
        try:
            value = dt.date(year, month, day)
        except ValueError:
            continue
        if value >= today - dt.timedelta(days=1) and value <= today + dt.timedelta(days=400):
            options.append(value)
    if not options:
        return None, 'out of range'
    date = min(options)
    if date.strftime('%A').lower() != match.group(1).lower():
        return date, 'WEEKDAY MISMATCH'
    return date, 'weekday matches'

print('Everything Art | READ-ONLY Lincoln Center collector preview')
print('No files will be written. Candidate dates must pass review before integration.')
today = dt.date.today()
print('Run date:', today)
req = urllib.request.Request(URL, headers={'User-Agent': 'Mozilla/5.0 (compatible; EverythingArtDiagnostic/1.0; +https://alexreynosoart.com)', 'Accept': 'text/html'})
try:
    with urllib.request.urlopen(req, timeout=35) as response:
        raw = response.read(5_000_000)
        print('HTTP:', response.status, '| bytes:', len(raw))
    page = Calendar()
    page.feed(raw.decode('utf-8', 'replace'))
    unique = {}
    for a in page.links:
        url = urljoin(URL, a['href']).split('#')[0].split('?')[0]
        if detail(url) and url not in unique:
            unique[url] = a
    print('Unique production URLs:', len(unique))
    print('Previewing up to 30 production URLs in calendar order:')
    accepted = 0
    for index, (url, a) in enumerate(list(unique.items())[:30], 1):
        before = compact(' '.join(page.tokens[max(0, a['start'] - 90):a['start']]))
        after = compact(' '.join(page.tokens[a['end']:a['end'] + 30]))
        dates = list(DATE.finditer(before))
        match = dates[-1] if dates else None
        date, check = parse_date(match, today) if match else (None, 'no date')
        # A match may be a repeated navigation/calendar entry. This is a preview only.
        title = compact(' '.join(a['text'])) or urlparse(url).path.rsplit('/', 1)[-1].replace('-', ' ')
        print('\n%02d | %s | %s | %s' % (index, date.isoformat() if date else 'NO DATE', check, title[:95]))
        print(' URL:', url)
        print(' TIME:', match.group(4) if match and match.group(4) else 'Multiple times' if match and match.group(5) else 'not specified')
        print(' BEFORE:', before[-140:])
        print(' AFTER:', after[:175])
        if date and check == 'weekday matches':
            accepted += 1
    print('\nCANDIDATE MATCHES (first 30):', accepted)
    print('IMPORTANT: Matching weekdays do not independently prove the date belongs to the linked show.')
    print('Diagnostic complete. No event file written or modified.')
except Exception as exc:
    print('Diagnostic error:', type(exc).__name__, str(exc)[:300])
    raise
