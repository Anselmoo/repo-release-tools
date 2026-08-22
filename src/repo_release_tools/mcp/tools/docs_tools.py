"""Docs lockfile drift-check tools for the rrt MCP server."""

from __future__ import annotations

from pathlib import Path

from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from repo_release_tools import __version__ as _PKG_VERSION
from repo_release_tools.mcp.models import DocsCheckResponse


def register(mcp: FastMCP) -> None:
    """Register docs-check tools on *mcp*."""

    @mcp.tool(
        title="Are the generated docs stale?",
        tags={"docs", "inspection"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        meta={"domain": "rrt", "surface": "mcp", "audience": "agent"},
    )
    def rrt_docs_check(ctx: Context) -> DocsCheckResponse:
        """Check whether .rrt/docs.lock.toml is current against source-owned docs.

        Use after editing any source docstring that feeds generated documentation,
        before opening a PR — CI fails on this drift. Read-only — never regenerates or
        writes files. If stale, run `rrt docs generate --format toml` to refresh. Covers
        .rrt/docs.lock.toml only; `rrt docs map --check` has no tool here — use the CLI.
        """
        from repo_release_tools.commands.docs_cmd import _build_docs_lock_sources
        from repo_release_tools.config import DocsConfig
        from repo_release_tools.docs.extractor import extract_docs_from_dir
        from repo_release_tools.state import docs_lock_path, lock_is_current

        root: Path = ctx.lifespan_context.get("root", Path.cwd())
        config = ctx.lifespan_context.get("config")
        docs_cfg = config.docs if (config is not None and config.docs is not None) else DocsConfig()

        lock_path = docs_lock_path(root, docs_cfg.lock_file)
        entries = extract_docs_from_dir(root, docs_cfg)
        sources = _build_docs_lock_sources(entries)
        is_current, messages = lock_is_current(lock_path, sources)

        return DocsCheckResponse(is_current=is_current, messages=messages)
