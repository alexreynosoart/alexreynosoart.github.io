#!/usr/bin/env python3
"""Read-only Everything Art staging: Wave Hill and Staten Island Museum.
Requires scripts/rule_of_three_source_preview.py (V3). No cache reads/writes.
Python standard library only.
"""
import json
import re
from datetime import date
from html import unescape
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import rule_of_three_source_preview as preview

SOURCES = (
    ('Wave Hill', 'https://www.wavehill.org/calendar', 'Bronx, NY'),
    ('Staten Island Museum', 'https://www.statenislandmuseum.org/events/list/', 'Staten Island, NY'),
)
ART = re.compile(r'\b(art|artist|gallery|exhibit|exhibition|museum|painting|drawing|craft|sculpt|photo|print|workshop|collection|creative|history|making|design|film|lecture|talk|tour)\b', re.I)
EXCLUDE = re.compile(r'\b(yoga|birding|bird and nature walk|hawk watch|garden highlights walk|afternoon tea|owl adventure|kids on the move)\b', re.I)

def category(title):
    if re.search(r'\b(opening|reception|preview)\b', title, re.I): return 'opening'
    if re.search(r'\b(exhibition|exhibit|gallery|collection)\b', title, re.I): return 'exhibition'
    if re.search(r'\b(tour|walking tour|behind the scenes)\b', title, re.I): return 'tour exhibition'
    if re.search(r'\b(talk|lecture|discussion)\b', title, re.I): return 'talk'
    if re.search(r'\b(family|kids|children)\b', title, re.I): return 'family workshop'
    return 'workshop'

def stage(name, url, location):
    req = Request(url, headers={'User-Agent':'EverythingArtEventCollector/1.0 (public calendar staging)', 'Accept':'text/html,application/xhtml+xml'})
    with urlopen(req, timeout=35) as response:
        if response.status != 200 or urlparse(response.url).hostname != urlparse(url).hostname:
            raise ValueError('Unexpected status or redirected domain')
        if 'html' not in response.headers.get('Content-Type','').lower():
            raise ValueError('Expected HTML calendar')
        raw = response.read(preview.MAX_BYTES + 1)
        if len(raw) > preview.MAX_BYTES: raise ValueError('Oversized calendar')
    tree = preview.Tree()
    tree.feed(raw.decode('utf-8', 'replace'))
    candidates = preview.candidates(tree, url, name)
    accepted, rejected, seen = [], [], set()
    for title, start, link, origin, confidence in candidates:
        title = ' '.join(unescape(title).replace('\xa0', ' ').split())
        reason = None
        if not title or start < date.today(): reason = 'expired or missing title'
        elif EXCLUDE.search(title): reason = 'not primarily an art event'
        elif not ART.search(title): reason = 'art relevance not established by title'
        elif urlparse(link).hostname != urlparse(url).hostname: reason = 'unexpected link domain'
        elif (title.casefold(), start.isoformat(), link) in seen: reason = 'duplicate'
        if reason:
            rejected.append((title, reason))
            continue
        seen.add((title.casefold(), start.isoformat(), link))
        item = dict(title=title, description='', date=start.isoformat(), endDate=start.isoformat(),
                    venue=name, location=location, type=category(title), features='nyc us',
                    country='United States', url=link, source=name, free=False)
        # Schema check against the fields used by the existing collector.
        assert all(k in item for k in ('title','description','date','endDate','venue','location','type','features','country','url','source','free'))
        accepted.append(item)
    return len(raw), len(candidates), accepted, rejected

def main():
    print('RULE OF THREE: EVENT SCHEMA STAGING, READ-ONLY', flush=True)
    total = 0
    for name, url, location in SOURCES:
        print(f'\n=== {name} ===', flush=True)
        try:
            size, count, accepted, rejected = stage(name, url, location)
        except Exception as exc:
            print(f'FAILED: {type(exc).__name__}: {exc}', flush=True)
            return 1
        print(f'HTTP 200 | bytes={size} | candidates={count} | accepted={len(accepted)} | rejected={len(rejected)}', flush=True)
        for item in accepted:
            print('STAGED ' + json.dumps(item, ensure_ascii=False), flush=True)
        for title, reason in rejected:
            print(f'REJECTED {title!r}: {reason}', flush=True)
        total += len(accepted)
    print(f'\nSTAGED TOTAL: {total} records (NOT published)', flush=True)
    print('No event cache read or written. Production collector unchanged.', flush=True)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
