"""Tests for the `rrt project info` command surface."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from repo_release_tools.commands import project_cmd


def _args(**overrides: object) -> argparse.Namespace:
    base: dict[str, object] = {
        "root": ".",
        "project_format": "text",
        "key": None,
        "output": None,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def _seed_pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """\
[project]
name = "demo"
version = "0.1.0"
description = "A demo project"
authors = [{ name = "Anselm", email = "anselm@example.com" }]
license = { text = "MIT" }

[project.urls]
Homepage = "https://example.com"
""",
        encoding="utf-8",
    )


def test_project_info_text_format(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_pyproject(tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = project_cmd.cmd_project_info(_args())
    out = capsys.readouterr().out
    assert rc == 0
    assert "Name: demo" in out
    assert "Version: 0.1.0" in out
    assert "Description: A demo project" in out
    assert "Anselm <anselm@example.com>" in out
    assert "Homepage: https://example.com" in out


def test_project_info_json_format(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_pyproject(tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = project_cmd.cmd_project_info(_args(project_format="json"))
    out = capsys.readouterr().out
    data = json.loads(out)
    assert rc == 0
    assert data["name"] == "demo"
    assert data["version"] == "0.1.0"
    assert data["urls"] == {"Homepage": "https://example.com"}


def test_project_info_key_filters_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_pyproject(tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = project_cmd.cmd_project_info(_args(key="description"))
    assert rc == 0
    assert capsys.readouterr().out.strip() == "A demo project"


def test_project_info_key_authors_lists_each(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_pyproject(tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = project_cmd.cmd_project_info(_args(key="authors"))
    assert rc == 0
    out = capsys.readouterr().out
    assert "Anselm <anselm@example.com>" in out


def test_project_info_writes_output_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_pyproject(tmp_path)
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "info.txt"
    rc = project_cmd.cmd_project_info(_args(output=str(target)))
    assert rc == 0
    assert capsys.readouterr().out == ""
    assert "Name: demo" in target.read_text(encoding="utf-8")


def test_project_info_unknown_key_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_pyproject(tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = project_cmd.cmd_project_info(_args(key="nope"))
    err = capsys.readouterr().err
    assert rc == 1
    assert "Unknown --key" in err


def test_project_info_root_not_directory_errors(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "file.txt").write_text("", encoding="utf-8")
    rc = project_cmd.cmd_project_info(_args(root=str(tmp_path / "file.txt")))
    assert rc == 1
    assert "not a directory" in capsys.readouterr().err


def test_project_info_key_json_format(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--format json --key description` emits a JSON-encoded value."""
    _seed_pyproject(tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = project_cmd.cmd_project_info(_args(key="description", project_format="json"))
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out == json.dumps("A demo project")


def test_project_info_key_none_value_emits_blank_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Missing scalar fields render as a single newline so consumers see ''."""
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    rc = project_cmd.cmd_project_info(_args(key="description"))
    assert rc == 0
    assert capsys.readouterr().out == "\n"


def test_project_info_key_urls_emits_label_url_pairs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--key urls` renders dict entries one per line."""
    _seed_pyproject(tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = project_cmd.cmd_project_info(_args(key="urls"))
    assert rc == 0
    out = capsys.readouterr().out
    assert "Homepage: https://example.com" in out


def test_project_default_handler_prints_help_when_no_subcommand(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Running `rrt project` with no subcommand prints help and exits 1."""
    import argparse as _argparse

    parser = _argparse.ArgumentParser(prog="rrt")
    subparsers = parser.add_subparsers(dest="command")
    project_cmd.register(subparsers)
    project_parser = subparsers.choices["project"]
    handler = project_parser.get_default("handler")
    assert handler is not None
    rc = handler(_argparse.Namespace())
    assert rc == 1
    assert "project" in capsys.readouterr().out
