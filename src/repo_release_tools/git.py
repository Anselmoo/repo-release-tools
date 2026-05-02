"""Git helpers for repo-release-tools."""

from __future__ import annotations

import subprocess
from pathlib import Path

from repo_release_tools.ui import DryRunPrinter

GIT_MAGIC_DOC = """# Git magic

`repo-release-tools` ships a small set of opinionated Git workflows for branch
health, commit drafting, sync, and history repair.

This page is generated from `repo_release_tools.git.GIT_MAGIC_DOC`.
This page stays workflow-oriented. For the full command surface and option
details, see [docs/rrt-cli.md](rrt-cli.md).

## Workflow map

- **Inspect** — `rrt git status`, `diff`, `log`, `doctor`, `sync-status`,
  `check-dirty-tree`
- **Draft commits** — `rrt git commit`, `commit-all`, `squash-local`
- **Move and sync** — `rrt git sync`, `move`, `undo-safe`, `rebootstrap`
- **Branch workflows** — `rrt branch new`, `rescue`, `rename`

## What the Git helpers optimize for

- compact, human-readable summaries first
- explicit safety checks before destructive actions
- conventional commit subjects and conventional branch names when possible
- reuse across local CLI, hooks, and CI

## Notable behavior

- `rrt git commit` infers the commit type from the current branch only when the
  branch is a conventional `type/slug` branch.
- Branches named `main`, `master`, `develop`, `release/v<semver>`, AI helper
  branches, bot branches, and custom branch prefixes are treated as special
  cases and may require `--type` for commit drafting.
- `sync` and `move` auto-stash local changes when needed.
- `undo-safe` and `rebootstrap` can rewrite history; `rebootstrap` also
  requires explicit confirmation before it destroys the current repository
  history.
- Commands that support `--dry-run` preview git operations without changing the
  worktree.

## Current command surface

```text
rrt git status
rrt git diff
rrt git log
rrt git doctor
rrt git sync-status
rrt git check-dirty-tree
rrt git commit "handle empty config"
rrt git commit-all "snapshot parser cleanup"
rrt git sync
rrt git move feat/new-parser
rrt git squash-local "ship parser cleanup"
rrt git undo-safe --keep-staged
rrt git rebootstrap --yes-i-know-this-destroys-history --dry-run
```

## See also

- [Conventional branches](branch.md)
- [Generated CLI reference](rrt-cli.md)
"""

# Ordered source-owned topic docs for future generic docs generation.
SOURCE_OWNED_TOPIC_DOCS: tuple[tuple[str, str], ...] = (("git", GIT_MAGIC_DOC),)


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
        p = DryRunPrinter(dry_run=False)
        p.action(f"$ {pretty}")
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        p = DryRunPrinter(dry_run=False)
        if result.stdout.strip():
            for line in result.stdout.strip().splitlines():
                p.action(line)
        if result.stderr.strip():
            for line in result.stderr.strip().splitlines():
                p.warn(line, stream=None)
        raise RuntimeError(f"{label} failed (exit {result.returncode})")
    if result.stdout.strip():
        p = DryRunPrinter(dry_run=False)
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
    return bool(capture(["git", "branch", "--list", branch], cwd))


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
    """Return short log lines for commits on HEAD not in the base ref."""
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
    """Return whether *ref* resolves to an object in this repository."""
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
