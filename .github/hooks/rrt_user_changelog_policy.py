#!/usr/bin/env python3
"""Check whether changelog state is acceptable for the proposed commit.

Install surfaces:
- Claude: ./.claude or ~/.claude
- Codex: ./.codex or ~/.codex
- Gemini: ./.gemini or ~/.gemini
- Copilot: ./.github or ~/.copilot

Exit codes:
- 0: changelog state is acceptable
- 1: changelog action is required
- 2: commit subject could not be classified
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

RELEVANT_TYPES = {"feat", "fix", "refactor", "perf", "docs"}
SUBJECT_RE = re.compile(
    r"^(feat|fix|refactor|perf|docs|chore|ci|build|test|deps)(\([^)]+\))?(!)?: ",
)


def _subject_from_args(args: argparse.Namespace) -> str | None:
    if args.subject:
        return args.subject.strip()
    if args.message_file:
        lines = Path(args.message_file).read_text(encoding="utf-8").splitlines()
        return next((line.strip() for line in lines if line.strip()), None)
    return None


def main() -> int:
    """Check changelog readiness for the current commit context."""
    parser = argparse.ArgumentParser(
        description="Require basic changelog readiness for relevant commits.",
    )
    parser.add_argument("--subject", help="Commit subject to classify.")
    parser.add_argument("--message-file", help="Commit message file to read the subject from.")
    parser.add_argument(
        "--changelog",
        default="CHANGELOG.md",
        help="Changelog path. Defaults to CHANGELOG.md.",
    )
    args = parser.parse_args()
    subject = _subject_from_args(args)
    if not subject:
        print("Could not read a commit subject. Pass --subject or --message-file.", file=sys.stderr)
        return 2
    match = SUBJECT_RE.match(subject)
    if not match:
        print(
            f"Could not classify commit subject '{subject}'. Run the commit policy check first.",
            file=sys.stderr,
        )
        return 2
    if match.group(1) not in RELEVANT_TYPES:
        return 0
    changelog = Path(args.changelog)
    if not changelog.is_file():
        print(
            f"{changelog} is missing. Add a Keep-a-Changelog file with an [Unreleased] section.",
            file=sys.stderr,
        )
        return 1
    content = changelog.read_text(encoding="utf-8")
    if "[Unreleased]" not in content:
        print(
            f"{changelog} does not contain an [Unreleased] section. Create or restore it before committing '{subject}'.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
