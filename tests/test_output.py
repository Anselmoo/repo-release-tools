import io

import pytest

from repo_release_tools import output
from repo_release_tools.glyphs import GLYPHS


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


def test_dry_run_complete_uses_shared_typography() -> None:
    rendered = output.dry_run_complete("no changes made")

    assert "[dry-run] complete" in rendered
    assert "no changes made" in rendered
    assert rendered.startswith("[-]") or rendered.startswith("⊖")


def test_spinner_lines_noop_on_non_tty(capsys) -> None:
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


def test_spinner_lines_noop_on_legacy_terminal(monkeypatch, capsys) -> None:
    """spinner_lines must skip threading when IS_LEGACY_TERMINAL is True."""
    import io

    monkeypatch.setattr(output, "IS_LEGACY_TERMINAL", True)
    non_tty = io.StringIO()
    with output.spinner_lines("Working…", file=non_tty):
        pass

    assert non_tty.getvalue() == ""


def test_spinner_lines_noop_yields_normally(capsys) -> None:
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

    monkeypatch.setattr(output.threading, "Event", _FakeEvent)
    monkeypatch.setattr(output.threading, "Thread", _FakeThread)

    with output.spinner_lines("Working", file=tty):
        pass

    rendered = tty.getvalue()
    assert "Working" in rendered
    assert f"{output.GLYPHS.bullet.ok}  Working" in rendered


def test_spinner_lines_writes_detail_on_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    tty = _TtyBuffer()

    monkeypatch.setattr(output.threading, "Event", _FakeEvent)
    monkeypatch.setattr(output.threading, "Thread", _FakeThread)

    with output.spinner_lines("Working", detail="$ uv lock -U", file=tty):
        pass

    rendered = tty.getvalue()
    assert "$ uv lock -U" in rendered
    assert f"{output.GLYPHS.bullet.ok}  Working  $ uv lock -U" in rendered


def test_progress_line_writes_initial_bar_on_tty() -> None:
    tty = _TtyBuffer()
    progress = output.ProgressLine(file=tty)

    progress.update_bar(0.5)

    assert tty.getvalue() == f"\r  {output.GLYPHS.progress.render_bar(0.5)}"


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

    monkeypatch.setattr(output.threading, "Event", _FakeEvent)
    monkeypatch.setattr(output.threading, "Thread", _FakeThread)

    with pytest.raises(RuntimeError, match="boom"):
        with output.spinner_lines("Exploding", file=tty):
            raise RuntimeError("boom")

    rendered = tty.getvalue()
    assert "Exploding" in rendered
    assert f"{output.GLYPHS.bullet.error}  Exploding" in rendered
