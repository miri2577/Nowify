#!/usr/bin/env python3
"""Pull a batch of artwork JPGs from the Metropolitan Museum of Art.

Uses the public Met Collection API (https://metmuseum.github.io/),
no auth, no key. Two tricks for speed:
  1) /search filters to hasImages=true AND isHighlight=true — ~2000
     curated works across all departments, most of them public-domain.
  2) Object details + image downloads run in a thread pool so the
     wall clock scales with latency of one request × N, not × total.

Stdlib only.
"""
import json
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

IMAGE_DIR = os.environ.get('ARTFRAME_DIR', '/var/lib/artframe/images')
KEEP_MAX = int(os.environ.get('ARTFRAME_KEEP', '40'))

API_BASE = 'https://collectionapi.metmuseum.org/public/collection/v1'

# Departments: 11=European Paintings, 14=American Paintings & Sculpture,
# 21=Modern & Contemporary Art, 19=Photographs, 9=Drawings & Prints
DEPT_IDS = os.environ.get('ARTFRAME_DEPTS', '11,14,21,19,9')

# Restrict to curated highlights (~2000 total)? Much higher PD hit rate.
HIGHLIGHTS_ONLY = os.environ.get('ARTFRAME_HIGHLIGHTS', '1') not in ('0', '')

WORKERS = int(os.environ.get('ARTFRAME_WORKERS', '32'))

UA = 'artframe/1.0 (+https://github.com/miri2577/Nowify)'

# Orientation filter: 'landscape', 'portrait', or 'any'.
ORIENTATION = os.environ.get('ARTFRAME_ORIENT', 'landscape').lower()

MAX_BYTES = 5 * 1024 * 1024   # skip images bigger than 5 MB


def http_get(url, timeout=30):
    # Met occasionally has literal spaces in image paths; safe-encode.
    safe_url = urllib.parse.quote(url, safe=':/?&=%#')
    req = urllib.request.Request(safe_url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_search_ids():
    """Aggregate candidate object IDs via /search across departments.

    Met's /search appears to cap results per query. Fan out with every
    letter of the alphabet as a separate query to maximise coverage;
    we dedupe on our end.
    """
    all_ids = []
    seen = set()
    queries = list('abcdefghijklmnopqrstuvwxyz')
    highlight = '&isHighlight=true' if HIGHLIGHTS_ONLY else ''

    def one(url):
        try:
            return json.loads(http_get(url, timeout=60)).get('objectIDs') or []
        except Exception:
            return []

    # Use a pool for the search fan-out too — 130 calls otherwise take
    # ages serially.
    urls = []
    for dept in DEPT_IDS.split(','):
        dept = dept.strip()
        if not dept:
            continue
        for q in queries:
            urls.append(
                f'{API_BASE}/search?q={q}'
                f'&hasImages=true{highlight}&departmentId={dept}'
            )
    with ThreadPoolExecutor(max_workers=min(WORKERS, 16)) as pool:
        for ids in pool.map(one, urls):
            for oid in ids:
                if oid not in seen:
                    seen.add(oid)
                    all_ids.append(oid)
    return all_ids


def jpeg_dims(data):
    if len(data) < 10 or data[:2] != b'\xff\xd8':
        return None
    i, n = 2, len(data)
    while i < n - 9:
        if data[i] != 0xff:
            i += 1
            continue
        m = data[i + 1]
        if 0xc0 <= m <= 0xcf and m not in (0xc4, 0xc8, 0xcc):
            h = (data[i + 5] << 8) | data[i + 6]
            w = (data[i + 7] << 8) | data[i + 8]
            return (w, h)
        seg = (data[i + 2] << 8) | data[i + 3]
        i += 2 + seg
    return None


def orientation_ok(w, h):
    if ORIENTATION == 'landscape':
        return w >= h
    if ORIENTATION == 'portrait':
        return h >= w
    return True


def existing_ids():
    if not os.path.isdir(IMAGE_DIR):
        return set()
    return {
        os.path.splitext(f)[0]
        for f in os.listdir(IMAGE_DIR)
        if f.endswith('.jpg')
    }


def fetch_candidate(oid):
    """Fetch object metadata and image in one worker call.

    Returns (oid, title, artist, bytes) or None to reject. Catches
    any network / parsing / encoding error so one bad entry doesn't
    kill the whole run.
    """
    try:
        obj = json.loads(http_get(f'{API_BASE}/objects/{oid}', timeout=30))
    except Exception:
        return None
    if not obj.get('isPublicDomain'):
        return None
    img_url = obj.get('primaryImageSmall') or obj.get('primaryImage')
    if not img_url:
        return None
    try:
        data = http_get(img_url, timeout=60)
    except Exception:
        return None
    if len(data) < 10_000 or len(data) > MAX_BYTES:
        return None
    dims = jpeg_dims(data)
    if dims and not orientation_ok(*dims):
        return None
    return (
        oid,
        (obj.get('title') or '').strip()[:50],
        (obj.get('artistDisplayName') or '').strip()[:30],
        data,
    )


def main():
    os.makedirs(IMAGE_DIR, exist_ok=True)
    have = existing_ids()
    need = max(0, KEEP_MAX - len(have))
    if need == 0:
        print(f'already have {len(have)} images, nothing to do', flush=True)
        return 0

    print(f'fetching Met search list (depts {DEPT_IDS}, '
          f'highlights={HIGHLIGHTS_ONLY})...', flush=True)
    all_ids = [i for i in fetch_search_ids() if str(i) not in have]
    random.shuffle(all_ids)
    print(f'{len(all_ids)} candidates, fetching with {WORKERS} workers',
          flush=True)

    if not all_ids:
        if HIGHLIGHTS_ONLY:
            print('no highlights candidates — rerun with '
                  'ARTFRAME_HIGHLIGHTS=0 for the full catalogue',
                  flush=True)
        return 1

    added = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(fetch_candidate, oid): oid for oid in all_ids}
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
                oid, title, artist, data = result
                dest = os.path.join(IMAGE_DIR, f'{oid}.jpg')
                with open(dest, 'wb') as f:
                    f.write(data)
                added += 1
                print(f'[{added}/{need}] {oid} — {artist} / {title}',
                      flush=True)
        finally:
            for f in futures:
                f.cancel()

    print(f'done: added {added}, on disk {len(existing_ids())}', flush=True)
    return 0 if added else 2


if __name__ == '__main__':
    sys.exit(main())
