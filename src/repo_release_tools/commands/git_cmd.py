"""Opinionated Git workflow helpers for rrt."""

from __future__ import annotations

import argparse
import datetime as dt
import shutil
import sys

from dataclasses import dataclass
from pathlib import Path

from repo_release_tools import git, output
from repo_release_tools.commands.branch import CONVENTIONAL_TYPES, join_description
from repo_release_tools.hooks import (
    ALLOWED_BRANCH_NAMES,
    MAGIC_BRANCH_TYPES,
    changelog_is_updated,
    commit_subject_requires_changelog,
    validate_branch_name,
    validate_commit_subject,
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
    if type_part in MAGIC_BRANCH_TYPES:
        return None
    if type_part in CONVENTIONAL_TYPES:
        return type_part
    return None


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


def classify_status_line(line: str) -> tuple[str, str]:
    """Classify a porcelain status line into a compact diff category."""
    status_code = line[:2]
    path_text = line[3:] if len(line) > 3 else line
    if status_code == "??":
        return ("untracked", path_text)
    if "U" in status_code or status_code in {"AA", "DD"}:
        return ("conflict", path_text)
    if "R" in status_code or "C" in status_code:
        return ("renamed", path_text)
    if "A" in status_code:
        return ("added", path_text)
    if "D" in status_code:
        return ("removed", path_text)
    return ("modified", path_text)


def render_status_entry(line: str) -> str:
    """Render one git status line with a typed glyph."""
    kind, path_text = classify_status_line(line)
    symbol_map = {
        "added": output.GLYPHS.diff.added,
        "removed": output.GLYPHS.diff.removed,
        "modified": output.GLYPHS.diff.modified,
        "renamed": output.GLYPHS.diff.renamed,
        "conflict": output.GLYPHS.diff.conflict,
        "untracked": output.GLYPHS.git.untracked,
    }
    return output.status(symbol_map[kind], path_text)


def summarize_status(branch_name: str, status_lines: list[str], *, upstream: str | None) -> str:
    """Render a compact one-line branch status summary."""
    modified = 0
    untracked = 0
    for line in status_lines:
        kind, _ = classify_status_line(line)
        if kind == "untracked":
            untracked += 1
        else:
            modified += 1

    ahead = 0
    behind = 0
    if upstream is not None:
        ahead, behind = git.ahead_behind(Path.cwd(), upstream)

    return output.GLYPHS.git.status_line(
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


def cmd_status(args: argparse.Namespace) -> int:
    """Show a compact repository status view."""
    root = Path.cwd()
    if not git.is_git_repository(root):
        print(f"{root} is not inside a Git work tree.", file=sys.stderr)
        return 1

    branch_name = git.current_branch(root) or "<detached>"
    upstream = git.upstream_branch(root)
    try:
        status_lines = load_status_lines(root)
    except RuntimeError as exc:
        print(output.error(str(exc)), file=sys.stderr)
        return 1
    summary = summarize_status(branch_name, status_lines, upstream=upstream)

    print()
    print(
        output.panel(
            "Git status",
            [
                ("Branch", branch_name),
                ("Upstream", upstream or "<none>"),
                ("Status", summary),
            ],
        )
    )
    print()

    if not status_lines:
        print(output.ok("Working tree is clean."))
        return 0

    print(output.section("Changes"))
    for line in status_lines:
        print(render_status_entry(line))
    return 0


def cmd_log(args: argparse.Namespace) -> int:
    """Show a compact git log view using rrt glyphs."""
    root = Path.cwd()
    if not git.is_git_repository(root):
        print(f"{root} is not inside a Git work tree.", file=sys.stderr)
        return 1

    raw = git.capture(
        ["git", "log", f"-n{args.limit}", "--pretty=format:%h%x09%s%x09%D"],
        root,
    )
    lines = [line for line in raw.splitlines() if line.strip()]

    print()
    print(output.panel("Git log", [("Count", str(len(lines))), ("Limit", str(args.limit))]))
    print()

    if not lines:
        print(output.warning("No commits found."))
        return 0

    for line in lines:
        sha, subject, *rest = line.split("\t", 2)
        refs_raw = rest[0] if rest else ""
        refs = [ref.strip() for ref in refs_raw.split(",") if ref.strip()]
        print(
            output.status(output.GLYPHS.bullet.dot, output.GLYPHS.git.log_line(sha, subject, refs))
        )
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """Run a compact repository health report for rrt workflows."""
    root = Path.cwd()
    if not git.is_git_repository(root):
        print(f"{root} is not inside a Git work tree.", file=sys.stderr)
        return 1

    branch_name = git.current_branch(root) or "<detached>"
    upstream = git.upstream_branch(root)
    try:
        status_lines = load_status_lines(root)
    except RuntimeError as exc:
        print(output.error(str(exc)), file=sys.stderr)
        return 1
    latest_subject = git.capture(["git", "log", "-1", "--pretty=%s"], root).strip()

    branch_problem = validate_branch_name(branch_name)
    subject_problem = (
        validate_commit_subject(latest_subject) if latest_subject else "No commits found."
    )
    dirty_problem = None if not status_lines else "Working tree has uncommitted changes."

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

    summary = summarize_status(branch_name, status_lines, upstream=upstream)
    print()
    print(
        output.panel(
            "Git doctor",
            [
                ("Branch", branch_name),
                ("Upstream", upstream or "<none>"),
                ("Status", summary),
                ("Commit", latest_subject or "<none>"),
            ],
        )
    )
    print()

    print(output.section("Checks"))
    failures = 0

    checks: list[tuple[bool, str]] = [
        (branch_problem is None, "Branch naming matches rrt policy."),
        (upstream is not None, "Upstream branch is configured."),
        (dirty_problem is None, "Working tree is clean."),
        (subject_problem is None, "Latest commit subject is conventional."),
        (changelog_problem is None, f"Changelog state is valid for {args.changelog_file}."),
    ]
    problems = [
        branch_problem or "",
        "No upstream branch configured." if upstream is None else "",
        dirty_problem or "",
        subject_problem or "",
        changelog_problem or "",
    ]

    for (ok, success), problem in zip(checks, problems, strict=True):
        if ok:
            print(output.ok(success))
            continue
        failures += 1
        print(output.error(problem))

    if failures == 0:
        print()
        print(output.ok("Doctor checks passed."))
        return 0

    print()
    print(output.warning(f"Doctor found {failures} issue(s)."), file=sys.stderr)
    return 1


def cmd_check_dirty_tree(args: argparse.Namespace) -> int:
    """Return non-zero when the working tree is dirty."""
    root = Path.cwd()
    if not git.is_git_repository(root):
        print(f"{root} is not inside a Git work tree.", file=sys.stderr)
        return 1
    clean = git.working_tree_clean(root)
    if clean:
        branch_name = git.current_branch(root) or "<detached>"
        upstream = git.upstream_branch(root)
        print(output.ok("Working tree is clean."))
        print(
            output.status(
                output.GLYPHS.bullet.dot, summarize_status(branch_name, [], upstream=upstream)
            )
        )
        return 0

    branch_name = git.current_branch(root) or "<detached>"
    upstream = git.upstream_branch(root)
    try:
        changed = load_status_lines(root)
    except RuntimeError as exc:
        print(output.error(str(exc)), file=sys.stderr)
        return 1
    print(output.warning("Working tree has uncommitted changes."), file=sys.stderr)
    print(
        output.status(
            output.GLYPHS.bullet.dot, summarize_status(branch_name, changed, upstream=upstream)
        ),
        file=sys.stderr,
    )
    for line in changed:
        print(render_status_entry(line), file=sys.stderr)
    return 1


def run_commit(args: argparse.Namespace, *, stage_all: bool) -> int:
    """Create a conventional commit, optionally staging all files first."""
    root = Path.cwd()
    try:
        branch_name, subject = resolve_commit_subject(args, root)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    title = "[DRY RUN] Commit" if args.dry_run else "Commit"
    print()
    print(
        output.panel(
            title,
            [
                ("Branch", branch_name),
                ("Mode", "stage all" if stage_all else "commit only"),
                ("Subject", subject),
            ],
        )
    )
    print()

    print(output.section("Git"))
    if stage_all:
        git.run(["git", "add", "."], root, dry_run=args.dry_run, label="git add")
    git.run(["git", "commit", "-m", subject], root, dry_run=args.dry_run, label="git commit")

    print()
    print(output.ok(f"Done. Created commit: {subject!r}"))
    if args.dry_run:
        print(output.dry_run_complete("no changes made"))
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
        print(output.error(f"{root} is not inside a Git work tree."), file=sys.stderr)
        return 1
    branch_name = git.current_branch(root) or "<detached>"
    upstream = git.upstream_branch(root)
    if upstream is None:
        print(
            "No upstream branch is configured for the current branch. "
            "Set one first or use git push -u.",
            file=sys.stderr,
        )
        return 1

    dirty = not git.working_tree_clean(root)
    try:
        status_lines = load_status_lines(root)
    except RuntimeError as exc:
        print(output.error(str(exc)), file=sys.stderr)
        return 1
    strategy = "merge" if args.merge else "rebase"
    title = "[DRY RUN] Sync" if args.dry_run else "Sync"
    print()
    print(
        output.panel(
            title,
            [
                ("Branch", branch_name),
                ("Upstream", upstream),
                ("Strategy", strategy),
                ("Working tree", "dirty" if dirty else "clean"),
                ("Status", summarize_status(branch_name, status_lines, upstream=upstream)),
            ],
        )
    )
    print()

    print(output.section("Syncing"))
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
            print(
                output.warning("Pull failed. The auto-stash remains on the stash stack."),
                file=sys.stderr,
            )
        raise

    if dirty:
        git.run(["git", "stash", "pop"], root, dry_run=args.dry_run, label="git stash pop")

    print()
    print(output.ok(f"Done. {branch_name} is synced from {upstream} using {strategy}."))
    if args.dry_run:
        print(output.dry_run_complete("working tree preserved"))
    return 0


def cmd_move(args: argparse.Namespace) -> int:
    """Switch branches safely by stashing and restoring local changes."""
    root = Path.cwd()
    if not git.is_git_repository(root):
        print(output.error(f"{root} is not inside a Git work tree."), file=sys.stderr)
        return 1
    current = git.current_branch(root) or "<detached>"
    dirty = not git.working_tree_clean(root)
    target_label = f"new branch {args.target}" if args.create else args.target
    title = "[DRY RUN] Move" if args.dry_run else "Move"
    print()
    print(
        output.panel(
            title,
            [
                ("From", current),
                ("To", target_label),
                ("Working tree", "dirty" if dirty else "clean"),
            ],
        )
    )
    print()

    print(output.section("Switching"))
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
            print(
                output.warning("Branch switch failed. The auto-stash remains on the stash stack."),
                file=sys.stderr,
            )
        raise

    if dirty:
        git.run(["git", "stash", "pop"], root, dry_run=args.dry_run, label="git stash pop")

    print()
    print(output.ok(f"Done. Switched to {args.target!r}."))
    if args.dry_run:
        print(output.dry_run_complete("branch switch preview only"))
    return 0


def cmd_squash_local(args: argparse.Namespace) -> int:
    """Squash local commits since a base ref into one conventional commit."""
    root = Path.cwd()
    if not args.dry_run and not git.working_tree_clean(root):
        print("Working tree has uncommitted changes. Commit or stash them first.", file=sys.stderr)
        return 1

    base_ref = args.base_ref or git.upstream_branch(root)
    if base_ref is None:
        print("No upstream branch is configured and no --base-ref was provided.", file=sys.stderr)
        return 1

    try:
        branch_name, subject = resolve_commit_subject(args, root)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    commits = git.commits_ahead(root, base_ref)
    if not commits:
        print(f"No commits found ahead of {base_ref!r}. Nothing to squash.", file=sys.stderr)
        return 1

    squash_base = git.merge_base(root, base_ref)
    if squash_base is None:
        print(f"Could not determine merge-base for {base_ref!r} and HEAD.", file=sys.stderr)
        return 1

    title = "[DRY RUN] Squash local" if args.dry_run else "Squash local"
    print()
    print(
        output.panel(
            title,
            [
                ("Branch", branch_name),
                ("Base", base_ref),
                ("Commits", str(len(commits))),
                ("Subject", subject),
            ],
        )
    )
    print()

    print(output.section("Commits to squash"))
    for line in commits:
        print(output.status(output.GLYPHS.bullet.dot, line))

    print(f"\n{output.section('Squashing')}")
    git.run(
        ["git", "reset", "--soft", squash_base],
        root,
        dry_run=args.dry_run,
        label="git reset --soft",
    )
    git.run(["git", "commit", "-m", subject], root, dry_run=args.dry_run, label="git commit")

    print()
    print(output.ok(f"Done. Squashed {len(commits)} commit(s) into {subject!r}."))
    if args.dry_run:
        print(output.dry_run_complete("commit graph preserved"))
    return 0


def cmd_undo_safe(args: argparse.Namespace) -> int:
    """Undo the last commit while keeping work in the index or working tree."""
    mode = "--soft" if args.keep_staged else "--mixed"
    title = "[DRY RUN] Undo safe" if args.dry_run else "Undo safe"
    print()
    print(
        output.panel(
            title,
            [
                ("Target", args.target),
                ("Mode", "keep staged" if args.keep_staged else "keep files"),
            ],
        )
    )
    print()

    git.run(
        ["git", "reset", mode, args.target],
        Path.cwd(),
        dry_run=args.dry_run,
        label="git reset",
    )
    print()
    print(output.ok(f"Done. Reset to {args.target!r} using {mode}."))
    if args.dry_run:
        print(output.dry_run_complete("HEAD unchanged"))
    return 0


def cmd_rebootstrap(args: argparse.Namespace) -> int:
    """Remove repository history and create a fresh initial history."""
    root = Path.cwd()
    git_dir = root / ".git"
    if not git_dir.exists():
        print(f"{root} does not look like a Git repository.", file=sys.stderr)
        return 1
    if not require_explicit_confirmation(args):
        print(
            "Refusing to destroy repository history without --yes-i-know-this-destroys-history.",
            file=sys.stderr,
        )
        return 1

    remotes = git.remote_names(root)
    if remotes and not args.allow_remote:
        print(
            "Refusing to rebootstrap a repository with configured remotes. "
            "Use --allow-remote if that is intentional.",
            file=sys.stderr,
        )
        return 1

    branch_name = args.branch or git.current_branch(root) or "main"
    backup_path = backup_path_for_git_dir(root)
    title = "[DRY RUN] Rebootstrap history" if args.dry_run else "Rebootstrap history"
    print()
    print(
        output.panel(
            title,
            [
                ("Branch", branch_name),
                ("Backup", str(backup_path)),
                ("Remote guard", "ignored" if args.allow_remote else "enabled"),
                ("Commit", args.message),
            ],
        )
    )
    print()

    print(output.section("Reinitializing"))
    if args.dry_run:
        print(output.dry_run(f"Would move {git_dir} to {backup_path}"))
        git.run(["git", "init", "-b", branch_name], root, dry_run=True, label="git init")
        if args.empty_first:
            git.run(
                ["git", "commit", "--allow-empty", "-m", args.empty_message],
                root,
                dry_run=True,
                label="git commit --allow-empty",
            )
        git.run(["git", "add", "."], root, dry_run=True, label="git add")
        git.run(["git", "commit", "-m", args.message], root, dry_run=True, label="git commit")
        print()
        print(output.dry_run_complete("history preserved via preview only"))
        return 0

    shutil.move(str(git_dir), str(backup_path))
    print(output.action(f"Moved original git data to {backup_path}"))

    try:
        git.run(["git", "init", "-b", branch_name], root, dry_run=False, label="git init")
        if args.empty_first:
            git.run(
                ["git", "commit", "--allow-empty", "-m", args.empty_message],
                root,
                dry_run=False,
                label="git commit --allow-empty",
            )
        git.run(["git", "add", "."], root, dry_run=False, label="git add")
        git.run(["git", "commit", "-m", args.message], root, dry_run=False, label="git commit")
    except RuntimeError as exc:
        print(
            output.warning(f"Rebootstrap failed. Original git data is backed up at {backup_path}."),
            file=sys.stderr,
        )
        print(str(exc), file=sys.stderr)
        return 1

    print()
    print(output.ok(f"Done. Repository history reinitialized on {branch_name!r}."))
    print(output.status(output.GLYPHS.bullet.dot, f"Original git data: {backup_path}"))
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


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the git command group."""
    parser = subparsers.add_parser("git", help="Git workflow helpers.")
    git_sub = parser.add_subparsers(dest="git_command", required=True)

    status_parser = git_sub.add_parser(
        "status",
        help="Show a compact branch and worktree status view.",
    )
    status_parser.set_defaults(handler=cmd_status)

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
        "--branch",
        default=None,
        metavar="BRANCH",
        help="Initial branch name for the new repository. Defaults to the current branch.",
    )
    rebootstrap_parser.add_argument(
        "--message",
        default=DEFAULT_REBOOTSTRAP_MESSAGE,
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
