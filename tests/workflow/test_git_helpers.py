"""Tests for git.py command helpers and dry-run logic."""

from __future__ import annotations

import datetime as dt
import subprocess
from pathlib import Path

import pytest

from repo_release_tools.workflow import git


def _init_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=root, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=root, check=True)


def test_run_dry_run_skips_subprocess(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("subprocess should not run")),
    )

    result = git.run(["git", "status"], tmp_path, dry_run=True, label="git status")

    assert result == ""
    assert "Would run: git status" in capsys.readouterr().out


def test_run_prints_stdout_on_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_run(
        cmd: list[str],
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert cmd == ["git", "status"]
        return subprocess.CompletedProcess(cmd, 0, stdout="line one\nline two\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = git.run(["git", "status"], tmp_path, dry_run=False, label="git status")

    captured = capsys.readouterr().out
    assert result == "line one\nline two"
    assert "git status" in captured
    assert "line one" in captured
    assert "line two" in captured


def test_run_can_suppress_initial_command_announcement(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_run(
        cmd: list[str],
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert cmd == ["git", "status"]
        return subprocess.CompletedProcess(cmd, 0, stdout="line one\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = git.run(
        ["git", "status"],
        tmp_path,
        dry_run=False,
        label="git status",
        suppress_announce=True,
    )

    captured = capsys.readouterr().out
    assert result == "line one"
    assert "git status" not in captured
    assert "line one" in captured


def test_run_prints_stdout_and_stderr_before_raising(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_run(
        cmd: list[str],
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 2, stdout="out line\n", stderr="err line\n")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match=r"git status failed \(exit 2\)"):
        git.run(["git", "status"], tmp_path, dry_run=False, label="git status")

    captured = capsys.readouterr().out
    assert "out line" in captured
    assert "err line" in captured


def test_run_error_detail_surfaces_last_stderr_line_not_first(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A tool's most specific error line is usually its *last* stderr line,
    not its first (e.g. pre-commit's hook summary starts with a generic
    "<hook>.......Failed" header and ends with the actionable detail, like
    "- files were modified by this hook"). Callers that pattern-match on
    ``str(exc)`` (e.g. bump.py's commit-retry narrowing) need that detail
    line, not the generic header.
    """

    def fake_run(
        cmd: list[str],
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            cmd,
            1,
            stdout="",
            stderr="rewriter.................................................Failed\n"
            "- hook id: rewriter\n"
            "- files were modified by this hook\n",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="files were modified by this hook"):
        git.run(["git", "commit", "-m", "x"], tmp_path, dry_run=False, label="git commit")


def test_run_error_detail_ignores_trailing_passed_hook_line(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Regression test for #182: a hook that passes *after* the actually
    failing hook must not have its "...Passed" status line mistaken for the
    failure reason just because it happened to print last.
    """

    def fake_run(
        cmd: list[str],
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            cmd,
            1,
            stdout="",
            stderr="rewriter.................................................Failed\n"
            "- hook id: rewriter\n"
            "- files were modified by this hook\n"
            "\n"
            "check for case conflicts.................................................Passed\n",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError) as exc_info:
        git.run(["git", "commit", "-m", "x"], tmp_path, dry_run=False, label="git commit")

    message = str(exc_info.value)
    assert "files were modified by this hook" in message
    assert "check for case conflicts" not in message


def test_run_error_detail_multiple_failed_hooks_uses_last(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_run(
        cmd: list[str],
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            cmd,
            1,
            stdout="",
            stderr="first-hook...............................................Failed\n"
            "- first hook detail\n"
            "\n"
            "second-hook..............................................Failed\n"
            "- second hook detail\n",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError) as exc_info:
        git.run(["git", "commit", "-m", "x"], tmp_path, dry_run=False, label="git commit")

    message = str(exc_info.value)
    assert "second hook detail" in message
    assert "first hook detail" not in message


def test_run_error_detail_falls_back_to_last_line_without_failed_marker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_run(
        cmd: list[str],
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            cmd, 128, stdout="", stderr="fatal: not a git repository\nsome other line\n"
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="some other line"):
        git.run(["git", "status"], tmp_path, dry_run=False, label="git status")


def test_run_error_detail_falls_back_to_stdout_when_stderr_empty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_run(
        cmd: list[str],
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 1, stdout="only stdout output\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="only stdout output"):
        git.run(["git", "status"], tmp_path, dry_run=False, label="git status")


def test_capture_and_capture_checked_strip_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_run(
        cmd: list[str],
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 0, stdout="  value\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert git.capture(["git", "branch", "--show-current"], tmp_path) == "value"
    assert git.capture_checked(["git", "rev-parse", "HEAD"], tmp_path) == "value"


def test_capture_checked_raises_on_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_run(
        cmd: list[str],
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 7, stdout="", stderr="fatal")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match=r"git rev-parse HEAD failed \(exit 7\): fatal"):
        git.capture_checked(["git", "rev-parse", "HEAD"], tmp_path)


def test_capture_checked_includes_failed_hook_detail(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_run(
        cmd: list[str],
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            cmd,
            1,
            stdout="",
            stderr="rewriter.................................................Failed\n"
            "- files were modified by this hook\n",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="files were modified by this hook"):
        git.capture_checked(["git", "commit", "-m", "x"], tmp_path)


def test_current_branch_branch_exists_and_commits_ahead_delegate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_capture(cmd: list[str], cwd: Path) -> str:
        if cmd == ["git", "branch", "--show-current"]:
            return "feature/current"
        if cmd == ["git", "branch", "--list", "--", "release/v1.2.3"]:
            return "  release/v1.2.3"
        if cmd == ["git", "log", "origin/main..HEAD", "--pretty=format:%h %s"]:
            return "abc123 feat: add parser\n\nxyz789 fix: typo\n"
        raise AssertionError(cmd)

    monkeypatch.setattr(git, "capture", fake_capture)

    assert git.current_branch(tmp_path) == "feature/current"
    assert git.branch_exists(tmp_path, "release/v1.2.3") is True
    assert git.commits_ahead(tmp_path, "origin/main") == [
        "abc123 feat: add parser",
        "xyz789 fix: typo",
    ]


def test_branch_exists_uses_dashdash_separator(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """SEC-004: a dash-prefixed branch name must not be parsed as a git option."""
    captured: list[list[str]] = []

    def fake_capture(cmd: list[str], cwd: Path) -> str:
        captured.append(cmd)
        return ""

    monkeypatch.setattr(git, "capture", fake_capture)

    assert git.branch_exists(tmp_path, "--force") is False
    assert captured == [["git", "branch", "--list", "--", "--force"]]


def test_commits_ahead_rejects_dash_prefixed_base_ref(tmp_path: Path) -> None:
    """SEC-004: ``<base_ref>..HEAD`` is a single positional revision-range argument

    that ``--`` cannot safely guard (it would be reinterpreted as a pathspec), so a
    leading dash is rejected outright instead of reaching the subprocess.
    """
    with pytest.raises(ValueError, match=r"base_ref must not start with '-'"):
        git.commits_ahead(tmp_path, "--output=/tmp/evil")


def test_working_tree_clean_and_ahead_behind_handle_multiple_outcomes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    responses = iter(
        [
            subprocess.CompletedProcess([], 0, stdout="", stderr=""),
            subprocess.CompletedProcess([], 0, stdout=" M file.py\n", stderr=""),
            subprocess.CompletedProcess([], 0, stdout="3 2\n", stderr=""),
            subprocess.CompletedProcess([], 1, stdout="", stderr="fatal"),
            subprocess.CompletedProcess([], 0, stdout="malformed\n", stderr=""),
        ],
    )

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: next(responses))

    assert git.working_tree_clean(tmp_path) is True
    assert git.working_tree_clean(tmp_path) is False
    assert git.ahead_behind(tmp_path, "origin/main") == (3, 2)
    assert git.ahead_behind(tmp_path, "origin/main") == (0, 0)
    assert git.ahead_behind(tmp_path, "origin/main") == (0, 0)


def test_upstream_branch_returns_value_or_none(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    responses = iter(
        [
            subprocess.CompletedProcess([], 0, stdout="origin/main\n", stderr=""),
            subprocess.CompletedProcess([], 0, stdout="\n", stderr=""),
            subprocess.CompletedProcess([], 128, stdout="", stderr="fatal"),
        ],
    )

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: next(responses))

    assert git.upstream_branch(tmp_path) == "origin/main"
    assert git.upstream_branch(tmp_path) is None
    assert git.upstream_branch(tmp_path) is None


def test_git_dir_merge_base_remote_names_and_repository_detection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    responses = iter(
        [
            subprocess.CompletedProcess([], 0, stdout=".git\n", stderr=""),
            subprocess.CompletedProcess([], 0, stdout="\n", stderr=""),
            subprocess.CompletedProcess([], 128, stdout="", stderr="fatal"),
            subprocess.CompletedProcess([], 0, stdout="abc123\n", stderr=""),
            subprocess.CompletedProcess([], 128, stdout="", stderr="fatal"),
            subprocess.CompletedProcess([], 0, stdout="true\n", stderr=""),
            subprocess.CompletedProcess([], 0, stdout="false\n", stderr=""),
            subprocess.CompletedProcess([], 128, stdout="", stderr="fatal"),
        ],
    )

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr(git, "capture", lambda cmd, cwd: "origin\n\nupstream\n")

    assert git.git_dir(tmp_path) == (tmp_path / ".git").resolve()
    assert git.git_dir(tmp_path) is None
    assert git.git_dir(tmp_path) is None
    assert git.merge_base(tmp_path, "origin/main") == "abc123"
    assert git.merge_base(tmp_path, "origin/main") is None
    assert git.remote_names(tmp_path) == ["origin", "upstream"]
    assert git.is_git_repository(tmp_path) is True
    assert git.is_git_repository(tmp_path) is False
    assert git.is_git_repository(tmp_path) is False


def test_status_porcelain_preserves_leading_spaces(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_run(
        cmd: list[str],
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert cmd == ["git", "status", "--short"]
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=" M src/repo_release_tools/cli.py\n?? docs/git.md\n",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    lines = git.status_porcelain(tmp_path)

    assert lines == [" M src/repo_release_tools/cli.py", "?? docs/git.md"]


def test_status_porcelain_can_include_branch_header(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_run(
        cmd: list[str],
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert cmd == ["git", "status", "--short", "--branch"]
        return subprocess.CompletedProcess(cmd, 0, stdout="## feat/add-parser\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert git.status_porcelain(tmp_path, include_branch=True) == ["## feat/add-parser"]


def test_status_porcelain_raises_on_git_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_run(
        cmd: list[str],
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="fatal")

    monkeypatch.setattr(subprocess, "run", fake_run)

    try:
        git.status_porcelain(tmp_path)
    except RuntimeError as exc:
        assert "git status --short failed" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError")


def test_ref_exists_checks_rev_parse(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_run(
        cmd: list[str],
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert cmd == ["git", "rev-parse", "--verify", "--quiet", "HEAD~1"]
        return subprocess.CompletedProcess(cmd, 0, stdout="abc123\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert git.ref_exists(tmp_path, "HEAD~1") is True


def test_ref_exists_rejects_dash_prefixed_ref_without_invoking_git(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """SEC-004: a dash-prefixed ref must not reach ``git rev-parse --verify``.

    Unlike a plain positional path, ``--`` does not reliably stop option parsing
    for ``rev-parse``, so a leading dash is rejected before the subprocess call.
    """
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("git must not run")),
    )

    assert git.ref_exists(tmp_path, "--output=/tmp/evil") is False


def test_in_progress_operation_detects_rebase_and_merge(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    rebase_dir = tmp_path / ".git" / "rebase-merge"
    rebase_dir.mkdir(parents=True)
    monkeypatch.setattr(git, "git_dir", lambda cwd: tmp_path / ".git")

    assert git.in_progress_operation(tmp_path) == "rebase"

    rebase_dir.rmdir()
    (tmp_path / ".git" / "MERGE_HEAD").write_text("abc123\n", encoding="utf-8")

    assert git.in_progress_operation(tmp_path) == "merge"


def test_in_progress_operation_returns_none_without_git_dir_or_markers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(git, "git_dir", lambda cwd: None)
    assert git.in_progress_operation(tmp_path) is None

    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    monkeypatch.setattr(git, "git_dir", lambda cwd: git_dir)
    assert git.in_progress_operation(tmp_path) is None


def test_remote_url_returns_configured_url(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://example.com/x.git"],
        cwd=tmp_path,
        check=True,
    )
    assert git.remote_url(tmp_path, "origin") == "https://example.com/x.git"


def test_remote_url_missing_remote_returns_none(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    assert git.remote_url(tmp_path, "does-not-exist") is None


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("git@github.com:org/repo.git", "https://github.com/org/repo"),
        ("https://github.com/org/repo.git", "https://GitHub.com/org/repo/"),
        ("ssh://git@github.com/org/repo.git", "git@github.com:org/repo"),
        ("file:///tmp/foo/repo.git", "/tmp/foo/repo.git"),
        ("/tmp/foo/../foo/repo.git", "/tmp/foo/repo.git"),
        ("file:///tmp/foo/bar/../repo.git", "/tmp/foo/repo.git"),
    ],
)
def test_normalize_remote_url_treats_equivalent_forms_as_equal(left: str, right: str) -> None:
    assert git.normalize_remote_url(left) == git.normalize_remote_url(right)


def test_normalize_remote_url_treats_different_repos_as_different() -> None:
    assert git.normalize_remote_url("git@github.com:org/repo.git") != git.normalize_remote_url(
        "git@github.com:org/other-repo.git",
    )


def test_normalize_remote_url_treats_different_local_paths_as_different() -> None:
    """Path-traversal normalization must not accidentally merge distinct repos."""
    assert git.normalize_remote_url("/tmp/foo/repo.git") != git.normalize_remote_url(
        "/tmp/foo/other-repo.git",
    )


def test_primary_remote_conflict_detects_conflict(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://example.com/x.git"],
        cwd=tmp_path,
        check=True,
    )
    assert git.primary_remote_conflict(tmp_path, "https://example.com/x.git", "origin") == (
        "--remote 'https://example.com/x.git' resolves to the same URL as origin "
        "(https://example.com/x.git)."
    )


def test_primary_remote_conflict_allows_distinct_remote(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://example.com/x.git"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "remote", "add", "gitlab", "https://gitlab.example.org/x.git"],
        cwd=tmp_path,
        check=True,
    )
    assert git.primary_remote_conflict(tmp_path, "gitlab", "origin") is None


def test_primary_remote_conflict_allows_when_primary_remote_unset(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://example.com/x.git"],
        cwd=tmp_path,
        check=True,
    )
    assert git.primary_remote_conflict(tmp_path, "origin", "gitlab") is None


def test_primary_remote_conflict_uses_configured_primary_remote(tmp_path: Path) -> None:
    """A repo with a non-default primary_remote can publish-snapshot to `origin`."""
    _init_repo(tmp_path)
    subprocess.run(
        ["git", "remote", "add", "gitlab", "https://gitlab.example.org/x.git"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/x.git"],
        cwd=tmp_path,
        check=True,
    )
    assert git.primary_remote_conflict(tmp_path, "origin", "gitlab") is None
    assert git.primary_remote_conflict(tmp_path, "gitlab", "gitlab") == (
        "--remote 'gitlab' resolves to the same URL as gitlab (https://gitlab.example.org/x.git)."
    )


def test_unique_snapshot_branch_name_avoids_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _init_repo(tmp_path)
    monkeypatch.setattr(
        git,
        "branch_exists",
        lambda cwd, branch: branch == "rrt-snapshot-tmp-20260705120000",
    )
    name = git.unique_snapshot_branch_name(
        tmp_path,
        now=lambda: dt.datetime(2026, 7, 5, 12, 0, 0, tzinfo=dt.UTC),
    )
    assert name == "rrt-snapshot-tmp-20260705120000-1"


def test_unique_snapshot_branch_name_avoids_multiple_collisions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _init_repo(tmp_path)
    taken = {
        "rrt-snapshot-tmp-20260705120000",
        "rrt-snapshot-tmp-20260705120000-1",
        "rrt-snapshot-tmp-20260705120000-2",
    }
    monkeypatch.setattr(git, "branch_exists", lambda cwd, branch: branch in taken)
    name = git.unique_snapshot_branch_name(
        tmp_path,
        now=lambda: dt.datetime(2026, 7, 5, 12, 0, 0, tzinfo=dt.UTC),
    )
    assert name == "rrt-snapshot-tmp-20260705120000-3"


def test_unique_snapshot_branch_name_default_prefix(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    name = git.unique_snapshot_branch_name(
        tmp_path,
        now=lambda: dt.datetime(2026, 7, 5, 12, 0, 0, tzinfo=dt.UTC),
    )
    assert name == "rrt-snapshot-tmp-20260705120000"
