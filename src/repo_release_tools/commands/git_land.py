"""`rrt git land`: fast-forward, remove the worktree and delete the branch in one process.

Landing is one logical operation. Run as three commands, a hook can re-dirty
the worktree between them, and a failure halfway leaves a stale worktree
and branch behind. `land` checks every precondition before it changes
anything, then runs each step in the same process. Every step is skipped
when its work is already done, so re-running after a failure finishes the
job instead of failing again.

The planning and applying halves never print. The CLI handler renders
their structured results, and the MCP `rrt_git_land` tool returns them as
data, so both surfaces run exactly the same steps.

rrt:docs-exempt — published through the `rrt git` topic doc in workflow/git.py.
"""

from __future__ import annotations

import argparse
import shlex
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from repo_release_tools.commands._git_shared import add_dry_run_flag
from repo_release_tools.config import load_git_config
from repo_release_tools.ui import DryRunPrinter
from repo_release_tools.workflow import git

GIT_LAND_EXAMPLES = """\
  $ rrt git land feat/parser --dry-run
  $ rrt git land feat/parser
  $ rrt git land feat/parser --onto develop --restore-generated
  $ rrt git land feat/parser --keep-branch"""

StepStatus = Literal["done", "skipped", "would-run", "failed", "not-run"]


class LandError(Exception):
    """A precondition failed before anything was changed."""

    def __init__(self, message: str, details: list[str] | None = None) -> None:
        """Store the headline *message* and optional detail lines."""
        super().__init__(message)
        self.details = details or []


@dataclass(frozen=True)
class LandOptions:
    """Typed view of the ``rrt git land`` arguments, shared with the MCP tool."""

    branch: str
    onto: str = "main"
    restore_generated: bool = False
    keep_branch: bool = False
    dry_run: bool = False
    verbose: int = 0

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> LandOptions:
        """Build :class:`LandOptions` from a parsed ``argparse.Namespace``."""
        return cls(
            branch=args.branch,
            onto=args.onto,
            restore_generated=bool(args.restore_generated),
            keep_branch=bool(args.keep_branch),
            dry_run=bool(args.dry_run),
            verbose=getattr(args, "verbose", 0) or 0,
        )


@dataclass(frozen=True)
class LandStep:
    """One planned step: a git command, or files to delete, or a skip."""

    name: str
    cwd: Path
    argv: tuple[str, ...] = ()
    unlink: tuple[Path, ...] = ()
    skip_reason: str | None = None

    @property
    def command(self) -> str:
        """Return a copy-pasteable rendering of what this step does."""
        if self.unlink:
            return "rm -- " + " ".join(shlex.quote(str(path)) for path in self.unlink)
        return shlex.join(self.argv)


@dataclass(frozen=True)
class LandPlan:
    """Everything `land` decided before changing anything."""

    branch: str
    onto: str
    main_root: Path
    worktree: Path | None
    generated: tuple[str, ...]
    steps: tuple[LandStep, ...]
    worktrees_before: int
    branches_before: int
    cwd_inside_worktree: bool


@dataclass(frozen=True)
class LandStepResult:
    """What happened to one step."""

    name: str
    command: str
    status: StepStatus
    detail: str = ""


@dataclass(frozen=True)
class LandOutcome:
    """The result of applying a :class:`LandPlan`."""

    plan: LandPlan
    results: tuple[LandStepResult, ...]
    worktrees_after: int | None = None
    branches_after: int | None = None
    error: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return whether every step finished, was skipped, or would run."""
        return self.error is None


def _branch_count(root: Path) -> int:
    out = git.capture_checked(["git", "for-each-ref", "--format=%(refname)", "refs/heads"], root)
    return len([line for line in out.splitlines() if line])


def _rev(root: Path, ref: str) -> str:
    return git.capture_checked(["git", "rev-parse", "--verify", f"{ref}^{{commit}}"], root)


def plan_land(cwd: Path, opts: LandOptions) -> LandPlan:
    """Check every precondition and return the steps to run.

    Raises :class:`LandError` when landing is not possible; nothing has been
    changed at that point. Every step runs from the main worktree, so `land`
    works from inside the very worktree it removes.
    """
    if not git.is_git_repository(cwd):
        raise LandError(f"{cwd} is not inside a Git work tree.")
    branch, onto = opts.branch, opts.onto
    if branch.startswith("-") or onto.startswith("-"):
        raise LandError("Branch names must not start with '-'.")
    if branch == onto:
        raise LandError(f"Cannot land {branch!r} onto itself.")

    worktrees = git.worktree_list(cwd)
    main_root = worktrees[0].path
    for name in (branch, onto):
        if not git.ref_exists(main_root, f"refs/heads/{name}"):
            raise LandError(f"Local branch {name!r} not found.")

    branch_ref, onto_ref = f"refs/heads/{branch}", f"refs/heads/{onto}"
    branch_sha = _rev(main_root, branch_ref)
    onto_sha = _rev(main_root, onto_ref)
    already_landed = git.is_ancestor(main_root, branch_ref, onto_ref)
    if not already_landed and not git.is_ancestor(main_root, onto_ref, branch_ref):
        raise LandError(
            f"{onto!r} cannot be fast-forwarded to {branch!r}.",
            [f"Rebase {branch!r} onto {onto!r} first, then land again."],
        )

    branch_wt = next((wt for wt in worktrees if wt.branch == branch), None)
    onto_wt = next((wt for wt in worktrees if wt.branch == onto and not wt.prunable), None)
    if branch_wt is not None and branch_wt.path == main_root:
        raise LandError(
            f"{branch!r} is checked out in the main worktree.",
            ["Check out another branch there first; the main worktree is never removed."],
        )

    steps: list[LandStep] = []
    if already_landed:
        steps.append(
            LandStep("fast-forward", main_root, skip_reason=f"{onto} already contains {branch}")
        )
    elif onto_wt is not None:
        steps.append(
            LandStep("fast-forward", onto_wt.path, ("git", "merge", "--ff-only", branch_sha))
        )
    else:
        steps.append(
            LandStep(
                "fast-forward",
                main_root,
                ("git", "update-ref", onto_ref, branch_sha, onto_sha),
            )
        )

    generated: tuple[str, ...] = ()
    if branch_wt is None:
        steps.append(
            LandStep("remove-worktree", main_root, skip_reason=f"no worktree for {branch}")
        )
    elif branch_wt.prunable:
        steps.append(LandStep("remove-worktree", main_root, ("git", "worktree", "prune")))
    else:
        worktree_steps, generated = _worktree_steps(branch_wt, main_root, opts)
        steps.extend(worktree_steps)

    if opts.keep_branch:
        steps.append(LandStep("delete-branch", main_root, skip_reason="--keep-branch"))
    else:
        steps.append(LandStep("delete-branch", main_root, ("git", "branch", "-D", "--", branch)))

    cwd_inside = False
    if branch_wt is not None:
        cwd_inside = cwd.resolve().is_relative_to(branch_wt.path.resolve())
    return LandPlan(
        branch=branch,
        onto=onto,
        main_root=main_root,
        worktree=branch_wt.path if branch_wt is not None else None,
        generated=generated,
        steps=tuple(steps),
        worktrees_before=len(worktrees),
        branches_before=_branch_count(main_root),
        cwd_inside_worktree=cwd_inside,
    )


def _worktree_steps(
    wt: git.Worktree, main_root: Path, opts: LandOptions
) -> tuple[list[LandStep], tuple[str, ...]]:
    """Plan restore and removal for a live branch worktree, or raise LandError.

    Generated patterns come from the branch worktree's own config, since that
    is the tree whose dirt is being judged. They are returned for reporting.
    """
    if wt.locked:
        raise LandError(
            f"Worktree {wt.path} is locked.",
            [f"Unlock it with: git worktree unlock {shlex.quote(str(wt.path))}"],
        )
    operation = git.in_progress_operation(wt.path)
    if operation is not None:
        raise LandError(f"A {operation} is in progress in {wt.path}.")
    try:
        patterns = load_git_config(wt.path).generated
    except ValueError as exc:
        raise LandError(str(exc)) from exc
    other, generated = git.split_generated(wt.path, patterns)
    if other:
        raise LandError(
            f"Worktree {wt.path} has uncommitted changes.",
            [entry.short_line for entry in other],
        )
    if generated and not opts.restore_generated:
        raise LandError(
            f"Worktree {wt.path} has changes to generated paths only.",
            [
                *(entry.short_line for entry in generated),
                "Pass --restore-generated to discard them as part of landing.",
            ],
        )

    tracked = [entry.path for entry in generated if not entry.untracked]
    untracked = [wt.path / entry.path for entry in generated if entry.untracked]
    steps: list[LandStep] = []
    if tracked:
        steps.append(
            LandStep(
                "restore-generated",
                wt.path,
                (
                    "git",
                    "restore",
                    "--source=HEAD",
                    "--staged",
                    "--worktree",
                    "--",
                    *git.literal_pathspecs(tracked),
                ),
            )
        )
    if untracked:
        steps.append(LandStep("remove-untracked-generated", wt.path, unlink=tuple(untracked)))
    steps.append(
        LandStep("remove-worktree", main_root, ("git", "worktree", "remove", str(wt.path)))
    )
    return steps, patterns


def apply_land(plan: LandPlan, *, dry_run: bool) -> LandOutcome:
    """Run the planned steps in order, stopping at the first failure.

    Never prints. In dry-run mode every runnable step is reported as
    ``would-run`` and nothing is executed.
    """
    results: list[LandStepResult] = []
    error: str | None = None
    for step in plan.steps:
        if error is not None:
            results.append(LandStepResult(step.name, step.command, "not-run"))
            continue
        if step.skip_reason is not None:
            results.append(LandStepResult(step.name, step.command, "skipped", step.skip_reason))
            continue
        if dry_run:
            results.append(LandStepResult(step.name, step.command, "would-run"))
            continue
        try:
            _run_step(plan, step)
        except (RuntimeError, OSError) as exc:
            error = str(exc)
            results.append(LandStepResult(step.name, step.command, "failed", error))
            continue
        results.append(LandStepResult(step.name, step.command, "done"))

    if dry_run:
        return LandOutcome(plan=plan, results=tuple(results))
    try:
        worktrees_after = len(git.worktree_list(plan.main_root))
        branches_after = _branch_count(plan.main_root)
    except RuntimeError:
        worktrees_after = branches_after = None
    notes: list[str] = []
    if error is not None:
        notes.append("Fix the cause and run the same command again; finished steps are skipped.")
    elif plan.cwd_inside_worktree:
        notes.append(f"Your working directory was removed. Continue in {plan.main_root}.")
    return LandOutcome(
        plan=plan,
        results=tuple(results),
        worktrees_after=worktrees_after,
        branches_after=branches_after,
        error=error,
        notes=notes,
    )


def _run_step(plan: LandPlan, step: LandStep) -> None:
    """Execute one step; raise RuntimeError or OSError on failure."""
    if step.unlink:
        for path in step.unlink:
            path.unlink(missing_ok=True)
        return
    if step.name == "delete-branch" and not git.is_ancestor(
        plan.main_root, f"refs/heads/{plan.branch}", f"refs/heads/{plan.onto}"
    ):
        # `branch -d` checks merged-ness against HEAD, not --onto, so verify
        # against --onto here and use -D only once that check has passed.
        raise RuntimeError(f"{plan.branch!r} is not contained in {plan.onto!r}; not deleting it.")
    git.capture_checked(list(step.argv), step.cwd)


def cmd_land(args: argparse.Namespace) -> int:
    """Land a branch: fast-forward --onto, remove its worktree, delete it."""
    opts = LandOptions.from_args(args)
    p = DryRunPrinter(opts.dry_run, verbose=opts.verbose)
    try:
        plan = plan_land(Path.cwd(), opts)
    except LandError as exc:
        p.line(str(exc), ok=False, stream=sys.stderr)
        for detail in exc.details:
            p.action(detail, stream=sys.stderr)
        return 1
    except RuntimeError as exc:
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1

    outcome = apply_land(plan, dry_run=opts.dry_run)
    render_land_outcome(p, outcome)
    return 0 if outcome.ok else 1


def render_land_outcome(p: DryRunPrinter, outcome: LandOutcome) -> None:
    """Print a land outcome in the house dry-run layout."""
    plan = outcome.plan
    p.blank_line()
    p.header(
        f"Land {plan.branch} onto {plan.onto}",
        Worktree=str(plan.worktree) if plan.worktree is not None else "none",
        Generated=", ".join(plan.generated) or "none configured",
    )
    p.section("Steps")
    for result in outcome.results:
        if result.status == "would-run":
            p.would_run(result.command)
        elif result.status == "done":
            p.line(f"{result.name}: {result.command}", ok=True)
        elif result.status == "skipped":
            p.action(f"{result.name}: skipped ({result.detail})")
        elif result.status == "failed":
            p.line(f"{result.name}: {result.detail}", ok=False, stream=sys.stderr)
        else:
            p.action(f"{result.name}: not run", stream=sys.stderr)
    p.blank_line()
    if outcome.worktrees_after is not None:
        p.meta("Worktrees", f"{plan.worktrees_before} → {outcome.worktrees_after}")
    if outcome.branches_after is not None:
        p.meta("Branches", f"{plan.branches_before} → {outcome.branches_after}")
    for note in outcome.notes:
        p.warn(note, stream=sys.stderr if outcome.error else None)
    if outcome.ok:
        p.footer("Done." if not p.dry_run else "Done. Re-run without --dry-run to land.")


def register_land(git_sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register ``rrt git land``."""
    parser = git_sub.add_parser(
        "land",
        help="Fast-forward a branch onto its target, remove its worktree and delete it.",
        description=(
            "Land a finished branch in one process: fast-forward --onto, restore generated "
            "paths if asked, remove the branch's worktree, and delete the branch. All checks "
            "run before any change; re-running after a failure skips finished steps."
        ),
        epilog=GIT_LAND_EXAMPLES,
    )
    parser.add_argument("branch", help="Local branch to land.")
    parser.add_argument(
        "--onto", default="main", metavar="BRANCH", help="Branch to fast-forward (default: main)."
    )
    parser.add_argument(
        "--restore-generated",
        action="store_true",
        help=(
            "Discard changes to [tool.rrt.git].generated paths in the worktree first: restore "
            "tracked files and delete untracked ones."
        ),
    )
    parser.add_argument(
        "--keep-branch", action="store_true", help="Keep the branch after landing it."
    )
    add_dry_run_flag(parser)
    parser.set_defaults(handler=cmd_land)
