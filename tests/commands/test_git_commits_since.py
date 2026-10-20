"""`rrt git commits-since` against a real repository."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import pytest
from repo_fixtures import init_git_repo

from repo_release_tools.commands import git_inspect


def _commit(root: Path, rel: str, text: str, message: str) -> None:
    (root / rel).write_text(text, encoding="utf-8")
    subprocess.run(["git", "add", "--", rel], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", message], cwd=root, check=True, capture_output=True
    )


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root, branch="main")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.1.0"\n\n[tool.rrt]\n\n'
        '[[tool.rrt.version_targets]]\npath = "pyproject.toml"\nkind = "pep621"\n\n'
        '[tool.rrt.git]\ngenerated = ["HANDOFF.md"]\n',
        encoding="utf-8",
    )
    _commit(root, "pyproject.toml", (root / "pyproject.toml").read_text(), "chore: init")
    subprocess.run(["git", "tag", "base"], cwd=root, check=True, capture_output=True)
    _commit(root, "app.py", "one\n", "feat: one")
    _commit(root, "HANDOFF.md", "head\n", "docs: handoff")
    monkeypatch.chdir(root)
    return root


def _run(ref: str, **kwargs: object) -> int:
    return git_inspect.cmd_commits_since(argparse.Namespace(verbose=0, ref=ref, **kwargs))


def test_lists_commits_with_header(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _run("base") == 0
    out = capsys.readouterr().out
    assert "Commits since base" in out
    assert "Count: 2" in out
    assert "Excluded: nothing" in out
    assert "feat: one" in out and "docs: handoff" in out


def test_exclude_and_count(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _run("base", exclude=["HANDOFF.md"], count=True) == 0
    assert capsys.readouterr().out.strip() == "1"


def test_exclude_generated_reads_config(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _run("base", exclude_generated=True) == 0
    out = capsys.readouterr().out
    assert "Excluded: HANDOFF.md" in out
    assert "docs: handoff" not in out


def test_up_to_date(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _run("HEAD") == 0
    assert "HEAD has no commits beyond HEAD" in capsys.readouterr().out


def test_unknown_ref_exits_1(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _run("missing", count=True) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "exit 128" in captured.err


def test_option_like_ref_exits_1(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _run("--all") == 1
    assert "must not start with '-'" in capsys.readouterr().err


def test_outside_repo_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert _run("HEAD") == 1
    assert "is not inside a Git work tree" in capsys.readouterr().err


def test_parser_wiring() -> None:
    from repo_release_tools.cli import build_parser

    args = build_parser().parse_args(
        ["git", "commits-since", "v1", "--exclude", "a", "--exclude", "b", "--count"]
    )
    assert args.handler is git_inspect.cmd_commits_since
    assert args.exclude == ["a", "b"]
    assert args.count is True
    assert args.exclude_generated is False
