#!/usr/bin/env python3
"""Emit a non-blocking docs sync reminder when docs-facing files change.

Install surfaces:
- Claude: ./.claude or ~/.claude
- Codex: ./.codex or ~/.codex
- Gemini: ./.gemini or ~/.gemini
- Copilot: ./.github or ~/.copilot

Exit codes:
- 0: no blocking issue; reminder may be emitted
- 2: git state could not be inspected
"""

from __future__ import annotations

import subprocess
import sys

DOC_PREFIXES = ("docs/", ".github/skills/", ".github/agents/", ".github/hooks/")
DOC_FILES = {"README.md", "pyproject.toml", ".rrt.toml", "action.yml"}


def _changed_files() -> tuple[int, list[str]]:
    commands = (
        ["git", "diff", "--name-only", "--cached"],
        ["git", "diff", "--name-only"],
    )
    for command in commands:
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=False)
        except OSError:
            return 2, []
        if result.returncode == 0:
            files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            if files:
                return 0, files
    return 0, []


def main() -> int:
    """Hint when source-owned docs appear to have drifted."""
    code, files = _changed_files()
    if code != 0:
        print("Could not inspect git changes. Run `rrt docs check` manually.", file=sys.stderr)
        return 2
    if any(path in DOC_FILES or path.startswith(DOC_PREFIXES) for path in files):
        print(
            "Docs-facing files changed. Run `rrt docs check` (and `poe sync-assets` if assets changed).",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
