#!/usr/bin/env python3
"""Pre-commit hook: fail if raw print(...) is used outside src/repo_release_tools/ui.

Allow prints in:
 - src/repo_release_tools/ui/
 - src/repo_release_tools/assets/hooks/  (boilerplate standalone scripts)
 - tests/ (test scaffolding)

Otherwise, report file:line occurrences and exit non-zero.
"""

import sys
import tokenize
from io import StringIO
from pathlib import Path

ROOT = Path()
IGNORE_DIR = Path("src/repo_release_tools/ui")
IGNORE_ASSETS_HOOKS = Path("src/repo_release_tools/assets/hooks")


def _iter_print_call_lines(text: str) -> set[int]:
    """Return line numbers containing real ``print(...)`` calls.

    Uses Python tokenization so string literals (including docstrings) and
    comments are ignored automatically.
    """
    lines: set[int] = set()
    tokens = list(tokenize.generate_tokens(StringIO(text).readline))
    for idx, tok in enumerate(tokens):
        if tok.type != tokenize.NAME or tok.string != "print":
            continue

        # Look ahead to the next non-trivia token.
        j = idx + 1
        while j < len(tokens) and tokens[j].type in {
            tokenize.NL,
            tokenize.NEWLINE,
            tokenize.INDENT,
            tokenize.DEDENT,
            tokenize.COMMENT,
        }:
            j += 1

        if j < len(tokens) and tokens[j].string == "(":
            lines.add(tok.start[0])
    return lines


errors = []
for p in (ROOT / "src" / "repo_release_tools").rglob("*.py"):
    try:
        rel = p.relative_to(ROOT)
    except Exception:
        rel = p
    if IGNORE_DIR in p.parents:
        continue
    if IGNORE_ASSETS_HOOKS in p.parents:
        continue
    if "tests" in p.parts:
        continue
    text = p.read_text(encoding="utf-8")
    for line_no in sorted(_iter_print_call_lines(text)):
        source_line = text.splitlines()[line_no - 1].strip()
        errors.append(f"{rel}:{line_no}: {source_line}")
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
