#!/usr/bin/env python3
"""Read-only preview of NYC and ONLINE art-event sources.
No event-cache writes. Python standard library only.
Usage: python scripts/rule_of_three_source_preview.py --online
       python scripts/rule_of_three_source_preview.py --nyc
       python scripts/rule_of_three_source_preview.py --all
"""
import argparse
import json
import re
import time
from datetime import date, datetime
from html import unescape
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

NYC_SOURCES = [
    ('Wave Hill', 'https://www.wavehill.org/calendar'),
    ('Staten Island Museum', 'https://www.statenislandmuseum.org/events/list/'),
    ('Bronx Council on the Arts', 'https://www.bronxarts.org/events/'),
]
ONLINE_SOURCES = [
    ('Smithsonian Associates', 'https://smithsonianassociates.org/ticketing/online/'),
    ('National Gallery of Art (DC)', 'https://www.nga.gov/calendar'),
    ('National Gallery (London)', 'https://www.nationalgallery.org.uk/learning/courses'),
]
DATE = re.compile(r'\b20\d{2}-\d{2}-\d{2}\b|\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+\d{1,2}(?:,?\s+20\d{2})?\b', re.I)
BAD = re.compile(r'^(?:home|events?|calendar|learn more|read more|view all|more info|details|menu|skip to|next|previous|visit|about|discover|education|support|exhibitions?)$', re.I)
ONLINE_WORDS = re.compile(r'\b(?:online|virtual|webinar|livestream|live.stream|zoom|webcast|remote)\b', re.I)
MAX_BYTES = 4_000_000

class Node:
    def __init__(self, tag='', attrs=None, parent=None):
        self.tag, self.attrs, self.parent = tag, dict(attrs or []), parent
        self.children, self.bits = [], []
    def text(self):
        return ' '.join(' '.join(self.bits).split())

class Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node('root')
        self.stack = [self.root]
        self.jsonld = []
        self.in_ld = False
        self.ld_bits = []
    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.stack[-1])
        self.stack[-1].children.append(node)
        if tag == 'script' and 'ld+json' in node.attrs.get('type', '').lower():
            self.in_ld, self.ld_bits = True, []
        if tag not in ('meta', 'link', 'img', 'br', 'hr', 'input', 'source', 'area', 'embed', 'wbr'):
            self.stack.append(node)
    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if self.stack[-1].tag == tag:
            self.stack.pop()
    def handle_endtag(self, tag):
        if tag == 'script' and self.in_ld:
            self.jsonld.append(''.join(self.ld_bits))
            self.in_ld = False
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return
    def handle_data(self, data):
        if self.in_ld:
            self.ld_bits.append(data)
        if any(n.tag in ('script', 'style', 'noscript') for n in self.stack):
            return
        for n in self.stack:
            n.bits.append(data)

def walk(node):
    yield node
    for child in node.children:
        yield from walk(child)

def event_json(obj):
    if isinstance(obj, list):
        for item in obj:
            yield from event_json(item)
    elif isinstance(obj, dict):
        types = obj.get('@type', [])
        if isinstance(types, str):
            types = [types]
        if any(t.lower().endswith('event') for t in types if isinstance(t, str)):
            yield obj
        for value in obj.values():
            if isinstance(value, (dict, list)):
                yield from event_json(value)

def event_date(raw):
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace('Z', '+00:00')).date()
    except ValueError:
        pass
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None

def human_date(raw):
    parsed = event_date(raw)
    if parsed:
        return parsed
    for fmt in ('%b %d %Y', '%B %d %Y', '%b %d, %Y', '%B %d, %Y'):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            pass
    return None

def clean_title(label, name, link):
    label = unescape(label).replace('\xa0', ' ').strip()
    if name == 'Bronx Council on the Arts':
        slug = urlparse(link).path.rsplit('/', 1)[-1].removesuffix('.html')
        slug = re.sub(r'(?:-20\d{2}-\d{2}-\d{2})+$', '', slug)
        return slug.replace('-', ' ').strip().title(), 'URL-SLUG (unverified)'
    if name == 'Wave Hill':
        label = re.sub(r'\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+20\d{2}.*$', '', label, flags=re.I).strip()
        for prefix in ('Art Talks + Tours ', 'Families Family Art Project: ', 'Families Nature Talks + Tours ', 'Nature Talks + Tours Wellness + Cooking ', 'Gardens Talks + Tours ', 'Special Events ', 'Wellness + Cooking ', 'Talks + Tours '):
            if label.startswith(prefix):
                label = label[len(prefix):]
                break
    return label, 'VISIBLE-HTML'

def candidates(tree, base, name, online=False):
    host = urlparse(base).hostname
    today = date.today()
    results, seen = [], set()
    for script in tree.jsonld:
        try:
            objects = list(event_json(json.loads(script)))
        except (ValueError, TypeError):
            continue
        for item in objects:
            title, rawdate, link = item.get('name', ''), item.get('startDate', ''), item.get('url', '')
            if isinstance(link, dict):
                link = link.get('@id', '')
            if not all(isinstance(v, str) and v for v in (title, rawdate, link)):
                continue
            absolute = urljoin(base, link)
            start = human_date(rawdate)
            if urlparse(absolute).hostname != host or not start or start < today or absolute in seen:
                continue
            confidence = 'VERIFIED-STRUCTURE'
            if online:
                loc = item.get('location', '')
                signal = json.dumps(loc, ensure_ascii=False) + ' ' + str(item.get('eventAttendanceMode', '')) + ' ' + str(item.get('description', '')) + ' ' + title
                if not (ONLINE_WORDS.search(signal) or 'OnlineEventAttendanceMode' in signal):
                    continue
                confidence = 'ONLINE-SIGNAL / VERIFY ATTENDANCE'
            seen.add(absolute)
            results.append((unescape(title), start, absolute, 'JSON-LD', confidence))
    for n in walk(tree.root):
        if n.tag != 'a' or not n.attrs.get('href'):
            continue
        link = urljoin(base, n.attrs['href']).split('#')[0]
        path = urlparse(link).path.rstrip('/')
        if urlparse(link).hostname != host or link in seen:
            continue
        if name == 'Wave Hill' and not path.startswith('/calendar/'):
            continue
        if name == 'Staten Island Museum' and '/event/' not in path:
            continue
        if name == 'Bronx Council on the Arts' and not (path.startswith('/events/') and path.endswith('.html')):
            continue
        label = n.text()[:220].strip()
        if not label or BAD.match(label) or label.lower() == 'submit an event':
            continue
        context = n.parent
        best = None
        signal = ''
        for _ in range(5):
            if context is None:
                break
            times = [x.attrs['datetime'] for x in walk(context) if x.tag == 'time' and x.attrs.get('datetime')]
            dates = DATE.findall(context.text()[:2500])
            if times or dates:
                best = (times or dates)[0]
                signal = context.text()[:2500]
                break
            context = context.parent
        if not best:
            continue
        start = human_date(best)
        if not start or start < today:
            continue
        title, confidence = clean_title(label, name, link)
        if not title or DATE.fullmatch(title):
            continue
        if online:
            # Page-level words alone are not sufficient: require a signal near the link.
            if not ONLINE_WORDS.search(signal):
                continue
            confidence = 'NEARBY ONLINE WORD / UNVERIFIED'
        seen.add(link)
        results.append((title, start, link, 'HTML', confidence))
    return sorted(results, key=lambda row: (row[1], row[0]))

SMITHSONIAN_BATCH_SIZE = 100
SMITHSONIAN_MAX_LIST_PAGES = 24
SMITHSONIAN_DELAY_SECONDS = 0.45
# Verified public Smithsonian art-category pages (official URLs, not guessed API endpoints).
# These are seed listings, never treated as individual events.
SMITHSONIAN_ART_CATEGORY_URLS = [
    'https://smithsonianassociates.org/ticketing/programs/drawing',
    'https://smithsonianassociates.org/ticketing/programs/painting',
    'https://smithsonianassociates.org/ticketing/programs/mixed-media',
    'https://smithsonianassociates.org/ticketing/programs/photography',
    'https://smithsonianassociates.org/ticketing/programs/other-media',
    'https://smithsonianassociates.org/ticketing/programs/art-theory-and-practice',
]
ART_TERMS = re.compile(
    r"\b(?:art|artist|artwork|painting|paint|drawing|sketch|illustrat|"
    r"photograph|sculpt|ceramic|pottery|printmak|watercolor|collage|"
    r"design|architecture|architect|museum|gallery|exhibition|"
    r"craft|textile|weaving|fiber art|mixed media|visual culture|"
    r"art history|film|animation|calligraphy|miniature)\w*\b", re.I
)

SMITHSONIAN_CATEGORY_WORDS = re.compile(
    r'\b(?:art|architecture|drawing|painting|sculpture|photography|mixed media|fiber arts|'
    r'printmaking|ceramics|design|studio arts|craft|illustration|textiles)\b', re.I
)
SMITHSONIAN_DIRECTORY_TITLE = re.compile(
    r'^(?:all upcoming\b|what.s new this month\??$|studio arts: what.s new\??$)', re.I
)

def smithsonian_program_links(tree, base):
    """Collect actual official program URLs; directories are classified later."""
    links = set()
    for node in walk(tree.root):
        if node.tag != 'a' or not node.attrs.get('href'):
            continue
        link = urljoin(base, node.attrs['href']).split('#')[0]
        parsed = urlparse(link)
        if (parsed.hostname == urlparse(base).hostname
                and re.match(r'^/ticketing/programs/[^/]+/?$', parsed.path)
                and parsed.path.rstrip('/') != '/ticketing/programs'):
            links.add(link)
    return links

def smithsonian_listing_links(tree, base):
    """Use only real, linked official listing pages, not speculative endpoints."""
    links = set()
    for node in walk(tree.root):
        if node.tag != 'a' or not node.attrs.get('href'):
            continue
        link = urljoin(base, node.attrs['href']).split('#')[0]
        parsed = urlparse(link)
        if parsed.hostname != urlparse(base).hostname:
            continue
        path = parsed.path.rstrip('/')
        if (path in ('/ticketing/programs', '/ticketing/search', '/ticketing/online')
                or path.startswith('/ticketing/online/')):
            links.add(link)
    return links

def smithsonian_art_directory_links(tree, base):
    """Follow linked 'All upcoming [art category]' cards as directories."""
    links = set()
    for node in walk(tree.root):
        if node.tag != 'a' or not node.attrs.get('href'):
            continue
        label = node.text().strip()
        if not (SMITHSONIAN_DIRECTORY_TITLE.search(label)
                and SMITHSONIAN_CATEGORY_WORDS.search(label)):
            continue
        link = urljoin(base, node.attrs['href']).split('#')[0]
        parsed = urlparse(link)
        if parsed.hostname == urlparse(base).hostname and parsed.path.startswith('/ticketing/'):
            links.add(link)
    return links

def smithsonian_category_diagnostics(tree, base):
    """Print actual category anchor destinations, including JS/data-driven links."""
    found = set()
    for node in walk(tree.root):
        if node.tag != 'a':
            continue
        label = node.text().strip()
        if not (label.lower().startswith('all upcoming') and SMITHSONIAN_CATEGORY_WORDS.search(label)):
            continue
        raw_href = node.attrs.get('href', '')
        extra = {k: v for k, v in node.attrs.items() if k.startswith('data-') or k in ('onclick', 'role')}
        record = (label, raw_href, repr(extra)[:240])
        if record in found:
            continue
        found.add(record)
        print(f'  ART CATEGORY LINK label={label!r} href={raw_href!r} attrs={extra!r}')
    print(f'Smithsonian art category anchor diagnostics: {len(found)} unique links')

def smithsonian_detail_candidates(tree, base):
    """Discover up to 100 official programs; verify dates, online status and art relevance."""
    program_links = smithsonian_program_links(tree, base)
    category_urls = set(SMITHSONIAN_ART_CATEGORY_URLS)
    listing_queue = sorted(category_urls | smithsonian_listing_links(tree, base) | smithsonian_art_directory_links(tree, base))
    print(f'Smithsonian verified art-category seeds: {len(category_urls)}')
    print(f'Smithsonian official listing and art-directory links discovered: {len(listing_queue)}')
    for page in listing_queue[:8]:
        print(f'  DISCOVERED LISTING {page}')
    visited_listings = {base}
    category_program_links = set()
    while listing_queue and len(visited_listings) < SMITHSONIAN_MAX_LIST_PAGES and len(program_links) < SMITHSONIAN_BATCH_SIZE:
        page = listing_queue.pop(0)
        if page in visited_listings:
            continue
        visited_listings.add(page)
        time.sleep(SMITHSONIAN_DELAY_SECONDS)
        try:
            req = Request(page, headers={'User-Agent': 'EverythingArtEventCollector/1.0 (+read-only verification)', 'Accept': 'text/html'})
            with urlopen(req, timeout=15) as response:
                if response.status != 200 or urlparse(response.url).hostname != urlparse(base).hostname:
                    continue
                raw = response.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES or 'html' not in response.headers.get('Content-Type', '').lower():
                    continue
        except (HTTPError, URLError, TimeoutError, OSError):
            continue
        page_tree = Tree()
        page_tree.feed(raw.decode('utf-8', 'replace'))
        if urlparse(page).path.rstrip('/') == '/ticketing/programs':
            smithsonian_category_diagnostics(page_tree, base)
        page_programs = smithsonian_program_links(page_tree, base)
        # Do not count the category's own URL as an event.
        page_programs.discard(page)
        if page.rstrip('/') in {u.rstrip('/') for u in category_urls}:
            category_program_links.update(page_programs)
            print(f'  ART CATEGORY {page}: {len(page_programs)} program links on page')
        new_programs = page_programs - program_links
        print(f'  LISTING {page}: {len(new_programs)} additional program links')
        program_links.update(new_programs)
        listing_queue.extend(sorted((smithsonian_listing_links(page_tree, base) | smithsonian_art_directory_links(page_tree, base)) - visited_listings - set(listing_queue)))
    # Prefer verified art-topic program URLs, rather than spending the 100-item
    # budget on category navigation entries from the program directory.
    # Remove category and directory pages from event-detail checks, then
    # prioritize actual links gathered from the verified art categories.
    program_links.difference_update(category_urls)
    priority = sorted(category_program_links - category_urls)
    links = (priority + sorted(program_links - set(priority)))[:SMITHSONIAN_BATCH_SIZE]
    print(f'Smithsonian category-sourced program links: {len(category_program_links - category_urls)}')
    print(f'Smithsonian official program links discovered: {len(program_links)} across {len(visited_listings)} listing page(s); checking {len(links)} (cap {SMITHSONIAN_BATCH_SIZE})')
    if len(program_links) < SMITHSONIAN_BATCH_SIZE:
        print('DISCOVERY NOTE: Accessible linked listings expose fewer than 100 program links. A dynamic catalog may require a different approved source.')
    approved, held, unrelated = [], 0, 0
    for link in links:
        time.sleep(SMITHSONIAN_DELAY_SECONDS)
        try:
            req = Request(link, headers={'User-Agent': 'EverythingArtEventCollector/1.0 (+read-only verification)', 'Accept': 'text/html'})
            with urlopen(req, timeout=15) as response:
                if response.status != 200 or urlparse(response.url).hostname != urlparse(base).hostname:
                    held += 1
                    continue
                raw = response.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES or 'html' not in response.headers.get('Content-Type', '').lower():
                    held += 1
                    continue
        except (HTTPError, URLError, TimeoutError, OSError):
            held += 1
            continue
        detail = Tree()
        detail.feed(raw.decode('utf-8', 'replace'))
        main = next((n for n in walk(detail.root) if n.tag == 'main'), None)
        if main is None:
            held += 1
            print(f'  HOLD no main content: {link}')
            continue
        headings = [n.text().strip() for n in walk(main) if n.tag == 'h1' and n.text().strip()]
        title = headings[0] if headings else ''
        body = main.text()[:20000]
        if re.search(r'(?:this program is over|registration for this program is now closed)', body[:1800], re.I):
            held += 1
            print(f'  HOLD closed or past registration: {title!r}')
            continue
        if not title or len(title) > 180 or SMITHSONIAN_DIRECTORY_TITLE.search(title) or title.lower().startswith('programs'):
            held += 1
            print(f'  HOLD invalid event title: {title!r}')
            continue
        # Require a meaningful art signal in the title or a strong art-specific
        # phrase in the event body; generic words elsewhere in navigation are not enough.
        strong_body_art = re.search(r'\b(?:art history|visual arts?|fine arts?|studio art|art museum|art exhibition|painting workshop|drawing workshop|photography workshop|architecture lecture|design history|craft workshop)\b', body[:2500], re.I)
        if not ART_TERMS.search(title) and not strong_body_art:
            unrelated += 1
            print(f'  SKIP not clearly art-related: {title!r}')
            continue
        time_dates = [event_date(n.attrs.get('datetime')) for n in walk(main)
                      if n.tag == 'time' and n.attrs.get('datetime')]
        time_dates = [d for d in time_dates if d and d >= date.today()]
        date_strings = re.findall(r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+\d{1,2},?\s+20\d{2}\b', body, re.I)
        body_dates = [human_date(d) for d in date_strings]
        body_dates = [d for d in body_dates if d and d >= date.today()]
        dates = sorted(set(time_dates or body_dates))
        if not dates:
            held += 1
            print(f'  HOLD no verified future date: {title!r}')
            continue
        online = bool(re.search(r'\b(?:online program|online lecture|online class|online workshop|virtual program|virtual event|via zoom|on zoom|livestream|live stream|webinar)\b', body, re.I))
        if not online:
            held += 1
            print(f'  HOLD online attendance unverified: {title!r}')
            continue
        if len(dates) > 1:
            # A course is one listing, not one duplicate per meeting.
            # Keep its start date for downstream preview compatibility, and
            # display the end date here for explicit human review.
            approved.append((title, dates[0], link, 'DETAIL PAGE / COURSE', 'MULTI-SESSION / MANUAL REVIEW'))
            print(f'  COURSE CANDIDATE title={title!r} | starts={dates[0]} | ends={dates[-1]} | sessions={len(dates)} | url={link}')
            continue
        approved.append((title, dates[0], link, 'DETAIL PAGE', 'DATE + ONLINE + ART SCREENED'))
        print(f'  CANDIDATE title={title!r} | date={dates[0]} | url={link}')
    print(f'Smithsonian art-screened preview: {len(approved)} candidates; {held} held; {unrelated} unrelated; READ-ONLY')
    print('ART SCREEN CAUTION: Keyword matching is preliminary; course end dates and session counts need manual review.')
    print('DISCOVERY CAUTION: Six verified official art-category URLs are seeded directly; individual dates, registration and online status still require review.')
    return approved

def inspect(name, url, online=False):
    print(f'\n=== {name} ===', flush=True)
    req = Request(url, headers={'User-Agent': 'EverythingArtEventCollector/1.0 (+public calendar preview)', 'Accept': 'text/html,application/xhtml+xml'})
    try:
        with urlopen(req, timeout=35) as response:
            final, status = response.url, response.status
            kind = response.headers.get('Content-Type', '')
            raw = response.read(MAX_BYTES+1)
    except HTTPError as e:
        print(f'HTTP {e.code}: unavailable; 0 records approved')
        return
    except (URLError, TimeoutError, OSError) as e:
        print(f'Fetch failed: {type(e).__name__}: {e}')
        return
    print(f'HTTP {status} | bytes {len(raw)} | {kind}')
    if urlparse(final).hostname != urlparse(url).hostname or len(raw) > MAX_BYTES or 'html' not in kind.lower():
        print('Safety guard: unexpected response; skipping')
        return
    tree = Tree()
    tree.feed(raw.decode('utf-8', 'replace'))
    found = (smithsonian_detail_candidates(tree, final)
             if name == 'Smithsonian Associates' and online
             else candidates(tree, final, name, online=online))
    print(f'JSON-LD blocks: {len(tree.jsonld)} | event-level candidate links: {len(found)}')
    for title, start, link, origin, confidence in found[:15]:
        print(f'  [{origin} / {confidence}] title={title!r} | date={start.isoformat()} | url={link}')
    print(f'Preview count: {len(found)} future candidates; no publication approval implied')
    if online:
        print('ONLINE CAUTION: Only Smithsonian detail-page checks are strengthened in this version; other online sources remain exploratory.')
    print('PREVIEW ONLY. Candidate records require date/title/link review before publication.')



# ===== INDEPENDENT STAGING ADAPTER =====
import json
import re
from datetime import date
from html import unescape
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import sys
# This file includes the known-good preview parser to avoid version mismatch.
preview = sys.modules[__name__]

# Independent response-size guard; do not depend on preview module constants.
MAX_BYTES = 4_000_000

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
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES: raise ValueError('Oversized calendar')
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


# Manually reviewed program IDs. A positive discovery result alone is not approval.
# Review these again when the Smithsonian catalog changes.
SMITHSONIAN_APPROVED_SLUGS = frozenset({
    'art-of-surviving-belle-isle',
    'artists-travels-north-africa',
    'make-it-miniature-big-ideas-in-small-formats',
    'art-of-floral-design',
    'drawing-light-and-how-masters-did-it-in-color',
    'van-goghs-toolbox-techniques-in-drawing',
    'mixed-media-art-warmups',
    'jazz-it-up-holiday-cards-pointed-pen-calligraphy',
    'takuga-botanical-prints',
})
SMITHSONIAN_EXCLUDED_SLUGS = frozenset({
    'night-photography-in-washington-d-c',  # requires in-person participation
    'crafting-witches',  # primarily history, not visual-art instruction
})
# Official class start dates reviewed separately from registration deadlines.
SMITHSONIAN_START_OVERRIDES = {
    'jazz-it-up-holiday-cards-pointed-pen-calligraphy': date(2026, 12, 5),
    'takuga-botanical-prints': date(2026, 12, 5),
}

def stage_smithsonian():
    """Read-only Smithsonian candidates, verified from official detail pages."""
    from datetime import datetime
    import time
    base = 'https://smithsonianassociates.org/ticketing/online/'
    req = Request(base, headers={'User-Agent': 'EverythingArtEventCollector/1.0 (read-only staging)', 'Accept': 'text/html'})
    with urlopen(req, timeout=35) as response:
        if response.status != 200 or urlparse(response.url).hostname != urlparse(base).hostname:
            raise ValueError('Smithsonian listing response not trusted')
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES: raise ValueError('Smithsonian listing too large')
    tree = preview.Tree()
    tree.feed(raw.decode('utf-8', 'replace'))
    discovered = preview.smithsonian_detail_candidates(tree, base)
    accepted, held = [], []
    for title, start, link, origin, confidence in discovered:
        slug = urlparse(link).path.rstrip('/').split('/')[-1]
        if slug in SMITHSONIAN_EXCLUDED_SLUGS:
            held.append((title, 'excluded: in-person requirement or not primarily visual art'))
            continue
        if slug not in SMITHSONIAN_APPROVED_SLUGS:
            held.append((title, 'not on manually reviewed Smithsonian art shortlist'))
            continue
        if start <= date.today():
            # Same-day listings lack a verified local start time. Do not publish
            # an event that might already have finished.
            held.append((title, 'same-day or expired; start time not independently verified'))
            continue
        # Reopen the official detail page to capture the complete course range.
        time.sleep(preview.SMITHSONIAN_DELAY_SECONDS)
        try:
            request = Request(link, headers={'User-Agent': 'EverythingArtEventCollector/1.0 (read-only staging)', 'Accept': 'text/html'})
            with urlopen(request, timeout=20) as response:
                if response.status != 200 or urlparse(response.url).hostname != 'smithsonianassociates.org':
                    raise ValueError('Untrusted detail response')
                content = response.read(MAX_BYTES + 1)
                if len(content) > MAX_BYTES: raise ValueError('Oversized detail')
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
            date_strings = re.findall(r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+\d{1,2},?\s+20\d{2}\b', body, re.I)
            body_dates = [preview.human_date(value) for value in date_strings]
            body_dates = [d for d in body_dates if d and d >= date.today()]
            dates = sorted(set(time_dates or body_dates))
            if not dates: raise ValueError('No dated program details')
            override = SMITHSONIAN_START_OVERRIDES.get(slug)
            if override:
                # A registration cutoff may precede the first class. Explicitly
                # anchor the event to its separately reviewed class start.
                if override not in dates:
                    raise ValueError('Reviewed class start missing from current official page')
                first = override
            else:
                if dates[0] != start: raise ValueError('Date mismatch')
                first = start
            if first <= date.today():
                raise ValueError('Same-day or expired; start time unverified')
            # Only retain dates on/after the actual start, never a registration deadline.
            session_dates = [d for d in dates if d >= first]
            last = max(session_dates)
            course = len(session_dates) > 1
            description = (f'Online course, {len(session_dates)} listed dates. '
                           if course else 'Online Smithsonian Associates program. ')
            if course:
                description += f'First listed class {first.isoformat()}, last listed date {last.isoformat()}. '
            description += 'Check the official program page for registration, schedule and attendance details.'
            accepted.append(dict(title=title, description=description[:360],
                date=first.isoformat(), endDate=last.isoformat(),
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
