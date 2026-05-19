"""Tests for the ASCII banner constants and PNG export."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from repo_release_tools.ui.glyphs import display_width


def _assert_banner_geometry(banner: str) -> None:
    lines = banner.splitlines()
    widths = [display_width(line) for line in lines]

    assert lines, "banner must contain lines"
    assert len(set(widths)) == 1, widths
    assert widths[0] > 0


def test_banner_unicode_geometry_is_consistent() -> None:
    from repo_release_tools.assets.banner import BANNER_UNICODE

    _assert_banner_geometry(BANNER_UNICODE)


def test_banner_ascii_geometry_is_consistent() -> None:
    from repo_release_tools.assets.banner import BANNER_ASCII

    _assert_banner_geometry(BANNER_ASCII)


def test_banner_unicode_is_non_empty_string() -> None:
    from repo_release_tools import __version__
    from repo_release_tools.assets.banner import BANNER_UNICODE

    assert isinstance(BANNER_UNICODE, str)
    assert len(BANNER_UNICODE) > 1000
    assert "SYSTEM" in BANNER_UNICODE
    assert "STATUS" in BANNER_UNICODE
    assert "VER " in BANNER_UNICODE
    assert __version__ in BANNER_UNICODE
    # Optimized UI fragments
    assert "PIPELINE ENGINE" in BANNER_UNICODE
    assert "COVERAGE " in BANNER_UNICODE
    assert "STATE: OPTIMAL" in BANNER_UNICODE
    # Credit branding
    assert "MIT License 2026" in BANNER_UNICODE
    assert "GITHUB.COM/ANSELMOO/REPO-RELEASE-TOOLS" in BANNER_UNICODE
    # Verify no player/token/co
    assert "PLAYER:" not in BANNER_UNICODE
    assert "INSERT TOKEN" not in BANNER_UNICODE
    assert "REPO-RELEASE-TOOLS CO." not in BANNER_UNICODE
    assert "ANSELM HAHN" not in BANNER_UNICODE


def test_banner_ascii_is_non_empty_string() -> None:
    from repo_release_tools import __version__
    from repo_release_tools.assets.banner import BANNER_ASCII

    assert isinstance(BANNER_ASCII, str)
    assert len(BANNER_ASCII) > 1000
    assert "SYSTEM" in BANNER_ASCII
    assert "STATUS" in BANNER_ASCII
    assert __version__ in BANNER_ASCII
    assert "MIT License 2026" in BANNER_ASCII


def test_retro_glyphs() -> None:
    from repo_release_tools.ui.glyphs import GLYPHS

    assert str(GLYPHS.retro.pipe_rim_l) == "▛"
    assert str(GLYPHS.retro.pipe_rim_r) == "▜"
    assert str(GLYPHS.retro.flag) == "⚑"
    assert str(GLYPHS.retro.star) in {"★", "(*)"}
    assert str(GLYPHS.retro.home) in {"⌂", "(H)"}


def test_banner_ascii_contains_only_ascii() -> None:
    from repo_release_tools.assets.banner import BANNER_ASCII

    assert BANNER_ASCII.isascii(), "BANNER_ASCII must contain only ASCII characters"


def test_get_banner_truncates_overlong_dynamic_rows() -> None:
    from repo_release_tools.assets import banner as banner_mod

    metrics = {
        "ver": "9.9.9" * 20,
        "tools": "9999",
        "loc": "123456k",
        "files": "9999",
        "tests": "9999",
        "py": "3.13",
        "os": "DARWIN",
        "branch": "feature/" + ("x" * 160),
    }

    with patch.object(banner_mod, "_collect_metrics", return_value=metrics):
        banner = banner_mod.get_banner("unicode", version=metrics["ver"])

    _assert_banner_geometry(banner)
    assert metrics["branch"] not in banner
    assert metrics["ver"] not in banner


def test_normalize_banner_uses_display_width() -> None:
    from repo_release_tools.assets.banner import _normalize_banner

    normalized = _normalize_banner("A\n漢")
    widths = [display_width(line) for line in normalized.splitlines()]

    assert len(set(widths)) == 1


def test_export_banner_png_writes_file(tmp_path: Path) -> None:
    from repo_release_tools.assets.banner import BANNER_ASCII, export_banner_png

    out = tmp_path / "banner.png"
    export_banner_png(BANNER_ASCII, out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_export_banner_png_creates_parent_dirs(tmp_path: Path) -> None:
    from repo_release_tools.assets.banner import BANNER_ASCII, export_banner_png

    out = tmp_path / "nested" / "deep" / "banner.png"
    export_banner_png(BANNER_ASCII, out)
    assert out.exists()


def test_export_banner_png_raises_without_pillow(tmp_path: Path) -> None:
    from repo_release_tools.assets import banner as banner_mod

    out = tmp_path / "banner.png"
    with patch.dict(
        sys.modules, {"PIL": None, "PIL.Image": None, "PIL.ImageDraw": None, "PIL.ImageFont": None}
    ):
        with pytest.raises(RuntimeError, match="Pillow"):
            banner_mod.export_banner_png("test", out)


def test_export_banner_png_fallback_font(tmp_path: Path) -> None:
    from repo_release_tools.assets import banner as banner_mod

    out = tmp_path / "banner_fallback.png"
    with patch.object(banner_mod, "_MONOSPACE_CANDIDATES", new=[]):
        banner_mod.export_banner_png(banner_mod.BANNER_UNICODE, out)
    assert out.exists()


def test_export_banner_png_retries_candidates_before_succeeding(tmp_path: Path) -> None:
    from repo_release_tools.assets import banner as banner_mod

    out = tmp_path / "banner_retry.png"
    fake_font = object()
    with (
        patch.object(banner_mod, "_MONOSPACE_CANDIDATES", new=["missing-one", "present-two"]),
        patch("PIL.ImageFont.truetype", side_effect=[OSError("missing"), fake_font]) as truetype,
        patch("PIL.ImageDraw.ImageDraw.textbbox", return_value=(0, 0, 8, 12)) as textbbox,
        patch("PIL.ImageDraw.ImageDraw.text") as draw_text,
    ):
        banner_mod.export_banner_png("retry", out)

    assert out.exists()
    assert truetype.call_count == 2
    assert truetype.call_args_list[0].args[0] == "missing-one"
    assert truetype.call_args_list[1].args[0] == "present-two"
    assert textbbox.called
    assert draw_text.called


def test_main_writes_unicode_banner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = tmp_path / "out.png"
    monkeypatch.setattr(sys, "argv", ["banner", str(out), "unicode"])
    from repo_release_tools.assets.banner import _main

    _main()
    assert out.exists()


def test_main_writes_ascii_banner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = tmp_path / "out.png"
    monkeypatch.setattr(sys, "argv", ["banner", str(out), "ascii"])
    from repo_release_tools.assets.banner import _main

    _main()
    assert out.exists()


def test_main_writes_light_banner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = tmp_path / "light.png"
    monkeypatch.setattr(sys, "argv", ["banner", str(out), "light"])
    from repo_release_tools.assets.banner import _main

    _main()
    assert out.exists()


def test_main_writes_social_card(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = tmp_path / "social-card.png"
    monkeypatch.setattr(sys, "argv", ["banner", str(out), "social"])
    from PIL import Image

    from repo_release_tools.assets.banner import _main

    _main()

    assert out.exists()
    with Image.open(out) as img:
        assert img.size == (1280, 640)


def test_main_default_args(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["banner"])
    monkeypatch.chdir(tmp_path)
    from repo_release_tools.assets.banner import _main

    _main()
    assert (tmp_path / "docs" / "assets" / "banner-dark.png").exists()
    assert (tmp_path / "docs" / "assets" / "banner-light.png").exists()
    assert (tmp_path / "docs" / "assets" / "banner-windows.png").exists()
    assert (tmp_path / "docs" / "assets" / "social-card.png").exists()


def test_legacy_banner_constants_are_lazy_and_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    from repo_release_tools import __version__
    from repo_release_tools.assets import banner as banner_mod

    calls = {"count": 0}

    def fake_get_banner(variant: str = "unicode", version: str = __version__) -> str:
        calls["count"] += 1
        return f"{variant}:{version}"

    banner_mod.get_cached_banner.cache_clear()
    monkeypatch.setattr(banner_mod, "get_banner", fake_get_banner)

    first = getattr(banner_mod, "BANNER_ASCII")
    second = getattr(banner_mod, "BANNER_ASCII")

    assert first == second
    assert calls["count"] == 1


def test_render_banner_image_skips_zero_width_cells() -> None:
    from repo_release_tools.assets import banner as banner_mod

    # Combining marks have display width 0 and must not create 0-width cell images.
    image = banner_mod._render_banner_image("\u0301", font_size=14, padding=2)
    assert image.width > 0
    assert image.height > 0
