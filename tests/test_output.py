from repo_release_tools import output
from repo_release_tools.glyphs import GLYPHS, display_width


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

    assert rendered == "\n".join(
        [
            f"{GLYPHS.box.tl} New branch {GLYPHS.box.h * 13}{GLYPHS.box.tr}",
            f"{GLYPHS.box.v} Base   {GLYPHS.box.v} main           {GLYPHS.box.v}",
            f"{GLYPHS.box.left}{GLYPHS.box.h * 8}{GLYPHS.box.cross}{GLYPHS.box.h * 16}{GLYPHS.box.right}",
            f"{GLYPHS.box.v} Branch {GLYPHS.box.v} feat/v0-15-0   {GLYPHS.box.v}",
            f"{GLYPHS.box.left}{GLYPHS.box.h * 8}{GLYPHS.box.cross}{GLYPHS.box.h * 16}{GLYPHS.box.right}",
            f"{GLYPHS.box.v} Title  {GLYPHS.box.v} feat: v0.15.0  {GLYPHS.box.v}",
            f"{GLYPHS.box.bl}{GLYPHS.box.h * 25}{GLYPHS.box.br}",
        ]
    )


def test_panel_uses_display_width_when_padding() -> None:
    rendered = output.panel("Status", [("State", "漢字"), ("ASCII", "ok")])
    lines = rendered.splitlines()

    assert len({display_width(line) for line in lines}) == 1


def test_dry_run_complete_uses_shared_typography() -> None:
    rendered = output.dry_run_complete("no changes made")

    assert "[dry-run] complete" in rendered
    assert "no changes made" in rendered
    assert rendered.startswith("[-]") or rendered.startswith("⊖")
