"""Tests for lightweight Markdown utilities used by docs rendering."""

from __future__ import annotations

from repo_release_tools.docs.formats.markdown import (
    has_markdown_headings,
    heading_level,
    normalize_markdown_headings,
    parse_markdown_lines,
)


def test_heading_level_rejects_invalid_heading_variants() -> None:
    assert heading_level("####### Too many") is None
    assert heading_level("###No space") is None


def test_has_markdown_headings_ignores_fenced_blocks() -> None:
    text = "```python\n# fenced heading\n```\nplain text"

    assert has_markdown_headings(text) is False


def test_has_markdown_headings_detects_real_headings() -> None:
    assert has_markdown_headings("# Title\n\nBody") is True


def test_parse_markdown_lines_marks_heading_and_fence_lines() -> None:
    parsed = parse_markdown_lines("# Title\n\n```text\n# inside fence\n```\nBody")

    assert parsed[0].kind == "heading"
    assert parsed[0].level == 1
    assert parsed[2].kind == "fence"
    assert parsed[3].kind == "fence"
    assert parsed[-1].kind == "text"


def test_normalize_markdown_headings_returns_trimmed_text_without_headings() -> None:
    text = "plain text\n\n```python\n# fenced heading\n```\n"

    assert normalize_markdown_headings(text, min_level=2) == text.strip()


def test_normalize_markdown_headings_leaves_already_nested_headings_unchanged() -> None:
    text = "## Title\n\nBody\n"

    assert normalize_markdown_headings(text, min_level=2) == text.strip()


def test_normalize_markdown_headings_raises_shallow_heading_level() -> None:
    text = "# Title\n\n## Section\n"

    assert normalize_markdown_headings(text, min_level=3) == "### Title\n\n#### Section"
