"""Inspection commands for `rrt git`.

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
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from repo_release_tools.commands._git_shared import (
    STATUS_MAX,
    conflict_status_lines,
    load_status_lines,
    summarize_status,
)
from repo_release_tools.config import load_extra_branch_types
from repo_release_tools.ui import GLYPHS, VerbosePrinter
from repo_release_tools.workflow import git
from repo_release_tools.workflow.hooks import (
    changelog_is_updated,
    commit_subject_requires_changelog,
    validate_branch_name,
    validate_commit_subject,
)

_HUNK_HEADER_RE = re.compile(r"^@@ -(?P<old>\d+)(?:,\d+)? \+(?P<new>\d+)(?:,\d+)? @@")

GIT_STATUS_EXAMPLES = "  $ rrt git status"

GIT_DIFF_EXAMPLES = "  $ rrt git diff\n  $ rrt git diff --staged\n  $ rrt git diff --against HEAD~1"

GIT_LOG_EXAMPLES = "  $ rrt git log\n  $ rrt git log --limit 20"

GIT_DOCTOR_EXAMPLES = "  $ rrt git doctor\n  $ rrt git doctor --changelog-file docs/CHANGELOG.md"

GIT_SYNC_STATUS_EXAMPLES = "  $ rrt git sync-status\n  $ rrt git sync-status --base-ref origin/main"

GIT_CHECK_DIRTY_TREE_EXAMPLES = "  $ rrt git check-dirty-tree"


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


@dataclass(frozen=True)
class StatusOptions:
    """Typed view of ``argparse.Namespace`` for ``rrt git status``.

    Built once via :meth:`from_args` at the top of :func:`cmd_status` so the
    single flag it reads has a typed read site instead of a bare
    ``getattr(args, ..., default)`` call.
    """

    verbose: int

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> StatusOptions:
        """Build a :class:`StatusOptions` from a parsed ``argparse.Namespace``.

        ``verbose`` is set globally by cli.py's parser, so a Namespace produced
        by argparse always carries it. The getattr fallback exists only because
        several tests in tests/commands/test_git_inspect.py call cmd_status with
        a bare ``argparse.Namespace()`` that never sets ``verbose``.
        """
        return cls(verbose=getattr(args, "verbose", 0) or 0)


def cmd_status(args: argparse.Namespace) -> int:
    """Show a compact repository status view."""
    opts = StatusOptions.from_args(args)
    verbose = opts.verbose
    root = Path.cwd()
    if not git.is_git_repository(root):
        p = VerbosePrinter(verbose=verbose)
        p.line(f"{root} is not inside a Git work tree.", ok=False, stream=sys.stderr)
        return 1

    branch_name = git.current_branch(root) or "<detached>"
    upstream = git.upstream_branch(root)
    try:
        status_lines = load_status_lines(root)
    except RuntimeError as exc:
        p = VerbosePrinter(verbose=verbose)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1
    summary = summarize_status(branch_name, status_lines, upstream=upstream, root=root)

    p = VerbosePrinter(verbose=verbose)
    p.blank_line()
    p.header(
        "Git status",
        Branch=branch_name,
        Upstream=upstream or "<none>",
        Status=summary,
    )

    if not status_lines:
        p.ok("Working tree is clean.")
        return 0

    p.section("Changes")
    shown = status_lines[:STATUS_MAX]
    for line in shown:
        p.file_entry(*git.classify_status_line(line))
    if len(status_lines) > STATUS_MAX:
        p.action(f"…and {len(status_lines) - STATUS_MAX} more")
    return 0


@dataclass(frozen=True)
class LogOptions:
    """Typed view of ``argparse.Namespace`` for ``rrt git log``.

    Built once via :meth:`from_args` at the top of :func:`cmd_log` so both
    flags it reads have typed read sites instead of ``getattr(args, ...,
    default)`` / ``args.x`` calls throughout the function body.
    """

    verbose: int
    limit: int

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> LogOptions:
        """Build a :class:`LogOptions` from a parsed ``argparse.Namespace``.

        ``limit`` is given a real default (10) by git_inspect.py's own
        register_inspect(), so a Namespace produced by argparse always
        carries it and is read directly. ``verbose`` is set globally by
        cli.py's parser, but tests/commands/test_git_inspect.py calls
        cmd_log with ``argparse.Namespace(limit=...)`` that never sets
        ``verbose``, so the getattr fallback here absorbs that gap.
        """
        return cls(verbose=getattr(args, "verbose", 0) or 0, limit=args.limit)


def cmd_log(args: argparse.Namespace) -> int:
    """Show a compact git log view using rrt glyphs."""
    opts = LogOptions.from_args(args)
    verbose = opts.verbose
    root = Path.cwd()
    if not git.is_git_repository(root):
        p = VerbosePrinter(verbose=verbose)
        p.line(f"{root} is not inside a Git work tree.", ok=False, stream=sys.stderr)
        return 1

    raw = git.capture(
        ["git", "log", f"-n{opts.limit}", "--pretty=format:%h%x09%s%x09%D"],
        root,
    )
    lines = [line for line in raw.splitlines() if line.strip()]

    p = VerbosePrinter(verbose=verbose)
    p.blank_line()
    p.header("Git log", Count=str(len(lines)), Limit=str(opts.limit))

    if not lines:
        p.warn("No commits found.")
        return 0

    p.section("Commits")
    for line in lines:
        sha, subject, *rest = line.split("\t", 2)
        refs_raw = rest[0] if rest else ""
        refs = [ref.strip() for ref in refs_raw.split(",") if ref.strip()]
        p.list_item(GLYPHS.git.log_line(sha, subject, refs))
    return 0


@dataclass(frozen=True)
class DoctorOptions:
    """Typed view of ``argparse.Namespace`` for ``rrt git doctor``.

    Built once via :meth:`from_args` at the top of :func:`cmd_doctor` so both
    flags it reads have typed read sites instead of ``getattr(args, ...,
    default)`` / ``args.x`` calls throughout the function body.
    """

    verbose: int
    changelog_file: str

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> DoctorOptions:
        """Build a :class:`DoctorOptions` from a parsed ``argparse.Namespace``.

        ``changelog_file`` is given a real default ("CHANGELOG.md") by
        git_inspect.py's own register_inspect(), so a Namespace produced by
        argparse always carries it and is read directly. ``verbose`` is set
        globally by cli.py's parser, but every test in
        tests/commands/test_git_inspect.py that exercises cmd_doctor calls it
        with ``argparse.Namespace(changelog_file="CHANGELOG.md")`` that never
        sets ``verbose``, so the getattr fallback here absorbs that gap.
        """
        return cls(
            verbose=getattr(args, "verbose", 0) or 0,
            changelog_file=args.changelog_file,
        )


def _compute_changelog_problem(
    *,
    latest_subject: str,
    branch_name: str,
    changelog_file: str,
    root: Path,
) -> str | None:
    """Return a changelog problem message, or ``None`` when no changelog work is required.

    Mirrors the original inline body of :func:`cmd_doctor`: only inspects
    HEAD's changed files (via ``git diff-tree``) when *latest_subject*
    indicates changelog work is expected for this commit type.
    """
    if not latest_subject or not commit_subject_requires_changelog(latest_subject):
        return None
    changed_files = git.capture(
        ["git", "diff-tree", "--no-commit-id", "--name-only", "--root", "-r", "HEAD"],
        root,
    )
    changed = [line for line in changed_files.splitlines() if line.strip()]
    if changelog_is_updated(changed, changelog_file=changelog_file, cwd=root):
        return None
    return (
        f"Branch {branch_name!r} suggests changelog work, but {changelog_file} is not part of HEAD."
    )


def _build_doctor_checks(
    *,
    branch_problem: str | None,
    upstream: str | None,
    dirty_problem: str | None,
    operation_problem: str | None,
    conflict_problem: str | None,
    subject_problem: str | None,
    changelog_problem: str | None,
    changelog_file: str,
    branch_name: str,
    relation_problem: str | None,
) -> list[tuple[bool, str, str]]:
    """Build the ordered (ok, ok_message, problem_message) tuples for `rrt git doctor`.

    One tuple per health check; the sync-relation check is appended only when
    an upstream branch is configured, matching the original inline logic.
    """
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
            f"Changelog state is valid for {changelog_file}.",
            changelog_problem or "",
        ),
    ]
    if upstream is not None:
        checks.append(
            (
                relation_problem is None,
                f"{branch_name} does not need sync from {upstream}.",
                relation_problem or "",
            ),
        )
    return checks


def cmd_doctor(args: argparse.Namespace) -> int:
    """Run a compact repository health report for rrt workflows."""
    opts = DoctorOptions.from_args(args)
    verbose = opts.verbose
    root = Path.cwd()
    if not git.is_git_repository(root):
        p = VerbosePrinter(verbose=verbose)
        p.line(f"{root} is not inside a Git work tree.", ok=False, stream=sys.stderr)
        return 1

    branch_name = git.current_branch(root) or "<detached>"
    upstream = git.upstream_branch(root)
    try:
        status_lines = load_status_lines(root)
    except RuntimeError as exc:
        p = VerbosePrinter(verbose=verbose)
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
    changelog_problem = _compute_changelog_problem(
        latest_subject=latest_subject,
        branch_name=branch_name,
        changelog_file=opts.changelog_file,
        root=root,
    )

    summary = summarize_status(branch_name, status_lines, upstream=upstream, root=root)
    p = VerbosePrinter(verbose=verbose)
    p.blank_line()
    p.header(
        "Git doctor",
        Branch=branch_name,
        Upstream=upstream or "<none>",
        Sync=describe_sync_relation(ahead=ahead, behind=behind, base_ref=upstream),
        Status=summary,
        Commit=latest_subject or "<none>",
    )

    p.section("Checks")
    failures = 0

    checks = _build_doctor_checks(
        branch_problem=branch_problem,
        upstream=upstream,
        dirty_problem=dirty_problem,
        operation_problem=operation_problem,
        conflict_problem=conflict_problem,
        subject_problem=subject_problem,
        changelog_problem=changelog_problem,
        changelog_file=opts.changelog_file,
        branch_name=branch_name,
        relation_problem=relation_problem,
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


@dataclass(frozen=True)
class CheckDirtyTreeOptions:
    """Typed view of ``argparse.Namespace`` for ``rrt git check-dirty-tree``.

    Built once via :meth:`from_args` at the top of :func:`cmd_check_dirty_tree`
    so the single flag it reads has a typed read site instead of a bare
    ``getattr(args, ..., default)`` call.
    """

    verbose: int

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> CheckDirtyTreeOptions:
        """Build a :class:`CheckDirtyTreeOptions` from a parsed ``argparse.Namespace``.

        ``verbose`` is set globally by cli.py's parser, so a Namespace produced
        by argparse always carries it. The getattr fallback exists only because
        several tests in tests/commands/test_git_inspect.py call
        cmd_check_dirty_tree with a bare ``argparse.Namespace()`` that never
        sets ``verbose``.
        """
        return cls(verbose=getattr(args, "verbose", 0) or 0)


def cmd_check_dirty_tree(args: argparse.Namespace) -> int:
    """Return non-zero when the working tree is dirty."""
    opts = CheckDirtyTreeOptions.from_args(args)
    verbose = opts.verbose
    root = Path.cwd()
    if not git.is_git_repository(root):
        p = VerbosePrinter(verbose=verbose)
        p.line(f"{root} is not inside a Git work tree.", ok=False, stream=sys.stderr)
        return 1
    p = VerbosePrinter(verbose=verbose)
    if git.working_tree_clean(root):
        branch_name = git.current_branch(root) or "<detached>"
        upstream = git.upstream_branch(root)
        p.ok("Working tree is clean.")
        p.meta("Status", summarize_status(branch_name, [], upstream=upstream, root=root))
        return 0

    branch_name = git.current_branch(root) or "<detached>"
    upstream = git.upstream_branch(root)
    try:
        changed = load_status_lines(root)
    except RuntimeError as exc:
        p = VerbosePrinter(verbose=verbose)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1
    p.warn("Working tree has uncommitted changes.", stream=sys.stderr)
    p.meta(
        "Status",
        summarize_status(branch_name, changed, upstream=upstream, root=root),
        stream=sys.stderr,
    )
    shown = changed[:STATUS_MAX]
    for line in shown:
        p.file_entry(*git.classify_status_line(line), stream=sys.stderr)
    if len(changed) > STATUS_MAX:
        p.action(f"…and {len(changed) - STATUS_MAX} more", stream=sys.stderr)
    return 1


@dataclass(frozen=True)
class SyncStatusOptions:
    """Typed view of ``argparse.Namespace`` for ``rrt git sync-status``.

    Built once via :meth:`from_args` at the top of :func:`cmd_sync_status` so
    both flags it reads have typed read sites instead of ``getattr(args, ...,
    default)`` / ``args.x`` calls throughout the function body.
    """

    verbose: int
    base_ref: str | None

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> SyncStatusOptions:
        """Build a :class:`SyncStatusOptions` from a parsed ``argparse.Namespace``.

        ``base_ref`` is given a real default (None) by git_inspect.py's own
        register_inspect(), so a Namespace produced by argparse always
        carries it and is read directly. ``verbose`` is set globally by
        cli.py's parser, but every test in tests/commands/test_git_inspect.py
        that exercises cmd_sync_status calls it with
        ``argparse.Namespace(base_ref=...)`` that never sets ``verbose``, so
        the getattr fallback here absorbs that gap.
        """
        return cls(verbose=getattr(args, "verbose", 0) or 0, base_ref=args.base_ref)


def _render_sync_analysis(
    p: VerbosePrinter,
    *,
    branch_name: str,
    base_ref: str | None,
    operation: str | None,
    conflicts: list[str],
    ahead: int,
    behind: int,
) -> int:
    """Render the "Analysis" section for `rrt git sync-status` and return failure count.

    Checks, in order: in-progress merge/rebase, unresolved conflicts, and
    ahead/behind drift against *base_ref*. Matches the original inline body
    of :func:`cmd_sync_status` exactly, including message wording.
    """
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

    return failures


def cmd_sync_status(args: argparse.Namespace) -> int:
    """Analyze merge/rebase blockers and divergence against a sync base."""
    opts = SyncStatusOptions.from_args(args)
    verbose = opts.verbose
    root = Path.cwd()
    if not git.is_git_repository(root):
        p = VerbosePrinter(verbose=verbose)
        p.line(f"{root} is not inside a Git work tree.", ok=False, stream=sys.stderr)
        return 1

    branch_name = git.current_branch(root) or "<detached>"
    base_ref = opts.base_ref or git.upstream_branch(root)
    if base_ref is not None and not git.ref_exists(root, base_ref):
        p = VerbosePrinter(verbose=verbose)
        p.line(f"Base ref {base_ref!r} does not exist.", ok=False, stream=sys.stderr)
        return 1
    operation = git.in_progress_operation(root)
    try:
        status_lines = load_status_lines(root)
    except RuntimeError as exc:
        p = VerbosePrinter(verbose=verbose)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1

    conflicts = conflict_status_lines(status_lines)
    ahead, behind = (0, 0) if base_ref is None else git.ahead_behind(root, base_ref)
    relation = describe_sync_relation(ahead=ahead, behind=behind, base_ref=base_ref)

    p = VerbosePrinter(verbose=verbose)
    p.blank_line()
    p.header(
        "Sync status",
        Branch=branch_name,
        Base=base_ref or "<none>",
        Relation=relation,
        Operation=operation or "idle",
        Status=summarize_status(branch_name, status_lines, upstream=base_ref, root=root),
    )

    failures = _render_sync_analysis(
        p,
        branch_name=branch_name,
        base_ref=base_ref,
        operation=operation,
        conflicts=conflicts,
        ahead=ahead,
        behind=behind,
    )

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


def _parse_diff_line(raw: str) -> tuple[str, str, int | None]:
    """Parse a unified diff header or context line into (kind, text, lineno)."""
    if raw.startswith("+++") or raw.startswith("---"):
        return ("unchanged", raw, None)
    if raw.startswith("@@"):
        # Extract new-file line number from @@ -a,b +c,d @@ ...
        try:
            after_plus = raw.split("+")[1].split(",", maxsplit=1)[0].split(" ", maxsplit=1)[0]
            lineno = int(after_plus)
        except (IndexError, ValueError):
            lineno = None
        return ("unchanged", raw, lineno)
    if raw.startswith("+"):
        return ("added", raw[1:], None)
    if raw.startswith("-"):
        return ("removed", raw[1:], None)
    return ("unchanged", raw.removeprefix(" "), None)


def _parse_diff_hunk_header(raw: str) -> tuple[int, int] | None:
    """Return old/new line starts from a unified diff hunk header."""
    match = _HUNK_HEADER_RE.match(raw)
    if match is None:
        return None
    return (int(match.group("old")), int(match.group("new")))


@dataclass(frozen=True)
class DiffOptions:
    """Typed view of ``argparse.Namespace`` for ``rrt git diff``.

    Built once via :meth:`from_args` at the top of :func:`cmd_diff` so all
    flags it reads have typed read sites instead of ``getattr(args, ...,
    default)`` / ``args.x`` calls throughout the function body.
    """

    verbose: int
    staged: bool
    against: str | None

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> DiffOptions:
        """Build a :class:`DiffOptions` from a parsed ``argparse.Namespace``.

        ``staged`` and ``against`` are given real defaults by git_inspect.py's
        own register_inspect(), so a Namespace produced by argparse always
        carries both and they are read directly. ``verbose`` is set globally
        by cli.py's parser, but every test in
        tests/commands/test_git_inspect.py that exercises cmd_diff calls it
        with ``argparse.Namespace(staged=..., against=...)`` that never sets
        ``verbose``, so the getattr fallback here absorbs that gap.
        """
        return cls(
            verbose=getattr(args, "verbose", 0) or 0,
            staged=args.staged,
            against=args.against,
        )


def cmd_diff(args: argparse.Namespace) -> int:
    """Show a compact git diff using DiffGlyphs."""
    opts = DiffOptions.from_args(args)
    verbose = opts.verbose
    root = Path.cwd()
    if not git.is_git_repository(root):
        p = VerbosePrinter(verbose=verbose)
        p.line(f"{root} is not inside a Git work tree.", ok=False, stream=sys.stderr)
        return 1

    cmd = ["git", "diff", "--unified=3"]
    if opts.staged:
        cmd.append("--staged")
    if opts.against:
        cmd.append(opts.against)

    try:
        raw = git.capture_checked(cmd, root)
    except RuntimeError as exc:
        p = VerbosePrinter(verbose=verbose)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1
    if not raw.strip():
        p = VerbosePrinter(verbose=verbose)
        p.ok("No diff to show.")
        return 0

    current_file: str = ""
    old_lineno: int | None = None
    new_lineno: int | None = None

    p = VerbosePrinter(verbose=verbose)
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
            p = VerbosePrinter(verbose=verbose)
            p.blank_line()
            p.section(current_file)
            old_lineno = None
            new_lineno = None
            continue
        if raw_line.startswith("+++ /dev/null"):
            if current_file:
                p = VerbosePrinter(verbose=verbose)
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
            p = VerbosePrinter(verbose=verbose)
            p.action(f"  {GLYPHS.typography.mdash} {raw_line.strip()}")
            continue

        kind, text, hunk_start = _parse_diff_line(raw_line)
        if hunk_start is not None:
            p = VerbosePrinter(verbose=verbose)
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
            kind,
            text.rstrip(),
            lineno=rendered_lineno if kind != "unchanged" else None,
        )
        p = VerbosePrinter(verbose=verbose)
        p.line(f"  {rendered}")

    p.blank_line()
    return 0


def register_inspect(git_sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register status, diff, log, doctor, sync-status, and check-dirty-tree."""
    status_parser = git_sub.add_parser(
        "status",
        help="Show a compact branch and worktree status view.",
        description="Show the current branch, upstream, and compact typed worktree changes for the repository.",
        epilog=GIT_STATUS_EXAMPLES,
    )
    status_parser.set_defaults(handler=cmd_status)

    diff_parser = git_sub.add_parser(
        "diff",
        help="Show a compact diff using rrt glyph formatting.",
        description="Render a compact tracked-file diff with rrt glyphs for working-tree, staged, or ref-based changes.",
        epilog=GIT_DIFF_EXAMPLES,
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
        description="Show recent commits in a compact rrt log view with short SHAs, subjects, and refs.",
        epilog=GIT_LOG_EXAMPLES,
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
        description="Run branch, upstream, worktree, conflict, commit-subject, and changelog checks for an rrt workflow.",
        epilog=GIT_DOCTOR_EXAMPLES,
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
        description="Report merge or rebase blockers plus ahead/behind drift against the upstream branch or --base-ref.",
        epilog=GIT_SYNC_STATUS_EXAMPLES,
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
        description="Exit non-zero when the working tree is dirty and print a compact status summary for hooks or CI.",
        epilog=GIT_CHECK_DIRTY_TREE_EXAMPLES,
    )
    dirty_parser.set_defaults(handler=cmd_check_dirty_tree)
