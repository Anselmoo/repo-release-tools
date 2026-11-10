"""Tests for the `rrt_arch_check` MCP tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

pytest.importorskip("fastmcp", reason="[mcp] extra not installed")

from repo_release_tools.mcp.models import ArchCheckResponse
from repo_release_tools.mcp.tools.arch_tools import register
from repo_release_tools.state import write_arch_baseline

_PYPROJECT = """\
[project]
name = "demo"
version = "0.1.0"

[tool.rrt]

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[tool.rrt.architecture]
root = "src/pkg"
top_level_files = ["__init__.py"]
layers = ["api", "core"]

[[tool.rrt.architecture.units]]
name = "api"
role = "door"

[[tool.rrt.architecture.units]]
name = "core"
"""

_LAYER_ID = "layer-import:src/pkg/core/__init__.py -> src/pkg/api/__init__.py"


class _CaptureMCP:
    def __init__(self) -> None:
        self._tools: dict[str, Any] = {}

    def tool(self, *_args: Any, **_kwargs: Any) -> Any:
        def decorator(fn: Any) -> Any:
            self._tools[fn.__name__] = fn
            return fn

        return decorator


def _write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _repo(root: Path, *, planted: bool = False) -> Path:
    _write(root / "pyproject.toml", _PYPROJECT)
    pkg = root / "src" / "pkg"
    _write(pkg / "__init__.py")
    _write(pkg / "api" / "__init__.py", "from pkg import core\n")
    _write(pkg / "core" / "__init__.py", "from pkg import api\n" if planted else "")
    return root


def _check(server_root: Path, **kwargs: Any) -> ArchCheckResponse:
    mcp = _CaptureMCP()
    register(mcp)  # ty: ignore[invalid-argument-type]
    ctx = MagicMock()
    ctx.lifespan_context = {"root": server_root, "config": None}
    return mcp._tools["rrt_arch_check"](ctx, **kwargs)


def test_clean_tree_is_ok(tmp_path: Path) -> None:
    result = _check(_repo(tmp_path), strict=True)
    assert result.ok is True
    assert result.exit_code == 0
    assert result.findings == []
    assert result.root == "src/pkg"
    assert result.baseline is None
    assert result.templates is None


def test_new_finding_is_advisory_unless_strict(tmp_path: Path) -> None:
    repo = _repo(tmp_path, planted=True)
    advisory = _check(repo)
    assert advisory.ok is True and advisory.exit_code == 0
    [finding] = advisory.findings
    assert finding.id == _LAYER_ID
    assert finding.kind == "layer-import"
    assert finding.path == _LAYER_ID.split(":", 1)[1]
    assert finding.status == "new"
    assert "src/pkg/core/__init__.py" in finding.message
    strict = _check(repo, strict=True)
    assert strict.ok is False and strict.exit_code == 1
    assert (strict.new_count, strict.baselined_count, strict.stale_count) == (1, 0, 0)


def test_baselined_and_stale_entries(tmp_path: Path) -> None:
    repo = _repo(tmp_path, planted=True)
    write_arch_baseline(
        repo / ".rrt" / "architecture.baseline.toml", [_LAYER_ID, "undeclared:src/pkg/gone.py"]
    )
    result = _check(repo, strict=True)
    statuses = {f.id: f.status for f in result.findings}
    assert statuses == {_LAYER_ID: "baselined", "undeclared:src/pkg/gone.py": "stale"}
    stale = next(f for f in result.findings if f.status == "stale")
    assert (stale.kind, stale.path) == ("undeclared", "src/pkg/gone.py")
    assert result.baseline == ".rrt/architecture.baseline.toml"
    assert (result.new_count, result.baselined_count, result.stale_count) == (0, 1, 1)
    assert result.exit_code == 1  # a stale entry fails --strict, as on the CLI


def test_relative_root_resolves_against_the_server_root(tmp_path: Path) -> None:
    _repo(tmp_path / "sub", planted=True)
    result = _check(tmp_path, root="sub", strict=True)
    assert result.exit_code == 1
    assert result.findings[0].id == _LAYER_ID


def test_missing_config_is_an_error(tmp_path: Path) -> None:
    _write(tmp_path / "pyproject.toml", _PYPROJECT.split("[tool.rrt.architecture]")[0])
    result = _check(tmp_path)
    assert result.ok is False
    assert result.exit_code == 1
    assert result.error == "[tool.rrt.architecture] is not configured."


def test_missing_root_is_an_error(tmp_path: Path) -> None:
    _write(tmp_path / "pyproject.toml", _PYPROJECT)
    result = _check(tmp_path)
    assert result.error == "Architecture root 'src/pkg' does not exist."


def test_check_templates_reports_each_kind(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    for name, body in (("good", "X = '$name'\n"), ("bad", "def broken(:\n")):
        kind = repo / ".rrt" / "templates" / name
        _write(kind / "kind.toml", f'description = "{name}"\n')
        _write(kind / "files" / "${root}" / "${name}.py.tmpl", body)
    result = _check(repo, check_templates=True)
    assert result.templates is not None
    assert [(t.kind, t.ok) for t in result.templates] == [("bad", False), ("good", True)]
    assert result.templates[0].problems
    assert result.exit_code == 1  # a failed kind fails even without strict
    assert result.ok is False


def test_check_templates_with_no_kinds_is_ok(tmp_path: Path) -> None:
    result = _check(_repo(tmp_path), check_templates=True)
    assert result.templates == []
    assert result.ok is True
