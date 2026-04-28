"""Small layout helpers for terminal-friendly text rendering."""

from __future__ import annotations

import shutil

from typing import Literal

from repo_release_tools.ui.glyphs import GLYPHS, display_width, pad_right


BoxKind = Literal["single", "rounded", "bold", "ascii"]


class _AsciiBoxGlyphs:
    h = "-"
    v = "|"
    tl = "+"
    tr = "+"
    bl = "+"
    br = "+"
    top = "+"
    bottom = "+"


ASCII_BOX = _AsciiBoxGlyphs()


def terminal_width(default: int = 100) -> int:
    """Return current terminal width, or *default* when unknown."""
    try:
        return shutil.get_terminal_size(fallback=(default, 24)).columns
    except Exception:  # pragma: no cover
        return default


def truncate(text: str, width: int, ellipsis: str = "…") -> str:
    """Truncate text to terminal cell width, preserving whole characters."""
    if width <= 0:
        return ""
    if display_width(text) <= width:
        return text

    ellipsis_width = display_width(ellipsis)
    if ellipsis_width >= width:
        return ellipsis[:width]

    out: list[str] = []
    used = 0
    for char in text:
        char_w = display_width(char)
        if used + char_w + ellipsis_width > width:
            break
        out.append(char)
        used += char_w
    return "".join(out) + ellipsis


def align(text: str, width: int, mode: str = "left") -> str:
    """Align text in a fixed terminal width."""
    visible = display_width(text)
    if visible >= width:
        return truncate(text, width)

    delta = width - visible
    if mode == "right":
        return (" " * delta) + text
    if mode == "center":
        left = delta // 2
        right = delta - left
        return (" " * left) + text + (" " * right)
    return pad_right(text, width)


def section_line(
    title: str, *, body_width: int | None = None, glyph: str = "─", left: int = 2
) -> str:
    """Render a horizontal section line compatible with current rrt style.

    When *body_width* is ``None`` (default) the current terminal width minus 4
    is used so the line fills the visible area.
    """
    effective_width = (terminal_width() - 4) if body_width is None else body_width
    fill = max(1, effective_width - display_width(title))
    return f"{glyph * left} {title} {glyph * fill}"


def rule(title: str | None = None, *, style: str = "─", width: int | None = None) -> str:
    """Render a full-width horizontal rule, optionally with a centred title.

    Example::

        rule()              # ─────────────────────────────────────────────
        rule("Section")     # ── Section ───────────────────────────────────

    Parameters
    ----------
    title:  Optional label to centre in the rule.
    style:  Repeated glyph character (default ``─``).
    width:  Total rule width in cells.  ``None`` → ``terminal_width() - 4``.
    """
    total = (terminal_width() - 4) if width is None else width
    if not title:
        return style * total
    padded = f" {title} "
    title_w = display_width(padded)
    if title_w >= total:
        return padded
    left_fill = 2
    right_fill = max(1, total - left_fill - title_w)
    return f"{style * left_fill}{padded}{style * right_fill}"


def box(
    content: str | list[str],
    *,
    title: str | None = None,
    padding: int = 1,
    style: BoxKind = "single",
    width: int | None = None,
) -> str:
    """Render a generic text box using unicode or ASCII borders.

    Parameters
    ----------
    content:
            Either a single string (possibly multi-line) or explicit lines.
    title:
            Optional title rendered in the top border.
    padding:
            Horizontal padding inside the frame.
    style:
            `single`, `rounded`, `bold`, or `ascii`.
    width:
            Inner content width in cells.  ``None`` uses the widest content
            line, capped at ``terminal_width() - 4``.
    """
    lines = (content.splitlines() if isinstance(content, str) else list(content)) or [""]

    if style == "rounded":
        g = GLYPHS.rounded_box
    elif style == "bold":
        g = GLYPHS.bold_box
    elif style == "ascii":
        # Explicit ASCII fallback regardless of terminal support.
        g = ASCII_BOX
    else:
        g = GLYPHS.box

    content_max = max(display_width(line) for line in lines)
    if width is not None:
        inner_width = width + (padding * 2)
    else:
        max_inner = terminal_width() - 4
        inner_width = min(content_max + (padding * 2), max_inner)
    title_text = f" {title} " if title else ""
    min_top = display_width(title_text)
    inner_width = max(inner_width, min_top)

    if title_text:
        top_fill = max(0, inner_width - display_width(title_text))
        top = f"{g.tl}{title_text}{str(g.h) * top_fill}{g.tr}"
    else:
        top = f"{g.tl}{str(g.h) * inner_width}{g.tr}"

    cell_w = inner_width - (padding * 2)
    body = [
        f"{g.v}{' ' * padding}{pad_right(truncate(line, cell_w) if display_width(line) > cell_w else line, cell_w)}{' ' * padding}{g.v}"
        for line in lines
    ]
    bottom = f"{g.bl}{str(g.h) * inner_width}{g.br}"
    return "\n".join([top, *body, bottom])


def render_table(rows: list[tuple[str, str]], ctx: object | None = None) -> str:
    """Render a compact two-column table with consistent padding."""
    del ctx
    if not rows:
        return ""

    glyphs = GLYPHS.box
    col1 = max(display_width(label) for label, _ in rows) + 2
    col2 = max(display_width(value) for _, value in rows) + 2

    top = f"{glyphs.tl}{str(glyphs.h) * col1}{glyphs.top}{str(glyphs.h) * col2}{glyphs.tr}"
    sep = f"{glyphs.left}{str(glyphs.h) * col1}{glyphs.cross}{str(glyphs.h) * col2}{glyphs.right}"
    bottom = f"{glyphs.bl}{str(glyphs.h) * col1}{glyphs.bottom}{str(glyphs.h) * col2}{glyphs.br}"

    lines = [top]
    for index, (label, value) in enumerate(rows):
        lines.append(
            f"{glyphs.v} {pad_right(label, col1 - 2)} {glyphs.v} {pad_right(value, col2 - 2)} {glyphs.v}"
        )
        if index < len(rows) - 1:
            lines.append(sep)
    lines.append(bottom)
    return "\n".join(lines)


def progress_bar(
    value: float,
    *,
    width: int = 20,
    full: str | None = None,
    empty: str | None = None,
    label: str | None = None,
    show_pct: bool = True,
) -> str:
    """Render a dependency-free progress bar.

    Uses Unicode block glyphs when available (``█`` / ``░``), falling back to
    ``#`` / ``-`` on legacy terminals.  Pass *full* / *empty* to override.

    Parameters
    ----------
    value:      Fraction complete, 0.0 – 1.0.
    width:      Bar width in characters.
    full:       Character for filled portion (default: ``█`` or ``#``).
    empty:      Character for empty portion (default: ``░`` or ``-``).
    label:      Optional trailing label (e.g. ``"Loading…"``).
    show_pct:   Whether to append a percentage indicator.
    """
    import os as _os

    _use_unicode = _os.environ.get("TERM", "") != "dumb" and _os.environ.get("NO_COLOR") is None
    _full = full if full is not None else ("█" if _use_unicode else "#")
    _empty = empty if empty is not None else ("░" if _use_unicode else "-")

    clamped = max(0.0, min(1.0, value))
    filled = round(clamped * width)
    bar = f"[{_full * filled}{_empty * (width - filled)}]"
    parts = [bar]
    if show_pct:
        parts.append(f"{clamped:.0%}")
    if label:
        parts.append(label)
    return " ".join(parts)


def sparkline(values: list[float], *, width: int | None = None, ascii_only: bool = False) -> str:
    """Render a compact sparkline for a numeric series.

    If ``ascii_only`` is true, use ``._-~=*#`` levels.
    """
    if not values:
        return ""

    vals = values if width is None or width >= len(values) else values[-width:]
    vmin = min(vals)
    vmax = max(vals)
    span = vmax - vmin

    levels = "._-~=*#" if ascii_only else "▁▂▃▄▅▆▇█"
    if span == 0:
        return levels[0] * len(vals)

    max_index = len(levels) - 1
    return "".join(levels[round(((v - vmin) / span) * max_index)] for v in vals)
