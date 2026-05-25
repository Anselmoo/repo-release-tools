"""Git workflow tools for the rrt MCP server."""

from __future__ import annotations

from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from repo_release_tools import __version__ as _PKG_VERSION
from repo_release_tools.mcp.models import BranchResult


def register(mcp: FastMCP) -> None:
    """Register git workflow tools on *mcp*."""

    @mcp.tool(
        title="RRT Branch New",
        tags={"git", "branching"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(destructiveHint=True),
        timeout=10.0,
        meta={"domain": "rrt", "surface": "mcp"},
    )
    async def rrt_branch_new(
        ctx: Context,
        commit_type: str,
        description: str,
        scope: str | None = None,
        dry_run: bool = True,
    ) -> BranchResult:
        """Create a new conventionally-named branch. commit_type: feat|fix|chore|docs|refactor|test|ci|perf|style|build. dry_run=True by default."""
        from pathlib import Path

        from repo_release_tools.commands.branch import CONVENTIONAL_TYPES, BranchName
        from repo_release_tools.workflow import git

        if commit_type not in CONVENTIONAL_TYPES:
            allowed = ", ".join(CONVENTIONAL_TYPES)
            return BranchResult(
                branch="",
                created=False,
                dry_run=dry_run,
                suggested_commit_title="",
                error=f"Invalid commit type. Choose one of: {allowed}",
            )

        root: Path = ctx.lifespan_context.get("root", Path.cwd())
        branch = BranchName(type=commit_type, description=description, scope=scope)
        branch_name = branch.slug()
        commit_title = branch.commit_title()

        await ctx.info(f"Branch target: {branch_name} (suggested title: {commit_title})")

        if not dry_run:
            await ctx.warning(f"Creating branch '{branch_name}' — this modifies git state")
            if git.branch_exists(root, branch_name):
                return BranchResult(
                    branch=branch_name,
                    created=False,
                    dry_run=False,
                    suggested_commit_title=commit_title,
                    error=f"Branch '{branch_name}' already exists. Delete it first or choose a different description.",
                )
            git.run(
                ["git", "checkout", "-b", branch_name], root, dry_run=False, label="git checkout -b"
            )

        return BranchResult(
            branch=branch_name,
            created=not dry_run,
            dry_run=dry_run,
            suggested_commit_title=commit_title,
        )
