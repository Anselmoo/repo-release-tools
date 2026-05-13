#!/usr/bin/env python3
"""Validate Conventional Commit subjects for rrt users.

Install surfaces:
- Claude: ./.claude or ~/.claude
- Codex: ./.codex or ~/.codex
- Gemini: ./.gemini or ~/.gemini
- Copilot: ./.github or ~/.copilot

Exit codes:
- 0: commit subject is valid
- 1: commit subject violates policy
- 2: commit subject could not be read
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ALLOWED_TYPES = "feat|fix|refactor|perf|docs|chore|ci|build|test|deps"
SUBJECT_RE = re.compile(rf"^({ALLOWED_TYPES})(\([a-z0-9._/-]+\))?(!)?: .+")


def _read_subject(message_file: str | None, message: str | None) -> str | None:
    if message:
        return message.strip()
    if message_file:
        lines = Path(message_file).read_text(encoding="utf-8").splitlines()
        return next((line.strip() for line in lines if line.strip()), None)
    if not sys.stdin.isatty():
        data = sys.stdin.read().strip().splitlines()
        return next((line.strip() for line in data if line.strip()), None)
    return None


def main() -> int:
    """Validate the current commit subject against repo policy."""
    parser = argparse.ArgumentParser(description="Validate a Conventional Commit subject.")
    parser.add_argument("--message-file", help="Path to a commit message file.")
    parser.add_argument("--message", help="Explicit commit subject.")
    args = parser.parse_args()
    subject = _read_subject(args.message_file, args.message)
    if not subject:
        print("Could not read a commit subject. Pass --message or --message-file.", file=sys.stderr)
        return 2
    if SUBJECT_RE.fullmatch(subject):
        return 0
    print(
        f"Invalid commit subject '{subject}'. Expected Conventional Commits such as "
        'feat: add release audit or fix(cli): repair branch parser. Try: rrt git commit --type fix "describe the change".',
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
