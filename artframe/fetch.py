#!/usr/bin/env python3
"""Pull a batch of artwork JPGs from the Art Institute of Chicago.

Keeps IMAGE_DIR populated with up to KEEP_MAX recent images. Each run
fetches a random page from the public AIC API and tops up any missing
slots. Uses stdlib only (urllib) so the Pi doesn't need pip.
"""
import json
import os
import random
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request

IMAGE_DIR = '/var/lib/artframe/images'
KEEP_MAX = 40
WIDTH = 1920  # IIIF width; height scales to keep aspect

API_URL = 'https://api.artic.edu/api/v1/artworks'
IIIF_BASE = 'https://www.artic.edu/iiif/2'
UA = 'artframe/1.0 (+https://github.com/miri2577/Nowify)'

# Orientation filter: 'landscape', 'portrait', or 'any'.
ORIENTATION = os.environ.get('ARTFRAME_ORIENT', 'landscape').lower()


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_page(page):
    fields = 'id,title,artist_display,image_id,thumbnail'
    url = f'{API_URL}?page={page}&limit=50&fields={fields}'
    raw = http_get(url)
    data = json.loads(raw).get('data', [])
    return [a for a in data if a.get('image_id') and a.get('thumbnail')]


def orientation_ok(thumb):
    w = thumb.get('width') or 0
    h = thumb.get('height') or 0
    if not w or not h:
        return False
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


def prune(keep):
    if not os.path.isdir(IMAGE_DIR):
        return
    files = [
        os.path.join(IMAGE_DIR, f)
        for f in os.listdir(IMAGE_DIR)
        if f.endswith('.jpg')
    ]
    files.sort(key=os.path.getmtime)
    while len(files) > keep:
        victim = files.pop(0)
        try:
            os.remove(victim)
            print(f'pruned {os.path.basename(victim)}', flush=True)
        except OSError:
            pass


def download_one(art):
    image_id = art['image_id']
    url = f'{IIIF_BASE}/{image_id}/full/{WIDTH},/0/default.jpg'
    dest = os.path.join(IMAGE_DIR, f'{image_id}.jpg')
    if os.path.exists(dest):
        return False
    try:
        data = http_get(url, timeout=60)
    except (urllib.error.URLError, TimeoutError) as e:
        print(f'skip {image_id}: {e}', flush=True)
        return False
    if len(data) < 10_000:  # guard: AIC 404 is tiny HTML/JSON
        return False
    fd, tmp = tempfile.mkstemp(
        prefix='.', suffix='.jpg', dir=IMAGE_DIR
    )
    with os.fdopen(fd, 'wb') as f:
        f.write(data)
    os.replace(tmp, dest)
    title = (art.get('title') or '').strip()[:60]
    print(f'saved {image_id} — {title}', flush=True)
    return True


def main():
    os.makedirs(IMAGE_DIR, exist_ok=True)
    have = existing_ids()
    need = max(0, KEEP_MAX - len(have))
    if need == 0:
        print(f'already have {len(have)} images, nothing to do', flush=True)
        return 0

    added = 0
    tries = 0
    while added < need and tries < 6:
        tries += 1
        page = random.randint(1, 200)
        try:
            items = fetch_page(page)
        except (urllib.error.URLError, TimeoutError) as e:
            print(f'page {page} failed: {e}', flush=True)
            time.sleep(2)
            continue
        items = [a for a in items if orientation_ok(a.get('thumbnail', {}))]
        random.shuffle(items)
        for art in items:
            if added >= need:
                break
            if art['image_id'] in have:
                continue
            if download_one(art):
                have.add(art['image_id'])
                added += 1

    prune(KEEP_MAX)
    print(f'done: added {added}, on disk {len(existing_ids())}', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
