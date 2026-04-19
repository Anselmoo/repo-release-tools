from __future__ import annotations

import argparse
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
