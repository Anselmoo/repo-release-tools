"""ASCII banner and PNG export for repo-release-tools."""

from __future__ import annotations

import os
import sys
from contextlib import suppress
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from repo_release_tools import __version__
from repo_release_tools.ui import align, display_width, pad_right

if TYPE_CHECKING:
    from typing import LiteralString

# High-Readability Arcade Splash Screen Style (Emoji-free).
# Features the full name Repo-Release-Tools split into three readable lines.


_BANNER_ROW_WIDTH = 74

_BANNER_EXPORTS: dict[str, tuple[str, tuple[int, int, int]]] = {
    # GitHub dark theme: a bright mint foreground pops against the dark page.
    "unicode": ("banner-dark.png", (195, 255, 196)),
    # GitHub light theme: a deeper green keeps the banner readable on white.
    "light": ("banner-light.png", (24, 102, 53)),
    # ASCII fallback stays available as the Windows-friendly export.
    "ascii": ("banner-windows.png", (204, 204, 204)),
}

_SOCIAL_CARD_EXPORT = ("social-card.png", (22, 17, 12, 255), (255, 191, 102))
_SOCIAL_CARD_SIZE = (1280, 640)
_SOCIAL_CARD_SUPERSAMPLE = 2

_CRT_THEMES: dict[str, dict[str, tuple[int, int, int, int] | tuple[int, int, int]]] = {
    "dark": {
        "card_bg": (22, 17, 12, 255),
        "bezel_outer": (46, 39, 30, 255),
        "bezel_inner": (72, 60, 44, 255),
        "screen_bg": (17, 12, 8, 255),
        "screen_outline": (158, 132, 96, 255),
        "screen_glow": (255, 214, 140, 110),
        "fg": (255, 191, 102),
    },
    "light": {
        "card_bg": (236, 224, 206, 255),
        "bezel_outer": (208, 192, 166, 255),
        "bezel_inner": (228, 211, 184, 255),
        "screen_bg": (255, 249, 237, 255),
        "screen_outline": (176, 146, 96, 255),
        "screen_glow": (168, 124, 54, 90),
        "fg": (122, 77, 28),
    },
}

_CRT_BANNER_VARIANTS = {"unicode": "dark", "light": "light"}


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


@lru_cache(maxsize=8)
def get_cached_banner(variant: str = "unicode", version: str = __version__) -> str:
    """Return a cached rendered banner to avoid repeated metric scans."""
    return get_banner(variant, version)


def __getattr__(name: str) -> str:
    """Provide lazy legacy banner constants for compatibility.

    This keeps ``BANNER_UNICODE``/``BANNER_ASCII`` import-compatible without
    performing expensive metric collection during module import.
    """
    if name == "BANNER_UNICODE":
        return get_cached_banner("unicode")
    if name == "BANNER_ASCII":
        return get_cached_banner("ascii")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
    img = _render_banner_image(banner_str, font_size=font_size, bg=bg, fg=fg, padding=padding)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out))


def _render_banner_image(
    banner_str: str,
    *,
    font_size: int = 14,
    bg: tuple[int, int, int, int] = (0, 0, 0, 0),
    fg: tuple[int, int, int] = (204, 204, 204),
    padding: int = 24,
) -> Any:
    """Render a banner string to an in-memory PNG image."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise RuntimeError(
            "Pillow is required for PNG export. Install it with: pip install pillow"
        ) from exc

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

            cell_count = display_width(safe_char)
            if cell_count <= 0:
                continue
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

    return img


def _compose_crt_monitor(
    content_img: Any,
    *,
    theme: str,
    fixed_size: tuple[int, int] | None,
    scale: int,
) -> Any:
    """Compose an image into an 80s tube monitor frame, anchored toward the top."""
    from PIL import Image, ImageDraw

    theme_cfg = _CRT_THEMES[theme]
    card_bg = theme_cfg["card_bg"]
    bezel_outer = theme_cfg["bezel_outer"]
    bezel_inner = theme_cfg["bezel_inner"]
    screen_bg = theme_cfg["screen_bg"]
    screen_outline = theme_cfg["screen_outline"]
    screen_glow = theme_cfg["screen_glow"]
    assert isinstance(card_bg, tuple)
    assert isinstance(bezel_outer, tuple)
    assert isinstance(bezel_inner, tuple)
    assert isinstance(screen_bg, tuple)
    assert isinstance(screen_outline, tuple)
    assert isinstance(screen_glow, tuple)

    if fixed_size is None:
        work_w = content_img.width + (144 * scale)
        work_h = content_img.height + (168 * scale)
    else:
        work_w, work_h = fixed_size[0] * scale, fixed_size[1] * scale

    card = Image.new("RGBA", (work_w, work_h), card_bg)
    draw = ImageDraw.Draw(card)

    outer_margin = 28 * scale
    inner_margin = 60 * scale
    footer_height = 46 * scale
    corner_r = 14 * scale

    draw.rounded_rectangle(
        (outer_margin, outer_margin, work_w - outer_margin, work_h - outer_margin),
        radius=corner_r,
        fill=bezel_outer,
        outline=(102, 85, 64, 255),
        width=4 * scale,
    )
    draw.rounded_rectangle(
        (inner_margin, inner_margin, work_w - inner_margin, work_h - inner_margin),
        radius=10 * scale,
        fill=bezel_inner,
        outline=(132, 108, 78, 255),
        width=3 * scale,
    )

    screen_left = inner_margin + 18 * scale
    screen_top = inner_margin + 18 * scale
    screen_right = work_w - inner_margin - 18 * scale
    screen_bottom = work_h - inner_margin - footer_height

    draw.rectangle(
        (screen_left, screen_top, screen_right, screen_bottom),
        fill=screen_bg,
        outline=screen_outline,
        width=2 * scale,
    )

    screen_w = screen_right - screen_left
    screen_h = screen_bottom - screen_top
    crop_w = min(content_img.width, screen_w - 20 * scale)
    crop_h = min(content_img.height, screen_h - 20 * scale)
    crop_left = max(0, (content_img.width - crop_w) // 2)
    crop = content_img.crop((crop_left, 0, crop_left + crop_w, crop_h))

    # Keep the title block at the top of the display area.
    x = screen_left + max(0, (screen_w - crop.width) // 2)
    y = screen_top + 10 * scale
    card.paste(crop, (x, y), crop)

    draw.rectangle(
        (
            screen_left + 2 * scale,
            screen_top + 2 * scale,
            screen_right - 2 * scale,
            screen_bottom - 2 * scale,
        ),
        outline=screen_glow,
        width=2 * scale,
    )
    for yline in range(screen_top + 2 * scale, screen_bottom, 4 * scale):
        draw.line(
            (screen_left + 2 * scale, yline, screen_right - 2 * scale, yline),
            fill=(0, 0, 0, 28),
            width=1,
        )

    # Footer control: a single power switch instead of RGB status LEDs.
    power_box_w = 68 * scale
    power_box_h = 24 * scale
    power_x2 = work_w - inner_margin - 18 * scale
    power_x1 = power_x2 - power_box_w
    power_y1 = work_h - inner_margin - footer_height + (footer_height - power_box_h) // 2
    power_y2 = power_y1 + power_box_h

    draw.rounded_rectangle(
        (power_x1, power_y1, power_x2, power_y2),
        radius=5 * scale,
        fill=bezel_outer,
        outline=screen_outline,
        width=2 * scale,
    )

    # Classic power glyph: ring with centered top gap + centered vertical stroke.
    cx = (power_x1 + power_x2) // 2
    cy = (power_y1 + power_y2) // 2
    r = 6 * scale
    ring_w = 2 * scale
    draw.ellipse(
        (cx - r, cy - r, cx + r, cy + r),
        outline=screen_glow,
        width=ring_w,
    )
    gap = 2 * scale
    draw.rectangle(
        (cx - gap, cy - r - ring_w, cx + gap, cy - r + 2 * scale),
        fill=bezel_outer,
    )
    draw.line(
        (cx, cy - r - 1 * scale, cx, cy - 1 * scale),
        fill=screen_glow,
        width=2 * scale,
    )

    if scale > 1:
        resample_filter = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
        return card.resize((work_w // scale, work_h // scale), resample=resample_filter)
    return card


def export_crt_banner_png(
    banner_str: str,
    output_path: str | Path,
    *,
    theme: str,
    font_size: int = 14,
    padding: int = 24,
    supersample: int = 2,
) -> None:
    """Render a theme-specific CRT monitor styled banner image."""
    theme_cfg = _CRT_THEMES[theme]
    fg_theme_any = theme_cfg["fg"]
    assert isinstance(fg_theme_any, tuple)
    fg_theme = (int(fg_theme_any[0]), int(fg_theme_any[1]), int(fg_theme_any[2]))

    img = _render_banner_image(
        banner_str,
        font_size=font_size * supersample,
        bg=(0, 0, 0, 0),
        fg=fg_theme,
        padding=padding * supersample,
    )
    card = _compose_crt_monitor(img, theme=theme, fixed_size=None, scale=supersample)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    card.save(str(out))


def export_social_card_png(
    banner_str: str,
    output_path: str | Path,
    *,
    font_size: int = 14,
    bg: tuple[int, int, int, int] = _SOCIAL_CARD_EXPORT[1],
    fg: tuple[int, int, int] = _SOCIAL_CARD_EXPORT[2],
    padding: int = 24,
    card_size: tuple[int, int] = _SOCIAL_CARD_SIZE,
) -> None:
    """Render a banner string into a 1280×640 social card.

    The card keeps the top portion of the banner and deletes the lower part,
    leaving a full-color background for GitHub social previews.
    """
    _ = bg
    _ = fg

    theme_cfg = _CRT_THEMES["dark"]
    fg_theme_any = theme_cfg["fg"]
    assert isinstance(fg_theme_any, tuple)
    fg_theme = (int(fg_theme_any[0]), int(fg_theme_any[1]), int(fg_theme_any[2]))

    img = _render_banner_image(
        banner_str,
        font_size=font_size * _SOCIAL_CARD_SUPERSAMPLE,
        bg=(0, 0, 0, 0),
        fg=fg_theme,
        padding=padding * _SOCIAL_CARD_SUPERSAMPLE,
    )
    card = _compose_crt_monitor(
        img,
        theme="dark",
        fixed_size=card_size,
        scale=_SOCIAL_CARD_SUPERSAMPLE,
    )

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    card.save(str(out))


def _export_all_banner_assets(out_dir: Path) -> None:
    """Export all banner and social-card assets into ``out_dir``."""
    for variant_name, (file_name, fg) in _BANNER_EXPORTS.items():
        out = out_dir / file_name
        theme = _CRT_BANNER_VARIANTS.get(variant_name)
        if theme is None:
            export_banner_png(get_banner(variant_name), out, fg=fg)
        else:
            export_crt_banner_png(get_banner(variant_name), out, theme=theme)
        sys.stdout.write(f"wrote {out}\n")

    social_out = out_dir / _SOCIAL_CARD_EXPORT[0]
    export_social_card_png(get_banner("unicode"), social_out)
    sys.stdout.write(f"wrote {social_out}\n")


def _main() -> None:
    """Export banner PNG(s).

    Usage:
        banner.py [out_dir_or_file] [variant]

    When *variant* is ``"all"`` (the default when no variant is supplied),
    the GitHub theme pair and the ASCII-fallback (Windows) variant are
    exported side-by-side:

        <out_dir>/banner-dark.png     — Unicode variant (Linux / macOS)
        <out_dir>/banner-light.png    — light-theme variant (GitHub light mode)
        <out_dir>/banner-windows.png  — ASCII-fallback variant (Windows)

    Passing an explicit variant (``"unicode"``, ``"light"`` or ``"ascii"``)
    exports only that variant to the path given as the first argument.
    """
    first_arg = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs/assets")
    variant = sys.argv[2] if len(sys.argv) > 2 else "all"

    if variant == "all":
        out_dir = first_arg if first_arg.suffix == "" else first_arg.parent
        _export_all_banner_assets(out_dir)
    elif variant == "social":
        file_name = _SOCIAL_CARD_EXPORT[0]
        out = first_arg if first_arg.suffix else first_arg / file_name
        export_social_card_png(get_banner("unicode"), out)
        sys.stdout.write(f"wrote {out}\n")
    else:
        # Single-variant export — first_arg is treated as the output file path.
        file_name, fg = _BANNER_EXPORTS.get(variant, _BANNER_EXPORTS["unicode"])
        out = first_arg if first_arg.suffix else first_arg / file_name
        theme = _CRT_BANNER_VARIANTS.get(variant)
        if theme is None:
            export_banner_png(get_banner(variant), out, fg=fg)
        else:
            export_crt_banner_png(get_banner(variant), out, theme=theme)
        sys.stdout.write(f"wrote {out}\n")


if __name__ == "__main__":  # pragma: no cover
    _main()
