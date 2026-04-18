"""Small platform-aware glyph registry for repo-release-tools.

This module is intentionally narrow. It adapts a few ideas from the author's
broader glyph/emoji exploration into a stable, non-emoji terminal layer for
rrt. The public surface is kept compact so CLI output stays predictable.
"""

from __future__ import annotations

import itertools
import locale
import os
import sys
import unicodedata

from dataclasses import dataclass, field
from typing import Iterator, Literal


def _detect_legacy_terminal() -> bool:
    """Return True when the terminal cannot reliably render Unicode box-drawing glyphs."""
    if sys.platform == "win32":
        return True
    if os.environ.get("TERM") == "dumb":
        return True
    if "NO_COLOR" in os.environ:
        return True
    return False


IS_LEGACY_TERMINAL: bool = _detect_legacy_terminal()


def _detect_cjk_locale() -> bool:
    """Return True when the active locale uses wide (CJK) ambiguous-width rendering.

    Respects the ``RRT_WIDE_AMBIGUOUS=1`` environment override for testing or
    explicit opt-in on setups where locale detection is unreliable.
    """
    if os.environ.get("RRT_WIDE_AMBIGUOUS") == "1":
        return True
    if os.environ.get("RRT_WIDE_AMBIGUOUS") == "0":
        return False
    try:
        lang, encoding = locale.getlocale()
    except Exception:  # pragma: no cover
        return False
    if lang is None:
        return False
    lang_lower = lang.lower()
    return any(lang_lower.startswith(prefix) for prefix in ("zh", "ja", "ko"))


_AMBIGUOUS_IS_WIDE: bool = _detect_cjk_locale()


def _g(windows_ascii: str, unicode_glyph: str) -> str:
    """Return an ASCII fallback on legacy Windows terminals."""
    return windows_ascii if IS_LEGACY_TERMINAL else unicode_glyph


def display_width(text: str) -> int:
    """Return the terminal cell width for a string.

    Handles full-width (F/W) and, when the active locale uses CJK wide rendering
    or ``RRT_WIDE_AMBIGUOUS=1`` is set, ambiguous-width (A) characters as well.
    Combining marks and invisible control characters are counted as zero-width.
    """
    width = 0
    for char in text:
        if unicodedata.combining(char) or unicodedata.category(char) in {"Cc", "Cf"}:
            continue
        eaw = unicodedata.east_asian_width(char)
        if eaw in {"F", "W"}:
            width += 2
        elif eaw == "A" and _AMBIGUOUS_IS_WIDE:
            width += 2
        else:
            width += 1
    return width


def pad_right(text: str, width: int) -> str:
    """Right-pad text to a terminal cell width."""
    return text + (" " * max(0, width - display_width(text)))


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
    top: Glyph = field(default_factory=lambda: Glyph(_g("+", "┬"), "top"))
    bottom: Glyph = field(default_factory=lambda: Glyph(_g("+", "┴"), "bottom"))
    left: Glyph = field(default_factory=lambda: Glyph(_g("+", "├"), "left"))
    right: Glyph = field(default_factory=lambda: Glyph(_g("+", "┤"), "right"))
    cross: Glyph = field(default_factory=lambda: Glyph(_g("+", "┼"), "cross"))
    dh: Glyph = field(default_factory=lambda: Glyph(_g("=", "═"), "double_h"))
    dv: Glyph = field(default_factory=lambda: Glyph(_g("|", "║"), "double_v"))
    dtl: Glyph = field(default_factory=lambda: Glyph(_g("+", "╔"), "double_top_left"))
    dtr: Glyph = field(default_factory=lambda: Glyph(_g("+", "╗"), "double_top_right"))
    dbl: Glyph = field(default_factory=lambda: Glyph(_g("+", "╚"), "double_bottom_left"))
    dbr: Glyph = field(default_factory=lambda: Glyph(_g("+", "╝"), "double_bottom_right"))
    dcross: Glyph = field(default_factory=lambda: Glyph(_g("+", "╬"), "double_cross"))

    def box(self, text: str, padding: int = 1) -> str:
        """Render a simple single-line box around text."""
        pad = " " * padding
        inner = f"{pad}{text}{pad}"
        width = display_width(inner)
        return "\n".join(
            [
                f"{self.tl}{self.h * width}{self.tr}",
                f"{self.v}{inner}{self.v}",
                f"{self.bl}{self.h * width}{self.br}",
            ]
        )

    def double_box(self, text: str, padding: int = 1) -> str:
        """Render a simple double-line box around text."""
        pad = " " * padding
        inner = f"{pad}{text}{pad}"
        width = display_width(inner)
        return "\n".join(
            [
                f"{self.dtl}{self.dh * width}{self.dtr}",
                f"{self.dv}{inner}{self.dv}",
                f"{self.dbl}{self.dh * width}{self.dbr}",
            ]
        )

    def table(self, headers: list[str], rows: list[list[str]]) -> str:
        """Render a compact single-line table."""
        if not headers:
            return ""
        if any(len(row) != len(headers) for row in rows):
            raise ValueError("table rows must match header count")

        columns = list(zip(headers, *rows)) if rows else [(header,) for header in headers]
        widths = [max(display_width(str(cell)) for cell in column) + 2 for column in columns]

        def row_line(cells: list[str] | tuple[str, ...]) -> str:
            parts = [f" {pad_right(str(cell), width - 2)} " for cell, width in zip(cells, widths)]
            return f"{self.v}{str(self.v).join(parts)}{self.v}"

        def sep(left: Glyph, mid: Glyph, right: Glyph) -> str:
            return str(left) + str(mid).join(str(self.h) * width for width in widths) + str(right)

        return "\n".join(
            [
                sep(self.tl, self.top, self.tr),
                row_line(headers),
                sep(self.left, self.cross, self.right),
                *(row_line(row) for row in rows),
                sep(self.bl, self.bottom, self.br),
            ]
        )


BoxStyle = Literal["single", "rounded", "bold", "mixed"]


@dataclass(frozen=True)
class RoundedBoxGlyphs:
    """Box-drawing glyphs with rounded corners (╭╮╰╯)."""

    h: Glyph = field(default_factory=lambda: Glyph(_g("-", "─"), "h"))
    v: Glyph = field(default_factory=lambda: Glyph(_g("|", "│"), "v"))
    tl: Glyph = field(default_factory=lambda: Glyph(_g("+", "╭"), "top_left"))
    tr: Glyph = field(default_factory=lambda: Glyph(_g("+", "╮"), "top_right"))
    bl: Glyph = field(default_factory=lambda: Glyph(_g("+", "╰"), "bottom_left"))
    br: Glyph = field(default_factory=lambda: Glyph(_g("+", "╯"), "bottom_right"))
    top: Glyph = field(default_factory=lambda: Glyph(_g("+", "┬"), "top"))
    bottom: Glyph = field(default_factory=lambda: Glyph(_g("+", "┴"), "bottom"))
    left: Glyph = field(default_factory=lambda: Glyph(_g("+", "├"), "left"))
    right: Glyph = field(default_factory=lambda: Glyph(_g("+", "┤"), "right"))
    cross: Glyph = field(default_factory=lambda: Glyph(_g("+", "┼"), "cross"))

    def box(self, text: str, padding: int = 1) -> str:
        """Render a simple rounded-corner box around text."""
        pad = " " * padding
        inner = f"{pad}{text}{pad}"
        inner_dw = display_width(inner)
        h_dw = display_width(str(self.h))
        v_dw = display_width(str(self.v))
        corner_dw = display_width(str(self.tl))
        # display columns needed for the horizontal fill inside the corners
        fill_dw = 2 * v_dw + inner_dw - 2 * corner_dw
        # if h chars are wide (e.g. CJK ambiguous=2), pad inner so fill divides evenly
        if h_dw > 1 and fill_dw % h_dw:
            extra = h_dw - (fill_dw % h_dw)
            inner = inner + " " * extra
            fill_dw += extra
        h_count = fill_dw // h_dw
        return "\n".join(
            [
                f"{self.tl}{self.h * h_count}{self.tr}",
                f"{self.v}{inner}{self.v}",
                f"{self.bl}{self.h * h_count}{self.br}",
            ]
        )


@dataclass(frozen=True)
class BoldBoxGlyphs:
    """Box-drawing glyphs with bold/thick borders (┏┓┗┛┃━)."""

    h: Glyph = field(default_factory=lambda: Glyph(_g("-", "━"), "h"))
    v: Glyph = field(default_factory=lambda: Glyph(_g("|", "┃"), "v"))
    tl: Glyph = field(default_factory=lambda: Glyph(_g("+", "┏"), "top_left"))
    tr: Glyph = field(default_factory=lambda: Glyph(_g("+", "┓"), "top_right"))
    bl: Glyph = field(default_factory=lambda: Glyph(_g("+", "┗"), "bottom_left"))
    br: Glyph = field(default_factory=lambda: Glyph(_g("+", "┛"), "bottom_right"))
    top: Glyph = field(default_factory=lambda: Glyph(_g("+", "┳"), "top"))
    bottom: Glyph = field(default_factory=lambda: Glyph(_g("+", "┻"), "bottom"))
    left: Glyph = field(default_factory=lambda: Glyph(_g("+", "┣"), "left"))
    right: Glyph = field(default_factory=lambda: Glyph(_g("+", "┫"), "right"))
    cross: Glyph = field(default_factory=lambda: Glyph(_g("+", "╋"), "cross"))

    def box(self, text: str, padding: int = 1) -> str:
        """Render a simple bold-border box around text."""
        pad = " " * padding
        inner = f"{pad}{text}{pad}"
        inner_dw = display_width(inner)
        h_dw = display_width(str(self.h))
        v_dw = display_width(str(self.v))
        corner_dw = display_width(str(self.tl))
        fill_dw = 2 * v_dw + inner_dw - 2 * corner_dw
        if h_dw > 1 and fill_dw % h_dw:
            extra = h_dw - (fill_dw % h_dw)
            inner = inner + " " * extra
            fill_dw += extra
        h_count = fill_dw // h_dw
        return "\n".join(
            [
                f"{self.tl}{self.h * h_count}{self.tr}",
                f"{self.v}{inner}{self.v}",
                f"{self.bl}{self.h * h_count}{self.br}",
            ]
        )


@dataclass(frozen=True)
class TreeGlyphs:
    """Tree-drawing glyphs for hierarchical output."""

    branch: Glyph = field(default_factory=lambda: Glyph(_g("|--", "├──"), "branch"))
    last: Glyph = field(default_factory=lambda: Glyph(_g("`--", "└──"), "last"))
    pipe: Glyph = field(default_factory=lambda: Glyph(_g("|", "│"), "pipe"))
    blank: Glyph = field(default_factory=lambda: Glyph(" ", "blank"))

    def render(self, entries: list[tuple[str, bool, list | None]]) -> str:
        """Render nested entries as a tree."""
        lines: list[str] = []

        def visit(nodes: list[tuple[str, bool, list | None]], prefix: str = "") -> None:
            for index, (name, is_dir, children) in enumerate(nodes):
                is_last = index == len(nodes) - 1
                connector = self.last if is_last else self.branch
                suffix = "/" if is_dir else ""
                lines.append(f"{prefix}{connector} {name}{suffix}")
                if children:
                    extension = (str(self.blank) * 4) if is_last else f"{self.pipe}{self.blank * 3}"
                    visit(children, prefix=f"{prefix}{extension}")

        visit(entries)
        return "\n".join(lines)


@dataclass(frozen=True)
class ProgressGlyphs:
    """Progress bars and spinner frames for terminal status output."""

    full: Glyph = field(default_factory=lambda: Glyph(_g("#", "█"), "full"))
    high: Glyph = field(default_factory=lambda: Glyph(_g("=", "▓"), "high"))
    mid: Glyph = field(default_factory=lambda: Glyph(_g("-", "▒"), "mid"))
    low: Glyph = field(default_factory=lambda: Glyph(_g(".", "░"), "low"))
    empty: Glyph = field(default_factory=lambda: Glyph(" ", "empty"))
    bar_left: Glyph = field(default_factory=lambda: Glyph(_g("[", "▕"), "bar_left"))
    bar_right: Glyph = field(default_factory=lambda: Glyph(_g("]", "▏"), "bar_right"))

    SPINNER_BRAILLE: tuple[str, ...] = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
    SPINNER_ASCII: tuple[str, ...] = ("|", "/", "-", "\\")
    SPINNER_ARROW: tuple[str, ...] = ("←", "↖", "↑", "↗", "→", "↘", "↓", "↙")
    SPINNER_BOUNCE: tuple[str, ...] = (
        "▁",
        "▃",
        "▄",
        "▅",
        "▆",
        "▇",
        "█",
        "▇",
        "▆",
        "▅",
        "▄",
        "▃",
    )

    def spinner(self, style: str = "braille") -> Iterator[str]:
        """Return an infinite spinner frame iterator."""
        frames = {
            "braille": self.SPINNER_BRAILLE,
            "ascii": self.SPINNER_ASCII,
            "arrow": self.SPINNER_ARROW,
            "bounce": self.SPINNER_BOUNCE,
        }
        source = (
            self.SPINNER_ASCII if IS_LEGACY_TERMINAL else frames.get(style, self.SPINNER_BRAILLE)
        )
        return itertools.cycle(source)

    def render_bar(self, value: float, width: int = 20) -> str:
        """Render a whole-cell progress bar."""
        clamped = max(0.0, min(1.0, value))
        filled = round(clamped * width)
        bar = str(self.full) * filled + str(self.low) * (width - filled)
        return f"{self.bar_left}{bar}{self.bar_right} {clamped:.0%}"


@dataclass(frozen=True)
class ArrowGlyphs:
    """Directional glyphs for transitions and actions."""

    right: Glyph = field(default_factory=lambda: Glyph(_g("->", "→"), "right"))
    left: Glyph = field(default_factory=lambda: Glyph(_g("<-", "←"), "left"))
    up: Glyph = field(default_factory=lambda: Glyph(_g("^", "↑"), "up"))
    down: Glyph = field(default_factory=lambda: Glyph(_g("v", "↓"), "down"))


@dataclass(frozen=True)
class BulletGlyphs:
    """Status glyphs for compact terminal output."""

    dot: Glyph = field(default_factory=lambda: Glyph(_g("*", "•"), "dot"))
    ok: Glyph = field(default_factory=lambda: Glyph(_g("[OK]", "✔"), "ok"))
    skip: Glyph = field(default_factory=lambda: Glyph(_g("[-]", "⊖"), "skip"))
    warning: Glyph = field(default_factory=lambda: Glyph(_g("/!\\", "▲"), "warning"))
    error: Glyph = field(default_factory=lambda: Glyph(_g("[E]", "✖"), "error"))


@dataclass(frozen=True)
class TypographyGlyphs:
    """Typography glyphs that benefit from fallbacks."""

    ellipsis: Glyph = field(default_factory=lambda: Glyph(_g("...", "…"), "ellipsis"))
    mdash: Glyph = field(default_factory=lambda: Glyph(_g("--", "—"), "mdash"))
    ndash: Glyph = field(default_factory=lambda: Glyph(_g("-", "–"), "ndash"))


@dataclass(frozen=True)
class DiffGlyphs:
    """Minimal diff glyphs for file and line summaries."""

    added: Glyph = field(default_factory=lambda: Glyph("+", "added"))
    removed: Glyph = field(default_factory=lambda: Glyph("-", "removed"))
    modified: Glyph = field(default_factory=lambda: Glyph("~", "modified"))
    unchanged: Glyph = field(default_factory=lambda: Glyph(" ", "unchanged"))
    renamed: Glyph = field(default_factory=lambda: Glyph(_g("=>", "⇒"), "renamed"))
    moved: Glyph = field(default_factory=lambda: Glyph(_g("->", "→"), "moved"))
    conflict: Glyph = field(default_factory=lambda: Glyph(_g("!=", "≠"), "conflict"))

    def line(self, kind: str, text: str, lineno: int | None = None) -> str:
        """Render a compact diff line."""
        glyph_map = {
            "added": self.added,
            "removed": self.removed,
            "modified": self.modified,
            "unchanged": self.unchanged,
        }
        glyph = glyph_map.get(kind, self.unchanged)
        prefix = f"{lineno:>4} " if lineno is not None else ""
        return f"{prefix}{glyph} {text}"


@dataclass(frozen=True)
class GitGlyphs:
    """Git-centric glyphs for future status and log summaries."""

    branch: Glyph = field(default_factory=lambda: Glyph(_g("br", "⎇"), "branch"))
    commit: Glyph = field(default_factory=lambda: Glyph(_g("o", "●"), "commit"))
    ahead: Glyph = field(default_factory=lambda: Glyph(_g("^", "↑"), "ahead"))
    behind: Glyph = field(default_factory=lambda: Glyph(_g("v", "↓"), "behind"))
    clean: Glyph = field(default_factory=lambda: Glyph(_g("OK", "✔"), "clean"))
    dirty: Glyph = field(default_factory=lambda: Glyph(_g("*", "✎"), "dirty"))
    modified: Glyph = field(default_factory=lambda: Glyph("~", "modified"))
    untracked: Glyph = field(default_factory=lambda: Glyph("?", "untracked"))
    ref_l: Glyph = field(default_factory=lambda: Glyph("(", "ref_left"))
    ref_r: Glyph = field(default_factory=lambda: Glyph(")", "ref_right"))

    def status_line(
        self,
        branch_name: str,
        *,
        ahead: int = 0,
        behind: int = 0,
        modified: int = 0,
        untracked: int = 0,
    ) -> str:
        """Render a compact git status line."""
        parts = [f"{self.branch} {branch_name}"]
        if ahead:
            parts.append(f"{self.ahead}{ahead}")
        if behind:
            parts.append(f"{self.behind}{behind}")
        if modified:
            parts.append(f"{self.modified}{modified}")
        if untracked:
            parts.append(f"{self.untracked}{untracked}")
        parts.append(str(self.clean if not (modified or untracked) else self.dirty))
        return "  ".join(parts)

    def log_line(self, sha: str, message: str, refs: list[str] | tuple[str, ...] = ()) -> str:
        """Render a compact git log line."""
        ref_text = ""
        if refs:
            joined = " ".join(f"{self.ref_l}{ref}{self.ref_r}" for ref in refs)
            ref_text = f" {joined}"
        return f"{self.commit} {sha[:7]}{ref_text} {message}"


@dataclass(frozen=True)
class GlyphSet:
    """Shared glyph registry for terminal output."""

    box: BoxGlyphs = field(default_factory=BoxGlyphs)
    rounded_box: RoundedBoxGlyphs = field(default_factory=RoundedBoxGlyphs)
    bold_box: BoldBoxGlyphs = field(default_factory=BoldBoxGlyphs)
    tree: TreeGlyphs = field(default_factory=TreeGlyphs)
    progress: ProgressGlyphs = field(default_factory=ProgressGlyphs)
    arrow: ArrowGlyphs = field(default_factory=ArrowGlyphs)
    bullet: BulletGlyphs = field(default_factory=BulletGlyphs)
    typography: TypographyGlyphs = field(default_factory=TypographyGlyphs)
    diff: DiffGlyphs = field(default_factory=DiffGlyphs)
    git: GitGlyphs = field(default_factory=GitGlyphs)


GLYPHS = GlyphSet()
