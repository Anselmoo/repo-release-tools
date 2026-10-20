"""Git workflow tools for the rrt MCP server."""

from __future__ import annotations

from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from repo_release_tools import __version__ as _PKG_VERSION
from repo_release_tools.mcp.models import (
    BranchResult,
    CommitsSinceResult,
    DirtyEntryModel,
    DirtyTreeResult,
    LandResult,
    LandStepModel,
)


def register(mcp: FastMCP) -> None:
    """Register git workflow tools on *mcp*."""

    @mcp.tool(
        title="Create a policy-compliant branch for this task",
        tags={"git", "branching"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(destructiveHint=True),
        timeout=10.0,
        meta={"domain": "rrt", "surface": "mcp", "audience": "agent"},
    )
    async def rrt_branch_new(
        ctx: Context,
        commit_type: str,
        description: str,
        scope: str | None = None,
        dry_run: bool = True,
    ) -> BranchResult:
        """Derive a compliant branch name from a type + description.

        When dry_run=False, checks it out. Use instead of `git checkout -b` with a
        hand-written name — it also returns a matching Conventional Commit title to use
        for the first commit, though nothing enforces that the caller actually uses it.

        commit_type: feat|fix|chore|docs|refactor|test|ci|perf|style|build. dry_run=True by default.
        """
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
            import subprocess as _sp

            await ctx.warning(f"Creating branch '{branch_name}' — this modifies git state")
            if git.branch_exists(root, branch_name):
                return BranchResult(
                    branch=branch_name,
                    created=False,
                    dry_run=False,
                    suggested_commit_title=commit_title,
                    error=f"Branch '{branch_name}' already exists. Delete it first or choose a different description.",
                )
            try:
                _result = _sp.run(
                    ["git", "checkout", "-b", branch_name],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    timeout=8.0,
                )
            except _sp.TimeoutExpired:
                return BranchResult(
                    branch=branch_name,
                    created=False,
                    dry_run=False,
                    suggested_commit_title=commit_title,
                    error="git checkout -b timed out after 8 seconds.",
                )
            if _result.returncode != 0:
                return BranchResult(
                    branch=branch_name,
                    created=False,
                    dry_run=False,
                    suggested_commit_title=commit_title,
                    error=f"git checkout -b failed: {(_result.stderr or _result.stdout).strip()}",
                )
            await ctx.info(f"Created branch '{branch_name}'")

        return BranchResult(
            branch=branch_name,
            created=not dry_run,
            dry_run=dry_run,
            suggested_commit_title=commit_title,
        )

    @mcp.tool(
        title="Which paths are dirty, and which of them are generated?",
        tags={"git", "inspection"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        timeout=10.0,
        meta={"domain": "rrt", "surface": "mcp", "audience": "agent"},
    )
    def rrt_git_dirty_tree(ctx: Context, ignore_generated: bool = False) -> DirtyTreeResult:
        """List every uncommitted path, each marked when it matches [tool.rrt.git].generated.

        Use instead of `git status` before landing or committing. A regenerated manifest
        or handoff file shows as `generated: true`, so you can decide rather than guess.
        With ignore_generated=True, `clean` ignores generated entries. Read-only.
        """
        from pathlib import Path

        from repo_release_tools.commands._git_shared import split_generated_dirt

        root: Path = ctx.lifespan_context.get("root", Path.cwd())
        try:
            split = split_generated_dirt(root)
        except (RuntimeError, ValueError) as exc:
            return DirtyTreeResult(clean=False, ignore_generated=ignore_generated, error=str(exc))
        entries = [
            DirtyEntryModel(status=e.status, path=e.path, orig_path=e.orig_path, generated=False)
            for e in split.other
        ] + [
            DirtyEntryModel(status=e.status, path=e.path, orig_path=e.orig_path, generated=True)
            for e in split.generated
        ]
        clean = not split.other and (ignore_generated or not split.generated)
        return DirtyTreeResult(
            clean=clean,
            ignore_generated=ignore_generated,
            entries=entries,
            patterns=list(split.patterns),
        )

    @mcp.tool(
        title="How many commits since a ref, ignoring generated files?",
        tags={"git", "inspection"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        timeout=10.0,
        meta={"domain": "rrt", "surface": "mcp", "audience": "agent"},
    )
    def rrt_git_commits_since(
        ctx: Context,
        ref: str,
        exclude: list[str] | None = None,
        exclude_generated: bool = False,
    ) -> CommitsSinceResult:
        """List commits in <ref>..HEAD, leaving out commits that only touch *exclude* paths.

        A file that records HEAD can exclude itself, making "one commit behind" its
        resting state. Patterns are root-anchored git globs. exclude_generated adds every
        [tool.rrt.git].generated pattern. An unknown ref returns `error`, never count 0.
        """
        from pathlib import Path

        from repo_release_tools.config import load_git_config
        from repo_release_tools.workflow import git

        root: Path = ctx.lifespan_context.get("root", Path.cwd())
        patterns = list(exclude or [])
        try:
            if exclude_generated:
                patterns += load_git_config(root).generated
            commits = git.commits_since(root, ref, exclude=patterns)
        except (RuntimeError, ValueError) as exc:
            return CommitsSinceResult(ref=ref, exclude=patterns, error=str(exc))
        return CommitsSinceResult(ref=ref, exclude=patterns, commits=commits, count=len(commits))

    @mcp.tool(
        title="Land a finished branch: fast-forward, remove worktree, delete branch",
        tags={"git", "branching"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(destructiveHint=True),
        timeout=60.0,
        meta={"domain": "rrt", "surface": "mcp", "audience": "agent"},
    )
    async def rrt_git_land(
        ctx: Context,
        branch: str,
        onto: str = "main",
        restore_generated: bool = False,
        keep_branch: bool = False,
        dry_run: bool = True,
    ) -> LandResult:
        """Fast-forward *onto* to *branch*, remove the branch's worktree, and delete it.

        One call, one process: three separate git calls cannot do this safely, because a
        hook can re-dirty the worktree between them. All checks run before any change.
        Local only — never pushes. Re-running after a failure skips finished steps.
        restore_generated discards [tool.rrt.git].generated changes in the worktree first.
        dry_run=True by default.
        """
        from pathlib import Path

        from repo_release_tools.commands.git_land import (
            LandError,
            LandOptions,
            apply_land,
            plan_land,
        )

        root: Path = ctx.lifespan_context.get("root", Path.cwd())
        opts = LandOptions(
            branch=branch,
            onto=onto,
            restore_generated=restore_generated,
            keep_branch=keep_branch,
            dry_run=dry_run,
        )
        try:
            plan = plan_land(root, opts)
        except LandError as exc:
            return LandResult(
                branch=branch, onto=onto, dry_run=dry_run, error=str(exc), details=exc.details
            )
        except RuntimeError as exc:
            return LandResult(branch=branch, onto=onto, dry_run=dry_run, error=str(exc))

        if not dry_run:
            await ctx.warning(f"Landing {branch} onto {onto} — this modifies git state")
        outcome = apply_land(plan, dry_run=dry_run)
        landed = outcome.ok and not dry_run
        return LandResult(
            branch=branch,
            onto=onto,
            dry_run=dry_run,
            landed=landed,
            worktree=str(plan.worktree) if plan.worktree is not None else None,
            steps=[
                LandStepModel(name=r.name, command=r.command, status=r.status, detail=r.detail)
                for r in outcome.results
            ],
            worktrees_before=plan.worktrees_before,
            worktrees_after=outcome.worktrees_after,
            branches_before=plan.branches_before,
            branches_after=outcome.branches_after,
            cwd_removed=landed and plan.cwd_inside_worktree,
            notes=outcome.notes,
            error=outcome.error,
        )
