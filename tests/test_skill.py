from __future__ import annotations

import argparse
from argparse import Namespace
from pathlib import Path

from repo_release_tools.commands.skill import (
    _dedupe_targets,
    _display_path,
    _resolve_install_plan,
    cmd_install,
    register,
)
from repo_release_tools.skill_assets import INSTALLED_CLI_SKILL


def _mock_home(monkeypatch, home: Path) -> None:
    monkeypatch.setattr("repo_release_tools.commands.skill.Path.home", lambda: home)


def test_bundled_skill_matches_checked_in_skill_file() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    checked_in = repo_root / ".github" / "skills" / "repo-release-tools" / "SKILL.md"

    assert checked_in.read_text(encoding="utf-8") == INSTALLED_CLI_SKILL.markdown.rstrip() + "\n"


def test_cmd_install_writes_local_skill(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    monkeypatch.chdir(tmp_path)
    _mock_home(monkeypatch, home)

    result = cmd_install(Namespace(targets=["copilot-local"], dry_run=False, force=False))

    assert result == 0
    installed = tmp_path / ".copilot" / "skills" / "repo-release-tools" / "SKILL.md"
    assert installed.exists()
    assert installed.read_text(encoding="utf-8").startswith("---\nname: repo-release-tools\n")


def test_cmd_install_dry_run_does_not_write(monkeypatch, tmp_path: Path, capsys) -> None:
    home = tmp_path / "home"
    monkeypatch.chdir(tmp_path)
    _mock_home(monkeypatch, home)

    result = cmd_install(Namespace(targets=["claude-local"], dry_run=True, force=False))

    captured = capsys.readouterr()
    assert result == 0
    assert not (tmp_path / ".claude" / "skills" / "repo-release-tools").exists()
    assert "Would install repo-release-tools to claude-local" in captured.out
    assert "[dry-run] complete" in captured.out


def test_cmd_install_refuses_existing_skill_without_force(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    home = tmp_path / "home"
    monkeypatch.chdir(tmp_path)
    _mock_home(monkeypatch, home)
    installed = tmp_path / ".codex" / "skills" / "repo-release-tools"
    installed.mkdir(parents=True)
    skill_file = installed / "SKILL.md"
    skill_file.write_text("old skill\n", encoding="utf-8")

    result = cmd_install(Namespace(targets=["codex-local"], dry_run=False, force=False))

    captured = capsys.readouterr()
    assert result == 1
    assert skill_file.read_text(encoding="utf-8") == "old skill\n"
    assert "Use --force to overwrite it" in captured.err


def test_cmd_install_force_overwrites_existing_skill(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    monkeypatch.chdir(tmp_path)
    _mock_home(monkeypatch, home)
    installed = tmp_path / ".copilot" / "skills" / "repo-release-tools"
    installed.mkdir(parents=True)
    (installed / "SKILL.md").write_text("old skill\n", encoding="utf-8")

    result = cmd_install(Namespace(targets=["copilot-local"], dry_run=False, force=True))

    assert result == 0
    assert (installed / "SKILL.md").read_text(encoding="utf-8") == (
        INSTALLED_CLI_SKILL.markdown.rstrip() + "\n"
    )


def test_cmd_install_global_target_uses_home_directory(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    monkeypatch.chdir(tmp_path)
    _mock_home(monkeypatch, home)

    result = cmd_install(Namespace(targets=["claude-global"], dry_run=False, force=False))

    assert result == 0
    installed = home / ".claude" / "skills" / "repo-release-tools" / "SKILL.md"
    assert installed.exists()


def test_cmd_install_aborts_all_targets_when_one_conflicts(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    home = tmp_path / "home"
    monkeypatch.chdir(tmp_path)
    _mock_home(monkeypatch, home)
    conflict_dir = tmp_path / ".copilot" / "skills" / "repo-release-tools"
    conflict_dir.mkdir(parents=True)
    (conflict_dir / "SKILL.md").write_text("old skill\n", encoding="utf-8")

    result = cmd_install(
        Namespace(targets=["copilot-local", "codex-local"], dry_run=False, force=False)
    )

    captured = capsys.readouterr()
    assert result == 1
    assert "copilot-local already has repo-release-tools" in captured.err
    assert not (tmp_path / ".codex" / "skills" / "repo-release-tools").exists()


def test_dedupe_targets_preserves_order_and_drops_duplicates() -> None:
    result = _dedupe_targets(["copilot-local", "claude-local", "copilot-local", "codex-local"])

    assert result == ["copilot-local", "claude-local", "codex-local"]


def test_display_path_uses_cwd_home_and_absolute(tmp_path: Path) -> None:
    cwd = tmp_path / "repo"
    home = tmp_path / "home"
    cwd.mkdir()
    home.mkdir()

    assert _display_path(cwd / "file.txt", cwd=cwd, home=home) == "file.txt"
    assert (
        _display_path(home / ".copilot" / "skills" / "repo-release-tools", cwd=cwd, home=home)
        == "~/.copilot/skills/repo-release-tools"
    )
    absolute = Path("/tmp") / "outside"
    assert _display_path(absolute, cwd=cwd, home=home) == str(absolute)


def test_resolve_install_plan_uses_target_mappings(tmp_path: Path) -> None:
    cwd = tmp_path / "repo"
    home = tmp_path / "home"
    cwd.mkdir()
    home.mkdir()

    plan = _resolve_install_plan(
        ["copilot-local", "claude-global", "copilot-local"], cwd=cwd, home=home
    )

    assert plan == [
        ("copilot-local", cwd / ".copilot" / "skills"),
        ("claude-global", home / ".claude" / "skills"),
    ]


def test_cmd_install_returns_one_for_os_error(monkeypatch, tmp_path: Path, capsys) -> None:
    home = tmp_path / "home"
    monkeypatch.chdir(tmp_path)
    _mock_home(monkeypatch, home)

    def raise_os_error(self, *args, **kwargs):
        raise OSError("boom")

    monkeypatch.setattr(Path, "write_text", raise_os_error)

    result = cmd_install(Namespace(targets=["copilot-local"], dry_run=False, force=True))

    captured = capsys.readouterr()
    assert result == 1
    assert "Could not install repo-release-tools to copilot-local" in captured.err


def test_register_adds_skill_install_parser() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    register(subparsers)

    args = parser.parse_args(["skill", "install", "--target", "copilot-local"])

    assert args.command == "skill"
    assert args.skill_command == "install"
    assert args.targets == ["copilot-local"]
