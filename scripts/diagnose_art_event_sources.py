#!/usr/bin/env python3
"""READ-ONLY extraction probe for Bronx Museum and Creative Time.

Run: python scripts/diagnose_art_event_sources.py
Prints candidate records only. Never writes data/art-events.json.
"""
import datetime as dt
import html
from html.parser import HTMLParser
import re
import urllib.request
from urllib.parse import urljoin, urlparse

TODAY = dt.date.today()
MONTHS = {name: i for i, name in enumerate(
    'January February March April May June July August September October November December'.split(), 1)}
MONTH_PATTERN = '|'.join(MONTHS)
DATE_PATTERN = re.compile(rf'\b({MONTH_PATTERN})\s+(\d{{1,2}}),?\s+(20\d{{2}})\b', re.I)
RANGE_PATTERN = re.compile(rf'\b({MONTH_PATTERN})\s+(\d{{1,2}}),?\s+(20\d{{2}})\s*[–—-]\s*({MONTH_PATTERN})\s+(\d{{1,2}}),?\s+(20\d{{2}})\b', re.I)

class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.text = []
        self.title = []
        self.in_title = False
        self.hidden = 0
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('script', 'style', 'noscript'):
            self.hidden += 1
        if tag == 'title':
            self.in_title = True
        if tag == 'a' and a.get('href'):
            self.links.append((a['href'], len(self.text)))
    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript'):
            self.hidden = max(0, self.hidden - 1)
        if tag == 'title':
            self.in_title = False
    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)
        elif not self.hidden and data.strip():
            self.text.append(html.unescape(data.strip()))

def get(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; EverythingArtEventCollector/1.1; +https://alexreynosoart.com)',
        'Accept': 'text/html,application/xhtml+xml'})
    with urllib.request.urlopen(req, timeout=25) as response:
        raw = response.read(2_000_000).decode('utf-8', 'replace')
    parser = Page()
    parser.feed(raw)
    return parser

def iso(month, day, year):
    return dt.date(int(year), MONTHS[month.capitalize()], int(day))

def dates_near(text):
    """Candidates only. Dates must be checked against detail-page meaning."""
    ranges = []
    for match in RANGE_PATTERN.finditer(text):
        a = iso(*match.groups()[:3]); b = iso(*match.groups()[3:])
        if b >= TODAY:
            ranges.append((a.isoformat(), b.isoformat(), text[max(0, match.start()-90):match.end()+90]))
    singles = []
    for match in DATE_PATTERN.finditer(text):
        d = iso(*match.groups())
        if d >= TODAY:
            singles.append((d.isoformat(), text[max(0, match.start()-90):match.end()+90]))
    return ranges, singles

def inspect(name, index, allowed_prefix, limit=8):
    print(f'\n=== {name} ===')
    try:
        listing = get(index)
    except Exception as exc:
        print('INDEX ERROR:', type(exc).__name__, str(exc)[:200]); return
    links = []
    for href, _ in listing.links:
        absolute = urljoin(index, href).split('#', 1)[0].split('?', 1)[0]
        if urlparse(absolute).netloc == urlparse(index).netloc and allowed_prefix in urlparse(absolute).path:
            if absolute not in links: links.append(absolute)
    print('Candidate detail links:', len(links))
    for link in links[:limit]:
        try:
            page = get(link)
            title = ' '.join(page.title).split('|')[0].strip()
            visible = ' '.join(page.text)
            ranges, singles = dates_near(visible[:12000])
            print('\nTITLE:', title[:130]); print('URL:', link)
            print('DATE RANGES:', [(a,b) for a,b,_ in ranges[:3]])
            print('OTHER DATES:', [d for d,_ in singles[:5]])
            for a,b,context in ranges[:1]: print('DATE CONTEXT:', context[:220])
            if not ranges and singles:
                print('DATE CONTEXT:', singles[0][1][:220])
            if not ranges and not singles:
                print('NO FUTURE DATE FOUND: do not publish automatically')
        except Exception as exc:
            print('DETAIL ERROR:', link, type(exc).__name__, str(exc)[:160])

if __name__ == '__main__':
    inspect('Bronx Museum exhibitions', 'https://bronxmuseum.org/exhibitions/', '/exhibition/', 10)
    inspect('Creative Time events', 'https://creativetime.org/events/', '/events/', 10)
    print('\nREAD-ONLY extraction test complete. No files changed.')
