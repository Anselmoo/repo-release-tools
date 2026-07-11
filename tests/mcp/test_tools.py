"""Tests for all MCP tool registrations (tools/*.py and tools/__init__.py)."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("fastmcp", reason="[mcp] extra not installed")

from repo_release_tools.config import RrtConfig, VersionGroup, VersionTarget
from repo_release_tools.mcp.models import (
    BranchResult,
    BranchValidationResult,
    ChangelogResponse,
    CommitValidationResult,
    ConfigError,
    DoctorResponse,
    LockError,
    PublishSnapshotResult,
)
from repo_release_tools.mcp.tools import publish_tools, register_tools
from repo_release_tools.mcp.tools.changelog_tools import register as register_changelog
from repo_release_tools.mcp.tools.config_tools import _path_to_str
from repo_release_tools.mcp.tools.config_tools import register as register_config
from repo_release_tools.mcp.tools.git_tools import register as register_git
from repo_release_tools.mcp.tools.lock_tools import register as register_locks
from repo_release_tools.mcp.tools.publish_tools import register as register_publish
from repo_release_tools.mcp.tools.validation_tools import register as register_validation
from repo_release_tools.mcp.tools.version_tools import register as register_version

pytestmark = pytest.mark.mcp


# ── shared ────────────────────────────────────────────────────────────────────


class _CaptureMCP:
    def __init__(self) -> None:
        self._tools: dict[str, Any] = {}

    def tool(self, *args: Any, **kwargs: Any) -> Any:
        def decorator(fn: Any) -> Any:
            self._tools[fn.__name__] = fn
            return fn

        return decorator


def _ctx(tmp_path: Path, config: Any = None) -> MagicMock:
    ctx = MagicMock()
    ctx.lifespan_context = {"root": tmp_path, "config": config}
    ctx.info = AsyncMock()
    ctx.warning = AsyncMock()
    ctx.report_progress = AsyncMock()
    return ctx


# ── register_tools ────────────────────────────────────────────────────────────


def test_register_tools_all_present() -> None:
    mcp = _CaptureMCP()
    register_tools(mcp)  # ty: ignore[invalid-argument-type]
    expected = {
        "rrt_config",
        "rrt_doctor",
        "rrt_health",
        "rrt_drift",
        "rrt_tree",
        "rrt_artifacts",
        "rrt_version",
        "rrt_bump",
        "rrt_validate_branch",
        "rrt_validate_commit",
        "rrt_changelog",
        "rrt_branch_new",
    }
    assert expected <= set(mcp._tools.keys())


# ── config_tools._path_to_str ─────────────────────────────────────────────────


def test_path_to_str_config_path() -> None:
    assert _path_to_str(Path("/tmp")) == "/tmp"


def test_path_to_str_config_dict() -> None:
    assert _path_to_str({"k": Path("/x")}) == {"k": "/x"}


def test_path_to_str_config_list() -> None:
    assert _path_to_str([Path("/a"), "b"]) == ["/a", "b"]


def test_path_to_str_config_tuple() -> None:
    assert _path_to_str((Path("/a"),)) == ["/a"]


def test_path_to_str_config_primitive() -> None:
    assert _path_to_str(99) == 99


# ── rrt_config ────────────────────────────────────────────────────────────────


def test_rrt_config_config_error(tmp_path: Path) -> None:
    mcp = _CaptureMCP()
    register_config(mcp)  # ty: ignore[invalid-argument-type]
    ctx = _ctx(tmp_path, config=None)
    ctx.lifespan_context["config_error"] = "bad TOML"
    result = mcp._tools["rrt_config"](ctx)
    assert isinstance(result, ConfigError)
    assert "bad TOML" in result.error


def test_rrt_config_no_config(tmp_path: Path) -> None:
    mcp = _CaptureMCP()
    register_config(mcp)  # ty: ignore[invalid-argument-type]
    ctx = _ctx(tmp_path, config=None)
    result = mcp._tools["rrt_config"](ctx)
    assert isinstance(result, ConfigError)


def test_rrt_config_success(tmp_path: Path) -> None:
    mcp = _CaptureMCP()
    register_config(mcp)  # ty: ignore[invalid-argument-type]
    mock_config = MagicMock()
    ctx = _ctx(tmp_path, config=mock_config)
    with patch(
        "repo_release_tools.mcp.tools.config_tools.asdict", return_value={"version": "1.0.0"}
    ):
        result = mcp._tools["rrt_config"](ctx)
    assert isinstance(result, dict)


def test_rrt_config_error(tmp_path: Path) -> None:
    mcp = _CaptureMCP()
    register_config(mcp)  # ty: ignore[invalid-argument-type]
    mock_config = MagicMock()  # Not a dataclass → asdict() raises TypeError → ConfigError
    ctx = _ctx(tmp_path, config=mock_config)
    with patch("repo_release_tools.mcp.tools.config_tools.asdict", side_effect=Exception("boom")):
        result = mcp._tools["rrt_config"](ctx)
    assert isinstance(result, ConfigError)


# ── rrt_doctor ────────────────────────────────────────────────────────────────


def test_rrt_doctor(tmp_path: Path) -> None:
    mcp = _CaptureMCP()
    register_config(mcp)  # ty: ignore[invalid-argument-type]
    ctx = _ctx(tmp_path)
    ok_check = ("all good", True, "ok")
    hook_checks = {"pre_commit": ok_check, "lefthook": ok_check, "husky": ok_check}
    with (
        patch(
            "repo_release_tools.commands.doctor._check_hook_integrations", return_value=hook_checks
        ),
        patch("repo_release_tools.commands.doctor._check_github_workflows", return_value=ok_check),
    ):
        result = mcp._tools["rrt_doctor"](ctx)
    assert isinstance(result, DoctorResponse)
    assert result.pre_commit.ok


# ── lock tools ────────────────────────────────────────────────────────────────


def _lock_tools(tmp_path: Path) -> dict[str, Any]:
    mcp = _CaptureMCP()
    register_locks(mcp)  # ty: ignore[invalid-argument-type]
    return mcp._tools


def test_rrt_health_empty(tmp_path: Path) -> None:
    tools = _lock_tools(tmp_path)
    ctx = _ctx(tmp_path)
    with patch("repo_release_tools.state.read_lock", return_value={}):
        result = tools["rrt_health"](ctx)
    assert "error" in result


def test_rrt_health_data(tmp_path: Path) -> None:
    tools = _lock_tools(tmp_path)
    ctx = _ctx(tmp_path)
    data = {"checks": {"lint": {"status": "ok"}}}
    with patch("repo_release_tools.state.read_lock", return_value=data):
        result = tools["rrt_health"](ctx)
    assert "checks" in result


def test_rrt_drift_empty(tmp_path: Path) -> None:
    tools = _lock_tools(tmp_path)
    ctx = _ctx(tmp_path)
    with patch("repo_release_tools.state.read_lock", return_value={}):
        result = tools["rrt_drift"](ctx)
    assert "error" in result


def test_rrt_drift_data(tmp_path: Path) -> None:
    tools = _lock_tools(tmp_path)
    ctx = _ctx(tmp_path)
    with patch("repo_release_tools.state.read_lock", return_value={"sources": {}}):
        result = tools["rrt_drift"](ctx)
    assert "sources" in result


def test_rrt_tree_empty(tmp_path: Path) -> None:
    tools = _lock_tools(tmp_path)
    ctx = _ctx(tmp_path)
    with patch("repo_release_tools.state.read_lock", return_value={}):
        result = tools["rrt_tree"](ctx)
    assert "error" in result


def test_rrt_tree_data(tmp_path: Path) -> None:
    tools = _lock_tools(tmp_path)
    ctx = _ctx(tmp_path)
    with patch("repo_release_tools.state.read_lock", return_value={"snapshot": {}}):
        result = tools["rrt_tree"](ctx)
    assert "snapshot" in result


def test_rrt_artifacts_empty(tmp_path: Path) -> None:
    tools = _lock_tools(tmp_path)
    ctx = _ctx(tmp_path)
    with patch("repo_release_tools.state.read_lock", return_value={}):
        result = tools["rrt_artifacts"](ctx)
    assert "error" in result


def test_rrt_artifacts_data(tmp_path: Path) -> None:
    tools = _lock_tools(tmp_path)
    ctx = _ctx(tmp_path)
    with patch("repo_release_tools.state.read_lock", return_value={"files": {}}):
        result = tools["rrt_artifacts"](ctx)
    assert "files" in result


# ── version tools ─────────────────────────────────────────────────────────────


def _ver_tools(tmp_path: Path) -> dict[str, Any]:
    mcp = _CaptureMCP()
    register_version(mcp)  # ty: ignore[invalid-argument-type]
    return mcp._tools


def test_rrt_version_config_error(tmp_path: Path) -> None:
    tools = _ver_tools(tmp_path)
    ctx = _ctx(tmp_path, config=None)
    ctx.lifespan_context["config_error"] = "broken config"
    result = tools["rrt_version"](ctx)
    assert isinstance(result, ConfigError)
    assert "broken config" in result.error


def test_rrt_version_no_config(tmp_path: Path) -> None:
    tools = _ver_tools(tmp_path)
    ctx = _ctx(tmp_path, config=None)
    result = tools["rrt_version"](ctx)
    assert isinstance(result, ConfigError)


def test_rrt_version_with_config(tmp_path: Path) -> None:
    tools = _ver_tools(tmp_path)
    mock_target = MagicMock()
    mock_group = MagicMock()
    mock_group.name = "main"
    mock_group.primary_target.return_value = mock_target
    mock_config = MagicMock()
    mock_config.version_groups = [mock_group]
    ctx = _ctx(tmp_path, config=mock_config)
    with patch("repo_release_tools.version.targets.read_version_string", return_value="1.0.0"):
        result = tools["rrt_version"](ctx)
    assert isinstance(result, list)
    assert result[0].version == "1.0.0"


def test_rrt_version_read_error(tmp_path: Path) -> None:
    tools = _ver_tools(tmp_path)
    mock_group = MagicMock()
    mock_group.name = "main"
    mock_group.primary_target.return_value = MagicMock()
    mock_config = MagicMock()
    mock_config.version_groups = [mock_group]
    ctx = _ctx(tmp_path, config=mock_config)
    with patch(
        "repo_release_tools.version.targets.read_version_string", side_effect=RuntimeError("oops")
    ):
        result = tools["rrt_version"](ctx)
    assert result[0].error is not None


def test_rrt_bump_config_error(tmp_path: Path) -> None:
    tools = _ver_tools(tmp_path)
    ctx = _ctx(tmp_path, config=None)
    ctx.lifespan_context["config_error"] = "broken config"

    async def _run() -> Any:
        return await tools["rrt_bump"](ctx, level="patch")

    result = asyncio.run(_run())
    assert "error" in result
    assert "broken config" in result["error"]


def test_rrt_bump_invalid_level(tmp_path: Path) -> None:
    tools = _ver_tools(tmp_path)
    ctx = _ctx(tmp_path)

    async def _run() -> Any:
        return await tools["rrt_bump"](ctx, level="invalid")

    result = asyncio.run(_run())
    assert "error" in result


def test_rrt_bump_no_config(tmp_path: Path) -> None:
    tools = _ver_tools(tmp_path)
    ctx = _ctx(tmp_path, config=None)

    async def _run() -> Any:
        return await tools["rrt_bump"](ctx, level="patch")

    result = asyncio.run(_run())
    assert "error" in result


def test_rrt_bump_empty_groups_skips_progress(tmp_path: Path) -> None:
    tools = _ver_tools(tmp_path)
    mock_config = MagicMock()
    mock_config.version_groups = []
    ctx = _ctx(tmp_path, config=mock_config)

    async def _run() -> Any:
        return await tools["rrt_bump"](ctx, level="patch")

    result = asyncio.run(_run())
    assert result == []
    ctx.report_progress.assert_not_called()


def _real_group_config(tmp_path: Path, *, name: str = "default") -> tuple[VersionGroup, RrtConfig]:
    """Build a real (non-mock) VersionGroup + RrtConfig backed by a pyproject.toml on disk.

    Used by the rrt_bump tests below to exercise the actual Phase-5 pipeline
    (resolve_bump_target -> apply_bump_files -> update_changelog -> ... ->
    finalize_bump_git) end-to-end, matching how tests/commands/test_bump.py fixtures
    the same functions for the CLI side.
    """
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "fixture"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n### Added\n- something\n",
        encoding="utf-8",
    )
    target = VersionTarget(path=tmp_path / "pyproject.toml", kind="pep621")
    group = VersionGroup(
        name=name,
        release_branch="release/v{version}",
        changelog_file=tmp_path / "CHANGELOG.md",
        lock_command=[],
        generated_files=[],
        version_targets=[target],
        changelog_workflow="incremental",
    )
    config = RrtConfig(
        root=tmp_path,
        config_file=tmp_path / ".rrt.toml",
        version_groups=[group],
        default_group_name=name,
    )
    return group, config


def test_rrt_bump_dry_run(tmp_path: Path) -> None:
    tools = _ver_tools(tmp_path)
    _, config = _real_group_config(tmp_path)
    ctx = _ctx(tmp_path, config=config)

    async def _run() -> Any:
        return await tools["rrt_bump"](ctx, level="patch", dry_run=True)

    result = asyncio.run(_run())
    assert isinstance(result, list)
    assert result[0].current == "1.0.0"
    assert result[0].new == "1.0.1"
    assert result[0].dry_run is True
    assert result[0].applied is False
    assert ctx.report_progress.await_count >= 1

    # dry-run must not touch disk at all (D9 fix: preflight + apply_bump_files both
    # honour dry_run just like the CLI).
    assert "1.0.0" in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert "[Unreleased]" in (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")


def test_rrt_bump_applied(tmp_path: Path) -> None:
    """D9 fix: a non-dry-run MCP bump runs the SAME pipeline as the CLI's cmd_bump.

    Version target, changelog promotion, and git branch/commit all happen -- unlike
    the pre-Phase-5 MCP tool, which only wrote version targets.
    """
    tools = _ver_tools(tmp_path)
    _, config = _real_group_config(tmp_path)
    ctx = _ctx(tmp_path, config=config)

    monkeypatch_calls: list[list[str]] = []

    def fake_run(
        cmd: list[str],
        root: Path,
        *,
        dry_run: bool,
        label: str,
        suppress_announce: bool = False,
    ) -> str:
        monkeypatch_calls.append(cmd)
        return ""

    async def _run() -> Any:
        with (
            patch("repo_release_tools.commands.bump.git.working_tree_clean", return_value=True),
            patch("repo_release_tools.commands.bump.git.branch_exists", return_value=False),
            patch("repo_release_tools.commands.bump.git.current_branch", return_value="main"),
            patch("repo_release_tools.commands.bump.git.run", side_effect=fake_run),
        ):
            return await tools["rrt_bump"](ctx, level="patch", dry_run=False)

    result = asyncio.run(_run())
    assert result[0].error is None, result[0]
    assert result[0].applied is True
    assert result[0].new == "1.0.1"

    # Version target updated on disk.
    assert "1.0.1" in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    # Changelog promoted -- the D9 fix: this file was never touched by the old tool.
    changelog_text = (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "[1.0.1]" in changelog_text

    # Git branch + commit stage happened via finalize_bump_git -- the D9 fix.
    assert ["git", "checkout", "-b", "release/v1.0.1"] in monkeypatch_calls
    assert any(cmd[:2] == ["git", "commit"] for cmd in monkeypatch_calls)


def test_rrt_bump_existing_release_branch_returns_error(tmp_path: Path) -> None:
    """A non-dry-run bump refuses to proceed when the release branch already exists."""
    tools = _ver_tools(tmp_path)
    _, config = _real_group_config(tmp_path)
    ctx = _ctx(tmp_path, config=config)

    async def _run() -> Any:
        with (
            patch("repo_release_tools.commands.bump.git.working_tree_clean", return_value=True),
            patch("repo_release_tools.commands.bump.git.branch_exists", return_value=True),
            patch("repo_release_tools.commands.bump.git.current_branch", return_value="main"),
        ):
            return await tools["rrt_bump"](ctx, level="patch", dry_run=False)

    result = asyncio.run(_run())
    assert result[0].error is not None
    assert "already exists" in result[0].error
    # No files should have been touched -- the error is raised before apply_bump_files.
    assert "1.0.0" in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")


def test_rrt_bump_runs_lock_command_when_configured(tmp_path: Path) -> None:
    """When a group configures ``lock_command``, the MCP bump refreshes it like the CLI."""
    tools = _ver_tools(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "fixture"\nversion = "1.0.0"\n', encoding="utf-8"
    )
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## [Unreleased]\n", encoding="utf-8")
    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=tmp_path / "CHANGELOG.md",
        lock_command=["echo", "locking"],
        generated_files=[],
        version_targets=[VersionTarget(path=tmp_path / "pyproject.toml", kind="pep621")],
        changelog_workflow="incremental",
    )
    config = RrtConfig(
        root=tmp_path,
        config_file=tmp_path / ".rrt.toml",
        version_groups=[group],
        default_group_name="default",
    )
    ctx = _ctx(tmp_path, config=config)

    async def _run() -> Any:
        with patch("repo_release_tools.commands.bump.refresh_bump_lockfile") as mock_refresh:
            return await tools["rrt_bump"](ctx, level="patch", dry_run=True), mock_refresh

    result, mock_refresh = asyncio.run(_run())
    assert result[0].error is None, result[0]
    mock_refresh.assert_called_once()
    assert mock_refresh.call_args.kwargs["dry_run"] is True


def test_rrt_bump_generated_asset_failure_returns_error(tmp_path: Path) -> None:
    """A generated-asset refresh failure surfaces as a per-group error, not a crash."""
    from repo_release_tools.config import GeneratedAsset

    tools = _ver_tools(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "fixture"\nversion = "1.0.0"\n', encoding="utf-8"
    )
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## [Unreleased]\n", encoding="utf-8")
    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=tmp_path / "CHANGELOG.md",
        lock_command=[],
        generated_files=[],
        version_targets=[VersionTarget(path=tmp_path / "pyproject.toml", kind="pep621")],
        generated_assets=[GeneratedAsset(path=Path("out.txt"), command=["true"])],
        changelog_workflow="incremental",
    )
    config = RrtConfig(
        root=tmp_path,
        config_file=tmp_path / ".rrt.toml",
        version_groups=[group],
        default_group_name="default",
    )
    ctx = _ctx(tmp_path, config=config)

    async def _run() -> Any:
        with patch(
            "repo_release_tools.commands.bump.refresh_bump_generated_assets", return_value=False
        ):
            return await tools["rrt_bump"](ctx, level="patch", dry_run=True)

    result = asyncio.run(_run())
    assert result[0].error is not None
    assert "Generated asset refresh failed" in result[0].error


def test_rrt_bump_group_filter_selects_one_group(tmp_path: Path) -> None:
    """The new ``group`` parameter restricts the bump to a single named version group."""
    tools = _ver_tools(tmp_path)
    target_a = VersionTarget(path=tmp_path / "a.json", kind="package_json")
    target_b = VersionTarget(path=tmp_path / "b.json", kind="package_json")
    (tmp_path / "a.json").write_text('{"name": "a", "version": "1.0.0"}\n', encoding="utf-8")
    (tmp_path / "b.json").write_text('{"name": "b", "version": "2.0.0"}\n', encoding="utf-8")
    group_a = VersionGroup(
        name="a",
        release_branch="release/a-v{version}",
        changelog_file=tmp_path / "CHANGELOG.md",
        lock_command=[],
        generated_files=[],
        version_targets=[target_a],
        changelog_workflow="incremental",
    )
    group_b = VersionGroup(
        name="b",
        release_branch="release/b-v{version}",
        changelog_file=tmp_path / "CHANGELOG.md",
        lock_command=[],
        generated_files=[],
        version_targets=[target_b],
        changelog_workflow="incremental",
    )
    config = RrtConfig(
        root=tmp_path,
        config_file=tmp_path / ".rrt.toml",
        version_groups=[group_a, group_b],
        default_group_name="a",
    )
    ctx = _ctx(tmp_path, config=config)

    async def _run() -> Any:
        return await tools["rrt_bump"](ctx, level="patch", dry_run=True, group="b")

    result = asyncio.run(_run())
    assert len(result) == 1
    assert result[0].group == "b"
    assert result[0].current == "2.0.0"
    assert result[0].new == "2.0.1"


def test_rrt_bump_unknown_group_returns_error(tmp_path: Path) -> None:
    tools = _ver_tools(tmp_path)
    _, config = _real_group_config(tmp_path)
    ctx = _ctx(tmp_path, config=config)

    async def _run() -> Any:
        return await tools["rrt_bump"](ctx, level="patch", group="does-not-exist")

    result = asyncio.run(_run())
    assert "error" in result
    assert "does-not-exist" in result["error"]


def test_rrt_bump_version_error(tmp_path: Path) -> None:
    tools = _ver_tools(tmp_path)
    mock_group = MagicMock()
    mock_group.name = "main"
    mock_group.primary_target.return_value = MagicMock()
    mock_config = MagicMock()
    mock_config.version_groups = [mock_group]
    ctx = _ctx(tmp_path, config=mock_config)

    async def _run() -> Any:
        with patch(
            "repo_release_tools.version.targets.read_version_string", side_effect=OSError("no file")
        ):
            return await tools["rrt_bump"](ctx, level="minor")

    result = asyncio.run(_run())
    assert result[0].error is not None


# ── validation tools ──────────────────────────────────────────────────────────


def _val_tools(tmp_path: Path) -> dict[str, Any]:
    mcp = _CaptureMCP()
    register_validation(mcp)  # ty: ignore[invalid-argument-type]
    return mcp._tools


def test_rrt_validate_branch_valid(tmp_path: Path) -> None:
    tools = _val_tools(tmp_path)
    ctx = _ctx(tmp_path)
    with (
        patch("repo_release_tools.config.load_extra_branch_types", return_value=()),
        patch("repo_release_tools.workflow.hooks.validate_branch_name", return_value=None),
    ):
        result = tools["rrt_validate_branch"](ctx, branch_name="feat/foo")
    assert isinstance(result, BranchValidationResult)
    assert result.valid is True


def test_rrt_validate_branch_invalid(tmp_path: Path) -> None:
    tools = _val_tools(tmp_path)
    ctx = _ctx(tmp_path)
    with (
        patch("repo_release_tools.config.load_extra_branch_types", return_value=()),
        patch("repo_release_tools.workflow.hooks.validate_branch_name", return_value="bad format"),
    ):
        result = tools["rrt_validate_branch"](ctx, branch_name="bad")
    assert result.valid is False
    assert result.reason == "bad format"


def test_rrt_validate_branch_load_error(tmp_path: Path) -> None:
    tools = _val_tools(tmp_path)
    ctx = _ctx(tmp_path)
    with (
        patch(
            "repo_release_tools.config.load_extra_branch_types",
            side_effect=FileNotFoundError("no file"),
        ),
        patch("repo_release_tools.workflow.hooks.validate_branch_name", return_value=None),
    ):
        result = tools["rrt_validate_branch"](ctx, branch_name="feat/ok")
    assert result.valid is True


def test_rrt_validate_commit_valid(tmp_path: Path) -> None:
    tools = _val_tools(tmp_path)
    ctx = _ctx(tmp_path)
    with (
        patch("repo_release_tools.config.load_extra_branch_types", return_value=()),
        patch("repo_release_tools.workflow.hooks.validate_commit_subject", return_value=None),
    ):
        result = tools["rrt_validate_commit"](ctx, subject="feat: add thing")
    assert isinstance(result, CommitValidationResult)
    assert result.valid is True


def test_rrt_validate_commit_invalid(tmp_path: Path) -> None:
    tools = _val_tools(tmp_path)
    ctx = _ctx(tmp_path)
    with (
        patch("repo_release_tools.config.load_extra_branch_types", return_value=()),
        patch("repo_release_tools.workflow.hooks.validate_commit_subject", return_value="no colon"),
    ):
        result = tools["rrt_validate_commit"](ctx, subject="bad")
    assert result.valid is False


def test_rrt_validate_commit_load_error(tmp_path: Path) -> None:
    tools = _val_tools(tmp_path)
    ctx = _ctx(tmp_path)
    with (
        patch(
            "repo_release_tools.config.load_extra_branch_types",
            side_effect=FileNotFoundError("no file"),
        ),
        patch("repo_release_tools.workflow.hooks.validate_commit_subject", return_value=None),
    ):
        result = tools["rrt_validate_commit"](ctx, subject="feat: good")
    assert result.valid is True


# ── changelog tools ───────────────────────────────────────────────────────────


def _changelog_tools(tmp_path: Path) -> dict[str, Any]:
    mcp = _CaptureMCP()
    register_changelog(mcp)  # ty: ignore[invalid-argument-type]
    return mcp._tools


def test_rrt_changelog_no_config_no_file(tmp_path: Path) -> None:
    tools = _changelog_tools(tmp_path)
    ctx = _ctx(tmp_path, config=None)
    result = tools["rrt_changelog"](ctx)
    assert isinstance(result, LockError)


def test_rrt_changelog_no_config_with_file(tmp_path: Path) -> None:
    tools = _changelog_tools(tmp_path)
    (tmp_path / "CHANGELOG.md").write_text("## Unreleased\n- Added: foo")
    ctx = _ctx(tmp_path, config=None)
    with patch("repo_release_tools.changelog.get_unreleased_entries", return_value=["Added: foo"]):
        result = tools["rrt_changelog"](ctx)
    assert isinstance(result, ChangelogResponse)
    assert result.section == "unreleased"


def test_rrt_changelog_full_section(tmp_path: Path) -> None:
    tools = _changelog_tools(tmp_path)
    (tmp_path / "CHANGELOG.md").write_text("# Full changelog")
    ctx = _ctx(tmp_path, config=None)
    result = tools["rrt_changelog"](ctx, section="full")
    assert isinstance(result, ChangelogResponse)
    assert result.section == "full"
    assert result.content is not None


def test_rrt_changelog_with_config(tmp_path: Path) -> None:
    tools = _changelog_tools(tmp_path)
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("## Unreleased\n- Added: bar")
    mock_group = MagicMock()
    mock_group.changelog_file = changelog
    mock_config = MagicMock()
    mock_config.version_groups = [mock_group]
    ctx = _ctx(tmp_path, config=mock_config)
    with patch("repo_release_tools.changelog.get_unreleased_entries", return_value=["Added: bar"]):
        result = tools["rrt_changelog"](ctx)
    assert isinstance(result, ChangelogResponse)


# ── git tools ─────────────────────────────────────────────────────────────────


def _git_tools(tmp_path: Path) -> dict[str, Any]:
    mcp = _CaptureMCP()
    register_git(mcp)  # ty: ignore[invalid-argument-type]
    return mcp._tools


def test_rrt_branch_new_invalid_type(tmp_path: Path) -> None:
    tools = _git_tools(tmp_path)
    ctx = _ctx(tmp_path)

    async def _run() -> BranchResult:
        return await tools["rrt_branch_new"](ctx, commit_type="invalid", description="foo")

    result = asyncio.run(_run())
    assert result.created is False
    assert result.error is not None


def test_rrt_branch_new_dry_run(tmp_path: Path) -> None:
    tools = _git_tools(tmp_path)
    ctx = _ctx(tmp_path)

    async def _run() -> BranchResult:
        return await tools["rrt_branch_new"](
            ctx, commit_type="feat", description="add thing", dry_run=True
        )

    result = asyncio.run(_run())
    assert result.dry_run is True
    assert result.created is False
    assert "feat" in result.branch


def test_rrt_branch_new_with_scope(tmp_path: Path) -> None:
    tools = _git_tools(tmp_path)
    ctx = _ctx(tmp_path)

    async def _run() -> BranchResult:
        return await tools["rrt_branch_new"](
            ctx, commit_type="fix", description="crash on load", scope="cli", dry_run=True
        )

    result = asyncio.run(_run())
    assert result.dry_run is True
    assert "fix" in result.branch


def test_rrt_branch_new_apply_success(tmp_path: Path) -> None:
    tools = _git_tools(tmp_path)
    ctx = _ctx(tmp_path)
    mock_run = MagicMock(return_value=MagicMock(returncode=0, stdout="", stderr=""))

    async def _run() -> BranchResult:
        with (
            patch("repo_release_tools.workflow.git.branch_exists", return_value=False),
            patch("subprocess.run", mock_run),
        ):
            return await tools["rrt_branch_new"](
                ctx, commit_type="feat", description="new feature", dry_run=False
            )

    result = asyncio.run(_run())
    assert result.created is True
    mock_run.assert_called_once()
    assert mock_run.call_args.args[0] == ["git", "checkout", "-b", result.branch]
    assert mock_run.call_args.kwargs["timeout"] == 8.0
    assert mock_run.call_args.kwargs["capture_output"] is True
    assert mock_run.call_args.kwargs["text"] is True


def test_rrt_branch_new_apply_git_fails(tmp_path: Path) -> None:
    tools = _git_tools(tmp_path)
    ctx = _ctx(tmp_path)

    async def _run() -> BranchResult:
        fake_proc = MagicMock(returncode=1, stdout="", stderr="branch error")
        with (
            patch("repo_release_tools.workflow.git.branch_exists", return_value=False),
            patch("subprocess.run", return_value=fake_proc),
        ):
            return await tools["rrt_branch_new"](
                ctx, commit_type="feat", description="bad branch", dry_run=False
            )

    result = asyncio.run(_run())
    assert result.created is False
    assert result.error is not None
    assert "git checkout -b failed" in result.error


def test_rrt_branch_new_apply_already_exists(tmp_path: Path) -> None:
    tools = _git_tools(tmp_path)
    ctx = _ctx(tmp_path)

    async def _run() -> BranchResult:
        with patch("repo_release_tools.workflow.git.branch_exists", return_value=True):
            return await tools["rrt_branch_new"](
                ctx, commit_type="feat", description="dup", dry_run=False
            )

    result = asyncio.run(_run())
    assert result.created is False
    assert result.error is not None


def test_rrt_branch_new_apply_timeout(tmp_path: Path) -> None:
    tools = _git_tools(tmp_path)
    ctx = _ctx(tmp_path)

    async def _run() -> BranchResult:
        with (
            patch("repo_release_tools.workflow.git.branch_exists", return_value=False),
            patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd=["git", "checkout", "-b"], timeout=8.0),
            ),
        ):
            return await tools["rrt_branch_new"](
                ctx, commit_type="feat", description="slow branch", dry_run=False
            )

    result = asyncio.run(_run())
    assert result.created is False
    assert result.error == "git checkout -b timed out after 8 seconds."


# ── publish snapshot tools ────────────────────────────────────────────────────


def _publish_tools(tmp_path: Path) -> dict[str, Any]:
    mcp = _CaptureMCP()
    register_publish(mcp)  # ty: ignore[invalid-argument-type]
    return mcp._tools


def test_rrt_publish_snapshot_not_a_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(publish_tools.git, "is_git_repository", lambda root: False)
    tools = _publish_tools(tmp_path)
    ctx = _ctx(tmp_path)

    async def _run() -> PublishSnapshotResult:
        return await tools["rrt_publish_snapshot"](
            ctx, remote="mirror", branch="main", dry_run=True
        )

    result = asyncio.run(_run())
    assert result.published is False
    assert result.error is not None
    assert "not inside a Git work tree" in result.error


def test_rrt_publish_snapshot_dry_run_previews(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(publish_tools.git, "is_git_repository", lambda root: True)
    monkeypatch.setattr(
        publish_tools.git,
        "remote_url",
        lambda root, name: {"origin": "https://x/a.git", "mirror": "https://x/b.git"}.get(name),
    )
    monkeypatch.setattr(publish_tools.git, "in_progress_operation", lambda root: None)
    tools = _publish_tools(tmp_path)
    ctx = _ctx(tmp_path)

    async def _run() -> PublishSnapshotResult:
        return await tools["rrt_publish_snapshot"](
            ctx, remote="mirror", branch="main", dry_run=True
        )

    result = asyncio.run(_run())
    assert result.dry_run is True
    assert result.published is False
    assert result.error is None


def test_rrt_publish_snapshot_allows_when_origin_not_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(publish_tools.git, "is_git_repository", lambda root: True)
    monkeypatch.setattr(
        publish_tools.git,
        "remote_url",
        lambda root, name: {"origin": None, "mirror": "https://x/b.git"}.get(name),
    )
    monkeypatch.setattr(publish_tools.git, "in_progress_operation", lambda root: None)
    tools = _publish_tools(tmp_path)
    ctx = _ctx(tmp_path)

    async def _run() -> PublishSnapshotResult:
        return await tools["rrt_publish_snapshot"](
            ctx, remote="mirror", branch="main", dry_run=True
        )

    result = asyncio.run(_run())
    assert result.dry_run is True
    assert result.published is False
    assert result.error is None


def test_rrt_publish_snapshot_rejects_origin_remote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(publish_tools.git, "is_git_repository", lambda root: True)
    monkeypatch.setattr(publish_tools.git, "remote_url", lambda root, name: "https://x/a.git")
    tools = _publish_tools(tmp_path)
    ctx = _ctx(tmp_path)

    async def _run() -> PublishSnapshotResult:
        return await tools["rrt_publish_snapshot"](
            ctx, remote="origin", branch="main", dry_run=True
        )

    result = asyncio.run(_run())
    assert result.published is False
    assert result.error is not None
    assert "origin" in result.error.lower()


def test_rrt_publish_snapshot_allows_origin_when_primary_remote_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A repo with primary_remote = 'gitlab' can publish-snapshot to origin."""
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]
primary_remote = "gitlab"

[[tool.rrt.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(publish_tools.git, "is_git_repository", lambda root: True)
    monkeypatch.setattr(
        publish_tools.git,
        "remote_url",
        lambda root, name: {
            "origin": "https://github.com/org/repo.git",
            "gitlab": "https://gitlab.example.org/org/repo.git",
        }.get(name),
    )
    monkeypatch.setattr(publish_tools.git, "in_progress_operation", lambda root: None)
    tools = _publish_tools(tmp_path)
    ctx = _ctx(tmp_path)

    async def _run() -> PublishSnapshotResult:
        return await tools["rrt_publish_snapshot"](
            ctx, remote="origin", branch="main", dry_run=True
        )

    result = asyncio.run(_run())
    assert result.dry_run is True
    assert result.published is False
    assert result.error is None


def test_rrt_publish_snapshot_allows_raw_url_target_when_primary_remote_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Issue #135's second repro: passing origin's raw URL (not the name 'origin')
    must not be refused either, once a non-default primary_remote is configured."""
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]
primary_remote = "gitlab"

[[tool.rrt.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(publish_tools.git, "is_git_repository", lambda root: True)
    monkeypatch.setattr(
        publish_tools.git,
        "remote_url",
        lambda root, name: {
            "origin": "https://github.com/org/repo.git",
            "gitlab": "https://gitlab.example.org/org/repo.git",
        }.get(name),
    )
    monkeypatch.setattr(publish_tools.git, "in_progress_operation", lambda root: None)
    tools = _publish_tools(tmp_path)
    ctx = _ctx(tmp_path)

    async def _run() -> PublishSnapshotResult:
        return await tools["rrt_publish_snapshot"](
            ctx, remote="https://github.com/org/repo.git", branch="main", dry_run=True
        )

    result = asyncio.run(_run())
    assert result.dry_run is True
    assert result.published is False
    assert result.error is None


def test_rrt_publish_snapshot_in_progress_operation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(publish_tools.git, "is_git_repository", lambda root: True)
    monkeypatch.setattr(
        publish_tools.git,
        "remote_url",
        lambda root, name: {"origin": "https://x/a.git", "mirror": "https://x/b.git"}.get(name),
    )
    monkeypatch.setattr(publish_tools.git, "in_progress_operation", lambda root: "rebase")
    tools = _publish_tools(tmp_path)
    ctx = _ctx(tmp_path)

    async def _run() -> PublishSnapshotResult:
        return await tools["rrt_publish_snapshot"](
            ctx, remote="mirror", branch="main", dry_run=True
        )

    result = asyncio.run(_run())
    assert result.published is False
    assert result.error is not None
    assert "rebase" in result.error


# ── D4/D6 fix: confirm parameter gates the destructive push ──────────────────


def test_rrt_publish_snapshot_dry_run_false_without_confirm_fails_safe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D6 fix: dry_run=False alone (confirm omitted/False) must NOT force-push.

    Mirrors the CLI's two-signal requirement (not-dry-run AND
    --yes-i-know-this-overwrites-remote-history). No git mutation calls should even
    be attempted -- the tool should short-circuit to the dry-run preview branch.
    """
    monkeypatch.setattr(publish_tools.git, "is_git_repository", lambda root: True)
    monkeypatch.setattr(
        publish_tools.git,
        "remote_url",
        lambda root, name: {"origin": "https://x/a.git", "mirror": "https://x/b.git"}.get(name),
    )
    monkeypatch.setattr(publish_tools.git, "in_progress_operation", lambda root: None)
    run_calls: list[list[str]] = []

    def _fake_run(cmd: list[str], root: Path, *, dry_run: bool, label: str) -> str:
        run_calls.append(cmd)
        return ""

    monkeypatch.setattr(publish_tools.git, "run", _fake_run)
    tools = _publish_tools(tmp_path)
    ctx = _ctx(tmp_path)

    async def _run() -> PublishSnapshotResult:
        # confirm intentionally omitted (defaults to False).
        return await tools["rrt_publish_snapshot"](
            ctx, remote="mirror", branch="main", dry_run=False
        )

    result = asyncio.run(_run())
    assert result.published is False
    assert result.dry_run is True
    assert result.error is None
    assert run_calls == [], f"no git mutation commands should run without confirm; got {run_calls}"


def test_rrt_publish_snapshot_confirm_true_without_dry_run_false_still_previews(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D4/D6 fix: confirm=True alone (dry_run defaults to True) must NOT force-push either.

    Both signals are required; confirm=True is not sufficient on its own.
    """
    monkeypatch.setattr(publish_tools.git, "is_git_repository", lambda root: True)
    monkeypatch.setattr(
        publish_tools.git,
        "remote_url",
        lambda root, name: {"origin": "https://x/a.git", "mirror": "https://x/b.git"}.get(name),
    )
    monkeypatch.setattr(publish_tools.git, "in_progress_operation", lambda root: None)
    run_calls: list[list[str]] = []

    def _fake_run(cmd: list[str], root: Path, *, dry_run: bool, label: str) -> str:
        run_calls.append(cmd)
        return ""

    monkeypatch.setattr(publish_tools.git, "run", _fake_run)
    tools = _publish_tools(tmp_path)
    ctx = _ctx(tmp_path)

    async def _run() -> PublishSnapshotResult:
        # dry_run intentionally omitted (defaults to True); confirm=True alone.
        return await tools["rrt_publish_snapshot"](
            ctx, remote="mirror", branch="main", confirm=True
        )

    result = asyncio.run(_run())
    assert result.published is False
    assert result.dry_run is True
    assert run_calls == [], f"confirm=True alone must not push; got {run_calls}"


def test_rrt_publish_snapshot_dry_run_false_and_confirm_true_publishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D4/D6 fix: both dry_run=False AND confirm=True together force-push."""
    monkeypatch.setattr(publish_tools.git, "is_git_repository", lambda root: True)
    monkeypatch.setattr(
        publish_tools.git,
        "remote_url",
        lambda root, name: {"origin": "https://x/a.git", "mirror": "https://x/b.git"}.get(name),
    )
    monkeypatch.setattr(publish_tools.git, "in_progress_operation", lambda root: None)
    monkeypatch.setattr(publish_tools.git, "current_branch", lambda root: "main")
    monkeypatch.setattr(
        publish_tools.git, "unique_snapshot_branch_name", lambda root: "snapshot-tmp"
    )
    run_calls: list[list[str]] = []

    def _fake_run(cmd: list[str], root: Path, *, dry_run: bool, label: str) -> str:
        run_calls.append(cmd)
        return ""

    monkeypatch.setattr(publish_tools.git, "run", _fake_run)
    tools = _publish_tools(tmp_path)
    ctx = _ctx(tmp_path)

    async def _run() -> PublishSnapshotResult:
        return await tools["rrt_publish_snapshot"](
            ctx, remote="mirror", branch="main", dry_run=False, confirm=True
        )

    result = asyncio.run(_run())
    assert result.published is True
    assert result.dry_run is False
    assert any(cmd[:2] == ["git", "push"] for cmd in run_calls)


def test_rrt_publish_snapshot_apply_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(publish_tools.git, "is_git_repository", lambda root: True)
    monkeypatch.setattr(
        publish_tools.git,
        "remote_url",
        lambda root, name: {"origin": "https://x/a.git", "mirror": "https://x/b.git"}.get(name),
    )
    monkeypatch.setattr(publish_tools.git, "in_progress_operation", lambda root: None)
    monkeypatch.setattr(publish_tools.git, "current_branch", lambda root: "main")
    monkeypatch.setattr(
        publish_tools.git, "unique_snapshot_branch_name", lambda root: "snapshot-tmp"
    )
    run_calls: list[list[str]] = []

    def _fake_run(cmd: list[str], root: Path, *, dry_run: bool, label: str) -> str:
        run_calls.append(cmd)
        return ""

    monkeypatch.setattr(publish_tools.git, "run", _fake_run)
    tools = _publish_tools(tmp_path)
    ctx = _ctx(tmp_path)

    async def _run() -> PublishSnapshotResult:
        return await tools["rrt_publish_snapshot"](
            ctx, remote="mirror", branch="main", message="snap", dry_run=False, confirm=True
        )

    result = asyncio.run(_run())
    assert result.published is True
    assert result.dry_run is False
    assert result.error is None
    assert any(cmd[:2] == ["git", "push"] for cmd in run_calls)
    assert any(cmd[:2] == ["git", "checkout"] and cmd[-1] == "main" for cmd in run_calls)
    assert any(cmd[:3] == ["git", "branch", "-D"] for cmd in run_calls)


def test_rrt_publish_snapshot_excludes_matching_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(publish_tools.git, "is_git_repository", lambda root: True)
    monkeypatch.setattr(
        publish_tools.git,
        "remote_url",
        lambda root, name: {"origin": "https://x/a.git", "mirror": "https://x/b.git"}.get(name),
    )
    monkeypatch.setattr(publish_tools.git, "in_progress_operation", lambda root: None)
    monkeypatch.setattr(publish_tools.git, "current_branch", lambda root: "main")
    monkeypatch.setattr(
        publish_tools.git, "unique_snapshot_branch_name", lambda root: "snapshot-tmp"
    )
    monkeypatch.setattr(
        publish_tools.git, "capture", lambda cmd, root: "README.md\ndocs/superpowers/plans/x.md"
    )
    run_calls: list[list[str]] = []

    def _fake_run(cmd: list[str], root: Path, *, dry_run: bool, label: str) -> str:
        run_calls.append(cmd)
        return ""

    monkeypatch.setattr(publish_tools.git, "run", _fake_run)
    tools = _publish_tools(tmp_path)
    ctx = _ctx(tmp_path)

    async def _run() -> PublishSnapshotResult:
        return await tools["rrt_publish_snapshot"](
            ctx,
            remote="mirror",
            branch="main",
            message="snap",
            exclude=["docs/superpowers/*"],
            dry_run=False,
            confirm=True,
        )

    result = asyncio.run(_run())
    assert result.published is True
    assert result.excluded_paths == ("docs/superpowers/plans/x.md",)
    assert ["git", "rm", "-r", "--ignore-unmatch", "--", "docs/superpowers/plans/x.md"] in run_calls


def test_rrt_publish_snapshot_apply_push_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(publish_tools.git, "is_git_repository", lambda root: True)
    monkeypatch.setattr(
        publish_tools.git,
        "remote_url",
        lambda root, name: {"origin": "https://x/a.git", "mirror": "https://x/b.git"}.get(name),
    )
    monkeypatch.setattr(publish_tools.git, "in_progress_operation", lambda root: None)
    monkeypatch.setattr(publish_tools.git, "current_branch", lambda root: "main")
    monkeypatch.setattr(
        publish_tools.git, "unique_snapshot_branch_name", lambda root: "snapshot-tmp"
    )
    cleanup_calls: list[list[str]] = []

    def _fake_run(cmd: list[str], root: Path, *, dry_run: bool, label: str) -> str:
        if cmd[:2] == ["git", "push"]:
            raise RuntimeError("git push --force failed (exit 1): rejected")
        cleanup_calls.append(cmd)
        return ""

    monkeypatch.setattr(publish_tools.git, "run", _fake_run)
    tools = _publish_tools(tmp_path)
    ctx = _ctx(tmp_path)

    async def _run() -> PublishSnapshotResult:
        return await tools["rrt_publish_snapshot"](
            ctx, remote="mirror", branch="main", dry_run=False, confirm=True
        )

    result = asyncio.run(_run())
    assert result.published is False
    assert result.dry_run is False
    assert result.error is not None
    assert "rejected" in result.error
    assert any(cmd[:2] == ["git", "checkout"] for cmd in cleanup_calls)
    assert any(cmd[:3] == ["git", "branch", "-D"] for cmd in cleanup_calls)


def test_rrt_publish_snapshot_cleanup_failure_does_not_mask_push_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed cleanup step must warn, not replace the original push error."""
    monkeypatch.setattr(publish_tools.git, "is_git_repository", lambda root: True)
    monkeypatch.setattr(
        publish_tools.git,
        "remote_url",
        lambda root, name: {"origin": "https://x/a.git", "mirror": "https://x/b.git"}.get(name),
    )
    monkeypatch.setattr(publish_tools.git, "in_progress_operation", lambda root: None)
    monkeypatch.setattr(publish_tools.git, "current_branch", lambda root: "main")
    monkeypatch.setattr(
        publish_tools.git, "unique_snapshot_branch_name", lambda root: "snapshot-tmp"
    )

    def _fake_run(cmd: list[str], root: Path, *, dry_run: bool, label: str) -> str:
        if cmd[:2] == ["git", "push"]:
            raise RuntimeError("git push --force failed (exit 1): rejected")
        if cmd[:2] == ["git", "checkout"] and "--orphan" not in cmd:
            raise RuntimeError("checkout failed (exit 128): could not restore branch")
        if cmd[:2] == ["git", "branch"]:
            raise RuntimeError("branch failed (exit 1): branch not found")
        return ""

    monkeypatch.setattr(publish_tools.git, "run", _fake_run)
    tools = _publish_tools(tmp_path)
    ctx = _ctx(tmp_path)

    async def _run() -> PublishSnapshotResult:
        return await tools["rrt_publish_snapshot"](
            ctx, remote="mirror", branch="main", dry_run=False, confirm=True
        )

    result = asyncio.run(_run())
    assert result.published is False
    assert result.error is not None
    assert "rejected" in result.error
    warned = [call.args[0] for call in ctx.warning.call_args_list]
    assert any("failed to restore branch" in message for message in warned)
    assert any("failed to delete temp branch" in message for message in warned)


def test_rrt_publish_snapshot_cleanup_failure_after_success_still_published(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A published snapshot is still reported as success even if cleanup fails."""
    monkeypatch.setattr(publish_tools.git, "is_git_repository", lambda root: True)
    monkeypatch.setattr(
        publish_tools.git,
        "remote_url",
        lambda root, name: {"origin": "https://x/a.git", "mirror": "https://x/b.git"}.get(name),
    )
    monkeypatch.setattr(publish_tools.git, "in_progress_operation", lambda root: None)
    monkeypatch.setattr(publish_tools.git, "current_branch", lambda root: "main")
    monkeypatch.setattr(
        publish_tools.git, "unique_snapshot_branch_name", lambda root: "snapshot-tmp"
    )

    def _fake_run(cmd: list[str], root: Path, *, dry_run: bool, label: str) -> str:
        if cmd[:2] == ["git", "checkout"] and "--orphan" not in cmd:
            raise RuntimeError("checkout failed (exit 128): could not restore branch")
        if cmd[:2] == ["git", "branch"]:
            raise RuntimeError("branch failed (exit 1): branch not found")
        return ""

    monkeypatch.setattr(publish_tools.git, "run", _fake_run)
    tools = _publish_tools(tmp_path)
    ctx = _ctx(tmp_path)

    async def _run() -> PublishSnapshotResult:
        return await tools["rrt_publish_snapshot"](
            ctx, remote="mirror", branch="main", dry_run=False, confirm=True
        )

    result = asyncio.run(_run())
    assert result.published is True
    assert result.error is None
    warned = [call.args[0] for call in ctx.warning.call_args_list]
    assert any("failed to restore branch" in message for message in warned)
    assert any("failed to delete temp branch" in message for message in warned)
