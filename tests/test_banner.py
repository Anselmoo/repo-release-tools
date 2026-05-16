"""Tests for the ASCII banner constants and PNG export."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest


def test_banner_unicode_is_non_empty_string() -> None:
    from repo_release_tools.assets.banner import BANNER_UNICODE

    assert isinstance(BANNER_UNICODE, str)
    assert len(BANNER_UNICODE) > 100
    assert "RELEASE" in BANNER_UNICODE
    assert "PIPELINE" in BANNER_UNICODE
    assert "release policy" in BANNER_UNICODE


def test_banner_ascii_is_non_empty_string() -> None:
    from repo_release_tools.assets.banner import BANNER_ASCII

    assert isinstance(BANNER_ASCII, str)
    assert len(BANNER_ASCII) > 100
    assert "RELEASE" in BANNER_ASCII
    assert "PIPELINE" in BANNER_ASCII
    assert "release policy" in BANNER_ASCII


def test_banner_ascii_contains_only_ascii() -> None:
    from repo_release_tools.assets.banner import BANNER_ASCII

    assert BANNER_ASCII.isascii(), "BANNER_ASCII must contain only ASCII characters"


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


def test_main_default_args(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["banner"])
    monkeypatch.chdir(tmp_path)
    from repo_release_tools.assets.banner import _main

    _main()
    assert (tmp_path / "docs" / "assets" / "banner.png").exists()
