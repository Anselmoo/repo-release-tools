"""Small platform-aware glyph registry for repo-release-tools.

This module is intentionally narrow. It adapts a few ideas from the author's
broader glyph/emoji exploration into a stable, non-emoji terminal layer for
rrt. The public surface is kept compact so CLI output stays predictable.
"""

from __future__ import annotations

import sys

from dataclasses import dataclass, field


IS_LEGACY_TERMINAL = sys.platform == "win32"


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
    arrow: ArrowGlyphs = field(default_factory=ArrowGlyphs)
    bullet: BulletGlyphs = field(default_factory=BulletGlyphs)
    typography: TypographyGlyphs = field(default_factory=TypographyGlyphs)
    diff: DiffGlyphs = field(default_factory=DiffGlyphs)
    git: GitGlyphs = field(default_factory=GitGlyphs)


GLYPHS = GlyphSet()
