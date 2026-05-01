from __future__ import annotations

import sys

from repo_release_tools.ui.glyphs import GLYPHS
from repo_release_tools.ui.glyphs import Glyph
from repo_release_tools.ui.glyphs import _detect_legacy_terminal
from repo_release_tools.ui.glyphs import display_width


def test_glyph_multiplies_like_a_string() -> None:
    glyph = Glyph("-", "dash")

    assert glyph * 3 == "---"
    assert 2 * glyph == "--"


def test_git_status_line_stays_compact() -> None:
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


def test_detect_legacy_terminal_dumb(monkeypatch) -> None:
    monkeypatch.setenv("TERM", "dumb")
    # Patch sys.platform so this test exercises the TERM branch on Windows CI too.
    monkeypatch.setattr(sys, "platform", "linux")
    assert _detect_legacy_terminal() is True


def test_detect_legacy_terminal_no_color(monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    # Patch sys.platform so this test exercises the NO_COLOR branch on Windows CI too.
    monkeypatch.setattr(sys, "platform", "linux")
    assert _detect_legacy_terminal() is True


def test_detect_legacy_terminal_normal(monkeypatch) -> None:
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


def test_display_width_ambiguous_narrow_by_default(monkeypatch) -> None:
    # Bullet '•' has east_asian_width 'A' – counted as 1 in a non-CJK locale.
    monkeypatch.setenv("RRT_WIDE_AMBIGUOUS", "0")
    from importlib import reload
    import repo_release_tools.ui.glyphs as g

    reload(g)
    assert g.display_width("•") == 1
    monkeypatch.delenv("RRT_WIDE_AMBIGUOUS")
    reload(g)  # restore _AMBIGUOUS_IS_WIDE to its natural value


def test_display_width_ambiguous_wide_when_override(monkeypatch) -> None:
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
