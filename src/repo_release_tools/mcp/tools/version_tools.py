"""Version tools for the rrt MCP server."""

from __future__ import annotations

from pathlib import Path
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
        group: str | None = None,
    ) -> list[BumpGroupResult] | dict[str, Any]:
        """Preview or apply a version bump.

        level: major | minor | patch | alpha | beta | rc. dry_run=True by default.
        group: restrict the bump to one ``[tool.rrt]`` version group; omit to bump every
        configured group (one :class:`BumpGroupResult` per group either way).

        Runs the SAME pipeline as the ``rrt bump`` CLI command (preflight, version
        targets, pin targets, changelog promotion/generation, lockfile and generated-asset
        refresh, then release-branch checkout + commit) via
        :mod:`repo_release_tools.commands.bump`'s shared stage functions, so an MCP bump
        and a CLI bump of the same repo produce identical results (fixes defect D9: the
        previous MCP bump only rewrote version-target files and skipped pins, changelog,
        lockfiles, generated assets, and git branch/commit entirely).
        """
        valid_levels = ("major", "minor", "patch", "alpha", "beta", "rc")
        if level not in valid_levels:
            return {"error": f"level must be one of: {', '.join(valid_levels)}"}

        config_error = ctx.lifespan_context.get("config_error")
        if config_error is not None:
            return {"error": f"Invalid rrt configuration: {config_error}"}
        config = ctx.lifespan_context.get("config")
        if config is None:
            return {"error": "No rrt configuration found."}

        from repo_release_tools.commands import bump as bump_cmd
        from repo_release_tools.preflight import PreflightError, run_preflight
        from repo_release_tools.workflow import git

        root: Path = ctx.lifespan_context.get("root", Path.cwd())

        try:
            groups = [config.resolve_group(group)] if group is not None else config.version_groups
        except ValueError as exc:
            return {"error": str(exc)}
        total = float(len(groups))
        results: list[BumpGroupResult] = []
        for i, target_group in enumerate(groups):
            group_opts = bump_cmd.Options(
                bump=level,
                group=target_group.name,
                dry_run=dry_run,
                force=False,
                no_commit=False,
                no_verify=False,
                no_changelog=False,
                no_pin_sync=False,
                no_update=False,
                include_maintenance=False,
                changelog_mode=None,
                base_branch=None,
                calver_scheme="YYYY.MM.DD",
                verbose=0,
            )
            try:
                resolved = bump_cmd.resolve_bump_target(config, group_opts)
            except (bump_cmd.BumpResolutionError, RuntimeError, OSError, ValueError) as exc:
                results.append(BumpGroupResult(group=target_group.name, error=str(exc)))
                if total > 0:
                    await ctx.report_progress(float(i + 1), total)
                continue

            current, new = resolved.current, resolved.new
            new_ver = str(new)
            await ctx.info(
                f"{'Would bump' if dry_run else 'Bumping'} {target_group.name}: "
                f"{current} → {new_ver}"
            )
            try:
                run_preflight(config, dry_run=dry_run, group=target_group)

                branch_name = target_group.release_branch.format(version=new)
                base = "<current>" if dry_run else git.current_branch(root)

                if not dry_run and git.branch_exists(root, branch_name):
                    raise RuntimeError(
                        f"Branch '{branch_name}' already exists. Delete it first or "
                        "choose a different version."
                    )

                changed_paths = bump_cmd.apply_bump_files(
                    target_group, new, config, dry_run=dry_run
                )

                effective_changelog_mode = bump_cmd.resolve_changelog_mode(config, None)
                bump_cmd.update_changelog(
                    bump_cmd.RrtConfig(
                        root=config.root,
                        config_file=config.config_file,
                        version_groups=[target_group],
                        default_group_name=target_group.name,
                    ),
                    new_ver,
                    include_maintenance=False,
                    dry_run=dry_run,
                    changelog_mode=effective_changelog_mode,
                )

                if target_group.lock_command:
                    bump_cmd.refresh_bump_lockfile(target_group, root, dry_run=dry_run)

                if target_group.generated_assets and not bump_cmd.refresh_bump_generated_assets(
                    target_group, root, dry_run=dry_run
                ):
                    raise RuntimeError(
                        f"Generated asset refresh failed for group {target_group.name!r}."
                    )

                bump_cmd.finalize_bump_git(
                    target_group,
                    new,
                    changed_paths,
                    root,
                    branch_name=branch_name,
                    base=base,
                    force=False,
                    opts=group_opts,
                )
            except (bump_cmd.BumpResolutionError, PreflightError, RuntimeError, OSError) as exc:
                results.append(BumpGroupResult(group=target_group.name, error=str(exc)))
                if total > 0:
                    await ctx.report_progress(float(i + 1), total)
                continue

            results.append(
                BumpGroupResult(
                    group=target_group.name,
                    current=str(current),
                    new=new_ver,
                    dry_run=dry_run,
                    applied=not dry_run,
                )
            )
            if total > 0:
                await ctx.report_progress(float(i + 1), total)
        if total > 0:
            await ctx.report_progress(total, total)
        return results
