#!/usr/bin/env python3
"""Everything Art: READ-ONLY deep diagnostic for BRIC and Film at Lincoln Center.
Standard library only. No writes, no changes to published event data.
"""
import html
import json
import re
from datetime import date
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

TODAY = date.today()
SITES = {
    'BRIC': [
        'https://bricartsmedia.org/events/',
        'https://bricartsmedia.org/events/calendar/',
        'https://bricartsmedia.org/event/jazzfest-2026/',
        'https://bricartsmedia.org/event/reel-sisters-bric-present-an-evening-of-staged-script-readings-2026/',
        'https://bricartsmedia.org/event/bric-the-immigrant-artist-biennial-present-memories-of-disruption/',
    ],
    'Film at Lincoln Center': [
        'https://www.filmlinc.org/',
        'https://www.filmlinc.org/now-playing/?tab=films&filters=true',
        'https://www.filmlinc.org/films/the-devils/',
        'https://www.filmlinc.org/films/once-upon-a-time-in-harlem/',
        'https://www.filmlinc.org/films/fatherland/',
    ],
}
DATE_PATTERN = re.compile(
    r'\b(?:20\d{2}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)?'
    r'|(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+20\d{2})?'
    r'|\d{1,2}/\d{1,2}/20\d{2})\b', re.I)

class Inspector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = []
        self.in_title = False
        self.metas = []
        self.times = []
        self.in_time = False
        self.time_text = []
        self.scripts = []
        self.in_jsonld = False
        self.current_script = []
        self.headings = []
        self.in_heading = False
        self.heading_text = []
        self.links = []
        self.visible = []
        self.skip = 0
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'title': self.in_title = True
        if tag == 'meta':
            key = a.get('property') or a.get('name') or a.get('itemprop') or ''
            value = a.get('content') or ''
            if key and value and re.search(r'title|date|time|description|start|end|event', key, re.I):
                self.metas.append((key, value[:220]))
        if tag == 'time':
            self.in_time = True
            if a.get('datetime'): self.times.append(('datetime', a['datetime']))
        if tag in ('h1', 'h2'):
            self.in_heading = True; self.heading_text = []
        if tag == 'a' and a.get('href'):
            self.links.append(a['href'])
        if tag in ('script', 'style'):
            self.skip += 1
            if tag == 'script' and 'ld+json' in a.get('type', '').lower():
                self.in_jsonld = True; self.current_script = []
    def handle_endtag(self, tag):
        if tag == 'title': self.in_title = False
        if tag == 'time': self.in_time = False
        if tag in ('h1', 'h2') and self.in_heading:
            v = ' '.join(''.join(self.heading_text).split())
            if v: self.headings.append(v[:180])
            self.in_heading = False
        if tag == 'script' and self.in_jsonld:
            self.scripts.append(''.join(self.current_script))
            self.in_jsonld = False
        if tag in ('script', 'style'):
            self.skip = max(0, self.skip - 1)
    def handle_data(self, data):
        if self.in_title: self.title.append(data)
        if self.in_time: self.time_text.append(data)
        if self.in_heading: self.heading_text.append(data)
        if self.in_jsonld: self.current_script.append(data)
        if not self.skip: self.visible.append(data)

def walk_json(value, found):
    if isinstance(value, list):
        for v in value: walk_json(v, found)
    elif isinstance(value, dict):
        typ = value.get('@type', '')
        if isinstance(typ, list): typ = ', '.join(map(str, typ))
        if 'Event' in str(typ) or any(k in value for k in ('startDate', 'endDate')):
            found.append({k: str(value[k])[:180] for k in ('@type','name','startDate','endDate','url') if k in value})
        for v in value.values(): walk_json(v, found)

def inspect(url):
    print('\nURL:', url)
    try:
        req = Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; EverythingArtDiagnostic/1.0)', 'Accept': 'text/html'})
        with urlopen(req, timeout=22) as response:
            content = response.read(2_000_000)
            status = response.status
            final = response.url
        page = content.decode('utf-8', errors='replace')
        p = Inspector(); p.feed(page)
        print('HTTP:', status, '| bytes read:', len(content), '| final:', final)
        print('TITLE:', ' '.join(''.join(p.title).split())[:180])
        print('HEADINGS:', p.headings[:6])
        print('META:', p.metas[:12])
        print('TIME attributes:', p.times[:15])
        visible = ' '.join(' '.join(p.visible).split())
        print('VISIBLE date samples:', list(dict.fromkeys(DATE_PATTERN.findall(visible)))[:18])
        print('RAW HTML date samples:', list(dict.fromkeys(DATE_PATTERN.findall(page)))[:18])
        print('JSON-LD blocks:', len(p.scripts))
        events = []
        for raw in p.scripts:
            try: walk_json(json.loads(raw), events)
            except (ValueError, TypeError): pass
        print('JSON-LD Event objects:', events[:8])
        # Print context around a few visible dates to tell if dates attach to specific events.
        contexts = []
        for match in list(DATE_PATTERN.finditer(visible))[:8]:
            contexts.append(visible[max(0, match.start()-90):match.end()+110])
        print('VISIBLE date context:')
        for context in contexts: print('  -', context[:260])
        # Distinguish film pages with a showtime from generic release or copyright dates.
        hints = ['showtime', 'screening', 'tickets', 'event-date', 'startdate', 'datetime', 'calendar', 'schedule']
        print('HTML hint counts:', {h: len(re.findall(re.escape(h), page, re.I)) for h in hints})
        print('Same-site event/film links:', len([u for u in p.links if '/event/' in u or '/films/' in u]))
    except (HTTPError, URLError, TimeoutError, OSError) as e:
        print('ERROR:', type(e).__name__, str(e)[:220])
    except Exception as e:
        print('PARSE ERROR:', type(e).__name__, str(e)[:220])

if __name__ == '__main__':
    print('Everything Art | READ-ONLY deep event date diagnostic |', TODAY)
    print('No files will be written. This is not the live collector.')
    for name, urls in SITES.items():
        print('\n' + '=' * 72 + '\n' + name + '\n' + '=' * 72)
        for url in urls: inspect(url)
    print('\nDiagnostic complete. No event files changed.')
