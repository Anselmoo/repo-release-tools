"""Terminal output helpers with platform-aware glyph fallbacks."""

from __future__ import annotations

import sys

from dataclasses import dataclass, field


IS_LEGACY_TERMINAL = sys.platform == "win32"
SECTION_WIDTH = 52


def _g(windows_ascii: str, unicode_glyph: str) -> str:
    """Return an ASCII fallback on legacy Windows terminals."""
    return windows_ascii if IS_LEGACY_TERMINAL else unicode_glyph


@dataclass(frozen=True)
class Glyph:
    """A platform-aware terminal glyph."""

    symbol: str
    name: str

    def __str__(self) -> str:
        return self.symbol

    def __mul__(self, count: int) -> str:
        return self.symbol * count

    def __rmul__(self, count: int) -> str:
        return self.symbol * count


@dataclass(frozen=True)
class BoxGlyphs:
    """Box-drawing glyphs used for summaries and sections."""

    h: Glyph = field(default_factory=lambda: Glyph(_g("-", "─"), "h"))
    v: Glyph = field(default_factory=lambda: Glyph(_g("|", "│"), "v"))
    tl: Glyph = field(default_factory=lambda: Glyph(_g("+", "┌"), "top_left"))
    tr: Glyph = field(default_factory=lambda: Glyph(_g("+", "┐"), "top_right"))
    bl: Glyph = field(default_factory=lambda: Glyph(_g("+", "└"), "bottom_left"))
    br: Glyph = field(default_factory=lambda: Glyph(_g("+", "┘"), "bottom_right"))
    left: Glyph = field(default_factory=lambda: Glyph(_g("+", "├"), "left"))
    right: Glyph = field(default_factory=lambda: Glyph(_g("+", "┤"), "right"))
    cross: Glyph = field(default_factory=lambda: Glyph(_g("+", "┼"), "cross"))


@dataclass(frozen=True)
class ArrowGlyphs:
    """Directional glyphs for transitions and actions."""

    right: Glyph = field(default_factory=lambda: Glyph(_g("->", "→"), "right"))


@dataclass(frozen=True)
class BulletGlyphs:
    """Status glyphs for successful, skipped, and warning states."""

    dot: Glyph = field(default_factory=lambda: Glyph(_g("*", "•"), "dot"))
    ok: Glyph = field(default_factory=lambda: Glyph(_g("[OK]", "✔"), "ok"))
    skip: Glyph = field(default_factory=lambda: Glyph(_g("[-]", "⊖"), "skip"))
    warning: Glyph = field(default_factory=lambda: Glyph(_g("/!\\", "▲"), "warning"))


@dataclass(frozen=True)
class TypographyGlyphs:
    """Typography glyphs that benefit from fallbacks."""

    ellipsis: Glyph = field(default_factory=lambda: Glyph(_g("...", "…"), "ellipsis"))
    mdash: Glyph = field(default_factory=lambda: Glyph(_g("--", "—"), "mdash"))


@dataclass(frozen=True)
class GlyphSet:
    """Shared glyph registry for terminal output."""

    box: BoxGlyphs = field(default_factory=BoxGlyphs)
    arrow: ArrowGlyphs = field(default_factory=ArrowGlyphs)
    bullet: BulletGlyphs = field(default_factory=BulletGlyphs)
    typography: TypographyGlyphs = field(default_factory=TypographyGlyphs)


GLYPHS = GlyphSet()


def section(title: str) -> str:
    """Render a section heading."""
    fill = max(1, SECTION_WIDTH - len(title))
    return f"{GLYPHS.box.h * 2} {title} {GLYPHS.box.h * fill}"


def panel(title: str, rows: list[tuple[str, str]]) -> str:
    """Render a compact two-column summary panel."""
    if not rows:
        return title

    label_width = max(len(label) for label, _ in rows)
    value_width = max(len(value) for _, value in rows)
    title_text = f" {title} "
    row_width = label_width + value_width + 8
    min_width = len(title_text) + 2
    if row_width < min_width:
        value_width += min_width - row_width
        row_width = min_width

    top_fill = row_width - len(title_text) - 2
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
            f"{GLYPHS.box.v} {label.ljust(label_width)} {GLYPHS.box.v} "
            f"{value.ljust(value_width)} {GLYPHS.box.v}"
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


def dry_run(message: str, *, indent: int = 2) -> str:
    """Render a dry-run preview line."""
    return status(GLYPHS.bullet.skip, f"[dry-run] {message}", indent=indent)


def action(message: str, *, indent: int = 0) -> str:
    """Render an action line."""
    return status(GLYPHS.arrow.right, message, indent=indent)


def dry_run_complete(message: str) -> str:
    """Render the dry-run completion line."""
    return dry_run(f"complete {GLYPHS.typography.mdash} {message}", indent=0)
