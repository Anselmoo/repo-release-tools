"""Branch maintenance and synchronization commands for `rrt git`.

- `sync` fetches, auto-stashes dirty changes when needed, and pulls from the
  upstream branch.
- `move` switches branches safely and can create the target branch first.
- `undo-safe` resets to another ref while keeping changes staged or in the
  working tree.
- `rebootstrap` backs up `.git`, reinitializes the repository, and creates a
  fresh history snapshot or empty bootstrap commit.
- `purge-cache` expires reflogs and runs `git gc` to reclaim local cache space.
- `publish-snapshot` force-pushes a single-commit snapshot of tracked content to a
  secondary remote. It refuses to run when `--remote` resolves to the same URL as
  `origin`, and requires `--yes-i-know-this-overwrites-remote-history` to do
  anything beyond a preview. Force-pushing does not immediately purge the old
  objects on the remote host — they can remain fetchable by direct SHA until the
  host runs garbage collection. If secrets were ever committed, run
  `git filter-repo` or the BFG Repo-Cleaner first; this command only controls
  what is visible going forward. Clones or forks made before the force-push
  retain the old history locally, which is outside this tool's control.
"""

from __future__ import annotations

import argparse
import datetime as dt
import shutil
import sys
from fnmatch import fnmatch
from pathlib import Path

from repo_release_tools.commands._git_shared import (
    STATUS_MAX,
    add_dry_run_flag,
    conflict_status_lines,
    load_status_lines,
    summarize_status,
)
from repo_release_tools.config import load_or_autodetect_config, load_primary_remote
from repo_release_tools.ui import (
    DryRunPrinter,
    VerbosePrinter,
    spinner_lines,
)
from repo_release_tools.workflow import git

DEFAULT_REBOOTSTRAP_EMPTY_MESSAGE = "chore: bootstrap repository"
DEFAULT_REBOOTSTRAP_MESSAGE = "chore: initial commit"
MOVE_STASH_MESSAGE = "rrt git move auto-stash"
SYNC_STASH_MESSAGE = "rrt git sync auto-stash"


def resolve_excluded_paths(tracked_files: list[str], patterns: tuple[str, ...]) -> list[str]:
    """Return tracked_files entries matching any exclude glob (fnmatch, repo-relative POSIX)."""
    if not patterns:
        return []
    return [f for f in tracked_files if any(fnmatch(f, pat) for pat in patterns)]


def backup_path_for_git_dir(root: Path) -> Path:
    """Return an external backup path for the current .git directory."""
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d%H%M%S")
    return root.parent / f".{root.name}.git-backup-{stamp}"


def require_explicit_confirmation(args: argparse.Namespace) -> bool:
    """Return whether the destructive rebootstrap command is confirmed."""
    return bool(args.yes_i_know_this_destroys_history)


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


def cmd_publish_snapshot(args: argparse.Namespace) -> int:
    """Force-push a single-commit snapshot of tracked content to a secondary remote."""
    verbose: int = getattr(args, "verbose", 0) or 0
    root = Path.cwd()
    if not git.is_git_repository(root):
        p = VerbosePrinter(verbose=verbose)
        p.line(f"{root} is not inside a Git work tree.", ok=False, stream=sys.stderr)
        return 1

    remote = args.remote
    branch = args.branch
    message = args.message
    exclude_patterns = tuple(getattr(args, "exclude", None) or ())
    if getattr(args, "target", None):
        config = load_or_autodetect_config(root)
        target = config.publish_targets.get(args.target)
        if target is None:
            p = VerbosePrinter(verbose=verbose)
            p.line(
                f"No publish target named {args.target!r} in [tool.rrt.publish_targets].",
                ok=False,
                stream=sys.stderr,
            )
            return 1
        remote = remote or target.remote
        branch = branch or target.branch
        message = message or target.message
        exclude_patterns = tuple(target.exclude) + exclude_patterns
    branch = branch or "main"
    message = message or "Initial commit"

    if not remote:
        p = VerbosePrinter(verbose=verbose)
        p.line("No --remote given and no config target resolved one.", ok=False, stream=sys.stderr)
        return 1

    primary_remote = load_primary_remote(root)
    conflict = git.primary_remote_conflict(root, remote, primary_remote)
    if conflict is not None:
        p = VerbosePrinter(verbose=verbose)
        p.line(f"Refusing to publish: {conflict}", ok=False, stream=sys.stderr)
        return 1

    operation = git.in_progress_operation(root)
    if operation is not None:
        p = VerbosePrinter(verbose=verbose)
        p.line(
            f"Cannot publish while a {operation} is in progress. Resolve or abort it first.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    confirmed = bool(args.yes_i_know_this_overwrites_remote_history)
    dry_run = args.dry_run or not confirmed
    original_branch = git.current_branch(root) or "main"
    tmp_branch = git.unique_snapshot_branch_name(root)

    p = DryRunPrinter(dry_run, verbose=verbose)
    p.blank_line()
    p.header("Publish snapshot", Remote=remote, Branch=branch, Message=message)
    if not confirmed:
        p.warn(
            "Refusing to push without --yes-i-know-this-overwrites-remote-history. Showing a preview instead.",
        )
    p.section("Git")
    try:
        git.run(
            ["git", "checkout", "--orphan", tmp_branch],
            root,
            dry_run=dry_run,
            label="git checkout --orphan",
        )
        if exclude_patterns:
            tracked = git.capture(["git", "ls-files"], root).splitlines()
            to_remove = resolve_excluded_paths(tracked, exclude_patterns)
            if to_remove:
                git.run(
                    ["git", "rm", "-r", "--ignore-unmatch", "--", *to_remove],
                    root,
                    dry_run=dry_run,
                    label="git rm",
                )
        git.run(["git", "add", "-u"], root, dry_run=dry_run, label="git add -u")
        git.run(["git", "commit", "-m", message], root, dry_run=dry_run, label="git commit")
        git.run(
            ["git", "push", "--force", "--", remote, f"{tmp_branch}:{branch}"],
            root,
            dry_run=dry_run,
            label="git push --force",
        )
    finally:
        try:
            git.run(
                ["git", "checkout", original_branch], root, dry_run=dry_run, label="git checkout"
            )
        except RuntimeError as exc:
            p.warn(f"Cleanup: failed to restore branch {original_branch!r}: {exc}")
        try:
            git.run(
                ["git", "branch", "-D", tmp_branch], root, dry_run=dry_run, label="git branch -D"
            )
        except RuntimeError as exc:
            p.warn(f"Cleanup: failed to delete temp branch {tmp_branch!r}: {exc}")

    p.blank_line()
    if dry_run:
        p.footer(f"Done. Preview complete — nothing was pushed to {remote}:{branch}.")
    else:
        p.footer(f"Done. Pushed a single-commit snapshot to {remote}:{branch}.")
    return 0


GIT_SYNC_EXAMPLES = "  $ rrt git sync\n  $ rrt git sync --merge\n  $ rrt git sync --dry-run"

GIT_MOVE_EXAMPLES = "  $ rrt git move release/v1.2.0\n  $ rrt git move -b feat/help-copy --dry-run"

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

GIT_PUBLISH_SNAPSHOT_EXAMPLES = (
    "  $ rrt git publish-snapshot --remote mirror --dry-run\n"
    "  $ rrt git publish-snapshot demo --yes-i-know-this-overwrites-remote-history\n"
    '  $ rrt git publish-snapshot --remote mirror --branch main --message "Initial commit" '
    "--yes-i-know-this-overwrites-remote-history\n"
    "  $ rrt git publish-snapshot --remote mirror --exclude 'docs/internal/*' --dry-run"
)


def register_sync(git_sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the branch maintenance and synchronization subcommands."""
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

    publish_snapshot_parser = git_sub.add_parser(
        "publish-snapshot",
        help="Force-push a single-commit snapshot of tracked content to a secondary remote.",
        description=(
            "Create an orphan branch from tracked content, commit it once, and force-push "
            "it to a secondary remote. Refuses to run if --remote resolves to the same URL "
            "as the configured primary remote (tool.rrt.primary_remote, default: origin), "
            "and requires --yes-i-know-this-overwrites-remote-history to do "
            "anything beyond a preview. Safety notes: force-pushing does not immediately "
            "purge old objects on the remote host — they can remain fetchable by direct SHA "
            "until the host runs garbage collection. If secrets were ever committed, run "
            "git filter-repo or the BFG Repo-Cleaner first; this command only controls what "
            "is visible going forward. Clones or forks made before the force-push retain the "
            "old history locally, which is outside this tool's control."
        ),
        epilog=GIT_PUBLISH_SNAPSHOT_EXAMPLES,
    )
    publish_snapshot_parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help="Named [tool.rrt.publish_targets.<name>] entry to resolve remote/branch/message from.",
    )
    publish_snapshot_parser.add_argument(
        "--remote", default=None, help="Remote name or URL to force-push to."
    )
    publish_snapshot_parser.add_argument(
        "--branch", default=None, help="Remote branch to force-push to. Defaults to main."
    )
    publish_snapshot_parser.add_argument(
        "--message", default=None, help="Commit message for the snapshot commit."
    )
    publish_snapshot_parser.add_argument(
        "--exclude",
        action="append",
        default=None,
        metavar="PATTERN",
        help="Glob (fnmatch, repo-relative) to exclude from the snapshot. Repeatable; extends "
        "the resolved target's [tool.rrt.publish_targets.<name>].exclude list.",
    )
    publish_snapshot_parser.add_argument(
        "--yes-i-know-this-overwrites-remote-history",
        action="store_true",
        help="Required confirmation to actually force-push. Without it, behaves as --dry-run.",
    )
    add_dry_run_flag(publish_snapshot_parser)
    publish_snapshot_parser.set_defaults(handler=cmd_publish_snapshot)
