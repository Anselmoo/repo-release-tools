"""Git helpers."""

from __future__ import annotations

import subprocess

from pathlib import Path

from repo_release_tools import output


def run(cmd: list[str], cwd: Path, *, dry_run: bool, label: str) -> str:
    """Run a command in a repository."""
    pretty = " ".join(cmd)
    if dry_run:
        print(output.dry_run(f"Would run: {pretty}"))
        return ""
    print(output.status("$", pretty))
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        if result.stdout.strip():
            for line in result.stdout.strip().splitlines():
                print(output.status(">", line, indent=4))
        if result.stderr.strip():
            for line in result.stderr.strip().splitlines():
                print(output.status("!", line, indent=4))
        raise RuntimeError(f"{label} failed (exit {result.returncode})")
    if result.stdout.strip():
        for line in result.stdout.strip().splitlines():
            print(output.status(">", line, indent=4))
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
