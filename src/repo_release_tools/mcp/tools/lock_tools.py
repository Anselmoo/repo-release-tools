"""Lock file tools for the rrt MCP server."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from repo_release_tools import __version__ as _PKG_VERSION


def register(mcp: FastMCP) -> None:
    """Register lock-file inspection tools on *mcp*."""

    @mcp.tool(
        title="RRT Health Lock",
        tags={"locks", "inspection"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        meta={"domain": "rrt", "surface": "mcp"},
    )
    def rrt_health(ctx: Context) -> dict[str, Any]:
        """Return the health check results from .rrt/health.lock.toml."""
        from repo_release_tools.state import health_lock_path, read_lock

        root: Path = ctx.lifespan_context.get("root", Path.cwd())
        data = read_lock(health_lock_path(root))
        if not data:
            return {"error": "No health lock found. Run: rrt doctor --snapshot"}
        return data

    @mcp.tool(
        title="RRT Drift Lock",
        tags={"locks", "inspection"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        meta={"domain": "rrt", "surface": "mcp"},
    )
    def rrt_drift(ctx: Context) -> dict[str, Any]:
        """Return source drift state from .rrt/drift.lock.toml (file hashes and symbols)."""
        from repo_release_tools.state import drift_lock_path, read_lock

        root: Path = ctx.lifespan_context.get("root", Path.cwd())
        data = read_lock(drift_lock_path(root))
        if not data:
            return {"error": "No drift lock found. Run: rrt drift --snapshot"}
        return data

    @mcp.tool(
        title="RRT Tree Lock",
        tags={"locks", "inspection"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        meta={"domain": "rrt", "surface": "mcp"},
    )
    def rrt_tree(ctx: Context) -> dict[str, Any]:
        """Return the repository tree snapshot from .rrt/tree.lock.toml."""
        from repo_release_tools.state import read_lock, tree_lock_path

        root: Path = ctx.lifespan_context.get("root", Path.cwd())
        data = read_lock(tree_lock_path(root))
        if not data:
            return {"error": "No tree lock found. Run: rrt tree --snapshot"}
        return data

    @mcp.tool(
        title="RRT Artifacts Lock",
        tags={"locks", "inspection"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        meta={"domain": "rrt", "surface": "mcp"},
    )
    def rrt_artifacts(ctx: Context) -> dict[str, Any]:
        """Return the artifact integrity map from .rrt/artifacts.lock.toml."""
        from repo_release_tools.state import artifacts_lock_path, read_lock

        root: Path = ctx.lifespan_context.get("root", Path.cwd())
        data = read_lock(artifacts_lock_path(root))
        if not data:
            return {"error": "No artifacts lock found. Run: rrt artifacts --snapshot"}
        return data
