"""ASCII banner and PNG export for repo-release-tools."""

from __future__ import annotations

import os
import sys
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING

from repo_release_tools import __version__
from repo_release_tools.ui import align
from repo_release_tools.ui.glyphs import display_width, pad_right

if TYPE_CHECKING:
    from typing import LiteralString

# High-Readability Arcade Splash Screen Style (Emoji-free).
# Features the full name Repo-Release-Tools split into three readable lines.


_BANNER_ROW_WIDTH = 74

_BANNER_EXPORTS: dict[str, tuple[str, tuple[int, int, int]]] = {
    # GitHub dark theme: a bright mint foreground pops against the dark page.
    "unicode": ("banner.png", (195, 255, 196)),
    # GitHub light theme: a deeper green keeps the banner readable on white.
    "light": ("banner-light.png", (24, 102, 53)),
    # ASCII fallback stays available as the Windows-friendly export.
    "ascii": ("banner-windows.png", (204, 204, 204)),
}


def _fit_banner_row(text: str) -> str:
    """Fit a dynamic banner row to the fixed HUD width."""
    return align(text, _BANNER_ROW_WIDTH)


def _normalize_banner(banner: str) -> str:
    """Pad each rendered line so the full banner stays rectangular.

    Uses ``pad_right`` instead of ``align`` to avoid the truncation path that
    ``align`` applies when ``display_width(line) >= width``.  A banner line is
    never truncated — it is only right-padded to match the widest line.
    """
    lines = banner.splitlines()
    if not lines:
        return banner

    width = max(display_width(line) for line in lines)

    left_frame = {"|", "+", "║", "╔", "╠", "╚"}
    right_frame = {"|", "+", "║", "╗", "╣", "╝"}

    normalized: list[str] = []
    for line in lines:
        clean = line.rstrip(" ")
        missing = max(0, width - display_width(clean))
        if missing > 0 and len(clean) >= 2 and clean[0] in left_frame and clean[-1] in right_frame:
            # Keep border glyphs on fixed columns by padding before the trailing border.
            normalized.append(f"{clean[:-1]}{' ' * missing}{clean[-1]}")
            continue

        normalized.append(pad_right(clean, width))

    return "\n".join(normalized)


def _collect_metrics() -> dict[str, str]:
    """Collect live code-based metrics and system facts for the HUD."""
    src_root = Path(__file__).parent.parent.parent
    commands_dir = src_root / "repo_release_tools" / "commands"
    test_root = src_root.parent / "tests"

    tools_count = 0
    if commands_dir.exists():
        tools_count = len([f for f in commands_dir.glob("*.py") if f.name != "__init__.py"])

    loc_count = 0
    file_count = 0
    for py_file in src_root.rglob("*.py"):
        file_count += 1
        try:
            with open(py_file, encoding="utf-8") as f:
                loc_count += len([line for line in f if line.strip()])
        except (OSError, UnicodeDecodeError):
            continue

    test_count = 0
    if test_root.exists():
        test_count = len(list(test_root.rglob("test_*.py")))

    # Hard facts
    branch = "UNKNOWN"
    with suppress(Exception):
        # Fast way to get branch without subprocess
        head_path = src_root.parent / ".git" / "HEAD"
        if head_path.exists():
            content = head_path.read_text().strip()
            branch = content.split("/")[-1].upper() if "/" in content else content[:7].upper()

    return {
        "ver": __version__,
        "tools": str(tools_count),
        "loc": f"{loc_count / 1000:.1f}k" if loc_count >= 1000 else str(loc_count),
        "files": str(file_count),
        "tests": str(test_count),
        "py": f"{sys.version_info.major}.{sys.version_info.minor}",
        "os": sys.platform.upper(),
        "branch": branch,
    }


BANNER_UNICODE_TEMPLATE: LiteralString = r"""
╔════════════════════════════════════════════════════════════════════════════════════════════╗
║▓▒░▒▓▓▒░▒▓▓▒░▒▓▓▒░▒▓▓▒░▒▓▓▒░▒▓▓▒░▒▓▓▒░▒▓▓▒░▒▓▓▒░▒▓▓▒░▒▓▓▒░▒▓▓▒░▒▓▓▒░▒▓▓▒░▒▓▓▒░▒▓▓▒░▒▓▓▒░▒▓▓▒║
║░                                                                                          ░║
║    ██████╗ ███████╗██████╗  ██████╗                                                       ║
║    ██╔══██╗██╔════╝██╔══██╗██╔═══██╗                                                      ║
║    ██████╔╝█████╗  ██████╔╝██║   ██║                                                      ║
║    ██╔══██╗██╔══╝  ██╔═══╝ ██║   ██║                                                      ║
║    ██║  ██║███████╗██║     ╚██████╔╝                                                      ║
║    ╚═╝  ╚═╝╚══════╝╚═╝      ╚═════╝                                                       ║
║                                                                                            ║
║     ██████╗ ███████╗██╗     ███████╗ █████╗ ███████╗███████╗                               ║
║     ██╔══██╗██╔════╝██║     ██╔════╝██╔══██╗██╔════╝██╔════╝                               ║
║     ██████╔╝█████╗  ██║     █████╗  ███████║███████╗█████╗                                 ║
║     ██╔══██╗██╔══╝  ██║     ██╔══╝  ██╔══██║╚════██║██╔══╝                                 ║
║     ██║  ██║███████╗███████╗███████╗██║  ██║███████║███████╗                               ║
║     ╚═╝  ╚═╝╚══════╝╚══════╝╚══════╝╚═╝  ╚═╝╚══════╝╚══════╝                               ║
║                                                                                            ║
║     ████████╗ ██████╗  ██████╗ ██╗     ███████╗                                     ║
║     ╚══██╔══╝██╔═══██╗██╔═══██╗██║     ██╔════╝                                     ║
║        ██║   ██║   ██║██║   ██║██║     ███████╗                                     ║
║        ██║   ██║   ██║██║   ██║██║     ╚════██║                                     ║
║        ██║   ╚██████╔╝╚██████╔╝███████╗███████║                                     ║
║        ╚═╝    ╚═════╝  ╚═════╝ ╚══════╝╚══════╝                                     ║
║                                                                                            ║
║░                                                                                          ░║
║      ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓         ║
║      ┃ {hud_line}┃         ║
║      ┃ {stats_line}┃         ║
║      ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛         ║
║                                                                                            ║
╠════════════════════════════════════════════════════════════════════════════════════════════╣
║▒░▓▒░▓▒░▓▒░▓▒░▓▒░▓▒░▓▒░▓▒░▓▒░▓▒░▓▒░▓▒░▓▒░▓▒░▓▒░▓▒░▓▒░▓▒░▓▒░▓▒░▓▒░▓▒░▓▒░▓▒░▓▒░▓▒░▓▒░▓▒░▓▒░▓▒░║
║                                                                                            ║
║         *                 .                     ✦                  .             ☾         ║
║                                                                                            ║
║           ╔══════════════════════════════════════════════════════════════╗                 ║
║           ║  PIPELINE ENGINE ▐  STATE: OPTIMAL ▐  LINK: ★                ║                 ║
║           ╠══════════════════════════════════════════════════════════════╣                 ║
║           ║  COVERAGE ████████████████████████████████████ 100%          ║                 ║
║           ║  TESTS   ✔ ✔ ✔ ✔ ✔ ✔ ✔ ✔ ✔ ✔ ✔ ✔ ✔ ✔ ✔ ✔ ✔ ✔ ✔ ✔             ║                 ║
║           ║  HEALTH  ○ ○ ○ ○ ○ ○ ○ ○ ○ ○ ○ ○ ○ ○ ○ ○ ○ ○ ○ ○ ○ ○         ║                 ║
║           ╚══════════════════════════════════════════════════════════════╝                 ║
║                                                                                            ║
║           ╭──────╮         ╭──────╮         ╭──────╮         ╭──────╮                      ║
║      ═════┥ BUMP ┝═════════┥ TAG  ┝═════════┥ DOCS ┝═════════┥ SHIP ┝═══════              ║
║           ╰──┬───╯         ╰──┬───╯         ╰──┬───╯         ╰──┬───╯                      ║
║              │                │                │                │                          ║
║             ╱█╲              ╱█╲              ╱█╲              ╱█╲                         ║
║            ╱███╲            ╱███╲            ╱███╲            ╱███╲                        ║
║                                                                                            ║
║▓▒░▒▓▓▒░▒▓▓▒░▒▓▓▒░▒▓▓▒░▒▓▓▒░▒▓▓▒░▒▓▓▒░▒▓▓▒░▒▓▓▒░▒▓▓▒░▒▓▓▒░▒▓▓▒░▒▓▓▒░▒▓▓▒░▒▓▓▒░▒▓▓▒░▒▓▓▒░▒▓▓▒║
╠════════════════════════════════════════════════════════════════════════════════════════════╣
║  MIT License 2026              GITHUB.COM/ANSELMOO/REPO-RELEASE-TOOLS                      ║
╚════════════════════════════════════════════════════════════════════════════════════════════╝
""".strip()

# ASCII template removed: we render from the Unicode template and use
# `_apply_ascii_fallbacks()` for ASCII output to keep layouts consistent.


def get_banner(variant: str = "unicode", version: str = __version__) -> str:
    """Return the rendered banner for the given variant."""
    metrics = _collect_metrics()
    metrics["ver"] = version

    # Dynamic line formatting with block separators for a professional console feel
    sep = " ▐ " if variant == "unicode" else " | "

    # SYSTEM HUD: Version, Python, OS, Branch
    sys_parts = [
        f"VER {metrics['ver']}",
        f"PY {metrics['py']}",
        f"OS {metrics['os']}",
        f"BRANCH {metrics['branch']}",
    ]
    hud_line = _fit_banner_row(f"SYSTEM {sep} {sep.join(sys_parts)}")

    # STATUS HUD: Tools, LOC, Files, Tests
    stat_parts = [
        f"TOOLS {metrics['tools']}",
        f"LOC {metrics['loc']}",
        f"FILES {metrics['files']}",
        f"TESTS {metrics['tests']}",
    ]
    stats_line = _fit_banner_row(f"STATUS {sep} {sep.join(stat_parts)}")

    # Always base the rendered banner on the Unicode template.  When an ASCII
    # variant is requested we produce it by mapping unsupported glyphs to the
    # safe fallbacks defined in `_PNG_SAFE_FALLBACKS` so the layout stays
    # identical between variants while still providing an ASCII-friendly
    # representation.
    template = BANNER_UNICODE_TEMPLATE
    banner = _normalize_banner(template.format(hud_line=hud_line, stats_line=stats_line))

    return _apply_ascii_fallbacks(banner) if variant == "ascii" else banner


_MONOSPACE_CANDIDATES = [
    "/System/Library/Fonts/Menlo.ttc",
    "/System/Library/Fonts/SFNSMono.ttf",
    "/System/Library/Fonts/Supplemental/Courier New.ttf",
    "/System/Library/Fonts/Supplemental/Andale Mono.ttf",
    "/Library/Fonts/DejaVuSansMono.ttf",
    "/Library/Fonts/NotoSansMono-Regular.ttf",
    "DejaVuSansMono.ttf",
    "DejaVuSansMono",
    "Courier New.ttf",
    "Courier New",
    "Menlo.ttc",
    "Menlo",
    "Consolas.ttf",
    "Consolas",
    "CourierNew.ttf",
    "LiberationMono-Regular.ttf",
    "UbuntuMono-R.ttf",
]

_PNG_SAFE_FALLBACKS = {
    "✦": "*",
    "☾": "o",
    "★": "*",
    "⚑": "^",
    "✔": "v",
    "○": "o",
    # Box drawing and shading fallbacks for fonts with incomplete glyph sets
    "╔": "+",
    "╗": "+",
    "╚": "+",
    "╝": "+",
    "═": "-",
    "║": "|",
    "╠": "+",
    "╣": "+",
    "╦": "+",
    "╩": "+",
    "╬": "+",
    "┏": "+",
    "┓": "+",
    "┗": "+",
    "┛": "+",
    "┃": "|",
    "━": "-",
    "─": "-",
    "│": "|",
    "┬": "+",
    "┥": ">",
    "┝": "<",
    "▓": "#",
    "▒": "=",
    "░": ".",
    "█": "#",
    "▐": "|",
    "▌": "|",
    "╭": "+",
    "╮": "+",
    "╯": "+",
    "╰": "+",
    "╱": "/",
    "╲": "\\",
}


def _apply_ascii_fallbacks(s: str) -> str:
    """Return an ASCII-safe copy of a banner string by applying the per-character fallback table."""
    table = {ord(k): v for k, v in _PNG_SAFE_FALLBACKS.items()}
    return s.translate(table)


# The ASCII template has been removed in favor of rendering from the
# Unicode template and applying safe fallbacks when an ASCII representation
# is requested. This keeps layouts identical while avoiding duplicated
# template maintenance.


# Legacy constants for compatibility with existing code/tests
BANNER_UNICODE = get_banner("unicode")
BANNER_ASCII = get_banner("ascii")


def export_banner_png(
    banner_str: str,
    output_path: str | Path,
    *,
    font_size: int = 14,
    bg: tuple[int, int, int, int] = (0, 0, 0, 0),
    fg: tuple[int, int, int] = (204, 204, 204),
    padding: int = 24,
) -> None:
    """Render a banner string to a PNG image using a strict character grid.

    Each character is placed at an exact ``(col * char_w, row * line_height)``
    pixel coordinate so that the PNG output mirrors the terminal's fixed-width
    grid precisely regardless of font kerning or Unicode block widths.
    Wide characters (east-Asian width F/W) advance two cell columns.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise RuntimeError(
            "Pillow is required for PNG export. Install it with: pip install pillow"
        ) from exc

    from repo_release_tools.ui.glyphs import display_width

    lines = banner_str.splitlines()

    font: ImageFont.FreeTypeFont | ImageFont.ImageFont | None = None
    using_default_font = False

    # Allow an explicit font override via environment for deterministic
    # rendering on CI or developer machines. Examples: '/Library/Fonts/DejaVuSansMono.ttf'
    env_font = os.environ.get("RRT_BANNER_FONT")
    force_unicode = os.environ.get("RRT_BANNER_FORCE_UNICODE") == "1"

    if env_font:
        try:
            font = ImageFont.truetype(env_font, font_size)
        except (OSError, AttributeError):
            font = None

    if font is None:
        for candidate in _MONOSPACE_CANDIDATES:
            try:
                font = ImageFont.truetype(candidate, font_size)
                break
            except (OSError, AttributeError):
                continue

    if font is None:
        font = ImageFont.load_default()
        using_default_font = True

    # Measure a single monospace cell with the reference character "M".
    dummy = Image.new("RGB", (1, 1))
    draw_dummy = ImageDraw.Draw(dummy)
    bbox = draw_dummy.textbbox((0, 0), "M", font=font)
    char_w = max(1, int(bbox[2] - bbox[0]))
    char_h = max(1, int(bbox[3] - bbox[1]))
    line_height = char_h + 4

    # Canvas size is determined purely from the grid dimensions, not from
    # Pillow's own string-measurement which may include kerning drift.
    max_cols = max((display_width(line) for line in lines), default=0)
    img_w = max_cols * char_w + padding * 2
    img_h = len(lines) * line_height + padding * 2

    img = Image.new("RGBA", (img_w, img_h), bg)
    row_pixel_width = max_cols * char_w

    for row, line in enumerate(lines):
        y = padding + row * line_height
        # Draw each row onto a clipped surface first so glyph overhang at line
        # ends cannot leak into the right margin and create vertical artifacts.
        row_img = Image.new("RGBA", (row_pixel_width, line_height), (0, 0, 0, 0))
        col = 0  # current grid column (in terminal cells)
        for char in line:
            # Apply safe fallbacks only when we are using the Pillow default
            # font (which often lacks many box/emoji glyphs). When a system
            # monospace font is found we prefer the original glyph so the PNG
            # matches the terminal output as closely as possible.
            # Respect explicit force-unicode flag: when set we keep the
            # original glyphs even if the loaded font is the Pillow default
            # (which may render tofu boxes on some systems). Otherwise, when
            # using the default font we apply the ASCII-safe fallbacks to
            # avoid ugly missing-glyph boxes in the output image.
            safe_char = (
                char
                if (not using_default_font or force_unicode)
                else _PNG_SAFE_FALLBACKS.get(char, char)
            )

            cell_count = display_width(char)
            cell_w = char_w * cell_count

            # Render each character into its own cell image to prevent negative
            # bearings or kerning from overlapping neighbouring cells.
            char_img = Image.new("RGBA", (cell_w, line_height), (0, 0, 0, 0))
            char_draw = ImageDraw.Draw(char_img)
            char_draw.text((0, 0), safe_char, font=font, fill=fg)

            x = col * char_w
            row_img.paste(char_img, (x, 0), char_img)

            # Advance by terminal cell width using the same logic as banner layout.
            col += cell_count
        img.paste(row_img, (padding, y), row_img)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out))


def _main() -> None:
    """Export banner PNG(s).

    Usage:
        banner.py [out_dir_or_file] [variant]

    When *variant* is ``"all"`` (the default when no variant is supplied),
    the GitHub theme pair and the ASCII-fallback (Windows) variant are
    exported side-by-side:

        <out_dir>/banner.png          — Unicode variant (Linux / macOS)
        <out_dir>/banner-light.png    — light-theme variant (GitHub light mode)
        <out_dir>/banner-windows.png  — ASCII-fallback variant (Windows)

    Passing an explicit variant (``"unicode"``, ``"light"`` or ``"ascii"``)
    exports only that variant to the path given as the first argument.
    """
    first_arg = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs/assets")
    variant = sys.argv[2] if len(sys.argv) > 2 else "all"

    if variant == "all":
        # Export both platforms at once into the same directory.
        out_dir = first_arg if first_arg.suffix == "" else first_arg.parent
        exports: list[tuple[str, Path]] = [
            (variant_name, out_dir / file_name)
            for variant_name, (file_name, _) in _BANNER_EXPORTS.items()
        ]
        for var, out in exports:
            _, fg = _BANNER_EXPORTS[var]
            export_banner_png(get_banner(var), out, fg=fg)
            sys.stdout.write(f"wrote {out}\n")
    else:
        # Single-variant export — first_arg is treated as the output file path.
        file_name, fg = _BANNER_EXPORTS.get(variant, _BANNER_EXPORTS["unicode"])
        out = first_arg if first_arg.suffix else first_arg / file_name
        export_banner_png(get_banner(variant), out, fg=fg)
        sys.stdout.write(f"wrote {out}\n")


if __name__ == "__main__":  # pragma: no cover
    _main()
