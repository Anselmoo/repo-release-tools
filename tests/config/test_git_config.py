"""Tests for the [tool.rrt.git] and [[tool.rrt.gates]] config sections."""

from __future__ import annotations

from pathlib import Path

import pytest

from repo_release_tools.config import (
    GateSpec,
    GitConfig,
    load_config,
    load_gates,
    load_git_config,
)
from repo_release_tools.config import git_config as gc

_BASE_RRT_CONFIG = """\
[tool.rrt]

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[project]
name = "example"
version = "0.1.0"
"""


def _write_cfg(tmp_path: Path, extra: str = "") -> None:
    (tmp_path / "pyproject.toml").write_text(_BASE_RRT_CONFIG + extra, encoding="utf-8")


# ── [tool.rrt.git] ───────────────────────────────────────────────────────────


def test_git_section_absent_defaults_to_no_generated_paths(tmp_path: Path) -> None:
    _write_cfg(tmp_path)
    cfg = load_config(tmp_path)
    assert cfg.git == GitConfig()
    assert cfg.gates == ()


def test_git_generated_patterns_are_stripped_and_deduplicated(tmp_path: Path) -> None:
    _write_cfg(
        tmp_path,
        '\n[tool.rrt.git]\ngenerated = ["HANDOFF.md", " .rrt/*.lock.toml ", "HANDOFF.md"]\n',
    )
    assert load_config(tmp_path).git.generated == ("HANDOFF.md", ".rrt/*.lock.toml")


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("not-a-table", "tool.rrt.git must be a table"),
        ({"generated": "HANDOFF.md"}, "must be a list of strings"),
        ({"generated": ["ok", 3]}, "must be a list of strings"),
        ({"generated": ["  "]}, "must not contain empty strings"),
    ],
)
def test_load_git_config_rejects_bad_shapes(raw: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        gc._load_git_config(raw)


def test_empty_git_table_has_no_generated_paths() -> None:
    # Compare fields, not instances: the config package swaps itself for
    # core, so a directly imported helper module can see a second model class.
    assert gc._load_git_config({}).generated == ()


def test_load_git_config_helper_without_config_file(tmp_path: Path) -> None:
    assert load_git_config(tmp_path) == GitConfig()


def test_load_git_config_helper_without_tool_rrt_section(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
    assert load_git_config(tmp_path) == GitConfig()


def test_load_git_config_helper_reads_section(tmp_path: Path) -> None:
    _write_cfg(tmp_path, '\n[tool.rrt.git]\ngenerated = ["HANDOFF.md"]\n')
    assert load_git_config(tmp_path).generated == ("HANDOFF.md",)


def test_load_git_config_helper_surfaces_other_errors(tmp_path: Path) -> None:
    _write_cfg(tmp_path, "\n[tool.rrt.git]\ngenerated = 5\n")
    with pytest.raises(ValueError, match=r"Failed to load \[tool.rrt.git\]"):
        load_git_config(tmp_path)


# ── [[tool.rrt.gates]] ───────────────────────────────────────────────────────

_GATES = """
[[tool.rrt.gates]]
name = "unit"
run = "uv run pytest -q | tail -3"

[[tool.rrt.gates]]
name = "seeded-defect"
run = ["uv", "run", "pytest", "tests/test_seeded.py"]
expect = 1
timeout = 30
description = "must stay red until the defect is fixed"
"""


def test_gates_parse_string_and_argv_forms(tmp_path: Path) -> None:
    _write_cfg(tmp_path, _GATES)
    unit, seeded = load_config(tmp_path).gates
    assert unit == GateSpec(name="unit", run="uv run pytest -q | tail -3")
    assert seeded.run == ("uv", "run", "pytest", "tests/test_seeded.py")
    assert seeded.expect == 1
    assert seeded.timeout == 30.0
    assert seeded.description == "must stay red until the defect is fixed"


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({"gates": 1}, "must be an array of tables"),
        ([1], r"tool.rrt.gates\[0\] must be a table"),
        ([{"run": "x"}], r"gates\[0\].name must be a non-empty string"),
        ([{"name": "a"}], r"gates\[0\].run must be a string or a non-empty list"),
        ([{"name": "a", "run": "  "}], r"gates\[0\].run must not be empty"),
        ([{"name": "a", "run": []}], "non-empty list"),
        ([{"name": "a", "run": ["ok", ""]}], "non-empty list"),
        ([{"name": "a", "run": "x", "expect": "1"}], r"expect must be an integer"),
        ([{"name": "a", "run": "x", "expect": True}], r"expect must be an integer"),
        ([{"name": "a", "run": "x", "expect": 256}], "between 0 and 255"),
        ([{"name": "a", "run": "x", "timeout": "1"}], "number of seconds"),
        ([{"name": "a", "run": "x", "timeout": False}], "number of seconds"),
        ([{"name": "a", "run": "x", "timeout": 0}], "timeout must be positive"),
        ([{"name": "a", "run": "x", "description": 1}], r"description must be a string"),
        ([{"name": "a", "run": "x"}, {"name": "a", "run": "y"}], "duplicate gate name"),
    ],
)
def test_load_gates_rejects_bad_shapes(raw: object, message: str) -> None:
    payload = raw["gates"] if isinstance(raw, dict) else raw
    with pytest.raises(ValueError, match=message):
        gc._load_gates(payload)


def test_gate_spec_validate_rejects_programmatic_misuse() -> None:
    with pytest.raises(ValueError, match="gate name must be a non-empty string"):
        GateSpec(name=" ", run="x").validate()
    with pytest.raises(ValueError, match="run must not be empty"):
        GateSpec(name="a", run=()).validate()


def test_load_gates_helper_paths(tmp_path: Path) -> None:
    assert load_gates(tmp_path) == ()
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
    assert load_gates(tmp_path) == ()
    _write_cfg(tmp_path, _GATES)
    assert [gate.name for gate in load_gates(tmp_path)] == ["unit", "seeded-defect"]
    _write_cfg(tmp_path, "\n[[tool.rrt.gates]]\nname = 'a'\n")
    with pytest.raises(ValueError, match=r"Failed to load \[\[tool.rrt.gates\]\]"):
        load_gates(tmp_path)
