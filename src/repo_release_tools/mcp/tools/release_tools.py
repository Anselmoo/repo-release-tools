"""Release-target validation tools for the rrt MCP server."""

from __future__ import annotations

from pathlib import Path

from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from repo_release_tools import __version__ as _PKG_VERSION
from repo_release_tools.mcp.models import ReleaseCheckEntry, ReleaseCheckResponse, ReleaseGroupCheck


def register(mcp: FastMCP) -> None:
    """Register release-check tools on *mcp*."""

    @mcp.tool(
        title="RRT Release Check",
        tags={"release", "inspection"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        meta={"domain": "rrt", "surface": "mcp"},
    )
    def rrt_release_check(ctx: Context) -> ReleaseCheckResponse:
        """Validate version, pin, and changelog targets for every version group.

        Read-only — never modifies files.
        """
        from repo_release_tools.commands.release_cmd import (
            _check_pin_target,
            _check_version_target,
            _resolve_expected_version,
        )

        config_error = ctx.lifespan_context.get("config_error")
        if config_error is not None:
            return ReleaseCheckResponse(
                all_ok=False, error=f"Invalid rrt configuration: {config_error}"
            )
        config = ctx.lifespan_context.get("config")
        if config is None:
            return ReleaseCheckResponse(all_ok=False, error="No rrt configuration found.")

        root: Path = ctx.lifespan_context.get("root", Path.cwd())
        all_ok = True
        groups: list[ReleaseGroupCheck] = []

        for group in config.version_groups:
            group_ok = True
            entries: list[ReleaseCheckEntry] = []

            for target in group.version_targets:
                message, ok, severity = _check_version_target(target, root)
                entries.append(ReleaseCheckEntry(message=message, ok=ok, severity=severity))
                if not ok:
                    group_ok = False

            all_pins = group.pin_targets + config.global_pin_targets
            if all_pins:
                expected_version, warning = _resolve_expected_version(group)
                if warning is not None:
                    entries.append(ReleaseCheckEntry(message=warning, ok=True, severity="warning"))

                seen: set[tuple[object, str]] = set()
                for pin in all_pins:
                    key = (pin.path, pin.pattern)
                    if key in seen:
                        continue
                    seen.add(key)
                    message, ok, severity = _check_pin_target(pin, root, expected_version)
                    entries.append(ReleaseCheckEntry(message=message, ok=ok, severity=severity))
                    if not ok:
                        group_ok = False

            changelog = group.changelog_file
            if changelog.exists():
                entries.append(
                    ReleaseCheckEntry(
                        message=f"{changelog.relative_to(root)} exists", ok=True, severity="ok"
                    )
                )
            else:
                entries.append(
                    ReleaseCheckEntry(
                        message=f"{changelog.relative_to(root)} not found",
                        ok=False,
                        severity="error",
                    )
                )
                group_ok = False

            groups.append(ReleaseGroupCheck(group=group.name, ok=group_ok, entries=entries))
            if not group_ok:
                all_ok = False

        return ReleaseCheckResponse(all_ok=all_ok, groups=groups)
