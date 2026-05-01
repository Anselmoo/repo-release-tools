#!/usr/bin/env python3
"""Pre-commit hook: fail if raw print(...) is used outside src/repo_release_tools/ui.

Allow prints in:
 - src/repo_release_tools/ui/
 - tests/ (test scaffolding)

Otherwise, report file:line occurrences and exit non-zero.
"""

import re
import sys
from pathlib import Path

ROOT = Path(".")
PATTERN = re.compile(r"\bprint\s*\(")
IGNORE_DIR = Path("src/repo_release_tools/ui")

errors = []
for p in (ROOT / "src" / "repo_release_tools").rglob("*.py"):
    try:
        rel = p.relative_to(ROOT)
    except Exception:
        rel = p
    if IGNORE_DIR in p.parents:
        continue
    if "tests" in p.parts:
        continue
    text = p.read_text(encoding="utf-8")
    for i, line in enumerate(text.splitlines(), start=1):
        if PATTERN.search(line):
            errors.append(f"{rel}:{i}: {line.strip()}")

if errors:
    print("ERROR: Raw print(...) usage detected outside allowed UI surface:\n", file=sys.stderr)
    for e in errors:
        print(e, file=sys.stderr)
    print(
        "\nPlease migrate printing to repo_release_tools.ui (DryRunPrinter, color helpers, ProgressLine).",
        file=sys.stderr,
    )
    sys.exit(1)

print("No disallowed print(...) found.")
sys.exit(0)
