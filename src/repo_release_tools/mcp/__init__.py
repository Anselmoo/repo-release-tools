"""FastMCP server for repo-release-tools. Install with: pip install repo-release-tools[mcp]."""

from __future__ import annotations

try:
    from .server import create_server
except ImportError as exc:
    if "fastmcp" in str(exc) or "prefab" in str(exc):
        raise ImportError(
            "FastMCP is required for the MCP server. "
            "Install it with: pip install repo-release-tools[mcp]"
        ) from exc
    raise

__all__ = ["create_server"]
