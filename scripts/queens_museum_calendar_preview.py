#!/usr/bin/env python3
"""Everything Art | Queens Museum calendar investigation (READ ONLY).

Run from repository root:
    python scripts/queens_museum_calendar_preview.py

This diagnostic NEVER edits the event cache and NEVER publishes events.
Only official queensmuseum.org URLs are requested. No login or bypasses.
"""
import datetime as dt
import html
from html.parser import HTMLParser
import json
import re
import urllib.error
import urllib.parse
import urllib.request

URL = 'https://queensmuseum.org/calendar/'
MAX_BYTES = 7_000_000
MONTHS = r'January|February|March|April|May|June|July|August|September|October|November|December'
DATE_PATTERN = re.compile(r'\b(?:' + MONTHS + r')\s+\d{1,2}(?:,?\s+20\d{2})?\b', re.I)
ISO_PATTERN = re.compile(r'\b20\d{2}-\d{2}-\d{2}\b')


def tidy(s):
    return re.sub(r'\s+', ' ', html.unescape(str(s))).strip()


class CalendarReader(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.stack = []
        self.text = []
        self.scripts = []
        self._script = None
        self._anchor = None
        self._hidden = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('style', 'noscript'):
            self._hidden += 1
        if tag == 'script':
            self._script = {'type': a.get('type', ''), 'id': a.get('id', ''), 'text': []}
        if tag == 'a' and self._anchor is None:
            self._anchor = {'href': a.get('href', ''), 'text': []}
        if tag in ('p', 'li', 'h1', 'h2', 'h3', 'h4', 'time', 'article', 'div', 'section', 'br'):
            self.text.append('\n')
        if tag == 'time':
            value = a.get('datetime', '')
            if value:
                self.text.append(' ' + value + ' ')

    def handle_data(self, data):
        if self._script is not None:
            self._script['text'].append(data)
            return
        if self._hidden:
            return
        self.text.append(data + ' ')
        if self._anchor is not None:
            self._anchor['text'].append(data)

    def handle_endtag(self, tag):
        if tag == 'script' and self._script is not None:
            self._script['text'] = ''.join(self._script['text'])
            self.scripts.append(self._script)
            self._script = None
        if tag == 'a' and self._anchor is not None:
            self.links.append((self._anchor['href'], tidy(' '.join(self._anchor['text']))))
            self._anchor = None
        if tag in ('style', 'noscript'):
            self._hidden = max(0, self._hidden - 1)
        if tag in ('p', 'li', 'h1', 'h2', 'h3', 'h4', 'time', 'article', 'div', 'section'):
            self.text.append('\n')


def main():
    request = urllib.request.Request(URL, headers={
        'User-Agent': 'EverythingArtEventCollector/1.0 (alexreynosoart.com)',
        'Accept': 'text/html,application/xhtml+xml',
    })
    try:
        with urllib.request.urlopen(request, timeout=35) as response:
            host = urllib.parse.urlparse(response.geturl()).hostname or ''
            if host not in ('queensmuseum.org', 'www.queensmuseum.org'):
                print('STOP: unexpected redirect destination'); return 1
            raw = response.read(MAX_BYTES + 1)
            print('Queens Museum: HTTP', response.status)
            print('Content-Type:', response.headers.get('Content-Type', 'unknown'))
            print('Bytes read:', len(raw), '| cap:', MAX_BYTES)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        print('Queens Museum: request unavailable:', str(exc)[:180]); return 0
    if len(raw) > MAX_BYTES:
        print('STOP: HTML exceeds safety cap; no assumptions about incomplete page'); return 0
    content = raw.decode('utf-8', 'replace')
    parser = CalendarReader()
    parser.feed(content)
    visible = tidy(' '.join(parser.text))
    print('Visible text characters:', len(visible))
    print('Script blocks:', len(parser.scripts))
    print('Natural-language date occurrences:', len(DATE_PATTERN.findall(visible)))
    print('ISO date occurrences in HTML:', len(ISO_PATTERN.findall(content)))
    print('Visible date examples:', DATE_PATTERN.findall(visible)[:12])

    links = []
    seen = set()
    for href, label in parser.links:
        absolute = urllib.parse.urljoin(URL, href).split('#')[0]
        parts = urllib.parse.urlparse(absolute)
        if parts.scheme != 'https' or parts.hostname not in ('queensmuseum.org', 'www.queensmuseum.org'):
            continue
        if not re.search(r'/(calendar|event|events|exhibition|exhibitions)/', parts.path, re.I):
            continue
        if absolute in seen or not label or len(label) > 160:
            continue
        seen.add(absolute)
        links.append((label, absolute))
    print('Official calendar/event/exhibition links:', len(links))
    for label, link in links[:15]:
        print(' LINK:', label[:90], '|', link)

    for item in parser.scripts:
        if item['type'].lower() != 'application/ld+json':
            continue
        try:
            data = json.loads(item['text'])
            print('JSON-LD block parsed:', str(data)[:200])
        except (ValueError, TypeError):
            print('JSON-LD block present but invalid')

    markers = ['__NEXT_DATA__', '__NUXT__', 'wp-block', 'tribe-events', 'eventDate', 'startDate', 'datePublished', 'calendar']
    print('HTML framework/event markers:', {m: content.lower().count(m.lower()) for m in markers})
    print('PREVIEW ONLY: 0 events published; data/art-events.json untouched.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
