"""Publish-snapshot tools for the rrt MCP server."""

from __future__ import annotations

from pathlib import Path

from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from repo_release_tools import __version__ as _PKG_VERSION
from repo_release_tools.mcp.models import PublishSnapshotResult
from repo_release_tools.workflow import git


def register(mcp: FastMCP) -> None:
    """Register publish-snapshot tools on *mcp*."""

    @mcp.tool(
        title="RRT Publish Snapshot",
        tags={"git", "publishing"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(destructiveHint=True),
        timeout=15.0,
        meta={"domain": "rrt", "surface": "mcp"},
    )
    async def rrt_publish_snapshot(
        ctx: Context,
        remote: str,
        branch: str = "main",
        message: str = "Initial commit",
        dry_run: bool = True,
    ) -> PublishSnapshotResult:
        """Force-push a single-commit snapshot of tracked content to a secondary remote. dry_run=True by default; force-push additionally requires dry_run=False (no separate confirmation flag on this surface — treat dry_run=False as the explicit confirmation)."""
        root: Path = ctx.lifespan_context.get("root", Path.cwd())

        if not git.is_git_repository(root):
            return PublishSnapshotResult(
                remote=remote,
                branch=branch,
                published=False,
                dry_run=dry_run,
                error=f"{root} is not inside a Git work tree.",
            )

        from repo_release_tools.config import load_primary_remote

        primary_remote = load_primary_remote(root)
        conflict = git.primary_remote_conflict(root, remote, primary_remote)
        if conflict is not None:
            return PublishSnapshotResult(
                remote=remote,
                branch=branch,
                published=False,
                dry_run=dry_run,
                error=conflict,
            )

        operation = git.in_progress_operation(root)
        if operation is not None:
            return PublishSnapshotResult(
                remote=remote,
                branch=branch,
                published=False,
                dry_run=dry_run,
                error=f"Cannot publish while a {operation} is in progress.",
            )

        await ctx.info(f"Publish target: {remote}:{branch}")
        if dry_run:
            return PublishSnapshotResult(
                remote=remote, branch=branch, published=False, dry_run=True
            )

        await ctx.warning(
            f"Force-pushing a snapshot to {remote}:{branch} — this overwrites remote history"
        )
        original_branch = git.current_branch(root) or "main"
        tmp_branch = git.unique_snapshot_branch_name(root)
        try:
            git.run(
                ["git", "checkout", "--orphan", tmp_branch],
                root,
                dry_run=False,
                label="git checkout --orphan",
            )
            git.run(["git", "add", "-u"], root, dry_run=False, label="git add -u")
            git.run(["git", "commit", "-m", message], root, dry_run=False, label="git commit")
            git.run(
                ["git", "push", "--force", "--", remote, f"{tmp_branch}:{branch}"],
                root,
                dry_run=False,
                label="git push --force",
            )
        except RuntimeError as exc:
            return PublishSnapshotResult(
                remote=remote, branch=branch, published=False, dry_run=False, error=str(exc)
            )
        finally:
            try:
                git.run(
                    ["git", "checkout", original_branch], root, dry_run=False, label="git checkout"
                )
            except RuntimeError as exc:
                await ctx.warning(f"Cleanup: failed to restore branch {original_branch!r}: {exc}")
            try:
                git.run(
                    ["git", "branch", "-D", tmp_branch], root, dry_run=False, label="git branch -D"
                )
            except RuntimeError as exc:
                await ctx.warning(f"Cleanup: failed to delete temp branch {tmp_branch!r}: {exc}")

        return PublishSnapshotResult(remote=remote, branch=branch, published=True, dry_run=False)
