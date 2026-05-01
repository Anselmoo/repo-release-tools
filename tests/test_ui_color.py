from __future__ import annotations

import pytest

from repo_release_tools.ui import color


def test_apply_returns_plain_text_when_not_supported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(color, "supports_color", lambda stream=None: False)

    rendered = color.apply("hello", color.Style(fg=31, bold=True))

    assert rendered == "hello"


def test_apply_wraps_ansi_when_supported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(color, "supports_color", lambda stream=None: True)

    rendered = color.apply("hello", color.Style(fg=31, bold=True))

    assert rendered.startswith("\x1b[")
    assert rendered.endswith("\x1b[0m")
    assert "hello" in rendered


def test_supports_color_disabled_on_non_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RRT_COLOR", raising=False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)

    assert color.supports_color() is False


def test_supports_color_accepts_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    monkeypatch.setattr(color, "detect_color_level", lambda: "standard")

    class FakeStream(io.StringIO):
        def isatty(self) -> bool:
            return True

    stream = FakeStream()
    assert color.supports_color(stream) is True


def test_detect_color_level_respects_rrt_color_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("RRT_COLOR", "truecolor")
    assert color.detect_color_level() == "truecolor"


def test_detect_color_level_returns_none_for_dumb_term(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "dumb")
    assert color.detect_color_level() == "none"


def test_detect_color_level_returns_none_when_no_color_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    assert color.detect_color_level() == "none"


def test_detect_color_level_returns_256_for_rtt_color_256(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("RRT_COLOR", "256")
    assert color.detect_color_level() == "256"


def test_detect_color_level_returns_256_for_term_256color(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("RRT_COLOR", raising=False)
    monkeypatch.delenv("COLORTERM", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    assert color.detect_color_level() == "256"


def test_detect_color_level_returns_none_for_rtt_color_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("RRT_COLOR", "false")
    assert color.detect_color_level() == "none"


def test_detect_color_level_defaults_to_standard_without_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("RRT_COLOR", raising=False)
    monkeypatch.delenv("COLORTERM", raising=False)
    monkeypatch.setenv("TERM", "xterm")
    monkeypatch.setattr(color.sys, "platform", "darwin")
    assert color.detect_color_level() == "standard"


def test_detect_color_level_returns_truecolor_for_colorterm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("RRT_COLOR", raising=False)
    monkeypatch.setenv("COLORTERM", "truecolor")
    assert color.detect_color_level() == "truecolor"


def test_detect_color_level_returns_none_on_legacy_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("RRT_COLOR", raising=False)
    monkeypatch.delenv("COLORTERM", raising=False)
    monkeypatch.setenv("TERM", "xterm")
    monkeypatch.setattr(color.sys, "platform", "win32")
    monkeypatch.delenv("WT_SESSION", raising=False)
    assert color.detect_color_level() == "none"


def test_apply_returns_plain_text_when_no_style_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(color, "supports_color", lambda stream=None: True)
    rendered = color.apply("hello", color.Style())
    assert rendered == "hello"


def test_color_wrappers_forward_stream_to_apply(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_apply(text: str, style: color.Style, *, stream: object = None) -> str:
        captured["text"] = text
        captured["style"] = style
        captured["stream"] = stream
        return f"APPLIED:{text}"

    monkeypatch.setattr(color, "apply", fake_apply)

    stream = __import__("io").StringIO()
    assert color.success("ok", stream=stream) == "APPLIED:ok"
    assert color.warning("warn", stream=stream) == "APPLIED:warn"
    assert color.error("fail", stream=stream) == "APPLIED:fail"
    assert color.info("info", stream=stream) == "APPLIED:info"
    assert color.subtle("quiet", stream=stream) == "APPLIED:quiet"
    assert captured["stream"] is stream


# ── Phase 2 I2+I3 tests ──────────────────────────────────────────────────────


def test_hex_to_rgb_parses_six_digit_hex() -> None:
    from repo_release_tools.ui.color import _hex_to_rgb

    assert _hex_to_rgb("#ff6400") == (255, 100, 0)


def test_hex_to_rgb_parses_three_digit_hex() -> None:
    from repo_release_tools.ui.color import _hex_to_rgb

    assert _hex_to_rgb("#f00") == (255, 0, 0)


def test_hex_to_rgb_raises_on_invalid() -> None:
    from repo_release_tools.ui.color import _hex_to_rgb

    with pytest.raises(ValueError):
        _hex_to_rgb("#gg0000")


def test_hex_to_rgb_rejects_invalid_length() -> None:
    from repo_release_tools.ui.color import _hex_to_rgb

    with pytest.raises(ValueError):
        _hex_to_rgb("#12345")


def test_rgb_to_ansi_returns_truecolor_sequence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(color, "detect_color_level", lambda: "truecolor")
    assert color._rgb_to_ansi(255, 0, 0) == "38;2;255;0;0"
    assert color._rgb_to_ansi(255, 0, 0, bg=True) == "48;2;255;0;0"


def test_rgb_to_ansi_returns_256_sequence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(color, "detect_color_level", lambda: "256")
    result = color._rgb_to_ansi(255, 100, 0)
    assert result.startswith("38;5;")


def test_rgb_to_ansi_returns_standard_sequence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(color, "detect_color_level", lambda: "standard")
    assert color._rgb_to_ansi(255, 0, 0) == "31"


def test_apply_style_named_color_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("RRT_COLOR", "1")
    result = color.apply_style("Done!", bold=True, color="success")
    # Should contain ANSI escape
    assert "\x1b[" in result
    assert "Done!" in result


def test_apply_style_with_hex_fg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("RRT_COLOR", "truecolor")
    result = color.apply_style("hex color", fg="#ff6400")
    assert "\x1b[" in result
    assert "hex color" in result


def test_apply_style_with_rgb_fg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("RRT_COLOR", "truecolor")
    result = color.apply_style("rgb color", fg=(255, 100, 0))
    assert "\x1b[" in result


def test_apply_style_no_color_returns_plain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    result = color.apply_style("plain", bold=True, color="error")
    assert result == "plain"


def test_apply_style_with_style_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("RRT_COLOR", "1")
    from repo_release_tools.ui.color import Style

    result = color.apply_style("styled", color=Style(fg=32, bold=True))
    assert "\x1b[" in result


def test_apply_style_supports_italic_and_background(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("RRT_COLOR", "truecolor")

    result = color.apply_style(
        "styled",
        bold=True,
        italic=True,
        underline=True,
        fg="#ff0000",
        bg=(0, 255, 0),
    )

    assert "\x1b[" in result
    assert "styled" in result


def test_apply_style_uses_style_background_when_no_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("RRT_COLOR", "1")
    from repo_release_tools.ui.color import Style

    result = color.apply_style("styled", color=Style(fg=32, bg=44))
    assert "\x1b[" in result


# ── Phase 3a M13: Theme system tests ────────────────────────────────────────


def test_set_theme_default_resets_to_default() -> None:
    from repo_release_tools.ui.color import THEMES, get_theme, set_theme

    set_theme("default")
    current = get_theme()
    assert current["success"] == THEMES["default"]["success"]


def test_set_theme_monochrome_changes_styles() -> None:
    from repo_release_tools.ui.color import THEMES, get_theme, set_theme

    try:
        set_theme("monochrome")
        current = get_theme()
        assert current["success"] == THEMES["monochrome"]["success"]
    finally:
        # always restore default
        set_theme("default")


def test_set_theme_pastel_applies() -> None:
    from repo_release_tools.ui.color import THEMES, get_theme, set_theme

    try:
        set_theme("pastel")
        current = get_theme()
        assert current["error"] == THEMES["pastel"]["error"]
    finally:
        set_theme("default")


def test_set_theme_custom_dict() -> None:
    from repo_release_tools.ui.color import Style, get_theme, set_theme

    custom = {"success": Style(fg=200, bold=True)}
    try:
        set_theme(custom)
        assert get_theme()["success"] == Style(fg=200, bold=True)
    finally:
        set_theme("default")


def test_set_theme_unknown_raises() -> None:
    from repo_release_tools.ui.color import set_theme

    with pytest.raises(ValueError, match="Unknown theme"):
        set_theme("nonexistent-theme")


def test_get_theme_returns_dict() -> None:
    from repo_release_tools.ui.color import get_theme

    result = get_theme()
    assert isinstance(result, dict)
    assert "success" in result
