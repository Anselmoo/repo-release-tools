#!/usr/bin/env python3
"""Run a local, change-aware rrt preflight before CI sees the branch.

Install surfaces:
- Claude: ./.claude or ~/.claude
- Codex: ./.codex or ~/.codex
- Gemini: ./.gemini or ~/.gemini
- Copilot: ./.github or ~/.copilot

Exit codes:
- 0: preflight checks passed
- 1: one or more preflight checks failed
- 2: rrt or git state is unavailable
"""

from __future__ import annotations

import shutil
import subprocess
import sys


def _changed_files() -> list[str]:
    for command in (["git", "diff", "--name-only", "--cached"], ["git", "diff", "--name-only"]):
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode == 0 and result.stdout.strip():
            return [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return []


def main() -> int:
    """Run the local CI preflight reminder hook."""
    if shutil.which("rrt") is None:
        print(
            "rrt is not on PATH. Install repo-release-tools before using this preflight.",
            file=sys.stderr,
        )
        return 2
    commands: list[list[str]] = [["rrt", "doctor"]]
    changed = _changed_files()
    if any(
        path.startswith(("docs/", ".github/skills/", ".github/agents/", ".github/hooks/"))
        or path in {"README.md", "pyproject.toml"}
        for path in changed
    ):
        commands.append(["rrt", "docs", "check"])
    if any(
        path in {"CHANGELOG.md", "pyproject.toml", ".rrt.toml", "package.json", "Cargo.toml"}
        for path in changed
    ):
        commands.append(["rrt", "release", "check"])
    failures: list[str] = []
    for command in commands:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            summary = (
                result.stdout.strip() or result.stderr.strip() or "command failed"
            ).splitlines()[0]
            failures.append(f"{' '.join(command)} -> {summary}")
    if failures:
        print("Local preflight failed:\n- " + "\n- ".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
