"""Tool registration for the rrt MCP server."""

from __future__ import annotations

from fastmcp import FastMCP

from .changelog_tools import register as register_changelog
from .config_tools import register as register_config
from .git_tools import register as register_git
from .lock_tools import register as register_locks
from .validation_tools import register as register_validation
from .version_tools import register as register_version


def register_tools(mcp: FastMCP) -> None:
    """Register all rrt tools on the given FastMCP instance."""
    register_config(mcp)
    register_locks(mcp)
    register_version(mcp)
    register_validation(mcp)
    register_changelog(mcp)
    register_git(mcp)
