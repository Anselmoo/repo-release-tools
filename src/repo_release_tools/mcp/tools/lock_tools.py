"""Lock file tools for the rrt MCP server."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from repo_release_tools import __version__ as _PKG_VERSION


def register(mcp: FastMCP) -> None:
    """Register lock-file inspection tools on *mcp*.

    These four tools are thin ``read_lock()`` wrappers around a small, readable
    TOML file at a fixed, known path — a client that can read files directly
    (e.g. an agent with a ``Read`` tool) gets nothing from calling these that it
    could not get from reading ``.rrt/<name>.lock.toml`` itself. They exist for
    clients that cannot read the filesystem (e.g. Claude Desktop). Each reflects
    the last ``--snapshot``, not current state.
    """

    @mcp.tool(
        title="Last recorded repo-health snapshot",
        tags={"locks", "inspection"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        meta={"domain": "rrt", "surface": "mcp", "audience": "agent"},
    )
    def rrt_health(ctx: Context) -> dict[str, Any]:
        """Return the health check results from .rrt/health.lock.toml.

        Reflects the last `rrt doctor --snapshot`, not current state; run the CLI
        check to compare against the working tree. If your client can read files
        directly, `Read .rrt/health.lock.toml` is equivalent — prefer rrt_doctor
        for a live check instead.
        """
        from repo_release_tools.state import health_lock_path, read_lock

        root: Path = ctx.lifespan_context.get("root", Path.cwd())
        data = read_lock(health_lock_path(root))
        if not data:
            return {"error": "No health lock found. Run: rrt doctor --snapshot"}
        return data

    @mcp.tool(
        title="Last recorded source-drift snapshot",
        tags={"locks", "inspection"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        meta={"domain": "rrt", "surface": "mcp", "audience": "agent"},
    )
    def rrt_drift(ctx: Context) -> dict[str, Any]:
        """Return source drift state from .rrt/drift.lock.toml (file hashes and symbols).

        Reflects the last `rrt drift --snapshot`, not current state; run the CLI
        check to compare against the working tree. If your client can read files
        directly, `Read .rrt/drift.lock.toml` is equivalent.
        """
        from repo_release_tools.state import drift_lock_path, read_lock

        root: Path = ctx.lifespan_context.get("root", Path.cwd())
        data = read_lock(drift_lock_path(root))
        if not data:
            return {"error": "No drift lock found. Run: rrt drift --snapshot"}
        return data

    @mcp.tool(
        title="Last recorded file-tree snapshot (NOT a live check)",
        tags={"locks", "inspection"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        meta={"domain": "rrt", "surface": "mcp", "audience": "agent"},
    )
    def rrt_tree(ctx: Context) -> dict[str, Any]:
        """Return the repository tree snapshot from .rrt/tree.lock.toml.

        Reflects the last `rrt tree --snapshot`, not current state — this tool does
        NOT run `rrt tree --check` and cannot tell you whether the working tree still
        matches it. There is no MCP tool for that check; use the CLI. If your client
        can read files directly, `Read .rrt/tree.lock.toml` is equivalent.
        """
        from repo_release_tools.state import read_lock, tree_lock_path

        root: Path = ctx.lifespan_context.get("root", Path.cwd())
        data = read_lock(tree_lock_path(root))
        if not data:
            return {"error": "No tree lock found. Run: rrt tree --snapshot"}
        return data

    @mcp.tool(
        title="Last recorded artifact-integrity snapshot",
        tags={"locks", "inspection"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        meta={"domain": "rrt", "surface": "mcp", "audience": "agent"},
    )
    def rrt_artifacts(ctx: Context) -> dict[str, Any]:
        """Return the artifact integrity map from .rrt/artifacts.lock.toml.

        Reflects the last `rrt artifacts --snapshot`, not current state; run the CLI
        check to compare against the working tree. If your client can read files
        directly, `Read .rrt/artifacts.lock.toml` is equivalent.
        """
        from repo_release_tools.state import artifacts_lock_path, read_lock

        root: Path = ctx.lifespan_context.get("root", Path.cwd())
        data = read_lock(artifacts_lock_path(root))
        if not data:
            return {"error": "No artifacts lock found. Run: rrt artifacts --snapshot"}
        return data
