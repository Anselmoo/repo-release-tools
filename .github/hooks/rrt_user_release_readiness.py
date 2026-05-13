#!/usr/bin/env python3
"""Run read-only release readiness checks for rrt users.

Install surfaces:
- Claude: ./.claude or ~/.claude
- Codex: ./.codex or ~/.codex
- Gemini: ./.gemini or ~/.gemini
- Copilot: ./.github or ~/.copilot

Exit codes:
- 0: readiness checks passed
- 1: one or more readiness checks failed
- 2: required tooling is unavailable
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def _run(command: list[str]) -> tuple[int, str]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        return 2, str(exc)
    summary = (result.stdout.strip() or result.stderr.strip() or "command failed").splitlines()[0]
    return result.returncode, summary


def main() -> int:
    """Run the release-readiness reminder hook."""
    if shutil.which("rrt") is None:
        print(
            "rrt is not on PATH. Install repo-release-tools before using this hook.",
            file=sys.stderr,
        )
        return 2
    commands = [["rrt", "doctor"], ["rrt", "release", "check"]]
    if Path("docs").exists() or Path("README.md").exists():
        commands.append(["rrt", "docs", "check"])
    failures: list[str] = []
    for command in commands:
        code, summary = _run(command)
        if code != 0:
            failures.append(f"{' '.join(command)} -> {summary}")
    if failures:
        print("Release readiness failed:\n- " + "\n- ".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
