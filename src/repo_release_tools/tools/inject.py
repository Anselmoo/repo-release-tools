"""Anchor-based block replacement and doc-write helpers for Markdown, MDX, and RST files.

Anchor markers surround a block of generated content inside a larger document.

For Markdown (``.md`` files), markers are invisible HTML comments::

    <!-- rrt:auto:start:my-anchor -->
    ...generated content replaced on every run...
    <!-- rrt:auto:end:my-anchor -->

For MDX (``.mdx`` files), markers use JSX comment syntax instead, since MDX's
JSX-aware parser cannot parse raw HTML comments::

    {/* rrt:auto:start:my-anchor */}
    ...generated content replaced on every run...
    {/* rrt:auto:end:my-anchor */}

For reStructuredText (``.rst`` / ``.txt`` files), markers use RST comment syntax::

    .. rrt:auto:start:my-anchor

    ...generated content replaced on every run...

    .. rrt:auto:end:my-anchor

Any text before or after the anchors is preserved unchanged.

This module is used by the ``rrt docs publish`` / ``rrt docs inject`` commands
and the ``rrt tree --inject`` command.

## Anchor ID rules

An anchor ID must start with an ASCII letter or digit followed by any
combination of ASCII letters, digits, dots, underscores, or hyphens.

## Format detection

The format is inferred automatically from the file extension:
``rst`` and ``txt`` → RST; ``mdx`` → MDX; everything else → Markdown.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol

ANCHOR_START_TOKEN: str = "rrt:auto:start:"
ANCHOR_END_TOKEN: str = "rrt:auto:end:"
RST_ANCHOR_START_TOKEN: str = ".. rrt:auto:start:"
RST_ANCHOR_END_TOKEN: str = ".. rrt:auto:end:"
MDX_ANCHOR_START_TOKEN: str = "rrt:auto:start:"
MDX_ANCHOR_END_TOKEN: str = "rrt:auto:end:"
_ANCHOR_ID_RE: re.Pattern[str] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_RST_EXTENSIONS: frozenset[str] = frozenset({".rst", ".txt"})
_MDX_EXTENSIONS: frozenset[str] = frozenset({".mdx"})


def _detect_inject_format(path: Path | str) -> str:
    """Return ``'rst'`` for ``.rst``/``.txt``, ``'mdx'`` for ``.mdx``, ``'md'`` otherwise."""
    suffix = Path(path).suffix.lower()
    if suffix in _RST_EXTENSIONS:
        return "rst"
    if suffix in _MDX_EXTENSIONS:
        return "mdx"
    return "md"


def _anchor_comment_pattern(token: str, anchor_id: str) -> re.Pattern[str]:
    """Return a strict marker matcher for ``<!-- <token><anchor_id> -->``."""
    marker = re.escape(f"{token}{anchor_id}")
    return re.compile(rf"^\s*<!--\s*{marker}\s*-->\s*$")


def _anchor_rst_pattern(token: str, anchor_id: str) -> re.Pattern[str]:
    """Return a strict RST comment marker matcher for ``.. <token><anchor_id>``."""
    marker = re.escape(f"{token}{anchor_id}")
    return re.compile(rf"^\s*{marker}\s*$")


def _anchor_mdx_pattern(token: str, anchor_id: str) -> re.Pattern[str]:
    """Return a strict marker matcher for ``{/* <token><anchor_id> */}``."""
    marker = re.escape(f"{token}{anchor_id}")
    return re.compile(rf"^\s*\{{/\*\s*{marker}\s*\*/\}}\s*$")


class SupportsWrite(Protocol):
    """Minimal text stream protocol for stdout/stderr injection."""

    def write(self, s: str, /) -> object:
        """Write text to the underlying stream-like object."""


def insert_anchor_stub_str(
    content: str,
    anchor_id: str,
    *,
    position: str = "prepend",
    before_blank_lines: int = 0,
    after_blank_lines: int = 1,
) -> str:
    """Return *content* with an empty anchor pair inserted if *anchor_id* is absent.

    Mirrors the placement logic of :func:`ensure_anchor_stub` but operates on a
    string rather than a file path, making it suitable for in-memory content
    generation.

    Note: this helper (and :func:`ensure_anchor_stub`) hardcodes the Markdown
    HTML-comment anchor form and is not format-aware (it doesn't handle RST or
    MDX today). Its current call sites never target ``.mdx`` files, so this is
    a pre-existing, deferred gap rather than a regression — add an ``mdx``
    branch here too whenever a call site starts targeting the ``.mdx`` tree.
    """
    if position not in {"prepend", "append"}:
        raise ValueError(f"Unsupported anchor position: {position!r}")
    if before_blank_lines < 0:
        raise ValueError("before_blank_lines must be >= 0")
    if after_blank_lines < 0:
        raise ValueError("after_blank_lines must be >= 0")

    start = f"<!-- rrt:auto:start:{anchor_id} -->"
    if start in content:
        return content

    end = f"<!-- rrt:auto:end:{anchor_id} -->"
    newline = "\r\n" if "\r\n" in content else "\n"
    anchor_lines = [newline for _ in range(before_blank_lines)]
    anchor_lines.extend([f"{start}{newline}", f"{end}{newline}"])
    anchor_lines.extend([newline for _ in range(after_blank_lines)])

    lines = content.splitlines(keepends=True)
    insert_at = len(lines)

    if position == "prepend":
        if content.startswith("---\n") or content.startswith("---\r\n"):
            close_idx = next(
                (i for i in range(1, len(lines)) if lines[i].rstrip("\r\n") == "---"), -1
            )
            insert_at = close_idx + 1 if close_idx > 0 else 0
        else:
            insert_at = 0

    return "".join(lines[:insert_at] + anchor_lines + lines[insert_at:])


def ensure_anchor_stub(
    path: Path,
    anchor_id: str,
    *,
    position: str = "prepend",
    before_blank_lines: int = 0,
    after_blank_lines: int = 1,
) -> None:
    """Insert an empty anchor pair when *anchor_id* is missing from *path*.

    The stub is placed either after YAML front matter (``position='prepend'``)
    or at the end of the file (``position='append'``), with configurable blank
    lines before and after the marker pair.
    """
    if position not in {"prepend", "append"}:
        raise ValueError(f"Unsupported anchor position: {position!r}")
    if before_blank_lines < 0:
        raise ValueError("before_blank_lines must be >= 0")
    if after_blank_lines < 0:
        raise ValueError("after_blank_lines must be >= 0")
    if not path.exists():
        return
    existing = path.read_text(encoding="utf-8")
    updated = insert_anchor_stub_str(
        existing,
        anchor_id,
        position=position,
        before_blank_lines=before_blank_lines,
        after_blank_lines=after_blank_lines,
    )
    if updated != existing:
        path.write_text(updated, encoding="utf-8")


def _find_anchor_bounds(lines: list[str], *, anchor_id: str, fmt: str) -> tuple[int, int] | None:
    """Return the (start_idx, end_idx) of the anchor marker lines in *lines*.

    Returns ``None`` when the start marker for *anchor_id* is absent.

    Raises:
        ValueError: When *anchor_id* is invalid, or when the start marker is
            present but the end marker is absent.
    """
    if not _ANCHOR_ID_RE.fullmatch(anchor_id):
        raise ValueError(f"Invalid anchor id: {anchor_id!r}")

    if fmt == "rst":
        start_re = _anchor_rst_pattern(RST_ANCHOR_START_TOKEN, anchor_id)
        end_re = _anchor_rst_pattern(RST_ANCHOR_END_TOKEN, anchor_id)
        end_token_display = f"{RST_ANCHOR_END_TOKEN}{anchor_id}"
    elif fmt == "mdx":
        start_re = _anchor_mdx_pattern(MDX_ANCHOR_START_TOKEN, anchor_id)
        end_re = _anchor_mdx_pattern(MDX_ANCHOR_END_TOKEN, anchor_id)
        end_token_display = f"{{/* {MDX_ANCHOR_END_TOKEN}{anchor_id} */}}"
    else:
        start_re = _anchor_comment_pattern(ANCHOR_START_TOKEN, anchor_id)
        end_re = _anchor_comment_pattern(ANCHOR_END_TOKEN, anchor_id)
        end_token_display = f"{ANCHOR_END_TOKEN}{anchor_id}"

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
        raise ValueError(f"Missing end anchor for {anchor_id!r} ({end_token_display})")

    return start_idx, end_idx


def extract_anchored_block(existing: str, *, anchor_id: str, fmt: str = "md") -> str | None:
    """Return the body between matching anchor markers in *existing*.

    Args:
        existing: Full text of the target file.
        anchor_id: The anchor identifier, e.g. ``"project-tree"``.  Must match
            ``[A-Za-z0-9][A-Za-z0-9._-]*``.
        fmt: ``'md'`` for Markdown HTML-comment anchors (default), ``'rst'`` for
            reStructuredText comment anchors, ``'mdx'`` for MDX JSX-comment anchors.

    Returns:
        The text strictly between the start and end marker lines, or ``None``
        when the start marker for *anchor_id* is not found in *existing*.

    Raises:
        ValueError: When *anchor_id* is invalid, or when the start marker is
            present but the end marker is absent.
    """
    lines = existing.splitlines(keepends=True)
    bounds = _find_anchor_bounds(lines, anchor_id=anchor_id, fmt=fmt)
    if bounds is None:
        return None
    start_idx, end_idx = bounds
    return "".join(lines[start_idx + 1 : end_idx])


def replace_anchored_block(
    existing: str, *, anchor_id: str, content: str, fmt: str = "md"
) -> str | None:
    """Replace the body between matching anchor markers in *existing*.

    Args:
        existing: Full text of the target file.
        anchor_id: The anchor identifier, e.g. ``"project-tree"``.  Must match
            ``[A-Za-z0-9][A-Za-z0-9._-]*``.
        content: New content to place between the markers. Trailing newline is
            normalised automatically.
        fmt: ``'md'`` for Markdown HTML-comment anchors (default), ``'rst'`` for
            reStructuredText comment anchors, ``'mdx'`` for MDX JSX-comment anchors.

    Returns:
        Updated file text with the block replaced, or ``None`` when the start
        marker for *anchor_id* is not found in *existing*.

    Raises:
        ValueError: When *anchor_id* is invalid, or when the start marker is
            present but the end marker is absent.
    """
    lines = existing.splitlines(keepends=True)
    bounds = _find_anchor_bounds(lines, anchor_id=anchor_id, fmt=fmt)
    if bounds is None:
        return None
    start_idx, end_idx = bounds

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
    inject_fmt = _detect_inject_format(output_path)

    if anchor_id is not None:
        if inject_fmt == "rst":
            start_token_display = f"{RST_ANCHOR_START_TOKEN}{anchor_id}"
            end_token_display = f"{RST_ANCHOR_END_TOKEN}{anchor_id}"
        elif inject_fmt == "mdx":
            start_token_display = f"{{/* {MDX_ANCHOR_START_TOKEN}{anchor_id} */}}"
            end_token_display = f"{{/* {MDX_ANCHOR_END_TOKEN}{anchor_id} */}}"
        else:
            start_token_display = f"{ANCHOR_START_TOKEN}{anchor_id}"
            end_token_display = f"{ANCHOR_END_TOKEN}{anchor_id}"

        if current is None:
            stderr.write(
                f"{output_path} missing required anchor block ({start_token_display}).\n",
            )
            return 1
        replaced = replace_anchored_block(
            current, anchor_id=anchor_id, content=content, fmt=inject_fmt
        )
        if replaced is None:
            stderr.write(
                f"{output_path} is missing required anchors "
                f"{start_token_display} / {end_token_display}.\n",
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
