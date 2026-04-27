"""Font emphasis helpers for terminal output.

Terminals do not support arbitrary font families reliably, but they do support
common emphasis attributes such as bold, italic, and underline via ANSI SGR.
"""

from __future__ import annotations

from dataclasses import dataclass

from repo_release_tools.ui.color import Style, apply


@dataclass(frozen=True)
class Emphasis:
    """Terminal-safe emphasis options."""

    bold: bool = False
    italic: bool = False
    underline: bool = False
    dim: bool = False


def emphasize(text: str, emphasis: Emphasis) -> str:
    """Apply emphasis to *text* using ANSI styles when supported."""
    return apply(
        text,
        Style(
            bold=emphasis.bold,
            italic=emphasis.italic,
            underline=emphasis.underline,
            dim=emphasis.dim,
        ),
    )


def bold(text: str) -> str:
    """Render bold text."""
    return emphasize(text, Emphasis(bold=True))


def italic(text: str) -> str:
    """Render italic text."""
    return emphasize(text, Emphasis(italic=True))


def underline(text: str) -> str:
    """Render underlined text."""
    return emphasize(text, Emphasis(underline=True))
