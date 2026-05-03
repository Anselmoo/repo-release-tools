"""Anchor-based block replacement for Markdown files.

Anchor markers are HTML comments (invisible in rendered output) that surround a
block of generated content inside a larger document:

.. code-block:: markdown

    <!-- rrt:auto:start:my-anchor -->
    ...generated content replaced on every run...
    <!-- rrt:auto:end:my-anchor -->

Any text before or after the anchors is preserved unchanged.

This module is used by both the docs generator pipeline
(``scripts/generate_cli_docs.py``) and the ``rrt tree --inject`` command.

## Anchor ID rules

An anchor ID must start with an ASCII letter or digit followed by any
combination of ASCII letters, digits, dots, underscores, or hyphens.
"""

from __future__ import annotations

import re

ANCHOR_START_TOKEN: str = "rrt:auto:start:"
ANCHOR_END_TOKEN: str = "rrt:auto:end:"
_ANCHOR_ID_RE: re.Pattern[str] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _anchor_comment_pattern(token: str, anchor_id: str) -> re.Pattern[str]:
    """Return a strict marker matcher for ``<!-- <token><anchor_id> -->``."""
    marker = re.escape(f"{token}{anchor_id}")
    return re.compile(rf"^\s*<!--\s*{marker}\s*-->\s*$")


def replace_anchored_block(existing: str, *, anchor_id: str, content: str) -> str | None:
    """Replace the body between matching anchor markers in *existing*.

    Args:
        existing: Full text of the target file.
        anchor_id: The anchor identifier, e.g. ``"project-tree"``.  Must match
            ``[A-Za-z0-9][A-Za-z0-9._-]*``.
        content: New content to place between the markers. Trailing newline is
            normalised automatically.

    Returns:
        Updated file text with the block replaced, or ``None`` when the start
        marker for *anchor_id* is not found in *existing*.

    Raises:
        ValueError: When *anchor_id* is invalid, or when the start marker is
            present but the end marker is absent.
    """
    if not _ANCHOR_ID_RE.fullmatch(anchor_id):
        raise ValueError(f"Invalid anchor id: {anchor_id!r}")

    lines = existing.splitlines(keepends=True)
    start_re = _anchor_comment_pattern(ANCHOR_START_TOKEN, anchor_id)
    end_re = _anchor_comment_pattern(ANCHOR_END_TOKEN, anchor_id)

    start_idx = next(
        (idx for idx, line in enumerate(lines) if start_re.match(line.rstrip("\r\n"))),
        None,
    )
    if start_idx is None:
        return None

    end_idx = next(
        (
            idx
            for idx in range(start_idx + 1, len(lines))
            if end_re.match(lines[idx].rstrip("\r\n"))
        ),
        None,
    )
    if end_idx is None:
        raise ValueError(f"Missing end anchor for {anchor_id!r} ({ANCHOR_END_TOKEN}{anchor_id})")

    block = content.rstrip("\n")
    body = f"{block}\n" if block else ""
    updated_lines = lines[: start_idx + 1] + [body] + lines[end_idx:]
    return "".join(updated_lines)
