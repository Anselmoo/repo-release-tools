"""Version tools for the rrt MCP server."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from repo_release_tools import __version__ as _PKG_VERSION
from repo_release_tools.mcp.models import BumpGroupResult, ConfigError, VersionGroupResult


def register(mcp: FastMCP) -> None:
    """Register version read/bump tools on *mcp*."""

    @mcp.tool(
        title="RRT Version Reader",
        tags={"versioning"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        meta={"domain": "rrt", "surface": "mcp"},
    )
    def rrt_version(ctx: Context) -> list[VersionGroupResult] | ConfigError:
        """Return the current version from each version group's primary target."""
        from repo_release_tools.version.targets import read_version_string

        config_error = ctx.lifespan_context.get("config_error")
        if config_error is not None:
            return ConfigError(error=f"Invalid rrt configuration: {config_error}")
        config = ctx.lifespan_context.get("config")
        if config is None:
            return ConfigError(error="No rrt configuration found.")
        results: list[VersionGroupResult] = []
        for group in config.version_groups:
            try:
                ver = read_version_string(group.primary_target())
                results.append(VersionGroupResult(group=group.name, version=ver))
            except (RuntimeError, OSError) as exc:
                results.append(VersionGroupResult(group=group.name, version="", error=str(exc)))
        return results

    @mcp.tool(
        title="RRT Version Bump",
        tags={"versioning"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(destructiveHint=True),
        timeout=30.0,
        meta={"domain": "rrt", "surface": "mcp"},
    )
    async def rrt_bump(
        ctx: Context,
        level: str,
        dry_run: bool = True,
    ) -> list[BumpGroupResult] | dict[str, Any]:
        """Preview or apply a version bump. level: major | minor | patch | alpha | beta | rc. dry_run=True by default."""
        valid_levels = ("major", "minor", "patch", "alpha", "beta", "rc")
        if level not in valid_levels:
            return {"error": f"level must be one of: {', '.join(valid_levels)}"}

        config_error = ctx.lifespan_context.get("config_error")
        if config_error is not None:
            return {"error": f"Invalid rrt configuration: {config_error}"}
        config = ctx.lifespan_context.get("config")
        if config is None:
            return {"error": "No rrt configuration found."}

        from repo_release_tools.version.semver import Version
        from repo_release_tools.version.targets import read_version_string

        groups = config.version_groups
        total = float(len(groups))
        results: list[BumpGroupResult] = []
        for i, group in enumerate(groups):
            try:
                current = read_version_string(group.primary_target())
                new_ver = str(Version.parse(current).bump(level))
                await ctx.info(
                    f"{'Would bump' if dry_run else 'Bumping'} {group.name}: {current} → {new_ver}"
                )
                applied = False
                if not dry_run:
                    from repo_release_tools.version.targets import replace_version_in_file

                    for target in group.version_targets:
                        replace_version_in_file(target, new_ver, dry_run=False)
                        await ctx.info(f"Updated {target.path}")
                    applied = True
                results.append(
                    BumpGroupResult(
                        group=group.name,
                        current=current,
                        new=new_ver,
                        dry_run=dry_run,
                        applied=applied,
                    )
                )
            except (RuntimeError, OSError, ValueError) as exc:
                results.append(BumpGroupResult(group=group.name, error=str(exc)))
            if total > 0:
                await ctx.report_progress(float(i + 1), total)
        if total > 0:
            await ctx.report_progress(total, total)
        return results
