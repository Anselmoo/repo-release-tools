import pytest

from repo_release_tools.assets import banner
from repo_release_tools.ui.glyphs import display_width


def test_fit_banner_row_produces_fixed_width() -> None:
    out = banner._fit_banner_row("hello world")
    assert display_width(out) == banner._BANNER_ROW_WIDTH


def test_normalize_banner_preserves_frame_borders_and_aligns() -> None:
    a = "║  long content here  ║"
    b = "║x║"
    out = banner._normalize_banner("\n".join([a, b]))
    lines = out.splitlines()
    # both lines should now have equal display width
    assert display_width(lines[0]) == display_width(lines[1])
    # ensure the trailing border remains the last visible char
    assert lines[1].rstrip().endswith("║")


def test_normalize_banner_empty_returns_input() -> None:
    # empty banner should be returned unchanged
    assert banner._normalize_banner("") == ""


def test_collect_metrics_handles_unreadable_files(monkeypatch: pytest.MonkeyPatch) -> None:
    # Simulate an OSError when opening files to exercise the except branch
    import builtins

    import repo_release_tools.assets.banner as bmod

    def fake_open(*args: object, **kwargs: object) -> None:
        raise OSError("unreadable file")

    monkeypatch.setattr(builtins, "open", fake_open)

    # Should not raise and should return a metrics dict
    metrics = bmod._collect_metrics()
    assert isinstance(metrics, dict)


def test_export_banner_png_env_font_success(
    tmp_path: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RRT_BANNER_FONT set and truetype succeeds — env font is used, candidates are skipped."""
    from pathlib import Path
    from unittest.mock import patch

    import repo_release_tools.assets.banner as bmod

    out = Path(str(tmp_path)) / "env_font.png"  # type: ignore[arg-type]
    monkeypatch.setenv("RRT_BANNER_FONT", "/custom/MonoFont.ttf")
    fake_font = object()

    with (
        patch.object(bmod, "_MONOSPACE_CANDIDATES", new=["should-not-be-tried"]),
        patch("PIL.ImageFont.truetype", return_value=fake_font) as truetype_mock,
        patch("PIL.ImageDraw.ImageDraw.textbbox", return_value=(0, 0, 8, 12)),
        patch("PIL.ImageDraw.ImageDraw.text"),
    ):
        bmod.export_banner_png("hi", out)

    # truetype called exactly once — for the env font, not for any candidate
    assert truetype_mock.call_count == 1
    assert truetype_mock.call_args.args[0] == "/custom/MonoFont.ttf"
    assert out.exists()


def test_export_banner_png_env_font_oserror_falls_back(
    tmp_path: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RRT_BANNER_FONT set but truetype raises OSError — falls back to the candidate list."""
    from pathlib import Path
    from unittest.mock import patch

    import repo_release_tools.assets.banner as bmod

    out = Path(str(tmp_path)) / "env_font_fallback.png"  # type: ignore[arg-type]
    monkeypatch.setenv("RRT_BANNER_FONT", "/bad/font.ttf")
    fake_font = object()

    with (
        patch.object(bmod, "_MONOSPACE_CANDIDATES", new=["good-candidate"]),
        patch(
            "PIL.ImageFont.truetype",
            side_effect=[OSError("no such font"), fake_font],
        ) as truetype_mock,
        patch("PIL.ImageDraw.ImageDraw.textbbox", return_value=(0, 0, 8, 12)),
        patch("PIL.ImageDraw.ImageDraw.text"),
    ):
        bmod.export_banner_png("hi", out)

    # First call → env font (OSError), second call → candidate (succeeds)
    assert truetype_mock.call_count == 2
    assert truetype_mock.call_args_list[0].args[0] == "/bad/font.ttf"
    assert truetype_mock.call_args_list[1].args[0] == "good-candidate"
    assert out.exists()


def test_compose_crt_monitor_scale_gt_one_resizes_output() -> None:
    from PIL import Image

    import repo_release_tools.assets.banner as bmod

    content = Image.new("RGBA", (900, 520), (0, 0, 0, 0))

    out_scale_1 = bmod._compose_crt_monitor(content, theme="dark", fixed_size=None, scale=1)
    out_scale_2 = bmod._compose_crt_monitor(content, theme="dark", fixed_size=None, scale=2)

    # scale=2 path downsamples before returning; output should be smaller.
    assert out_scale_2.size[0] < out_scale_1.size[0]
    assert out_scale_2.size[1] < out_scale_1.size[1]


def test_compose_crt_monitor_uses_integer_rounded_rectangle_coords(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from PIL import Image, ImageDraw

    import repo_release_tools.assets.banner as bmod

    content = Image.new("RGBA", (900, 520), (0, 0, 0, 0))
    recorded_boxes: list[tuple[float, ...]] = []

    def _capture_rounded_rectangle(
        _self: ImageDraw.ImageDraw,
        xy: tuple[float, float, float, float],
        *_args: object,
        **_kwargs: object,
    ) -> None:
        recorded_boxes.append(tuple(xy))

    monkeypatch.setattr(ImageDraw.ImageDraw, "rounded_rectangle", _capture_rounded_rectangle)

    bmod._compose_crt_monitor(content, theme="dark", fixed_size=(1280, 640), scale=1)

    assert recorded_boxes
    assert all(all(isinstance(value, int) for value in box) for box in recorded_boxes)
