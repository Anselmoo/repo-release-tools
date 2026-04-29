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
BRANCH_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

BRANCH_EPILOG = (
    '  $ rrt branch new feat "add parser"\n'
    '  $ rrt branch new fix "repair config loader" --scope api\n'
    '  $ rrt branch rename --type fix --scope api "fix config loader"\n'
    '  $ rrt branch rescue feat "rescue work in progress"'
)


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


def _count_status_changes(status_lines: list[str]) -> tuple[int, int]:
    staged = 0
    unstaged = 0
    for line in status_lines:
        if len(line) >= 2:
            staged += 1 if line[0] != " " else 0
            unstaged += 1 if line[1] != " " else 0
    return staged, unstaged


def _status_rows(status_lines: list[str]) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for line in status_lines:
        if len(line) < 3:
            continue
        rows.append((line[3:], line[:2]))
    return rows


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
    print(output.ok(title))
    print(output.info(f"Base: {base}"))
    print(output.info(f"Branch: {branch_name}"))
    print(output.info(f"Title: {commit_title}"))
    print()

    if not args.dry_run and git.branch_exists(root, branch_name):
        print(
            f"Branch '{branch_name}' already exists. Delete it first or choose a different description.",
            file=sys.stderr,
        )
        return 1

    status_lines = git.status_porcelain(root)
    dirty = bool(status_lines)
    staged_count, unstaged_count = _count_status_changes(status_lines)

    print(output.section("Creating branch"))
    git.run(
        ["git", "checkout", "-b", branch_name], root, dry_run=args.dry_run, label="git checkout -b"
    )

    if dirty:
        action_text = (
            "Would move uncommitted changes to the new branch."
            if args.dry_run
            else "Uncommitted changes moved to the new branch."
        )
        print(f"{output.action(action_text)}\n")
        summary = f"Files changed: {len(status_lines)} | Staged: {staged_count} | Unstaged: {unstaged_count}"
        print(output.info(summary))
        print(output.section("Changed files"))
        for path, status in _status_rows(status_lines):
            print(output.status(status, path, indent=2))
        print()
    else:
        clean_message = (
            "No uncommitted changes would be moved." if args.dry_run else "Working tree clean."
        )
        if args.dry_run:
            print(output.dry_run(clean_message))
        else:
            print(output.ok(clean_message))
        print()

    print(output.ok(f"Done. Suggested commit title: {commit_title}"))
    print()
    if args.dry_run:
        print(output.dry_run_complete("no changes made"))
    return 0


def _parse_current_branch(branch: str) -> tuple[str, str]:
    """Split ``type/slug`` → ``(type, slug)``.

    Raises :exc:`ValueError` when the branch name does not follow the
    ``type/slug`` convention expected by *rrt*.
    """
    if "/" not in branch:
        raise ValueError(
            f"Current branch {branch!r} does not follow the '<type>/<slug>' convention. "
            "Cannot determine which part to rename."
        )
    commit_type, _, slug = branch.partition("/")
    return commit_type, slug


def cmd_rename(args: argparse.Namespace) -> int:
    """Rename the current branch, changing any combination of type / scope / description."""
    root = Path.cwd()
    no_scope: bool = getattr(args, "no_scope", False)
    new_type_arg: str | None = getattr(args, "type", None)
    scope: str | None = getattr(args, "scope", None)
    description_words: list[str] = list(getattr(args, "description", None) or [])

    # Validate: at least one change must be requested
    if not new_type_arg and not scope and not no_scope and not description_words:
        print(
            "Nothing to rename. Specify --type, --scope, --no-scope, or new description words.",
            file=sys.stderr,
        )
        return 1

    # --no-scope without description means we can't strip the embedded scope from the slug
    if no_scope and not description_words:
        print(
            "--no-scope requires description words so the slug can be rebuilt without a scope.",
            file=sys.stderr,
        )
        return 1

    current_branch = git.current_branch(root)

    try:
        current_type, current_slug = _parse_current_branch(current_branch)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1

    new_type = new_type_arg or current_type

    if description_words:
        # Full rebuild: type + scope + new description
        description = join_description(description_words)
        effective_scope = None if no_scope else scope
        branch = BranchName(type=new_type, description=description, scope=effective_scope)
        new_name = branch.slug()
        commit_title = branch.commit_title()
    else:
        # Slug-preserving rename: only type and/or scope prefix changes
        if scope:
            scope_slug = re.sub(r"[^a-z0-9]+", "-", scope.lower()).strip("-")
            new_slug = f"{scope_slug}-{current_slug}"
        else:
            new_slug = current_slug

        # Validate the resulting slug against the same rules used by branch creation
        if len(new_slug) > SLUG_MAX:
            print(
                f"Computed slug {new_slug!r} is too long ({len(new_slug)} > {SLUG_MAX}). "
                "Provide a new description to rebuild the slug.",
                file=sys.stderr,
            )
            return 1
        if not BRANCH_SLUG_RE.fullmatch(new_slug):
            print(
                f"Computed slug {new_slug!r} is not valid kebab-case. "
                "Provide a new description to rebuild the slug.",
                file=sys.stderr,
            )
            return 1

        new_name = f"{new_type}/{new_slug}"
        scope_part = f"({scope})" if scope else ""
        commit_title = f"{new_type}{scope_part}: <preserved description>"

    if new_name == current_branch:
        print("Branch name is unchanged. Nothing to do.", file=sys.stderr)
        return 1

    g = output.GLYPHS
    title = "[DRY RUN] Rename branch" if args.dry_run else "Rename branch"
    print()
    print(output.ok(title))
    print(output.info(f"{g.git.branch} From: {current_branch}"))
    print(output.info(f"{g.diff.renamed} To: {new_name}"))
    print(output.info(f"{g.arrow.right} Commit title: {commit_title}"))
    print()

    if not args.dry_run:
        if git.branch_exists(root, new_name):
            print(
                f"Branch '{new_name}' already exists. Delete it first or choose a different name.",
                file=sys.stderr,
            )
            return 1
        git.run(
            ["git", "branch", "-m", current_branch, new_name],
            root,
            dry_run=False,
            label="git branch -m",
        )
        print(output.ok(f"Done. Renamed '{current_branch}' {g.diff.renamed} '{new_name}'."))
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
    print(output.ok(title))
    print(output.info(f"From: {origin_branch}"))
    print(output.info(f"Branch: {branch_name}"))
    print(output.info(f"Reset to: {reset_target}"))
    print(output.info(f"Title: {commit_title}"))
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
    branch_parser = subparsers.add_parser(
        "branch",
        help="Branch management helpers.",
        description="Branch management helpers for conventional branch naming.",
        epilog=BRANCH_EPILOG,
    )
    branch_sub = branch_parser.add_subparsers(
        dest="branch_command",
        metavar="<branch_command>",
        parser_class=type(branch_parser),
        required=True,
    )

    new_parser = branch_sub.add_parser(
        "new",
        help="Create a new conventionally named branch.",
        description="Create a new conventionally named branch from a commit type, optional scope, and description.",
        epilog=BRANCH_EPILOG,
    )
    add_common_branch_arguments(new_parser)
    new_parser.set_defaults(handler=cmd_new)

    rescue_parser = branch_sub.add_parser(
        "rescue",
        help="Move commits to a new branch and reset the current branch.",
        description="Rescue commits onto a new branch and reset the current branch to a safe point.",
        epilog=BRANCH_EPILOG,
    )
    add_common_branch_arguments(rescue_parser)
    rescue_parser.add_argument(
        "--since",
        metavar="SHA",
        default=None,
        help="Rescue commits since this SHA instead of origin/<branch>.",
    )
    rescue_parser.set_defaults(handler=cmd_rescue)

    rename_parser = branch_sub.add_parser(
        "rename",
        help="Rename the current branch: change type, scope, description, or any combination.",
        description="Rename the current branch using conventional branch naming rules.",
        epilog=BRANCH_EPILOG,
    )
    rename_parser.add_argument(
        "--type",
        dest="type",
        type=normalize_commit_type,
        metavar="TYPE",
        default=None,
        help="New conventional commit type (e.g. feat, fix, build).",
    )
    rename_parser.add_argument(
        "--scope",
        metavar="SCOPE",
        default=None,
        help="New scope to prefix the slug with.",
    )
    rename_parser.add_argument(
        "--no-scope",
        action="store_true",
        default=False,
        help="Remove the scope from the new branch name (requires description words).",
    )
    rename_parser.add_argument(
        "description",
        nargs="*",
        help="New branch description words (replaces the current description).",
    )
    rename_parser.add_argument(
        "--dry-run", action="store_true", help="Preview the rename without touching git."
    )
    rename_parser.set_defaults(handler=cmd_rename)
