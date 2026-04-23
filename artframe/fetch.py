#!/usr/bin/env python3
"""Pull a batch of artwork JPGs from Wikimedia Commons.

Source: the Commons categories listed in CATEGORIES — curated by the
Commons community, all freely-licensed (public domain or CC), tens of
thousands of high-resolution paintings from museums worldwide (Louvre,
Rijksmuseum, Prado, Uffizi, etc.). No API key, no auth, direct URLs.

Stdlib only.
"""
import json
import os
import random
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

IMAGE_DIR = os.environ.get('ARTFRAME_DIR', '/var/lib/artframe/images')
KEEP_MAX = int(os.environ.get('ARTFRAME_KEEP', '40'))

# Comma-separated Commons category names (without the "Category:" prefix).
# Default pool is the curated Featured + Quality painting set — several
# thousand top-tier images. Add more for broader variety.
# Curated Commons pools (paintings, sculptures, photos, architecture,
# nature — all genres, all freely licensed). Override via env.
CATEGORIES = os.environ.get(
    'ARTFRAME_CATEGORIES',
    'Featured pictures on Wikimedia Commons,'
    'Quality images'
).split(',')

MAX_DEPTH = int(os.environ.get('ARTFRAME_DEPTH', '2'))
MAX_TITLES = int(os.environ.get('ARTFRAME_MAX_TITLES', '8000'))

COMMONS_API = 'https://commons.wikimedia.org/w/api.php'
UA = ('artframe/1.0 '
      '(https://github.com/miri2577/Nowify; contact via GitHub issues)')

WORKERS = int(os.environ.get('ARTFRAME_WORKERS', '16'))
WIDTH = int(os.environ.get('ARTFRAME_WIDTH', '1920'))
MAX_BYTES = 8 * 1024 * 1024

# Orientation filter: 'landscape', 'portrait', or 'any'.
ORIENTATION = os.environ.get('ARTFRAME_ORIENT', 'landscape').lower()


def http_get(url, timeout=30):
    safe_url = urllib.parse.quote(url, safe=':/?&=%#+')
    req = urllib.request.Request(safe_url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _list_category(category):
    """Return (files, subcats) for a single Commons category, paginated."""
    files, subcats = [], []
    cont = None
    while True:
        params = {
            'action': 'query',
            'list': 'categorymembers',
            'cmtitle': f'Category:{category.strip()}',
            'cmtype': 'file|subcat',
            'cmlimit': '500',
            'format': 'json',
        }
        if cont:
            params['cmcontinue'] = cont
        url = f'{COMMONS_API}?{urllib.parse.urlencode(params)}'
        try:
            data = json.loads(http_get(url, timeout=60))
        except Exception:
            break
        for m in data.get('query', {}).get('categorymembers', []):
            ns = m.get('ns')
            title = m.get('title', '')
            if ns == 6:           # File
                files.append(title)
            elif ns == 14:        # Subcategory
                subcats.append(title.split(':', 1)[1])
        cont = (data.get('continue') or {}).get('cmcontinue')
        if not cont:
            break
    return files, subcats


def fetch_category_tree(category):
    """BFS traversal: files from category and subcats up to MAX_DEPTH."""
    files = []
    seen_cats = set()
    queue = [(category, 0)]
    while queue and len(files) < MAX_TITLES:
        cat, depth = queue.pop(0)
        if cat in seen_cats:
            continue
        seen_cats.add(cat)
        local_files, subcats = _list_category(cat)
        files.extend(local_files)
        if depth < MAX_DEPTH:
            for sc in subcats:
                if sc not in seen_cats:
                    queue.append((sc, depth + 1))
    return files[:MAX_TITLES]


def fetch_image_infos(titles_batch):
    """For up to 50 File: titles, return list of (title, url, w, h)."""
    params = {
        'action': 'query',
        'titles': '|'.join(titles_batch),
        'prop': 'imageinfo',
        'iiprop': 'url|size|mediatype',
        'iiurlwidth': str(WIDTH),
        'format': 'json',
    }
    url = f'{COMMONS_API}?{urllib.parse.urlencode(params)}'
    try:
        data = json.loads(http_get(url, timeout=60))
    except Exception:
        return []
    out = []
    for page in (data.get('query', {}).get('pages') or {}).values():
        ii = (page.get('imageinfo') or [None])[0]
        if not ii:
            continue
        if ii.get('mediatype') != 'BITMAP':
            continue
        img_url = ii.get('thumburl') or ii.get('url')
        if not img_url:
            continue
        w = ii.get('thumbwidth') or ii.get('width') or 0
        h = ii.get('thumbheight') or ii.get('height') or 0
        out.append((page.get('title', ''), img_url, w, h))
    return out


def orientation_ok(w, h):
    if not w or not h:
        return True
    if ORIENTATION == 'landscape':
        return w >= h
    if ORIENTATION == 'portrait':
        return h >= w
    return True


def safe_filename(title):
    # "File:Mona Lisa.jpg" → "Mona_Lisa.jpg"
    base = title.split(':', 1)[-1].replace(' ', '_')
    # Drop anything that would be path-traversal
    return ''.join(c for c in base if c.isalnum() or c in '._-')[:120]


def existing_names():
    if not os.path.isdir(IMAGE_DIR):
        return set()
    return {f for f in os.listdir(IMAGE_DIR) if f.endswith('.jpg')}


def download_one(title, url, w, h):
    if not orientation_ok(w, h):
        return None
    try:
        data = http_get(url, timeout=90)
    except Exception:
        return None
    if len(data) < 10_000 or len(data) > MAX_BYTES:
        return None
    if data[:3] != b'\xff\xd8\xff':   # must be JPEG
        return None
    return (title, data)


def main():
    os.makedirs(IMAGE_DIR, exist_ok=True)
    have = existing_names()
    need = max(0, KEEP_MAX - len(have))
    if need == 0:
        print(f'already have {len(have)} images, nothing to do', flush=True)
        return 0

    print(f'fetching Commons category trees ({len(CATEGORIES)} roots, '
          f'depth {MAX_DEPTH})...', flush=True)
    all_titles = []
    seen = set()
    with ThreadPoolExecutor(max_workers=min(WORKERS, 8)) as pool:
        for titles in pool.map(fetch_category_tree, CATEGORIES):
            for t in titles:
                if t not in seen:
                    seen.add(t)
                    all_titles.append(t)
    print(f'{len(all_titles)} unique titles collected', flush=True)
    if not all_titles:
        print('no titles — check ARTFRAME_CATEGORIES / network', flush=True)
        return 1

    random.shuffle(all_titles)

    # Resolve titles → URL in batches of 50 (Commons API limit).
    infos = []
    batches = [all_titles[i:i + 50] for i in range(0, len(all_titles), 50)]
    print(f'resolving URLs in {len(batches)} batches...', flush=True)
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for batch_infos in pool.map(fetch_image_infos, batches):
            infos.extend(batch_infos)
    print(f'{len(infos)} image URLs resolved', flush=True)

    added = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {
            pool.submit(download_one, t, u, w, h): t
            for (t, u, w, h) in infos
        }
        try:
            for fut in as_completed(futures):
                if added >= need:
                    break
                try:
                    result = fut.result()
                except Exception:
                    continue
                if not result:
                    continue
                title, data = result
                name = safe_filename(title)
                if not name or name in have:
                    continue
                dest = os.path.join(IMAGE_DIR, name)
                with open(dest, 'wb') as f:
                    f.write(data)
                have.add(name)
                added += 1
                print(f'[{added}/{need}] {title}', flush=True)
        finally:
            for f in futures:
                f.cancel()

    print(f'done: added {added}, on disk {len(existing_names())}', flush=True)
    return 0 if added else 2


if __name__ == '__main__':
    sys.exit(main())
