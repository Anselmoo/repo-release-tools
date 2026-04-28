"""Pure-Python ANSI styling utilities for rrt terminal output.

This module intentionally avoids hard dependencies and degrades gracefully:

* no ANSI on legacy terminals / non-interactive output
* no ANSI when ``NO_COLOR`` is set
* optional explicit override with ``RRT_COLOR`` when ``NO_COLOR`` is unset
"""

from __future__ import annotations

import os
import sys

from dataclasses import dataclass
from typing import IO, Literal


ColorLevel = Literal["none", "standard", "256", "truecolor"]

# Named semantic colors used by apply_style().
_NAMED_STYLES: dict[str, "Style"] = {}  # populated after Style is defined


def detect_color_level() -> ColorLevel:
    """Detect the ANSI color level supported by the current terminal."""
    if os.environ.get("NO_COLOR") is not None:
        return "none"

    override = os.environ.get("RRT_COLOR", "").strip().lower()
    if override in {"0", "off", "false", "none"}:
        return "none"
    if override in {"1", "on", "true", "standard"}:
        return "standard"
    if override in {"256", "8bit"}:
        return "256"
    if override in {"24bit", "truecolor"}:
        return "truecolor"

    term = os.environ.get("TERM", "")
    colorterm = os.environ.get("COLORTERM", "").lower()

    if term == "dumb":
        return "none"
    if "truecolor" in colorterm or "24bit" in colorterm:
        return "truecolor"
    if "256color" in term:
        return "256"

    # Keep legacy windows conservative by default.
    if sys.platform == "win32" and "WT_SESSION" not in os.environ:
        return "none"

    return "standard"


def supports_color(stream: IO[str] | None = None) -> bool:
    """Return whether ANSI styling should be emitted for the given stream."""
    override = os.environ.get("RRT_COLOR", "").strip().lower()
    if override in {"1", "on", "true", "standard", "256", "8bit", "24bit", "truecolor"}:
        return detect_color_level() != "none"
    if stream is None:
        stream = sys.stdout
    return stream.isatty() and detect_color_level() != "none"


def _rgb_to_ansi(r: int, g: int, b: int, *, bg: bool = False) -> str:
    """Convert an RGB triple to the best ANSI code for the detected color level.

    * truecolor → ``38;2;r;g;b`` / ``48;2;r;g;b``
    * 256-color  → nearest xterm-256 index
    * standard   → nearest of 8 standard colors (index 30-37 / 40-47)
    """
    level = detect_color_level()
    base = 48 if bg else 38
    if level == "truecolor":
        return f"{base};2;{r};{g};{b}"
    if level == "256":
        # Map to xterm 216-color cube: indices 16–231
        ri, gi, bi = (round(c / 255 * 5) for c in (r, g, b))
        idx = 16 + 36 * ri + 6 * gi + bi
        return f"{base};5;{idx}"
    # Standard 8-color: pick nearest by luminance-weighted distance
    _STD = [
        (0, 0, 0),
        (128, 0, 0),
        (0, 128, 0),
        (128, 128, 0),
        (0, 0, 128),
        (128, 0, 128),
        (0, 128, 128),
        (192, 192, 192),
    ]
    best = min(range(8), key=lambda i: sum((a - b_) ** 2 for a, b_ in zip((r, g, b), _STD[i])))
    return str((40 if bg else 30) + best)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Parse a hex color string like ``#ff6400`` or ``ff6400`` to (r, g, b)."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        raise ValueError(f"Invalid hex color: {hex_color!r}")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def apply(
    text: str,
    style: "Style",
    *,
    fg: tuple[int, int, int] | str | None = None,
    bg: tuple[int, int, int] | str | None = None,
    stream: IO[str] | None = None,
) -> str:
    """Apply ANSI style to text when supported, otherwise return plain text.

    ``fg`` and ``bg`` accept:

    * ``(r, g, b)`` — RGB triple, auto-mapped to truecolor/256/standard
    * ``"#rrggbb"`` or ``"rrggbb"`` — hex string, same mapping
    * ``None``      — use the fg/bg codes from *style*
    """
    if not supports_color(stream):
        return text

    codes: list[str] = []
    if style.bold:
        codes.append("1")
    if style.dim:
        codes.append("2")
    if style.italic:
        codes.append("3")
    if style.underline:
        codes.append("4")

    # Resolve foreground: explicit override > style.fg
    if fg is not None:
        rgb = _hex_to_rgb(fg) if isinstance(fg, str) else fg
        codes.append(_rgb_to_ansi(*rgb))
    elif style.fg is not None:
        codes.append(str(style.fg))

    # Resolve background: explicit override > style.bg
    if bg is not None:
        rgb_bg = _hex_to_rgb(bg) if isinstance(bg, str) else bg
        codes.append(_rgb_to_ansi(*rgb_bg, bg=True))
    elif style.bg is not None:
        codes.append(str(style.bg))

    if not codes:
        return text
    prefix = "\x1b[" + ";".join(codes) + "m"
    return f"{prefix}{text}\x1b[0m"


@dataclass(frozen=True)
class Style:
    """ANSI text style descriptor."""

    fg: int | None = None
    bg: int | None = None
    bold: bool = False
    italic: bool = False
    underline: bool = False
    dim: bool = False


def apply_style(
    text: str,
    *,
    bold: bool = False,
    italic: bool = False,
    underline: bool = False,
    dim: bool = False,
    color: "str | Style | None" = None,
    fg: "tuple[int, int, int] | str | None" = None,
    bg: "tuple[int, int, int] | str | None" = None,
    stream: IO[str] | None = None,
) -> str:
    """Apply combined color and emphasis in a single call.

    ``color`` accepts a named style key (``"success"``, ``"warning"``,
    ``"error"``, ``"info"``, ``"subtle"``) or a ``Style`` instance.
    ``fg``/``bg`` accept RGB triples or hex strings for precise colors.

    Example::

        apply_style("Done!", bold=True, color="success")
        apply_style("hex", fg="#ff6400", bold=True)
    """
    base_style: Style
    if isinstance(color, Style):
        base_style = color
    elif isinstance(color, str):
        base_style = _NAMED_STYLES.get(color, Style())
    else:
        base_style = Style()

    merged = Style(
        fg=base_style.fg,
        bg=base_style.bg,
        bold=bold or base_style.bold,
        italic=italic or base_style.italic,
        underline=underline or base_style.underline,
        dim=dim or base_style.dim,
    )
    return apply(text, merged, fg=fg, bg=bg, stream=stream)


def success(text: str, *, stream: IO[str] | None = None) -> str:
    """Render success-themed text."""
    return apply(text, Style(fg=32, bold=True), stream=stream)


def warning(text: str, *, stream: IO[str] | None = None) -> str:
    """Render warning-themed text."""
    return apply(text, Style(fg=33, bold=True), stream=stream)


def error(text: str, *, stream: IO[str] | None = None) -> str:
    """Render error-themed text."""
    return apply(text, Style(fg=31, bold=True), stream=stream)


def info(text: str, *, stream: IO[str] | None = None) -> str:
    """Render info-themed text."""
    return apply(text, Style(fg=36, italic=True), stream=stream)


def subtle(text: str, *, stream: IO[str] | None = None) -> str:
    """Render subtle/de-emphasized text."""
    return apply(text, Style(fg=90), stream=stream)


def heading(text: str, *, stream: IO[str] | None = None) -> str:
    """Render a structural section heading (gold bold, no italic/underline)."""
    return apply(text, Style(fg=33, bold=True), stream=stream)


def chrome(text: str, *, stream: IO[str] | None = None) -> str:
    """Render structural chrome such as rule separators (gold dim)."""
    return apply(text, Style(fg=33, dim=True), stream=stream)


# ── Theme system ─────────────────────────────────────────────────────────────

#: Built-in named themes.  Each theme is a mapping of semantic role →
#: ``Style``.  Callers that want custom colour schemes can call
#: :func:`set_theme` with a theme name or pass a mapping directly.
THEMES: dict[str, dict[str, Style]] = {
    "default": {
        "success": Style(fg=32, bold=True),
        "warning": Style(fg=33, bold=True),
        "error": Style(fg=31, bold=True),
        "info": Style(fg=36, italic=True),
        "subtle": Style(fg=90),
        "heading": Style(fg=33, bold=True),
        "chrome": Style(fg=33, dim=True),
    },
    "monochrome": {
        "success": Style(bold=True),
        "warning": Style(bold=True, underline=True),
        "error": Style(bold=True),
        "info": Style(italic=True),
        "subtle": Style(dim=True),
        "heading": Style(bold=True),
        "chrome": Style(dim=True),
    },
    "pastel": {
        "success": Style(fg=114, bold=True),  # soft green
        "warning": Style(fg=221, bold=True),  # soft yellow
        "error": Style(fg=203, bold=True),  # soft red
        "info": Style(fg=117, italic=True),  # soft blue
        "subtle": Style(fg=102),  # muted grey
        "heading": Style(fg=221, bold=True),  # soft yellow
        "chrome": Style(fg=221, dim=True),  # soft yellow dim
    },
}


def set_theme(name_or_styles: str | dict[str, Style]) -> None:
    """Apply a named theme or a custom style mapping to the semantic colour registry.

    After calling ``set_theme("pastel")`` all semantic helpers such as
    :func:`success` and :func:`warning` will render with the pastel palette.

    Parameters
    ----------
    name_or_styles:
        Either a theme name from :data:`THEMES` (``"default"``,
        ``"monochrome"``, ``"pastel"``) or a dict mapping semantic role
        strings to :class:`Style` instances.
    """
    if isinstance(name_or_styles, str):
        try:
            styles = THEMES[name_or_styles]
        except KeyError as exc:
            available = ", ".join(sorted(THEMES))
            raise ValueError(f"Unknown theme {name_or_styles!r}. Available: {available}") from exc
    else:
        styles = name_or_styles

    _NAMED_STYLES.update(styles)


def get_theme() -> dict[str, Style]:
    """Return a snapshot of the current semantic style registry."""
    return dict(_NAMED_STYLES)


# Populate named style registry after all style helpers are defined.
_NAMED_STYLES.update(
    {
        "success": Style(fg=32, bold=True),
        "warning": Style(fg=33, bold=True),
        "error": Style(fg=31, bold=True),
        "info": Style(fg=36, italic=True),
        "subtle": Style(fg=90),
        "heading": Style(fg=33, bold=True),
        "chrome": Style(fg=33, dim=True),
    }
)
