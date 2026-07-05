"""Cross-cutting helpers shared by two or more `rrt git` command families.

`rrt git` is organized into three command families documented in
`git_cmd.py`: inspection, commit drafting, and branch maintenance/sync.
A handful of helpers -- `STATUS_MAX`, `load_status_lines`,
`conflict_status_lines`, `summarize_status`, and `add_dry_run_flag` -- are
used by two or more of those families, so they live here instead of in any
single family module. This module holds no command handlers of its own and
is not registered as a subcommand; it exists purely as internal
infrastructure imported by the family modules.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from repo_release_tools.ui import GLYPHS
from repo_release_tools.workflow import git

STATUS_MAX = 15


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


def add_dry_run_flag(parser: argparse.ArgumentParser) -> None:
    """Register a shared dry-run flag."""
    parser.add_argument("--dry-run", action="store_true", help="Preview without changing git.")
