"""Anchor-based block replacement and doc-write helpers for Markdown files.

Anchor markers are HTML comments (invisible in rendered output) that surround a
block of generated content inside a larger document:

.. code-block:: markdown

    <!-- rrt:auto:start:my-anchor -->
    ...generated content replaced on every run...
    <!-- rrt:auto:end:my-anchor -->

Any text before or after the anchors is preserved unchanged.

This module is used by the ``rrt docs publish`` / ``rrt docs inject`` commands
and the ``rrt tree --inject`` command.

## Anchor ID rules

An anchor ID must start with an ASCII letter or digit followed by any
combination of ASCII letters, digits, dots, underscores, or hyphens.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol

ANCHOR_START_TOKEN: str = "rrt:auto:start:"
ANCHOR_END_TOKEN: str = "rrt:auto:end:"
_ANCHOR_ID_RE: re.Pattern[str] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class SupportsWrite(Protocol):
    """Minimal text stream protocol for stdout/stderr injection."""

    def write(self, s: str, /) -> object:
        """Write text to the underlying stream-like object."""


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


def apply_generated_docs(
    content: str,
    *,
    output_path: Path,
    check: bool,
    write: bool,
    fail_on_change: bool,
    stdout: SupportsWrite,
    stderr: SupportsWrite,
    anchor_id: str | None = None,
    stale_hint: str = "rrt docs publish",
) -> int:
    """Check and/or write generated docs, returning the desired exit code.

    Args:
        content: The desired file content (or anchor-block body when
            *anchor_id* is set).
        output_path: Destination file path.
        check: When ``True`` and no *write*, fail if content differs from disk.
        write: When ``True``, write the desired content to disk.
        fail_on_change: After writing, return exit code 1 so hook workflows
            can stop and prompt for re-staging.
        stdout: Stream for informational messages.
        stderr: Stream for error/warning messages.
        anchor_id: When set, the content is injected *inside* anchor markers
            rather than replacing the whole file.
        stale_hint: Human-facing hint shown when the file is stale in check mode.

    Returns:
        0 when up-to-date or successfully written; 1 on errors or when
        *fail_on_change* triggers after a write.
    """
    current = output_path.read_text(encoding="utf-8") if output_path.exists() else None
    desired = content

    if anchor_id is not None:
        if current is None:
            stderr.write(
                f"{output_path} missing required anchor block ({ANCHOR_START_TOKEN}{anchor_id}).\n",
            )
            return 1
        replaced = replace_anchored_block(current, anchor_id=anchor_id, content=content)
        if replaced is None:
            stderr.write(
                f"{output_path} is missing required anchors "
                f"{ANCHOR_START_TOKEN}{anchor_id} / {ANCHOR_END_TOKEN}{anchor_id}.\n",
            )
            return 1
        desired = replaced

    if current == desired:
        stdout.write(f"{output_path} is up-to-date.\n")
        return 0

    if check and not write:
        stderr.write(f"{output_path} is stale. Run: {stale_hint}\n")
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(desired, encoding="utf-8")

    if fail_on_change:
        stderr.write(
            f"Updated {output_path}. Review the generated diff and re-stage the file before retrying.\n",
        )
        return 1

    stdout.write(f"Wrote {output_path}.\n")
    return 0
