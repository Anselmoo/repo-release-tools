#!/usr/bin/env python3
"""Validate semantic branch names for rrt users.

Install surfaces:
- Claude: ./.claude or ~/.claude
- Codex: ./.codex or ~/.codex
- Gemini: ./.gemini or ~/.gemini
- Copilot: ./.github or ~/.copilot

Exit codes:
- 0: branch is valid
- 1: branch violates policy
- 2: branch name could not be resolved
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

ALLOWED_TYPES = (
    "feat",
    "fix",
    "refactor",
    "perf",
    "docs",
    "chore",
    "ci",
    "build",
    "test",
    "deps",
    "claude",
    "codex",
    "copilot",
    "dependabot",
    "renovate",
)
BRANCH_RE = re.compile(rf"^({'|'.join(ALLOWED_TYPES)})/[a-z0-9]+(?:-[a-z0-9]+)*$")


def _resolve_branch(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    branch = result.stdout.strip()
    return branch if result.returncode == 0 and branch and branch != "HEAD" else None


def main() -> int:
    """Validate the current branch name and exit with a status code."""
    parser = argparse.ArgumentParser(description="Validate an rrt semantic branch name.")
    parser.add_argument(
        "--branch",
        help="Explicit branch name. Defaults to the current git branch.",
    )
    args = parser.parse_args()
    branch = _resolve_branch(args.branch)
    if branch is None:
        print(
            "Could not resolve a branch name. Pass --branch or run inside a git worktree.",
            file=sys.stderr,
        )
        return 2
    if BRANCH_RE.fullmatch(branch):
        return 0
    allowed = ", ".join(ALLOWED_TYPES)
    print(
        f"Invalid branch '{branch}'. Expected <type>/<kebab-slug> where type is one of: {allowed}. "
        'Try: rrt branch new feat "describe the change".',
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
