"""Run opinionated Git workflow helpers for rrt.

`rrt git` bundles the repository workflows that are used most often while
developing and releasing this project. The command group favors compact,
human-readable summaries with explicit safety checks before any destructive
operation.

Most commands are designed to run from a Git work tree and emit a short
summary first, followed by the details needed to act on the result.

## Command families

### Inspection

- `status` shows the current branch, upstream, and a compact view of worktree
  changes.
- `diff` renders a condensed diff for the working tree, staged changes, or a
  specific ref.
- `log` shows recent commits with short SHAs, subjects, and refs.
- `doctor` runs a repository health report for common rrt workflow rules.
- `sync-status` reports unresolved conflicts and ahead/behind drift against a
  sync base.
- `check-dirty-tree` exits non-zero when the worktree is dirty, which makes it
  useful for hooks and CI.

### Commit drafting

- `commit` creates one conventional commit and infers the type from the current
  branch when possible.
- `commit-all` stages all tracked and untracked files before creating the
  commit.
- `squash-local` squashes commits ahead of an upstream branch or `--base-ref`
  into one conventional commit.

### Branch maintenance and synchronization

- `sync` fetches, auto-stashes dirty changes when needed, and pulls from the
  upstream branch.
- `move` switches branches safely and can create the target branch first.
- `undo-safe` resets to another ref while keeping changes staged or in the
  working tree.
- `rebootstrap` backs up `.git`, reinitializes the repository, and creates a
  fresh history snapshot or empty bootstrap commit.
- `purge-cache` expires reflogs and runs `git gc` to reclaim local cache space.

## Behavior details

- Commit subjects use conventional commit syntax with optional scope and
  breaking markers.
- Commands that support `--dry-run` preview the git operations without making
  changes.
- Several commands refuse to continue when the repository is in an unsafe
  state, such as unresolved conflicts, an in-progress merge or rebase, or a
  missing upstream branch.
- `rebootstrap` requires explicit confirmation before it can destroy history.
- `purge-cache` is safe for normal worktrees but can take time on large repos;
    use `--dry-run` first to preview the maintenance commands.

## Examples

```text
$ rrt git status
$ rrt git commit "refresh help examples"
$ rrt git sync --dry-run
$ rrt git squash-local --base-ref origin/main "ship parser"
$ rrt git rebootstrap --yes-i-know-this-destroys-history --dry-run
$ rrt git purge-cache --dry-run
```

## Safety notes

- `sync` and `move` auto-stash local changes, but a failed pull or checkout can
  leave the stash on the stack.
- `undo-safe` and `rebootstrap` can rewrite repository history; use them only
  when that is intended.
- `rebootstrap` also guards against accidental use on repositories with
  configured remotes unless explicitly allowed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from repo_release_tools.commands._git_shared import (
    STATUS_MAX,
    add_dry_run_flag,
    conflict_status_lines,
    load_status_lines,
    summarize_status,
)
from repo_release_tools.commands.branch import CONVENTIONAL_TYPES, join_description
from repo_release_tools.commands.git_inspect import register_inspect
from repo_release_tools.ui import (
    DryRunPrinter,
    VerbosePrinter,
    spinner_lines,
)
from repo_release_tools.workflow import git
from repo_release_tools.workflow.hooks import (
    ALLOWED_BRANCH_NAMES,
    BOT_BRANCH_TYPES,
    MAGIC_BRANCH_TYPES,
)

COMMIT_TYPES = (*CONVENTIONAL_TYPES, "deps")
DEFAULT_REBOOTSTRAP_EMPTY_MESSAGE = "chore: bootstrap repository"
DEFAULT_REBOOTSTRAP_MESSAGE = "chore: initial commit"
MOVE_STASH_MESSAGE = "rrt git move auto-stash"
SYNC_STASH_MESSAGE = "rrt git sync auto-stash"


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


def backup_path_for_git_dir(root: Path) -> Path:
    """Return an external backup path for the current .git directory."""
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d%H%M%S")
    return root.parent / f".{root.name}.git-backup-{stamp}"


def require_explicit_confirmation(args: argparse.Namespace) -> bool:
    """Return whether the destructive rebootstrap command is confirmed."""
    return bool(args.yes_i_know_this_destroys_history)


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


def cmd_sync(args: argparse.Namespace) -> int:
    """Fetch, stash when needed, and pull the current branch."""
    verbose: int = getattr(args, "verbose", 0) or 0
    root = Path.cwd()
    if not git.is_git_repository(root):
        p = VerbosePrinter(verbose=verbose)
        p.line(f"{root} is not inside a Git work tree.", ok=False, stream=sys.stderr)
        return 1
    branch_name = git.current_branch(root) or "<detached>"
    upstream = git.upstream_branch(root)
    if upstream is None:
        p = VerbosePrinter(verbose=verbose)
        p.line(
            "No upstream branch is configured for the current branch. Set one first or use git push -u.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    dirty = not git.working_tree_clean(root)
    try:
        status_lines = load_status_lines(root)
    except RuntimeError as exc:
        p = VerbosePrinter(verbose=verbose)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1
    conflicts = conflict_status_lines(status_lines)
    operation = git.in_progress_operation(root)
    if operation is not None:
        p = VerbosePrinter(verbose=verbose)
        p.line(
            f"Cannot sync while a {operation} is in progress. Resolve or abort it first.",
            ok=False,
            stream=sys.stderr,
        )
        return 1
    if conflicts:
        p = VerbosePrinter(verbose=verbose)
        p.line("Cannot sync with unresolved merge conflicts.", ok=False, stream=sys.stderr)
        shown = conflicts[:STATUS_MAX]
        for line in shown:
            p.file_entry(*git.classify_status_line(line), stream=sys.stderr)
        if len(conflicts) > STATUS_MAX:
            p.action(f"…and {len(conflicts) - STATUS_MAX} more", stream=sys.stderr)
        return 1
    p = DryRunPrinter(args.dry_run, verbose=verbose)
    strategy = "merge" if args.merge else "rebase"
    p.blank_line()
    p.header(
        "Sync",
        Branch=branch_name,
        Upstream=upstream,
        Strategy=strategy,
        **{
            "Working tree": "dirty" if dirty else "clean",
            "Status": summarize_status(branch_name, status_lines, upstream=upstream),
        },
    )
    p.section("Syncing")
    with spinner_lines("Fetching…"):
        git.run(["git", "fetch", "--prune"], root, dry_run=args.dry_run, label="git fetch")
    if dirty:
        git.run(
            ["git", "stash", "push", "-u", "-m", SYNC_STASH_MESSAGE],
            root,
            dry_run=args.dry_run,
            label="git stash push",
        )

    pull_command = ["git", "pull"]
    if not args.merge:
        pull_command.append("--rebase")

    try:
        git.run(pull_command, root, dry_run=args.dry_run, label="git pull")
    except RuntimeError:
        if dirty and not args.dry_run:
            p.line(
                "Pull failed. The auto-stash remains on the stash stack.",
                ok=False,
                stream=sys.stderr,
            )
        raise

    if dirty:
        git.run(["git", "stash", "pop"], root, dry_run=args.dry_run, label="git stash pop")

    p.blank_line()
    p.footer(f"Done. {branch_name} is synced from {upstream} using {strategy}.")
    return 0


def cmd_move(args: argparse.Namespace) -> int:
    """Switch branches safely by stashing and restoring local changes."""
    verbose: int = getattr(args, "verbose", 0) or 0
    root = Path.cwd()
    if not git.is_git_repository(root):
        p = VerbosePrinter(verbose=verbose)
        p.line(f"{root} is not inside a Git work tree.", ok=False, stream=sys.stderr)
        return 1
    p = DryRunPrinter(args.dry_run, verbose=verbose)
    current = git.current_branch(root) or "<detached>"
    dirty = not git.working_tree_clean(root)
    target_label = f"new branch {args.target}" if args.create else args.target
    p.blank_line()
    p.header(
        "Move",
        From=current,
        To=target_label,
        **{"Working tree": "dirty" if dirty else "clean"},
    )
    p.section("Switching")
    if dirty:
        git.run(
            ["git", "stash", "push", "-u", "-m", MOVE_STASH_MESSAGE],
            root,
            dry_run=args.dry_run,
            label="git stash push",
        )

    checkout = (
        ["git", "checkout", "-b", args.target] if args.create else ["git", "checkout", args.target]
    )
    try:
        git.run(checkout, root, dry_run=args.dry_run, label="git checkout")
    except RuntimeError:
        if dirty and not args.dry_run:
            p.line(
                "Branch switch failed. The auto-stash remains on the stash stack.",
                ok=False,
                stream=sys.stderr,
            )
        raise

    if dirty:
        git.run(["git", "stash", "pop"], root, dry_run=args.dry_run, label="git stash pop")

    p.blank_line()
    p.footer(f"Done. Switched to {args.target!r}.")
    return 0


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


def cmd_undo_safe(args: argparse.Namespace) -> int:
    """Undo the last commit while keeping work in the index or working tree."""
    verbose: int = getattr(args, "verbose", 0) or 0
    mode = "--soft" if args.keep_staged else "--mixed"
    p = DryRunPrinter(args.dry_run, verbose=verbose)
    p.blank_line()
    p.header(
        "Undo safe",
        Target=args.target,
        Mode="keep staged" if args.keep_staged else "keep files",
    )

    git.run(
        ["git", "reset", mode, args.target],
        Path.cwd(),
        dry_run=args.dry_run,
        label="git reset",
    )
    p.blank_line()
    p.footer(f"Done. Reset to {args.target!r} using {mode}.")
    return 0


def cmd_rebootstrap(args: argparse.Namespace) -> int:
    """Remove repository history and create a fresh initial history."""
    verbose: int = getattr(args, "verbose", 0) or 0
    root = Path.cwd()
    git_dir = git.git_dir(root) or (root / ".git")
    if not git_dir.exists():
        p = VerbosePrinter(verbose=verbose)
        p.line(f"{root} does not look like a Git repository.", ok=False, stream=sys.stderr)
        return 1
    if not require_explicit_confirmation(args):
        p = VerbosePrinter(verbose=verbose)
        p.line(
            "Refusing to destroy repository history without --yes-i-know-this-destroys-history.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    if args.hard_init and args.empty_first:
        p = VerbosePrinter(verbose=verbose)
        p.line("Use either --hard-init or --empty-first, not both.", ok=False, stream=sys.stderr)
        return 1

    remotes = git.remote_names(root)
    if remotes and not args.allow_remote:
        p = VerbosePrinter(verbose=verbose)
        p.line(
            "Refusing to rebootstrap a repository with configured remotes. Use --allow-remote if that is intentional.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    branch_name = args.branch or git.current_branch(root) or "main"
    backup_path = backup_path_for_git_dir(root)
    commit_message = args.message
    if commit_message is None:
        commit_message = (
            DEFAULT_REBOOTSTRAP_EMPTY_MESSAGE if args.hard_init else DEFAULT_REBOOTSTRAP_MESSAGE
        )
    p = DryRunPrinter(args.dry_run, verbose=verbose)
    p.blank_line()
    p.header(
        "Rebootstrap history",
        Branch=branch_name,
        Mode="empty hard-init" if args.hard_init else "snapshot current files",
        Backup=str(backup_path),
        **{
            "Remote guard": "ignored" if args.allow_remote else "enabled",
            "Commit": commit_message,
        },
    )
    p.section("Reinitializing")
    if args.dry_run:
        p.would_run(f"mv {git_dir} {backup_path}")
        git.run(["git", "init", "-b", branch_name], root, dry_run=True, label="git init")
        if args.hard_init:
            git.run(
                ["git", "commit", "--allow-empty", "-m", commit_message],
                root,
                dry_run=True,
                label="git commit --allow-empty",
            )
        elif args.empty_first:
            git.run(
                ["git", "commit", "--allow-empty", "-m", args.empty_message],
                root,
                dry_run=True,
                label="git commit --allow-empty",
            )
        if not args.hard_init:
            git.run(["git", "add", "."], root, dry_run=True, label="git add")
            git.run(["git", "commit", "-m", commit_message], root, dry_run=True, label="git commit")
        p.footer("Done. Reinit preview complete.")
        return 0

    shutil.move(str(git_dir), str(backup_path))
    p.action(f"Moved original git data to {backup_path}")

    try:
        git.run(["git", "init", "-b", branch_name], root, dry_run=False, label="git init")
        if args.hard_init:
            git.run(
                ["git", "commit", "--allow-empty", "-m", commit_message],
                root,
                dry_run=False,
                label="git commit --allow-empty",
            )
        elif args.empty_first:
            git.run(
                ["git", "commit", "--allow-empty", "-m", args.empty_message],
                root,
                dry_run=False,
                label="git commit --allow-empty",
            )
        if not args.hard_init:
            git.run(["git", "add", "."], root, dry_run=False, label="git add")
            git.run(
                ["git", "commit", "-m", commit_message],
                root,
                dry_run=False,
                label="git commit",
            )
    except RuntimeError as exc:
        p = VerbosePrinter(verbose=verbose)
        p.line(
            f"Rebootstrap failed. Original git data is backed up at {backup_path}.",
            ok=False,
            stream=sys.stderr,
        )
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1

    p.blank_line()
    if args.hard_init:
        p.ok(f"Done. Repository history hard-initialized on {branch_name!r}.")
    else:
        p.ok(f"Done. Repository history reinitialized on {branch_name!r}.")
    p.line(f"Original git data: {backup_path}")
    return 0


def cmd_purge_cache(args: argparse.Namespace) -> int:
    """Expire reflogs and run git garbage collection."""
    verbose: int = getattr(args, "verbose", 0) or 0
    root = Path.cwd()
    if not git.is_git_repository(root):
        p = VerbosePrinter(verbose=verbose)
        p.line(f"{root} is not inside a Git work tree.", ok=False, stream=sys.stderr)
        return 1

    dirty = not git.working_tree_clean(root)
    p = DryRunPrinter(args.dry_run, verbose=verbose)
    p.blank_line()
    p.header(
        "Purge cache",
        **{
            "Working tree": "dirty" if dirty else "clean",
            "Scope": "reflogs + git gc",
        },
    )
    if dirty:
        p.warn("Working tree changes are preserved; this only rewrites local Git maintenance data.")

    p.section("Purging")
    git.run(
        ["git", "reflog", "expire", "--expire=now", "--all"],
        root,
        dry_run=args.dry_run,
        label="git reflog expire",
    )
    git.run(["git", "gc", "--prune=now"], root, dry_run=args.dry_run, label="git gc")

    p.blank_line()
    p.footer("Done. Git cache maintenance complete.")
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


GIT_EPILOG = (
    "  $ rrt git status\n"
    "  $ rrt git diff --against HEAD~1\n"
    '  $ rrt git commit --type fix "make output clearer"\n'
    "  $ rrt git sync\n"
    "  $ rrt git undo-safe"
)

GIT_COMMIT_EXAMPLES = (
    '  $ rrt git commit "refresh help examples"\n'
    '  $ rrt git commit --type fix --scope cli "handle empty config"\n'
    '  $ rrt git commit --breaking "ship parser v2"'
)

GIT_COMMIT_ALL_EXAMPLES = (
    '  $ rrt git commit-all "refresh release metadata"\n'
    '  $ rrt git commit-all --type chore --scope deps "update lockfiles"'
)

GIT_SYNC_EXAMPLES = "  $ rrt git sync\n  $ rrt git sync --merge\n  $ rrt git sync --dry-run"

GIT_MOVE_EXAMPLES = "  $ rrt git move release/v1.2.0\n  $ rrt git move -b feat/help-copy --dry-run"

GIT_SQUASH_LOCAL_EXAMPLES = (
    '  $ rrt git squash-local "ship parser"\n'
    '  $ rrt git squash-local --base-ref origin/main --type fix "repair sync handling"'
)

GIT_UNDO_SAFE_EXAMPLES = (
    "  $ rrt git undo-safe\n"
    "  $ rrt git undo-safe --keep-staged\n"
    "  $ rrt git undo-safe --target HEAD~2 --dry-run"
)

GIT_REBOOTSTRAP_EXAMPLES = (
    "  $ rrt git rebootstrap --yes-i-know-this-destroys-history --dry-run\n"
    "  $ rrt git rebootstrap --yes-i-know-this-destroys-history --empty-first\n"
    "  $ rrt git rebootstrap --yes-i-know-this-destroys-history --hard-init --branch main"
)

GIT_PURGE_CACHE_EXAMPLES = "  $ rrt git purge-cache\n  $ rrt git purge-cache --dry-run"


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the git command group."""
    parser = subparsers.add_parser(
        "git",
        help="Git workflow helpers.",
        description="Git workflow helpers for repository status, commit, sync, and history operations.",
        epilog=GIT_EPILOG,
    )
    git_sub = parser.add_subparsers(
        dest="git_command",
        metavar="<git_command>",
        parser_class=type(parser),
        required=True,
    )

    register_inspect(git_sub)

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

    sync_parser = git_sub.add_parser(
        "sync",
        help="Fetch, stash if needed, and pull the current branch safely.",
        description="Fetch, auto-stash when needed, and pull the current branch from its upstream using rebase by default.",
        epilog=GIT_SYNC_EXAMPLES,
    )
    sync_parser.add_argument(
        "--merge",
        action="store_true",
        help="Use plain git pull instead of git pull --rebase.",
    )
    add_dry_run_flag(sync_parser)
    sync_parser.set_defaults(handler=cmd_sync)

    move_parser = git_sub.add_parser(
        "move",
        help="Switch branches safely by stashing and restoring local changes.",
        description="Switch to another branch, optionally creating it, while auto-stashing and restoring local changes when needed.",
        epilog=GIT_MOVE_EXAMPLES,
    )
    move_parser.add_argument("target", help="Target branch name.")
    move_parser.add_argument(
        "-b",
        "--create",
        action="store_true",
        help="Create the target branch before switching to it.",
    )
    add_dry_run_flag(move_parser)
    move_parser.set_defaults(handler=cmd_move)

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

    undo_parser = git_sub.add_parser(
        "undo-safe",
        help="Undo a commit while keeping work staged or in the working tree.",
        description="Reset to HEAD~1 or another target while keeping changes staged (--keep-staged) or in the working tree.",
        epilog=GIT_UNDO_SAFE_EXAMPLES,
    )
    undo_parser.add_argument(
        "--target",
        default="HEAD~1",
        metavar="REF",
        help="Ref to reset to. Defaults to HEAD~1.",
    )
    undo_parser.add_argument(
        "--keep-staged",
        action="store_true",
        help="Use git reset --soft so changes stay staged.",
    )
    add_dry_run_flag(undo_parser)
    undo_parser.set_defaults(handler=cmd_undo_safe)

    rebootstrap_parser = git_sub.add_parser(
        "rebootstrap",
        help="Destroy current git history and create a fresh repository history.",
        description="Back up the current .git directory, reinitialize the repository, and create a fresh history snapshot or empty bootstrap commit.",
        epilog=GIT_REBOOTSTRAP_EXAMPLES,
    )
    rebootstrap_parser.add_argument(
        "--yes-i-know-this-destroys-history",
        action="store_true",
        help="Required confirmation for the destructive history reset.",
    )
    rebootstrap_parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Allow rebootstrap even when remotes are configured.",
    )
    rebootstrap_parser.add_argument(
        "--hard-init",
        action="store_true",
        help="Recreate .git and make only one empty initial commit, leaving files untracked.",
    )
    rebootstrap_parser.add_argument(
        "--branch",
        default=None,
        metavar="BRANCH",
        help="Initial branch name for the new repository. Defaults to the current branch.",
    )
    rebootstrap_parser.add_argument(
        "--message",
        default=None,
        help="Commit message for the new initial commit.",
    )
    rebootstrap_parser.add_argument(
        "--empty-first",
        action="store_true",
        help="Create an empty bootstrap commit before adding files.",
    )
    rebootstrap_parser.add_argument(
        "--empty-message",
        default=DEFAULT_REBOOTSTRAP_EMPTY_MESSAGE,
        help="Commit message for the optional empty bootstrap commit.",
    )
    add_dry_run_flag(rebootstrap_parser)
    rebootstrap_parser.set_defaults(handler=cmd_rebootstrap)

    purge_cache_parser = git_sub.add_parser(
        "purge-cache",
        help="Expire reflogs and run git garbage collection.",
        description="Expire local reflogs and run git gc to reclaim repository cache space.",
        epilog=GIT_PURGE_CACHE_EXAMPLES,
    )
    add_dry_run_flag(purge_cache_parser)
    purge_cache_parser.set_defaults(handler=cmd_purge_cache)
