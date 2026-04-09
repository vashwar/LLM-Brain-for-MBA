#!/usr/bin/env python3
"""
Initialize image_tags.json with all PNG files from the charts folder.
Run once to create the file, then fill in captions manually.

Usage:
    python init_image_tags.py
"""

import json
from pathlib import Path

CHARTS_DIR = Path('MBAWiki') / 'assets' / 'charts'
TAGS_FILE = CHARTS_DIR / 'image_tags.json'


def main():
    images = sorted([f.name for f in CHARTS_DIR.glob('*.png')])

    if not images:
        print("No PNG files found in MBAWiki/assets/charts/")
        return

    # Load existing tags if any (don't overwrite captions already filled in)
    existing = {}
    if TAGS_FILE.exists():
        with open(TAGS_FILE, 'r', encoding='utf-8') as f:
            existing = json.load(f)

    tags = {}
    new_count = 0
    for img in images:
        if img in existing:
            tags[img] = existing[img]
        else:
            tags[img] = []
            new_count += 1

    with open(TAGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(tags, f, indent=2, ensure_ascii=False)

    print(f"✅ {TAGS_FILE}")
    print(f"   {len(images)} images total, {new_count} new entries added")
    print(f"\n   Fill in captions like:")
    print(f'   "{images[0]}": ["caption here"]')


if __name__ == '__main__':
    main()
