"""Commit drafting commands for `rrt git`.

- `commit` creates one conventional commit and infers the type from the current
  branch when possible.
- `commit-all` stages all tracked and untracked files before creating the
  commit.
- `squash-local` squashes commits ahead of an upstream branch or `--base-ref`
  into one conventional commit.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from repo_release_tools.commands._git_shared import add_dry_run_flag
from repo_release_tools.commands.branch import CONVENTIONAL_TYPES, join_description
from repo_release_tools.ui import DryRunPrinter, VerbosePrinter
from repo_release_tools.workflow import git
from repo_release_tools.workflow.hooks import (
    ALLOWED_BRANCH_NAMES,
    BOT_BRANCH_TYPES,
    MAGIC_BRANCH_TYPES,
)

COMMIT_TYPES = (*CONVENTIONAL_TYPES, "deps")


@dataclass(frozen=True)
class CommitSubject:
    """A conventional commit subject assembled from CLI input."""

    type: str
    description: str
    scope: str | None = None
    breaking: bool = False

    def render(self) -> str:
        """Return the conventional commit subject."""
        scope_part = f"({self.scope})" if self.scope else ""
        breaking_part = "!" if self.breaking else ""
        return f"{self.type}{scope_part}{breaking_part}: {self.description}"


def normalize_commit_subject_type(value: str) -> str:
    """Validate a commit type accepted by commit helpers."""
    normalized = value.lower()
    if normalized not in COMMIT_TYPES:
        allowed = ", ".join(COMMIT_TYPES)
        raise argparse.ArgumentTypeError(
            f"invalid commit type: {value!r} (choose one of: {allowed})",
        )
    return normalized


def infer_commit_type(branch_name: str) -> str | None:
    """Infer a conventional commit type from the current branch name."""
    if (
        not branch_name
        or branch_name in ALLOWED_BRANCH_NAMES
        or branch_name.startswith("release/v")
        or "/" not in branch_name
    ):
        return None

    type_part, _ = branch_name.split("/", 1)
    if type_part in MAGIC_BRANCH_TYPES or type_part in BOT_BRANCH_TYPES:
        return None
    return type_part if type_part in CONVENTIONAL_TYPES else None


def resolve_commit_subject(args: argparse.Namespace, root: Path) -> tuple[str, str]:
    """Resolve the current branch and conventional commit subject."""
    branch_name = git.current_branch(root)
    commit_type = args.type or infer_commit_type(branch_name)
    if commit_type is None:
        raise ValueError(
            "Could not infer a conventional commit type from the current branch. "
            "Use --type explicitly.",
        )

    subject = CommitSubject(
        type=commit_type,
        description=join_description(args.description),
        scope=args.scope,
        breaking=args.breaking,
    ).render()
    return branch_name or "<detached>", subject


def run_commit(args: argparse.Namespace, *, stage_all: bool) -> int:
    """Create a conventional commit, optionally staging all files first."""
    root = Path.cwd()
    try:
        branch_name, subject = resolve_commit_subject(args, root)
    except ValueError as exc:
        p = VerbosePrinter()
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1

    p = DryRunPrinter(args.dry_run)
    p.blank_line()
    p.header(
        "Commit",
        Branch=branch_name,
        Mode="stage all" if stage_all else "commit only",
        Subject=subject,
    )
    p.section("Git")
    if stage_all:
        git.run(["git", "add", "."], root, dry_run=args.dry_run, label="git add")
    git.run(["git", "commit", "-m", subject], root, dry_run=args.dry_run, label="git commit")

    p.blank_line()
    p.footer(f"Done. Created commit: {subject!r}")
    return 0


def cmd_commit(args: argparse.Namespace) -> int:
    """Create a conventional commit from the current branch context."""
    return run_commit(args, stage_all=False)


def cmd_commit_all(args: argparse.Namespace) -> int:
    """Stage all tracked and untracked files, then create a conventional commit."""
    return run_commit(args, stage_all=True)


def cmd_squash_local(args: argparse.Namespace) -> int:
    """Squash local commits since a base ref into one conventional commit."""
    verbose: int = getattr(args, "verbose", 0) or 0
    root = Path.cwd()
    if not args.dry_run and not git.working_tree_clean(root):
        p = VerbosePrinter(verbose=verbose)
        p.line(
            "Working tree has uncommitted changes. Commit or stash them first.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    base_ref = args.base_ref or git.upstream_branch(root)
    if base_ref is None:
        p = VerbosePrinter(verbose=verbose)
        p.line(
            "No upstream branch is configured and no --base-ref was provided.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    try:
        branch_name, subject = resolve_commit_subject(args, root)
    except ValueError as exc:
        p = VerbosePrinter(verbose=verbose)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1

    commits = git.commits_ahead(root, base_ref)
    if not commits:
        p = VerbosePrinter(verbose=verbose)
        p.line(
            f"No commits found ahead of {base_ref!r}. Nothing to squash.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    squash_base = git.merge_base(root, base_ref)
    if squash_base is None:
        p = VerbosePrinter(verbose=verbose)
        p.line(
            f"Could not determine merge-base for {base_ref!r} and HEAD.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    p = DryRunPrinter(args.dry_run, verbose=verbose)
    p.blank_line()
    p.header(
        "Squash local",
        Branch=branch_name,
        Base=base_ref,
        Commits=str(len(commits)),
        Subject=subject,
    )
    p.section("Commits to squash")
    for line in commits:
        p.list_item(line)

    p.section("Squashing")
    git.run(
        ["git", "reset", "--soft", squash_base],
        root,
        dry_run=args.dry_run,
        label="git reset --soft",
    )
    git.run(["git", "commit", "-m", subject], root, dry_run=args.dry_run, label="git commit")

    p.blank_line()
    p.footer(f"Done. Squashed {len(commits)} commit(s) into {subject!r}.")
    return 0


def add_commit_arguments(parser: argparse.ArgumentParser) -> None:
    """Register shared commit drafting arguments."""
    parser.add_argument("description", nargs="+", help="Commit description words.")
    parser.add_argument(
        "--type",
        dest="type",
        default=None,
        type=normalize_commit_subject_type,
        metavar="TYPE",
        help="Explicit conventional commit type. Defaults to the current branch type.",
    )
    parser.add_argument("--scope", default=None, metavar="SCOPE", help="Optional commit scope.")
    parser.add_argument("--breaking", action="store_true", help="Mark the commit as breaking.")
    add_dry_run_flag(parser)


GIT_COMMIT_EXAMPLES = (
    '  $ rrt git commit "refresh help examples"\n'
    '  $ rrt git commit --type fix --scope cli "handle empty config"\n'
    '  $ rrt git commit --breaking "ship parser v2"'
)

GIT_COMMIT_ALL_EXAMPLES = (
    '  $ rrt git commit-all "refresh release metadata"\n'
    '  $ rrt git commit-all --type chore --scope deps "update lockfiles"'
)

GIT_SQUASH_LOCAL_EXAMPLES = (
    '  $ rrt git squash-local "ship parser"\n'
    '  $ rrt git squash-local --base-ref origin/main --type fix "repair sync handling"'
)


def register_commit(git_sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the commit drafting subcommands."""
    commit_parser = git_sub.add_parser(
        "commit",
        help="Create a conventional commit, inferring type from the current branch.",
        description="Create one conventional commit from the provided description, inferring the type from the current branch when possible.",
        epilog=GIT_COMMIT_EXAMPLES,
    )
    add_commit_arguments(commit_parser)
    commit_parser.set_defaults(handler=cmd_commit)

    commit_all_parser = git_sub.add_parser(
        "commit-all",
        help="Stage all files and create a conventional commit from the branch context.",
        description="Stage all tracked and untracked changes, then create one conventional commit from the current branch context.",
        epilog=GIT_COMMIT_ALL_EXAMPLES,
    )
    add_commit_arguments(commit_all_parser)
    commit_all_parser.set_defaults(handler=cmd_commit_all)

    squash_parser = git_sub.add_parser(
        "squash-local",
        help="Squash local commits since upstream or a base ref into one commit.",
        description="Squash commits ahead of the upstream branch or --base-ref into one conventional commit.",
        epilog=GIT_SQUASH_LOCAL_EXAMPLES,
    )
    add_commit_arguments(squash_parser)
    squash_parser.add_argument(
        "--base-ref",
        default=None,
        metavar="REF",
        help="Base ref to squash against. Defaults to the current upstream branch.",
    )
    squash_parser.set_defaults(handler=cmd_squash_local)
