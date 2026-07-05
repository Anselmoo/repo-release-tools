from __future__ import annotations

import argparse

import pytest

from repo_release_tools.commands import git_cmd, git_commit, git_inspect, git_sync


def test_register_wires_all_three_families(capsys: pytest.CaptureFixture[str]) -> None:
    parser = argparse.ArgumentParser(prog="rrt")
    subparsers = parser.add_subparsers(dest="command")
    git_cmd.register(subparsers)
    args = parser.parse_args(["git", "status"])
    assert args.handler is git_inspect.cmd_status

    args = parser.parse_args(["git", "commit", "hello"])
    assert args.handler is git_commit.cmd_commit

    args = parser.parse_args(["git", "sync"])
    assert args.handler is git_sync.cmd_sync
