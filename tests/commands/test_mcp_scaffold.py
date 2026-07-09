"""Tests for the `rrt mcp tool new` scaffolder."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import cast

import pytest

from repo_release_tools.commands import mcp_cmd


def _args(**overrides: object) -> argparse.Namespace:
    base: dict[str, object] = {
        "name": "sample",
        "title": None,
        "description": None,
        "into": None,
        "dry_run": False,
        "force": False,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def test_mcp_tool_new_writes_file_with_register_and_tool(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "sample_tools.py"
    rc = mcp_cmd.cmd_mcp_tool_new(_args(into=str(target)))
    assert rc == 0
    body = target.read_text(encoding="utf-8")
    assert "def register(mcp: FastMCP)" in body
    assert "def rrt_sample(ctx: Context)" in body
    assert "class SampleResponse" in body
    assert "TODO: implement" in body
    assert "Created" in capsys.readouterr().out


def test_mcp_tool_new_default_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    rc = mcp_cmd.cmd_mcp_tool_new(_args(name="my_widget"))
    assert rc == 0
    expected = tmp_path / "src" / "repo_release_tools" / "mcp" / "tools" / "my_widget_tools.py"
    assert expected.exists()
    body = expected.read_text(encoding="utf-8")
    assert "def rrt_my_widget(ctx: Context)" in body
    assert "class MyWidgetResponse" in body


def test_mcp_tool_new_dry_run_does_not_write(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "scratch_tools.py"
    rc = mcp_cmd.cmd_mcp_tool_new(_args(into=str(target), dry_run=True))
    assert rc == 0
    assert not target.exists()
    out = capsys.readouterr().out
    assert "Would write" in out
    assert "def register(mcp: FastMCP)" in out


def test_mcp_tool_new_refuses_existing_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "existing_tools.py"
    target.write_text("old\n", encoding="utf-8")
    rc = mcp_cmd.cmd_mcp_tool_new(_args(name="existing", into=str(target)))
    assert rc == 1
    assert "Refusing to overwrite" in capsys.readouterr().err
    assert target.read_text(encoding="utf-8") == "old\n"


def test_mcp_tool_new_force_overwrites(
    tmp_path: Path,
) -> None:
    target = tmp_path / "force_tools.py"
    target.write_text("old\n", encoding="utf-8")
    rc = mcp_cmd.cmd_mcp_tool_new(_args(name="force", into=str(target), force=True))
    assert rc == 0
    assert "def register(mcp: FastMCP)" in target.read_text(encoding="utf-8")


@pytest.mark.parametrize("bad_name", ["1starts_digit", "Bad-Casing", "kebab-case", ""])
def test_mcp_tool_new_rejects_invalid_names(
    bad_name: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "x_tools.py"
    rc = mcp_cmd.cmd_mcp_tool_new(_args(name=bad_name, into=str(target)))
    assert rc == 1
    assert "Invalid tool name" in capsys.readouterr().err


def test_mcp_tool_new_custom_title_and_description(
    tmp_path: Path,
) -> None:
    target = tmp_path / "rich_tools.py"
    rc = mcp_cmd.cmd_mcp_tool_new(
        _args(
            name="rich",
            title="Rich Renderer",
            description="Renders the chart.",
            into=str(target),
        )
    )
    assert rc == 0
    body = target.read_text(encoding="utf-8")
    assert "'Rich Renderer'" in body or '"Rich Renderer"' in body
    assert "Renders the chart." in body


def test_mcp_default_handlers_print_help_when_no_subcommand(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`rrt mcp` and `rrt mcp tool` with no subcommand print help and exit 1."""
    parser = argparse.ArgumentParser(prog="rrt")
    subparsers = parser.add_subparsers(dest="command")
    mcp_cmd.register(subparsers)

    mcp_parser = subparsers.choices["mcp"]
    handler = mcp_parser.get_default("handler")
    assert handler is not None
    rc = handler(argparse.Namespace())
    assert rc == 1
    assert "mcp" in capsys.readouterr().out

    tool_subparsers_action = next(
        action
        for action in mcp_parser._actions  # type: ignore[attr-defined]
        if isinstance(action, argparse._SubParsersAction)
    )
    tool_parser = cast("argparse.ArgumentParser", tool_subparsers_action.choices["tool"])
    tool_handler = tool_parser.get_default("handler")
    assert tool_handler is not None
    rc = tool_handler(argparse.Namespace())
    assert rc == 1
    assert "tool" in capsys.readouterr().out
