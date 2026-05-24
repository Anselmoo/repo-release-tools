"""Documentation subsystem package for repo-release-tools."""

from .extractor import DocEntry, extract_docs, extract_docs_from_dir, lang_for_path
from .formats import render
from .formats.markdown import (
    MarkdownLine,
    has_markdown_headings,
    heading_level,
    normalize_markdown_headings,
    parse_markdown_lines,
)

__all__ = [
    "DocEntry",
    "MarkdownLine",
    "extract_docs",
    "extract_docs_from_dir",
    "has_markdown_headings",
    "heading_level",
    "lang_for_path",
    "normalize_markdown_headings",
    "parse_markdown_lines",
    "render",
]
