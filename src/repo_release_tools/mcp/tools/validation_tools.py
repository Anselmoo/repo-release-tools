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
        title="Will this branch name pass the repo's hooks?",
        tags={"validation"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        meta={"domain": "rrt", "surface": "mcp", "audience": "agent"},
    )
    def rrt_validate_branch(ctx: Context, branch_name: str) -> BranchValidationResult:
        """Check a branch name against this repo's configured type allow-list before you create it.

        Cheaper than creating it and having the pre-commit hook reject it. Honors
        [[tool.rrt.branch_types]] and extra_branch_types from config, which a
        hardcoded regex would miss.
        """
        from repo_release_tools.config import load_type_registry
        from repo_release_tools.workflow.hooks import validate_branch_name

        root = ctx.lifespan_context.get("root", Path.cwd())
        try:
            types = load_type_registry(root)
        except ValueError as exc:
            return BranchValidationResult(valid=False, branch=branch_name, reason=str(exc))
        error = validate_branch_name(branch_name, registry=types)
        if error is None:
            return BranchValidationResult(valid=True, branch=branch_name)
        return BranchValidationResult(valid=False, branch=branch_name, reason=error)

    @mcp.tool(
        title="Will this commit subject pass the repo's hooks?",
        tags={"validation"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        meta={"domain": "rrt", "surface": "mcp", "audience": "agent"},
    )
    def rrt_validate_commit(
        ctx: Context, subject: str, branch: str | None = None
    ) -> CommitValidationResult:
        """Check a commit subject against Conventional Commits as this repo enforces it, before you commit.

        Prefer this over `rrt-hooks commit-msg` in a shell: the subject is passed as a
        string argument, so backticks, quotes, `!`, and `$` in the message cannot be
        mangled by shell quoting. Honors [[tool.rrt.commit_types]] and
        extra_commit_types from config, as the hook does. Pass `branch` (the branch
        the commit lands on) to also apply that branch type's `commit_types`
        restriction; without it the restriction is not checked.
        """
        from repo_release_tools.config import load_type_registry
        from repo_release_tools.workflow.hooks import validate_commit_subject

        root = ctx.lifespan_context.get("root", Path.cwd())
        try:
            types = load_type_registry(root)
        except ValueError as exc:
            return CommitValidationResult(valid=False, subject=subject, reason=str(exc))
        error = validate_commit_subject(subject, registry=types, branch=branch or "")
        if error is None:
            return CommitValidationResult(valid=True, subject=subject)
        return CommitValidationResult(valid=False, subject=subject, reason=error)
