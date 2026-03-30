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
    return capture(["git", "status", "--porcelain"], cwd) == ""


def commits_ahead(cwd: Path, base_ref: str) -> list[str]:
    """Return short log lines for commits on HEAD not in the base ref."""
    out = capture(["git", "log", f"{base_ref}..HEAD", "--pretty=format:%h %s"], cwd)
    return [line for line in out.splitlines() if line]
