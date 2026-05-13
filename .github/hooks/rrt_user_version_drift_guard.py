#!/usr/bin/env python3
"""Block on detected version-target drift using rrt's own release checks.

Install surfaces:
- Claude: ./.claude or ~/.claude
- Codex: ./.codex or ~/.codex
- Gemini: ./.gemini or ~/.gemini
- Copilot: ./.github or ~/.copilot

Exit codes:
- 0: no version drift detected
- 1: version drift detected
- 2: rrt is unavailable
"""

from __future__ import annotations

import shutil
import subprocess
import sys


def main() -> int:
    """Warn when local version files appear out of sync."""
    if shutil.which("rrt") is None:
        print(
            "rrt is not on PATH. Install repo-release-tools before using this guard.",
            file=sys.stderr,
        )
        return 2
    try:
        result = subprocess.run(
            ["rrt", "release", "check"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        print(exc, file=sys.stderr)
        return 2
    if result.returncode == 0:
        return 0
    summary = result.stdout.strip() or result.stderr.strip() or "rrt release check failed"
    print(summary, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
