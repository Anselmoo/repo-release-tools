"""Opinionated Git workflow helpers for rrt."""

from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from repo_release_tools import git
from repo_release_tools.commands.branch import CONVENTIONAL_TYPES, join_description
from repo_release_tools.config import load_extra_branch_types
from repo_release_tools.hooks import (
    ALLOWED_BRANCH_NAMES,
    BOT_BRANCH_TYPES,
    MAGIC_BRANCH_TYPES,
    changelog_is_updated,
    commit_subject_requires_changelog,
    validate_branch_name,
    validate_commit_subject,
)
from repo_release_tools.ui import (
    GLYPHS,
    DryRunPrinter,
    spinner_lines,
)

COMMIT_TYPES = (*CONVENTIONAL_TYPES, "deps")
DEFAULT_REBOOTSTRAP_EMPTY_MESSAGE = "chore: bootstrap repository"
DEFAULT_REBOOTSTRAP_MESSAGE = "chore: initial commit"
MOVE_STASH_MESSAGE = "rrt git move auto-stash"
SYNC_STASH_MESSAGE = "rrt git sync auto-stash"
_HUNK_HEADER_RE = re.compile(r"^@@ -(?P<old>\d+)(?:,\d+)? \+(?P<new>\d+)(?:,\d+)? @@")
STATUS_MAX = 15


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
            f"invalid commit type: {value!r} (choose one of: {allowed})"
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
            "Use --type explicitly."
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


def _print_summary(title: str, entries: list[tuple[str, str]]) -> None:
    """Print a compact colored command summary without boxed tables."""
    p = DryRunPrinter(False)
    p.header(title, **{label: value for label, value in entries})


def conflict_status_lines(status_lines: list[str]) -> list[str]:
    """Return unresolved-conflict entries from porcelain status lines."""
    return [line for line in status_lines if git.classify_status_line(line)[0] == "conflict"]


def summarize_status(branch_name: str, status_lines: list[str], *, upstream: str | None) -> str:
    """Render a compact one-line branch status summary."""
    modified = 0
    untracked = 0
    for line in status_lines:
        kind, _ = git.classify_status_line(line)
        if kind == "untracked":
            untracked += 1
        else:
            modified += 1

    ahead = 0
    behind = 0
    if upstream is not None:
        ahead, behind = git.ahead_behind(Path.cwd(), upstream)

    return GLYPHS.git.status_line(
        branch_name,
        ahead=ahead,
        behind=behind,
        modified=modified,
        untracked=untracked,
    )


def load_status_lines(root: Path) -> list[str]:
    """Load status lines or raise a user-facing runtime error."""
    try:
        return git.status_porcelain(root)
    except RuntimeError as exc:
        raise RuntimeError(str(exc)) from exc


def describe_sync_relation(*, ahead: int, behind: int, base_ref: str | None) -> str:
    """Describe how HEAD relates to the chosen sync base."""
    if base_ref is None:
        return "no upstream"
    if ahead == 0 and behind == 0:
        return "up to date"
    if ahead > 0 and behind == 0:
        return "ahead locally"
    return "behind base" if ahead == 0 and behind > 0 else "diverged"


def sync_problem(branch_name: str, *, base_ref: str | None, ahead: int, behind: int) -> str | None:
    """Return a user-facing sync problem when the branch needs attention."""
    if base_ref is None or behind == 0:
        return None
    if ahead > 0:
        return (
            f"Branch {branch_name!r} has diverged from {base_ref} "
            f"(ahead {ahead}, behind {behind}). Rebase or merge is needed."
        )
    return f"Branch {branch_name!r} is behind {base_ref} by {behind} commit(s). Sync is needed."


def cmd_status(args: argparse.Namespace) -> int:
    """Show a compact repository status view."""
    root = Path.cwd()
    if not git.is_git_repository(root):
        p = DryRunPrinter(False)
        p.line(f"{root} is not inside a Git work tree.", ok=False, stream=sys.stderr)
        return 1

    branch_name = git.current_branch(root) or "<detached>"
    upstream = git.upstream_branch(root)
    try:
        status_lines = load_status_lines(root)
    except RuntimeError as exc:
        p = DryRunPrinter(False)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1
    summary = summarize_status(branch_name, status_lines, upstream=upstream)

    _print_summary(
        "Git status",
        [
            ("Branch", branch_name),
            ("Upstream", upstream or "<none>"),
            ("Status", summary),
        ],
    )

    if not status_lines:
        p = DryRunPrinter(False)
        p.ok("Working tree is clean.")
        return 0

    p = DryRunPrinter(False)
    p.section("Changes")
    shown = status_lines[:STATUS_MAX]
    for line in shown:
        p.file_entry(*git.classify_status_line(line))
    if len(status_lines) > STATUS_MAX:
        p.action(f"…and {len(status_lines) - STATUS_MAX} more")
    return 0


def cmd_log(args: argparse.Namespace) -> int:
    """Show a compact git log view using rrt glyphs."""
    root = Path.cwd()
    if not git.is_git_repository(root):
        p = DryRunPrinter(False)
        p.line(f"{root} is not inside a Git work tree.", ok=False, stream=sys.stderr)
        return 1

    raw = git.capture(
        ["git", "log", f"-n{args.limit}", "--pretty=format:%h%x09%s%x09%D"],
        root,
    )
    lines = [line for line in raw.splitlines() if line.strip()]

    _print_summary(
        "Git log",
        [("Count", str(len(lines))), ("Limit", str(args.limit))],
    )

    if not lines:
        p = DryRunPrinter(False)
        p.warn("No commits found.")
        return 0

    p = DryRunPrinter(False)
    p.section("Commits")
    for line in lines:
        sha, subject, *rest = line.split("\t", 2)
        refs_raw = rest[0] if rest else ""
        refs = [ref.strip() for ref in refs_raw.split(",") if ref.strip()]
        p.list_item(GLYPHS.git.log_line(sha, subject, refs))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """Run a compact repository health report for rrt workflows."""
    root = Path.cwd()
    if not git.is_git_repository(root):
        p = DryRunPrinter(False)
        p.line(f"{root} is not inside a Git work tree.", ok=False, stream=sys.stderr)
        return 1

    branch_name = git.current_branch(root) or "<detached>"
    upstream = git.upstream_branch(root)
    try:
        status_lines = load_status_lines(root)
    except RuntimeError as exc:
        p = DryRunPrinter(False)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1
    conflicts = conflict_status_lines(status_lines)
    operation = git.in_progress_operation(root)
    ahead, behind = (0, 0) if upstream is None else git.ahead_behind(root, upstream)
    latest_subject = git.capture(["git", "log", "-1", "--pretty=%s"], root).strip()

    branch_problem = validate_branch_name(branch_name, extra_types=load_extra_branch_types(root))
    subject_problem = (
        validate_commit_subject(latest_subject) if latest_subject else "No commits found."
    )
    dirty_problem = "Working tree has uncommitted changes." if status_lines else None
    operation_problem = (
        None
        if operation is None
        else f"{operation.capitalize()} is in progress. Resolve or abort it first."
    )
    conflict_problem = (
        f"Found {len(conflicts)} conflicted path(s). Resolve them first." if conflicts else None
    )
    relation_problem = sync_problem(branch_name, base_ref=upstream, ahead=ahead, behind=behind)

    changelog_problem: str | None = None
    if latest_subject and commit_subject_requires_changelog(latest_subject):
        changed_files = git.capture(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "--root", "-r", "HEAD"],
            root,
        )
        changed = [line for line in changed_files.splitlines() if line.strip()]
        if not changelog_is_updated(changed, changelog_file=args.changelog_file, cwd=root):
            changelog_problem = (
                f"Branch {branch_name!r} suggests changelog work, but {args.changelog_file} "
                "is not part of HEAD."
            )

    p = DryRunPrinter(False)
    summary = summarize_status(branch_name, status_lines, upstream=upstream)
    _print_summary(
        "Git doctor",
        [
            ("Branch", branch_name),
            ("Upstream", upstream or "<none>"),
            ("Sync", describe_sync_relation(ahead=ahead, behind=behind, base_ref=upstream)),
            ("Status", summary),
            ("Commit", latest_subject or "<none>"),
        ],
    )

    p.section("Checks")
    failures = 0

    checks: list[tuple[bool, str, str]] = [
        (branch_problem is None, "Branch naming matches rrt policy.", branch_problem or ""),
        (
            upstream is not None,
            "Upstream branch is configured.",
            "No upstream branch configured." if upstream is None else "",
        ),
        (dirty_problem is None, "Working tree is clean.", dirty_problem or ""),
        (
            operation_problem is None,
            "No merge or rebase is in progress.",
            operation_problem or "",
        ),
        (
            conflict_problem is None,
            "No unresolved conflicts detected.",
            conflict_problem or "",
        ),
        (
            subject_problem is None,
            "Latest commit subject is conventional.",
            subject_problem or "",
        ),
        (
            changelog_problem is None,
            f"Changelog state is valid for {args.changelog_file}.",
            changelog_problem or "",
        ),
    ]
    if upstream is not None:
        checks.append(
            (
                relation_problem is None,
                f"{branch_name} does not need sync from {upstream}.",
                relation_problem or "",
            )
        )

    for ok, ok_msg, problem in checks:
        if ok:
            p.ok(ok_msg)
            continue
        failures += 1
        p.warn(problem)

    if conflicts:
        p.section("Conflicts")
        shown = conflicts[:STATUS_MAX]
        for line in shown:
            p.file_entry(*git.classify_status_line(line))
        if len(conflicts) > STATUS_MAX:
            p.action(f"…and {len(conflicts) - STATUS_MAX} more")

    if failures == 0:
        p.footer("Doctor checks passed.")
        return 0

    p.warn(f"Doctor found {failures} issue(s).")
    return 1


def cmd_check_dirty_tree(args: argparse.Namespace) -> int:
    """Return non-zero when the working tree is dirty."""
    root = Path.cwd()
    if not git.is_git_repository(root):
        p = DryRunPrinter(False)
        p.line(f"{root} is not inside a Git work tree.", ok=False, stream=sys.stderr)
        return 1
    p = DryRunPrinter(False)
    if git.working_tree_clean(root):
        branch_name = git.current_branch(root) or "<detached>"
        upstream = git.upstream_branch(root)
        p.ok("Working tree is clean.")
        p.meta("Status", summarize_status(branch_name, [], upstream=upstream))
        return 0

    branch_name = git.current_branch(root) or "<detached>"
    upstream = git.upstream_branch(root)
    try:
        changed = load_status_lines(root)
    except RuntimeError as exc:
        p = DryRunPrinter(False)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1
    p.warn("Working tree has uncommitted changes.", stream=sys.stderr)
    p.meta("Status", summarize_status(branch_name, changed, upstream=upstream), stream=sys.stderr)
    shown = changed[:STATUS_MAX]
    for line in shown:
        p.file_entry(*git.classify_status_line(line), stream=sys.stderr)
    if len(changed) > STATUS_MAX:
        p.action(f"…and {len(changed) - STATUS_MAX} more", stream=sys.stderr)
    return 1


def cmd_sync_status(args: argparse.Namespace) -> int:
    """Analyze merge/rebase blockers and divergence against a sync base."""
    root = Path.cwd()
    if not git.is_git_repository(root):
        p = DryRunPrinter(False)
        p.line(f"{root} is not inside a Git work tree.", ok=False, stream=sys.stderr)
        return 1

    branch_name = git.current_branch(root) or "<detached>"
    base_ref = args.base_ref or git.upstream_branch(root)
    if base_ref is not None and not git.ref_exists(root, base_ref):
        p = DryRunPrinter(False)
        p.line(f"Base ref {base_ref!r} does not exist.", ok=False, stream=sys.stderr)
        return 1
    operation = git.in_progress_operation(root)
    try:
        status_lines = load_status_lines(root)
    except RuntimeError as exc:
        p = DryRunPrinter(False)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1

    conflicts = conflict_status_lines(status_lines)
    ahead, behind = (0, 0) if base_ref is None else git.ahead_behind(root, base_ref)
    relation = describe_sync_relation(ahead=ahead, behind=behind, base_ref=base_ref)

    _print_summary(
        "Sync status",
        [
            ("Branch", branch_name),
            ("Base", base_ref or "<none>"),
            ("Relation", relation),
            ("Operation", operation or "idle"),
            ("Status", summarize_status(branch_name, status_lines, upstream=base_ref)),
        ],
    )

    p = DryRunPrinter(False)
    p.section("Analysis")
    failures = 0

    if operation is None:
        p.ok("No merge or rebase is in progress.")
    else:
        failures += 1
        p.warn(f"{operation.capitalize()} is in progress. Resolve or abort it first.")

    if not conflicts:
        p.ok("No unresolved conflicts detected.")
    else:
        failures += 1
        p.warn(f"Found {len(conflicts)} conflicted path(s).")

    if base_ref is None:
        failures += 1
        p.warn("No upstream branch is configured. Use --base-ref to analyze sync drift.")
    elif ahead == 0 and behind == 0:
        p.ok(f"{branch_name} matches {base_ref}.")
    elif ahead > 0 and behind == 0:
        p.ok(f"{branch_name} is ahead of {base_ref} by {ahead} commit(s).")
    else:
        failures += 1
        problem = sync_problem(branch_name, base_ref=base_ref, ahead=ahead, behind=behind)
        if problem is not None:
            p.warn(problem)

    if conflicts:
        p.blank_line()
        p.section("Conflicts")
        shown = conflicts[:STATUS_MAX]
        for line in shown:
            p.file_entry(*git.classify_status_line(line))
        if len(conflicts) > STATUS_MAX:
            p.action(f"…and {len(conflicts) - STATUS_MAX} more")

    if failures == 0:
        p.blank_line()
        p.ok("Sync analysis passed.")
        return 0

    p.blank_line()
    p.warn(f"Sync analysis found {failures} issue(s).")
    return 1


def run_commit(args: argparse.Namespace, *, stage_all: bool) -> int:
    """Create a conventional commit, optionally staging all files first."""
    root = Path.cwd()
    try:
        branch_name, subject = resolve_commit_subject(args, root)
    except ValueError as exc:
        p = DryRunPrinter(False)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1

    title = "[DRY RUN] Commit" if args.dry_run else "Commit"
    _print_summary(
        title,
        [
            ("Branch", branch_name),
            ("Mode", "stage all" if stage_all else "commit only"),
            ("Subject", subject),
        ],
    )

    p = DryRunPrinter(args.dry_run)
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
    root = Path.cwd()
    if not git.is_git_repository(root):
        p = DryRunPrinter(False)
        p.line(f"{root} is not inside a Git work tree.", ok=False, stream=sys.stderr)
        return 1
    branch_name = git.current_branch(root) or "<detached>"
    upstream = git.upstream_branch(root)
    if upstream is None:
        p = DryRunPrinter(False)
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
        p = DryRunPrinter(False)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1
    conflicts = conflict_status_lines(status_lines)
    operation = git.in_progress_operation(root)
    if operation is not None:
        p = DryRunPrinter(False)
        p.line(
            f"Cannot sync while a {operation} is in progress. Resolve or abort it first.",
            ok=False,
            stream=sys.stderr,
        )
        return 1
    if conflicts:
        p = DryRunPrinter(False)
        p.line("Cannot sync with unresolved merge conflicts.", ok=False, stream=sys.stderr)
        shown = conflicts[:STATUS_MAX]
        for line in shown:
            p.file_entry(*git.classify_status_line(line), stream=sys.stderr)
        if len(conflicts) > STATUS_MAX:
            p.action(f"…and {len(conflicts) - STATUS_MAX} more", stream=sys.stderr)
        return 1
    strategy = "merge" if args.merge else "rebase"
    title = "[DRY RUN] Sync" if args.dry_run else "Sync"
    _print_summary(
        title,
        [
            ("Branch", branch_name),
            ("Upstream", upstream),
            ("Strategy", strategy),
            ("Working tree", "dirty" if dirty else "clean"),
            ("Status", summarize_status(branch_name, status_lines, upstream=upstream)),
        ],
    )

    p = DryRunPrinter(args.dry_run)
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
    root = Path.cwd()
    if not git.is_git_repository(root):
        p = DryRunPrinter(False)
        p.line(f"{root} is not inside a Git work tree.", ok=False, stream=sys.stderr)
        return 1
    current = git.current_branch(root) or "<detached>"
    dirty = not git.working_tree_clean(root)
    target_label = f"new branch {args.target}" if args.create else args.target
    title = "[DRY RUN] Move" if args.dry_run else "Move"
    _print_summary(
        title,
        [
            ("From", current),
            ("To", target_label),
            ("Working tree", "dirty" if dirty else "clean"),
        ],
    )

    p = DryRunPrinter(args.dry_run)
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
    root = Path.cwd()
    if not args.dry_run and not git.working_tree_clean(root):
        p = DryRunPrinter(False)
        p.line(
            "Working tree has uncommitted changes. Commit or stash them first.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    base_ref = args.base_ref or git.upstream_branch(root)
    if base_ref is None:
        p = DryRunPrinter(False)
        p.line(
            "No upstream branch is configured and no --base-ref was provided.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    try:
        branch_name, subject = resolve_commit_subject(args, root)
    except ValueError as exc:
        p = DryRunPrinter(False)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1

    commits = git.commits_ahead(root, base_ref)
    if not commits:
        p = DryRunPrinter(False)
        p.line(
            f"No commits found ahead of {base_ref!r}. Nothing to squash.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    squash_base = git.merge_base(root, base_ref)
    if squash_base is None:
        p = DryRunPrinter(False)
        p.line(
            f"Could not determine merge-base for {base_ref!r} and HEAD.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    title = "[DRY RUN] Squash local" if args.dry_run else "Squash local"
    _print_summary(
        title,
        [
            ("Branch", branch_name),
            ("Base", base_ref),
            ("Commits", str(len(commits))),
            ("Subject", subject),
        ],
    )

    p = DryRunPrinter(args.dry_run)
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
    mode = "--soft" if args.keep_staged else "--mixed"
    title = "[DRY RUN] Undo safe" if args.dry_run else "Undo safe"
    _print_summary(
        title,
        [
            ("Target", args.target),
            ("Mode", "keep staged" if args.keep_staged else "keep files"),
        ],
    )

    git.run(
        ["git", "reset", mode, args.target],
        Path.cwd(),
        dry_run=args.dry_run,
        label="git reset",
    )
    p = DryRunPrinter(args.dry_run)
    p.blank_line()
    p.footer(f"Done. Reset to {args.target!r} using {mode}.")
    return 0


def cmd_rebootstrap(args: argparse.Namespace) -> int:
    """Remove repository history and create a fresh initial history."""
    root = Path.cwd()
    git_dir = git.git_dir(root) or (root / ".git")
    if not git_dir.exists():
        p = DryRunPrinter(False)
        p.line(f"{root} does not look like a Git repository.", ok=False, stream=sys.stderr)
        return 1
    if not require_explicit_confirmation(args):
        p = DryRunPrinter(False)
        p.line(
            "Refusing to destroy repository history without --yes-i-know-this-destroys-history.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    if args.hard_init and args.empty_first:
        p = DryRunPrinter(False)
        p.line("Use either --hard-init or --empty-first, not both.", ok=False, stream=sys.stderr)
        return 1

    remotes = git.remote_names(root)
    if remotes and not args.allow_remote:
        p = DryRunPrinter(False)
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
    title = "[DRY RUN] Rebootstrap history" if args.dry_run else "Rebootstrap history"
    _print_summary(
        title,
        [
            ("Branch", branch_name),
            ("Mode", "empty hard-init" if args.hard_init else "snapshot current files"),
            ("Backup", str(backup_path)),
            ("Remote guard", "ignored" if args.allow_remote else "enabled"),
            ("Commit", commit_message),
        ],
    )

    p = DryRunPrinter(args.dry_run)
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
                ["git", "commit", "-m", commit_message], root, dry_run=False, label="git commit"
            )
    except RuntimeError as exc:
        p = DryRunPrinter(False)
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


def _parse_diff_line(raw: str) -> tuple[str, str, int | None]:
    """Parse a unified diff header or context line into (kind, text, lineno)."""
    if raw.startswith("+++") or raw.startswith("---"):
        return ("unchanged", raw, None)
    if raw.startswith("@@"):
        # Extract new-file line number from @@ -a,b +c,d @@ ...
        try:
            after_plus = raw.split("+")[1].split(",")[0].split(" ")[0]
            lineno = int(after_plus)
        except (IndexError, ValueError):
            lineno = None
        return ("unchanged", raw, lineno)
    if raw.startswith("+"):
        return ("added", raw[1:], None)
    if raw.startswith("-"):
        return ("removed", raw[1:], None)
    return ("unchanged", raw[1:] if raw.startswith(" ") else raw, None)


def _parse_diff_hunk_header(raw: str) -> tuple[int, int] | None:
    """Return old/new line starts from a unified diff hunk header."""
    match = _HUNK_HEADER_RE.match(raw)
    if match is None:
        return None
    return (int(match.group("old")), int(match.group("new")))


def cmd_diff(args: argparse.Namespace) -> int:
    """Show a compact git diff using DiffGlyphs."""
    root = Path.cwd()
    if not git.is_git_repository(root):
        p = DryRunPrinter(False)
        p.line(f"{root} is not inside a Git work tree.", ok=False, stream=sys.stderr)
        return 1

    cmd = ["git", "diff", "--unified=3"]
    if args.staged:
        cmd.append("--staged")
    if args.against:
        cmd.append(args.against)

    try:
        raw = git.capture_checked(cmd, root)
    except RuntimeError as exc:
        p = DryRunPrinter(False)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1
    if not raw.strip():
        p = DryRunPrinter(False)
        p.ok("No diff to show.")
        return 0

    current_file: str = ""
    old_lineno: int | None = None
    new_lineno: int | None = None

    p = DryRunPrinter(False)
    p.blank_line()
    for raw_line in raw.splitlines():
        if raw_line.startswith("diff --git "):
            parts = raw_line.split()
            if len(parts) >= 4:
                old_path = parts[2]
                new_path = parts[3]
                if new_path.startswith("b/"):
                    current_file = new_path[2:]
                elif old_path.startswith("a/"):
                    current_file = old_path[2:]
            continue
        if raw_line.startswith("+++ b/"):
            current_file = raw_line[6:]
            p = DryRunPrinter(False)
            p.blank_line()
            p.section(current_file)
            old_lineno = None
            new_lineno = None
            continue
        if raw_line.startswith("+++ /dev/null"):
            if current_file:
                p = DryRunPrinter(False)
                p.blank_line()
                p.section(current_file)
            old_lineno = None
            new_lineno = None
            continue
        if (
            raw_line.startswith("--- ")
            or raw_line.startswith("index ")
            or raw_line.startswith("new file")
            or raw_line.startswith("deleted file")
        ):
            continue

        hunk_lines = _parse_diff_hunk_header(raw_line)
        if hunk_lines is not None:
            old_lineno, new_lineno = hunk_lines
            p = DryRunPrinter(False)
            p.action(f"  {GLYPHS.typography.mdash} {raw_line.strip()}")
            continue

        kind, text, hunk_start = _parse_diff_line(raw_line)
        if hunk_start is not None:
            p = DryRunPrinter(False)
            p.action(f"  {GLYPHS.typography.mdash} {text.strip()}")
            continue

        rendered_lineno: int | None = None
        if kind == "added":
            rendered_lineno = new_lineno
            if new_lineno is not None:
                new_lineno += 1
        elif kind == "removed":
            if old_lineno is not None:
                old_lineno += 1
        elif raw_line.startswith(" "):
            if old_lineno is not None:
                old_lineno += 1
            if new_lineno is not None:
                new_lineno += 1

        rendered = GLYPHS.diff.line(
            kind, text.rstrip(), lineno=rendered_lineno if kind != "unchanged" else None
        )
        p = DryRunPrinter(False)
        p.line(f"  {rendered}")

    p.blank_line()
    return 0


def add_dry_run_flag(parser: argparse.ArgumentParser) -> None:
    """Register a shared dry-run flag."""
    parser.add_argument("--dry-run", action="store_true", help="Preview without changing git.")


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
    '  $ rrt git commit fix "make output clearer"\n'
    "  $ rrt git sync\n"
    "  $ rrt git undo-safe"
)


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

    status_parser = git_sub.add_parser(
        "status",
        help="Show a compact branch and worktree status view.",
    )
    status_parser.set_defaults(handler=cmd_status)

    diff_parser = git_sub.add_parser(
        "diff",
        help="Show a compact diff using rrt glyph formatting.",
    )
    diff_parser.add_argument(
        "--staged",
        action="store_true",
        help="Show staged changes instead of working-tree changes.",
    )
    diff_parser.add_argument(
        "--against",
        metavar="REF",
        default=None,
        help="Diff against a specific commit or ref.",
    )
    diff_parser.set_defaults(handler=cmd_diff)

    log_parser = git_sub.add_parser(
        "log",
        help="Show a compact commit history view.",
    )
    log_parser.add_argument(
        "-n",
        "--limit",
        default=10,
        type=int,
        help="Number of commits to show.",
    )
    log_parser.set_defaults(handler=cmd_log)

    doctor_parser = git_sub.add_parser(
        "doctor",
        help="Run a compact repository health report for rrt workflows.",
    )
    doctor_parser.add_argument(
        "--changelog-file",
        default="CHANGELOG.md",
        help="Changelog path used for doctor checks.",
    )
    doctor_parser.set_defaults(handler=cmd_doctor)

    sync_status_parser = git_sub.add_parser(
        "sync-status",
        help="Analyze unresolved conflicts and whether sync/rebase work is needed.",
    )
    sync_status_parser.add_argument(
        "--base-ref",
        default=None,
        metavar="REF",
        help="Ref to analyze against. Defaults to the current upstream branch.",
    )
    sync_status_parser.set_defaults(handler=cmd_sync_status)

    dirty_parser = git_sub.add_parser(
        "check-dirty-tree",
        help="Exit non-zero when the working tree is dirty. Useful in hooks and CI.",
    )
    dirty_parser.set_defaults(handler=cmd_check_dirty_tree)

    commit_parser = git_sub.add_parser(
        "commit",
        help="Create a conventional commit, inferring type from the current branch.",
    )
    add_commit_arguments(commit_parser)
    commit_parser.set_defaults(handler=cmd_commit)

    commit_all_parser = git_sub.add_parser(
        "commit-all",
        help="Stage all files and create a conventional commit from the branch context.",
    )
    add_commit_arguments(commit_all_parser)
    commit_all_parser.set_defaults(handler=cmd_commit_all)

    sync_parser = git_sub.add_parser(
        "sync",
        help="Fetch, stash if needed, and pull the current branch safely.",
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
