"""Regenerate all SVG badge files using make_badge_svg (bypasses the cache).

Run with:
    uv run python scripts/regen_badges.py

This writes freshly-generated flat pill badges to:
  - src/repo_release_tools/assets/badges/  (package data — source of truth)
  - docs/assets/badges/                    (Jekyll site assets)

Use this whenever the cached files in assets/badges/ are stale, icon-only,
or missing entries after adding new keys to KNOWN_LABEL_KEYS.
"""

from __future__ import annotations

from pathlib import Path

from repo_release_tools.tools.platform import (
    LANGUAGE_LABELS,
    PLATFORM_LABELS,
    REGISTRY_LABELS,
    make_badge_svg,
)

VARIANTS = ["color", "dark", "light", "reto-dark", "reto-light"]

# Deduplicated ordered keys: platform first, then registry, then language.
# bash and java appear in both PLATFORM_LABELS and LANGUAGE_LABELS; they are
# covered by the platform pass and skipped on the language pass.
_seen: set[str] = set()
ALL_KEYS: list[str] = []
for _d in (PLATFORM_LABELS, REGISTRY_LABELS, LANGUAGE_LABELS):
    for _k in _d:
        if _k not in _seen:
            _seen.add(_k)
            ALL_KEYS.append(_k)

PKG_DIR = Path("src/repo_release_tools/assets/badges")
DOCS_DIR = Path("docs/assets/badges")


def main() -> None:
    """Generate all badge SVG files and write them to the package-data and docs directories."""
    PKG_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    total = 0
    for key in ALL_KEYS:
        for variant in VARIANTS:
            svg = make_badge_svg(key, variant=variant)
            suffix = f"-{variant}" if variant != "color" else ""
            fname = f"{key}{suffix}.svg"
            (PKG_DIR / fname).write_text(svg, encoding="utf-8")
            (DOCS_DIR / fname).write_text(svg, encoding="utf-8")
            total += 1
            print(f"  wrote  {fname}")

    print(f"\nDone: {len(ALL_KEYS)} keys × {len(VARIANTS)} variants = {total} files")


if __name__ == "__main__":
    main()
