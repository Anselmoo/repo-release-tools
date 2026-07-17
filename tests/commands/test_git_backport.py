from __future__ import annotations

import argparse
import pathlib

import pytest

from repo_release_tools.commands import git_backport
from repo_release_tools.config.model import PublishTarget, RrtConfig


def test_register_adds_git_backport_from_target_parser() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    git_sub = subparsers.add_parser("git")
    inner = git_sub.add_subparsers(dest="git_command", parser_class=type(git_sub))
    git_backport.register_backport(inner)

    args = parser.parse_args(["git", "backport-from-target", "demo", "--remote", "mirror"])

    assert args.command == "git"
    assert args.git_command == "backport-from-target"
    assert args.target == "demo"
    assert args.remote == "mirror"
    assert args.handler.__name__ == "cmd_backport_from_target"


def test_backport_requires_git_repository(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(git_backport.git, "is_git_repository", lambda root: False)
    args = argparse.Namespace(target="demo", remote=None, branch=None, base_ref=None, dry_run=False)
    assert git_backport.cmd_backport_from_target(args) == 1
    assert "is not inside a Git work tree" in capsys.readouterr().err


def test_backport_rejects_unknown_config_target(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = RrtConfig(root=tmp_path, config_file=tmp_path / "pyproject.toml", version_groups=[])
    monkeypatch.setattr(git_backport, "load_or_autodetect_config", lambda root: config)
    monkeypatch.setattr(git_backport.git, "is_git_repository", lambda root: True)
    args = argparse.Namespace(
        target="missing", remote=None, branch=None, base_ref=None, dry_run=False
    )
    monkeypatch.chdir(tmp_path)
    assert git_backport.cmd_backport_from_target(args) == 1
    err = capsys.readouterr().err
    assert "No publish target named 'missing'" in err


def _config_with_demo_target(tmp_path: pathlib.Path) -> RrtConfig:
    return RrtConfig(
        root=tmp_path,
        config_file=tmp_path / "pyproject.toml",
        version_groups=[],
        publish_targets={"demo": PublishTarget(remote="mirror", branch="main")},
    )


def test_backport_rejects_base_ref_starting_with_dash(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = _config_with_demo_target(tmp_path)
    monkeypatch.setattr(git_backport, "load_or_autodetect_config", lambda root: config)
    monkeypatch.setattr(git_backport.git, "is_git_repository", lambda root: True)
    monkeypatch.setattr(git_backport.git, "current_branch", lambda root: "main")
    monkeypatch.setattr(git_backport.git, "run", lambda cmd, cwd, *, dry_run, label: "")

    args = argparse.Namespace(
        target="demo", remote=None, branch=None, base_ref="--force", dry_run=False
    )
    monkeypatch.chdir(tmp_path)
    assert git_backport.cmd_backport_from_target(args) == 1
    assert "must not start with '-'" in capsys.readouterr().err


def test_backport_happy_path_lists_commits_and_prints_next_steps(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = _config_with_demo_target(tmp_path)
    monkeypatch.setattr(git_backport, "load_or_autodetect_config", lambda root: config)
    monkeypatch.setattr(git_backport.git, "is_git_repository", lambda root: True)
    monkeypatch.setattr(git_backport.git, "current_branch", lambda root: "main")

    fetch_commands: list[list[str]] = []
    monkeypatch.setattr(
        git_backport.git,
        "run",
        lambda cmd, cwd, *, dry_run, label: fetch_commands.append(cmd) or "",
    )
    monkeypatch.setattr(
        git_backport.git,
        "capture",
        lambda cmd, cwd: "def5678 fix docs\nabc1234 tweak workflow",
    )

    args = argparse.Namespace(target="demo", remote=None, branch=None, base_ref=None, dry_run=False)
    monkeypatch.chdir(tmp_path)
    assert git_backport.cmd_backport_from_target(args) == 0

    assert fetch_commands == [["git", "fetch", "mirror", "main"]]

    out = capsys.readouterr().out
    assert "def5678 fix docs" in out
    assert "abc1234 tweak workflow" in out
    assert "git checkout -b backport/demo main" in out
    # Cherry-pick order must be oldest-first (reversed from git log's newest-first).
    assert "git cherry-pick abc1234 def5678" in out


def test_backport_dry_run_skips_fetch_and_listing(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = _config_with_demo_target(tmp_path)
    monkeypatch.setattr(git_backport, "load_or_autodetect_config", lambda root: config)
    monkeypatch.setattr(git_backport.git, "is_git_repository", lambda root: True)
    monkeypatch.setattr(git_backport.git, "current_branch", lambda root: "main")

    run_calls: list[tuple[list[str], bool]] = []
    monkeypatch.setattr(
        git_backport.git,
        "run",
        lambda cmd, cwd, *, dry_run, label: run_calls.append((cmd, dry_run)) or "",
    )

    def _unexpected_capture(cmd: list[str], cwd: pathlib.Path) -> str:
        raise AssertionError("capture should not be called in dry-run mode")

    monkeypatch.setattr(git_backport.git, "capture", _unexpected_capture)

    args = argparse.Namespace(target="demo", remote=None, branch=None, base_ref=None, dry_run=True)
    monkeypatch.chdir(tmp_path)
    assert git_backport.cmd_backport_from_target(args) == 0
    assert run_calls == [(["git", "fetch", "mirror", "main"], True)]
    assert "[DRY RUN]" in capsys.readouterr().out


def test_backport_no_pending_commits_returns_friendly_message(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = _config_with_demo_target(tmp_path)
    monkeypatch.setattr(git_backport, "load_or_autodetect_config", lambda root: config)
    monkeypatch.setattr(git_backport.git, "is_git_repository", lambda root: True)
    monkeypatch.setattr(git_backport.git, "current_branch", lambda root: "main")
    monkeypatch.setattr(git_backport.git, "run", lambda cmd, cwd, *, dry_run, label: "")
    monkeypatch.setattr(git_backport.git, "capture", lambda cmd, cwd: "")

    args = argparse.Namespace(target="demo", remote=None, branch=None, base_ref=None, dry_run=False)
    monkeypatch.chdir(tmp_path)
    assert git_backport.cmd_backport_from_target(args) == 0
    assert "nothing to backport" in capsys.readouterr().out.lower()


def test_backport_remote_branch_base_ref_overrides(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config_with_demo_target(tmp_path)
    monkeypatch.setattr(git_backport, "load_or_autodetect_config", lambda root: config)
    monkeypatch.setattr(git_backport.git, "is_git_repository", lambda root: True)
    monkeypatch.setattr(git_backport.git, "current_branch", lambda root: "main")

    fetch_commands: list[list[str]] = []
    monkeypatch.setattr(
        git_backport.git,
        "run",
        lambda cmd, cwd, *, dry_run, label: fetch_commands.append(cmd) or "",
    )
    log_ranges: list[str] = []

    def _capture(cmd: list[str], cwd: pathlib.Path) -> str:
        log_ranges.append(cmd[2])
        return ""

    monkeypatch.setattr(git_backport.git, "capture", _capture)

    args = argparse.Namespace(
        target="demo",
        remote="override-remote",
        branch="override-branch",
        base_ref="origin/main",
        dry_run=False,
    )
    monkeypatch.chdir(tmp_path)
    assert git_backport.cmd_backport_from_target(args) == 0
    assert fetch_commands == [["git", "fetch", "override-remote", "override-branch"]]
    assert log_ranges == ["origin/main..FETCH_HEAD"]
