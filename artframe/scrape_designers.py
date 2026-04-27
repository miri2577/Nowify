#!/usr/bin/env python3
"""Themed image scraper — Dieter Rams, Bauhaus.

Each THEME wires its own set of sources (Wikimedia Commons categories,
Smithsonian/Cooper Hewitt queries, Harvard Art Museums, AIC, Met). All
results land in one folder with metadata.json compatible with the
artframe OSD label script.

Usage:
    THEME=rams MUSEUM_COUNT=200 \
      MUSEUM_OUT=C:\\Users\\mirkorichter\\museum_rams \
      python scrape_designers.py

    THEME=bauhaus MUSEUM_COUNT=1000 \
      HARVARD_API_KEY=... \
      MUSEUM_OUT=C:\\Users\\mirkorichter\\museum_bauhaus \
      python scrape_designers.py

Stdlib only.
"""
import concurrent.futures as cf
import json
import os
import random
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from html import unescape
from pathlib import Path

# ───── config ─────────────────────────────────────────────────────────
THEME    = os.environ.get('THEME', 'rams').strip().lower()
TARGET   = int(os.environ.get('MUSEUM_COUNT', '200'))
WORKERS  = int(os.environ.get('MUSEUM_WORKERS', '12'))
UA       = os.environ.get(
    'MUSEUM_UA',
    'ArtframeDesigners/1.0 (miri2577@googlemail.com)',
)
OUT_DIR  = Path(os.environ.get(
    'MUSEUM_OUT',
    rf'C:\Users\mirkorichter\museum_{THEME}',
))
HARV_KEY = os.environ.get('HARVARD_API_KEY', '').strip()
SI_KEY   = os.environ.get('SI_API_KEY', 'DEMO_KEY').strip()
EU_KEY   = os.environ.get('EUROPEANA_KEY', 'api2demo').strip()
DDB_KEY  = os.environ.get('DDB_API_KEY', '').strip()

IMG_DIR   = OUT_DIR / 'images'
META_FILE = OUT_DIR / 'metadata.json'

MIN_BYTES = 10_000
MAX_BYTES = 30 * 1024 * 1024


# ───── theme configs ──────────────────────────────────────────────────
THEMES = {
    'rams': {
        'description': 'Dieter Rams — Braun + Vitsœ industrial design',
        # No WMC — too much hobby material (store photos, portraits).
        # Europeana aggregates real museum inventory photography from
        # Kunstpalast Düsseldorf, HfG-Archiv Ulm, Museu del Disseny etc.
        'wmc': [],
        'aic': [],
        'met': [],
        'harvard': [],
        'smithsonian': ['Dieter Rams'],
        # Bias toward Braun electronics (Rams' actual day-job for 40+
        # years). One Vitsœ query stays so we get some furniture too,
        # but a quota in main() caps furniture at ~20% of the total.
        # Are.na temporarily empty: it 429s under heavy parallel load
        # and hangs the gather phase. DDB + Flickr + Europeana already
        # cover Rams well; bring back Are.na with sequential throttle
        # if needed later.
        'arena_disabled': [
            # Phonosuper / hi-fi consoles (1956-)
            'Phonosuper', 'Schneewittchensarg', 'snow white coffin',
            'Braun SK 4', 'Braun SK 5', 'Braun SK 6',
            'Braun SK 25', 'Braun SK 55', 'Braun SK 61',
            # Tuners + amplifiers + receivers
            'Braun studio 2', 'Braun studio 1000',
            'Braun atelier 1', 'Braun atelier 2', 'Braun atelier 3',
            'Braun atelier 1-81',
            'Braun regie 308', 'Braun regie 350', 'Braun regie 450',
            'Braun regie 510', 'Braun regie 520',
            'Braun audio 1', 'Braun audio 2', 'Braun audio 250',
            'Braun audio 300', 'Braun audio 308', 'Braun audio 400',
            'Braun CSV 13', 'Braun CSV 60', 'Braun CSV 250',
            'Braun CSV 1000',
            # Transistor / portable radios
            'Braun T 3', 'Braun T 22', 'Braun T 31', 'Braun T 41',
            'Braun T 1000', 'Braun T1000', 'Braun T 1000 CD',
            'Braun TP 1', 'Braun TP1', 'Braun TP 2', 'Braun TP2',
            'Braun world receiver',
            # Tape recorders + cassette
            'Braun TG 60', 'Braun TG 100', 'Braun TG 1000',
            'Braun TS 45', 'Braun TC 20', 'Braun TC 40',
            # Turntables / phono
            'Braun PS 2', 'Braun PS 350', 'Braun PS 400',
            'Braun PS 500', 'Braun PS 600', 'Braun PS 1000',
            'Braun PC 3', 'Braun PCS 4', 'Braun PCS 5', 'Braun PCS 51',
            # Loudspeakers
            'Braun L 1', 'Braun L 2', 'Braun L 60', 'Braun L 70',
            'Braun L 80', 'Braun L 410', 'Braun L 450',
            'Braun LE 1', 'Braun LE1', 'Braun L02',
            'Braun electrostat',
            # Television
            'Braun HF 1', 'Braun FS 80', 'Braun FS 1000',
            # Calculators + clocks + watches
            'Braun ET 11', 'Braun ET 22', 'Braun ET 33',
            'Braun ET 44', 'Braun ET 55', 'Braun ET 66', 'Braun ET 88',
            'Braun DN 30', 'Braun ABR 21', 'Braun AB 312',
            'Braun AW 10', 'Braun AW 20', 'Braun AW 50',
            # Hairdryers + shavers
            'Braun HLD 4', 'Braun HLD 6', 'Braun HLD 8',
            'Braun sixtant', 'Braun micron', 'Braun vario',
            # Kitchen
            'Braun KMM', 'Braun KMM 2', 'Braun KSM',
            'Braun HT 2', 'Braun M 12', 'Braun mixer',
            # Heaters + slide projectors + Super-8 cameras
            'Braun H 1', 'Braun H 7', 'Braun H 88',
            'Braun D 40', 'Braun D 45',
            'Nizo S8', 'Nizo S 8', 'Nizo FA 1', 'Nizo FA 3',
            # Generic catch-alls
            'Braun phonograph', 'Braun radio', 'Braun design',
            # Vitsœ — capped by quota
            'Vitsoe', 'Vitsoe 606',
        ],
        # Single broad DDB query — keep everything DDB returns for
        # the "Dieter Rams" full-text search, no client-side filter.
        'ddb': ['Dieter Rams'],
        # Flickr disabled — too much off-topic noise (slot-cars,
        # random Braun-Büffel leather, Kitsune fox audio, etc.)
        'flickr_disabled': [],
        'europeana': [
            # Creator filter — Rams himself
            'who:"Dieter Rams"',
            # HfG-Ulm collaborator (Phonosuper SK 4 etc.) — high signal
            'who:"Hans Gugelot" AND who:Braun',
            # Title-only matches with terms unique to Rams designs.
            # Avoid bare model numbers ("SK 4", "T 1000") which hit
            # Swedish military aircraft (Skolflygplan SK 5/61) and
            # Siemens teleprinter T 1000.
            'title:Phonosuper',
            'title:Schneewittchensarg',
            'title:Vitsoe',
            'title:"Vitsœ"',
            'title:"606 Universal"',
            'title:Phonokombination',
        ],
        'default_designer': 'Dieter Rams',
    },
    'bauhaus': {
        'description': 'Bauhaus 1919–1933 — paintings, design, photography',
        'wmc': [
            'Bauhaus', 'Bauhaus in Dessau', 'Bauhaus typography',
            'Wagenfeld lamps', 'Wassily Chair',
            'Paintings by Paul Klee', 'Paintings by Wassily Kandinsky',
            'Photographs by László Moholy-Nagy',
        ],
        'aic': [
            'Wassily Kandinsky', 'Paul Klee', 'László Moholy-Nagy',
            'Marianne Brandt', 'Josef Albers', 'Lyonel Feininger',
            'Oskar Schlemmer', 'Anni Albers', 'Bauhaus',
        ],
        'met': [
            'Wassily Kandinsky', 'Paul Klee', 'László Moholy-Nagy',
            'Marianne Brandt', 'Josef Albers', 'Lyonel Feininger',
            'Oskar Schlemmer', 'Bauhaus',
        ],
        'harvard': [
            'Wassily Kandinsky', 'Paul Klee', 'László Moholy-Nagy',
            'Lyonel Feininger', 'Josef Albers', 'Oskar Schlemmer',
            'Anni Albers', 'Bauhaus',
        ],
        'smithsonian': ['Bauhaus'],
        'europeana': [],
        'default_designer': None,
    },
}


# ───── http with throttling + 429 backoff ───────────────────────────
# Wikimedia's CDN (upload.wikimedia.org) plus the Commons API both
# throttle aggressively per-IP. A global lock with a 500 ms minimum gap
# between WMC requests keeps us under their radar without registering
# an OAuth client.
_WMC_LOCK     = threading.Lock()
_WMC_LAST_REQ = 0.0
_WMC_MIN_GAP  = 0.5


def _is_wmc_url(url):
    return 'wikimedia.org' in url or 'wikipedia.org' in url


def _wmc_throttle():
    global _WMC_LAST_REQ
    with _WMC_LOCK:
        gap = time.time() - _WMC_LAST_REQ
        if gap < _WMC_MIN_GAP:
            time.sleep(_WMC_MIN_GAP - gap)
        _WMC_LAST_REQ = time.time()


def http_get(url, headers=None, timeout=60, retries=5):
    safe = urllib.parse.quote(url, safe=':/?&=%#+')
    hdrs = {'User-Agent': UA}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(safe, headers=hdrs)
    is_wmc = _is_wmc_url(url)
    for attempt in range(retries):
        if is_wmc:
            _wmc_throttle()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < retries - 1:
                # Exponential backoff: 5, 10, 20, 40 s + jitter
                delay = 5 * (2 ** attempt) + random.random()
                time.sleep(delay)
                continue
            raise


def http_json(url, headers=None, timeout=60):
    return json.loads(http_get(url, headers, timeout).decode('utf-8'))


# ───── small helpers ──────────────────────────────────────────────────
_HTML_RE = re.compile(r'<[^>]+>')

def strip_html(s):
    if not s:
        return ''
    return unescape(_HTML_RE.sub('', s)).strip()


def free_license(s):
    s = (s or '').lower()
    return any(k in s for k in (
        'cc0', 'public domain', 'cc by-sa', 'cc-by-sa', 'cc by',
        'cc-by', 'cc zero', 'cc-zero', 'pd-', 'attribution',
    ))


_SLUG_RE = re.compile(r'[^\w]+', re.UNICODE)

def slug(s, n=60):
    return _SLUG_RE.sub('_', (s or '')).strip('_')[:n]


def to_str(v):
    """Coerce Europeana's mixed list/dict/string structures to a plain str."""
    if v is None:
        return ''
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        for k in ('def', 'value', '@value', 'name', 'label', 'en'):
            if k in v and isinstance(v[k], str):
                return v[k]
        # fallback: first string value in the dict
        for x in v.values():
            if isinstance(x, str):
                return x
        return ''
    if isinstance(v, list):
        for item in v:
            s = to_str(item)
            if s:
                return s
        return ''
    return str(v)


# ───── Wikimedia Commons ──────────────────────────────────────────────
COMMONS_API = 'https://commons.wikimedia.org/w/api.php'


def wmc_category_files(category, max_files=300, max_depth=1):
    """BFS — return list of File:… page titles in this Commons category."""
    seen, files = set(), []
    queue = [(category, 0)]
    while queue and len(files) < max_files:
        cat, depth = queue.pop(0)
        if cat in seen:
            continue
        seen.add(cat)
        cont = None
        while True:
            params = {
                'action':  'query',
                'list':    'categorymembers',
                'cmtitle': f'Category:{cat}',
                'cmtype':  'file|subcat',
                'cmlimit': '500',
                'format':  'json',
            }
            if cont:
                params['cmcontinue'] = cont
            url = f'{COMMONS_API}?{urllib.parse.urlencode(params)}'
            try:
                data = http_json(url, timeout=30)
            except Exception as e:
                print(f'  [wmc] {cat}: {e}', flush=True)
                break
            for m in data.get('query', {}).get('categorymembers', []):
                if m.get('ns') == 6:
                    files.append(m['title'])
                elif m.get('ns') == 14 and depth < max_depth:
                    sub = m['title'].split(':', 1)[1]
                    if sub not in seen:
                        queue.append((sub, depth + 1))
            cont = (data.get('continue') or {}).get('cmcontinue')
            if not cont:
                break
    return files[:max_files]


def wmc_image_info_batch(file_titles):
    """Resolve up to 50 File:… titles → list of art dicts."""
    if not file_titles:
        return []
    params = {
        'action':       'query',
        'titles':       '|'.join(file_titles),
        'prop':         'imageinfo',
        'iiprop':       'url|size|extmetadata|mime',
        'iiurlwidth':   '3000',
        'format':       'json',
    }
    url = f'{COMMONS_API}?{urllib.parse.urlencode(params)}'
    try:
        data = http_json(url, timeout=60)
    except Exception as e:
        print(f'  [wmc] image-info: {e}', flush=True)
        return []
    out = []
    for page in (data.get('query', {}).get('pages') or {}).values():
        ii = (page.get('imageinfo') or [None])[0]
        if not ii:
            continue
        mime = ii.get('mime', '')
        if mime not in ('image/jpeg', 'image/jpg', 'image/png'):
            continue
        ext = ii.get('extmetadata') or {}
        lic = (ext.get('LicenseShortName') or {}).get('value', '')
        if not free_license(lic):
            continue
        img_url = ii.get('thumburl') or ii.get('url')
        if not img_url:
            continue
        # File:Foo bar baz.jpg → "Foo bar baz"
        title_raw = page.get('title', '').split(':', 1)[-1].rsplit('.', 1)[0]
        title_clean = title_raw.replace('_', ' ')

        out.append({
            'id':         f'wmc_{abs(hash(page.get("title","")))%10**10}',
            'source':     'wmc',
            'title':      title_clean,
            'artist':     strip_html((ext.get('Artist') or {}).get('value', '')),
            'date':       strip_html((ext.get('DateTime') or {}).get('value', '')),
            'museum':     'Wikimedia Commons',
            'medium':     '',
            'dimensions': '',
            'license':    lic,
            'credit':     strip_html((ext.get('Credit') or {}).get('value', '')),
            'source_url': f'https://commons.wikimedia.org/wiki/{page.get("title","").replace(" ", "_")}',
            'image_url':  img_url,
        })
    return out


# ───── Smithsonian / Cooper Hewitt ────────────────────────────────────
SI_API = 'https://api.si.edu/openaccess/api/v1.0/search'

def smithsonian_search(query, key=None, limit=80, unit='CHNDM'):
    key = key or SI_KEY
    if not key:
        return []
    # Bare quoted phrase performs best across SI's units; the
    # unit_code/online_media_type Lucene filters return 0 hits with
    # DEMO_KEY for many queries (server-side restriction).
    q = f'"{query}"'
    params = {
        'q': q,
        'rows': str(limit),
        'api_key': key,
    }
    url = f'{SI_API}?{urllib.parse.urlencode(params)}'
    try:
        data = http_json(url, timeout=30)
    except Exception as e:
        print(f'  [si] {query}: {e}', flush=True)
        return []
    rows = data.get('response', {}).get('rows') or []
    out = []
    for row in rows:
        c = row.get('content', {}) or {}
        d = c.get('descriptiveNonRepeating', {}) or {}
        media = (d.get('online_media') or {}).get('media') or []
        img = next((m for m in media if m.get('type') == 'Images'), None)
        if not img:
            continue
        # Prefer IIIF full-size, else thumbnail
        idsmap = img.get('idsId') or img.get('content', '')
        iiif = img.get('content', '')
        if not iiif:
            continue
        # Smithsonian IIIF URL is the "content" if it's already an /full/
        # URL, or the IDS ID needs combining with the IIIF base
        if iiif.startswith('http') and '/full/' in iiif:
            img_url = iiif
        else:
            img_url = iiif  # fallback raw
        usage = (d.get('metadata_usage') or {}).get('access', '')
        title = c.get('descriptiveNonRepeating', {}).get('title', {}).get('content', '') \
                or row.get('title', '')
        # Artist from indexedStructured.name or freetext
        names = (c.get('indexedStructured') or {}).get('name', []) or []
        artist = names[0] if names else ''
        date = ''
        idx = c.get('indexedStructured', {}) or {}
        for k in ('date', 'date_made'):
            if k in idx and idx[k]:
                date = idx[k][0] if isinstance(idx[k], list) else idx[k]
                break
        out.append({
            'id':         f'si_{row.get("id","")}',
            'source':     'si',
            'title':      title,
            'artist':     artist,
            'date':       date,
            'museum':     d.get('data_source', '') or 'Cooper Hewitt',
            'medium':     '',
            'dimensions': '',
            'license':    usage,
            'credit':     '',
            'source_url': (d.get('record_link') or ''),
            'image_url':  img_url,
        })
    return out


# ───── Harvard Art Museums ────────────────────────────────────────────
HARV_API = 'https://api.harvardartmuseums.org/object'

def harvard_search(query, key, limit=100, page=1):
    if not key:
        return []
    params = {
        'apikey':   key,
        'q':        query,
        'size':     str(limit),
        'page':     str(page),
        'hasimage': '1',
        'fields': 'id,title,people,dated,medium,dimensions,classification,'
                  'primaryimageurl,images,copyright,division,creditline,url',
    }
    url = f'{HARV_API}?{urllib.parse.urlencode(params)}'
    try:
        data = http_json(url, timeout=30)
    except Exception as e:
        print(f'  [harv] {query} p{page}: {e}', flush=True)
        return []
    out = []
    for r in data.get('records') or []:
        # primaryimageurl is direct; if missing, try IIIF base
        pi = r.get('primaryimageurl')
        if not pi and r.get('images'):
            base = r['images'][0].get('iiifbaseuri')
            if base:
                pi = f'{base}/full/full/0/default.jpg'
        if not pi:
            continue
        copyr = (r.get('copyright') or '').lower()
        # Skip restricted-copyright items
        if copyr and 'restrict' in copyr and 'public domain' not in copyr:
            continue
        people = r.get('people') or []
        artist = people[0].get('name', '') if people else ''
        out.append({
            'id':         f'harv_{r.get("id","")}',
            'source':     'harv',
            'title':      r.get('title') or '',
            'artist':     artist,
            'date':       r.get('dated') or '',
            'museum':     r.get('division') or 'Harvard Art Museums',
            'medium':     r.get('medium') or '',
            'dimensions': r.get('dimensions') or '',
            'license':    r.get('copyright') or 'see source',
            'credit':     r.get('creditline') or '',
            'source_url': r.get('url') or '',
            'image_url':  pi,
        })
    return out


# ───── Flickr (public tag feed, no key needed) ───────────────────────
# Returns most recent ~20 photos for a given tag. The feed URL points
# at the _m.jpg derivative (240 px) — substitute _b (1024), _k (2048),
# or _o (original) on the same path for hi-res. Multi-tag mode AND-s
# tags by default; tagmode=any switches to OR.
FLICKR_FEED = 'https://api.flickr.com/services/feeds/photos_public.gne'


_FLICKR_WHITELIST = (
    'braun', 'rams', 'vitsoe', 'vitsœ',
    'phonosuper', 'schneewittchensarg', 'snow white coffin',
    'nizo', 'hfg ulm',
)


def flickr_tag_feed(tag, mode='any'):
    params = {'tags': tag, 'tagmode': mode, 'format': 'json',
              'nojsoncallback': '1'}
    url = f'{FLICKR_FEED}?{urllib.parse.urlencode(params)}'
    try:
        data = http_json(url, timeout=30)
    except Exception as e:
        print(f'  [flickr] {tag}: {e}', flush=True)
        return []
    out = []
    for it in data.get('items') or []:
        media = (it.get('media') or {}).get('m') or ''
        if not media:
            continue
        # Tag feeds often share generic short tags between unrelated
        # users (slot-car racers, architects, fox audio recorders all
        # tag with "brauntp1" or similar). Require a Rams keyword in
        # the human title before keeping the photo.
        title_raw = (it.get('title') or '').strip()
        descr_raw = (it.get('description') or '').strip()
        haystack = (title_raw + ' ' + descr_raw).lower()
        if not any(k in haystack for k in _FLICKR_WHITELIST):
            continue
        hi = media.replace('_m.jpg', '_b.jpg')
        title = title_raw or 'Untitled'
        author = it.get('author') or ''
        # author = "nobody@flickr.com (\"Real Name\")" — extract the quoted bit
        m = re.search(r'\("([^"]+)"\)', author)
        if m:
            author = m.group(1)
        out.append({
            'id':         f'flickr_{re.sub(r"[^0-9]", "", media.split("/")[-1])[:12]}',
            'source':     'flickr',
            'title':      title,
            'artist':     author,
            'date':       (it.get('date_taken') or '')[:10],
            'museum':     'Flickr',
            'medium':     '',
            'dimensions': '',
            'license':    'Creative Commons (Flickr)',
            'credit':     '',
            'source_url': it.get('link') or '',
            'image_url':  hi,
        })
    return out


# ───── Deutsche Digitale Bibliothek (DDB) ────────────────────────────
# Aggregator for 700+ German cultural institutions (museums, libraries,
# archives). Free API key. Per-item license sits in
# /items/{id}/binaries → @kind URL.
DDB_API = 'https://api.deutsche-digitale-bibliothek.de'

# Match "Braun" as the company name only — followed by a space, hyphen,
# punctuation, or end-of-string. Drops adjectival forms ("Braunes Haus",
# "Brauner Bär"), "Braunschweig" the city, "Braunsche Sammlung", etc.
_BRAUN_WORD_RE = re.compile(
    r'\bbraun(?:s)?(?=$|[\s\-.,;:!?/)])', re.IGNORECASE,
)


def _ddb_is_free_license(license_url):
    s = (license_url or '').lower()
    return any(k in s for k in (
        'publicdomain', 'cc0', '/cc/by', 'creativecommons',
        'rights_001',  # DDB short code for free reuse
    ))


def _ddb_fetch_binary(item_id, key):
    """Resolve a DDB item to (image_url, license_url) or None.

    Prefers DDB's own IIIF cache (iiif.deutsche-digitale-bibliothek.de)
    over the source museum's @local_pathname — many museum servers
    (SLUB Dresden, etc.) are slow or temporarily unreachable, while
    DDB's cache responds reliably."""
    try:
        data = http_json(
            f'{DDB_API}/items/{item_id}/binaries',
            headers={'Authorization': f'OAuth oauth_consumer_key="{key}"',
                     'Accept': 'application/json'},
            timeout=20,
        )
    except Exception:
        return None
    if not data:
        return None
    binary = data.get('binary')
    if isinstance(binary, list):
        binary = binary[0] if binary else None
    if not binary:
        return None

    ref = binary.get('@ref') or ''
    if ref:
        img_url = (f'https://iiif.deutsche-digitale-bibliothek.de'
                   f'/image/2/{ref}/full/full/0/default.jpg')
    else:
        img_url = binary.get('@local_pathname') or ''

    return img_url, binary.get('@kind', '')


def _ddb_item_creators(item_id, key):
    """Return list of agent prefLabel strings for an item — designers,
    photographers, sculptors etc. attributed by the institution."""
    try:
        data = http_json(
            f'{DDB_API}/items/{item_id}',
            headers={'Authorization': f'OAuth oauth_consumer_key="{key}"',
                     'Accept': 'application/json'},
            timeout=20,
        )
    except Exception:
        return []
    rdf = (data.get('edm') or {}).get('RDF') or {}
    agents = rdf.get('Agent') or []
    if isinstance(agents, dict):
        agents = [agents]
    names = []
    for a in agents:
        if not isinstance(a, dict):
            continue
        lbl = a.get('prefLabel')
        if isinstance(lbl, dict):
            lbl = lbl.get('$', '')
        if isinstance(lbl, str) and lbl:
            names.append(lbl)
    return names


def _ddb_resolve(item_id, key, creator_keywords=None):
    """Fetch binary URL + (optionally) verify creator."""
    bin_result = _ddb_fetch_binary(item_id, key)
    if not bin_result:
        return None
    img_url, license_url = bin_result
    if not img_url:
        return None
    # No license filter — DDB tags many items with restrictive license
    # URLs even though the thumbnail is publicly visible on the portal.
    # For private display we don't care.

    creators = _ddb_item_creators(item_id, key) if creator_keywords else []
    if creator_keywords:
        haystack = ' '.join(creators).lower()
        if not any(k in haystack for k in creator_keywords):
            return None
    return img_url, license_url, '; '.join(creators)


def ddb_search(query, key=None, rows=500, whitelist=None,
               creator_keywords=None):
    """DDB full-text search.

    creator_keywords: tuple of lowercase substrings. When set, each
    candidate item's full detail is fetched and its Agent prefLabels
    (designer, artist, photographer, etc.) are checked. Items without
    a matching creator are dropped. Costs +1 API call per item — use
    sparingly."""
    key = key or DDB_KEY
    if not key:
        return []
    # Bare query — DDB's media_fct.filter param raises GeneralException
    # for many queries. Filter media=='image' client-side instead.
    params = {
        'query':              query,
        'rows':               str(rows),
        'oauth_consumer_key': key,
    }
    url = f'{DDB_API}/search?{urllib.parse.urlencode(params)}'
    try:
        data = http_json(url, headers={'Accept': 'application/json'},
                         timeout=30)
    except Exception as e:
        print(f'  [ddb] {query}: {e}', flush=True)
        return []
    docs = []
    for r in data.get('results') or []:
        docs.extend(r.get('docs') or [])

    out = []
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        future_to_doc = {}
        for d in docs:
            if d.get('media') != 'image':
                continue
            item_id = d.get('id')
            if not item_id:
                continue
            future_to_doc[ex.submit(_ddb_resolve, item_id, key,
                                    creator_keywords)] = d

        for fut in cf.as_completed(future_to_doc):
            d = future_to_doc[fut]
            try:
                result = fut.result()
            except Exception:
                continue
            if not result:
                continue
            img_url, license_url, creators = result

            title = d.get('label') or d.get('title') or 'Untitled'
            view = d.get('view') or []
            descr = view[1] if len(view) > 1 else ''
            if whitelist:
                hay_low = (title + ' ' + descr).lower()
                if not any(k in hay_low for k in whitelist):
                    continue

            out.append({
                'id':         f'ddb_{d.get("id")}',
                'source':     'ddb',
                'title':      title,
                'artist':     creators,
                'date':       '',
                'museum':     'Deutsche Digitale Bibliothek',
                'medium':     view[0] if view else '',
                'dimensions': '',
                'license':    license_url,
                'credit':     descr[:200] if descr else '',
                'source_url': f'https://www.deutsche-digitale-bibliothek.de'
                              f'/item/{d.get("id")}',
                'image_url':  img_url,
            })
    return out


# ───── Are.na ─────────────────────────────────────────────────────────
# Curated design boards. Image blocks expose `image.original.url` =
# direct CloudFront hi-res, no key needed.
def _arena_block_to_art(b):
    if b.get('class') != 'Image':
        return None
    img = ((b.get('image') or {}).get('original') or {}).get('url') or ''
    if not img:
        return None
    user = (b.get('user') or {}).get('username') or ''
    title = (b.get('title') or b.get('generated_title')
             or b.get('description') or '').strip()
    return {
        'id':         f'arena_{b.get("id")}',
        'source':     'arena',
        'title':      title or 'Untitled',
        'artist':     user,
        'date':       (b.get('created_at') or '')[:10],
        'museum':     'Are.na',
        'medium':     '',
        'dimensions': '',
        'license':    'mixed',
        'credit':     '',
        'source_url': f'https://www.are.na/block/{b.get("id")}',
        'image_url':  img,
    }


def _arena_channel_contents(slug, per_page=100, max_pages=30):
    """Walk one Are.na channel, page through its contents, return image arts."""
    out = []
    for page in range(1, max_pages + 1):
        url = (f'https://api.are.na/v2/channels/{slug}/contents'
               f'?per={per_page}&page={page}')
        try:
            data = http_json(url, timeout=30)
        except Exception:
            break
        contents = data.get('contents') or []
        if not contents:
            break
        for b in contents:
            art = _arena_block_to_art(b)
            if art:
                out.append(art)
        if len(contents) < per_page:
            break
    return out


_ARENA_CHANNEL_WHITELIST = ('rams', 'braun', 'vitsoe', 'vitsœ', 'phonosuper')


def arena_search(query):
    """Combine direct block search (each block matches the query) with
    selective channel traversal — only channels whose title strongly
    references the topic. This keeps quality while picking up curated
    boards' contents."""
    out = []

    # 1. Direct block search — each match is query-relevant by definition
    try:
        url = ('https://api.are.na/v2/search?'
               + urllib.parse.urlencode({'q': query, 'per': '100',
                                         'page': '1'}))
        data = http_json(url, timeout=30)
        for b in data.get('blocks') or []:
            art = _arena_block_to_art(b)
            if art:
                out.append(art)
    except Exception as e:
        print(f'  [arena] {query}: {e}', flush=True)

    # 2. Channel traversal — only channels whose title contains a
    #    Rams-relevant token. Filters out generic boards.
    try:
        url = ('https://api.are.na/v2/search/channels?'
               + urllib.parse.urlencode({'q': query, 'per': '20'}))
        data = http_json(url, timeout=30)
        channels = data.get('channels') or []
    except Exception:
        channels = []
    for ch in channels:
        title = (ch.get('title') or '').lower()
        if not any(k in title for k in _ARENA_CHANNEL_WHITELIST):
            continue
        slug = ch.get('slug')
        if slug:
            out.extend(_arena_channel_contents(slug))
    return out


# ───── Europeana ──────────────────────────────────────────────────────
EU_API = 'https://api.europeana.eu/record/v2/search.json'


_EU_BAD_CREATORS = (
    # 19th-cent. Alsatian photographer of art reproductions
    'adolphe braun', 'braun et cie', 'braun and company',
    'braun et compagnie', 'braun & cie',
    # 16th-cent. cartographer (Civitates Orbis Terrarum atlas)
    'braun, georg', 'georg braun', 'hogenberg', 'hoefnagel',
)
_EU_BAD_TITLE_TERMS = (
    # 16th-cent. atlas
    'civitates orbis', 'depingebat', 'hoefnagle',
    # Swedish military aircraft Skolflygplan (Sk 5 / Sk 61 / Sk 16)
    'flygplan', 'skolflygplan',
    # Other vendors that share model numbers with Braun
    'siemens', 'kodak', 'fernschreiber', 'lochstreifen',
    'pulttisch', 'kofferradio',  # generic
    # Random map / book / scientific noise
    'carte de', 'catalogue', 'manuscrit', 'séismes',
    'saint-albin', 'reseradio',
    # Theodor Heuss / general HfG furniture noise
    'theodor heuss',
)


def europeana_search(query, key=None, rows=100):
    key = key or EU_KEY
    params = {
        'wskey':   key,
        # If the caller already supplied a Lucene field-prefix
        # (who:/title:/what:), use it raw; otherwise quote the phrase.
        'query':   query if ':' in query else f'"{query}"',
        'rows':    str(rows),
        'profile': 'rich',
    }
    url = f'{EU_API}?{urllib.parse.urlencode(params)}'
    try:
        data = http_json(url, timeout=30)
    except Exception as e:
        print(f'  [eu] {query}: {e}', flush=True)
        return []
    out = []
    for it in data.get('items') or []:
        img = (it.get('edmIsShownBy') or [None])[0]
        if not img:
            continue
        # Bump server-side resolution if the URL exposes a dimension hint
        img = re.sub(r'dimension=\d+x\d+', 'dimension=4000x4000', img)

        rights   = to_str(it.get('rights'))
        creator  = to_str(it.get('dcCreator')) \
                   or to_str(it.get('edmAgentLabel'))
        title    = to_str(it.get('title')) or to_str(it.get('dcTitle'))
        date     = to_str(it.get('year'))  or to_str(it.get('dcDate'))
        provider = to_str(it.get('dataProvider')) or 'Europeana'

        # Drop Europeana false positives — search for "Braun" ropes in
        # 19th-cent photographer Adolphe Braun and the 16th-cent atlas
        # by Georg Braun & Hogenberg, which dominate by sheer volume.
        c_low = creator.lower()
        t_low = title.lower()
        if any(b in c_low for b in _EU_BAD_CREATORS):
            continue
        if any(b in t_low for b in _EU_BAD_TITLE_TERMS):
            continue

        out.append({
            'id':         f'eu_{abs(hash(img)) % 10**10}',
            'source':     'eu',
            'title':      title,
            'artist':     creator,
            'date':       date,
            'museum':     provider,
            'medium':     '',
            'dimensions': '',
            'license':    rights,
            'credit':     '',
            'source_url': (it.get('edmIsShownAt') or [''])[0],
            'image_url':  img,
        })
    return out


# ───── AIC (Art Institute of Chicago) ─────────────────────────────────
AIC_API = 'https://api.artic.edu/api/v1/artworks/search'

def aic_search(query, per_page=100, pages=3):
    fields = ('id,title,artist_display,date_display,medium_display,'
              'classification_title,image_id,is_public_domain,credit_line')
    out = []
    for p in range(1, pages + 1):
        params = {
            'q': query, 'limit': str(per_page), 'page': str(p),
            'fields': fields,
        }
        url = f'{AIC_API}?{urllib.parse.urlencode(params)}'
        try:
            data = http_json(url, headers={'AIC-User-Agent': UA}, timeout=30)
        except Exception as e:
            print(f'  [aic] {query} p{p}: {e}', flush=True)
            break
        items = data.get('data') or []
        if not items:
            break
        for it in items:
            if not it.get('is_public_domain'):
                continue
            if not it.get('image_id'):
                continue
            iiif = (f'https://www.artic.edu/iiif/2/{it["image_id"]}/'
                    f'full/2400,/0/default.jpg')
            out.append({
                'id':         f'aic_{it["id"]}',
                'source':     'aic',
                'title':      it.get('title') or '',
                'artist':     it.get('artist_display') or '',
                'date':       it.get('date_display') or '',
                'museum':     'Art Institute of Chicago',
                'medium':     it.get('medium_display') or '',
                'dimensions': '',
                'license':    'CC0',
                'credit':     it.get('credit_line') or '',
                'source_url': f'https://www.artic.edu/artworks/{it["id"]}',
                'image_url':  iiif,
            })
        if len(items) < per_page:
            break
    return out


# ───── Met Museum ─────────────────────────────────────────────────────
MET_API = 'https://collectionapi.metmuseum.org/public/collection/v1'

def met_search(query, sample=120):
    params = {'q': query, 'hasImages': 'true'}
    url = f'{MET_API}/search?{urllib.parse.urlencode(params)}'
    try:
        ids = (http_json(url, timeout=30).get('objectIDs') or [])
    except Exception as e:
        print(f'  [met] search {query}: {e}', flush=True)
        return []
    random.shuffle(ids)
    return ids[:sample]


def met_fetch(objid):
    try:
        o = http_json(f'{MET_API}/objects/{objid}', timeout=30)
    except Exception:
        return None
    if not o.get('isPublicDomain'):
        return None
    img = o.get('primaryImage') or ''
    if not img:
        return None
    return {
        'id':         f'met_{objid}',
        'source':     'met',
        'title':      o.get('title') or '',
        'artist':     o.get('artistDisplayName') or '',
        'date':       o.get('objectDate') or '',
        'museum':     'Metropolitan Museum of Art',
        'medium':     o.get('medium') or '',
        'dimensions': o.get('dimensions') or '',
        'license':    'CC0',
        'credit':     o.get('creditLine') or '',
        'source_url': o.get('objectURL') or '',
        'image_url':  img,
    }


# ───── download ───────────────────────────────────────────────────────
def filename_for(art):
    base = f'{art["source"]}_{art["id"].split("_", 1)[-1]}'
    return f'{base}_{slug(art.get("title"))}.jpg' if slug(art.get('title')) \
           else f'{base}.jpg'


def download(art):
    extra = {'AIC-User-Agent': UA} if art['source'] == 'aic' else None
    try:
        data = http_get(art['image_url'], headers=extra, timeout=120)
    except Exception as e:
        return (art, None, f'{type(e).__name__}: {e}')
    if len(data) < MIN_BYTES or len(data) > MAX_BYTES:
        return (art, None, f'size {len(data)}B')
    if data[:3] != b'\xff\xd8\xff' and data[:8] != b'\x89PNG\r\n\x1a\n':
        return (art, None, 'not jpeg/png')
    return (art, data, None)


# ───── orchestrator ───────────────────────────────────────────────────
def gather(theme_cfg):
    pool = []

    # 1. WMC: list files in each category, then resolve image-info in
    #    50-title batches.
    if theme_cfg.get('wmc'):
        print('==> Wikimedia Commons', flush=True)
        all_titles = []
        with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
            for files in ex.map(wmc_category_files, theme_cfg['wmc']):
                all_titles.extend(files)
        all_titles = list(dict.fromkeys(all_titles))   # dedupe, preserve order
        print(f'   {len(all_titles)} files across categories', flush=True)
        batches = [all_titles[i:i+50] for i in range(0, len(all_titles), 50)]
        with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
            for batch_arts in ex.map(wmc_image_info_batch, batches):
                pool.extend(batch_arts)
        print(f'   {sum(1 for a in pool if a["source"]=="wmc")} '
              f'free-licensed', flush=True)

    # 1.5 DDB — German museum + archive aggregator
    if theme_cfg.get('ddb'):
        if DDB_KEY:
            print('==> Deutsche Digitale Bibliothek', flush=True)
            ck = theme_cfg.get('ddb_creators')
            with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
                results = ex.map(
                    lambda q: ddb_search(q, creator_keywords=ck),
                    theme_cfg['ddb'],
                )
                for arts in results:
                    pool.extend(arts)
            print(f'   {sum(1 for a in pool if a["source"]=="ddb")} '
                  f'candidates', flush=True)
        else:
            print('==> DDB skipped (set DDB_API_KEY)', flush=True)

    # 2.0 Flickr — public tag feeds, no key, hi-res via _m → _k swap
    if theme_cfg.get('flickr'):
        print('==> Flickr (public tag feeds)', flush=True)
        with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
            for arts in ex.map(flickr_tag_feed, theme_cfg['flickr']):
                pool.extend(arts)
        print(f'   {sum(1 for a in pool if a["source"]=="flickr")} '
              f'candidates', flush=True)

    # 2a. Are.na — curated design boards, direct CDN URLs
    if theme_cfg.get('arena'):
        print('==> Are.na', flush=True)
        with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
            for arts in ex.map(arena_search, theme_cfg['arena']):
                pool.extend(arts)
        print(f'   {sum(1 for a in pool if a["source"]=="arena")} candidates',
              flush=True)

    # 2b. Europeana — aggregates EU museums with great Rams coverage
    if theme_cfg.get('europeana'):
        print('==> Europeana', flush=True)
        with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
            for arts in ex.map(europeana_search, theme_cfg['europeana']):
                pool.extend(arts)
        print(f'   {sum(1 for a in pool if a["source"]=="eu")} candidates',
              flush=True)

    # 3. Smithsonian / Cooper Hewitt — DEMO_KEY ok for low volume
    if theme_cfg.get('smithsonian'):
        print('==> Smithsonian / Cooper Hewitt', flush=True)
        with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
            for arts in ex.map(smithsonian_search,
                               theme_cfg['smithsonian']):
                pool.extend(arts)
        print(f'   {sum(1 for a in pool if a["source"]=="si")} '
              f'candidates', flush=True)

    # 3. Harvard
    if theme_cfg.get('harvard') and HARV_KEY:
        print('==> Harvard Art Museums', flush=True)
        with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs = [ex.submit(harvard_search, q, HARV_KEY, 100, p)
                    for q in theme_cfg['harvard']
                    for p in (1, 2, 3)]
            for f in cf.as_completed(futs):
                pool.extend(f.result())
        print(f'   {sum(1 for a in pool if a["source"]=="harv")} candidates',
              flush=True)
    elif theme_cfg.get('harvard') and not HARV_KEY:
        print('==> Harvard skipped (no HARVARD_API_KEY set)', flush=True)

    # 4. AIC
    if theme_cfg.get('aic'):
        print('==> Art Institute of Chicago', flush=True)
        with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
            for arts in ex.map(aic_search, theme_cfg['aic']):
                pool.extend(arts)
        print(f'   {sum(1 for a in pool if a["source"]=="aic")} candidates',
              flush=True)

    # 5. Met
    if theme_cfg.get('met'):
        print('==> Metropolitan Museum', flush=True)
        ids_per_query = []
        with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
            for ids in ex.map(met_search, theme_cfg['met']):
                ids_per_query.extend(ids)
        ids_per_query = list(dict.fromkeys(ids_per_query))
        with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
            for art in ex.map(met_fetch, ids_per_query):
                if art:
                    pool.append(art)
        print(f'   {sum(1 for a in pool if a["source"]=="met")} candidates',
              flush=True)

    return pool


def main():
    if THEME not in THEMES:
        print(f'unknown THEME={THEME!r}; valid: {list(THEMES)}',
              file=sys.stderr)
        return 1
    cfg = THEMES[THEME]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    IMG_DIR.mkdir(parents=True, exist_ok=True)

    existing = []
    existing_ids = set()
    if META_FILE.exists():
        try:
            existing = json.loads(META_FILE.read_text(encoding='utf-8'))
            existing_ids = {m['id'] for m in existing}
        except Exception:
            pass

    print(f'theme: {THEME} — {cfg["description"]}', flush=True)
    print(f'target: {TARGET} images, output: {OUT_DIR}', flush=True)
    pool = gather(cfg)

    # Dedupe by id only — title-based dedup was eating half of DDB
    # because museum items often share generic titles ("Plattenspieler",
    # "Radio") with empty artist field.
    seen_ids = set()
    uniq = []
    for a in pool:
        aid = a['id']
        if aid in existing_ids or aid in seen_ids:
            continue
        seen_ids.add(aid)
        uniq.append(a)
    random.shuffle(uniq)
    print(f'==> {len(uniq)} unique candidates after dedupe', flush=True)

    if not uniq:
        print('nothing to download', flush=True)
        return 1

    # Furniture quota — Vitsœ shelving photographs dominate Are.na/
    # Flickr search so heavily that without a cap they'd fill ~80% of
    # the saved set even when most queries target Braun electronics.
    _FURNITURE_KW = (
        'vitsoe', 'vitsœ', 'shelving', 'shelves', 'bookcase',
        '606 universal', '606 system', '606 wall',
        'regal', 'möbel', 'chair', 'stuhl',
        '620 chair', '621', '622', '710 sofa', '720',
    )
    def _is_furniture(art):
        text = ((art.get('title')      or '') + ' '
                + (art.get('source_url') or '')).lower()
        return any(k in text for k in _FURNITURE_KW)

    furniture_pct = float(os.environ.get('FURNITURE_PCT', '0.20'))
    furniture_max = int(TARGET * furniture_pct)
    saved_furniture = 0
    print(f'==> furniture cap: max {furniture_max} of {TARGET} '
          f'({int(furniture_pct*100)}%)', flush=True)

    saved = []
    failed = 0
    existing_filenames = set()
    if META_FILE.exists():
        existing_filenames = {m.get('filename') for m in existing
                              if m.get('filename')}

    with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = set()
        idx = 0

        def submit_more():
            nonlocal idx
            while idx < len(uniq) and len(futs) < WORKERS * 2:
                futs.add(ex.submit(download, uniq[idx]))
                idx += 1

        submit_more()
        while futs and len(saved) < TARGET:
            done, futs = cf.wait(futs, return_when=cf.FIRST_COMPLETED)
            for f in done:
                try:
                    art, data, err = f.result()
                except Exception:
                    failed += 1; continue
                if data is None:
                    failed += 1
                    print(f'  skip {art["source"]:4s} {art["id"][:18]:>18}:'
                          f' {err}', flush=True)
                    continue
                furn = _is_furniture(art)
                if furn and saved_furniture >= furniture_max:
                    submit_more()
                    continue
                name = filename_for(art)
                base = name[:-4]
                suffix = 1
                while name in existing_filenames or (IMG_DIR/name).exists():
                    name = f'{base}_{suffix}.jpg'; suffix += 1
                (IMG_DIR / name).write_bytes(data)
                existing_filenames.add(name)
                art['filename'] = name
                art['bytes']    = len(data)
                saved.append(art)
                if furn:
                    saved_furniture += 1
                tag = 'furn' if furn else 'tech'
                print(f'[{len(saved):4d}/{TARGET}] {tag} {art["source"]:4s} '
                      f'{(art["artist"] or "?")[:24]:24s} · '
                      f'{(art["title"] or "?")[:50]}', flush=True)
                if len(saved) >= TARGET:
                    break
            submit_more()

        for f in futs:
            f.cancel()

    META_FILE.write_text(
        json.dumps(existing + saved, indent=2, ensure_ascii=False),
        encoding='utf-8',
    )
    by_src = {}
    for a in saved:
        by_src[a['source']] = by_src.get(a['source'], 0) + 1
    print('')
    print(f'done. {len(saved)} new, {len(existing) + len(saved)} total, '
          f'{failed} failures.')
    print('per source: ' + ', '.join(f'{k}={v}' for k, v in by_src.items()))
    print(f'images:   {IMG_DIR}')
    print(f'metadata: {META_FILE}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
