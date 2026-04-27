from __future__ import annotations

from repo_release_tools.ui import layout


def test_section_line_renders_with_prefix_and_fill() -> None:
    rendered = layout.section_line("Build", body_width=10, glyph="-", left=2)

    assert rendered.startswith("-- Build ")


def test_truncate_adds_ellipsis_when_needed() -> None:
    rendered = layout.truncate("abcdefghijklmnopqrstuvwxyz", width=8)

    assert rendered.endswith("…")
    assert len(rendered) <= 8


def test_align_center_preserves_width() -> None:
    rendered = layout.align("abc", width=9, mode="center")

    assert len(rendered) == 9
    assert rendered.strip() == "abc"


def test_box_renders_single_style_with_title() -> None:
    rendered = layout.box("hello", title="Title", style="single")

    lines = rendered.splitlines()
    assert len(lines) == 3
    assert "Title" in lines[0]
    assert "hello" in lines[1]


def test_box_renders_ascii_style() -> None:
    rendered = layout.box(["alpha", "beta"], style="ascii")

    lines = rendered.splitlines()
    assert lines[0].startswith("+")
    assert lines[1].startswith("|")
    assert lines[-1].startswith("+")


def test_box_renders_rounded_style() -> None:
    rendered = layout.box(["alpha", "beta"], style="rounded")

    assert rendered.splitlines()[0].startswith("╭") or rendered.splitlines()[0].startswith("+")


def test_box_renders_bold_style() -> None:
    rendered = layout.box(["alpha", "beta"], style="bold")

    assert rendered.splitlines()[0].startswith("┏") or rendered.splitlines()[0].startswith("+")


def test_ascii_box_fallback_is_reusable_module_scope() -> None:
    assert layout.ASCII_BOX.h == "-"
    assert layout.ASCII_BOX.tl == "+"
    assert layout.box("hello", style="ascii").startswith("+")


def test_progress_bar_clamps_value() -> None:
    low = layout.progress_bar(-1.0, width=10)
    high = layout.progress_bar(2.0, width=10)

    assert low.endswith("0%")
    assert high.endswith("100%")


def test_sparkline_ascii_mode() -> None:
    rendered = layout.sparkline([1, 2, 3, 4], ascii_only=True)

    assert len(rendered) == 4
    assert all(ch in "._-~=*#" for ch in rendered)


# ── Phase 2 I4/I7/I8/M8 tests ───────────────────────────────────────────────


def test_section_line_auto_width_fills_terminal(monkeypatch) -> None:
    monkeypatch.setattr(layout, "terminal_width", lambda default=100: 80)
    result = layout.section_line("Section")
    # Total length should be ≈ 76 chars (80 - 4 = 76)
    assert len(result) > 20


def test_section_line_explicit_width() -> None:
    result = layout.section_line("X", body_width=30)
    assert len(result) > 5


def test_progress_bar_with_label_and_pct() -> None:
    result = layout.progress_bar(0.5, label="Loading…", show_pct=True)
    assert "50%" in result
    assert "Loading…" in result


def test_progress_bar_no_pct() -> None:
    result = layout.progress_bar(0.75, show_pct=False)
    assert "%" not in result


def test_progress_bar_explicit_chars() -> None:
    result = layout.progress_bar(0.5, width=10, full="X", empty=".")
    assert "X" in result
    assert "." in result


def test_box_auto_width_does_not_exceed_terminal(monkeypatch) -> None:
    monkeypatch.setattr(layout, "terminal_width", lambda default=100: 40)
    long_line = "x" * 100
    result = layout.box(long_line)
    # inner_width = min(100+2, 40-4) = 36; border lines = 36 + 2 = 38
    lines = result.splitlines()
    assert max(len(line) for line in lines) <= 38


def test_box_explicit_width() -> None:
    result = layout.box("short", width=30)
    lines = result.splitlines()
    # inner_width = 30 + 2*padding (1) = 32, plus 2 for borders = 34
    assert len(lines[0]) == 34


def test_rule_full_width(monkeypatch) -> None:
    monkeypatch.setattr(layout, "terminal_width", lambda default=100: 60)
    result = layout.rule()
    assert len(result) == 56  # 60 - 4


def test_rule_with_title(monkeypatch) -> None:
    monkeypatch.setattr(layout, "terminal_width", lambda default=100: 60)
    result = layout.rule("Section")
    assert "Section" in result
    assert len(result) >= 56


def test_rule_explicit_width() -> None:
    result = layout.rule("X", width=20)
    assert "X" in result
    assert len(result) == 20


def test_rule_title_only_when_too_wide() -> None:
    result = layout.rule("very long title that exceeds width", width=5)
    assert "very long title that exceeds width" in result
