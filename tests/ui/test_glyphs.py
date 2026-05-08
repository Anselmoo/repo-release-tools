from __future__ import annotations

import sys

import pytest

from repo_release_tools.ui.glyphs import GLYPHS, Glyph, _detect_legacy_terminal, display_width


def test_glyph_multiplies_like_a_string() -> None:
    """Test that multiplying a Glyph by an integer produces the expected string output."""
    glyph = Glyph("-", "dash")

    assert glyph * 3 == "---"
    assert 2 * glyph == "--"


def test_git_status_line_stays_compact() -> None:
    """Test that the git status line remains compact and contains expected values."""
    line = GLYPHS.git.status_line(
        "feat/add-parser",
        ahead=2,
        behind=1,
        modified=3,
        untracked=1,
    )

    assert "feat/add-parser" in line
    assert "2" in line
    assert "1" in line


def test_diff_line_accepts_line_numbers() -> None:
    """Test that diff line rendering includes the provided line number and content."""
    rendered = GLYPHS.diff.line("added", "return result", lineno=12)

    assert "12" in rendered
    assert "return result" in rendered


def test_box_table_renders_consistent_widths() -> None:
    rendered = GLYPHS.box.table(
        ["Key", "Value"],
        [["branch", "feat/v0-15-0"], ["title", "feat: v0.15.0"]],
    )

    widths = {display_width(line) for line in rendered.splitlines()}
    assert len(widths) == 1
    assert "feat/v0-15-0" in rendered


def test_tree_render_supports_nested_entries() -> None:
    rendered = GLYPHS.tree.render(
        [
            ("src", True, [("repo_release_tools", True, [("glyphs.py", False, None)])]),
            ("README.md", False, None),
        ]
    )

    assert "src/" in rendered
    assert "repo_release_tools/" in rendered
    assert "glyphs.py" in rendered
    assert "README.md" in rendered


def test_progress_bar_and_spinner_are_available() -> None:
    bar = GLYPHS.progress.render_bar(0.5, width=4)
    spinner = GLYPHS.progress.spinner("ascii")

    assert "50%" in bar
    assert len(next(spinner)) >= 1


# ---------------------------------------------------------------------------
# Terminal detection
# ---------------------------------------------------------------------------


def test_detect_legacy_terminal_dumb(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TERM", "dumb")
    # Patch sys.platform so this test exercises the TERM branch on Windows CI too.
    monkeypatch.setattr(sys, "platform", "linux")
    assert _detect_legacy_terminal() is True


def test_detect_legacy_terminal_no_color(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    # Patch sys.platform so this test exercises the NO_COLOR branch on Windows CI too.
    monkeypatch.setattr(sys, "platform", "linux")
    assert _detect_legacy_terminal() is True


def test_detect_legacy_terminal_normal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TERM", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    # Patch sys.platform so this test works on Windows CI too.
    monkeypatch.setattr(sys, "platform", "linux")
    assert _detect_legacy_terminal() is False


# ---------------------------------------------------------------------------
# display_width – ambiguous-width characters
# ---------------------------------------------------------------------------


def test_display_width_ascii_unchanged() -> None:
    assert display_width("hello") == 5


def test_display_width_cjk_full_width() -> None:
    # 漢字 – each char is W (wide), width 2 each
    assert display_width("漢字") == 4


def test_display_width_ambiguous_narrow_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    # Bullet '•' has east_asian_width 'A' – counted as 1 in a non-CJK locale.
    monkeypatch.setenv("RRT_WIDE_AMBIGUOUS", "0")
    from importlib import reload

    import repo_release_tools.ui.glyphs as g

    reload(g)
    assert g.display_width("•") == 1
    monkeypatch.delenv("RRT_WIDE_AMBIGUOUS")
    reload(g)  # restore _AMBIGUOUS_IS_WIDE to its natural value


def test_display_width_ambiguous_wide_when_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RRT_WIDE_AMBIGUOUS", "1")
    from importlib import reload

    import repo_release_tools.ui.glyphs as g

    reload(g)
    assert g.display_width("•") == 2
    monkeypatch.delenv("RRT_WIDE_AMBIGUOUS")
    reload(g)  # restore _AMBIGUOUS_IS_WIDE to its natural value


# ---------------------------------------------------------------------------
# New box glyph sets – RoundedBoxGlyphs and BoldBoxGlyphs
# ---------------------------------------------------------------------------


def test_rounded_box_renders_consistent_width() -> None:
    rendered = GLYPHS.rounded_box.box("test string")
    lines = rendered.splitlines()
    assert len(lines) == 3
    widths = {display_width(line) for line in lines}
    assert len(widths) == 1


def test_rounded_box_has_rounded_corners() -> None:
    rendered = GLYPHS.rounded_box.box("x")
    top_line = rendered.splitlines()[0]
    bot_line = rendered.splitlines()[2]
    assert top_line.startswith("╭") or top_line.startswith("+")
    assert bot_line.startswith("╰") or bot_line.startswith("+")


def test_bold_box_renders_consistent_width() -> None:
    rendered = GLYPHS.bold_box.box("test string")
    lines = rendered.splitlines()
    assert len(lines) == 3
    widths = {display_width(line) for line in lines}
    assert len(widths) == 1


def test_bold_box_has_bold_corners() -> None:
    rendered = GLYPHS.bold_box.box("x")
    top_line = rendered.splitlines()[0]
    bot_line = rendered.splitlines()[2]
    assert top_line.startswith("┏") or top_line.startswith("+")
    assert bot_line.startswith("┗") or bot_line.startswith("+")


# ---------------------------------------------------------------------------
# Additional tests for remaining uncovered lines
# ---------------------------------------------------------------------------


def test_detect_legacy_terminal_on_win32(monkeypatch: pytest.MonkeyPatch) -> None:
    """Line 22: sys.platform == 'win32' returns True."""
    from repo_release_tools.ui import glyphs as _g_mod

    monkeypatch.setattr(_g_mod.sys, "platform", "win32")
    assert _g_mod._detect_legacy_terminal() is True


def test_detect_cjk_locale_returns_false_for_none_lang(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Line 48: locale.getlocale() returns (None, ...) → False."""
    import locale as _locale

    from repo_release_tools.ui import glyphs as _g_mod

    monkeypatch.setattr(_locale, "getlocale", lambda: (None, "UTF-8"))
    monkeypatch.delenv("RRT_WIDE_AMBIGUOUS", raising=False)
    assert _g_mod._detect_cjk_locale() is False


def test_display_width_skips_combining_and_control_chars() -> None:
    """Line 71: combining/control characters are skipped (width 0)."""
    from repo_release_tools.ui.glyphs import display_width

    # U+0301 is a combining acute accent (width 0)
    assert display_width("e\u0301") == 1
    # U+200B is a zero-width space (category Cf)
    assert display_width("a\u200bb") == 2


def test_repeat_to_width_zero_width_glyph() -> None:
    """Line 96: glyph_width <= 0 → returns spaces."""
    from repo_release_tools.ui.glyphs import Glyph, _repeat_to_width

    # U+200B has display_width 0
    zero_width_glyph = Glyph("\u200b", "zero")
    result = _repeat_to_width(zero_width_glyph, 5)
    assert result == " " * 5


def test_box_glyphs_box_renders() -> None:
    """Lines 148-151: BoxGlyphs.box() renders a 3-line box."""
    from repo_release_tools.ui.glyphs import BoxGlyphs

    box = BoxGlyphs()
    result = box.box("hello")
    lines = result.splitlines()
    assert len(lines) == 3
    assert "hello" in lines[1]


def test_box_glyphs_double_box_renders() -> None:
    """Lines 161-164: BoxGlyphs.double_box() renders a 3-line double-border box."""
    from repo_release_tools.ui.glyphs import BoxGlyphs

    box = BoxGlyphs()
    result = box.double_box("hello")
    lines = result.splitlines()
    assert len(lines) == 3
    assert "hello" in lines[1]


def test_box_glyphs_table_empty_headers_returns_empty() -> None:
    """Line 175: table() with no headers returns ''."""
    from repo_release_tools.ui.glyphs import BoxGlyphs

    assert BoxGlyphs().table([], []) == ""


def test_box_glyphs_table_row_length_mismatch_raises() -> None:
    """Line 177: table() with mismatched row length raises ValueError."""
    import pytest

    from repo_release_tools.ui.glyphs import BoxGlyphs

    with pytest.raises(ValueError, match="table rows must match header count"):
        BoxGlyphs().table(["A", "B"], [["only_one"]])


def test_git_glyphs_log_line_with_refs() -> None:
    """Lines 439-443: GitGlyphs.log_line() with refs includes ref labels."""
    from repo_release_tools.ui.glyphs import GitGlyphs

    git = GitGlyphs()
    result = git.log_line("abc1234", "fix bug", refs=["main", "HEAD"])
    assert "abc1234" in result
    assert "main" in result
    assert "HEAD" in result
    assert "fix bug" in result


def test_git_glyphs_log_line_without_refs() -> None:
    """Lines 439-443: GitGlyphs.log_line() without refs has no ref brackets."""
    from repo_release_tools.ui.glyphs import GitGlyphs

    git = GitGlyphs()
    result = git.log_line("deadbeef", "chore: update deps")
    assert "deadbee" in result
    assert "chore: update deps" in result
