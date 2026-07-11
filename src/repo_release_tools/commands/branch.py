"""Branch command helpers and utilities for conventional branches.

## Overview

The `rrt branch` command family provides a suite of helpers for managing
semantic, conventionally-named Git branches. By enforcing a consistent naming
structure—such as `feat/add-parser` or `fix/config-loader`—the tool ensures
that the repository's branch history remains searchable, readable, and
aligned with standard `conventional-commits` policies.

These helpers are particularly useful for teams practicing trunk-based
development, where branch names often serve as the primary signal for
automated release notes and CI workflow routing.

## Responsibilities

- validate branch names against project-specific prefix and slug rules
- scaffold new branches using the canonical `<type>/<kebab-slug>` format
- automate the renaming of branches while preserving description context
- "rescue" uncommitted work or divergent commits into new, semantic branches
- provide actionable suggestions when a branch name violates repository policy

## Standard Format

```text
<type>/[<scope>-]<kebab-case-description>
```

Example branches:
- `feat/add-config-discovery`
- `fix/handle-tag-workflows`
- `docs/split-readme-into-docs`

## Built-in branch types

Conventional branch types are accepted out of the box:
- `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `ci`, `perf`, `style`, `build`

## Special names

These branch names are also valid:
- `main`, `master`, `develop`
- `release/v<semver>` (validated as a semver-aware special case)

## AI helper and Bot branches

Branches created by assistant-driven workflows or dependency bots are accepted with these prefixes:
- `claude/...`, `codex/...`, `copilot/...`
- `dependabot/...`, `renovate/...`

Custom prefixes can be added via the `extra_branch_types` config key.

## Behavior

- **new**: Creates and switches to a new branch. Moves dirty changes if requested.
- **rename**: Rebuilds the current branch name based on new type, scope, or description.
- **rescue**: Moves commits ahead of upstream to a fresh semantic branch.
- **dry-run**: Previews all Git operations without modifying the repository.

## Examples

- `rrt branch new feat "add parser"`
- `rrt branch new fix "repair config loader" --scope api`
- `rrt branch rename --type fix --scope api "fix config loader"`
- `rrt branch rescue feat "rescue work in progress"`

## Caveats

- Branch slugs are limited to 60 characters by default.
- Custom branch types can be added via configuration.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from repo_release_tools.ui import GLYPHS, DryRunPrinter, VerbosePrinter
from repo_release_tools.workflow import git

SEMANTIC_BRANCHES_DOC = (
    "# rrt branch\n\n"
    "Branch command helpers and utilities for conventional branches.\n\n"
    f"{(__doc__ or '').split('\n\n', 1)[1]}"
    if __doc__ and "\n\n" in __doc__
    else (__doc__ or "")
)

# Ordered source-owned topic docs for future generic docs generation.
SOURCE_OWNED_TOPIC_DOCS: tuple[tuple[str, str], ...] = (("branch", SEMANTIC_BRANCHES_DOC),)

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
STATUS_MAX = 15
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
            f"invalid conventional type: {value!r} (choose one of: {allowed})",
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


@dataclass(frozen=True)
class NewOptions:
    """Typed view of ``argparse.Namespace`` for ``rrt branch new``.

    Built once via :meth:`from_args` at the top of :func:`cmd_new` so all
    flags it reads have typed read sites instead of ``getattr(args, ...,
    default)`` / ``args.x`` calls throughout the function body.
    """

    type: str
    description: list[str]
    scope: str | None
    dry_run: bool
    verbose: int

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> NewOptions:
        """Build a :class:`NewOptions` from a parsed ``argparse.Namespace``.

        ``type``, ``description``, ``scope``, and ``dry_run`` are all
        positional/required or given real defaults by branch.py's own
        add_common_branch_arguments(), and every test in
        tests/commands/test_branch.py that exercises cmd_new sets all four
        explicitly, so they are read directly. ``verbose`` is set globally by
        cli.py's parser, but no test Namespace here ever sets it, so the
        getattr fallback here absorbs that gap.
        """
        return cls(
            type=args.type,
            description=args.description,
            scope=args.scope,
            dry_run=args.dry_run,
            verbose=getattr(args, "verbose", 0) or 0,
        )


def cmd_new(args: argparse.Namespace) -> int:
    """Create a new branch."""
    opts = NewOptions.from_args(args)
    verbose = opts.verbose
    root = Path.cwd()
    description = join_description(opts.description)
    branch = BranchName(type=opts.type, description=description, scope=opts.scope)
    branch_name = branch.slug()
    commit_title = branch.commit_title()

    base = "<current>" if opts.dry_run else git.current_branch(root)
    p = DryRunPrinter(opts.dry_run, verbose=verbose)
    p.blank_line()
    p.header("New branch", Base=base, Branch=branch_name, Title=commit_title)

    if not opts.dry_run and git.branch_exists(root, branch_name):
        p.line(
            f"Branch '{branch_name}' already exists. Delete it first or choose a different description.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    status_lines = git.status_porcelain(root)
    dirty = bool(status_lines)
    staged_count, unstaged_count = _count_status_changes(status_lines)

    p.section("Creating branch")
    git.run(
        ["git", "checkout", "-b", branch_name],
        root,
        dry_run=opts.dry_run,
        label="git checkout -b",
    )

    if dirty:
        action_text = (
            "Would move uncommitted changes to the new branch."
            if opts.dry_run
            else "Uncommitted changes moved to the new branch."
        )
        p.action(action_text)
        p.meta("Files changed", str(len(status_lines)))
        p.meta("Staged", str(staged_count))
        p.meta("Unstaged", str(unstaged_count))
        p.section("Changed files")
        shown = status_lines[:STATUS_MAX]
        for line in shown:
            p.file_entry(*git.classify_status_line(line))
        if len(status_lines) > STATUS_MAX:
            p.action(f"…and {len(status_lines) - STATUS_MAX} more")
    else:
        clean_message = (
            "No uncommitted changes would be moved." if opts.dry_run else "Working tree clean."
        )
        p.ok(clean_message)

    p.footer(f"Done. Suggested commit title: {commit_title}")
    return 0


def _parse_current_branch(branch: str) -> tuple[str, str]:
    """Split ``type/slug`` → ``(type, slug)``.

    Raises :exc:`ValueError` when the branch name does not follow the
    ``type/slug`` convention expected by *rrt*.
    """
    if "/" not in branch:
        raise ValueError(
            f"Current branch {branch!r} does not follow the '<type>/<slug>' convention. "
            "Cannot determine which part to rename.",
        )
    commit_type, _, slug = branch.partition("/")
    return commit_type, slug


@dataclass(frozen=True)
class RenameOptions:
    """Typed view of ``argparse.Namespace`` for ``rrt branch rename``.

    Built once via :meth:`from_args` at the top of :func:`cmd_rename` so all
    flags it reads have typed read sites instead of ``getattr(args, ...,
    default)`` / ``args.x`` calls throughout the function body.
    """

    type: str | None
    scope: str | None
    no_scope: bool
    description: list[str]
    dry_run: bool
    verbose: int

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> RenameOptions:
        """Build a :class:`RenameOptions` from a parsed ``argparse.Namespace``.

        ``type``, ``scope``, ``no_scope``, ``description``, and ``dry_run``
        are all given real defaults by branch.py's own register() for the
        rename subparser, and every test in tests/commands/test_branch.py
        that exercises cmd_rename sets all five explicitly, so they are read
        directly. ``verbose`` is set globally by cli.py's parser, but no
        test Namespace here ever sets it, so the getattr fallback here
        absorbs that gap.
        """
        return cls(
            type=args.type,
            scope=args.scope,
            no_scope=args.no_scope,
            description=args.description,
            dry_run=args.dry_run,
            verbose=getattr(args, "verbose", 0) or 0,
        )


def cmd_rename(args: argparse.Namespace) -> int:
    """Rename the current branch, changing any combination of type / scope / description."""
    opts = RenameOptions.from_args(args)
    verbose = opts.verbose
    root = Path.cwd()
    no_scope = opts.no_scope
    new_type_arg = opts.type
    scope = opts.scope
    description_words = list(opts.description or [])

    # Validate: at least one change must be requested
    if not new_type_arg and not scope and not no_scope and not description_words:
        VerbosePrinter(verbose=verbose).line(
            "Nothing to rename. Specify --type, --scope, --no-scope, or new description words.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    # --no-scope without description means we can't strip the embedded scope from the slug
    if no_scope and not description_words:
        VerbosePrinter(verbose=verbose).line(
            "--no-scope requires description words so the slug can be rebuilt without a scope.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    current_branch = git.current_branch(root)

    try:
        current_type, current_slug = _parse_current_branch(current_branch)
    except ValueError as exc:
        VerbosePrinter(verbose=verbose).line(str(exc), ok=False, stream=sys.stderr)
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
            VerbosePrinter(verbose=verbose).line(
                f"Computed slug {new_slug!r} is too long ({len(new_slug)} > {SLUG_MAX}). "
                "Provide a new description to rebuild the slug.",
                ok=False,
                stream=sys.stderr,
            )
            return 1
        if not BRANCH_SLUG_RE.fullmatch(new_slug):
            VerbosePrinter(verbose=verbose).line(
                f"Computed slug {new_slug!r} is not valid kebab-case. "
                "Provide a new description to rebuild the slug.",
                ok=False,
                stream=sys.stderr,
            )
            return 1

        new_name = f"{new_type}/{new_slug}"
        scope_part = f"({scope})" if scope else ""
        commit_title = f"{new_type}{scope_part}: <preserved description>"

    if new_name == current_branch:
        VerbosePrinter(verbose=verbose).line(
            "Branch name is unchanged. Nothing to do.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    p = DryRunPrinter(opts.dry_run, verbose=verbose)
    p.blank_line()
    p.header(
        "Rename branch",
        **{
            f"{GLYPHS.git.branch} From": current_branch,
            f"{GLYPHS.diff.renamed} To": new_name,
            f"{GLYPHS.arrow.right} Commit title": commit_title,
        },
    )

    if not opts.dry_run:
        if git.branch_exists(root, new_name):
            p.line(
                f"Branch '{new_name}' already exists. Delete it first or choose a different name.",
                ok=False,
                stream=sys.stderr,
            )
            return 1
        git.run(
            ["git", "branch", "-m", current_branch, new_name],
            root,
            dry_run=False,
            label="git branch -m",
        )
        p.footer(f"Done. Renamed '{current_branch}' {GLYPHS.diff.renamed} '{new_name}'.")
    else:
        p.footer("no changes made")
    return 0


@dataclass(frozen=True)
class RescueOptions:
    """Typed view of ``argparse.Namespace`` for ``rrt branch rescue``.

    Built once via :meth:`from_args` at the top of :func:`cmd_rescue` so all
    flags it reads have typed read sites instead of ``getattr(args, ...,
    default)`` / ``args.x`` calls throughout the function body.
    """

    type: str
    description: list[str]
    scope: str | None
    dry_run: bool
    since: str | None
    verbose: int

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> RescueOptions:
        """Build a :class:`RescueOptions` from a parsed ``argparse.Namespace``.

        ``type``, ``description``, ``scope``, ``dry_run``, and ``since`` are
        all positional/required or given real defaults by branch.py's own
        register() for the rescue subparser, and every test in
        tests/commands/test_branch.py that exercises cmd_rescue sets all
        five explicitly, so they are read directly. ``verbose`` is set
        globally by cli.py's parser, but no test Namespace here ever sets
        it, so the getattr fallback here absorbs that gap.
        """
        return cls(
            type=args.type,
            description=args.description,
            scope=args.scope,
            dry_run=args.dry_run,
            since=args.since,
            verbose=getattr(args, "verbose", 0) or 0,
        )


def cmd_rescue(args: argparse.Namespace) -> int:
    """Rescue commits into a new branch."""
    opts = RescueOptions.from_args(args)
    verbose = opts.verbose
    root = Path.cwd()
    description = join_description(opts.description)
    branch = BranchName(type=opts.type, description=description, scope=opts.scope)
    branch_name = branch.slug()
    commit_title = branch.commit_title()

    origin_branch = "main" if opts.dry_run else git.current_branch(root)
    reset_target = opts.since or f"origin/{origin_branch}"
    try:
        log_lines = [] if opts.dry_run else git.commits_ahead(root, reset_target)
    except ValueError as exc:
        VerbosePrinter(verbose=verbose).line(str(exc), ok=False, stream=sys.stderr)
        return 1

    p = DryRunPrinter(opts.dry_run, verbose=verbose)
    p.blank_line()
    p.header(
        "Rescue commits",
        From=origin_branch,
        Branch=branch_name,
        **{"Reset to": reset_target, "Title": commit_title},
    )

    if not log_lines and not opts.dry_run:
        ref_label = opts.since or f"origin/{origin_branch}"
        p.line(
            f"No commits found ahead of '{ref_label}'. Nothing to rescue. Use --since <sha> to override.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    p.section("Commits to rescue")
    if log_lines:
        for line in log_lines:
            p.list_item(line)
    else:
        ahead = opts.since or f"origin/{origin_branch}"
        p.would_run(f"git log {ahead}..HEAD --oneline")

    if not opts.dry_run and git.branch_exists(root, branch_name):
        p.line(
            f"Branch '{branch_name}' already exists. Delete it first or choose a different description.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    p.blank_line()
    p.section("Creating rescue branch")
    git.run(
        ["git", "checkout", "-b", branch_name],
        root,
        dry_run=opts.dry_run,
        label="git checkout -b rescue",
    )

    p.blank_line()
    p.section("Resetting origin branch")
    git.run(
        ["git", "checkout", origin_branch],
        root,
        dry_run=opts.dry_run,
        label="git checkout origin",
    )
    git.run(
        ["git", "reset", "--hard", reset_target],
        root,
        dry_run=opts.dry_run,
        label="git reset --hard",
    )

    p.blank_line()
    p.section("Switching back to rescue branch")
    git.run(
        ["git", "checkout", branch_name],
        root,
        dry_run=opts.dry_run,
        label="git checkout rescue",
    )

    rescued_count = "Selected" if opts.dry_run else str(len(log_lines))
    p.blank_line()
    p.footer(
        f"Done. {rescued_count} commit(s) rescued into '{branch_name}'. "
        f"'{origin_branch}' reset to '{reset_target}'. "
        f"Suggested commit title: {commit_title}",
    )
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
        "--dry-run",
        action="store_true",
        help="Preview the rename without touching git.",
    )
    rename_parser.set_defaults(handler=cmd_rename)
