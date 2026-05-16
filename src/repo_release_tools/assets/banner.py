"""ASCII banner and PNG export for repo-release-tools."""

from __future__ import annotations

from pathlib import Path

# fmt: off
BANNER_UNICODE = r"""
╔════════════════════════════════════════════════════════════════════════════════╗
║                                                                                ║
║    ____  _____ ____   ___                                                      ║
║   |  _ \| ____|  _ \ / _ \                                                     ║
║   | |_) |  _| | |_) | | | |                                                    ║
║   |  _ <| |___|  __/| |_| |                                                    ║
║   |_| \_\_____|_|    \___/                                                     ║
║                                                                                ║
║    ____  _____ _     _____      _    ____  _____                               ║
║   |  _ \| ____| |   | ____|    / \  / ___|| ____|                              ║
║   | |_) |  _| | |   |  _|     / _ \ \___ \|  _|                                ║
║   |  _ <| |___| |___| |___   / ___ \ ___) | |___                               ║
║   |_| \_\_____|_____|_____| /_/   \_\____/|_____|                              ║
║                                                                                ║
║    _____ ___   ___  _     ____                                                 ║
║   |_   _/ _ \ / _ \| |   / ___|                                                ║
║     | || | | | | | | |   \___ \                                                ║
║     | || |_| | |_| | |___ ___) |                                               ║
║     |_| \___/ \___/|_____|____/                                                ║
║                                                                                ║
╠════════════════════════════════════════════════════════════════════════════════╣
║                                                                                ║
║  PIPELINE                                                                      ║
║                                                                                ║
║  ╔══════════╗       ╔══════════╗       ╔══════════╗                            ║
║  ║  branch  ╠═══════║   bump   ╠═══════║   tag    ╠══════════════════════╗     ║
║  ╚══════════╝       ╚══════════╝       ╚══════════╝                      ║     ║
║       ║                                                                  ║     ║
║       ║                                                                  ║     ║
║  ╔════╩═════╗       ╔══════════╗       ╔══════════╗               ╔══════╩═══╗ ║
║  ║changelog ╠═══════║   docs   ╠═══════║  publish ╠═══════════════║ RELEASE  ║ ║
║  ╚══════════╝       ╚══════════╝       ╚══════════╝               ╚══════════╝ ║
║                                                                                ║
╠════════════════════════════════════════════════════════════════════════════════╣
║  keep release policy boring in the best possible way                           ║
╚════════════════════════════════════════════════════════════════════════════════╝
""".strip()

BANNER_ASCII = r"""
+================================================================================+
|                                                                                |
|    ____  _____ ____   ___                                                      |
|   |  _ \| ____|  _ \ / _ \                                                     |
|   | |_) |  _| | |_) | | | |                                                    |
|   |  _ <| |___|  __/| |_| |                                                    |
|   |_| \_\_____|_|    \___/                                                     |
|                                                                                |
|    ____  _____ _     _____      _    ____  _____                               |
|   |  _ \| ____| |   | ____|    / \  / ___|| ____|                              |
|   | |_) |  _| | |   |  _|     / _ \ \___ \|  _|                                |
|   |  _ <| |___| |___| |___   / ___ \ ___) | |___                               |
|   |_| \_\_____|_____|_____| /_/   \_\____/|_____|                              |
|                                                                                |
|    _____ ___   ___  _     ____                                                 |
|   |_   _/ _ \ / _ \| |   / ___|                                                |
|     | || | | | | | | |   \___ \                                                |
|     | || |_| | |_| | |___ ___) |                                               |
|     |_| \___/ \___/|_____|____/                                                |
|                                                                                |
+================================================================================+
|                                                                                |
|  PIPELINE                                                                      |
|                                                                                |
|  +----------+       +----------+       +----------+                            |
|  |  branch  |=======|   bump   |=======|   tag    |====================+       |
|  +----------+       +----------+       +----------+                    |       |
|       |                                                                |       |
|       |                                                                |       |
|  +----+-----+       +----------+       +----------+          +---------+-+     |
|  |changelog |=======|   docs   |=======|  publish |==========|  RELEASE  |     |
|  +----------+       +----------+       +----------+          +-----------+     |
|                                                                                |
+================================================================================+
|  keep release policy boring in the best possible way                           |
+================================================================================+
""".strip()
# fmt: on


_MONOSPACE_CANDIDATES = [
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


def export_banner_png(
    banner: str,
    output_path: str | Path,
    *,
    font_size: int = 14,
    bg: tuple[int, int, int] = (18, 18, 18),
    fg: tuple[int, int, int] = (204, 204, 204),
    padding: int = 24,
) -> None:
    """Render an ASCII banner string to a PNG image using Pillow."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise RuntimeError(
            "Pillow is required for PNG export. Install it with: pip install pillow"
        ) from exc

    lines = banner.splitlines()

    font: ImageFont.FreeTypeFont | ImageFont.ImageFont | None = None
    for candidate in _MONOSPACE_CANDIDATES:
        try:
            font = ImageFont.truetype(candidate, font_size)
            break
        except (OSError, AttributeError):
            continue
    if font is None:
        font = ImageFont.load_default()

    # Measure character cell using a reference character
    dummy = Image.new("RGB", (1, 1))
    draw_dummy = ImageDraw.Draw(dummy)
    bbox = draw_dummy.textbbox((0, 0), "M", font=font)
    char_w = int(bbox[2] - bbox[0])
    char_h = int(bbox[3] - bbox[1])
    line_height = char_h + 4

    max_cols = max((len(line) for line in lines), default=1)
    img_w = max_cols * char_w + padding * 2
    img_h = len(lines) * line_height + padding * 2

    img = Image.new("RGB", (img_w, img_h), bg)
    draw = ImageDraw.Draw(img)

    for row, line in enumerate(lines):
        y = padding + row * line_height
        draw.text((padding, y), line, font=font, fill=fg)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out))


def _main() -> None:
    import sys

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs/assets/banner.png")
    variant = sys.argv[2] if len(sys.argv) > 2 else "unicode"
    banner = BANNER_ASCII if variant == "ascii" else BANNER_UNICODE
    export_banner_png(banner, out)
    sys.stdout.write(f"wrote {out}\n")


if __name__ == "__main__":  # pragma: no cover
    _main()
