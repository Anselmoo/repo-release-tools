"""Tests for git.py command helpers and dry-run logic."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from repo_release_tools import git


def test_run_dry_run_skips_subprocess(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
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
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_run(
        cmd: list[str], cwd: Path, capture_output: bool, text: bool, check: bool
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
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_run(
        cmd: list[str], cwd: Path, capture_output: bool, text: bool, check: bool
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
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_run(
        cmd: list[str], cwd: Path, capture_output: bool, text: bool, check: bool
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 2, stdout="out line\n", stderr="err line\n")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match=r"git status failed \(exit 2\)"):
        git.run(["git", "status"], tmp_path, dry_run=False, label="git status")

    captured = capsys.readouterr().out
    assert "out line" in captured
    assert "err line" in captured


def test_capture_and_capture_checked_strip_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_run(
        cmd: list[str], cwd: Path, capture_output: bool, text: bool, check: bool
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 0, stdout="  value\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert git.capture(["git", "branch", "--show-current"], tmp_path) == "value"
    assert git.capture_checked(["git", "rev-parse", "HEAD"], tmp_path) == "value"


def test_capture_checked_raises_on_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_run(
        cmd: list[str], cwd: Path, capture_output: bool, text: bool, check: bool
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 7, stdout="", stderr="fatal")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match=r"git rev-parse HEAD failed \(exit 7\)"):
        git.capture_checked(["git", "rev-parse", "HEAD"], tmp_path)


def test_current_branch_branch_exists_and_commits_ahead_delegate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_capture(cmd: list[str], cwd: Path) -> str:
        if cmd == ["git", "branch", "--show-current"]:
            return "feature/current"
        if cmd == ["git", "branch", "--list", "release/v1.2.3"]:
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


def test_working_tree_clean_and_ahead_behind_handle_multiple_outcomes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    responses = iter(
        [
            subprocess.CompletedProcess([], 0, stdout="", stderr=""),
            subprocess.CompletedProcess([], 0, stdout=" M file.py\n", stderr=""),
            subprocess.CompletedProcess([], 0, stdout="3 2\n", stderr=""),
            subprocess.CompletedProcess([], 1, stdout="", stderr="fatal"),
            subprocess.CompletedProcess([], 0, stdout="malformed\n", stderr=""),
        ]
    )

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: next(responses))

    assert git.working_tree_clean(tmp_path) is True
    assert git.working_tree_clean(tmp_path) is False
    assert git.ahead_behind(tmp_path, "origin/main") == (3, 2)
    assert git.ahead_behind(tmp_path, "origin/main") == (0, 0)
    assert git.ahead_behind(tmp_path, "origin/main") == (0, 0)


def test_upstream_branch_returns_value_or_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    responses = iter(
        [
            subprocess.CompletedProcess([], 0, stdout="origin/main\n", stderr=""),
            subprocess.CompletedProcess([], 0, stdout="\n", stderr=""),
            subprocess.CompletedProcess([], 128, stdout="", stderr="fatal"),
        ]
    )

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: next(responses))

    assert git.upstream_branch(tmp_path) == "origin/main"
    assert git.upstream_branch(tmp_path) is None
    assert git.upstream_branch(tmp_path) is None


def test_git_dir_merge_base_remote_names_and_repository_detection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
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
        ]
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
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_run(
        cmd: list[str], cwd: Path, capture_output: bool, text: bool, check: bool
    ) -> subprocess.CompletedProcess[str]:
        assert cmd == ["git", "status", "--short"]
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=" M src/repo_release_tools/cli.py\n?? docs/git-magic.md\n",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    lines = git.status_porcelain(tmp_path)

    assert lines == [" M src/repo_release_tools/cli.py", "?? docs/git-magic.md"]


def test_status_porcelain_raises_on_git_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_run(
        cmd: list[str], cwd: Path, capture_output: bool, text: bool, check: bool
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
        cmd: list[str], cwd: Path, capture_output: bool, text: bool, check: bool
    ) -> subprocess.CompletedProcess[str]:
        assert cmd == ["git", "rev-parse", "--verify", "--quiet", "HEAD~1"]
        return subprocess.CompletedProcess(cmd, 0, stdout="abc123\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert git.ref_exists(tmp_path, "HEAD~1") is True


def test_in_progress_operation_detects_rebase_and_merge(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    rebase_dir = tmp_path / ".git" / "rebase-merge"
    rebase_dir.mkdir(parents=True)
    monkeypatch.setattr(git, "git_dir", lambda cwd: tmp_path / ".git")

    assert git.in_progress_operation(tmp_path) == "rebase"

    rebase_dir.rmdir()
    (tmp_path / ".git" / "MERGE_HEAD").write_text("abc123\n", encoding="utf-8")

    assert git.in_progress_operation(tmp_path) == "merge"
