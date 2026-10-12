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

def smithsonian_detail_candidates(tree, base):
    """Discover up to 100 official programs; verify dates, online status and art relevance."""
    program_links = smithsonian_program_links(tree, base)
    listing_queue = sorted(smithsonian_listing_links(tree, base) | smithsonian_art_directory_links(tree, base))
    print(f'Smithsonian official listing and art-directory links discovered: {len(listing_queue)}')
    for page in listing_queue[:8]:
        print(f'  DISCOVERED LISTING {page}')
    visited_listings = {base}
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
        new_programs = smithsonian_program_links(page_tree, base) - program_links
        print(f'  LISTING {page}: {len(new_programs)} additional program links')
        program_links.update(new_programs)
        listing_queue.extend(sorted((smithsonian_listing_links(page_tree, base) | smithsonian_art_directory_links(page_tree, base)) - visited_listings - set(listing_queue)))
    # Prefer verified art-topic program URLs, rather than spending the 100-item
    # budget on category navigation entries from the program directory.
    links = sorted(program_links)[:SMITHSONIAN_BATCH_SIZE]
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
        if not title or len(title) > 180 or SMITHSONIAN_DIRECTORY_TITLE.search(title):
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
    print('DISCOVERY CAUTION: Category pages are followed only when linked in official HTML; candidate dates and online status still require review.')
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

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Read-only Rule of Three calendar investigation')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--online', action='store_true', help='Test three online art calendars')
    group.add_argument('--nyc', action='store_true', help='Test original three NYC calendars')
    group.add_argument('--all', action='store_true', help='Test all six calendars')
    args = parser.parse_args()
    print('RULE OF THREE: CLEAN FUTURE-EVENT CANDIDATES, READ-ONLY')
    sources = (NYC_SOURCES + ONLINE_SOURCES) if args.all else (ONLINE_SOURCES if args.online else NYC_SOURCES)
    for name, url in sources:
        inspect(name, url, online=(name in {n for n, _ in ONLINE_SOURCES}))
    print('\nNo event cache read or written; production collector unchanged.')
