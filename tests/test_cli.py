from __future__ import annotations

import argparse
import runpy
import subprocess
import sys

import pytest


from repo_release_tools import cli


def test_module_help_smoke() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "repo_release_tools", "--help"],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0
    assert "repo-release-tools" in result.stdout
    assert "branch" in result.stdout
    assert "bump" in result.stdout
    assert "git" in result.stdout
    assert "init" in result.stdout


def test_build_parser_registers_doctor_command() -> None:
    parser = cli.build_parser()

    args = parser.parse_args(["doctor"])

    assert args.command == "doctor"
    assert args.handler.__name__ == "cmd_doctor"


def test_main_dispatches_to_selected_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeParser:
        def parse_args(self) -> argparse.Namespace:
            return argparse.Namespace(handler=lambda args: 7)

    monkeypatch.setattr(cli, "build_parser", lambda: _FakeParser())

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 7


def test_package_module_executes_main(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []
    monkeypatch.setattr("repo_release_tools.cli.main", lambda: called.append("ran"))

    runpy.run_module("repo_release_tools", run_name="__main__")

    assert called == ["ran"]


def test_cli_module_main_block_exits_with_handler_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        argparse.ArgumentParser,
        "parse_args",
        lambda self: argparse.Namespace(handler=lambda args: 9),
    )

    with pytest.raises(SystemExit) as exc:
        runpy.run_module("repo_release_tools.cli", run_name="__main__")

    assert exc.value.code == 9
