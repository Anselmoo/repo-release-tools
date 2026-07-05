from __future__ import annotations

import argparse
import contextlib
import pathlib

import pytest

from repo_release_tools.commands import git_sync
from repo_release_tools.workflow import git


def test_cmd_sync_requires_git_repository(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(git_sync.git, "is_git_repository", lambda cwd: False)
    args = argparse.Namespace(merge=False, dry_run=True)

    assert git_sync.cmd_sync(args) == 1

    captured = capsys.readouterr()
    assert "is not inside a Git work tree" in captured.err


def test_cmd_move_requires_git_repository(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(git_sync.git, "is_git_repository", lambda cwd: False)
    args = argparse.Namespace(target="feat/add-parser", create=False, dry_run=True)

    assert git_sync.cmd_move(args) == 1

    captured = capsys.readouterr()
    assert "is not inside a Git work tree" in captured.err


def test_cmd_sync_dry_run_stashes_before_rebase(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_sync.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_sync.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_sync.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(git_sync.git, "working_tree_clean", lambda cwd: False)
    monkeypatch.setattr(git_sync.git, "in_progress_operation", lambda cwd: None)
    monkeypatch.setattr(
        git_sync.git,
        "status_porcelain",
        lambda cwd: [" M src/repo_release_tools/cli.py"],
    )
    monkeypatch.setattr(git_sync.git, "ahead_behind", lambda cwd, ref: (2, 1))
    args = argparse.Namespace(merge=False, dry_run=True)

    assert git_sync.cmd_sync(args) == 0

    captured = capsys.readouterr()
    assert "git fetch --prune" in captured.out
    assert "git stash push -u -m rrt git sync auto-stash" in captured.out
    assert "git pull --rebase" in captured.out
    assert "git stash pop" in captured.out


def test_cmd_sync_rejects_unresolved_conflicts(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_sync.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_sync.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_sync.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(git_sync.git, "working_tree_clean", lambda cwd: False)
    monkeypatch.setattr(git_sync.git, "in_progress_operation", lambda cwd: None)
    monkeypatch.setattr(git_sync.git, "status_porcelain", lambda cwd: ["UU src/conflicted.py"])
    monkeypatch.setattr(
        git_sync.git,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError),
    )
    args = argparse.Namespace(merge=False, dry_run=True)

    assert git_sync.cmd_sync(args) == 1

    captured = capsys.readouterr()
    assert "unresolved merge conflicts" in captured.err
    assert "src/conflicted.py" in captured.err


def test_cmd_move_dry_run_stashes_before_checkout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_sync.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_sync.git, "current_branch", lambda cwd: "main")
    monkeypatch.setattr(git_sync.git, "working_tree_clean", lambda cwd: False)
    args = argparse.Namespace(target="feat/add-parser", create=False, dry_run=True)

    assert git_sync.cmd_move(args) == 0

    captured = capsys.readouterr()
    assert "git stash push -u -m rrt git move auto-stash" in captured.out
    assert "git checkout feat/add-parser" in captured.out
    assert "git stash pop" in captured.out


def test_cmd_rebootstrap_requires_confirmation(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    args = argparse.Namespace(yes_i_know_this_destroys_history=False)

    assert git_sync.cmd_rebootstrap(args) == 1

    captured = capsys.readouterr()
    assert "--yes-i-know-this-destroys-history" in captured.err


def test_cmd_rebootstrap_hard_init_dry_run_skips_snapshot_commit(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(git_sync.git, "remote_names", lambda cwd: [])
    monkeypatch.setattr(git_sync.git, "current_branch", lambda cwd: "main")
    args = argparse.Namespace(
        yes_i_know_this_destroys_history=True,
        allow_remote=False,
        hard_init=True,
        empty_first=False,
        branch=None,
        message=None,
        empty_message=git_sync.DEFAULT_REBOOTSTRAP_EMPTY_MESSAGE,
        dry_run=True,
    )

    assert git_sync.cmd_rebootstrap(args) == 0

    captured = capsys.readouterr()
    assert "empty hard-init" in captured.out
    assert "git commit --allow-empty -m chore: bootstrap repository" in captured.out
    assert "git add ." not in captured.out


def test_cmd_rebootstrap_rejects_hard_init_with_empty_first(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    args = argparse.Namespace(
        yes_i_know_this_destroys_history=True,
        allow_remote=False,
        hard_init=True,
        empty_first=True,
        branch=None,
        message=None,
        empty_message=git_sync.DEFAULT_REBOOTSTRAP_EMPTY_MESSAGE,
        dry_run=True,
    )

    assert git_sync.cmd_rebootstrap(args) == 1

    captured = capsys.readouterr()
    assert "either --hard-init or --empty-first" in captured.err


def test_cmd_rebootstrap_hard_init_runs_empty_commit_only(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(git_sync.git, "remote_names", lambda cwd: [])
    monkeypatch.setattr(git_sync.git, "current_branch", lambda cwd: "main")
    monkeypatch.setattr(git_sync.git, "git_dir", lambda cwd: tmp_path / ".git")
    commands: list[list[str]] = []
    moved: list[tuple[str, str]] = []

    def fake_run(cmd: list[str], cwd: pathlib.Path, *, dry_run: bool, label: str) -> str:
        commands.append(cmd)
        return ""

    def fake_move(src: str, dst: str) -> None:
        moved.append((src, dst))

    monkeypatch.setattr(git_sync.git, "run", fake_run)
    monkeypatch.setattr(git_sync.shutil, "move", fake_move)
    args = argparse.Namespace(
        yes_i_know_this_destroys_history=True,
        allow_remote=False,
        hard_init=True,
        empty_first=False,
        branch=None,
        message=None,
        empty_message=git_sync.DEFAULT_REBOOTSTRAP_EMPTY_MESSAGE,
        dry_run=False,
    )

    assert git_sync.cmd_rebootstrap(args) == 0
    assert moved and moved[0][0] == str(tmp_path / ".git")
    assert commands == [
        ["git", "init", "-b", "main"],
        ["git", "commit", "--allow-empty", "-m", git_sync.DEFAULT_REBOOTSTRAP_EMPTY_MESSAGE],
    ]


def test_classify_status_line_covers_all_status_kinds() -> None:
    assert git.classify_status_line("?? docs/new.md") == ("untracked", "docs/new.md")
    assert git.classify_status_line("UU src/conflict.py") == ("conflict", "src/conflict.py")
    assert git.classify_status_line("R  old.py -> new.py") == ("renamed", "old.py -> new.py")
    assert git.classify_status_line("A  src/new.py") == ("added", "src/new.py")
    assert git.classify_status_line("D  src/old.py") == ("removed", "src/old.py")


def test_cmd_sync_requires_upstream_branch(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_sync.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_sync.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_sync.git, "upstream_branch", lambda cwd: None)

    assert git_sync.cmd_sync(argparse.Namespace(merge=False, dry_run=False)) == 1
    assert "No upstream branch is configured" in capsys.readouterr().err


def test_cmd_sync_reports_status_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_sync.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_sync.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_sync.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(git_sync.git, "working_tree_clean", lambda cwd: True)
    monkeypatch.setattr(
        git_sync.git,
        "status_porcelain",
        lambda cwd: (_ for _ in ()).throw(RuntimeError("git status --short failed (exit 128)")),
    )

    assert git_sync.cmd_sync(argparse.Namespace(merge=False, dry_run=False)) == 1
    assert "git status --short failed" in capsys.readouterr().err


def test_cmd_sync_rejects_in_progress_operation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_sync.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_sync.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_sync.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(git_sync.git, "working_tree_clean", lambda cwd: True)
    monkeypatch.setattr(git_sync.git, "status_porcelain", lambda cwd: [])
    monkeypatch.setattr(git_sync.git, "in_progress_operation", lambda cwd: "merge")

    assert git_sync.cmd_sync(argparse.Namespace(merge=False, dry_run=False)) == 1
    assert "Cannot sync while a merge is in progress" in capsys.readouterr().err


def test_cmd_sync_warns_when_pull_fails_after_auto_stash(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_sync.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_sync.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_sync.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(git_sync.git, "working_tree_clean", lambda cwd: False)
    monkeypatch.setattr(git_sync.git, "status_porcelain", lambda cwd: [" M src/file.py"])
    monkeypatch.setattr(git_sync.git, "in_progress_operation", lambda cwd: None)
    monkeypatch.setattr(git_sync.git, "ahead_behind", lambda cwd, ref: (1, 0))
    monkeypatch.setattr(git_sync, "spinner_lines", lambda *a, **k: contextlib.nullcontext())

    def fake_run(cmd: list[str], cwd: pathlib.Path, *, dry_run: bool, label: str) -> str:
        if cmd[:2] == ["git", "pull"]:
            raise RuntimeError("pull failed")
        return ""

    monkeypatch.setattr(git_sync.git, "run", fake_run)

    with pytest.raises(RuntimeError, match="pull failed"):
        git_sync.cmd_sync(argparse.Namespace(merge=True, dry_run=False))

    assert "auto-stash remains on the stash stack" in capsys.readouterr().err


def test_cmd_move_warns_when_checkout_fails_after_stash(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_sync.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_sync.git, "current_branch", lambda cwd: "main")
    monkeypatch.setattr(git_sync.git, "working_tree_clean", lambda cwd: False)

    def fake_run(cmd: list[str], cwd: pathlib.Path, *, dry_run: bool, label: str) -> str:
        if cmd[:2] == ["git", "checkout"]:
            raise RuntimeError("checkout failed")
        return ""

    monkeypatch.setattr(git_sync.git, "run", fake_run)

    with pytest.raises(RuntimeError, match="checkout failed"):
        git_sync.cmd_move(argparse.Namespace(target="feat/add-parser", create=False, dry_run=False))

    assert "auto-stash remains on the stash stack" in capsys.readouterr().err


def test_cmd_undo_safe_runs_soft_reset_in_dry_run(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr(
        git_sync.git,
        "run",
        lambda cmd, cwd, *, dry_run, label: commands.append(cmd) or "",
    )

    result = git_sync.cmd_undo_safe(
        argparse.Namespace(target="HEAD~2", keep_staged=True, dry_run=True),
    )

    assert result == 0
    assert commands == [["git", "reset", "--soft", "HEAD~2"]]
    assert "dry-run" in capsys.readouterr().out


def test_cmd_undo_safe_runs_mixed_reset(monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr(
        git_sync.git,
        "run",
        lambda cmd, cwd, *, dry_run, label: commands.append(cmd) or "",
    )

    assert (
        git_sync.cmd_undo_safe(
            argparse.Namespace(target="HEAD~1", keep_staged=False, dry_run=False)
        )
        == 0
    )
    assert commands == [["git", "reset", "--mixed", "HEAD~1"]]


def test_cmd_rebootstrap_rejects_missing_git_dir(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(git_sync.git, "git_dir", lambda cwd: None)
    args = argparse.Namespace(yes_i_know_this_destroys_history=True)

    assert git_sync.cmd_rebootstrap(args) == 1
    assert "does not look like a Git repository" in capsys.readouterr().err


def test_cmd_rebootstrap_rejects_remote_guard(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(git_sync.git, "remote_names", lambda cwd: ["origin"])
    args = argparse.Namespace(
        yes_i_know_this_destroys_history=True,
        allow_remote=False,
        hard_init=False,
        empty_first=False,
        branch=None,
        message=None,
        empty_message=git_sync.DEFAULT_REBOOTSTRAP_EMPTY_MESSAGE,
        dry_run=True,
    )

    assert git_sync.cmd_rebootstrap(args) == 1
    assert "Refusing to rebootstrap a repository with configured remotes" in capsys.readouterr().err


def test_cmd_rebootstrap_empty_first_dry_run(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(git_sync.git, "remote_names", lambda cwd: [])
    monkeypatch.setattr(git_sync.git, "current_branch", lambda cwd: "main")
    commands: list[list[str]] = []
    monkeypatch.setattr(
        git_sync.git,
        "run",
        lambda cmd, cwd, *, dry_run, label: commands.append(cmd) or "",
    )
    args = argparse.Namespace(
        yes_i_know_this_destroys_history=True,
        allow_remote=False,
        hard_init=False,
        empty_first=True,
        branch=None,
        message=None,
        empty_message="chore: empty bootstrap",
        dry_run=True,
    )

    assert git_sync.cmd_rebootstrap(args) == 0
    assert commands == [
        ["git", "init", "-b", "main"],
        ["git", "commit", "--allow-empty", "-m", "chore: empty bootstrap"],
        ["git", "add", "."],
        ["git", "commit", "-m", git_sync.DEFAULT_REBOOTSTRAP_MESSAGE],
    ]
    assert "dry-run" in capsys.readouterr().out


def test_cmd_rebootstrap_empty_first_non_dry_run(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(git_sync.git, "git_dir", lambda cwd: tmp_path / ".git")
    monkeypatch.setattr(git_sync.git, "remote_names", lambda cwd: [])
    monkeypatch.setattr(git_sync.git, "current_branch", lambda cwd: "main")
    monkeypatch.setattr(git_sync.shutil, "move", lambda src, dst: None)
    commands: list[list[str]] = []
    monkeypatch.setattr(
        git_sync.git,
        "run",
        lambda cmd, cwd, *, dry_run, label: commands.append(cmd) or "",
    )
    args = argparse.Namespace(
        yes_i_know_this_destroys_history=True,
        allow_remote=False,
        hard_init=False,
        empty_first=True,
        branch=None,
        message=None,
        empty_message="chore: empty bootstrap",
        dry_run=False,
    )

    assert git_sync.cmd_rebootstrap(args) == 0
    assert commands == [
        ["git", "init", "-b", "main"],
        ["git", "commit", "--allow-empty", "-m", "chore: empty bootstrap"],
        ["git", "add", "."],
        ["git", "commit", "-m", git_sync.DEFAULT_REBOOTSTRAP_MESSAGE],
    ]


def test_cmd_rebootstrap_reinitializes_snapshot_history(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(git_sync.git, "git_dir", lambda cwd: tmp_path / ".git")
    monkeypatch.setattr(git_sync.git, "remote_names", lambda cwd: [])
    monkeypatch.setattr(git_sync.git, "current_branch", lambda cwd: "main")
    moved: list[tuple[str, str]] = []
    commands: list[list[str]] = []
    monkeypatch.setattr(git_sync.shutil, "move", lambda src, dst: moved.append((src, dst)))
    monkeypatch.setattr(
        git_sync.git,
        "run",
        lambda cmd, cwd, *, dry_run, label: commands.append(cmd) or "",
    )
    args = argparse.Namespace(
        yes_i_know_this_destroys_history=True,
        allow_remote=False,
        hard_init=False,
        empty_first=False,
        branch=None,
        message=None,
        empty_message=git_sync.DEFAULT_REBOOTSTRAP_EMPTY_MESSAGE,
        dry_run=False,
    )

    assert git_sync.cmd_rebootstrap(args) == 0
    assert moved
    assert commands == [
        ["git", "init", "-b", "main"],
        ["git", "add", "."],
        ["git", "commit", "-m", git_sync.DEFAULT_REBOOTSTRAP_MESSAGE],
    ]
    assert "Repository history reinitialized" in capsys.readouterr().out


def test_cmd_rebootstrap_reports_runtime_failure_and_backup(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(git_sync.git, "git_dir", lambda cwd: tmp_path / ".git")
    monkeypatch.setattr(git_sync.git, "remote_names", lambda cwd: [])
    monkeypatch.setattr(git_sync.git, "current_branch", lambda cwd: "main")
    monkeypatch.setattr(git_sync.shutil, "move", lambda src, dst: None)
    monkeypatch.setattr(
        git_sync.git,
        "run",
        lambda cmd, cwd, *, dry_run, label: (_ for _ in ()).throw(RuntimeError("git init failed")),
    )
    args = argparse.Namespace(
        yes_i_know_this_destroys_history=True,
        allow_remote=False,
        hard_init=False,
        empty_first=False,
        branch=None,
        message=None,
        empty_message=git_sync.DEFAULT_REBOOTSTRAP_EMPTY_MESSAGE,
        dry_run=False,
    )

    assert git_sync.cmd_rebootstrap(args) == 1
    assert "Original git data is backed up" in capsys.readouterr().err


def test_cmd_purge_cache_dry_run_runs_maintenance_commands(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_sync.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_sync.git, "working_tree_clean", lambda cwd: True)
    commands: list[list[str]] = []
    monkeypatch.setattr(
        git_sync.git,
        "run",
        lambda cmd, cwd, *, dry_run, label: commands.append(cmd) or "",
    )

    assert git_sync.cmd_purge_cache(argparse.Namespace(dry_run=True)) == 0
    assert commands == [
        ["git", "reflog", "expire", "--expire=now", "--all"],
        ["git", "gc", "--prune=now"],
    ]
    assert "Purge cache" in capsys.readouterr().out


def test_cmd_purge_cache_rejects_non_git_repo(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(git_sync.git, "is_git_repository", lambda cwd: False)

    assert git_sync.cmd_purge_cache(argparse.Namespace(dry_run=False)) == 1
    assert "not inside a Git work tree" in capsys.readouterr().err


def test_cmd_purge_cache_warns_when_working_tree_is_dirty(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_sync.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_sync.git, "working_tree_clean", lambda cwd: False)
    monkeypatch.setattr(git_sync.git, "run", lambda cmd, cwd, *, dry_run, label: "")

    assert git_sync.cmd_purge_cache(argparse.Namespace(dry_run=True)) == 0
    assert "Working tree changes are preserved" in capsys.readouterr().out


def test_register_adds_git_purge_cache_parser() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    git_sub = subparsers.add_parser("git")
    inner = git_sub.add_subparsers(dest="git_command", parser_class=type(git_sub))
    git_sync.register_sync(inner)

    args = parser.parse_args(["git", "purge-cache"])

    assert args.command == "git"
    assert args.git_command == "purge-cache"
    assert args.handler.__name__ == "cmd_purge_cache"


def test_cmd_sync_truncates_conflicts(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_sync.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_sync.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_sync.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(git_sync.git, "working_tree_clean", lambda cwd: False)
    monkeypatch.setattr(git_sync.git, "in_progress_operation", lambda cwd: None)
    monkeypatch.setattr(
        git_sync.git,
        "status_porcelain",
        lambda cwd: [f"UU sync-{i}.py" for i in range(16)],
    )
    monkeypatch.setattr(
        git_sync.git,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("git.run should not be called"),
        ),
    )

    assert git_sync.cmd_sync(argparse.Namespace(merge=False, dry_run=True)) == 1
    assert "…and 1 more" in capsys.readouterr().err
