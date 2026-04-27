from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from repo_release_tools.commands.skill import cmd_install
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
