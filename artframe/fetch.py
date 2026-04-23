#!/usr/bin/env python3
"""Pull a batch of artwork JPGs from the Metropolitan Museum of Art.

Uses the public Met Collection API (https://metmuseum.github.io/),
no auth, no key. Filters to works that are public-domain and have a
primary image; orientation filter is done locally by parsing the JPEG
SOF marker after download. Stdlib only.
"""
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request

IMAGE_DIR = os.environ.get('ARTFRAME_DIR', '/var/lib/artframe/images')
KEEP_MAX = int(os.environ.get('ARTFRAME_KEEP', '40'))

API_BASE = 'https://collectionapi.metmuseum.org/public/collection/v1'

# Departments: 11=European Paintings, 14=American Paintings & Sculpture,
# 21=Modern & Contemporary Art, 19=Photographs, 9=Drawings & Prints
DEPT_IDS = os.environ.get('ARTFRAME_DEPTS', '11,14,21,19,9')

UA = 'artframe/1.0 (+https://github.com/miri2577/Nowify)'

# Orientation filter: 'landscape', 'portrait', or 'any'.
ORIENTATION = os.environ.get('ARTFRAME_ORIENT', 'landscape').lower()

# Cap individual image download size (bytes) — some full-size images are
# 20+ MB which is wasteful on a Pi. Small versions are usually < 2 MB.
MAX_BYTES = 5 * 1024 * 1024


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_object_ids():
    """Aggregate IDs via /search?hasImages=true per department.

    /objects would return every record — mostly image-less, giving us a
    <1% hit rate. /search with hasImages=true narrows massively.
    """
    all_ids = []
    seen = set()
    queries = ['a', 'of', 'the']  # common-word queries, maximize coverage
    for dept in DEPT_IDS.split(','):
        dept = dept.strip()
        if not dept:
            continue
        for q in queries:
            url = (f'{API_BASE}/search?q={q}'
                   f'&hasImages=true&departmentId={dept}')
            try:
                raw = http_get(url, timeout=60)
                ids = json.loads(raw).get('objectIDs') or []
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
                continue
            for oid in ids:
                if oid not in seen:
                    seen.add(oid)
                    all_ids.append(oid)
            if len(all_ids) > 5000:
                break
    return all_ids


def fetch_object(oid):
    url = f'{API_BASE}/objects/{oid}'
    raw = http_get(url, timeout=30)
    return json.loads(raw)


def jpeg_dims(data):
    """Return (width, height) by parsing the JPEG SOF marker, or None."""
    if len(data) < 10 or data[:2] != b'\xff\xd8':
        return None
    i, n = 2, len(data)
    while i < n - 9:
        if data[i] != 0xff:
            i += 1
            continue
        m = data[i + 1]
        # Start Of Frame (non-DHT/DAC/JPG) → next 7 bytes contain H/W.
        if 0xc0 <= m <= 0xcf and m not in (0xc4, 0xc8, 0xcc):
            h = (data[i + 5] << 8) | data[i + 6]
            w = (data[i + 7] << 8) | data[i + 8]
            return (w, h)
        # Skip segment (length includes the length bytes themselves).
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


def main():
    os.makedirs(IMAGE_DIR, exist_ok=True)
    have = existing_ids()
    need = max(0, KEEP_MAX - len(have))
    if need == 0:
        print(f'already have {len(have)} images, nothing to do', flush=True)
        return 0

    print(f'fetching Met object list (departments {DEPT_IDS})...', flush=True)
    try:
        all_ids = fetch_object_ids()
    except (urllib.error.URLError, TimeoutError) as e:
        print(f'ERROR: cannot reach Met API: {e}', flush=True)
        return 1
    random.shuffle(all_ids)
    print(f'{len(all_ids)} candidate objects', flush=True)

    added = 0
    scanned = 0
    for oid in all_ids:
        if added >= need:
            break
        scanned += 1
        if scanned % 50 == 0:
            print(f'  … scanned {scanned}, kept {added}', flush=True)
        if str(oid) in have:
            continue
        try:
            obj = fetch_object(oid)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            continue
        if not obj.get('isPublicDomain'):
            continue
        img_url = obj.get('primaryImageSmall') or obj.get('primaryImage')
        if not img_url:
            continue
        try:
            data = http_get(img_url, timeout=60)
        except (urllib.error.URLError, TimeoutError):
            continue
        if len(data) < 10_000 or len(data) > MAX_BYTES:
            continue
        dims = jpeg_dims(data)
        if dims and not orientation_ok(*dims):
            continue

        dest = os.path.join(IMAGE_DIR, f'{oid}.jpg')
        with open(dest, 'wb') as f:
            f.write(data)
        title = (obj.get('title') or '').strip()[:50]
        artist = (obj.get('artistDisplayName') or '').strip()[:30]
        print(f'[{added + 1}/{need}] {oid} — {artist} / {title}',
              flush=True)
        added += 1
        time.sleep(0.05)   # polite pacing

    print(f'done: added {added}, on disk {len(existing_ids())}', flush=True)
    return 0 if added else 2


if __name__ == '__main__':
    sys.exit(main())
