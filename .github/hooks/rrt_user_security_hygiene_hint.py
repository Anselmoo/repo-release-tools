#!/usr/bin/env python3
"""Flag obvious secret leaks and risky security patterns in staged changes.

Install surfaces:
- Claude: ./.claude or ~/.claude
- Codex: ./.codex or ~/.codex
- Gemini: ./.gemini or ~/.gemini
- Copilot: ./.github or ~/.copilot

Exit codes:
- 0: no blocking secret leak found
- 1: likely secret leak found
- 2: git diff could not be inspected
"""

from __future__ import annotations

import re
import subprocess
import sys

BLOCK_PATTERNS = {
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Private key": re.compile(r"-----BEGIN (RSA|OPENSSH|EC|DSA) PRIVATE KEY-----"),
}
WARN_PATTERNS = {
    "shell=True": re.compile(r"shell\s*=\s*True"),
    "eval(": re.compile(r"\beval\s*\("),
    "exec(": re.compile(r"\bexec\s*\("),
}


def main() -> int:
    """Emit a security-hygiene reminder before stopping."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--", "."],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        print("Could not inspect staged changes. Run a manual secret scan.", file=sys.stderr)
        return 2
    if result.returncode != 0:
        print((result.stderr or "git diff failed").strip(), file=sys.stderr)
        return 2
    diff_text = result.stdout
    blocking = [label for label, pattern in BLOCK_PATTERNS.items() if pattern.search(diff_text)]
    if blocking:
        print("Possible secret material detected: " + ", ".join(blocking) + ".", file=sys.stderr)
        return 1
    warnings = [label for label, pattern in WARN_PATTERNS.items() if pattern.search(diff_text)]
    if warnings:
        print(
            "Security hygiene hint: review these risky patterns before commit: "
            + ", ".join(warnings)
            + ".",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
