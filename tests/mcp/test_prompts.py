"""Tests for MCP prompt registrations (prompts.py)."""

from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("fastmcp", reason="[mcp] extra not installed")

from repo_release_tools.mcp.prompts import register_prompts

pytestmark = pytest.mark.mcp


class _CaptureMCP:
    def __init__(self) -> None:
        self._prompts: dict[str, Any] = {}

    def prompt(self, *args: Any, **kwargs: Any) -> Any:
        def decorator(fn: Any) -> Any:
            self._prompts[fn.__name__] = fn
            return fn

        return decorator


def _registered() -> dict[str, Any]:
    mcp = _CaptureMCP()
    register_prompts(mcp)  # ty: ignore[invalid-argument-type]
    return mcp._prompts


# ── registration ──────────────────────────────────────────────────────────────


def test_register_prompts_all_present() -> None:
    prompts = _registered()
    expected = {
        "release_workflow",
        "version_strategy",
        "branch_strategy",
        "commit_message_guide",
        "changelog_entry",
        "config_setup",
        "release_readiness",
    }
    assert expected == set(prompts.keys())


# ── release_workflow ──────────────────────────────────────────────────────────


def test_release_workflow_default() -> None:
    p = _registered()["release_workflow"]
    result = p()
    assert "minor" in result
    assert "rrt bump" in result


def test_release_workflow_custom() -> None:
    p = _registered()["release_workflow"]
    result = p(version_level="major", repo_name="my-repo")
    assert "major" in result
    assert "my-repo" in result


# ── version_strategy ──────────────────────────────────────────────────────────


def test_version_strategy_default() -> None:
    p = _registered()["version_strategy"]
    result = p()
    assert "semver" in result.lower() or "bump" in result.lower()


def test_version_strategy_with_summary() -> None:
    p = _registered()["version_strategy"]
    result = p(change_summary="added new API endpoint")
    assert "added new API endpoint" in result


# ── branch_strategy ───────────────────────────────────────────────────────────


def test_branch_strategy_default() -> None:
    p = _registered()["branch_strategy"]
    result = p()
    assert "feat" in result


def test_branch_strategy_with_context() -> None:
    p = _registered()["branch_strategy"]
    result = p(task_description="fix login bug", context_hint="auth module")
    assert "fix login bug" in result
    assert "auth module" in result


def test_branch_strategy_no_context_hint() -> None:
    p = _registered()["branch_strategy"]
    result = p(task_description="add feature")
    assert "add feature" in result


# ── commit_message_guide ──────────────────────────────────────────────────────


def test_commit_message_guide_default() -> None:
    p = _registered()["commit_message_guide"]
    result = p()
    assert "Conventional" in result


def test_commit_message_guide_with_info() -> None:
    p = _registered()["commit_message_guide"]
    result = p(staged_summary="updated README", branch_name="docs/readme")
    assert "updated README" in result
    assert "docs/readme" in result


# ── changelog_entry ───────────────────────────────────────────────────────────


def test_changelog_entry_default() -> None:
    p = _registered()["changelog_entry"]
    result = p()
    assert "Changelog" in result or "changelog" in result


def test_changelog_entry_with_summary() -> None:
    p = _registered()["changelog_entry"]
    result = p(commit_summary="add MCP server", section_hint="Added")
    assert "add MCP server" in result
    assert "Added" in result


# ── config_setup ──────────────────────────────────────────────────────────────


def test_config_setup_python() -> None:
    p = _registered()["config_setup"]
    result = p(project_type="python")
    assert "pep621" in result


def test_config_setup_node() -> None:
    p = _registered()["config_setup"]
    result = p(project_type="node")
    assert "package.json" in result or "package_json" in result


def test_config_setup_go() -> None:
    p = _registered()["config_setup"]
    result = p(project_type="go")
    assert "go" in result.lower()


def test_config_setup_unknown_falls_back_to_python() -> None:
    p = _registered()["config_setup"]
    result = p(project_type="rust")
    assert "pep621" in result


# ── release_readiness ─────────────────────────────────────────────────────────


def test_release_readiness_default() -> None:
    p = _registered()["release_readiness"]
    result = p()
    assert (
        "readiness" in result.lower()
        or "checklist" in result.lower()
        or "release" in result.lower()
    )


def test_release_readiness_with_version() -> None:
    p = _registered()["release_readiness"]
    result = p(version="2.0.0", target_env="staging")
    assert "v2.0.0" in result
    assert "staging" in result
