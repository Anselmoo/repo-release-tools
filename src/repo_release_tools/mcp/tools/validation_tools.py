"""Branch and commit validation tools for the rrt MCP server."""

from __future__ import annotations

from pathlib import Path

from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from repo_release_tools import __version__ as _PKG_VERSION
from repo_release_tools.mcp.models import BranchValidationResult, CommitValidationResult


def register(mcp: FastMCP) -> None:
    """Register branch and commit validation tools on *mcp*."""

    @mcp.tool(
        title="RRT Branch Validator",
        tags={"validation"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        meta={"domain": "rrt", "surface": "mcp"},
    )
    def rrt_validate_branch(ctx: Context, branch_name: str) -> BranchValidationResult:
        """Validate a branch name against rrt's conventional naming rules."""
        from repo_release_tools.config import load_extra_branch_types
        from repo_release_tools.workflow.hooks import validate_branch_name

        root = ctx.lifespan_context.get("root", Path.cwd())
        try:
            extra = load_extra_branch_types(root)
        except FileNotFoundError:
            extra = ()
        error = validate_branch_name(branch_name, extra_types=extra)
        if error is None:
            return BranchValidationResult(valid=True, branch=branch_name)
        return BranchValidationResult(valid=False, branch=branch_name, reason=error)

    @mcp.tool(
        title="RRT Commit Validator",
        tags={"validation"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        meta={"domain": "rrt", "surface": "mcp"},
    )
    def rrt_validate_commit(ctx: Context, subject: str) -> CommitValidationResult:
        """Validate a commit subject line against Conventional Commits rules."""
        from repo_release_tools.config import load_extra_branch_types
        from repo_release_tools.workflow.hooks import validate_commit_subject

        root = ctx.lifespan_context.get("root", Path.cwd())
        try:
            extra = load_extra_branch_types(root)
        except FileNotFoundError:
            extra = ()
        error = validate_commit_subject(subject, extra)
        if error is None:
            return CommitValidationResult(valid=True, subject=subject)
        return CommitValidationResult(valid=False, subject=subject, reason=error)
