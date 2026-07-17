"""Tests for the anchor-based block replace/extract primitives in tools/inject.py."""

from __future__ import annotations

import pytest

from repo_release_tools.tools.inject import extract_anchored_block, replace_anchored_block

MD_DOC = (
    "# Title\n"
    "\n"
    "<!-- rrt:auto:start:demo -->\n"
    "old body\n"
    "<!-- rrt:auto:end:demo -->\n"
    "\n"
    "trailing text\n"
)

MDX_DOC = (
    "# Title\n\n{/* rrt:auto:start:demo */}\nold body\n{/* rrt:auto:end:demo */}\n\ntrailing text\n"
)

RST_DOC = (
    "Title\n=====\n\n.. rrt:auto:start:demo\n\nold body\n\n.. rrt:auto:end:demo\n\ntrailing text\n"
)


@pytest.mark.parametrize(
    ("doc", "fmt"),
    [(MD_DOC, "md"), (MDX_DOC, "mdx"), (RST_DOC, "rst")],
)
def test_extract_anchored_block_returns_body(doc: str, fmt: str) -> None:
    body = extract_anchored_block(doc, anchor_id="demo", fmt=fmt)
    assert body is not None
    assert "old body" in body
    assert "trailing text" not in body


@pytest.mark.parametrize("fmt", ["md", "mdx", "rst"])
def test_extract_anchored_block_missing_start_returns_none(fmt: str) -> None:
    assert extract_anchored_block("just some text\n", anchor_id="demo", fmt=fmt) is None


@pytest.mark.parametrize(
    ("doc", "fmt"),
    [
        ("<!-- rrt:auto:start:demo -->\nbody\n", "md"),
        ("{/* rrt:auto:start:demo */}\nbody\n", "mdx"),
        (".. rrt:auto:start:demo\n\nbody\n", "rst"),
    ],
)
def test_extract_anchored_block_missing_end_raises(doc: str, fmt: str) -> None:
    with pytest.raises(ValueError, match="Missing end anchor"):
        extract_anchored_block(doc, anchor_id="demo", fmt=fmt)


def test_extract_anchored_block_invalid_anchor_id_raises() -> None:
    with pytest.raises(ValueError, match="Invalid anchor id"):
        extract_anchored_block(MD_DOC, anchor_id="-bad", fmt="md")


@pytest.mark.parametrize(
    ("doc", "fmt"),
    [(MD_DOC, "md"), (MDX_DOC, "mdx"), (RST_DOC, "rst")],
)
def test_replace_anchored_block_still_works_after_refactor(doc: str, fmt: str) -> None:
    """Regression guard: extracting _find_anchor_bounds() out of
    replace_anchored_block() must not change its existing behavior."""
    updated = replace_anchored_block(doc, anchor_id="demo", content="new body", fmt=fmt)
    assert updated is not None
    assert "new body" in updated
    assert "old body" not in updated
    assert "trailing text" in updated
    assert "Title" in updated


@pytest.mark.parametrize("fmt", ["md", "mdx", "rst"])
def test_replace_anchored_block_missing_start_returns_none(fmt: str) -> None:
    assert (
        replace_anchored_block("just some text\n", anchor_id="demo", content="x", fmt=fmt) is None
    )


@pytest.mark.parametrize(
    ("doc", "fmt"),
    [
        ("<!-- rrt:auto:start:demo -->\nbody\n", "md"),
        ("{/* rrt:auto:start:demo */}\nbody\n", "mdx"),
        (".. rrt:auto:start:demo\n\nbody\n", "rst"),
    ],
)
def test_replace_anchored_block_missing_end_raises(doc: str, fmt: str) -> None:
    with pytest.raises(ValueError, match="Missing end anchor"):
        replace_anchored_block(doc, anchor_id="demo", content="x", fmt=fmt)


def test_replace_anchored_block_invalid_anchor_id_raises() -> None:
    with pytest.raises(ValueError, match="Invalid anchor id"):
        replace_anchored_block(MD_DOC, anchor_id="-bad", content="x", fmt="md")


def test_extract_then_replace_round_trip() -> None:
    body = extract_anchored_block(MD_DOC, anchor_id="demo", fmt="md")
    assert body is not None
    updated = replace_anchored_block(MD_DOC, anchor_id="demo", content=body, fmt="md")
    assert updated == MD_DOC
