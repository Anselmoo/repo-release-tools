"""Lightweight Markdown helpers shared across docs rendering surfaces.

These helpers intentionally support only a narrow, dependency-free subset of
Markdown needed by repo-release-tools today:

- ATX headings (``#`` through ``######``)
- fenced code blocks using ````` or ``~~~``

The parser is line-based and conservative. It is designed to detect real
heading structure without interpreting fenced code contents as Markdown.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class MarkdownLine:
    """One parsed line from a lightweight Markdown scan."""

    kind: Literal["heading", "text", "fence"]
    text: str
    level: int | None = None


def heading_level(line: str) -> int | None:
    """Return the Markdown heading level for *line*, or ``None`` if not a heading."""
    stripped = line.lstrip()
    if not stripped.startswith("#"):
        return None
    hashes = len(stripped) - len(stripped.lstrip("#"))
    if hashes < 1 or hashes > 6:
        return None
    if len(stripped) <= hashes or stripped[hashes] != " ":
        return None
    return hashes


def parse_markdown_lines(text: str) -> tuple[MarkdownLine, ...]:
    """Parse *text* into lightweight Markdown-aware line records."""
    parsed: list[MarkdownLine] = []
    in_fence = False

    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            parsed.append(MarkdownLine(kind="fence", text=line))
            in_fence = not in_fence
            continue
        if in_fence:
            parsed.append(MarkdownLine(kind="fence", text=line))
            continue

        level = heading_level(line)
        if level is not None:
            parsed.append(
                MarkdownLine(kind="heading", text=stripped[level + 1 :].strip(), level=level)
            )
            continue
        parsed.append(MarkdownLine(kind="text", text=line))

    return tuple(parsed)


def has_markdown_headings(text: str) -> bool:
    """Return ``True`` when *text* contains Markdown headings outside fences."""
    return any(line.kind == "heading" for line in parse_markdown_lines(text))


def normalize_markdown_headings(text: str, *, min_level: int) -> str:
    """Shift headings in *text* so the shallowest heading nests under *min_level*."""
    parsed = parse_markdown_lines(text)
    heading_levels = [
        line.level for line in parsed if line.kind == "heading" and line.level is not None
    ]

    if not heading_levels:
        return text.strip()

    offset = max(min_level - min(heading_levels), 0)
    if offset == 0:
        return text.strip()

    normalized: list[str] = []
    for line in parsed:
        if line.kind != "heading" or line.level is None:
            normalized.append(line.text)
            continue
        normalized.append(f"{'#' * min(line.level + offset, 6)} {line.text}")

    return "\n".join(normalized).strip()
