"""Config and doctor tools for the rrt MCP server."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from repo_release_tools import __version__ as _PKG_VERSION
from repo_release_tools.mcp.models import CheckResult, ConfigError, DoctorResponse


def _path_to_str(obj: Any) -> Any:
    """Recursively convert Path objects to strings for JSON serialisation."""
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _path_to_str(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_path_to_str(i) for i in obj]
    return obj


def register(mcp: FastMCP) -> None:
    """Register config and doctor tools on *mcp*."""

    @mcp.tool(
        title="RRT Config Inspector",
        tags={"config", "inspection"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        meta={"domain": "rrt", "surface": "mcp"},
    )
    def rrt_config(ctx: Context) -> dict[str, Any] | ConfigError:
        """Return the resolved rrt configuration as a JSON-serialisable dict."""
        config_error = ctx.lifespan_context.get("config_error")
        if config_error is not None:
            return ConfigError(error=f"Invalid rrt configuration: {config_error}")
        config = ctx.lifespan_context.get("config")
        if config is None:
            return ConfigError(error="No rrt configuration found in this repository.")
        try:
            return _path_to_str(asdict(config))
        except Exception as exc:
            return ConfigError(error=str(exc))

    @mcp.tool(
        title="RRT Doctor",
        tags={"config", "inspection"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        meta={"domain": "rrt", "surface": "mcp"},
    )
    def rrt_doctor(ctx: Context) -> DoctorResponse | ConfigError:
        """Run rrt health checks (pre-commit, lefthook, husky, workflows) and return structured results."""
        from repo_release_tools.commands.doctor import (
            _check_github_workflows,
            _check_husky,
            _check_text_integration,
        )

        root: Path = ctx.lifespan_context.get("root", Path.cwd())
        raw = {
            "pre_commit": _check_text_integration(
                root,
                ".pre-commit-config.yaml",
                markers=("repo-release-tools", "rrt-"),
                success_message=".pre-commit-config.yaml includes repo-release-tools hooks",
                warning_message=".pre-commit-config.yaml exists but no repo-release-tools hooks detected",
            ),
            "lefthook": _check_text_integration(
                root,
                "lefthook.yml",
                markers=("rrt-hooks", "repo-release-tools"),
                success_message="lefthook.yml includes repo-release-tools hooks",
                warning_message="lefthook.yml exists but no repo-release-tools hooks detected",
            ),
            "husky": _check_husky(root),
            "workflows": _check_github_workflows(root),
        }
        return DoctorResponse(
            **{
                name: CheckResult(message=msg, ok=ok, severity=sev)
                for name, (msg, ok, sev) in raw.items()
            }
        )
