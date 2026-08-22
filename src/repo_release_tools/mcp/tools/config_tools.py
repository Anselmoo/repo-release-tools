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
        title="What release policy does this repo enforce?",
        tags={"config", "inspection"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        meta={"domain": "rrt", "surface": "mcp", "audience": "agent"},
    )
    def rrt_config(ctx: Context) -> dict[str, Any] | ConfigError:
        """Read the repo's resolved [tool.rrt] policy.

        Version targets, pin targets, changelog file, release branch pattern, folder
        rules. Call this before proposing any release-related change so you act on
        configured policy rather than assumptions. This returns the resolved config as
        structured data — a config-load error comes back as a typed ConfigError rather
        than a nonzero exit — but it does NOT run the per-target checks `rrt config
        --validate` does (target/pin/docs/folder `.validate()`); use rrt_release_check,
        rrt_folder_check, or rrt_docs_check for those.
        """
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
        title="Is this repo's release automation actually wired up?",
        tags={"config", "inspection"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        meta={"domain": "rrt", "surface": "mcp", "audience": "agent"},
    )
    def rrt_doctor(ctx: Context) -> DoctorResponse | ConfigError:
        """Check whether pre-commit, lefthook, husky, and GitHub Actions workflows are correctly wired.

        Use before recommending a hook or workflow change, and when a hook did not fire
        as expected. Returns one CheckResult per component with ok + severity — no
        output parsing.
        """
        from repo_release_tools.commands.doctor import (
            _check_github_workflows,
            _check_hook_integrations,
        )

        root: Path = ctx.lifespan_context.get("root", Path.cwd())
        raw = {**_check_hook_integrations(root), "workflows": _check_github_workflows(root)}
        return DoctorResponse(
            **{
                name: CheckResult(message=msg, ok=ok, severity=sev)
                for name, (msg, ok, sev) in raw.items()
            }
        )
