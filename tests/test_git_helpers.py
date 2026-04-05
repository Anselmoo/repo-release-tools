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
