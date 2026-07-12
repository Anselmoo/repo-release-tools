"""Upstream sync-check tools for the rrt MCP server."""

from __future__ import annotations

from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from repo_release_tools import __version__ as _PKG_VERSION
from repo_release_tools.mcp.models import SyncCheckResponse


def register(mcp: FastMCP) -> None:
    """Register sync-check tools on *mcp*."""

    @mcp.tool(
        title="RRT Sync Check",
        tags={"sync", "inspection"},
        version=_PKG_VERSION,
        # Deliberately not idempotent: a newer upstream release can appear
        # between calls, so results can legitimately change.
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=False),
        timeout=15.0,
        meta={"domain": "rrt", "surface": "mcp"},
    )
    def rrt_sync_check(ctx: Context, group: str | None = None) -> SyncCheckResponse:
        """List upstream package versions newer than the current project version.

        Reads the group's [tool.rrt.upstream] package config and queries the
        configured registry (PyPI/npm/NuGet/crates.io/Packagist). Read-only —
        never applies a bump. Requires network access to the registry.
        """
        from repo_release_tools.sync.providers import fetch_versions
        from repo_release_tools.version.semver import Version, newer_versions
        from repo_release_tools.version.targets import read_group_current_version

        config = ctx.lifespan_context.get("config")
        if config is None:
            return SyncCheckResponse(group=group or "", error="No rrt configuration found.")

        try:
            resolved = config.resolve_group(group)
        except ValueError as exc:
            return SyncCheckResponse(group=group or "", error=str(exc))

        if not resolved.upstream_package:
            return SyncCheckResponse(
                group=resolved.name, error="No [tool.rrt.upstream] package configured."
            )

        current = read_group_current_version(resolved)
        raw = fetch_versions(resolved.upstream_package, resolved.upstream_provider)

        parsed: list[Version] = []
        for v in raw:
            try:
                parsed.append(Version.parse(v))
            except ValueError:
                continue

        fresh = newer_versions(current, parsed)

        return SyncCheckResponse(
            group=resolved.name,
            current=str(current),
            upstream_package=resolved.upstream_package,
            upstream_provider=resolved.upstream_provider,
            newer_versions=[str(v) for v in fresh],
        )
