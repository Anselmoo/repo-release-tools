#!/usr/bin/env python3
"""Sync selected simple-icons SVGs into docs/assets/icons and create badge variants.

Usage: python3 scripts/sync_simple_icons.py [--include-secondary] [--generate-badges]

This script uses the GitHub contents API to locate icon files under the simple-icons
repo and writes them into docs/assets/icons. It creates simple placeholder badge
variants by copying the same SVG with different suffixes. ATTRIBUTION.md is written
with the pinned SHAs returned by the API.
"""
import argparse
import base64
import json
import os
import sys
from urllib.request import urlopen, Request
from urllib.error import HTTPError

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICONS_DIR = os.path.join(REPO_ROOT, 'docs', 'assets', 'icons')
BADGES_DIR = os.path.join(REPO_ROOT, 'docs', 'assets', 'badges')
README_BADGES_DIR = os.path.join(REPO_ROOT, 'docs', 'assets', 'readme-badges')
ATTRIBUTION_PATH = os.path.join(ICONS_DIR, 'ATTRIBUTION.md')

PRIMARY = ['python','pypi','npm','go','rust','nuget','docker','githubactions']
SECONDARY = ['typescript','ruby','php','csharp','cplusplus','swift','kotlin','dart','perl','scala','haskell','crates-io','rubygems','packagist','pub','cpan','hex']

# Candidate slug alternatives to try for fuzzy names
CANDIDATES = {
    'csharp': ['csharp'],
    'cplusplus': ['cplusplus','cpp'],
    'crates-io': ['crates-io','crates'],
    'pub': ['pub','dart'],
    'githubactions': ['githubactions','github-actions'],
    'pypi': ['pypi'],
    'nuget': ['nuget'],
}

API_BASE = 'https://api.github.com/repos/simple-icons/simple-icons/contents/icons/{}?ref=master'
RAW_BASE = 'https://raw.githubusercontent.com/simple-icons/simple-icons/refs/heads/master/icons/{}'

HEADERS = {'User-Agent': 'rrt-sync-script'}


def _try_fetch_slug(slug):
    url = API_BASE.format(slug)
    req = Request(url, headers=HEADERS)
    try:
        with urlopen(req) as r:
            data = json.load(r)
            # data contains 'content' (base64), 'sha', 'download_url'
            return data
    except HTTPError as e:
        return None


def write_svg_from_api(data, out_path):
    content_b64 = data.get('content','')
    content = base64.b64decode(content_b64)
    with open(out_path, 'wb') as fh:
        fh.write(content)


def ensure_dirs():
    os.makedirs(ICONS_DIR, exist_ok=True)
    os.makedirs(BADGES_DIR, exist_ok=True)
    os.makedirs(README_BADGES_DIR, exist_ok=True)


def make_variants(src_path, slug):
    # Create simple placeholder variants: copies of the original file
    variants = ['', '-dark', '-light', '-reto-dark', '-reto-light']
    for v in variants:
        dest = os.path.join(BADGES_DIR, f"{slug}{v}.svg")
        # copy src -> dest
        with open(src_path, 'rb') as r, open(dest, 'wb') as w:
            w.write(r.read())
    # For README badges, create pypi-reto-dark/light if slug is pypi
    if slug == 'pypi':
        for v in ['-reto-dark','-reto-light']:
            dest = os.path.join(README_BADGES_DIR, f"pypi{v}.svg")
            with open(src_path, 'rb') as r, open(dest, 'wb') as w:
                w.write(r.read())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--include-secondary', action='store_true')
    parser.add_argument('--generate-badges', action='store_true')
    args = parser.parse_args()

    ensure_dirs()
    targets = list(PRIMARY)
    if args.include_secondary:
        targets += SECONDARY

    attribution = []

    for name in targets:
        tried = []
        candidates = CANDIDATES.get(name, [name])
        # If the single name contains a dash or is exact, include it first
        if name not in candidates:
            candidates.insert(0, name)
        data = None
        used_slug = None
        for slug in candidates:
            tried.append(slug)
            data = _try_fetch_slug(slug)
            if data:
                used_slug = slug
                break
        if not data:
            # try the raw slug directly as last resort
            data = _try_fetch_slug(name)
            if data:
                used_slug = name
        if not data:
            print(f"WARN: icon not found for '{name}' (tried: {tried})", file=sys.stderr)
            continue
        filename = f"{used_slug}.svg"
        out_path = os.path.join(ICONS_DIR, filename)
        write_svg_from_api(data, out_path)
        sha = data.get('sha')
        download_url = data.get('download_url') or RAW_BASE.format(used_slug)
        attribution.append((name, used_slug, sha, download_url))
        print(f"Wrote {out_path} (slug={used_slug}, sha={sha})")
        if args.generate_badges:
            make_variants(out_path, used_slug)

    # write ATTRIBUTION.md
    if attribution:
        with open(ATTRIBUTION_PATH, 'w') as a:
            a.write('# Attribution: simple-icons assets\n\n')
            a.write('Icons fetched from simple-icons (https://github.com/simple-icons/simple-icons)\n\n')
            for name, slug, sha, url in attribution:
                a.write(f"- {name}: slug={slug}, sha={sha}, url={url}\n")
        print(f"Wrote attribution to {ATTRIBUTION_PATH}")
    else:
        print('No icons written; attribution not created', file=sys.stderr)

if __name__ == '__main__':
    main()
