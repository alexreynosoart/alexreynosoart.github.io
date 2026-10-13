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

def category(title, link):
    context = (title + ' ' + urlparse(link).path.replace('-', ' ')).lower()
    if re.search(r'\b(opening|reception|preview)\b', context): return 'opening'
    if 'family art project' in context: return 'family workshop'
    if re.search(r'\b(tour|walking tour|behind the scenes)\b', context): return 'tour'
    if 'workshop' in context and 'talk' in context: return 'workshop talk'
    if re.search(r'\b(talk|lecture|discussion)\b', context): return 'talk'
    if re.search(r'\b(exhibition|exhibit|gallery|collection)\b', context): return 'exhibition'
    return 'workshop'

def art_context(title, link):
    # Official event-path words can restore context removed from a display title.
    path = urlparse(link).path.lower().replace('-', ' ')
    return bool(ART.search(title) or
                'family art project' in path or
                ('stephanie dinkins' in path and 'preview' in path))


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
        elif not art_context(title, link): reason = 'art relevance not established by title or official event path'
        elif urlparse(link).hostname != urlparse(url).hostname: reason = 'unexpected link domain'
        elif (title.casefold(), start.isoformat(), link) in seen: reason = 'duplicate'
        if reason:
            rejected.append((title, reason))
            continue
        seen.add((title.casefold(), start.isoformat(), link))
        item = dict(title=title, description='', date=start.isoformat(), endDate=start.isoformat(),
                    venue=name, location=location, type=category(title, link), features='nyc us',
                    country='United States', url=link, source=name, free=False)
        # Schema check against the fields used by the existing collector.
        assert all(k in item for k in ('title','description','date','endDate','venue','location','type','features','country','url','source','free'))
        accepted.append(item)
    return len(raw), len(candidates), accepted, rejected


def stage_smithsonian():
    """Read-only Smithsonian candidates, verified from official detail pages."""
    from datetime import datetime
    import time
    base = 'https://smithsonianassociates.org/ticketing/online/'
    req = Request(base, headers={'User-Agent': 'EverythingArtEventCollector/1.0 (read-only staging)', 'Accept': 'text/html'})
    with urlopen(req, timeout=35) as response:
        if response.status != 200 or urlparse(response.url).hostname != urlparse(base).hostname:
            raise ValueError('Smithsonian listing response not trusted')
        raw = response.read(preview.MAX_BYTES + 1)
        if len(raw) > preview.MAX_BYTES: raise ValueError('Smithsonian listing too large')
    tree = preview.Tree()
    tree.feed(raw.decode('utf-8', 'replace'))
    discovered = preview.smithsonian_detail_candidates(tree, base)
    accepted, held = [], []
    for title, start, link, origin, confidence in discovered:
        # Reopen the official detail page to capture the complete course range.
        time.sleep(preview.SMITHSONIAN_DELAY_SECONDS)
        try:
            request = Request(link, headers={'User-Agent': 'EverythingArtEventCollector/1.0 (read-only staging)', 'Accept': 'text/html'})
            with urlopen(request, timeout=20) as response:
                if response.status != 200 or urlparse(response.url).hostname != 'smithsonianassociates.org':
                    raise ValueError('Untrusted detail response')
                content = response.read(preview.MAX_BYTES + 1)
                if len(content) > preview.MAX_BYTES: raise ValueError('Oversized detail')
            detail = preview.Tree()
            detail.feed(content.decode('utf-8', 'replace'))
            main = next((node for node in preview.walk(detail.root) if node.tag == 'main'), None)
            if main is None: raise ValueError('Missing main section')
            headings = [n.text().strip() for n in preview.walk(main) if n.tag == 'h1' and n.text().strip()]
            if not headings or headings[0] != title: raise ValueError('Title mismatch')
            body = main.text()[:20000]
            if not preview.ONLINE_WORDS.search(body):
                raise ValueError('Online attendance unverified')
            time_dates = [preview.event_date(n.attrs.get('datetime')) for n in preview.walk(main)
                          if n.tag == 'time' and n.attrs.get('datetime')]
            time_dates = [d for d in time_dates if d and d >= date.today()]
            date_strings = re.findall(r'\\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\\.?\\s+\\d{1,2},?\\s+20\\d{2}\\b', body, re.I)
            body_dates = [preview.human_date(value) for value in date_strings]
            body_dates = [d for d in body_dates if d and d >= date.today()]
            dates = sorted(set(time_dates or body_dates))
            if not dates or dates[0] != start: raise ValueError('Date mismatch')
            course = len(dates) > 1
            description = (f'Online course, {len(dates)} listed session dates. '
                           if course else 'Online Smithsonian Associates program. ')
            if course:
                description += f'First session {dates[0].isoformat()}, last listed session {dates[-1].isoformat()}. '
            description += 'Check the official program page for registration, schedule and attendance details.'
            accepted.append(dict(title=title, description=description[:360],
                date=dates[0].isoformat(), endDate=dates[-1].isoformat(),
                venue='Smithsonian Associates', location='Online', type='workshop' if course else 'talk',
                features='online us', country='United States', url=link,
                source='Smithsonian Associates', free=False))
        except (OSError, ValueError, TimeoutError) as exc:
            held.append((title, str(exc)[:130]))
    return len(discovered), accepted, held

def main():
    import sys
    if '--smithsonian' in sys.argv:
        print('RULE OF THREE: SMITHSONIAN ONLINE STAGING, READ-ONLY', flush=True)
        try:
            discovered, accepted, held = stage_smithsonian()
        except Exception as exc:
            print(f'FAILED: {type(exc).__name__}: {exc}', flush=True)
            return 1
        print(f'Smithsonian candidates={discovered}; staged={len(accepted)}; held={len(held)}')
        for item in accepted:
            print('STAGED ' + json.dumps(item, ensure_ascii=False), flush=True)
        for title, reason in held:
            print(f'HELD {title!r}: {reason}', flush=True)
        print('PREVIEW ONLY: no event cache read or written.')
        return 0
    print('RULE OF THREE: CONTEXT-AWARE EVENT STAGING V2, READ-ONLY', flush=True)
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
