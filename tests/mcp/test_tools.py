"""Tests for all MCP tool registrations (tools/*.py and tools/__init__.py)."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("fastmcp", reason="[mcp] extra not installed")

from repo_release_tools.mcp.models import (
    BranchResult,
    BranchValidationResult,
    ChangelogResponse,
    CommitValidationResult,
    ConfigError,
    DoctorResponse,
    LockError,
)
from repo_release_tools.mcp.tools import register_tools
from repo_release_tools.mcp.tools.changelog_tools import register as register_changelog
from repo_release_tools.mcp.tools.config_tools import _path_to_str
from repo_release_tools.mcp.tools.config_tools import register as register_config
from repo_release_tools.mcp.tools.git_tools import register as register_git
from repo_release_tools.mcp.tools.lock_tools import register as register_locks
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
    with (
        patch("repo_release_tools.commands.doctor._check_text_integration", return_value=ok_check),
        patch("repo_release_tools.commands.doctor._check_husky", return_value=ok_check),
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


def test_rrt_bump_dry_run(tmp_path: Path) -> None:
    tools = _ver_tools(tmp_path)
    mock_group = MagicMock()
    mock_group.name = "main"
    mock_group.primary_target.return_value = MagicMock()
    mock_config = MagicMock()
    mock_config.version_groups = [mock_group]
    ctx = _ctx(tmp_path, config=mock_config)

    async def _run() -> Any:
        with patch("repo_release_tools.version.targets.read_version_string", return_value="1.0.0"):
            return await tools["rrt_bump"](ctx, level="patch", dry_run=True)

    result = asyncio.run(_run())
    assert isinstance(result, list)
    assert result[0].dry_run is True
    assert result[0].applied is False
    assert ctx.report_progress.await_count >= 1


def test_rrt_bump_applied(tmp_path: Path) -> None:
    tools = _ver_tools(tmp_path)
    mock_group = MagicMock()
    mock_group.name = "main"
    mock_group.primary_target.return_value = MagicMock()
    mock_group.version_targets = [MagicMock()]
    mock_config = MagicMock()
    mock_config.version_groups = [mock_group]
    ctx = _ctx(tmp_path, config=mock_config)

    async def _run() -> Any:
        with (
            patch("repo_release_tools.version.targets.read_version_string", return_value="1.0.0"),
            patch("repo_release_tools.version.targets.replace_version_in_file"),
        ):
            return await tools["rrt_bump"](ctx, level="patch", dry_run=False)

    result = asyncio.run(_run())
    assert result[0].applied is True


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
