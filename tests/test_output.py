from repo_release_tools import output


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


def test_dry_run_complete_uses_shared_typography() -> None:
    rendered = output.dry_run_complete("no changes made")

    assert "[dry-run] complete" in rendered
    assert "no changes made" in rendered
    assert rendered.startswith("[-]") or rendered.startswith("⊖")
