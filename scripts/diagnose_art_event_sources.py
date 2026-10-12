#!/usr/bin/env python3
"""Read-only NYPL exhibition detail diagnostic for Everything Art.

Run using the existing manual diagnostic GitHub Action. No files are written.
"""
import html
import json
import re
import urllib.error
import urllib.request
from html.parser import HTMLParser

URLS = [
    'https://www.nypl.org/events/exhibitions/silly-old-bear-winnie-pooh-100',
    'https://www.nypl.org/events/exhibitions/martha-graham-mother-psychological-dance',
    'https://www.nypl.org/events/exhibitions/forging-ahead',
]
DATE_PATTERN = re.compile(
    r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)'
    r'\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+20\d{2})?'
    r'|\b20\d{2}-\d{2}-\d{2}\b', re.I)

class Inspect(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = []
        self.meta = []
        self.jsonld = []
        self.next_data = []
        self.text = []
        self.active = None
        self.buf = []
        self.in_hidden = 0
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('script', 'style'):
            self.in_hidden += 1
            if tag == 'script' and (a.get('type') == 'application/ld+json' or a.get('id') == '__NEXT_DATA__'):
                self.active = 'jsonld' if a.get('type') == 'application/ld+json' else 'next'
                self.buf = []
        elif tag == 'title':
            self.active = 'title'; self.buf = []
        elif tag == 'meta':
            name = a.get('name') or a.get('property') or a.get('itemprop') or ''
            if any(w in name.lower() for w in ('date', 'time', 'title', 'description')):
                self.meta.append((name, a.get('content', '')[:200]))
    def handle_data(self, data):
        if self.active:
            self.buf.append(data)
        elif not self.in_hidden:
            self.text.append(data)
    def handle_endtag(self, tag):
        if tag == 'script':
            if self.active in ('jsonld', 'next'):
                value = ''.join(self.buf)
                (self.jsonld if self.active == 'jsonld' else self.next_data).append(value)
                self.active = None; self.buf = []
            self.in_hidden = max(0, self.in_hidden - 1)
        elif tag == 'style':
            self.in_hidden = max(0, self.in_hidden - 1)
        elif tag == 'title' and self.active == 'title':
            self.title.append(''.join(self.buf).strip()); self.active = None; self.buf = []

def relevant_json(node, path='$', out=None, limit=24):
    if out is None: out = []
    if len(out) >= limit: return out
    if isinstance(node, dict):
        for k, v in node.items():
            p = path + '.' + str(k)
            if re.search(r'date|start|end|exhibit|event|title', str(k), re.I) and isinstance(v, (str, int, float)):
                out.append((p, str(v)[:160]))
                if len(out) >= limit: break
            if isinstance(v, (dict, list)): relevant_json(v, p, out, limit)
            if len(out) >= limit: break
    elif isinstance(node, list):
        for i, v in enumerate(node[:100]):
            if isinstance(v, (dict, list)): relevant_json(v, path + f'[{i}]', out, limit)
            if len(out) >= limit: break
    return out

for url in URLS:
    print('\n=== ' + url + ' ===', flush=True)
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; EverythingArtEventDiagnostic/1.0; +https://alexreynosoart.com)',
            'Accept': 'text/html,application/xhtml+xml',
        })
        with urllib.request.urlopen(req, timeout=25) as response:
            raw = response.read(2_000_000).decode('utf-8', 'replace')
            print('HTTP:', response.status, 'HTML chars:', len(raw))
        parser = Inspect(); parser.feed(raw)
        print('TITLE:', parser.title[:1])
        print('META date/title/description fields:', parser.meta[:12])
        print('JSON-LD blocks:', len(parser.jsonld), 'NEXT_DATA blocks:', len(parser.next_data))
        for label, blocks in [('JSON-LD', parser.jsonld), ('NEXT_DATA', parser.next_data)]:
            for index, block in enumerate(blocks[:2]):
                try:
                    obj = json.loads(block)
                    print(label, index, 'candidate fields:', relevant_json(obj))
                except ValueError:
                    print(label, index, 'invalid JSON; length:', len(block))
        visible = re.sub(r'\s+', ' ', html.unescape(' '.join(parser.text))).strip()
        matches = list(DATE_PATTERN.finditer(visible))
        print('VISIBLE DATE MATCHES:', len(matches))
        for m in matches[:12]:
            print('DATE CONTEXT:', visible[max(0, m.start()-90):m.end()+100])
        if not matches:
            print('No visible date strings detected with this limited pattern.')
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        print('ERROR:', type(exc).__name__, str(exc)[:250])
print('\nRead-only exhibition detail diagnostic complete. No files changed.')
