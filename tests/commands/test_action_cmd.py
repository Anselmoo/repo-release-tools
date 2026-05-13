from __future__ import annotations

import argparse
from argparse import Namespace
from pathlib import Path

import pytest

from repo_release_tools.commands.action_cmd import WORKFLOW_PATH, cmd_init, register


def test_cmd_init_writes_workflow(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)

    result = cmd_init(Namespace(dry_run=False, force=False))

    assert result == 0
    rendered = (tmp_path / WORKFLOW_PATH).read_text(encoding="utf-8")
    assert "Anselmoo/repo-release-tools@v" in rendered
    assert 'check-branch-name: "true"' in rendered


def test_cmd_init_dry_run_does_not_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    result = cmd_init(Namespace(dry_run=True, force=False))

    captured = capsys.readouterr()
    assert result == 0
    assert not (tmp_path / WORKFLOW_PATH).exists()
    assert "Would update" in captured.out


def test_cmd_init_refuses_existing_file_without_force(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    workflow_path = tmp_path / WORKFLOW_PATH
    workflow_path.parent.mkdir(parents=True)
    workflow_path.write_text("name: old\n", encoding="utf-8")

    result = cmd_init(Namespace(dry_run=False, force=False))

    captured = capsys.readouterr()
    assert result == 1
    assert workflow_path.read_text(encoding="utf-8") == "name: old\n"
    assert "already exists" in captured.err


def test_register_adds_action_init_parser() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    register(subparsers)

    args = parser.parse_args(["action", "init"])

    assert args.command == "action"
    assert args.action_command == "init"
    assert args.handler.__name__ == "cmd_init"
