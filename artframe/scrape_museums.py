#!/usr/bin/env python3
"""Download public-domain artworks from Met + AIC + Cleveland.

Three no-key APIs, four categories (painting / sculpture / drawing /
photograph), balanced quotas, metadata written to JSON. Stdlib only.

Env vars:
  MUSEUM_OUT      target directory (default: C:\\Users\\mirkorichter\\museum_images)
  MUSEUM_COUNT    total images (default: 250)
  MUSEUM_WORKERS  parallel download workers (default: 16)
  MUSEUM_UA       User-Agent string (default includes contact email)
"""
import concurrent.futures as cf
import json
import os
import random
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# ---------- config ----------
OUT_DIR = Path(os.environ.get(
    'MUSEUM_OUT',
    r'C:\Users\mirkorichter\museum_images',
))
IMG_DIR = OUT_DIR / 'images'
META_FILE = OUT_DIR / 'metadata.json'

TARGET = int(os.environ.get('MUSEUM_COUNT', '250'))
WORKERS = int(os.environ.get('MUSEUM_WORKERS', '16'))
UA = os.environ.get(
    'MUSEUM_UA',
    'ArtframeScraper/1.0 (miri2577@googlemail.com)',
)

MIN_BYTES = 300_000
MAX_BYTES = 10 * 1024 * 1024

ALL_CATEGORIES = ('painting', 'sculpture', 'drawing', 'photograph')

# MUSEUM_CATEGORIES restricts the run to a subset (comma-separated).
# Invaluable for per-category runs into their own output folder:
#   MUSEUM_CATEGORIES=painting MUSEUM_COUNT=250 MUSEUM_OUT=...\paintings
_raw_cats = os.environ.get('MUSEUM_CATEGORIES', '').strip().lower()
if _raw_cats:
    picked = [c.strip() for c in _raw_cats.split(',') if c.strip()]
    bad = [c for c in picked if c not in ALL_CATEGORIES]
    if bad:
        raise SystemExit(
            f'MUSEUM_CATEGORIES: unknown {bad}. valid: {ALL_CATEGORIES}'
        )
    CATEGORIES = tuple(picked)
else:
    CATEGORIES = ALL_CATEGORIES

# MUSEUM_WEIGHTS — same order as CATEGORIES. Absolute counts if they
# sum to >= TARGET; otherwise weights scaled to TARGET.
_raw_weights = os.environ.get('MUSEUM_WEIGHTS', '').strip()
if _raw_weights:
    _ws = [int(x) for x in _raw_weights.split(',')]
    if len(_ws) != len(CATEGORIES):
        raise SystemExit(
            f'MUSEUM_WEIGHTS needs {len(CATEGORIES)} values '
            f'(one per active category)'
        )
    total_w = sum(_ws)
    if total_w >= TARGET:
        QUOTAS = dict(zip(CATEGORIES, _ws))
        TARGET = total_w
    else:
        QUOTAS = {c: round(TARGET * w / total_w)
                  for c, w in zip(CATEGORIES, _ws)}
else:
    per = TARGET // len(CATEGORIES)
    rem = TARGET - per * len(CATEGORIES)
    QUOTAS = {c: per + (1 if i < rem else 0)
              for i, c in enumerate(CATEGORIES)}


# ---------- http ----------
def http_get(url, headers=None, timeout=60):
    hdrs = {'User-Agent': UA}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def http_json(url, headers=None, timeout=60):
    return json.loads(http_get(url, headers, timeout).decode('utf-8'))


# ---------- Met Museum ----------
MET_BASE = 'https://collectionapi.metmuseum.org/public/collection/v1'
MET_MEDIUM = {
    'painting':   'Paintings',
    'sculpture':  'Sculpture',
    'drawing':    'Drawings',
    'photograph': 'Photographs',
}


def met_search_ids(category, sample_size=150):
    """Returns up to sample_size random object IDs in this category."""
    medium = MET_MEDIUM[category]
    params = {
        'q': category,
        'hasImages': 'true',
        'medium': medium,
    }
    url = MET_BASE + '/search?' + urllib.parse.urlencode(params)
    try:
        data = http_json(url)
    except Exception as e:
        print(f'[met] search {category} failed: {e}', flush=True)
        return []
    ids = data.get('objectIDs') or []
    random.shuffle(ids)
    return ids[:sample_size]


def met_fetch_detail(objid, category):
    try:
        o = http_json(f'{MET_BASE}/objects/{objid}', timeout=30)
    except Exception:
        return None
    if not o.get('isPublicDomain'):
        return None
    # primaryImage (original) sits at 1-5 MB for most paintings/drawings
    # — perfect. Originals that exceed MAX_BYTES get rejected in
    # download() and the slot goes to a different candidate. web-large
    # looked attractive on paper but serves aggressively-compressed 50-
    # 200 KB files that fall below MIN_BYTES. primaryImageSmall is the
    # 500 px thumbnail, useless for a display frame.
    img = o.get('primaryImage') or ''
    if not img:
        return None
    return {
        'id': f'met_{objid}',
        'source': 'met',
        'category': category,
        'title':  o.get('title') or 'Untitled',
        'artist': o.get('artistDisplayName') or 'Unknown',
        'date':   o.get('objectDate') or '',
        'medium': o.get('medium') or '',
        'dimensions': o.get('dimensions') or '',
        'museum': 'Metropolitan Museum of Art',
        'credit': o.get('creditLine') or 'Open Access CC0',
        'license': 'CC0',
        'source_url': o.get('objectURL') or '',
        'image_url':  img,
    }


# ---------- Art Institute of Chicago ----------
AIC_BASE = 'https://api.artic.edu/api/v1'

# AIC's classification_title is a free-text field — ES term queries on
# it return nothing. Use q=<category> + client-side filter against this
# allow-list of substrings (lowercase). Covers the common medium
# descriptors that AIC actually stores per category.
AIC_CLS_ACCEPT = {
    'painting':   ('painting', 'oil on', 'tempera', 'fresco', 'acrylic',
                   'watercolor', 'gouache'),
    'sculpture':  ('sculpture', 'bronze', 'marble', 'terracotta',
                   'ceramic', 'stoneware', 'porcelain', 'jade',
                   'wood carving'),
    'drawing':    ('drawing', 'pastel', 'charcoal', 'pen and ink',
                   'ink on', 'sketch', 'chalk'),
    'photograph': ('photograph', 'photography', 'albumen', 'gelatin',
                   'daguerreotype', 'tintype', 'platinum print'),
}


def _aic_matches_category(item, category):
    cls = (item.get('classification_title') or '').lower()
    med = (item.get('medium_display') or '').lower()
    needles = AIC_CLS_ACCEPT[category]
    return any(n in cls or n in med for n in needles)


def aic_search(category, per_page=100, pages=6):
    fields = (
        'id,title,artist_display,date_display,medium_display,'
        'classification_title,image_id,is_public_domain,credit_line,'
        'dimensions'
    )
    out = []
    for page in range(1, pages + 1):
        params = {
            'q':      category,
            'limit':  str(per_page),
            'page':   str(page),
            'fields': fields,
        }
        url = AIC_BASE + '/artworks/search?' + urllib.parse.urlencode(params)
        try:
            data = http_json(url, headers={'AIC-User-Agent': UA})
        except Exception as e:
            print(f'[aic] search {category} page {page} failed: {e}', flush=True)
            break
        items = data.get('data') or []
        if not items:
            break
        for it in items:
            if not it.get('is_public_domain'):
                continue
            if not it.get('image_id'):
                continue
            if not _aic_matches_category(it, category):
                continue
            out.append(it)
        if len(items) < per_page:
            break
    random.shuffle(out)
    return out


def aic_to_art(item, category):
    image_id = item.get('image_id')
    if not image_id:
        return None
    img_url = f'https://www.artic.edu/iiif/2/{image_id}/full/2000,/0/default.jpg'
    return {
        'id': f'aic_{item["id"]}',
        'source': 'aic',
        'category': category,
        'title':  item.get('title') or 'Untitled',
        'artist': item.get('artist_display') or 'Unknown',
        'date':   item.get('date_display') or '',
        'medium': item.get('medium_display') or '',
        'dimensions': item.get('dimensions') or '',
        'museum': 'Art Institute of Chicago',
        'credit': item.get('credit_line') or 'Public Domain',
        'license': 'CC0',
        'source_url': f'https://www.artic.edu/artworks/{item["id"]}',
        'image_url':  img_url,
    }


# ---------- Cleveland Museum of Art ----------
CMA_BASE = 'https://openaccess-api.clevelandart.org/api'
CMA_TYPE = {
    'painting':   'Painting',
    'sculpture':  'Sculpture',
    'drawing':    'Drawing',
    'photograph': 'Photograph',
}


def cma_search(category, limit=200):
    t = CMA_TYPE[category]
    # random skip pulls different slices each run
    params = {
        'has_image': '1',
        'cc0':       '1',
        'type':      t,
        'limit':     str(limit),
        'skip':      str(random.randint(0, 1500)),
    }
    url = CMA_BASE + '/artworks/?' + urllib.parse.urlencode(params)
    try:
        data = http_json(url)
    except Exception as e:
        print(f'[cma] search {category} failed: {e}', flush=True)
        return []
    return data.get('data') or []


def cma_to_art(item, category):
    imgs = item.get('images') or {}
    # print (~3000px, 2-5 MB) first — web (~1500px) is thumbnail-ish.
    # full (originals) can be 50+ MB and busts the 10 MB cap; skip it.
    img_url = (
        (imgs.get('print') or {}).get('url')
        or (imgs.get('web') or {}).get('url')
    )
    if not img_url:
        return None
    creators = item.get('creators') or []
    artist = (creators[0].get('description') if creators else '') or 'Unknown'
    return {
        'id': f'cma_{item.get("id")}',
        'source': 'cma',
        'category': category,
        'title':  item.get('title') or 'Untitled',
        'artist': artist,
        'date':   item.get('creation_date') or '',
        'medium': item.get('technique') or item.get('type') or '',
        'dimensions': item.get('measurements') or '',
        'museum': 'Cleveland Museum of Art',
        'credit': 'Open Access CC0',
        'license': 'CC0',
        'source_url': item.get('url') or '',
        'image_url':  img_url,
    }


# ---------- download ----------
_SLUG_RE = re.compile(r'[^\w]+', re.UNICODE)


def safe_filename(art):
    num = art['id'].split('_', 1)[1]
    base = f'{art["source"]}_{num}'
    slug = _SLUG_RE.sub('_', art.get('title') or '').strip('_')[:60]
    return f'{base}_{slug}.jpg' if slug else f'{base}.jpg'


def download(art):
    # AIC's IIIF server rejects requests without the AIC-User-Agent
    # header (HTTP 403). Other sources ignore it.
    extra = {'AIC-User-Agent': UA} if art['source'] == 'aic' else None
    try:
        data = http_get(art['image_url'], headers=extra, timeout=120)
    except Exception as e:
        return (art, None, f'{type(e).__name__}: {e}')
    if len(data) < MIN_BYTES or len(data) > MAX_BYTES:
        return (art, None, f'size {len(data)}B')
    if data[:3] != b'\xff\xd8\xff':
        return (art, None, 'not jpeg')
    return (art, data, None)


# ---------- candidate pool ----------
def gather_candidates():
    """Fan out search calls, return {category: [art dicts]}."""
    pool = {c: [] for c in CATEGORIES}
    met_ids = {}

    with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        aic_futs = {ex.submit(aic_search, c): c for c in CATEGORIES}
        cma_futs = {ex.submit(cma_search, c): c for c in CATEGORIES}
        met_futs = {ex.submit(met_search_ids, c): c for c in CATEGORIES}

        for fut, cat in aic_futs.items():
            try:
                for it in fut.result():
                    art = aic_to_art(it, cat)
                    if art:
                        pool[cat].append(art)
            except Exception as e:
                print(f'[aic] {cat} err: {e}', flush=True)

        for fut, cat in cma_futs.items():
            try:
                for it in fut.result():
                    art = cma_to_art(it, cat)
                    if art:
                        pool[cat].append(art)
            except Exception as e:
                print(f'[cma] {cat} err: {e}', flush=True)

        for fut, cat in met_futs.items():
            try:
                met_ids[cat] = fut.result()
            except Exception as e:
                print(f'[met] ids {cat} err: {e}', flush=True)
                met_ids[cat] = []

    # Met needs a second pass — only ~10-30 % of IDs are public domain,
    # so we pull details in parallel and filter post-hoc.
    with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        jobs = []
        for cat, ids in met_ids.items():
            for oid in ids:
                jobs.append((cat, ex.submit(met_fetch_detail, oid, cat)))
        for cat, fut in jobs:
            try:
                art = fut.result()
            except Exception:
                continue
            if art:
                pool[cat].append(art)

    return pool


# ---------- orchestration ----------
def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    IMG_DIR.mkdir(parents=True, exist_ok=True)

    existing = []
    existing_ids = set()
    existing_files = set()
    if META_FILE.exists():
        try:
            existing = json.loads(META_FILE.read_text(encoding='utf-8'))
            existing_ids = {m['id'] for m in existing}
            existing_files = {m.get('filename') for m in existing if m.get('filename')}
        except Exception:
            existing = []

    quota_str = ', '.join(f'{c}={QUOTAS[c]}' for c in CATEGORIES)
    print(f'target: {TARGET} images ({quota_str})', flush=True)
    print(f'output: {OUT_DIR}', flush=True)
    print('gathering candidates from Met + AIC + Cleveland...', flush=True)

    pool = gather_candidates()

    # dedupe per category on (title, artist), drop already-downloaded ids
    def norm(s): return (s or '').lower().strip()
    for cat in CATEGORIES:
        seen = set()
        uniq = []
        for a in pool[cat]:
            if a['id'] in existing_ids:
                continue
            k = (norm(a['title']), norm(a['artist']))
            if k in seen:
                continue
            seen.add(k)
            uniq.append(a)
        random.shuffle(uniq)
        pool[cat] = uniq
        by_src = {'met': 0, 'aic': 0, 'cma': 0}
        for a in uniq:
            by_src[a['source']] += 1
        print(f'  {cat:11s}: {len(uniq):4d} candidates  '
              f'(met={by_src["met"]}, aic={by_src["aic"]}, cma={by_src["cma"]})',
              flush=True)

    if not any(pool[c] for c in CATEGORIES):
        print('no candidates — network down or all APIs failing', flush=True)
        return 1

    quotas = dict(QUOTAS)
    done_cat = {c: 0 for c in CATEGORIES}

    def pick():
        """Next art from the category with the biggest remaining gap."""
        best_cat, best_gap = None, -1
        for c in CATEGORIES:
            gap = quotas[c] - done_cat[c]
            if gap > best_gap and pool[c]:
                best_gap, best_cat = gap, c
        if best_cat is None or best_gap <= 0:
            return None
        return pool[best_cat].pop()

    saved = []
    failed = 0

    with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = set()
        for _ in range(WORKERS * 2):
            art = pick()
            if not art:
                break
            futs.add(ex.submit(download, art))

        while futs:
            done, futs = cf.wait(futs, return_when=cf.FIRST_COMPLETED)
            for fut in done:
                try:
                    art, data, err = fut.result()
                except Exception as e:
                    failed += 1
                    continue

                if data is None:
                    failed += 1
                    print(f'  skip {art["source"]:4s} {art["id"]:>18}: {err}',
                          flush=True)
                elif done_cat[art['category']] < quotas[art['category']]:
                    name = safe_filename(art)
                    # avoid filename collisions across runs
                    suffix = 1
                    candidate = name
                    while candidate in existing_files or (IMG_DIR / candidate).exists():
                        stem = name[:-4]
                        candidate = f'{stem}_{suffix}.jpg'
                        suffix += 1
                    name = candidate
                    (IMG_DIR / name).write_bytes(data)
                    existing_files.add(name)
                    art['filename'] = name
                    art['bytes'] = len(data)
                    saved.append(art)
                    done_cat[art['category']] += 1
                    progress = sum(done_cat.values())
                    print(f'[{progress:3d}/{TARGET}] {art["category"]:11s} '
                          f'{art["source"]:4s} {(art["artist"] or "?")[:26]:26s} '
                          f'· {(art["title"] or "?")[:50]}',
                          flush=True)

                if all(done_cat[c] >= quotas[c] for c in CATEGORIES):
                    break

                nxt = pick()
                if nxt:
                    futs.add(ex.submit(download, nxt))

            if all(done_cat[c] >= quotas[c] for c in CATEGORIES):
                for f in futs:
                    f.cancel()
                futs = set()
                break

    all_meta = existing + saved
    META_FILE.write_text(
        json.dumps(all_meta, indent=2, ensure_ascii=False),
        encoding='utf-8',
    )

    print('')
    print(f'done. {len(saved)} new, {len(all_meta)} total, '
          f'{failed} download failures.')
    print('per category: ' + ', '.join(f'{c}={done_cat[c]}' for c in CATEGORIES))
    print(f'images:   {IMG_DIR}')
    print(f'metadata: {META_FILE}')
    return 0 if saved else 2


if __name__ == '__main__':
    sys.exit(main())
