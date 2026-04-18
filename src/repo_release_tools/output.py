"""Terminal output helpers with a small shared glyph registry."""

from __future__ import annotations

from repo_release_tools.glyphs import (
    GLYPHS,
    BoldBoxGlyphs,
    BoxGlyphs,
    BoxStyle,
    Glyph,
    RoundedBoxGlyphs,
    display_width,
    pad_right,
)


SECTION_WIDTH = 52

# Union type for the box-drawing glyph sets accepted by panel().
_AnyBoxGlyphs = BoxGlyphs | RoundedBoxGlyphs | BoldBoxGlyphs


def _resolve_box(style: BoxStyle) -> _AnyBoxGlyphs:
    """Return the glyph set matching the requested panel style."""
    if style == "rounded":
        return GLYPHS.rounded_box
    if style == "bold":
        return GLYPHS.bold_box
    # "mixed" and "single" both use single-line corners as the base;
    # for "mixed" the outer frame is switched to bold_box inside panel().
    return GLYPHS.box


def section(title: str) -> str:
    """Render a section heading."""
    fill = max(1, SECTION_WIDTH - display_width(title))
    return f"{GLYPHS.box.h * 2} {title} {GLYPHS.box.h * fill}"


def panel(title: str, rows: list[tuple[str, str]], *, style: BoxStyle = "single") -> str:
    """Render a compact two-column summary panel.

    ``style`` selects the box-drawing character set:

    * ``"single"``  — thin lines (┌ ┐ └ ┘ │ ─)  *default*
    * ``"rounded"`` — rounded corners (╭ ╮ ╰ ╯ │ ─)
    * ``"bold"``    — thick/heavy borders (┏ ┓ ┗ ┛ ┃ ━)
    * ``"mixed"``   — bold outer frame + thin inner dividers
    """
    if not rows:
        return title

    # Resolve outer (frame) and inner (divider) glyph sets.
    outer: _AnyBoxGlyphs = GLYPHS.bold_box if style == "mixed" else _resolve_box(style)
    inner: _AnyBoxGlyphs = GLYPHS.box if style in {"mixed", "single"} else outer

    label_width = max(display_width(label) for label, _ in rows)
    # Keep one trailing cell in the value column so the body width matches the title bar.
    value_width = max(display_width(value) for _, value in rows) + 1
    title_text = f" {title} "
    row_width = label_width + value_width + 7
    min_width = display_width(title_text) + 2
    if row_width < min_width:
        value_width += min_width - row_width
        row_width = min_width

    top_fill = row_width - display_width(title_text) - 2
    # Row separator: ├────────┼─────────────────┤  (inner dividers)
    row_sep = (
        f"{inner.left}"
        f"{inner.h * (label_width + 2)}"
        f"{inner.cross}"
        f"{inner.h * (value_width + 2)}"
        f"{inner.right}"
    )
    # Bottom border: └────────┴─────────────────┘  (outer corners, inner bottom-T junction)
    bottom = (
        f"{outer.bl}"
        f"{inner.h * (label_width + 2)}"
        f"{inner.bottom}"
        f"{inner.h * (value_width + 2)}"
        f"{outer.br}"
    )

    # Top border uses outer corners + outer horizontal; rows use inner vertical for column divider.
    lines = [f"{outer.tl}{title_text}{outer.h * top_fill}{outer.tr}"]
    for index, (label, value) in enumerate(rows):
        lines.append(
            f"{outer.v} {pad_right(label, label_width)} {inner.v} "
            f"{pad_right(value, value_width)} {outer.v}"
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
