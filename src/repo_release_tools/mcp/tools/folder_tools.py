"""Folder structure policy tools for the rrt MCP server."""

from __future__ import annotations

from pathlib import Path

from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from repo_release_tools import __version__ as _PKG_VERSION
from repo_release_tools.mcp.models import (
    FolderCheckResponse,
    FolderTargetEntry,
    FolderViolationEntry,
)


def register(mcp: FastMCP) -> None:
    """Register folder-check tools on *mcp*."""

    @mcp.tool(
        title="RRT Folder Check",
        tags={"folders", "inspection"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        meta={"domain": "rrt", "surface": "mcp"},
    )
    def rrt_folder_check(
        ctx: Context,
        template: list[str] | None = None,
    ) -> FolderCheckResponse:
        """Validate the repository folder structure.

        Checks against [tool.rrt.folders] policy or named built-in templates.
        Read-only — never scaffolds files.
        """
        from repo_release_tools.commands.folder import _load_folder_policy_config
        from repo_release_tools.folders import check_folders

        root: Path = ctx.lifespan_context.get("root", Path.cwd())
        config = _load_folder_policy_config(root)
        report = check_folders(
            root=root,
            policy=None if config is None else config.folders,
            template_names=tuple(template or ()),
        )

        return FolderCheckResponse(
            mode=report.mode,
            ok=report.ok,
            violation_count=report.violation_count,
            targets=[
                FolderTargetEntry(
                    rule_name=target.rule_name,
                    selector=target.selector,
                    base_path=target.base_path,
                    ok=target.ok,
                    violations=[
                        FolderViolationEntry(
                            code=v.code, path=v.path, message=v.message, severity=v.severity
                        )
                        for v in target.violations
                    ],
                )
                for target in report.targets
            ],
        )
