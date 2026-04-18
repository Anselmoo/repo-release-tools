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


def test_spinner_lines_propagates_exception() -> None:
    """Exceptions raised inside the context propagate out."""
    import io

    with pytest.raises(ValueError, match="boom"):
        with output.spinner_lines("x", file=io.StringIO()):
            raise ValueError("boom")
