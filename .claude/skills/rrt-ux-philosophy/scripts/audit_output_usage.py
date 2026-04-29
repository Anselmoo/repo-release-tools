#!/usr/bin/env python3
"""rrt UX audit script.

Scans src/repo_release_tools/ for output.py usage, raw ANSI escapes, and
hardcoded widths. Produces a prioritised migration report.

Usage:
    python3 scripts/audit_output_usage.py [--root /path/to/repo]
    python3 scripts/audit_output_usage.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Violation patterns
# ---------------------------------------------------------------------------

CHECKS: list[tuple[str, str, re.Pattern[str]]] = [
    ("HARD", "raw ANSI escape", re.compile(r"\\x1b\[|\\033\[")),
    ("HARD", "print() with inline ANSI", re.compile(r'print\s*\(\s*f?"[^"]*\\x1b')),
    ("MIGRATE", "output.banner()", re.compile(r"\boutput\s*\.\s*banner\s*\(")),
    ("MIGRATE", "output.panel()", re.compile(r"\boutput\s*\.\s*panel\s*\(")),
    ("MIGRATE", "output.ok()", re.compile(r"\boutput\s*\.\s*ok\s*\(")),
    ("MIGRATE", "output.info()", re.compile(r"\boutput\s*\.\s*info\s*\(")),
    ("MIGRATE", "output.action()", re.compile(r"\boutput\s*\.\s*action\s*\(")),
    ("MIGRATE", "output.section()", re.compile(r"\boutput\s*\.\s*section\s*\(")),
    ("MIGRATE", "output.dry_run()", re.compile(r"\boutput\s*\.\s*dry_run\s*\(")),
    ("MIGRATE", "output.dry_run_complete()", re.compile(r"\boutput\s*\.\s*dry_run_complete\s*\(")),
    ("MIGRATE", "output.warning()", re.compile(r"\boutput\s*\.\s*warning\s*\(")),
    ("MIGRATE", "output.error()", re.compile(r"\boutput\s*\.\s*error\s*\(")),
    ("MIGRATE", "output.status()", re.compile(r"\boutput\s*\.\s*status\s*\(")),
    ("MIGRATE", "output.hint()", re.compile(r"\boutput\s*\.\s*hint\s*\(")),
    ("MIGRATE", "output.syntax()", re.compile(r"\boutput\s*\.\s*syntax\s*\(")),
    (
        "WARN",
        "import output",
        re.compile(r"from repo_release_tools import output\b|^import output\b", re.MULTILINE),
    ),
    (
        "WARN",
        "hardcoded column width",
        re.compile(r"\b(width|col_width|SECTION_WIDTH)\s*=\s*\d{2,}"),
    ),
]

SKIP_FILES = {"output.py"}  # the shim itself
SKIP_DIRS = {"__pycache__", ".venv", "venv", "dist", "build"}


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


def scan_file(path: Path) -> list[dict]:
    hits: list[dict] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return hits
    for lineno, line in enumerate(lines, 1):
        for severity, desc, pattern in CHECKS:
            if pattern.search(line):
                hits.append(
                    {
                        "file": str(path),
                        "line": lineno,
                        "severity": severity,
                        "description": desc,
                        "text": line.strip()[:120],
                    }
                )
                break  # one hit per line
    return hits


def scan_tree(root: Path) -> list[dict]:
    all_hits: list[dict] = []
    src = root / "src" / "repo_release_tools"
    for py in sorted(src.rglob("*.py")):
        if py.name in SKIP_FILES:
            continue
        if any(part in SKIP_DIRS for part in py.parts):
            continue
        all_hits.extend(scan_file(py))
    return all_hits


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def severity_order(s: str) -> int:
    return {"HARD": 0, "MIGRATE": 1, "WARN": 2}.get(s, 9)


def print_report(hits: list[dict], root: Path) -> None:
    if not hits:
        print("✔  No violations found — output layer is clean.")
        return

    by_file: dict[str, list[dict]] = {}
    for h in hits:
        by_file.setdefault(h["file"], []).append(h)

    hard = sum(1 for h in hits if h["severity"] == "HARD")
    migrate = sum(1 for h in hits if h["severity"] == "MIGRATE")
    warn = sum(1 for h in hits if h["severity"] == "WARN")

    print(f"rrt UX audit — {len(hits)} issue(s) in {len(by_file)} file(s)")
    print(f"  HARD={hard}  MIGRATE={migrate}  WARN={warn}")
    print()

    for path_str in sorted(
        by_file,
        key=lambda p: (
            severity_order(
                min(by_file[p], key=lambda h: severity_order(h["severity"]))["severity"]
            ),
            p,
        ),
    ):
        file_hits = sorted(by_file[path_str], key=lambda h: h["line"])
        rel = Path(path_str).relative_to(root) if Path(path_str).is_absolute() else Path(path_str)
        print(f"  {rel}")
        for h in file_hits:
            badge = {"HARD": "🚫", "MIGRATE": "⚠ ", "WARN": "ℹ "}.get(h["severity"], "  ")
            print(f"    {badge} line {h['line']:>4}  {h['description']}")
            print(f"           {h['text']}")
        print()

    if hard:
        print("🚫 HARD violations must be fixed before merge.")
    if migrate:
        print("⚠  MIGRATE violations: migrate output.py calls to ui/ on next touch.")
    if warn:
        print("ℹ  WARN: consider migrating the output import.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root (default: cwd)")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of text")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    hits = scan_tree(root)

    if args.json:
        print(json.dumps(hits, indent=2))
    else:
        print_report(hits, root)

    sys.exit(1 if any(h["severity"] == "HARD" for h in hits) else 0)


if __name__ == "__main__":
    main()
