"""Backward-compatibility re-export — canonical location is docs/formats/markdown.py."""

from repo_release_tools.docs.formats.markdown import (
    MarkdownLine,
    has_markdown_headings,
    heading_level,
    normalize_markdown_headings,
    parse_markdown_lines,
)

__all__ = [
    "MarkdownLine",
    "has_markdown_headings",
    "heading_level",
    "normalize_markdown_headings",
    "parse_markdown_lines",
]
