"""Tests for MCP PrefabApp dashboards and helper functions (apps.py)."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("fastmcp", reason="[mcp] extra not installed")

from prefab_ui.app import PrefabApp

from repo_release_tools.mcp.apps import (
    RrtInitForm,
    _badge_variant,
    _overall_badge,
    _severity_icon,
    register_apps,
)

pytestmark = pytest.mark.mcp

# ── helpers ───────────────────────────────────────────────────────────────────


class _CaptureMCP:
    def __init__(self) -> None:
        self._tools: dict[str, Any] = {}

    def tool(self, *args: Any, **kwargs: Any) -> Any:
        def decorator(fn: Any) -> Any:
            self._tools[fn.__name__] = fn
            return fn

        return decorator

    def add_provider(self, *args: Any, **kwargs: Any) -> None:
        pass


def _ctx(tmp_path: Path, config: Any = None) -> MagicMock:
    ctx = MagicMock()
    ctx.lifespan_context = {"root": tmp_path, "config": config}
    ctx.info = AsyncMock()
    ctx.warning = AsyncMock()
    ctx.report_progress = AsyncMock()
    return ctx


def _registered(tmp_path: Path) -> dict[str, Any]:
    mcp: _CaptureMCP = _CaptureMCP()
    register_apps(mcp)  # ty: ignore[invalid-argument-type]
    return mcp._tools


# ── _severity_icon ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "sev, expected",
    [("ok", "✓"), ("warning", "⚠"), ("error", "✗"), ("unknown", "?")],
)
def test_severity_icon(sev: str, expected: str) -> None:
    assert _severity_icon(sev) == expected


# ── _badge_variant ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "sev, expected",
    [("ok", "success"), ("warning", "warning"), ("error", "destructive"), ("other", "secondary")],
)
def test_badge_variant(sev: str, expected: str) -> None:
    assert _badge_variant(sev) == expected


# ── _overall_badge ────────────────────────────────────────────────────────────


def test_overall_badge_empty() -> None:
    label, variant = _overall_badge([])
    assert label == "All Healthy"
    assert variant == "success"


def test_overall_badge_all_ok() -> None:
    label, variant = _overall_badge(["ok", "ok"])
    assert label == "All Healthy"


def test_overall_badge_warning() -> None:
    label, variant = _overall_badge(["ok", "warning"])
    assert label == "Warnings"
    assert variant == "warning"


def test_overall_badge_error() -> None:
    label, variant = _overall_badge(["ok", "error"])
    assert label == "Errors"
    assert variant == "destructive"


# ── RrtInitForm ───────────────────────────────────────────────────────────────


def test_rrt_init_form_defaults() -> None:
    form = RrtInitForm()
    assert form.target == "rrt-toml"
    assert form.dry_run is True
    assert form.force is False


def test_rrt_init_form_custom() -> None:
    form = RrtInitForm(target="pyproject", dry_run=False, force=True)
    assert form.target == "pyproject"
    assert form.dry_run is False
    assert form.force is True


# ── register_apps ─────────────────────────────────────────────────────────────


def test_register_apps_registers_all_tools(tmp_path: Path) -> None:
    tools = _registered(tmp_path)
    expected = {
        "rrt_health_dashboard",
        "rrt_version_overview",
        "rrt_doctor_dashboard",
        "rrt_tree_dashboard",
        "rrt_init",
        "rrt_init_run",
        "rrt_locks_overview",
    }
    assert expected <= set(tools.keys())


# ── rrt_health_dashboard ──────────────────────────────────────────────────────


def test_health_dashboard_empty_state(tmp_path: Path) -> None:
    tools = _registered(tmp_path)
    ctx = _ctx(tmp_path)
    with patch("repo_release_tools.state.read_lock", return_value={}):
        result = tools["rrt_health_dashboard"](ctx)
    assert isinstance(result, PrefabApp)


def test_health_dashboard_ok_checks(tmp_path: Path) -> None:
    tools = _registered(tmp_path)
    rrt = tmp_path / ".rrt"
    rrt.mkdir()
    (rrt / "health.lock.toml").write_text(
        '[checks]\n[checks.lint]\nstatus = "ok"\nmessage = "pass"\nupdated_at = "now"\n'
    )
    (rrt / "tree.lock.toml").write_text(
        '[snapshot]\ntree_hash = "abc123xyz"\nentry_count = 10\nupdated_at = "now"\n'
    )
    ctx = _ctx(tmp_path)
    result = tools["rrt_health_dashboard"](ctx)
    assert isinstance(result, PrefabApp)


def test_health_dashboard_error_checks(tmp_path: Path) -> None:
    tools = _registered(tmp_path)
    rrt = tmp_path / ".rrt"
    rrt.mkdir()
    (rrt / "health.lock.toml").write_text(
        '[checks]\n[checks.lint]\nstatus = "error"\nmessage = "fail"\n'
    )
    ctx = _ctx(tmp_path)
    result = tools["rrt_health_dashboard"](ctx)
    assert isinstance(result, PrefabApp)


def test_health_dashboard_warning_checks(tmp_path: Path) -> None:
    tools = _registered(tmp_path)
    rrt = tmp_path / ".rrt"
    rrt.mkdir()
    (rrt / "health.lock.toml").write_text(
        '[checks]\n[checks.lint]\nstatus = "warning"\nmessage = "warn"\n'
    )
    (rrt / "artifacts.lock.toml").write_text(
        '[files]\n[files."dist/pkg.whl"]\ndescription = "wheel"\nupdated_at = "now"\n'
    )
    (rrt / "drift.lock.toml").write_text(
        '[sources]\n[sources.src]\nlang = "python"\nupdated_at = "now"\n'
    )
    ctx = _ctx(tmp_path)
    result = tools["rrt_health_dashboard"](ctx)
    assert isinstance(result, PrefabApp)


# ── rrt_version_overview ──────────────────────────────────────────────────────


def test_version_overview_no_config(tmp_path: Path) -> None:
    tools = _registered(tmp_path)
    ctx = _ctx(tmp_path, config=None)
    result = tools["rrt_version_overview"](ctx)
    assert isinstance(result, PrefabApp)


def test_version_overview_with_config(tmp_path: Path) -> None:
    tools = _registered(tmp_path)
    mock_target = MagicMock()
    mock_target.path = tmp_path / "pyproject.toml"
    mock_target.kind = "pep621"
    mock_group = MagicMock()
    mock_group.version_targets = [mock_target]
    mock_config = MagicMock()
    mock_config.version_groups = [mock_group]
    ctx = _ctx(tmp_path, config=mock_config)

    with patch("repo_release_tools.version.targets.read_version_string", return_value="1.2.3"):
        result = tools["rrt_version_overview"](ctx)
    assert isinstance(result, PrefabApp)


def test_version_overview_read_error(tmp_path: Path) -> None:
    tools = _registered(tmp_path)
    mock_target = MagicMock()
    mock_target.path = tmp_path / "pyproject.toml"
    mock_target.kind = "pep621"
    mock_group = MagicMock()
    mock_group.version_targets = [mock_target]
    mock_config = MagicMock()
    mock_config.version_groups = [mock_group]
    ctx = _ctx(tmp_path, config=mock_config)

    with patch(
        "repo_release_tools.version.targets.read_version_string",
        side_effect=RuntimeError("no file"),
    ):
        result = tools["rrt_version_overview"](ctx)
    assert isinstance(result, PrefabApp)


# ── rrt_doctor_dashboard ──────────────────────────────────────────────────────


def test_doctor_dashboard_empty(tmp_path: Path) -> None:
    tools = _registered(tmp_path)
    ctx = _ctx(tmp_path)
    with patch("repo_release_tools.state.read_lock", return_value={}):
        result = tools["rrt_doctor_dashboard"](ctx)
    assert isinstance(result, PrefabApp)


def test_doctor_dashboard_all_ok(tmp_path: Path) -> None:
    tools = _registered(tmp_path)
    ctx = _ctx(tmp_path)
    health_data = {
        "checks": {
            "lint": {"status": "ok", "message": "pass"},
            "test": {"status": "ok", "message": "pass"},
        }
    }
    with patch("repo_release_tools.state.read_lock", return_value=health_data):
        result = tools["rrt_doctor_dashboard"](ctx)
    assert isinstance(result, PrefabApp)


def test_doctor_dashboard_partial_ok(tmp_path: Path) -> None:
    tools = _registered(tmp_path)
    ctx = _ctx(tmp_path)
    health_data = {
        "checks": {
            "lint": {"status": "ok", "message": "pass"},
            "test": {"status": "warning", "message": "slow"},
        }
    }
    with patch("repo_release_tools.state.read_lock", return_value=health_data):
        result = tools["rrt_doctor_dashboard"](ctx)
    assert isinstance(result, PrefabApp)


def test_doctor_dashboard_all_fail(tmp_path: Path) -> None:
    tools = _registered(tmp_path)
    ctx = _ctx(tmp_path)
    health_data = {"checks": {"lint": {"status": "error", "message": "fail"}}}
    with patch("repo_release_tools.state.read_lock", return_value=health_data):
        result = tools["rrt_doctor_dashboard"](ctx)
    assert isinstance(result, PrefabApp)


# ── rrt_tree_dashboard ────────────────────────────────────────────────────────


def test_tree_dashboard_with_snapshot_git_ok(tmp_path: Path) -> None:
    tools = _registered(tmp_path)
    ctx = _ctx(tmp_path)
    tree_data = {
        "snapshot": {
            "tree_hash": "deadbeef12345678",
            "entry_count": 42,
            "updated_at": "2024-01-01",
        }
    }
    fake_proc = MagicMock(stdout="src/foo.py\nsrc/bar.py\n")
    with (
        patch("repo_release_tools.state.read_lock", return_value=tree_data),
        patch("subprocess.run", return_value=fake_proc),
    ):
        result = tools["rrt_tree_dashboard"](ctx)
    assert isinstance(result, PrefabApp)


def test_tree_dashboard_no_snapshot_git_ok(tmp_path: Path) -> None:
    tools = _registered(tmp_path)
    ctx = _ctx(tmp_path)
    fake_proc = MagicMock(stdout="src/a.py\ntests/b.py\n")
    with (
        patch("repo_release_tools.state.read_lock", return_value={}),
        patch("subprocess.run", return_value=fake_proc),
    ):
        result = tools["rrt_tree_dashboard"](ctx)
    assert isinstance(result, PrefabApp)


def test_tree_dashboard_git_fails(tmp_path: Path) -> None:
    tools = _registered(tmp_path)
    ctx = _ctx(tmp_path)
    with (
        patch("repo_release_tools.state.read_lock", return_value={}),
        patch("subprocess.run", side_effect=subprocess.SubprocessError("git not found")),
    ):
        result = tools["rrt_tree_dashboard"](ctx)
    assert isinstance(result, PrefabApp)


# ── rrt_init ─────────────────────────────────────────────────────────────────


def test_rrt_init(tmp_path: Path) -> None:
    tools = _registered(tmp_path)
    ctx = _ctx(tmp_path)
    result = tools["rrt_init"](ctx)
    assert isinstance(result, PrefabApp)


# ── rrt_init_run ──────────────────────────────────────────────────────────────


def test_rrt_init_run_dry_run(tmp_path: Path) -> None:
    tools = _registered(tmp_path)
    ctx = _ctx(tmp_path)
    fake_proc = MagicMock(stdout="Would write .rrt.toml", stderr="", returncode=0)

    async def _run() -> str:
        with patch("subprocess.run", return_value=fake_proc):
            return await tools["rrt_init_run"](ctx)

    result = asyncio.run(_run())
    assert "Would write" in result


def test_rrt_init_run_apply(tmp_path: Path) -> None:
    tools = _registered(tmp_path)
    ctx = _ctx(tmp_path)
    fake_proc = MagicMock(stdout="Wrote .rrt.toml", stderr="", returncode=0)

    async def _run() -> str:
        with patch("subprocess.run", return_value=fake_proc):
            return await tools["rrt_init_run"](ctx, target="rrt-toml", dry_run=False, force=False)

    result = asyncio.run(_run())
    assert "Wrote" in result


def test_rrt_init_run_with_stderr(tmp_path: Path) -> None:
    tools = _registered(tmp_path)
    ctx = _ctx(tmp_path)
    fake_proc = MagicMock(stdout="", stderr="some warning", returncode=1)

    async def _run() -> str:
        with patch("subprocess.run", return_value=fake_proc):
            return await tools["rrt_init_run"](ctx)

    result = asyncio.run(_run())
    assert "[stderr]" in result


def test_rrt_init_run_empty_output(tmp_path: Path) -> None:
    tools = _registered(tmp_path)
    ctx = _ctx(tmp_path)
    fake_proc = MagicMock(stdout="", stderr="", returncode=0)

    async def _run() -> str:
        with patch("subprocess.run", return_value=fake_proc):
            return await tools["rrt_init_run"](ctx, force=True)

    result = asyncio.run(_run())
    assert result == "Init complete."


def test_rrt_init_run_nonzero_no_output(tmp_path: Path) -> None:
    tools = _registered(tmp_path)
    ctx = _ctx(tmp_path)
    fake_proc = MagicMock(stdout="", stderr="", returncode=1)

    async def _run() -> str:
        with patch("subprocess.run", return_value=fake_proc):
            return await tools["rrt_init_run"](ctx)

    result = asyncio.run(_run())
    assert "[error]" in result
    assert "1" in result


# ── rrt_locks_overview ────────────────────────────────────────────────────────


def test_locks_overview_empty(tmp_path: Path) -> None:
    tools = _registered(tmp_path)
    ctx = _ctx(tmp_path)
    with patch("repo_release_tools.state.read_lock", return_value={}):
        result = tools["rrt_locks_overview"](ctx)
    assert isinstance(result, PrefabApp)


def test_locks_overview_full_state(tmp_path: Path) -> None:
    tools = _registered(tmp_path)
    ctx = _ctx(tmp_path)
    health_data = {
        "checks": {
            "lint": {"status": "ok", "message": "pass", "updated_at": "now"},
            "ci": {"status": "error", "message": "fail", "updated_at": "now"},
        }
    }
    tree_data = {"snapshot": {"tree_hash": "abc12345", "entry_count": 5, "updated_at": "now"}}
    artifacts_data = {"files": {"dist/x.whl": {"description": "wheel", "updated_at": "now"}}}
    drift_data = {"sources": {"src": {"lang": "python", "updated_at": "now"}}}

    def fake_read_lock(path: Any) -> dict[str, Any]:
        name = str(path)
        if "health" in name:
            return health_data
        if "tree" in name:
            return tree_data
        if "artifact" in name:
            return artifacts_data
        if "drift" in name:
            return drift_data
        return {}

    with patch("repo_release_tools.state.read_lock", side_effect=fake_read_lock):
        result = tools["rrt_locks_overview"](ctx)
    assert isinstance(result, PrefabApp)


def test_locks_overview_warning_only(tmp_path: Path) -> None:
    tools = _registered(tmp_path)
    ctx = _ctx(tmp_path)
    health_data = {
        "checks": {"lint": {"status": "warning", "message": "slow", "updated_at": "now"}}
    }

    with patch(
        "repo_release_tools.state.read_lock",
        side_effect=lambda p: health_data if "health" in str(p) else {},
    ):
        result = tools["rrt_locks_overview"](ctx)
    assert isinstance(result, PrefabApp)
