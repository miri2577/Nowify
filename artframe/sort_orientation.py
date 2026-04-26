#!/usr/bin/env python3
"""Sort a scraped image set into landscape/ and portrait/ subfolders by
aspect ratio. Splits metadata.json so each subfolder is a self-contained
input that build.sh can consume directly via ARTFRAME_IMAGES_SRC.

Usage:
    python sort_orientation.py <root-dir>

Reads:
    <root>/images/*.jpg
    <root>/metadata.json   (optional)

Writes:
    <root>/landscape/images/*.jpg
    <root>/landscape/metadata.json
    <root>/portrait/images/*.jpg
    <root>/portrait/metadata.json

Originals stay in place — re-runnable, idempotent.
"""
import json
import shutil
import struct
import sys
from pathlib import Path


def jpeg_dimensions(path):
    """Return (width, height) by parsing the JPEG SOF marker. Stdlib only."""
    try:
        with open(path, 'rb') as f:
            if f.read(2) != b'\xff\xd8':
                return None
            while True:
                b = f.read(1)
                if not b:
                    return None
                if b != b'\xff':
                    continue
                # Skip 0xFF filler bytes between marker and segment
                while b == b'\xff':
                    b = f.read(1)
                    if not b:
                        return None
                marker = b[0]
                # SOF0..15 except DHT(0xc4), JPG(0xc8), DAC(0xcc)
                if 0xc0 <= marker <= 0xcf and marker not in (0xc4, 0xc8, 0xcc):
                    f.read(3)               # segment length + sample precision
                    blob = f.read(4)
                    if len(blob) < 4:
                        return None
                    h, w = struct.unpack('>HH', blob)
                    return (w, h)
                # Other segment: skip its payload
                length_bytes = f.read(2)
                if len(length_bytes) < 2:
                    return None
                length = struct.unpack('>H', length_bytes)[0]
                f.seek(length - 2, 1)
    except OSError:
        return None


def main():
    if len(sys.argv) != 2:
        print(f'usage: {sys.argv[0]} <root-dir>', file=sys.stderr)
        return 1
    root = Path(sys.argv[1])
    src_images = root / 'images'
    if not src_images.is_dir():
        print(f'ERROR: {src_images} not found', file=sys.stderr)
        return 1

    meta_by_filename = {}
    src_meta_path = root / 'metadata.json'
    if src_meta_path.is_file():
        meta_list = json.loads(src_meta_path.read_text(encoding='utf-8'))
        meta_by_filename = {
            m.get('filename'): m
            for m in meta_list
            if m.get('filename')
        }

    landscape_dir = root / 'landscape' / 'images'
    portrait_dir  = root / 'portrait'  / 'images'
    landscape_dir.mkdir(parents=True, exist_ok=True)
    portrait_dir.mkdir(parents=True, exist_ok=True)

    landscape_meta, portrait_meta = [], []
    n_landscape = n_portrait = n_skipped = 0

    jpgs = sorted(src_images.glob('*.jpg'))
    for jpg in jpgs:
        dims = jpeg_dimensions(jpg)
        if not dims:
            n_skipped += 1
            continue
        w, h = dims
        portrait = h > w
        target_dir = portrait_dir if portrait else landscape_dir
        target_meta = portrait_meta if portrait else landscape_meta

        dest = target_dir / jpg.name
        if not dest.exists():
            shutil.copy2(jpg, dest)

        meta = meta_by_filename.get(jpg.name)
        if meta:
            meta = dict(meta)
            meta['width']  = w
            meta['height'] = h
            target_meta.append(meta)

        if portrait:
            n_portrait += 1
        else:
            n_landscape += 1

    (root / 'landscape' / 'metadata.json').write_text(
        json.dumps(landscape_meta, indent=2, ensure_ascii=False),
        encoding='utf-8',
    )
    (root / 'portrait' / 'metadata.json').write_text(
        json.dumps(portrait_meta, indent=2, ensure_ascii=False),
        encoding='utf-8',
    )

    print(f'landscape: {n_landscape:4d} images  → {landscape_dir}')
    print(f'portrait : {n_portrait:4d} images  → {portrait_dir}')
    if n_skipped:
        print(f'skipped  : {n_skipped:4d} (could not read dimensions)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
