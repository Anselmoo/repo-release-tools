from __future__ import annotations

import subprocess

from pathlib import Path

from repo_release_tools import git


def test_status_porcelain_preserves_leading_spaces(monkeypatch, tmp_path: Path) -> None:
    def fake_run(cmd, cwd, capture_output, text, check):
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


def test_status_porcelain_raises_on_git_failure(monkeypatch, tmp_path: Path) -> None:
    def fake_run(cmd, cwd, capture_output, text, check):
        return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="fatal")

    monkeypatch.setattr(subprocess, "run", fake_run)

    try:
        git.status_porcelain(tmp_path)
    except RuntimeError as exc:
        assert "git status --short failed" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError")


def test_ref_exists_checks_rev_parse(monkeypatch, tmp_path: Path) -> None:
    def fake_run(cmd, cwd, capture_output, text, check):
        assert cmd == ["git", "rev-parse", "--verify", "--quiet", "HEAD~1"]
        return subprocess.CompletedProcess(cmd, 0, stdout="abc123\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert git.ref_exists(tmp_path, "HEAD~1") is True


def test_in_progress_operation_detects_rebase_and_merge(monkeypatch, tmp_path: Path) -> None:
    rebase_dir = tmp_path / ".git" / "rebase-merge"
    rebase_dir.mkdir(parents=True)
    monkeypatch.setattr(git, "git_dir", lambda cwd: tmp_path / ".git")

    assert git.in_progress_operation(tmp_path) == "rebase"

    rebase_dir.rmdir()
    (tmp_path / ".git" / "MERGE_HEAD").write_text("abc123\n", encoding="utf-8")

    assert git.in_progress_operation(tmp_path) == "merge"
