"""Tests for MCP resource registrations (resources.py)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("fastmcp", reason="[mcp] extra not installed")

from repo_release_tools.mcp.resources import _path_to_str, register_resources

pytestmark = pytest.mark.mcp


class _CaptureMCP:
    def __init__(self) -> None:
        self._resources: dict[str, Any] = {}

    def resource(self, *args: Any, **kwargs: Any) -> Any:
        def decorator(fn: Any) -> Any:
            self._resources[fn.__name__] = fn
            return fn

        return decorator


def _registered() -> dict[str, Any]:
    mcp = _CaptureMCP()
    register_resources(mcp)  # ty: ignore[invalid-argument-type]
    return mcp._resources


# ── _path_to_str ──────────────────────────────────────────────────────────────


def test_path_to_str_path() -> None:
    assert _path_to_str(Path("/tmp/foo")) == "/tmp/foo"


def test_path_to_str_dict() -> None:
    result = _path_to_str({"a": Path("/x"), "b": 1})
    assert result == {"a": "/x", "b": 1}


def test_path_to_str_list() -> None:
    result = _path_to_str([Path("/a"), Path("/b")])
    assert result == ["/a", "/b"]


def test_path_to_str_tuple() -> None:
    result = _path_to_str((Path("/a"),))
    assert result == ["/a"]


def test_path_to_str_primitive() -> None:
    assert _path_to_str(42) == 42
    assert _path_to_str("hello") == "hello"
    assert _path_to_str(None) is None


# ── registration ──────────────────────────────────────────────────────────────


def test_register_resources_all_present() -> None:
    resources = _registered()
    expected = {
        "resource_version",
        "resource_config",
        "resource_config_schema",
        "resource_changelog",
        "resource_lock",
    }
    assert expected == set(resources.keys())


# ── resource_version ──────────────────────────────────────────────────────────


def test_resource_version() -> None:
    resources = _registered()
    result = resources["resource_version"]()
    assert isinstance(result, str)
    assert len(result) > 0


# ── resource_config ───────────────────────────────────────────────────────────


def test_resource_config_success(tmp_path: Path) -> None:
    mock_config = MagicMock()
    mock_config.version_groups = []
    with (
        patch("repo_release_tools.mcp.server._find_repo_root", return_value=tmp_path),
        patch("repo_release_tools.config.load_or_autodetect_config", return_value=mock_config),
        patch("dataclasses.asdict", return_value={"version": "1.0.0"}),
    ):
        resources = _registered()
        result = resources["resource_config"]()
    parsed = json.loads(result)
    assert isinstance(parsed, dict)


def test_resource_config_error(tmp_path: Path) -> None:
    with (
        patch("repo_release_tools.mcp.server._find_repo_root", return_value=tmp_path),
        patch(
            "repo_release_tools.config.load_or_autodetect_config",
            side_effect=FileNotFoundError("not found"),
        ),
    ):
        resources = _registered()
        result = resources["resource_config"]()
    parsed = json.loads(result)
    assert "error" in parsed


# ── resource_config_schema ────────────────────────────────────────────────────


def test_resource_config_schema() -> None:
    resources = _registered()
    with patch(
        "repo_release_tools.commands.config_cmd._load_schema", return_value={"type": "object"}
    ):
        result = resources["resource_config_schema"]()
    parsed = json.loads(result)
    assert parsed == {"type": "object"}


# ── resource_changelog ────────────────────────────────────────────────────────


def test_resource_changelog_exists(tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n## Unreleased\n- Added: thing")
    with patch("repo_release_tools.mcp.server._find_repo_root", return_value=tmp_path):
        resources = _registered()
        result = resources["resource_changelog"]()
    assert "Changelog" in result


def test_resource_changelog_missing(tmp_path: Path) -> None:
    with patch("repo_release_tools.mcp.server._find_repo_root", return_value=tmp_path):
        resources = _registered()
        result = resources["resource_changelog"]()
    assert "No CHANGELOG.md" in result


# ── resource_lock ─────────────────────────────────────────────────────────────


def _make_lock_dir(tmp_path: Path) -> Path:
    rrt = tmp_path / ".rrt"
    rrt.mkdir()
    return rrt


def test_resource_lock_valid_drift(tmp_path: Path) -> None:
    rrt = _make_lock_dir(tmp_path)
    (rrt / "drift.lock.toml").write_text("[sources]\n")
    with patch("repo_release_tools.mcp.server._find_repo_root", return_value=tmp_path):
        resources = _registered()
        result = resources["resource_lock"](name="drift")
    parsed = json.loads(result)
    assert isinstance(parsed, dict)


def test_resource_lock_valid_health(tmp_path: Path) -> None:
    rrt = _make_lock_dir(tmp_path)
    (rrt / "health.lock.toml").write_text("[checks]\n")
    with patch("repo_release_tools.mcp.server._find_repo_root", return_value=tmp_path):
        resources = _registered()
        result = resources["resource_lock"](name="health")
    parsed = json.loads(result)
    assert isinstance(parsed, dict)


def test_resource_lock_valid_tree(tmp_path: Path) -> None:
    _make_lock_dir(tmp_path)
    with patch("repo_release_tools.mcp.server._find_repo_root", return_value=tmp_path):
        resources = _registered()
        result = resources["resource_lock"](name="tree")
    assert isinstance(json.loads(result), dict)


def test_resource_lock_valid_artifacts(tmp_path: Path) -> None:
    rrt = _make_lock_dir(tmp_path)
    (rrt / "artifacts.lock.toml").write_text("[files]\n")
    with patch("repo_release_tools.mcp.server._find_repo_root", return_value=tmp_path):
        resources = _registered()
        result = resources["resource_lock"](name="artifacts")
    parsed = json.loads(result)
    assert isinstance(parsed, dict)


def test_resource_lock_invalid_name() -> None:
    resources = _registered()
    result = resources["resource_lock"](name="bogus")
    parsed = json.loads(result)
    assert "error" in parsed
    assert "bogus" in parsed["error"]
