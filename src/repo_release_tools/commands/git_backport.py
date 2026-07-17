"""Read-only counterpart to `rrt git publish-snapshot`: list commits pending backport.

`backport-from-target` fetches a `[tool.rrt.publish_targets.<name>]` entry's
remote/branch, lists the commits present there but not on the primary's tracked
branch, and prints the exact `git checkout -b`/`git cherry-pick` commands to run
next. It never cherry-picks, merges, or pushes on its own -- a fix made directly
on a disposable mirror skipped the primary's own CI, so folding it back in needs
a human decision, not automation.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from repo_release_tools.commands._git_shared import add_dry_run_flag
from repo_release_tools.config import load_or_autodetect_config
from repo_release_tools.ui import DryRunPrinter, VerbosePrinter
from repo_release_tools.workflow import git


@dataclass(frozen=True)
class BackportOptions:
    """Typed view of ``argparse.Namespace`` for ``rrt git backport-from-target``.

    Built once via :meth:`from_args` at the top of
    :func:`cmd_backport_from_target` so every flag has a single, typed read
    site instead of scattered ``getattr(args, ..., default)`` calls.
    """

    verbose: int
    target: str
    remote: str | None
    branch: str | None
    base_ref: str | None
    dry_run: bool

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> BackportOptions:
        """Build a :class:`BackportOptions` from a parsed ``argparse.Namespace``."""
        return cls(
            verbose=getattr(args, "verbose", 0) or 0,
            target=args.target,
            remote=args.remote,
            branch=args.branch,
            base_ref=args.base_ref,
            dry_run=args.dry_run,
        )


def _pending_commits(root: Path, base_ref: str) -> list[str]:
    """Return ``sha subject`` lines for commits on FETCH_HEAD not in *base_ref*.

    Rejects a *base_ref* starting with ``-``: the range expression
    ``<base_ref>..FETCH_HEAD`` is a single positional argument to ``git log``
    that cannot be guarded with a ``--`` separator (git would then treat the
    range as a pathspec instead of a revision range), so a leading dash is
    rejected outright to prevent option-injection (CWE-88) -- mirrors
    ``workflow/git.py``'s ``commits_ahead`` helper, which guards the same way
    for the same reason.
    """
    if base_ref.startswith("-"):
        raise ValueError(f"base_ref must not start with '-': {base_ref!r}")
    out = git.capture(["git", "log", f"{base_ref}..FETCH_HEAD", "--pretty=format:%h %s"], root)
    return [line for line in out.splitlines() if line]


def cmd_backport_from_target(args: argparse.Namespace) -> int:
    """Fetch a publish target and list commits pending backport to the primary."""
    opts = BackportOptions.from_args(args)
    verbose = opts.verbose
    root = Path.cwd()
    if not git.is_git_repository(root):
        p = VerbosePrinter(verbose=verbose)
        p.line(f"{root} is not inside a Git work tree.", ok=False, stream=sys.stderr)
        return 1

    config = load_or_autodetect_config(root)
    target = config.publish_targets.get(opts.target)
    if target is None:
        p = VerbosePrinter(verbose=verbose)
        p.line(
            f"No publish target named {opts.target!r} in [tool.rrt.publish_targets].",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    remote = opts.remote or target.remote
    branch = opts.branch or target.branch
    base_ref = opts.base_ref or (git.current_branch(root) or "HEAD")

    p = DryRunPrinter(opts.dry_run, verbose=verbose)
    p.blank_line()
    p.header(
        "Backport from target",
        Target=opts.target,
        Remote=remote,
        Branch=branch,
        Base=base_ref,
    )
    p.section("Git")
    git.run(["git", "fetch", remote, branch], root, dry_run=opts.dry_run, label="git fetch")

    if opts.dry_run:
        p.blank_line()
        p.footer("Done. Preview complete — fetch was not run, so no commits were listed.")
        return 0

    try:
        commits = _pending_commits(root, base_ref)
    except ValueError as exc:
        p2 = VerbosePrinter(verbose=verbose)
        p2.line(str(exc), ok=False, stream=sys.stderr)
        return 1

    if not commits:
        p.blank_line()
        p.footer(
            f"Done. {branch} on {remote} has no commits ahead of {base_ref} — nothing to backport.",
        )
        return 0

    p.section(f"Pending commits ({len(commits)})")
    for entry in commits:
        p.action(entry)

    shas = [entry.split(" ", 1)[0] for entry in reversed(commits)]
    backport_branch = f"backport/{opts.target}"
    p.section("Next steps (run manually)")
    p.action(f"git checkout -b {backport_branch} {base_ref}")
    p.action(f"git cherry-pick {' '.join(shas)}")

    p.blank_line()
    p.footer(f"Done. {len(commits)} commit(s) pending backport from {remote}:{branch}.")
    return 0


GIT_BACKPORT_EXAMPLES = (
    "  $ rrt git backport-from-target demo\n"
    "  $ rrt git backport-from-target demo --dry-run\n"
    "  $ rrt git backport-from-target demo --base-ref origin/main"
)


def register_backport(git_sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``backport-from-target`` subcommand."""
    parser = git_sub.add_parser(
        "backport-from-target",
        help="List commits pending backport from a publish-snapshot target.",
        description=(
            "Fetch a [tool.rrt.publish_targets.<name>] entry's remote/branch and list "
            "the commits present there but not on the primary's tracked branch, along "
            "with the exact git checkout -b / git cherry-pick commands to run next. "
            "Never cherry-picks, merges, or pushes on its own -- reviewing and landing "
            "a change that skipped the primary's own CI needs a human decision."
        ),
        epilog=GIT_BACKPORT_EXAMPLES,
    )
    parser.add_argument(
        "target",
        help="Named [tool.rrt.publish_targets.<name>] entry to resolve remote/branch from.",
    )
    parser.add_argument(
        "--remote",
        default=None,
        help="Remote name or URL to fetch from. Overrides the target's configured remote.",
    )
    parser.add_argument(
        "--branch",
        default=None,
        help="Remote branch to fetch. Overrides the target's configured branch.",
    )
    parser.add_argument(
        "--base-ref",
        default=None,
        metavar="REF",
        help="Primary-side ref to compare against. Defaults to the current branch.",
    )
    add_dry_run_flag(parser)
    parser.set_defaults(handler=cmd_backport_from_target)
