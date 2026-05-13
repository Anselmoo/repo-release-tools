#!/usr/bin/env python3
"""Fail when the git worktree is dirty.

Install surfaces:
- Claude: ./.claude or ~/.claude
- Codex: ./.codex or ~/.codex
- Gemini: ./.gemini or ~/.gemini
- Copilot: ./.github or ~/.copilot

Exit codes:
- 0: worktree is clean
- 1: worktree has uncommitted changes
- 2: git state could not be inspected
"""

from __future__ import annotations

import subprocess
import sys


def main() -> int:
    """Warn when the working tree is dirty before stopping."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        print("Could not run git status. Run inside a git repository.", file=sys.stderr)
        return 2
    if result.returncode != 0:
        print((result.stderr or "git status failed").strip(), file=sys.stderr)
        return 2
    if result.stdout.strip():
        print(
            "Working tree is dirty. Commit, stash, or clean changes before continuing.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
