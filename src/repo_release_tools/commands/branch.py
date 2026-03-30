"""Branch commands."""

from __future__ import annotations

import argparse
import re
import sys

from dataclasses import dataclass
from pathlib import Path

from repo_release_tools import git, output


CONVENTIONAL_TYPES = (
    "feat",
    "fix",
    "chore",
    "docs",
    "refactor",
    "test",
    "ci",
    "perf",
    "style",
    "build",
)

SLUG_MAX = 60


@dataclass(frozen=True)
class BranchName:
    """Branch name builder."""

    type: str
    description: str
    scope: str | None = None

    def slug(self) -> str:
        """Build the branch name."""
        raw = f"{self.scope}-{self.description}" if self.scope else self.description
        slug = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")
        slug = slug[:SLUG_MAX].rstrip("-")
        return f"{self.type}/{slug}"

    def commit_title(self) -> str:
        """Build the suggested commit title."""
        scope_part = f"({self.scope})" if self.scope else ""
        return f"{self.type}{scope_part}: {self.description}"


def normalize_commit_type(value: str) -> str:
    """Validate the conventional commit type."""
    normalized = value.lower()
    if normalized not in CONVENTIONAL_TYPES:
        allowed = ", ".join(CONVENTIONAL_TYPES)
        raise argparse.ArgumentTypeError(
            f"invalid conventional type: {value!r} (choose one of: {allowed})"
        )
    return normalized


def join_description(parts: list[str]) -> str:
    """Join free-form description words."""
    if not (description := " ".join(parts).strip()):
        raise argparse.ArgumentTypeError("description must not be empty")
    return description


def add_common_branch_arguments(parser: argparse.ArgumentParser) -> None:
    """Register shared arguments."""
    parser.add_argument("type", type=normalize_commit_type, metavar="TYPE")
    parser.add_argument("description", nargs="+", help="Short branch description.")
    parser.add_argument("--scope", metavar="SCOPE", default=None, help="Optional scope.")
    parser.add_argument("--dry-run", action="store_true", help="Preview without touching git.")


def cmd_new(args: argparse.Namespace) -> int:
    """Create a new branch."""
    root = Path.cwd()
    description = join_description(args.description)
    branch = BranchName(type=args.type, description=description, scope=args.scope)
    branch_name = branch.slug()
    commit_title = branch.commit_title()

    base = "<current>" if args.dry_run else git.current_branch(root)
    title = "[DRY RUN] New branch" if args.dry_run else "New branch"
    print()
    print(
        output.panel(
            title,
            [("Base", base), ("Branch", branch_name), ("Title", commit_title)],
        )
    )
    print()

    if not args.dry_run and git.branch_exists(root, branch_name):
        print(
            f"Branch '{branch_name}' already exists. Delete it first or choose a different description.",
            file=sys.stderr,
        )
        return 1

    has_changes = not args.dry_run and not git.working_tree_clean(root)

    print(output.section("Creating branch"))
    git.run(
        ["git", "checkout", "-b", branch_name], root, dry_run=args.dry_run, label="git checkout -b"
    )

    if has_changes:
        print(f"{output.action('Uncommitted changes moved to the new branch.')}\n")

    print(output.ok(f"Done. Suggested commit title: {commit_title}"))
    print()
    if args.dry_run:
        print(output.dry_run_complete("no changes made"))
    return 0


def cmd_rescue(args: argparse.Namespace) -> int:
    """Rescue commits into a new branch."""
    root = Path.cwd()
    description = join_description(args.description)
    branch = BranchName(type=args.type, description=description, scope=args.scope)
    branch_name = branch.slug()
    commit_title = branch.commit_title()

    origin_branch = "main" if args.dry_run else git.current_branch(root)
    if args.since:
        log_lines = [] if args.dry_run else git.commits_ahead(root, args.since)
        reset_target = args.since
    else:
        remote_ref = f"origin/{origin_branch}"
        log_lines = [] if args.dry_run else git.commits_ahead(root, remote_ref)
        reset_target = remote_ref

    title = "[DRY RUN] Rescue commits" if args.dry_run else "Rescue commits"
    print()
    print(
        output.panel(
            title,
            [
                ("From", origin_branch),
                ("Branch", branch_name),
                ("Reset to", reset_target),
                ("Title", commit_title),
            ],
        )
    )
    print()

    if not log_lines and not args.dry_run:
        ref_label = args.since or f"origin/{origin_branch}"
        print(
            f"No commits found ahead of '{ref_label}'. Nothing to rescue. Use --since <sha> to override.",
            file=sys.stderr,
        )
        return 1

    print(output.section("Commits to rescue"))
    if log_lines:
        for line in log_lines:
            print(output.status(output.GLYPHS.bullet.dot, line))
    else:
        ahead = args.since or f"origin/{origin_branch}"
        print(output.dry_run(f"Would detect commits ahead of {ahead}"))

    if not args.dry_run and git.branch_exists(root, branch_name):
        print(
            f"Branch '{branch_name}' already exists. Delete it first or choose a different description.",
            file=sys.stderr,
        )
        return 1

    print(f"\n{output.section('Creating rescue branch')}")
    git.run(
        ["git", "checkout", "-b", branch_name],
        root,
        dry_run=args.dry_run,
        label="git checkout -b rescue",
    )

    print(f"\n{output.section('Resetting origin branch')}")
    git.run(
        ["git", "checkout", origin_branch], root, dry_run=args.dry_run, label="git checkout origin"
    )
    git.run(
        ["git", "reset", "--hard", reset_target],
        root,
        dry_run=args.dry_run,
        label="git reset --hard",
    )

    print(f"\n{output.section('Switching back to rescue branch')}")
    git.run(
        ["git", "checkout", branch_name], root, dry_run=args.dry_run, label="git checkout rescue"
    )

    rescued_count = "Selected" if args.dry_run else str(len(log_lines))
    print()
    print(
        output.ok(
            f"Done. {rescued_count} commit(s) rescued into '{branch_name}'. "
            f"'{origin_branch}' reset to '{reset_target}'. "
            f"Suggested commit title: {commit_title}"
        )
    )
    print()
    if args.dry_run:
        print(output.dry_run_complete("no changes made"))
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register branch subcommands."""
    branch_parser = subparsers.add_parser("branch", help="Branch management helpers.")
    branch_sub = branch_parser.add_subparsers(dest="branch_command", required=True)

    new_parser = branch_sub.add_parser("new", help="Create a new conventionally named branch.")
    add_common_branch_arguments(new_parser)
    new_parser.set_defaults(handler=cmd_new)

    rescue_parser = branch_sub.add_parser(
        "rescue", help="Move commits to a new branch and reset the current branch."
    )
    add_common_branch_arguments(rescue_parser)
    rescue_parser.add_argument(
        "--since",
        metavar="SHA",
        default=None,
        help="Rescue commits since this SHA instead of origin/<branch>.",
    )
    rescue_parser.set_defaults(handler=cmd_rescue)
