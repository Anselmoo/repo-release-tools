from __future__ import annotations

import argparse
import contextlib

import pytest

from repo_release_tools.commands import git_cmd
from repo_release_tools import git


def test_infer_commit_type_from_branch() -> None:
    assert git_cmd.infer_commit_type("feat/add-parser") == "feat"
    assert git_cmd.infer_commit_type("main") is None
    assert git_cmd.infer_commit_type("copilot/add-parser") is None
    assert git_cmd.infer_commit_type("release/v1.2.3") is None


def test_cmd_commit_dry_run_uses_branch_type(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "feat/add-parser")
    args = argparse.Namespace(
        description=["handle", "empty", "config"],
        type=None,
        scope=None,
        breaking=False,
        dry_run=True,
    )

    assert git_cmd.cmd_commit(args) == 0

    captured = capsys.readouterr()
    assert "feat: handle empty config" in captured.out
    assert "[dry-run] complete" in captured.out


def test_cmd_status_renders_summary_and_entries(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(
        git_cmd.git,
        "status_porcelain",
        lambda cwd: [" M src/repo_release_tools/cli.py", "?? docs/git-magic.md"],
    )
    monkeypatch.setattr(git_cmd.git, "ahead_behind", lambda cwd, ref: (2, 1))
    args = argparse.Namespace()

    assert git_cmd.cmd_status(args) == 0

    captured = capsys.readouterr()
    assert "Git status" in captured.out
    assert "feat/add-parser" in captured.out
    assert "src/repo_release_tools/cli.py" in captured.out
    assert "docs/git-magic.md" in captured.out


def test_cmd_status_renders_clean_tree(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "main")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: "origin/main")
    monkeypatch.setattr(git_cmd.git, "status_porcelain", lambda cwd: [])
    monkeypatch.setattr(git_cmd.git, "ahead_behind", lambda cwd, ref: (0, 0))
    args = argparse.Namespace()

    assert git_cmd.cmd_status(args) == 0

    captured = capsys.readouterr()
    assert "Working tree is clean." in captured.out


def test_cmd_status_reports_status_failure(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "main")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: "origin/main")
    monkeypatch.setattr(
        git_cmd.git,
        "status_porcelain",
        lambda cwd: (_ for _ in ()).throw(RuntimeError("git status --short failed (exit 128)")),
    )
    args = argparse.Namespace()

    assert git_cmd.cmd_status(args) == 1

    captured = capsys.readouterr()
    assert "git status --short failed" in captured.err


def test_cmd_log_renders_compact_history(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(
        git_cmd.git,
        "capture",
        lambda cmd, cwd: (
            "abc1234\tfeat: add parser\tHEAD -> feat/add-parser, origin/feat/add-parser\n"
            "def5678\tfix: handle empty input\t"
        ),
    )
    args = argparse.Namespace(limit=2)

    assert git_cmd.cmd_log(args) == 0

    captured = capsys.readouterr()
    assert "Git log" in captured.out
    assert "abc1234" in captured.out
    assert "feat: add parser" in captured.out
    assert "origin/feat/add-parser" in captured.out


def test_cmd_doctor_reports_failures(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: None)
    monkeypatch.setattr(git_cmd.git, "in_progress_operation", lambda cwd: None)
    monkeypatch.setattr(
        git_cmd.git, "status_porcelain", lambda cwd: [" M src/repo_release_tools/cli.py"]
    )
    monkeypatch.setattr(git_cmd.git, "ahead_behind", lambda cwd, ref: (0, 0))

    def fake_capture(cmd, cwd) -> str:
        if cmd[:4] == ["git", "log", "-1", "--pretty=%s"]:
            return "update stuff"
        if cmd[:5] == ["git", "diff-tree", "--no-commit-id", "--name-only", "--root"]:
            return "src/repo_release_tools/cli.py"
        raise AssertionError(cmd)

    monkeypatch.setattr(git_cmd.git, "capture", fake_capture)
    args = argparse.Namespace(changelog_file="CHANGELOG.md")

    assert git_cmd.cmd_doctor(args) == 1

    captured = capsys.readouterr()
    assert "Git doctor" in captured.out
    assert "No upstream branch configured." in captured.out
    assert "Working tree has uncommitted changes." in captured.out
    assert "update stuff" in captured.out


def test_cmd_doctor_reports_success(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "in_progress_operation", lambda cwd: None)
    monkeypatch.setattr(git_cmd.git, "status_porcelain", lambda cwd: [])
    monkeypatch.setattr(git_cmd.git, "ahead_behind", lambda cwd, ref: (2, 0))

    def fake_capture(cmd, cwd) -> str:
        if cmd[:4] == ["git", "log", "-1", "--pretty=%s"]:
            return "feat: add parser"
        if cmd[:5] == ["git", "diff-tree", "--no-commit-id", "--name-only", "--root"]:
            return "CHANGELOG.md\nsrc/repo_release_tools/cli.py"
        raise AssertionError(cmd)

    monkeypatch.setattr(git_cmd.git, "capture", fake_capture)
    args = argparse.Namespace(changelog_file="CHANGELOG.md")

    assert git_cmd.cmd_doctor(args) == 0

    captured = capsys.readouterr()
    assert "Doctor checks passed." in captured.out


def test_cmd_doctor_uses_commit_subject_for_changelog_risk(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "in_progress_operation", lambda cwd: None)
    monkeypatch.setattr(git_cmd.git, "status_porcelain", lambda cwd: [])
    monkeypatch.setattr(git_cmd.git, "ahead_behind", lambda cwd, ref: (0, 0))

    def fake_capture(cmd, cwd) -> str:
        if cmd[:4] == ["git", "log", "-1", "--pretty=%s"]:
            return "chore: update docs tooling"
        if cmd[:5] == ["git", "diff-tree", "--no-commit-id", "--name-only", "--root"]:
            raise AssertionError("changelog diff should not be queried for chore commits")
        raise AssertionError(cmd)

    monkeypatch.setattr(git_cmd.git, "capture", fake_capture)
    args = argparse.Namespace(changelog_file="CHANGELOG.md")

    assert git_cmd.cmd_doctor(args) == 0

    captured = capsys.readouterr()
    assert "Doctor checks passed." in captured.out


def test_cmd_doctor_reports_conflicts_and_sync_need(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "in_progress_operation", lambda cwd: "rebase")
    monkeypatch.setattr(
        git_cmd.git,
        "status_porcelain",
        lambda cwd: ["UU src/conflicted.py", " M src/repo_release_tools/cli.py"],
    )
    monkeypatch.setattr(git_cmd.git, "ahead_behind", lambda cwd, ref: (2, 3))

    def fake_capture(cmd, cwd) -> str:
        if cmd[:4] == ["git", "log", "-1", "--pretty=%s"]:
            return "feat: add parser"
        if cmd[:5] == ["git", "diff-tree", "--no-commit-id", "--name-only", "--root"]:
            return "CHANGELOG.md\nsrc/repo_release_tools/cli.py"
        raise AssertionError(cmd)

    monkeypatch.setattr(git_cmd.git, "capture", fake_capture)
    args = argparse.Namespace(changelog_file="CHANGELOG.md")

    assert git_cmd.cmd_doctor(args) == 1

    captured = capsys.readouterr()
    assert "Rebase is in progress" in captured.out
    assert "Found 1 conflicted path" in captured.out
    assert "has diverged from origin/feat/add-parser" in captured.out
    assert "src/conflicted.py" in captured.out


def test_cmd_sync_requires_git_repository(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: False)
    args = argparse.Namespace(merge=False, dry_run=True)

    assert git_cmd.cmd_sync(args) == 1

    captured = capsys.readouterr()
    assert "is not inside a Git work tree" in captured.err


def test_cmd_move_requires_git_repository(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: False)
    args = argparse.Namespace(target="feat/add-parser", create=False, dry_run=True)

    assert git_cmd.cmd_move(args) == 1

    captured = capsys.readouterr()
    assert "is not inside a Git work tree" in captured.err


def test_cmd_sync_dry_run_stashes_before_rebase(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "working_tree_clean", lambda cwd: False)
    monkeypatch.setattr(git_cmd.git, "in_progress_operation", lambda cwd: None)
    monkeypatch.setattr(
        git_cmd.git, "status_porcelain", lambda cwd: [" M src/repo_release_tools/cli.py"]
    )
    monkeypatch.setattr(git_cmd.git, "ahead_behind", lambda cwd, ref: (2, 1))
    args = argparse.Namespace(merge=False, dry_run=True)

    assert git_cmd.cmd_sync(args) == 0

    captured = capsys.readouterr()
    assert "git fetch --prune" in captured.out
    assert "git stash push -u -m rrt git sync auto-stash" in captured.out
    assert "git pull --rebase" in captured.out
    assert "git stash pop" in captured.out


def test_cmd_sync_rejects_unresolved_conflicts(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "working_tree_clean", lambda cwd: False)
    monkeypatch.setattr(git_cmd.git, "in_progress_operation", lambda cwd: None)
    monkeypatch.setattr(git_cmd.git, "status_porcelain", lambda cwd: ["UU src/conflicted.py"])
    monkeypatch.setattr(
        git_cmd.git, "run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError)
    )
    args = argparse.Namespace(merge=False, dry_run=True)

    assert git_cmd.cmd_sync(args) == 1

    captured = capsys.readouterr()
    assert "unresolved merge conflicts" in captured.err
    assert "src/conflicted.py" in captured.err


def test_cmd_sync_status_reports_diverged_rebase_conflicts(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "ref_exists", lambda cwd, ref: True)
    monkeypatch.setattr(git_cmd.git, "in_progress_operation", lambda cwd: "rebase")
    monkeypatch.setattr(
        git_cmd.git,
        "status_porcelain",
        lambda cwd: ["UU src/conflicted.py", " M src/repo_release_tools/cli.py"],
    )
    monkeypatch.setattr(git_cmd.git, "ahead_behind", lambda cwd, ref: (2, 3))
    args = argparse.Namespace(base_ref=None)

    assert git_cmd.cmd_sync_status(args) == 1

    captured = capsys.readouterr()
    assert "Sync status" in captured.out
    assert "Rebase is in progress" in captured.out
    assert "Found 1 conflicted path" in captured.out
    assert "Rebase or merge is needed" in captured.out
    assert "src/conflicted.py" in captured.out


def test_cmd_sync_status_reports_clean_branch(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "main")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: "origin/main")
    monkeypatch.setattr(git_cmd.git, "ref_exists", lambda cwd, ref: True)
    monkeypatch.setattr(git_cmd.git, "in_progress_operation", lambda cwd: None)
    monkeypatch.setattr(git_cmd.git, "status_porcelain", lambda cwd: [])
    monkeypatch.setattr(git_cmd.git, "ahead_behind", lambda cwd, ref: (0, 0))
    args = argparse.Namespace(base_ref=None)

    assert git_cmd.cmd_sync_status(args) == 0

    captured = capsys.readouterr()
    assert "Sync analysis passed." in captured.out
    assert "matches origin/main" in captured.out


def test_cmd_sync_status_requires_base_ref_when_missing_upstream(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: None)
    monkeypatch.setattr(git_cmd.git, "in_progress_operation", lambda cwd: None)
    monkeypatch.setattr(git_cmd.git, "status_porcelain", lambda cwd: [])
    args = argparse.Namespace(base_ref=None)

    assert git_cmd.cmd_sync_status(args) == 1

    captured = capsys.readouterr()
    assert "No upstream branch is configured" in captured.out


def test_cmd_sync_status_rejects_missing_base_ref(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: None)
    monkeypatch.setattr(git_cmd.git, "ref_exists", lambda cwd, ref: False)
    args = argparse.Namespace(base_ref="origin/missing")

    assert git_cmd.cmd_sync_status(args) == 1

    captured = capsys.readouterr()
    assert "does not exist" in captured.err


def test_cmd_check_dirty_tree_reports_status_lines(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "working_tree_clean", lambda cwd: False)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(
        git_cmd.git,
        "status_porcelain",
        lambda cwd: [" M src/repo_release_tools/cli.py", "?? docs/git-magic.md"],
    )
    monkeypatch.setattr(git_cmd.git, "ahead_behind", lambda cwd, ref: (2, 1))
    args = argparse.Namespace()

    assert git_cmd.cmd_check_dirty_tree(args) == 1

    captured = capsys.readouterr()
    assert "Working tree has uncommitted changes." in captured.err
    assert "feat/add-parser" in captured.err
    assert "src/repo_release_tools/cli.py" in captured.err
    assert "docs/git-magic.md" in captured.err


def test_cmd_check_dirty_tree_reports_status_failure(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "working_tree_clean", lambda cwd: False)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(
        git_cmd.git,
        "status_porcelain",
        lambda cwd: (_ for _ in ()).throw(RuntimeError("git status --short failed (exit 128)")),
    )
    args = argparse.Namespace()

    assert git_cmd.cmd_check_dirty_tree(args) == 1

    captured = capsys.readouterr()
    assert "git status --short failed" in captured.err


def test_cmd_move_dry_run_stashes_before_checkout(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "main")
    monkeypatch.setattr(git_cmd.git, "working_tree_clean", lambda cwd: False)
    args = argparse.Namespace(target="feat/add-parser", create=False, dry_run=True)

    assert git_cmd.cmd_move(args) == 0

    captured = capsys.readouterr()
    assert "git stash push -u -m rrt git move auto-stash" in captured.out
    assert "git checkout feat/add-parser" in captured.out
    assert "git stash pop" in captured.out


def test_cmd_rebootstrap_requires_confirmation(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    args = argparse.Namespace(yes_i_know_this_destroys_history=False)

    assert git_cmd.cmd_rebootstrap(args) == 1

    captured = capsys.readouterr()
    assert "--yes-i-know-this-destroys-history" in captured.err


def test_cmd_rebootstrap_hard_init_dry_run_skips_snapshot_commit(
    tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(git_cmd.git, "remote_names", lambda cwd: [])
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "main")
    args = argparse.Namespace(
        yes_i_know_this_destroys_history=True,
        allow_remote=False,
        hard_init=True,
        empty_first=False,
        branch=None,
        message=None,
        empty_message=git_cmd.DEFAULT_REBOOTSTRAP_EMPTY_MESSAGE,
        dry_run=True,
    )

    assert git_cmd.cmd_rebootstrap(args) == 0

    captured = capsys.readouterr()
    assert "empty hard-init" in captured.out
    assert "git commit --allow-empty -m chore: bootstrap repository" in captured.out
    assert "git add ." not in captured.out


def test_cmd_rebootstrap_rejects_hard_init_with_empty_first(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    args = argparse.Namespace(
        yes_i_know_this_destroys_history=True,
        allow_remote=False,
        hard_init=True,
        empty_first=True,
        branch=None,
        message=None,
        empty_message=git_cmd.DEFAULT_REBOOTSTRAP_EMPTY_MESSAGE,
        dry_run=True,
    )

    assert git_cmd.cmd_rebootstrap(args) == 1

    captured = capsys.readouterr()
    assert "either --hard-init or --empty-first" in captured.err


def test_cmd_rebootstrap_hard_init_runs_empty_commit_only(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(git_cmd.git, "remote_names", lambda cwd: [])
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "main")
    monkeypatch.setattr(git_cmd.git, "git_dir", lambda cwd: tmp_path / ".git")
    commands: list[list[str]] = []
    moved: list[tuple[str, str]] = []

    def fake_run(cmd, cwd, *, dry_run, label) -> str:
        commands.append(cmd)
        return ""

    def fake_move(src: str, dst: str) -> None:
        moved.append((src, dst))

    monkeypatch.setattr(git_cmd.git, "run", fake_run)
    monkeypatch.setattr(git_cmd.shutil, "move", fake_move)
    args = argparse.Namespace(
        yes_i_know_this_destroys_history=True,
        allow_remote=False,
        hard_init=True,
        empty_first=False,
        branch=None,
        message=None,
        empty_message=git_cmd.DEFAULT_REBOOTSTRAP_EMPTY_MESSAGE,
        dry_run=False,
    )

    assert git_cmd.cmd_rebootstrap(args) == 0
    assert moved and moved[0][0] == str(tmp_path / ".git")
    assert commands == [
        ["git", "init", "-b", "main"],
        ["git", "commit", "--allow-empty", "-m", git_cmd.DEFAULT_REBOOTSTRAP_EMPTY_MESSAGE],
    ]


def test_parse_diff_line_added() -> None:
    kind, text, lineno = git_cmd._parse_diff_line("+hello world")
    assert kind == "added"
    assert text == "hello world"
    assert lineno is None


def test_parse_diff_line_removed() -> None:
    kind, text, lineno = git_cmd._parse_diff_line("-goodbye")
    assert kind == "removed"
    assert text == "goodbye"
    assert lineno is None


def test_parse_diff_line_unchanged_context() -> None:
    kind, text, lineno = git_cmd._parse_diff_line(" context line")
    assert kind == "unchanged"
    assert lineno is None


def test_parse_diff_line_hunk_header() -> None:
    kind, text, lineno = git_cmd._parse_diff_line("@@ -10,4 +20,6 @@ def foo():")
    assert kind == "unchanged"
    assert lineno == 20


def test_parse_diff_line_file_headers() -> None:
    for prefix in ("+++", "---"):
        kind, _, lineno = git_cmd._parse_diff_line(f"{prefix} a/file.py")
        assert kind == "unchanged"
        assert lineno is None


def test_cmd_diff_not_git_repo(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda _: False)
    args = argparse.Namespace(staged=False, against=None)

    assert git_cmd.cmd_diff(args) == 1
    assert tmp_path.name in capsys.readouterr().err


def test_cmd_diff_no_changes(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda _: True)
    monkeypatch.setattr(git_cmd.git, "capture_checked", lambda cmd, cwd: "")
    args = argparse.Namespace(staged=False, against=None)

    assert git_cmd.cmd_diff(args) == 0
    assert "No diff" in capsys.readouterr().out


def test_cmd_diff_renders_added_and_removed(monkeypatch, capsys) -> None:
    diff_output = (
        "diff --git a/foo.py b/foo.py\n"
        "index abc..def 100644\n"
        "--- a/foo.py\n"
        "+++ b/foo.py\n"
        "@@ -1,2 +1,3 @@\n"
        " unchanged\n"
        "-removed line\n"
        "+added line\n"
    )
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda _: True)
    monkeypatch.setattr(git_cmd.git, "capture_checked", lambda cmd, cwd: diff_output)
    args = argparse.Namespace(staged=False, against=None)

    rc = git_cmd.cmd_diff(args)
    captured = capsys.readouterr().out

    assert rc == 0
    assert "foo.py" in captured


def test_cmd_diff_staged_flag(monkeypatch) -> None:
    captured_cmd = {}
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda _: True)

    def fake_capture(cmd, cwd) -> str:
        captured_cmd["cmd"] = cmd
        return ""

    monkeypatch.setattr(git_cmd.git, "capture_checked", fake_capture)
    args = argparse.Namespace(staged=True, against=None)
    git_cmd.cmd_diff(args)
    assert "--staged" in captured_cmd["cmd"]


def test_cmd_diff_against_ref(monkeypatch) -> None:
    captured_cmd = {}
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda _: True)

    def fake_capture(cmd, cwd) -> str:
        captured_cmd["cmd"] = cmd
        return ""

    monkeypatch.setattr(git_cmd.git, "capture_checked", fake_capture)
    args = argparse.Namespace(staged=False, against="HEAD~2")
    git_cmd.cmd_diff(args)
    assert "HEAD~2" in captured_cmd["cmd"]


def test_cmd_diff_reports_invalid_ref(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda _: True)
    monkeypatch.setattr(
        git_cmd.git,
        "capture_checked",
        lambda cmd, cwd: (_ for _ in ()).throw(
            RuntimeError("git diff --unified=3 badref failed (exit 128)")
        ),
    )
    args = argparse.Namespace(staged=False, against="badref")

    assert git_cmd.cmd_diff(args) == 1

    captured = capsys.readouterr()
    assert "badref" in captured.err
    assert "No diff to show" not in captured.out


def test_cmd_diff_handles_deleted_file_headers(monkeypatch, capsys) -> None:
    diff_output = (
        "diff --git a/deleted.txt b/deleted.txt\n"
        "deleted file mode 100644\n"
        "index abcdef0..0000000 100644\n"
        "--- a/deleted.txt\n"
        "+++ /dev/null\n"
        "@@ -1 +0,0 @@\n"
        "-removed line\n"
    )
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda _: True)
    monkeypatch.setattr(git_cmd.git, "capture_checked", lambda cmd, cwd: diff_output)
    args = argparse.Namespace(staged=False, against=None)

    assert git_cmd.cmd_diff(args) == 0

    captured = capsys.readouterr().out
    assert "deleted.txt" in captured
    assert "removed line" in captured


def test_commit_subject_render_includes_scope_and_breaking_marker() -> None:
    subject = git_cmd.CommitSubject(
        type="feat", description="ship parser", scope="cli", breaking=True
    )

    assert subject.render() == "feat(cli)!: ship parser"


def test_normalize_commit_subject_type_accepts_and_rejects_values() -> None:
    assert git_cmd.normalize_commit_subject_type("FIX") == "fix"
    assert git_cmd.infer_commit_type("wizard/add-parser") is None

    with pytest.raises(argparse.ArgumentTypeError, match="invalid commit type"):
        git_cmd.normalize_commit_subject_type("wizard")


def test_resolve_commit_subject_requires_explicit_type_for_uninferable_branch(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "main")
    args = argparse.Namespace(description=["ship", "it"], type=None, scope=None, breaking=False)

    with pytest.raises(ValueError, match="Use --type explicitly"):
        git_cmd.resolve_commit_subject(args, tmp_path)


def test_classify_status_line_covers_all_status_kinds() -> None:
    assert git.classify_status_line("?? docs/new.md") == ("untracked", "docs/new.md")
    assert git.classify_status_line("UU src/conflict.py") == ("conflict", "src/conflict.py")
    assert git.classify_status_line("R  old.py -> new.py") == ("renamed", "old.py -> new.py")
    assert git.classify_status_line("A  src/new.py") == ("added", "src/new.py")
    assert git.classify_status_line("D  src/old.py") == ("removed", "src/old.py")


def test_describe_sync_relation_and_sync_problem_cover_remaining_states() -> None:
    assert (
        git_cmd.describe_sync_relation(ahead=0, behind=2, base_ref="origin/main") == "behind base"
    )
    assert git_cmd.describe_sync_relation(ahead=1, behind=2, base_ref="origin/main") == "diverged"
    assert (
        git_cmd.sync_problem("feat/add-parser", base_ref="origin/main", ahead=0, behind=2)
        == "Branch 'feat/add-parser' is behind origin/main by 2 commit(s). Sync is needed."
    )


def test_cmd_status_requires_git_repository(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: False)

    assert git_cmd.cmd_status(argparse.Namespace()) == 1
    assert "is not inside a Git work tree" in capsys.readouterr().err


def test_cmd_log_requires_git_repository(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: False)

    assert git_cmd.cmd_log(argparse.Namespace(limit=5)) == 1
    assert "is not inside a Git work tree" in capsys.readouterr().err


def test_cmd_log_handles_empty_history(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "capture", lambda cmd, cwd: "")

    assert git_cmd.cmd_log(argparse.Namespace(limit=5)) == 0
    assert "No commits found." in capsys.readouterr().out


def test_cmd_doctor_requires_git_repository(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: False)

    assert git_cmd.cmd_doctor(argparse.Namespace(changelog_file="CHANGELOG.md")) == 1
    assert "is not inside a Git work tree" in capsys.readouterr().err


def test_cmd_doctor_reports_status_failure(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "main")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: "origin/main")
    monkeypatch.setattr(
        git_cmd.git,
        "status_porcelain",
        lambda cwd: (_ for _ in ()).throw(RuntimeError("git status --short failed (exit 128)")),
    )

    assert git_cmd.cmd_doctor(argparse.Namespace(changelog_file="CHANGELOG.md")) == 1
    assert "git status --short failed" in capsys.readouterr().err


def test_cmd_doctor_reports_missing_changelog_entry(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "in_progress_operation", lambda cwd: None)
    monkeypatch.setattr(git_cmd.git, "status_porcelain", lambda cwd: [])
    monkeypatch.setattr(git_cmd.git, "ahead_behind", lambda cwd, ref: (0, 0))
    monkeypatch.setattr(git_cmd, "load_extra_branch_types", lambda cwd: ())

    def fake_capture(cmd, cwd) -> str:
        if cmd[:4] == ["git", "log", "-1", "--pretty=%s"]:
            return "feat: add parser"
        if cmd[:5] == ["git", "diff-tree", "--no-commit-id", "--name-only", "--root"]:
            return "src/repo_release_tools/cli.py"
        raise AssertionError(cmd)

    monkeypatch.setattr(git_cmd.git, "capture", fake_capture)

    assert git_cmd.cmd_doctor(argparse.Namespace(changelog_file="CHANGELOG.md")) == 1
    assert "is not part of HEAD" in capsys.readouterr().out


def test_cmd_check_dirty_tree_requires_git_repository(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: False)

    assert git_cmd.cmd_check_dirty_tree(argparse.Namespace()) == 1
    assert "is not inside a Git work tree" in capsys.readouterr().err


def test_cmd_check_dirty_tree_reports_clean_tree(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "working_tree_clean", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "main")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: "origin/main")
    monkeypatch.setattr(git_cmd.git, "ahead_behind", lambda cwd, ref: (0, 0))

    assert git_cmd.cmd_check_dirty_tree(argparse.Namespace()) == 0
    assert "Working tree is clean." in capsys.readouterr().out


def test_cmd_sync_status_requires_git_repository(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: False)

    assert git_cmd.cmd_sync_status(argparse.Namespace(base_ref=None)) == 1
    assert "is not inside a Git work tree" in capsys.readouterr().err


def test_cmd_sync_status_reports_status_failure(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "ref_exists", lambda cwd, ref: True)
    monkeypatch.setattr(git_cmd.git, "in_progress_operation", lambda cwd: None)
    monkeypatch.setattr(
        git_cmd.git,
        "status_porcelain",
        lambda cwd: (_ for _ in ()).throw(RuntimeError("git status --short failed (exit 128)")),
    )

    assert git_cmd.cmd_sync_status(argparse.Namespace(base_ref=None)) == 1
    assert "git status --short failed" in capsys.readouterr().err


def test_cmd_sync_status_reports_branch_ahead(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "ref_exists", lambda cwd, ref: True)
    monkeypatch.setattr(git_cmd.git, "in_progress_operation", lambda cwd: None)
    monkeypatch.setattr(git_cmd.git, "status_porcelain", lambda cwd: [])
    monkeypatch.setattr(git_cmd.git, "ahead_behind", lambda cwd, ref: (2, 0))

    assert git_cmd.cmd_sync_status(argparse.Namespace(base_ref=None)) == 0
    assert "is ahead of origin/feat/add-parser by 2 commit(s)." in capsys.readouterr().out


def test_cmd_commit_requires_explicit_type_when_branch_not_inferable(
    monkeypatch, tmp_path, capsys
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "main")
    args = argparse.Namespace(
        description=["ship", "parser"],
        type=None,
        scope=None,
        breaking=False,
        dry_run=False,
    )

    assert git_cmd.cmd_commit(args) == 1
    assert "Use --type explicitly" in capsys.readouterr().err


def test_cmd_commit_all_stages_and_commits(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "feat/add-parser")
    commands: list[list[str]] = []
    monkeypatch.setattr(
        git_cmd.git,
        "run",
        lambda cmd, cwd, *, dry_run, label: commands.append(cmd) or "",
    )
    args = argparse.Namespace(
        description=["ship", "parser"],
        type=None,
        scope=None,
        breaking=False,
        dry_run=False,
    )

    assert git_cmd.cmd_commit_all(args) == 0
    assert commands == [["git", "add", "."], ["git", "commit", "-m", "feat: ship parser"]]


def test_cmd_sync_requires_upstream_branch(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: None)

    assert git_cmd.cmd_sync(argparse.Namespace(merge=False, dry_run=False)) == 1
    assert "No upstream branch is configured" in capsys.readouterr().err


def test_cmd_sync_reports_status_failure(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "working_tree_clean", lambda cwd: True)
    monkeypatch.setattr(
        git_cmd.git,
        "status_porcelain",
        lambda cwd: (_ for _ in ()).throw(RuntimeError("git status --short failed (exit 128)")),
    )

    assert git_cmd.cmd_sync(argparse.Namespace(merge=False, dry_run=False)) == 1
    assert "git status --short failed" in capsys.readouterr().err


def test_cmd_sync_rejects_in_progress_operation(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "working_tree_clean", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "status_porcelain", lambda cwd: [])
    monkeypatch.setattr(git_cmd.git, "in_progress_operation", lambda cwd: "merge")

    assert git_cmd.cmd_sync(argparse.Namespace(merge=False, dry_run=False)) == 1
    assert "Cannot sync while a merge is in progress" in capsys.readouterr().err


def test_cmd_sync_warns_when_pull_fails_after_auto_stash(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "working_tree_clean", lambda cwd: False)
    monkeypatch.setattr(git_cmd.git, "status_porcelain", lambda cwd: [" M src/file.py"])
    monkeypatch.setattr(git_cmd.git, "in_progress_operation", lambda cwd: None)
    monkeypatch.setattr(git_cmd.git, "ahead_behind", lambda cwd, ref: (1, 0))
    monkeypatch.setattr(git_cmd, "spinner_lines", lambda *a, **k: contextlib.nullcontext())

    def fake_run(cmd, cwd, *, dry_run, label) -> str:
        if cmd[:2] == ["git", "pull"]:
            raise RuntimeError("pull failed")
        return ""

    monkeypatch.setattr(git_cmd.git, "run", fake_run)

    with pytest.raises(RuntimeError, match="pull failed"):
        git_cmd.cmd_sync(argparse.Namespace(merge=True, dry_run=False))

    assert "auto-stash remains on the stash stack" in capsys.readouterr().err


def test_cmd_move_warns_when_checkout_fails_after_stash(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "main")
    monkeypatch.setattr(git_cmd.git, "working_tree_clean", lambda cwd: False)

    def fake_run(cmd, cwd, *, dry_run, label) -> str:
        if cmd[:2] == ["git", "checkout"]:
            raise RuntimeError("checkout failed")
        return ""

    monkeypatch.setattr(git_cmd.git, "run", fake_run)

    with pytest.raises(RuntimeError, match="checkout failed"):
        git_cmd.cmd_move(argparse.Namespace(target="feat/add-parser", create=False, dry_run=False))

    assert "auto-stash remains on the stash stack" in capsys.readouterr().err


def test_cmd_squash_local_rejects_dirty_tree(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "working_tree_clean", lambda cwd: False)

    result = git_cmd.cmd_squash_local(
        argparse.Namespace(
            base_ref=None,
            description=["squash"],
            type="feat",
            scope=None,
            breaking=False,
            dry_run=False,
        )
    )

    assert result == 1
    assert "Working tree has uncommitted changes" in capsys.readouterr().err


def test_cmd_squash_local_requires_upstream_or_base(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "working_tree_clean", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: None)

    result = git_cmd.cmd_squash_local(
        argparse.Namespace(
            base_ref=None,
            description=["squash"],
            type="feat",
            scope=None,
            breaking=False,
            dry_run=False,
        )
    )

    assert result == 1
    assert "No upstream branch is configured" in capsys.readouterr().err


def test_cmd_squash_local_requires_commits_ahead(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "working_tree_clean", lambda cwd: True)
    monkeypatch.setattr(
        git_cmd, "resolve_commit_subject", lambda args, root: ("feat/add", "feat: add")
    )
    monkeypatch.setattr(git_cmd.git, "commits_ahead", lambda cwd, base_ref: [])

    result = git_cmd.cmd_squash_local(
        argparse.Namespace(
            base_ref="origin/main",
            description=["squash"],
            type="feat",
            scope=None,
            breaking=False,
            dry_run=False,
        )
    )

    assert result == 1
    assert "Nothing to squash" in capsys.readouterr().err


def test_cmd_squash_local_requires_merge_base(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "working_tree_clean", lambda cwd: True)
    monkeypatch.setattr(
        git_cmd, "resolve_commit_subject", lambda args, root: ("feat/add", "feat: add")
    )
    monkeypatch.setattr(git_cmd.git, "commits_ahead", lambda cwd, base_ref: ["abc123 feat: add"])
    monkeypatch.setattr(git_cmd.git, "merge_base", lambda cwd, base_ref: None)

    result = git_cmd.cmd_squash_local(
        argparse.Namespace(
            base_ref="origin/main",
            description=["squash"],
            type="feat",
            scope=None,
            breaking=False,
            dry_run=False,
        )
    )

    assert result == 1
    assert "Could not determine merge-base" in capsys.readouterr().err


def test_cmd_squash_local_reports_commit_subject_resolution_error(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "working_tree_clean", lambda cwd: True)
    monkeypatch.setattr(
        git_cmd,
        "resolve_commit_subject",
        lambda args, root: (_ for _ in ()).throw(ValueError("bad subject")),
    )

    result = git_cmd.cmd_squash_local(
        argparse.Namespace(
            base_ref="origin/main",
            description=["squash"],
            type="feat",
            scope=None,
            breaking=False,
            dry_run=False,
        )
    )

    assert result == 1
    assert "bad subject" in capsys.readouterr().err


def test_cmd_squash_local_dry_run_success(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        git_cmd, "resolve_commit_subject", lambda args, root: ("feat/add", "feat: add")
    )
    monkeypatch.setattr(
        git_cmd.git, "commits_ahead", lambda cwd, base_ref: ["a1 feat: one", "b2 fix: two"]
    )
    monkeypatch.setattr(git_cmd.git, "merge_base", lambda cwd, base_ref: "abc123")
    commands: list[list[str]] = []
    monkeypatch.setattr(
        git_cmd.git,
        "run",
        lambda cmd, cwd, *, dry_run, label: commands.append(cmd) or "",
    )

    result = git_cmd.cmd_squash_local(
        argparse.Namespace(
            base_ref="origin/main",
            description=["squash"],
            type="feat",
            scope=None,
            breaking=False,
            dry_run=True,
        )
    )

    assert result == 0
    assert commands == [["git", "reset", "--soft", "abc123"], ["git", "commit", "-m", "feat: add"]]
    assert "dry-run" in capsys.readouterr().out


def test_cmd_undo_safe_runs_soft_reset_in_dry_run(monkeypatch, capsys) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr(
        git_cmd.git,
        "run",
        lambda cmd, cwd, *, dry_run, label: commands.append(cmd) or "",
    )

    result = git_cmd.cmd_undo_safe(
        argparse.Namespace(target="HEAD~2", keep_staged=True, dry_run=True)
    )

    assert result == 0
    assert commands == [["git", "reset", "--soft", "HEAD~2"]]
    assert "dry-run" in capsys.readouterr().out


def test_cmd_undo_safe_runs_mixed_reset(monkeypatch) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr(
        git_cmd.git,
        "run",
        lambda cmd, cwd, *, dry_run, label: commands.append(cmd) or "",
    )

    assert (
        git_cmd.cmd_undo_safe(argparse.Namespace(target="HEAD~1", keep_staged=False, dry_run=False))
        == 0
    )
    assert commands == [["git", "reset", "--mixed", "HEAD~1"]]


def test_cmd_rebootstrap_rejects_missing_git_dir(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(git_cmd.git, "git_dir", lambda cwd: None)
    args = argparse.Namespace(yes_i_know_this_destroys_history=True)

    assert git_cmd.cmd_rebootstrap(args) == 1
    assert "does not look like a Git repository" in capsys.readouterr().err


def test_cmd_rebootstrap_rejects_remote_guard(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(git_cmd.git, "remote_names", lambda cwd: ["origin"])
    args = argparse.Namespace(
        yes_i_know_this_destroys_history=True,
        allow_remote=False,
        hard_init=False,
        empty_first=False,
        branch=None,
        message=None,
        empty_message=git_cmd.DEFAULT_REBOOTSTRAP_EMPTY_MESSAGE,
        dry_run=True,
    )

    assert git_cmd.cmd_rebootstrap(args) == 1
    assert "Refusing to rebootstrap a repository with configured remotes" in capsys.readouterr().err


def test_cmd_rebootstrap_empty_first_dry_run(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(git_cmd.git, "remote_names", lambda cwd: [])
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "main")
    commands: list[list[str]] = []
    monkeypatch.setattr(
        git_cmd.git,
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

    assert git_cmd.cmd_rebootstrap(args) == 0
    assert commands == [
        ["git", "init", "-b", "main"],
        ["git", "commit", "--allow-empty", "-m", "chore: empty bootstrap"],
        ["git", "add", "."],
        ["git", "commit", "-m", git_cmd.DEFAULT_REBOOTSTRAP_MESSAGE],
    ]
    assert "dry-run" in capsys.readouterr().out


def test_cmd_rebootstrap_empty_first_non_dry_run(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(git_cmd.git, "git_dir", lambda cwd: tmp_path / ".git")
    monkeypatch.setattr(git_cmd.git, "remote_names", lambda cwd: [])
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "main")
    monkeypatch.setattr(git_cmd.shutil, "move", lambda src, dst: None)
    commands: list[list[str]] = []
    monkeypatch.setattr(
        git_cmd.git,
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

    assert git_cmd.cmd_rebootstrap(args) == 0
    assert commands == [
        ["git", "init", "-b", "main"],
        ["git", "commit", "--allow-empty", "-m", "chore: empty bootstrap"],
        ["git", "add", "."],
        ["git", "commit", "-m", git_cmd.DEFAULT_REBOOTSTRAP_MESSAGE],
    ]


def test_cmd_rebootstrap_reinitializes_snapshot_history(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(git_cmd.git, "git_dir", lambda cwd: tmp_path / ".git")
    monkeypatch.setattr(git_cmd.git, "remote_names", lambda cwd: [])
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "main")
    moved: list[tuple[str, str]] = []
    commands: list[list[str]] = []
    monkeypatch.setattr(git_cmd.shutil, "move", lambda src, dst: moved.append((src, dst)))
    monkeypatch.setattr(
        git_cmd.git,
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
        empty_message=git_cmd.DEFAULT_REBOOTSTRAP_EMPTY_MESSAGE,
        dry_run=False,
    )

    assert git_cmd.cmd_rebootstrap(args) == 0
    assert moved
    assert commands == [
        ["git", "init", "-b", "main"],
        ["git", "add", "."],
        ["git", "commit", "-m", git_cmd.DEFAULT_REBOOTSTRAP_MESSAGE],
    ]
    assert "Repository history reinitialized" in capsys.readouterr().out


def test_cmd_rebootstrap_reports_runtime_failure_and_backup(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(git_cmd.git, "git_dir", lambda cwd: tmp_path / ".git")
    monkeypatch.setattr(git_cmd.git, "remote_names", lambda cwd: [])
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "main")
    monkeypatch.setattr(git_cmd.shutil, "move", lambda src, dst: None)
    monkeypatch.setattr(
        git_cmd.git,
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
        empty_message=git_cmd.DEFAULT_REBOOTSTRAP_EMPTY_MESSAGE,
        dry_run=False,
    )

    assert git_cmd.cmd_rebootstrap(args) == 1
    assert "Original git data is backed up" in capsys.readouterr().err


def test_parse_diff_line_handles_malformed_hunk_header() -> None:
    kind, text, lineno = git_cmd._parse_diff_line("@@ nonsense +oops @@")
    assert kind == "unchanged"
    assert text == "@@ nonsense +oops @@"
    assert lineno is None


def test_cmd_diff_prints_malformed_hunk_headers(monkeypatch, capsys) -> None:
    diff_output = "diff --git a/foo.py b/foo.py\n+++ b/foo.py\n@@ bad +12 @@\n+added line\n"
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda _: True)
    monkeypatch.setattr(git_cmd.git, "capture_checked", lambda cmd, cwd: diff_output)

    assert git_cmd.cmd_diff(argparse.Namespace(staged=False, against=None)) == 0
    captured = capsys.readouterr().out
    assert "@@ bad +12 @@" in captured
    assert "added line" in captured


def test_cmd_diff_uses_old_path_when_new_path_is_dev_null(monkeypatch, capsys) -> None:
    diff_output = (
        "diff --git a/deleted.txt /dev/null\n"
        "--- a/deleted.txt\n"
        "+++ /dev/null\n"
        "@@ -1 +0,0 @@\n"
        "-gone\n"
    )
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda _: True)
    monkeypatch.setattr(git_cmd.git, "capture_checked", lambda cmd, cwd: diff_output)

    assert git_cmd.cmd_diff(argparse.Namespace(staged=False, against=None)) == 0
    assert "deleted.txt" in capsys.readouterr().out


def test_cmd_status_truncates_long_change_list(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(
        git_cmd.git,
        "status_porcelain",
        lambda cwd: [f" M file-{i}.py" for i in range(16)],
    )
    monkeypatch.setattr(git_cmd.git, "ahead_behind", lambda cwd, ref: (0, 0))

    assert git_cmd.cmd_status(argparse.Namespace()) == 0
    assert "…and 1 more" in capsys.readouterr().out


def test_cmd_doctor_truncates_conflicts(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "in_progress_operation", lambda cwd: None)
    monkeypatch.setattr(
        git_cmd.git,
        "status_porcelain",
        lambda cwd: [f"UU conflict-{i}.py" for i in range(16)],
    )
    monkeypatch.setattr(git_cmd.git, "ahead_behind", lambda cwd, ref: (0, 0))

    def fake_capture(cmd, cwd) -> str:
        if cmd[:4] == ["git", "log", "-1", "--pretty=%s"]:
            return "feat: add parser"
        if cmd[:5] == ["git", "diff-tree", "--no-commit-id", "--name-only", "--root"]:
            return "CHANGELOG.md\nsrc/repo_release_tools/cli.py"
        raise AssertionError(cmd)

    monkeypatch.setattr(git_cmd.git, "capture", fake_capture)

    assert git_cmd.cmd_doctor(argparse.Namespace(changelog_file="CHANGELOG.md")) == 1
    assert "…and 1 more" in capsys.readouterr().out


def test_cmd_check_dirty_tree_truncates_status_lines(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "working_tree_clean", lambda cwd: False)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(
        git_cmd.git,
        "status_porcelain",
        lambda cwd: [f" M dirty-{i}.py" for i in range(16)],
    )
    monkeypatch.setattr(git_cmd.git, "ahead_behind", lambda cwd, ref: (0, 0))

    assert git_cmd.cmd_check_dirty_tree(argparse.Namespace()) == 1
    assert "…and 1 more" in capsys.readouterr().err


def test_cmd_sync_status_truncates_conflicts(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "ref_exists", lambda cwd, ref: True)
    monkeypatch.setattr(git_cmd.git, "in_progress_operation", lambda cwd: None)
    monkeypatch.setattr(
        git_cmd.git,
        "status_porcelain",
        lambda cwd: [f"UU sync-{i}.py" for i in range(16)],
    )
    monkeypatch.setattr(git_cmd.git, "ahead_behind", lambda cwd, ref: (1, 2))

    assert git_cmd.cmd_sync_status(argparse.Namespace(base_ref=None)) == 1
    assert "…and 1 more" in capsys.readouterr().out


def test_cmd_sync_truncates_conflicts(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "working_tree_clean", lambda cwd: False)
    monkeypatch.setattr(git_cmd.git, "in_progress_operation", lambda cwd: None)
    monkeypatch.setattr(
        git_cmd.git,
        "status_porcelain",
        lambda cwd: [f"UU sync-{i}.py" for i in range(16)],
    )
    monkeypatch.setattr(
        git_cmd.git,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("git.run should not be called")
        ),
    )

    assert git_cmd.cmd_sync(argparse.Namespace(merge=False, dry_run=True)) == 1
    assert "…and 1 more" in capsys.readouterr().err
