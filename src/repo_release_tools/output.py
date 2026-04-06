"""Terminal output helpers with a small shared glyph registry."""

from __future__ import annotations

import unicodedata

from repo_release_tools.glyphs import GLYPHS, Glyph


SECTION_WIDTH = 52


def _display_width(text: str) -> int:
    """Return the terminal cell width for a string."""
    width = 0
    for char in text:
        if unicodedata.combining(char) or unicodedata.category(char) in {"Cc", "Cf"}:
            continue
        width += 2 if unicodedata.east_asian_width(char) in {"F", "W"} else 1
    return width


def _pad_right(text: str, width: int) -> str:
    """Right-pad text to a terminal cell width."""
    return text + (" " * max(0, width - _display_width(text)))


def section(title: str) -> str:
    """Render a section heading."""
    fill = max(1, SECTION_WIDTH - _display_width(title))
    return f"{GLYPHS.box.h * 2} {title} {GLYPHS.box.h * fill}"


def panel(title: str, rows: list[tuple[str, str]]) -> str:
    """Render a compact two-column summary panel."""
    if not rows:
        return title

    label_width = max(_display_width(label) for label, _ in rows)
    # Keep one trailing cell in the value column so the body width matches the title bar.
    value_width = max(_display_width(value) for _, value in rows) + 1
    title_text = f" {title} "
    row_width = label_width + value_width + 7
    min_width = _display_width(title_text) + 2
    if row_width < min_width:
        value_width += min_width - row_width
        row_width = min_width

    top_fill = row_width - _display_width(title_text) - 2
    row_sep = (
        f"{GLYPHS.box.left}"
        f"{GLYPHS.box.h * (label_width + 2)}"
        f"{GLYPHS.box.cross}"
        f"{GLYPHS.box.h * (value_width + 2)}"
        f"{GLYPHS.box.right}"
    )
    bottom = (
        f"{GLYPHS.box.bl}"
        f"{GLYPHS.box.h * (label_width + 2)}"
        f"{GLYPHS.box.h}"
        f"{GLYPHS.box.h * (value_width + 2)}"
        f"{GLYPHS.box.br}"
    )

    lines = [f"{GLYPHS.box.tl}{title_text}{GLYPHS.box.h * top_fill}{GLYPHS.box.tr}"]
    for index, (label, value) in enumerate(rows):
        lines.append(
            f"{GLYPHS.box.v} {_pad_right(label, label_width)} {GLYPHS.box.v} "
            f"{_pad_right(value, value_width)} {GLYPHS.box.v}"
        )
        if index != len(rows) - 1:
            lines.append(row_sep)
    lines.append(bottom)
    return "\n".join(lines)


def status(symbol: Glyph | str, message: str, *, indent: int = 2) -> str:
    """Render an indented status line."""
    return f"{' ' * indent}{symbol} {message}"


def ok(message: str, *, indent: int = 2) -> str:
    """Render a success line."""
    return status(GLYPHS.bullet.ok, message, indent=indent)


def warning(message: str, *, indent: int = 2) -> str:
    """Render a warning line."""
    return status(GLYPHS.bullet.warning, message, indent=indent)


def error(message: str, *, indent: int = 2) -> str:
    """Render an error line."""
    return status(GLYPHS.bullet.error, message, indent=indent)


def dry_run(message: str, *, indent: int = 2) -> str:
    """Render a dry-run preview line."""
    return status(GLYPHS.bullet.skip, f"[dry-run] {message}", indent=indent)


def action(message: str, *, indent: int = 0) -> str:
    """Render an action line."""
    return status(GLYPHS.arrow.right, message, indent=indent)


def dry_run_complete(message: str) -> str:
    """Render the dry-run completion line."""
    return dry_run(f"complete {GLYPHS.typography.mdash} {message}", indent=0)
