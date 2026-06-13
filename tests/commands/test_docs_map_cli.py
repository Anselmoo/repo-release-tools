"""Integration tests for the `rrt docs map` CLI handler."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from repo_release_tools.commands.docs_cmd import _cmd_map, cmd_docs


def _make_repo_with_map(tmp_path: Path, *, with_map: bool = True) -> Path:
    """Create a synthetic repo with optional [tool.rrt.docs.map] config."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / ".rrt").mkdir()
    (repo / "src" / "a").mkdir()
    (repo / "src" / "a" / "m.py").write_text("x = 1\n", encoding="utf-8")
    body = (
        '[project]\nname = "t"\nversion = "0.0.1"\n\n'
        "[tool.rrt.docs]\n"
        "\n[[tool.rrt.version_targets]]\n"
        'path = "pyproject.toml"\nkind = "pep621"\n'
    )
    if with_map:
        body += '\n[tool.rrt.docs.map]\nroot = "src"\n'
    (repo / "pyproject.toml").write_text(body, encoding="utf-8")
    return repo


def test_cmd_map_returns_1_when_map_not_configured(tmp_path: Path) -> None:
    """Without [tool.rrt.docs.map], the command errors with a clear message."""
    repo = _make_repo_with_map(tmp_path, with_map=False)
    args = argparse.Namespace(root=str(repo), check=False, dry_run=False, verbose=0)
    assert _cmd_map(args) == 1


def test_cmd_map_generate_creates_readme(tmp_path: Path) -> None:
    """A successful generate run creates README.md and the lockfile."""
    repo = _make_repo_with_map(tmp_path)
    args = argparse.Namespace(root=str(repo), check=False, dry_run=False, verbose=0)
    assert _cmd_map(args) == 0
    assert (repo / "src" / "a" / "README.md").exists()
    assert (repo / ".rrt" / "docs_map.lock.toml").exists()


def test_cmd_map_dry_run_writes_nothing(tmp_path: Path) -> None:
    """Dry-run mode prints what would happen but writes no files."""
    repo = _make_repo_with_map(tmp_path)
    args = argparse.Namespace(root=str(repo), check=False, dry_run=True, verbose=0)
    assert _cmd_map(args) == 0
    assert not (repo / "src" / "a" / "README.md").exists()
    assert not (repo / ".rrt" / "docs_map.lock.toml").exists()


def test_cmd_map_check_passes_after_generate(tmp_path: Path) -> None:
    """`--check` after a fresh generate returns 0 (no drift)."""
    repo = _make_repo_with_map(tmp_path)
    gen_args = argparse.Namespace(root=str(repo), check=False, dry_run=False, verbose=0)
    assert _cmd_map(gen_args) == 0
    check_args = argparse.Namespace(root=str(repo), check=True, dry_run=False, verbose=0)
    assert _cmd_map(check_args) == 0


def test_cmd_map_check_fails_when_drift_detected(tmp_path: Path) -> None:
    """`--check` with no prior lockfile reports missing-entry drift and returns 1."""
    repo = _make_repo_with_map(tmp_path)
    args = argparse.Namespace(root=str(repo), check=True, dry_run=False, verbose=0)
    assert _cmd_map(args) == 1


def test_cmd_map_check_emits_error_messages(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A failing --check writes a drift summary plus a remediation hint."""
    repo = _make_repo_with_map(tmp_path)
    args = argparse.Namespace(root=str(repo), check=True, dry_run=False, verbose=0)
    _cmd_map(args)
    captured = capsys.readouterr()
    assert "drift item" in captured.err
    assert "missing-entry" in captured.err
    assert "rrt docs map" in captured.err


def test_cmd_docs_routes_map_action(tmp_path: Path) -> None:
    """The top-level `cmd_docs` dispatcher routes `docs_action='map'` to `_cmd_map`."""
    repo = _make_repo_with_map(tmp_path)
    args = argparse.Namespace(
        root=str(repo),
        docs_action="map",
        check=False,
        dry_run=False,
        verbose=0,
    )
    assert cmd_docs(args) == 0
