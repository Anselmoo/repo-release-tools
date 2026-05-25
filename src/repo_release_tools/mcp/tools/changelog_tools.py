"""Changelog tools for the rrt MCP server."""

from __future__ import annotations

from pathlib import Path

from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from repo_release_tools import __version__ as _PKG_VERSION
from repo_release_tools.mcp.models import ChangelogResponse, LockError


def register(mcp: FastMCP) -> None:
    """Register changelog tools on *mcp*."""

    @mcp.tool(
        title="RRT Changelog Reader",
        tags={"changelog"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        meta={"domain": "rrt", "surface": "mcp"},
    )
    def rrt_changelog(ctx: Context, section: str = "unreleased") -> ChangelogResponse | LockError:
        """Read changelog content. section: 'unreleased' (default) returns pending entries only; 'full' returns everything."""
        from repo_release_tools.changelog import get_unreleased_entries

        config = ctx.lifespan_context.get("config")
        root: Path = ctx.lifespan_context.get("root", Path.cwd())

        if config is not None and config.version_groups:
            changelog_path = config.version_groups[0].changelog_file
        else:
            changelog_path = root / "CHANGELOG.md"

        if not changelog_path.exists():
            return LockError(
                error=f"Changelog not found at {changelog_path}",
                hint="Create a CHANGELOG.md or configure changelog_file in [tool.rrt].",
            )

        text = changelog_path.read_text(encoding="utf-8")

        if section == "full":
            return ChangelogResponse(path=str(changelog_path), section="full", content=text)

        entries = get_unreleased_entries(text)
        return ChangelogResponse(path=str(changelog_path), section="unreleased", entries=entries)
