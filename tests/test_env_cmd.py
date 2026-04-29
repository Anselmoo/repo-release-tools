from __future__ import annotations

import argparse
import json
import sys

from repo_release_tools.commands import env_cmd


def test_cmd_env_outputs_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(sys, "version", "3.12.0 final")
    monkeypatch.setattr(sys, "executable", "/usr/bin/python3")
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setenv("COLORTERM", "truecolor")
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("RRT_COLOR", "standard")

    args = argparse.Namespace(json=True)
    env_cmd.cmd_env(args)

    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert data["Platform"] == "linux"
    assert data["Python"] == "3.12.0"
    assert data["Python executable"] == "/usr/bin/python3"
    assert data["TERM"] == "xterm-256color"
    assert data["RRT_COLOR"] == "standard"


def test_cmd_env_prints_panel_when_json_disabled(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(sys, "version", "3.12.0 final")
    monkeypatch.setattr(sys, "executable", "/usr/bin/python3")
    monkeypatch.setenv("TERM", "xterm")
    monkeypatch.setenv("COLORTERM", "")
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("RRT_COLOR", raising=False)

    panel_calls: list[tuple] = []

    class FakeOutput:
        @staticmethod
        def ok(message: str) -> str:
            return message

        @staticmethod
        def info(message: str) -> str:
            return message

        @staticmethod
        def panel(
            title: str,
            rows: list[tuple[str, str]],
            *,
            style: str = "single",
            expand: bool = False,
            title_mode: str = "border",
        ) -> str:
            panel_calls.append((title, rows, style, title_mode))
            return "PANEL"

    monkeypatch.setattr(env_cmd, "output", FakeOutput)

    args = argparse.Namespace(json=False)
    env_cmd.cmd_env(args)

    captured = capsys.readouterr()
    assert "Environment" in captured.out
    assert not panel_calls
