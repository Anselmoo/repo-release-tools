from __future__ import annotations

import io
import types

import pytest

from repo_release_tools.ui import (
    GLYPHS,
    ProgressLine,
    banner,
    diff_highlight,
    highlight_terminal,
    hyperlink,
    json_highlight,
    panel,
    pretty_print,
    render_dry_run_complete,
    render_hint,
    render_info,
    section_line,
    spinner_lines,
)

# Compatibility shim — maps legacy output.X names to the canonical ui API.
output = types.SimpleNamespace(
    panel=panel,
    banner=banner,
    info=render_info,
    hint=render_hint,
    dry_run_complete=render_dry_run_complete,
    spinner_lines=spinner_lines,
    section=section_line,
    GLYPHS=GLYPHS,
    ProgressLine=ProgressLine,
    highlight_terminal=highlight_terminal,
    hyperlink=hyperlink,
    pretty_print=pretty_print,
    json_highlight=json_highlight,
    diff_highlight=diff_highlight,
)


def test_panel_renders_boxed_summary() -> None:
    rendered = output.panel(
        "Version bump",
        [("Current", "0.1.0 -> 0.1.1"), ("Branch", "release/v0.1.1")],
    )

    assert "Version bump" in rendered
    assert "Current" in rendered
    assert "release/v0.1.1" in rendered
    assert rendered.splitlines()[0][0] in {"+", "┌"}
    assert rendered.splitlines()[-1][0] in {"+", "└"}


def test_panel_keeps_branch_summary_width_consistent() -> None:
    rendered = output.panel(
        "New branch",
        [("Base", "main"), ("Branch", "feat/v0-15-0"), ("Title", "feat: v0.15.0")],
    )

    b = GLYPHS.box
    assert rendered == "\n".join(
        [
            f"{b.tl} New branch {b.h * 13}{b.tr}",
            f"{b.v} Base   {b.v} main           {b.v}",
            f"{b.left}{b.h * 8}{b.cross}{b.h * 16}{b.right}",
            f"{b.v} Branch {b.v} feat/v0-15-0   {b.v}",
            f"{b.left}{b.h * 8}{b.cross}{b.h * 16}{b.right}",
            f"{b.v} Title  {b.v} feat: v0.15.0  {b.v}",
            f"{b.bl}{b.h * 8}{b.bottom}{b.h * 16}{b.br}",
        ]
    )


def test_panel_bottom_has_t_junction_not_plain_h() -> None:
    """The column junction in the bottom border must use ┴ not ─."""
    rendered = output.panel(
        "Test",
        [("A", "b"), ("C", "d")],
    )
    bottom_line = rendered.splitlines()[-1]
    assert "┴" in bottom_line or "+" in bottom_line  # unicode or ASCII fallback


def test_panel_style_rounded_uses_rounded_corners() -> None:
    rendered = output.panel(
        "Test",
        [("key", "value")],
        style="rounded",
    )
    assert rendered.startswith("╭") or rendered.startswith("+")  # unicode or ASCII
    assert rendered.splitlines()[-1].startswith("╰") or rendered.splitlines()[-1].startswith("+")
    # bottom junction must be ┴ (thin divider), not a plain h
    bottom_line = rendered.splitlines()[-1]
    assert "┴" in bottom_line or "+" in bottom_line


def test_panel_style_bold_uses_bold_corners() -> None:
    rendered = output.panel(
        "Test",
        [("key", "value")],
        style="bold",
    )
    assert rendered.startswith("┏") or rendered.startswith("+")
    assert rendered.splitlines()[-1].startswith("┗") or rendered.splitlines()[-1].startswith("+")
    bottom_line = rendered.splitlines()[-1]
    assert "┻" in bottom_line or "+" in bottom_line


def test_panel_style_mixed_bold_outer_thin_inner() -> None:
    rendered = output.panel(
        "Test",
        [("A", "b"), ("C", "d")],
        style="mixed",
    )
    lines = rendered.splitlines()
    # Top and bottom use bold corners; row separator uses thin dividers.
    assert lines[0].startswith("┏") or lines[0].startswith("+")
    assert lines[-1].startswith("┗") or lines[-1].startswith("+")
    if "─" in lines[2]:  # unicode terminal
        assert "┼" in lines[2]  # thin cross in interior separator


def test_banner_renders_a_boxed_title() -> None:
    rendered = output.banner("New action")

    assert rendered.splitlines()[0].startswith("┏") or rendered.splitlines()[0].startswith("+")
    assert rendered.splitlines()[-1].startswith("┗") or rendered.splitlines()[-1].startswith("+")
    assert "New action" in rendered


def test_info_renders_arrow_glyph() -> None:
    rendered = output.info("Process started")

    assert "Process started" in rendered
    assert rendered.strip().startswith(str(output.GLYPHS.arrow.right))


def test_hint_renders_ellipsis_glyph() -> None:
    rendered = output.hint("Use --dry-run to preview changes")

    assert "Use --dry-run to preview changes" in rendered
    assert rendered.strip().startswith(str(output.GLYPHS.typography.ellipsis))


def test_dry_run_complete_uses_shared_typography() -> None:
    rendered = output.dry_run_complete("no changes made")

    assert "[dry-run] complete" in rendered
    assert "no changes made" in rendered
    assert rendered.startswith("[-]") or rendered.startswith("⊖")


def test_spinner_lines_noop_on_non_tty() -> None:
    """spinner_lines must not crash and must produce no output when not a tty."""
    import io

    non_tty = io.StringIO()
    with output.spinner_lines("Working…", file=non_tty):
        pass

    assert non_tty.getvalue() == ""


def test_panel_empty_rows_returns_title_only() -> None:
    """panel() with no rows must return just the title string."""
    result = output.panel("Just a title", [])
    assert result == "Just a title"


def test_section_renders_a_heading_line() -> None:
    rendered = output.section("Build")

    assert "Build" in rendered
    assert rendered.startswith("──") or rendered.startswith("--")


def test_panel_expands_value_width_to_fit_title() -> None:
    rendered = output.panel("Long title header", [("A", "b")])

    assert "Long title header" in rendered
    assert len(rendered.splitlines()[0]) >= len(" Long title header ")


def test_panel_title_row_separates_title_from_border() -> None:
    rendered = output.panel("Environment", [("Platform", "darwin")], title_mode="row")

    lines = rendered.splitlines()
    assert lines[0].startswith("┌") or lines[0].startswith("+")
    assert "Environment" in lines[1]
    assert lines[1].startswith("│") or lines[1].startswith("|")
    assert lines[2].startswith("├") or lines[2].startswith("+")


def test_panel_empty_title_renders_plain_border() -> None:
    rendered = output.panel("", [("A", "b")])

    lines = rendered.splitlines()
    assert lines[0].startswith("┌") or lines[0].startswith("+")
    assert "A" in rendered
    assert "┌ " not in lines[0] or "┌  " not in lines[0]  # title should not render blank spaces


def test_panel_empty_title_row_renders_plain_border() -> None:
    rendered = output.panel("", [("A", "b")], title_mode="row")

    lines = rendered.splitlines()
    assert lines[0].startswith("┌") or lines[0].startswith("+")
    assert lines[1].startswith("├") or lines[1].startswith("+")
    assert "A" in rendered


def test_spinner_lines_noop_on_legacy_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """spinner_lines must skip threading when IS_LEGACY_TERMINAL is True."""
    import io
    import repo_release_tools.ui.progress as _prog

    monkeypatch.setattr(_prog, "IS_LEGACY_TERMINAL", True)
    non_tty = io.StringIO()
    with output.spinner_lines("Working…", file=non_tty):
        pass

    assert non_tty.getvalue() == ""


def test_spinner_lines_noop_yields_normally() -> None:
    """The body of the with block executes even in no-op mode."""
    import io

    ran = []
    with output.spinner_lines("x", file=io.StringIO()):
        ran.append(True)

    assert ran == [True]


def test_progress_line_noop_on_non_tty() -> None:
    non_tty = io.StringIO()
    progress = output.ProgressLine(file=non_tty)

    progress.update_bar(0.5)

    assert non_tty.getvalue() == ""


def test_spinner_lines_propagates_exception() -> None:
    """Exceptions raised inside the context propagate out."""
    with pytest.raises(ValueError, match="boom"):
        with output.spinner_lines("x", file=io.StringIO()):
            raise ValueError("boom")


class _TtyBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True


class _FakeEvent:
    def __init__(self) -> None:
        self._is_set = False

    def is_set(self) -> bool:
        return self._is_set

    def wait(self, timeout: float | None = None) -> bool:
        self._is_set = True
        return True

    def set(self) -> None:
        self._is_set = True


class _FakeThread:
    def __init__(self, target, daemon: bool) -> None:
        self._target = target
        self.daemon = daemon
        self.join_timeout: float | None = None

    def start(self) -> None:
        self._target()

    def join(self, timeout: float | None = None) -> None:
        self.join_timeout = timeout


def test_spinner_lines_writes_success_status_on_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    tty = _TtyBuffer()
    import repo_release_tools.ui.progress as _prog

    monkeypatch.setattr(_prog.threading, "Event", _FakeEvent)
    monkeypatch.setattr(_prog.threading, "Thread", _FakeThread)

    with output.spinner_lines("Working", file=tty):
        pass

    rendered = tty.getvalue()
    assert "Working" in rendered
    assert f"{output.GLYPHS.bullet.ok}  Working" in rendered


def test_spinner_lines_writes_detail_on_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    tty = _TtyBuffer()
    import repo_release_tools.ui.progress as _prog

    monkeypatch.setattr(_prog.threading, "Event", _FakeEvent)
    monkeypatch.setattr(_prog.threading, "Thread", _FakeThread)

    with output.spinner_lines("Working", detail="$ uv lock -U", file=tty):
        pass

    rendered = tty.getvalue()
    assert "$ uv lock -U" in rendered
    assert f"{output.GLYPHS.bullet.ok}  Working  $ uv lock -U" in rendered


def test_syntax_forwards_stream_to_highlight_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_highlight(
        code: str,
        language: str,
        *,
        line_numbers: bool = False,
        background: str = "dark",
        stream=None,
    ) -> str:
        captured["code"] = code
        captured["language"] = language
        captured["stream"] = stream
        return "rendered"

    import repo_release_tools.ui.syntax as _syn

    monkeypatch.setattr(_syn, "highlight_terminal", fake_highlight)
    monkeypatch.setattr(output, "highlight_terminal", fake_highlight)

    stream = io.StringIO()
    rendered = output.highlight_terminal("print('x')", "python", stream=stream)

    assert rendered == "rendered"
    assert captured["stream"] is stream


def test_progress_line_writes_initial_bar_on_tty() -> None:
    tty = _TtyBuffer()
    progress = output.ProgressLine(file=tty)

    progress.update_bar(0.5)

    assert tty.getvalue() == f"\r  {output.GLYPHS.progress.render_bar(0.5)}\x1b[K"


def test_progress_line_shorter_message_clears_trailing_chars() -> None:
    """A shorter update must not leave leftover chars from a longer prior render."""
    tty = _TtyBuffer()
    progress = output.ProgressLine(file=tty)

    progress.update("A" * 40)
    progress.update("B" * 10)

    rendered = tty.getvalue()
    # Both writes must carry the clear-to-EOL escape so leftovers are erased.
    assert rendered.count("\x1b[K") == 2
    # The 30 trailing 'A' characters must not appear after the second write.
    assert rendered.endswith(f"\r{'B' * 10}\x1b[K")


def test_progress_line_clear_then_rewrite() -> None:
    tty = _TtyBuffer()
    progress = output.ProgressLine(file=tty)

    progress.update_bar(0.5)
    progress.clear()
    tty.write("  ✔ updated file\n")
    progress.update_bar(1.0)

    rendered = tty.getvalue()
    assert f"\r  {output.GLYPHS.progress.render_bar(0.5)}" in rendered
    assert "\r\x1b[2K" in rendered
    assert f"\r  {output.GLYPHS.progress.render_bar(1.0)}" in rendered
    # old cursor-reposition sequences must not appear
    assert "\x1b[2A" not in rendered
    assert "\x1b[M" not in rendered


def test_spinner_lines_writes_error_status_on_tty_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tty = _TtyBuffer()
    import repo_release_tools.ui.progress as _prog

    monkeypatch.setattr(_prog.threading, "Event", _FakeEvent)
    monkeypatch.setattr(_prog.threading, "Thread", _FakeThread)

    with pytest.raises(RuntimeError, match="boom"):
        with output.spinner_lines("Exploding", file=tty):
            raise RuntimeError("boom")

    rendered = tty.getvalue()
    assert "Exploding" in rendered
    assert f"{output.GLYPHS.bullet.error}  Exploding" in rendered


# ── New Phase 2/3a tests ────────────────────────────────────────────────────


def test_panel_wraps_long_value(monkeypatch) -> None:
    """panel() must wrap values that exceed value_width when terminal is narrow."""
    import repo_release_tools.ui.layout as _layout

    monkeypatch.setattr(_layout, "terminal_width", lambda default=100: 40)
    rendered = output.panel(
        "Wrap test",
        [("Key", "short"), ("Long", "x " * 20)],
    )
    lines = rendered.splitlines()
    # The long value row should produce more than one body line.
    assert len(lines) > 5


def test_hyperlink_returns_osc8_when_color_supported(monkeypatch) -> None:
    import repo_release_tools.ui.color as _color

    monkeypatch.setattr(_color, "supports_color", lambda stream=None: True)
    result = output.hyperlink("click here", "https://example.com")
    assert "\x1b]8;;" in result
    assert "click here" in result
    assert "https://example.com" in result


def test_hyperlink_falls_back_to_plain_text_when_no_color(monkeypatch) -> None:
    import repo_release_tools.ui.color as _color

    monkeypatch.setattr(_color, "supports_color", lambda stream=None: False)
    result = output.hyperlink("click here", "https://example.com")
    assert result == "click here (https://example.com)"


def test_spinner_lines_cancelled_writes_warning_glyph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tty = _TtyBuffer()
    import repo_release_tools.ui.progress as _prog

    monkeypatch.setattr(_prog.threading, "Event", _FakeEvent)
    monkeypatch.setattr(_prog.threading, "Thread", _FakeThread)

    with pytest.raises(KeyboardInterrupt):
        with output.spinner_lines("Task", file=tty):
            raise KeyboardInterrupt

    rendered = tty.getvalue()
    assert "Cancelled" in rendered
    assert str(output.GLYPHS.bullet.warning) in rendered


def test_pretty_print_returns_string(monkeypatch) -> None:
    monkeypatch.setattr(output, "highlight_terminal", lambda code, lang, **kw: code)
    result = output.pretty_print({"a": 1})
    assert "a" in result


def test_json_highlight_returns_valid_json(monkeypatch) -> None:
    monkeypatch.setattr(output, "highlight_terminal", lambda code, lang, **kw: code)
    result = output.json_highlight({"key": "value"})
    import json

    parsed = json.loads(result)
    assert parsed == {"key": "value"}


# ── Phase 3a P3 + panel expand tests ────────────────────────────────────────


def test_diff_highlight_returns_non_empty_for_diff_text(monkeypatch) -> None:
    monkeypatch.setattr(output, "highlight_terminal", lambda code, lang, **kw: code)
    diff = "--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new\n"
    result = output.diff_highlight(diff)
    assert "old" in result
    assert "new" in result


def test_diff_highlight_empty_returns_empty() -> None:
    assert output.diff_highlight("   ") == "   "


def test_panel_expand_fills_terminal_width(monkeypatch) -> None:
    import repo_release_tools.ui.layout as _layout

    monkeypatch.setattr(_layout, "terminal_width", lambda default=100: 60)
    result = output.panel("T", [("k", "v")], expand=True)
    # The top border line should be close to 60 - 4 = 56 chars wide
    top_line = result.splitlines()[0]
    assert len(top_line) >= 54


def test_panel_no_expand_stays_narrow(monkeypatch) -> None:
    import repo_release_tools.ui.layout as _layout

    monkeypatch.setattr(_layout, "terminal_width", lambda default=100: 60)
    result = output.panel("T", [("k", "short")])
    top_line = result.splitlines()[0]
    # Without expand, the box should be narrower than terminal width
    assert len(top_line) < 55
