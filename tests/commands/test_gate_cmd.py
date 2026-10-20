"""`rrt gate run` with real (tiny) commands.

The point of the runner is how real exit codes are judged, so every gate
here executes: `true`, `exit 3`, a pipeline, a missing binary, a timeout.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from repo_release_tools.commands import gate_cmd
from repo_release_tools.config import GateSpec

_BASE = """\
[project]
name = "x"
version = "0.1.0"

[tool.rrt]

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"
"""

_GATES = """
[[tool.rrt.gates]]
name = "ok"
run = "true"

[[tool.rrt.gates]]
name = "seeded"
run = "echo boom >&2; exit 3"
expect = 3
description = "must stay red"
"""


def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, gates: str = _GATES) -> Path:
    (tmp_path / "pyproject.toml").write_text(_BASE + gates, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _run(*names: str, dry_run: bool = False) -> int:
    return gate_cmd.cmd_gate_run(argparse.Namespace(names=list(names), dry_run=dry_run, verbose=0))


def test_deliberately_red_line_passes_when_red(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _project(tmp_path, monkeypatch)
    assert _run() == 0
    out = capsys.readouterr().out
    assert "seeded" in out and "as expected" in out
    assert "All 2 gate line(s) matched their expected exit." in out


def test_every_line_runs_after_a_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gates = """
[[tool.rrt.gates]]
name = "first-fails"
run = "echo nope; exit 1"

[[tool.rrt.gates]]
name = "second-runs"
run = "touch ran.marker"
"""
    root = _project(tmp_path, monkeypatch, gates)
    assert _run() == 1
    assert (root / "ran.marker").exists()
    captured = capsys.readouterr()
    assert "1 of 2 gate line(s) did not match." in captured.out
    assert "first-fails: unexpected exit" in captured.err
    assert "nope" in captured.err


def test_pipeline_reports_first_failing_element(tmp_path: Path) -> None:
    result = gate_cmd.run_gate(tmp_path, GateSpec(name="p", run="false | tail -1"))
    assert result.exit == 1
    assert result.ok is False


def test_argv_form_runs_without_a_shell(tmp_path: Path) -> None:
    result = gate_cmd.run_gate(tmp_path, GateSpec(name="a", run=("sh", "-c", "exit 4"), expect=4))
    assert (result.exit, result.ok, result.command) == (4, True, "sh -c 'exit 4'")


def test_missing_executable_is_an_error_row(tmp_path: Path) -> None:
    result = gate_cmd.run_gate(tmp_path, GateSpec(name="m", run=("no-such-binary-rrt",)))
    assert result.exit is None
    assert result.ok is False
    assert result.error == "command not found: no-such-binary-rrt"


def test_timeout_is_an_error_row(tmp_path: Path) -> None:
    result = gate_cmd.run_gate(tmp_path, GateSpec(name="t", run="sleep 5", timeout=0.2))
    assert result.exit is None
    assert result.error == "timed out after 0.2s"


def test_report_table_and_error_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gates = """
[[tool.rrt.gates]]
name = "missing"
run = ["no-such-binary-rrt"]
"""
    _project(tmp_path, monkeypatch, gates)
    assert _run() == 1
    captured = capsys.readouterr()
    assert "│ missing │ 0        │ -      │" in captured.out
    assert "error" in captured.out
    assert "command not found" in captured.err


def test_named_subset_in_config_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _project(tmp_path, monkeypatch)
    assert _run("seeded") == 0
    out = capsys.readouterr().out
    assert "Lines: 1" in out
    assert "│ ok " not in out


def test_unknown_gate_name_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _project(tmp_path, monkeypatch)
    assert _run("nope", "ok") == 1
    assert "Unknown gate(s): nope. Available: ok, seeded" in capsys.readouterr().err


def test_unknown_gate_with_nothing_configured() -> None:
    with pytest.raises(ValueError, match="Available: none configured"):
        gate_cmd.select_gates((), ["x"])


def test_no_gates_configured_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _project(tmp_path, monkeypatch, gates="")
    assert _run() == 1
    assert "No [[tool.rrt.gates]] lines are configured." in capsys.readouterr().err


def test_dry_run_executes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gates = _GATES + '\n[[tool.rrt.gates]]\nname = "marker"\nrun = "touch ran.marker"\n'
    root = _project(tmp_path, monkeypatch, gates)
    assert _run(dry_run=True) == 0
    assert not (root / "ran.marker").exists()
    out = capsys.readouterr().out
    assert "[DRY RUN] Gate run" in out
    assert "echo boom >&2; exit 3  # expect exit 3" in out
    assert "must stay red" in out
    assert "[dry-run] complete" in out


def test_parser_wiring() -> None:
    from repo_release_tools.cli import build_parser

    args = build_parser().parse_args(["gate", "run", "a", "b", "--dry-run"])
    assert args.handler is gate_cmd.cmd_gate_run
    assert args.names == ["a", "b"]
    assert args.dry_run is True
