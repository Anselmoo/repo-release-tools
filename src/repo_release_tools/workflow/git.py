"""Git workflow helpers for repository status, commit, sync, and history operations.

## Overview

`repo-release-tools` ships a small set of opinionated Git workflows for branch
health, commit drafting, sync, and history repair. The tool group favors compact,
human-readable summaries with explicit safety checks before any destructive
operation.

Most commands are designed to run from a Git work tree and emit a short
summary first, followed by the details needed to act on the result.

## Workflow map

- **Inspect**: `rrt git status`, `diff`, `log`, `doctor`, `sync-status`,
  `check-dirty-tree`
- **Draft commits**: `rrt git commit`, `commit-all`, `squash-local`
- **Move and sync**: `rrt git sync`, `move`, `undo-safe`, `rebootstrap`
- **Branch workflows**: `rrt branch new`, `rescue`, `rename`
- **Publish**: `rrt git publish-snapshot` force-pushes a single-commit,
  no-history snapshot of tracked content to a secondary remote (e.g. a public
  mirror); `--exclude` drops specific paths (secrets, internal docs) from
  that snapshot.

## Responsibilities

- provide a high-level API for common Git operations used in release flows
- enforce repository policies during commit drafting and branch management
- automate repetitive tasks like auto-stashing during branch switches
- generate human-friendly summaries of repository state and history
- ensure safe operation through dry-run modes and state validation

## Notable behavior

- **Commit Drafting**: `rrt git commit` infers the commit type from the current
  branch only when the branch follows the conventional `type/slug` format.
- **State Management**: `sync` and `move` automatically stash local changes
  before execution and restore them afterward.
- **History Repair**: `undo-safe` and `rebootstrap` provide controlled ways to
  rewrite history, with `rebootstrap` requiring explicit confirmation.
- **Validation**: Refuses to continue in unsafe states, such as unresolved
  conflicts or in-progress merges.

## Examples

- `rrt git status`
- `rrt git commit "refresh help examples"`
- `rrt git sync --dry-run`
- `rrt git squash-local --base-ref origin/main "ship parser"`
- `rrt git rebootstrap --yes-i-know-this-destroys-history --dry-run`

## See also

- [Conventional branches](/repo-release-tools/commands/branch/)
- [Generated CLI reference](/repo-release-tools/commands/rrt-cli/)
"""

from __future__ import annotations

import datetime as dt
import posixpath
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

from repo_release_tools.ui import DryRunPrinter, VerbosePrinter

# Ordered source-owned topic docs for future generic docs generation.
GIT_DOC = (
    "# rrt git\n\n"
    "Git workflow helpers for repository status, commit, sync, and history operations.\n\n"
    f"{(__doc__ or '').split('\n\n', 1)[1]}"
    if __doc__ and "\n\n" in __doc__
    else (__doc__ or "")
)

SOURCE_OWNED_TOPIC_DOCS: tuple[tuple[str, str], ...] = (("git", GIT_DOC),)


def run(
    cmd: list[str],
    cwd: Path,
    *,
    dry_run: bool,
    label: str,
    suppress_announce: bool = False,
) -> str:
    """Run a command in a repository."""
    pretty = " ".join(cmd)
    if dry_run:
        p = DryRunPrinter(dry_run=True)
        p.would_run(pretty)
        return ""
    if not suppress_announce:
        p = VerbosePrinter()
        p.action(f"$ {pretty}")
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        p = VerbosePrinter()
        if result.stdout.strip():
            for line in result.stdout.strip().splitlines():
                p.action(line)
        if result.stderr.strip():
            for line in result.stderr.strip().splitlines():
                p.warn(line, stream=None)
        # The last stderr line is usually the actionable one (e.g. a
        # pre-commit hook's summary starts with a generic "<hook>...Failed"
        # header and ends with the specific reason, like "- files were
        # modified by this hook").
        last_err = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else ""
        detail = f": {last_err}" if last_err else ""
        raise RuntimeError(f"{label} failed (exit {result.returncode}){detail}")
    if result.stdout.strip():
        p = VerbosePrinter()
        for line in result.stdout.strip().splitlines():
            p.action(line)
    return result.stdout.strip()


def capture(cmd: list[str], cwd: Path) -> str:
    """Capture command output."""
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def capture_checked(cmd: list[str], cwd: Path) -> str:
    """Capture command output, raising RuntimeError on non-zero exit."""
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        label = " ".join(cmd)
        raise RuntimeError(f"{label} failed (exit {result.returncode})")
    return result.stdout.strip()


def current_branch(cwd: Path) -> str:
    """Return the current branch name."""
    return capture(["git", "branch", "--show-current"], cwd)


def branch_exists(cwd: Path, branch: str) -> bool:
    """Return whether a local branch exists."""
    return bool(capture(["git", "branch", "--list", "--", branch], cwd))


def working_tree_clean(cwd: Path) -> bool:
    """Return whether the repository has no uncommitted changes."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == ""


def commits_ahead(cwd: Path, base_ref: str) -> list[str]:
    """Return short log lines for commits on HEAD not in the base ref.

    Raises ``ValueError`` if *base_ref* starts with ``-``: the range expression
    ``<base_ref>..HEAD`` is a single positional argument to ``git log`` that
    cannot be guarded with a ``--`` separator (git would then treat the range
    as a pathspec instead of a revision range), so a leading dash is rejected
    outright to prevent option-injection (CWE-88).
    """
    if base_ref.startswith("-"):
        raise ValueError(f"base_ref must not start with '-': {base_ref!r}")
    out = capture(["git", "log", f"{base_ref}..HEAD", "--pretty=format:%h %s"], cwd)
    return [line for line in out.splitlines() if line]


def ahead_behind(cwd: Path, base_ref: str) -> tuple[int, int]:
    """Return commits ahead/behind relative to a base ref."""
    result = subprocess.run(
        ["git", "rev-list", "--left-right", "--count", f"HEAD...{base_ref}"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return (0, 0)
    raw = result.stdout.strip().split()
    if len(raw) != 2:
        return (0, 0)
    return (int(raw[0]), int(raw[1]))


def status_porcelain(cwd: Path, *, include_branch: bool = False) -> list[str]:
    """Return git status lines in porcelain format."""
    command = ["git", "status", "--short"]
    if include_branch:
        command.append("--branch")
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git status --short failed (exit {result.returncode})")
    return [line for line in result.stdout.splitlines() if line]


def upstream_branch(cwd: Path) -> str | None:
    """Return the configured upstream ref for the current branch, if any."""
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def ref_exists(cwd: Path, ref: str) -> bool:
    """Return whether *ref* resolves to an object in this repository.

    Returns ``False`` (rather than invoking git) if *ref* starts with ``-``:
    ``git rev-parse --verify`` parses its positional argument as an option
    when it looks like one even after a ``--`` separator, so a leading dash
    is rejected outright to prevent option-injection (CWE-88) instead of
    being passed through to the subprocess.
    """
    if ref.startswith("-"):
        return False
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", ref],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def git_dir(cwd: Path) -> Path | None:
    """Return the resolved .git directory for the current work tree, if available."""
    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    raw = result.stdout.strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = cwd / path
    return path.resolve()


def in_progress_operation(cwd: Path) -> str | None:
    """Return the current merge/rebase operation name, if one is in progress."""
    directory = git_dir(cwd)
    if directory is None:
        return None
    if (directory / "rebase-merge").exists() or (directory / "rebase-apply").exists():
        return "rebase"
    if (directory / "MERGE_HEAD").exists():
        return "merge"
    return None


def merge_base(cwd: Path, left: str, right: str = "HEAD") -> str | None:
    """Return the merge-base sha for two refs, if one exists."""
    result = subprocess.run(
        ["git", "merge-base", left, right],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def remote_names(cwd: Path) -> list[str]:
    """Return configured remote names."""
    out = capture(["git", "remote"], cwd)
    return [line.strip() for line in out.splitlines() if line.strip()]


def remote_url(cwd: Path, name: str) -> str | None:
    """Return the configured URL for a remote, or None if it doesn't exist."""
    result = subprocess.run(
        ["git", "remote", "get-url", name],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


_SCP_STYLE_RE = re.compile(r"^(?:[\w.-]+@)?([\w.-]+):(.+)$")


def normalize_remote_url(url: str) -> str:
    """Normalize a git remote URL to a scheme-and-case-insensitive host/path form.

    Used only for the publish-snapshot origin-equality guard, never for the
    actual push (which always uses the raw configured/flag value). Collapses
    ``..``/``.`` path segments so a same-repo URL padded with redundant path
    traversal still compares equal to its canonical form.
    """
    value = url.strip()
    for scheme in ("ssh://", "https://", "http://", "git://", "file://"):
        if value.startswith(scheme):
            value = value[len(scheme) :]
            break
    else:
        scp_match = _SCP_STYLE_RE.match(value)
        if scp_match:
            value = f"{scp_match.group(1)}/{scp_match.group(2)}"

    if "@" in value.split("/", 1)[0]:
        value = value.split("@", 1)[1]

    value = value.removesuffix(".git").rstrip("/")
    host, sep, path = value.partition("/")
    if sep:
        path = posixpath.normpath(f"/{path}").lstrip("/")
    return f"{host.lower()}/{path}"


def primary_remote_conflict(cwd: Path, remote: str, primary_remote: str = "origin") -> str | None:
    """Return an error message if *remote* resolves to the same URL as *primary_remote*, else None."""
    primary_url = remote_url(cwd, primary_remote)
    remote_url_value = remote_url(cwd, remote) or remote
    if primary_url is not None and normalize_remote_url(primary_url) == normalize_remote_url(
        remote_url_value
    ):
        return f"--remote {remote!r} resolves to the same URL as {primary_remote} ({primary_url})."
    return None


def unique_snapshot_branch_name(
    cwd: Path,
    *,
    prefix: str = "rrt-snapshot-tmp",
    now: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.UTC),
) -> str:
    """Return a local branch name for a publish-snapshot temp branch, avoiding collisions."""
    stamp = now().strftime("%Y%m%d%H%M%S")
    base = f"{prefix}-{stamp}"
    if not branch_exists(cwd, base):
        return base
    suffix = 1
    while branch_exists(cwd, f"{base}-{suffix}"):
        suffix += 1
    return f"{base}-{suffix}"


def is_git_repository(cwd: Path) -> bool:
    """Return whether cwd is inside a Git work tree."""
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def classify_status_line(line: str) -> tuple[str, str]:
    """Classify a git porcelain status line into a compact diff category.

    Returns a ``(kind, path_text)`` tuple where *kind* is one of:
    ``"added"``, ``"removed"``, ``"modified"``, ``"renamed"`,
    ``"conflict"``, or ``"untracked"``.
    """
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
