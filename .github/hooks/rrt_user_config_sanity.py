#!/usr/bin/env python3
"""Validate basic rrt config sanity without assuming repo internals.

Install surfaces:
- Claude: ./.claude or ~/.claude
- Codex: ./.codex or ~/.codex
- Gemini: ./.gemini or ~/.gemini
- Copilot: ./.github or ~/.copilot

Exit codes:
- 0: config looks sane
- 1: config needs attention
- 2: config could not be parsed
"""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

CONFIG_FILES = ("pyproject.toml", ".rrt.toml", "Cargo.toml", "package.json")


def _load(path: Path) -> None:
    if path.suffix == ".json":
        json.loads(path.read_text(encoding="utf-8"))
        return
    tomllib.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    """Check for local repo-release-tools configuration files."""
    existing = [Path(name) for name in CONFIG_FILES if Path(name).is_file()]
    if not existing:
        print(
            "No supported rrt config file found. Create pyproject.toml, .rrt.toml, Cargo.toml, or package.json first.",
            file=sys.stderr,
        )
        return 1
    for path in existing:
        if ".geminini" in path.read_text(encoding="utf-8"):
            print(f"{path} contains '.geminini'. Replace it with '.gemini'.", file=sys.stderr)
            return 1
        try:
            _load(path)
        except Exception as exc:
            print(f"{path} could not be parsed: {exc}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
