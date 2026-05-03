"""Markdown table-of-contents generator.

Parses ATX-style headings (``# …``) from a Markdown document and renders a
nested bullet list suitable for injection into the same or a different file via
the anchor injection system in :mod:`repo_release_tools.tools.inject`.

GitHub-flavoured anchor algorithm
----------------------------------
1. Strip leading/trailing whitespace from the heading title.
2. Lowercase the entire string.
3. Replace every space with ``-``.
4. Remove every character that is not ``[a-z0-9-]``.
5. Deduplicate by appending ``-1``, ``-2``, … to repeated anchors.

Fenced code blocks
------------------
Lines inside fenced code blocks (delimited by ` ``` ` or ``~~~``) are never
treated as headings, so code examples with ``#!`` shebangs or comment lines
are ignored.
"""

from __future__ import annotations

import re

_ATX_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_ANCHOR_STRIP_RE = re.compile(r"[^a-z0-9\-]")


def parse_headings(text: str) -> list[tuple[int, str]]:
    """Return a list of ``(level, title)`` pairs from ATX headings in *text*.

    Headings inside fenced code blocks are skipped.  Setext-style headings
    (underlined with ``===`` / ``---``) are not supported.

    Args:
        text: Raw Markdown text.

    Returns:
        Ordered list of ``(level, title)`` tuples where *level* is 1–6.
    """
    headings: list[tuple[int, str]] = []
    in_fence = False
    fence_char = ""

    for line in text.splitlines():
        if m := _FENCE_RE.match(line):
            char = m.group(1)[:3]
            if not in_fence:
                in_fence = True
                fence_char = char
            elif char == fence_char:
                in_fence = False
            continue

        if in_fence:
            continue

        if hm := _ATX_RE.match(line):
            level = len(hm.group(1))
            title = hm.group(2)
            headings.append((level, title))

    return headings


def heading_anchor(title: str, counts: dict[str, int]) -> str:
    """Return the GitHub-flavoured anchor for *title*, updating *counts* for deduplication.

    Args:
        title: Raw heading title (e.g. ``"My Module"``)
        counts: Mutable counter dict shared across all headings in one document.
            Pass an empty ``{}`` for the first heading and reuse for subsequent ones.

    Returns:
        Anchor string, e.g. ``"my-module"`` or ``"my-module-1"``.
    """
    slug = title.lower()
    slug = slug.replace(" ", "-")
    slug = _ANCHOR_STRIP_RE.sub("", slug)

    count = counts.get(slug, 0)
    counts[slug] = count + 1

    return slug if count == 0 else f"{slug}-{count}"


def render_toc(
    headings: list[tuple[int, str]],
    *,
    min_level: int = 1,
    max_level: int = 6,
) -> str:
    """Render a nested Markdown bullet TOC from *headings*.

    Args:
        headings: Sequence of ``(level, title)`` tuples as returned by
            :func:`parse_headings`.
        min_level: Headings at this level or higher (numerically) are included.
            Defaults to 1 (``#``).
        max_level: Headings at this level or lower (numerically) are included.
            Defaults to 6 (``######``).

    Returns:
        Rendered TOC as a Markdown string (no trailing newline), or an empty
        string when no headings fall within the requested range.
    """
    filtered = [(lvl, title) for lvl, title in headings if min_level <= lvl <= max_level]
    if not filtered:
        return ""

    counts: dict[str, int] = {}
    lines: list[str] = []
    base = filtered[0][0]

    for level, title in filtered:
        indent = "  " * (level - base)
        anchor = heading_anchor(title, counts)
        lines.append(f"{indent}- [{title}](#{anchor})")

    return "\n".join(lines)
