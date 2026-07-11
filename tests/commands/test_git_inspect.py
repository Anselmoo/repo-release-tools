from __future__ import annotations

import argparse
import pathlib

import pytest

from repo_release_tools.commands import git_inspect


def test_cmd_status_renders_summary_and_entries(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_inspect.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_inspect.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(
        git_inspect.git,
        "status_porcelain",
        lambda cwd: [" M src/repo_release_tools/cli.py", "?? docs/git.md"],
    )
    monkeypatch.setattr(git_inspect.git, "ahead_behind", lambda cwd, ref: (2, 1))
    args = argparse.Namespace()

    assert git_inspect.cmd_status(args) == 0

    captured = capsys.readouterr()
    assert "Git status" in captured.out
    assert "feat/add-parser" in captured.out
    assert "src/repo_release_tools/cli.py" in captured.out
    assert "docs/git.md" in captured.out


def test_cmd_status_renders_clean_tree(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_inspect.git, "current_branch", lambda cwd: "main")
    monkeypatch.setattr(git_inspect.git, "upstream_branch", lambda cwd: "origin/main")
    monkeypatch.setattr(git_inspect.git, "status_porcelain", lambda cwd: [])
    monkeypatch.setattr(git_inspect.git, "ahead_behind", lambda cwd, ref: (0, 0))
    args = argparse.Namespace()

    assert git_inspect.cmd_status(args) == 0

    captured = capsys.readouterr()
    assert "Working tree is clean." in captured.out


def test_cmd_status_reports_status_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_inspect.git, "current_branch", lambda cwd: "main")
    monkeypatch.setattr(git_inspect.git, "upstream_branch", lambda cwd: "origin/main")
    monkeypatch.setattr(
        git_inspect.git,
        "status_porcelain",
        lambda cwd: (_ for _ in ()).throw(RuntimeError("git status --short failed (exit 128)")),
    )
    args = argparse.Namespace()

    assert git_inspect.cmd_status(args) == 1

    captured = capsys.readouterr()
    assert "git status --short failed" in captured.err


def test_cmd_log_renders_compact_history(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(
        git_inspect.git,
        "capture",
        lambda cmd, cwd: (
            "abc1234\tfeat: add parser\tHEAD -> feat/add-parser, origin/feat/add-parser\n"
            "def5678\tfix: handle empty input\t"
        ),
    )
    args = argparse.Namespace(limit=2)

    assert git_inspect.cmd_log(args) == 0

    captured = capsys.readouterr()
    assert "Git log" in captured.out
    assert "abc1234" in captured.out
    assert "feat: add parser" in captured.out
    assert "origin/feat/add-parser" in captured.out


def test_cmd_doctor_reports_failures(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_inspect.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_inspect.git, "upstream_branch", lambda cwd: None)
    monkeypatch.setattr(git_inspect.git, "in_progress_operation", lambda cwd: None)
    monkeypatch.setattr(
        git_inspect.git,
        "status_porcelain",
        lambda cwd: [" M src/repo_release_tools/cli.py"],
    )
    monkeypatch.setattr(git_inspect.git, "ahead_behind", lambda cwd, ref: (0, 0))

    def fake_capture(cmd: list[str], cwd: pathlib.Path) -> str:
        if cmd[:4] == ["git", "log", "-1", "--pretty=%s"]:
            return "update stuff"
        if cmd[:5] == ["git", "diff-tree", "--no-commit-id", "--name-only", "--root"]:
            return "src/repo_release_tools/cli.py"
        raise AssertionError(cmd)

    monkeypatch.setattr(git_inspect.git, "capture", fake_capture)
    args = argparse.Namespace(changelog_file="CHANGELOG.md")

    assert git_inspect.cmd_doctor(args) == 1

    captured = capsys.readouterr()
    assert "Git doctor" in captured.out
    assert "No upstream branch configured." in captured.out
    assert "Working tree has uncommitted changes." in captured.out
    assert "update stuff" in captured.out


def test_cmd_doctor_reports_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_inspect.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_inspect.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(git_inspect.git, "in_progress_operation", lambda cwd: None)
    monkeypatch.setattr(git_inspect.git, "status_porcelain", lambda cwd: [])
    monkeypatch.setattr(git_inspect.git, "ahead_behind", lambda cwd, ref: (2, 0))

    def fake_capture(cmd: list[str], cwd: pathlib.Path) -> str:
        if cmd[:4] == ["git", "log", "-1", "--pretty=%s"]:
            return "feat: add parser"
        if cmd[:5] == ["git", "diff-tree", "--no-commit-id", "--name-only", "--root"]:
            return "CHANGELOG.md\nsrc/repo_release_tools/cli.py"
        raise AssertionError(cmd)

    monkeypatch.setattr(git_inspect.git, "capture", fake_capture)
    args = argparse.Namespace(changelog_file="CHANGELOG.md")

    assert git_inspect.cmd_doctor(args) == 0

    captured = capsys.readouterr()
    assert "Doctor checks passed." in captured.out


def test_cmd_doctor_uses_commit_subject_for_changelog_risk(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_inspect.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_inspect.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(git_inspect.git, "in_progress_operation", lambda cwd: None)
    monkeypatch.setattr(git_inspect.git, "status_porcelain", lambda cwd: [])
    monkeypatch.setattr(git_inspect.git, "ahead_behind", lambda cwd, ref: (0, 0))

    def fake_capture(cmd: list[str], cwd: pathlib.Path) -> str:
        if cmd[:4] == ["git", "log", "-1", "--pretty=%s"]:
            return "chore: update docs tooling"
        if cmd[:5] == ["git", "diff-tree", "--no-commit-id", "--name-only", "--root"]:
            raise AssertionError("changelog diff should not be queried for chore commits")
        raise AssertionError(cmd)

    monkeypatch.setattr(git_inspect.git, "capture", fake_capture)
    args = argparse.Namespace(changelog_file="CHANGELOG.md")

    assert git_inspect.cmd_doctor(args) == 0

    captured = capsys.readouterr()
    assert "Doctor checks passed." in captured.out


def test_cmd_doctor_reports_conflicts_and_sync_need(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_inspect.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_inspect.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(git_inspect.git, "in_progress_operation", lambda cwd: "rebase")
    monkeypatch.setattr(
        git_inspect.git,
        "status_porcelain",
        lambda cwd: ["UU src/conflicted.py", " M src/repo_release_tools/cli.py"],
    )
    monkeypatch.setattr(git_inspect.git, "ahead_behind", lambda cwd, ref: (2, 3))

    def fake_capture(cmd: list[str], cwd: pathlib.Path) -> str:
        if cmd[:4] == ["git", "log", "-1", "--pretty=%s"]:
            return "feat: add parser"
        if cmd[:5] == ["git", "diff-tree", "--no-commit-id", "--name-only", "--root"]:
            return "CHANGELOG.md\nsrc/repo_release_tools/cli.py"
        raise AssertionError(cmd)

    monkeypatch.setattr(git_inspect.git, "capture", fake_capture)
    args = argparse.Namespace(changelog_file="CHANGELOG.md")

    assert git_inspect.cmd_doctor(args) == 1

    captured = capsys.readouterr()
    assert "Rebase is in progress" in captured.out
    assert "Found 1 conflicted path" in captured.out
    assert "has diverged from origin/feat/add-parser" in captured.out
    assert "src/conflicted.py" in captured.out


def test_compute_changelog_problem_skips_non_changelog_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No changelog problem is computed (and no diff-tree call made) for chore commits."""

    def fake_capture(cmd: list[str], cwd: pathlib.Path) -> str:
        raise AssertionError("diff-tree should not be queried for chore commits")

    monkeypatch.setattr(git_inspect.git, "capture", fake_capture)

    result = git_inspect._compute_changelog_problem(
        latest_subject="chore: update docs tooling",
        branch_name="chore/update-docs",
        changelog_file="CHANGELOG.md",
        root=pathlib.Path("/repo"),
    )

    assert result is None


def test_compute_changelog_problem_flags_missing_changelog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A feat commit whose HEAD diff doesn't touch the changelog file is flagged."""
    monkeypatch.setattr(
        git_inspect.git,
        "capture",
        lambda cmd, cwd: "src/repo_release_tools/cli.py",
    )

    result = git_inspect._compute_changelog_problem(
        latest_subject="feat: add parser",
        branch_name="feat/add-parser",
        changelog_file="CHANGELOG.md",
        root=pathlib.Path("/repo"),
    )

    assert result is not None
    assert "feat/add-parser" in result
    assert "CHANGELOG.md" in result


def test_build_doctor_checks_appends_relation_check_only_with_upstream() -> None:
    """The sync-relation check is appended only when an upstream branch is configured."""
    without_upstream = git_inspect._build_doctor_checks(
        branch_problem=None,
        upstream=None,
        dirty_problem=None,
        operation_problem=None,
        conflict_problem=None,
        subject_problem=None,
        changelog_problem=None,
        changelog_file="CHANGELOG.md",
        branch_name="main",
        relation_problem=None,
    )
    with_upstream = git_inspect._build_doctor_checks(
        branch_problem=None,
        upstream="origin/main",
        dirty_problem=None,
        operation_problem=None,
        conflict_problem=None,
        subject_problem=None,
        changelog_problem=None,
        changelog_file="CHANGELOG.md",
        branch_name="main",
        relation_problem="Branch 'main' is behind origin/main by 1 commit(s). Sync is needed.",
    )

    assert len(without_upstream) == 7
    assert len(with_upstream) == 8
    assert with_upstream[-1] == (
        False,
        "main does not need sync from origin/main.",
        "Branch 'main' is behind origin/main by 1 commit(s). Sync is needed.",
    )


def test_cmd_sync_status_reports_diverged_rebase_conflicts(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_inspect.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_inspect.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(git_inspect.git, "ref_exists", lambda cwd, ref: True)
    monkeypatch.setattr(git_inspect.git, "in_progress_operation", lambda cwd: "rebase")
    monkeypatch.setattr(
        git_inspect.git,
        "status_porcelain",
        lambda cwd: ["UU src/conflicted.py", " M src/repo_release_tools/cli.py"],
    )
    monkeypatch.setattr(git_inspect.git, "ahead_behind", lambda cwd, ref: (2, 3))
    args = argparse.Namespace(base_ref=None)

    assert git_inspect.cmd_sync_status(args) == 1

    captured = capsys.readouterr()
    assert "Sync status" in captured.out
    assert "Rebase is in progress" in captured.out
    assert "Found 1 conflicted path" in captured.out
    assert "Rebase or merge is needed" in captured.out
    assert "src/conflicted.py" in captured.out


def test_cmd_sync_status_reports_clean_branch(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_inspect.git, "current_branch", lambda cwd: "main")
    monkeypatch.setattr(git_inspect.git, "upstream_branch", lambda cwd: "origin/main")
    monkeypatch.setattr(git_inspect.git, "ref_exists", lambda cwd, ref: True)
    monkeypatch.setattr(git_inspect.git, "in_progress_operation", lambda cwd: None)
    monkeypatch.setattr(git_inspect.git, "status_porcelain", lambda cwd: [])
    monkeypatch.setattr(git_inspect.git, "ahead_behind", lambda cwd, ref: (0, 0))
    args = argparse.Namespace(base_ref=None)

    assert git_inspect.cmd_sync_status(args) == 0

    captured = capsys.readouterr()
    assert "Sync analysis passed." in captured.out
    assert "matches origin/main" in captured.out


def test_cmd_sync_status_requires_base_ref_when_missing_upstream(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_inspect.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_inspect.git, "upstream_branch", lambda cwd: None)
    monkeypatch.setattr(git_inspect.git, "in_progress_operation", lambda cwd: None)
    monkeypatch.setattr(git_inspect.git, "status_porcelain", lambda cwd: [])
    args = argparse.Namespace(base_ref=None)

    assert git_inspect.cmd_sync_status(args) == 1

    captured = capsys.readouterr()
    assert "No upstream branch is configured" in captured.out


def test_cmd_sync_status_rejects_missing_base_ref(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_inspect.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_inspect.git, "upstream_branch", lambda cwd: None)
    monkeypatch.setattr(git_inspect.git, "ref_exists", lambda cwd, ref: False)
    args = argparse.Namespace(base_ref="origin/missing")

    assert git_inspect.cmd_sync_status(args) == 1

    captured = capsys.readouterr()
    assert "does not exist" in captured.err


def test_render_sync_analysis_reports_all_clear(capsys: pytest.CaptureFixture[str]) -> None:
    """No operation, no conflicts, and a matching base ref yields zero failures."""
    p = git_inspect.VerbosePrinter(verbose=0)

    failures = git_inspect._render_sync_analysis(
        p,
        branch_name="main",
        base_ref="origin/main",
        operation=None,
        conflicts=[],
        ahead=0,
        behind=0,
    )

    out = capsys.readouterr().out
    assert failures == 0
    assert "No merge or rebase is in progress." in out
    assert "No unresolved conflicts detected." in out
    assert "main matches origin/main." in out


def test_render_sync_analysis_counts_each_failure(capsys: pytest.CaptureFixture[str]) -> None:
    """An in-progress rebase, conflicts, and divergence each count as a failure."""
    p = git_inspect.VerbosePrinter(verbose=0)

    failures = git_inspect._render_sync_analysis(
        p,
        branch_name="feat/x",
        base_ref="origin/feat/x",
        operation="rebase",
        conflicts=["UU src/conflicted.py"],
        ahead=2,
        behind=3,
    )

    out = capsys.readouterr().out
    assert failures == 3
    assert "Rebase is in progress" in out
    assert "Found 1 conflicted path(s)." in out
    assert "diverged" in out.lower() or "Rebase or merge is needed" in out


def test_cmd_check_dirty_tree_reports_status_lines(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_inspect.git, "working_tree_clean", lambda cwd: False)
    monkeypatch.setattr(git_inspect.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_inspect.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(
        git_inspect.git,
        "status_porcelain",
        lambda cwd: [" M src/repo_release_tools/cli.py", "?? docs/git.md"],
    )
    monkeypatch.setattr(git_inspect.git, "ahead_behind", lambda cwd, ref: (2, 1))
    args = argparse.Namespace()

    assert git_inspect.cmd_check_dirty_tree(args) == 1

    captured = capsys.readouterr()
    assert "Working tree has uncommitted changes." in captured.err
    assert "feat/add-parser" in captured.err
    assert "src/repo_release_tools/cli.py" in captured.err
    assert "docs/git.md" in captured.err


def test_cmd_check_dirty_tree_reports_status_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_inspect.git, "working_tree_clean", lambda cwd: False)
    monkeypatch.setattr(git_inspect.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_inspect.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(
        git_inspect.git,
        "status_porcelain",
        lambda cwd: (_ for _ in ()).throw(RuntimeError("git status --short failed (exit 128)")),
    )
    args = argparse.Namespace()

    assert git_inspect.cmd_check_dirty_tree(args) == 1

    captured = capsys.readouterr()
    assert "git status --short failed" in captured.err


def test_parse_diff_line_added() -> None:
    kind, text, lineno = git_inspect._parse_diff_line("+hello world")
    assert kind == "added"
    assert text == "hello world"
    assert lineno is None


def test_parse_diff_line_removed() -> None:
    kind, text, lineno = git_inspect._parse_diff_line("-goodbye")
    assert kind == "removed"
    assert text == "goodbye"
    assert lineno is None


def test_parse_diff_line_unchanged_context() -> None:
    kind, text, lineno = git_inspect._parse_diff_line(" context line")
    assert kind == "unchanged"
    assert lineno is None


def test_parse_diff_line_hunk_header() -> None:
    kind, text, lineno = git_inspect._parse_diff_line("@@ -10,4 +20,6 @@ def foo():")
    assert kind == "unchanged"
    assert lineno == 20


def test_parse_diff_line_file_headers() -> None:
    for prefix in ("+++", "---"):
        kind, _, lineno = git_inspect._parse_diff_line(f"{prefix} a/file.py")
        assert kind == "unchanged"
        assert lineno is None


def test_cmd_diff_not_git_repo(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda _: False)
    args = argparse.Namespace(staged=False, against=None)

    assert git_inspect.cmd_diff(args) == 1
    assert tmp_path.name in capsys.readouterr().err


def test_cmd_diff_no_changes(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda _: True)
    monkeypatch.setattr(git_inspect.git, "capture_checked", lambda cmd, cwd: "")
    args = argparse.Namespace(staged=False, against=None)

    assert git_inspect.cmd_diff(args) == 0
    assert "No diff" in capsys.readouterr().out


def test_cmd_diff_renders_added_and_removed(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
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
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda _: True)
    monkeypatch.setattr(git_inspect.git, "capture_checked", lambda cmd, cwd: diff_output)
    args = argparse.Namespace(staged=False, against=None)

    rc = git_inspect.cmd_diff(args)
    captured = capsys.readouterr().out

    assert rc == 0
    assert "foo.py" in captured


def test_render_diff_body_renders_added_and_removed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Direct call renders the file section and added/removed/unchanged lines."""
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

    git_inspect._render_diff_body(diff_output, verbose=0)

    out = capsys.readouterr().out
    assert "foo.py" in out
    assert "removed line" in out
    assert "added line" in out
    assert "unchanged" in out


def test_render_diff_body_handles_deleted_file(capsys: pytest.CaptureFixture[str]) -> None:
    """A deleted file (``+++ /dev/null``) still gets a section header from the old path."""
    diff_output = (
        "diff --git a/gone.py b/gone.py\n"
        "deleted file mode 100644\n"
        "index abc..000 100644\n"
        "--- a/gone.py\n"
        "+++ /dev/null\n"
        "@@ -1 +0,0 @@\n"
        "-old content\n"
    )

    git_inspect._render_diff_body(diff_output, verbose=0)

    out = capsys.readouterr().out
    assert "gone.py" in out
    assert "old content" in out


def test_cmd_diff_staged_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_cmd = {}
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda _: True)

    def fake_capture(cmd: list[str], cwd: pathlib.Path) -> str:
        captured_cmd["cmd"] = cmd
        return ""

    monkeypatch.setattr(git_inspect.git, "capture_checked", fake_capture)
    args = argparse.Namespace(staged=True, against=None)
    git_inspect.cmd_diff(args)
    assert "--staged" in captured_cmd["cmd"]


def test_cmd_diff_against_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_cmd = {}
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda _: True)

    def fake_capture(cmd: list[str], cwd: pathlib.Path) -> str:
        captured_cmd["cmd"] = cmd
        return ""

    monkeypatch.setattr(git_inspect.git, "capture_checked", fake_capture)
    args = argparse.Namespace(staged=False, against="HEAD~2")
    git_inspect.cmd_diff(args)
    assert "HEAD~2" in captured_cmd["cmd"]


def test_cmd_diff_reports_invalid_ref(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda _: True)
    monkeypatch.setattr(
        git_inspect.git,
        "capture_checked",
        lambda cmd, cwd: (_ for _ in ()).throw(
            RuntimeError("git diff --unified=3 badref failed (exit 128)"),
        ),
    )
    args = argparse.Namespace(staged=False, against="badref")

    assert git_inspect.cmd_diff(args) == 1

    captured = capsys.readouterr()
    assert "badref" in captured.err
    assert "No diff to show" not in captured.out


def test_cmd_diff_handles_deleted_file_headers(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    diff_output = (
        "diff --git a/deleted.txt b/deleted.txt\n"
        "deleted file mode 100644\n"
        "index abcdef0..0000000 100644\n"
        "--- a/deleted.txt\n"
        "+++ /dev/null\n"
        "@@ -1 +0,0 @@\n"
        "-removed line\n"
    )
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda _: True)
    monkeypatch.setattr(git_inspect.git, "capture_checked", lambda cmd, cwd: diff_output)
    args = argparse.Namespace(staged=False, against=None)

    assert git_inspect.cmd_diff(args) == 0

    captured = capsys.readouterr().out
    assert "deleted.txt" in captured
    assert "removed line" in captured


def test_describe_sync_relation_and_sync_problem_cover_remaining_states() -> None:
    assert (
        git_inspect.describe_sync_relation(ahead=0, behind=2, base_ref="origin/main")
        == "behind base"
    )
    assert (
        git_inspect.describe_sync_relation(ahead=1, behind=2, base_ref="origin/main") == "diverged"
    )
    assert (
        git_inspect.sync_problem("feat/add-parser", base_ref="origin/main", ahead=0, behind=2)
        == "Branch 'feat/add-parser' is behind origin/main by 2 commit(s). Sync is needed."
    )


def test_cmd_status_requires_git_repository(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda cwd: False)

    assert git_inspect.cmd_status(argparse.Namespace()) == 1
    assert "is not inside a Git work tree" in capsys.readouterr().err


def test_cmd_log_requires_git_repository(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda cwd: False)

    assert git_inspect.cmd_log(argparse.Namespace(limit=5)) == 1
    assert "is not inside a Git work tree" in capsys.readouterr().err


def test_cmd_log_handles_empty_history(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_inspect.git, "capture", lambda cmd, cwd: "")

    assert git_inspect.cmd_log(argparse.Namespace(limit=5)) == 0
    assert "No commits found." in capsys.readouterr().out


def test_cmd_doctor_requires_git_repository(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda cwd: False)

    assert git_inspect.cmd_doctor(argparse.Namespace(changelog_file="CHANGELOG.md")) == 1
    assert "is not inside a Git work tree" in capsys.readouterr().err


def test_cmd_doctor_reports_status_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_inspect.git, "current_branch", lambda cwd: "main")
    monkeypatch.setattr(git_inspect.git, "upstream_branch", lambda cwd: "origin/main")
    monkeypatch.setattr(
        git_inspect.git,
        "status_porcelain",
        lambda cwd: (_ for _ in ()).throw(RuntimeError("git status --short failed (exit 128)")),
    )

    assert git_inspect.cmd_doctor(argparse.Namespace(changelog_file="CHANGELOG.md")) == 1
    assert "git status --short failed" in capsys.readouterr().err


def test_cmd_doctor_reports_missing_changelog_entry(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_inspect.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_inspect.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(git_inspect.git, "in_progress_operation", lambda cwd: None)
    monkeypatch.setattr(git_inspect.git, "status_porcelain", lambda cwd: [])
    monkeypatch.setattr(git_inspect.git, "ahead_behind", lambda cwd, ref: (0, 0))
    monkeypatch.setattr(git_inspect, "load_extra_branch_types", lambda cwd: ())

    def fake_capture(cmd: list[str], cwd: pathlib.Path) -> str:
        if cmd[:4] == ["git", "log", "-1", "--pretty=%s"]:
            return "feat: add parser"
        if cmd[:5] == ["git", "diff-tree", "--no-commit-id", "--name-only", "--root"]:
            return "src/repo_release_tools/cli.py"
        raise AssertionError(cmd)

    monkeypatch.setattr(git_inspect.git, "capture", fake_capture)

    assert git_inspect.cmd_doctor(argparse.Namespace(changelog_file="CHANGELOG.md")) == 1
    assert "is not part of HEAD" in capsys.readouterr().out


def test_cmd_check_dirty_tree_requires_git_repository(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda cwd: False)

    assert git_inspect.cmd_check_dirty_tree(argparse.Namespace()) == 1
    assert "is not inside a Git work tree" in capsys.readouterr().err


def test_cmd_check_dirty_tree_reports_clean_tree(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_inspect.git, "working_tree_clean", lambda cwd: True)
    monkeypatch.setattr(git_inspect.git, "current_branch", lambda cwd: "main")
    monkeypatch.setattr(git_inspect.git, "upstream_branch", lambda cwd: "origin/main")
    monkeypatch.setattr(git_inspect.git, "ahead_behind", lambda cwd, ref: (0, 0))

    assert git_inspect.cmd_check_dirty_tree(argparse.Namespace()) == 0
    assert "Working tree is clean." in capsys.readouterr().out


def test_cmd_sync_status_requires_git_repository(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda cwd: False)

    assert git_inspect.cmd_sync_status(argparse.Namespace(base_ref=None)) == 1
    assert "is not inside a Git work tree" in capsys.readouterr().err


def test_cmd_sync_status_reports_status_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_inspect.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_inspect.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(git_inspect.git, "ref_exists", lambda cwd, ref: True)
    monkeypatch.setattr(git_inspect.git, "in_progress_operation", lambda cwd: None)
    monkeypatch.setattr(
        git_inspect.git,
        "status_porcelain",
        lambda cwd: (_ for _ in ()).throw(RuntimeError("git status --short failed (exit 128)")),
    )

    assert git_inspect.cmd_sync_status(argparse.Namespace(base_ref=None)) == 1
    assert "git status --short failed" in capsys.readouterr().err


def test_cmd_sync_status_reports_branch_ahead(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_inspect.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_inspect.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(git_inspect.git, "ref_exists", lambda cwd, ref: True)
    monkeypatch.setattr(git_inspect.git, "in_progress_operation", lambda cwd: None)
    monkeypatch.setattr(git_inspect.git, "status_porcelain", lambda cwd: [])
    monkeypatch.setattr(git_inspect.git, "ahead_behind", lambda cwd, ref: (2, 0))

    assert git_inspect.cmd_sync_status(argparse.Namespace(base_ref=None)) == 0
    assert "is ahead of origin/feat/add-parser by 2 commit(s)." in capsys.readouterr().out


def test_parse_diff_line_handles_malformed_hunk_header() -> None:
    kind, text, lineno = git_inspect._parse_diff_line("@@ nonsense +oops @@")
    assert kind == "unchanged"
    assert text == "@@ nonsense +oops @@"
    assert lineno is None


def test_cmd_diff_prints_malformed_hunk_headers(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    diff_output = "diff --git a/foo.py b/foo.py\n+++ b/foo.py\n@@ bad +12 @@\n+added line\n"
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda _: True)
    monkeypatch.setattr(git_inspect.git, "capture_checked", lambda cmd, cwd: diff_output)

    assert git_inspect.cmd_diff(argparse.Namespace(staged=False, against=None)) == 0
    captured = capsys.readouterr().out
    assert "@@ bad +12 @@" in captured
    assert "added line" in captured


def test_cmd_diff_uses_old_path_when_new_path_is_dev_null(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    diff_output = (
        "diff --git a/deleted.txt /dev/null\n"
        "--- a/deleted.txt\n"
        "+++ /dev/null\n"
        "@@ -1 +0,0 @@\n"
        "-gone\n"
    )
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda _: True)
    monkeypatch.setattr(git_inspect.git, "capture_checked", lambda cmd, cwd: diff_output)

    assert git_inspect.cmd_diff(argparse.Namespace(staged=False, against=None)) == 0
    assert "deleted.txt" in capsys.readouterr().out


def test_cmd_status_truncates_long_change_list(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_inspect.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_inspect.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(
        git_inspect.git,
        "status_porcelain",
        lambda cwd: [f" M file-{i}.py" for i in range(16)],
    )
    monkeypatch.setattr(git_inspect.git, "ahead_behind", lambda cwd, ref: (0, 0))

    assert git_inspect.cmd_status(argparse.Namespace()) == 0
    assert "…and 1 more" in capsys.readouterr().out


def test_cmd_doctor_truncates_conflicts(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_inspect.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_inspect.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(git_inspect.git, "in_progress_operation", lambda cwd: None)
    monkeypatch.setattr(
        git_inspect.git,
        "status_porcelain",
        lambda cwd: [f"UU conflict-{i}.py" for i in range(16)],
    )
    monkeypatch.setattr(git_inspect.git, "ahead_behind", lambda cwd, ref: (0, 0))

    def fake_capture(cmd: list[str], cwd: pathlib.Path) -> str:
        if cmd[:4] == ["git", "log", "-1", "--pretty=%s"]:
            return "feat: add parser"
        if cmd[:5] == ["git", "diff-tree", "--no-commit-id", "--name-only", "--root"]:
            return "CHANGELOG.md\nsrc/repo_release_tools/cli.py"
        raise AssertionError(cmd)

    monkeypatch.setattr(git_inspect.git, "capture", fake_capture)

    assert git_inspect.cmd_doctor(argparse.Namespace(changelog_file="CHANGELOG.md")) == 1
    assert "…and 1 more" in capsys.readouterr().out


def test_cmd_check_dirty_tree_truncates_status_lines(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_inspect.git, "working_tree_clean", lambda cwd: False)
    monkeypatch.setattr(git_inspect.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_inspect.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(
        git_inspect.git,
        "status_porcelain",
        lambda cwd: [f" M dirty-{i}.py" for i in range(16)],
    )
    monkeypatch.setattr(git_inspect.git, "ahead_behind", lambda cwd, ref: (0, 0))

    assert git_inspect.cmd_check_dirty_tree(argparse.Namespace()) == 1
    assert "…and 1 more" in capsys.readouterr().err


def test_cmd_sync_status_truncates_conflicts(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_inspect.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_inspect.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_inspect.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(git_inspect.git, "ref_exists", lambda cwd, ref: True)
    monkeypatch.setattr(git_inspect.git, "in_progress_operation", lambda cwd: None)
    monkeypatch.setattr(
        git_inspect.git,
        "status_porcelain",
        lambda cwd: [f"UU sync-{i}.py" for i in range(16)],
    )
    monkeypatch.setattr(git_inspect.git, "ahead_behind", lambda cwd, ref: (1, 2))

    assert git_inspect.cmd_sync_status(argparse.Namespace(base_ref=None)) == 1
    assert "…and 1 more" in capsys.readouterr().out
