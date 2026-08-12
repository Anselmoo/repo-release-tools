from __future__ import annotations

from pathlib import Path

from repo_release_tools.commands._install_shared import (
    dedupe_targets,
    display_path,
    resolve_install_plan,
)

FAKE_TARGET_PATHS = {
    "alpha-local": lambda cwd, home: cwd / ".alpha",
    "alpha-global": lambda cwd, home: home / ".alpha",
}


def test_dedupe_targets_preserves_order_and_drops_duplicates() -> None:
    result = dedupe_targets(["claude-local", "codex-local", "claude-local"])
    assert result == ["claude-local", "codex-local"]


def test_display_path_uses_cwd_home_and_absolute(tmp_path: Path) -> None:
    cwd = tmp_path / "project"
    home = tmp_path / "home"
    local_path = cwd / "file.txt"
    home_path = home / "file.txt"
    abs_path = tmp_path / "other" / "file.txt"

    assert display_path(local_path, cwd=cwd, home=home) == "file.txt"
    assert display_path(home_path, cwd=cwd, home=home) == "~/file.txt"
    assert display_path(abs_path, cwd=cwd, home=home) == str(abs_path)


def test_resolve_install_plan_dedupes_and_resolves_via_target_paths(tmp_path: Path) -> None:
    cwd = tmp_path / "project"
    home = tmp_path / "home"

    plan = resolve_install_plan(
        ["alpha-local", "alpha-global", "alpha-local"],
        FAKE_TARGET_PATHS,
        cwd=cwd,
        home=home,
    )

    assert plan == [
        ("alpha-local", cwd / ".alpha"),
        ("alpha-global", home / ".alpha"),
    ]
