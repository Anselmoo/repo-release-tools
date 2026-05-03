#!/usr/bin/env python3
"""rrt-ux-design agent hook — UserPromptSubmit.

Reads the UserPromptSubmit JSON from stdin. Does two things:

1. Keyword scan — when the prompt mentions terminal-output topics, injects a
   reminder of the rrt UX contract as additionalContext.

2. File-scope scan — looks at any Python file paths mentioned in the prompt
   and checks for known violations already present in those files, then
   includes a targeted report so Claude sees exactly what needs fixing before
   it starts writing.

Exit codes:
  0  — continue (with or without injected context)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Keyword trigger — decides whether to inject the UX contract reminder
# ---------------------------------------------------------------------------

_UI_KEYWORDS = re.compile(
    r"\b("
    r"color|colour|ansi|escape|styling|style|no.color|output|print|terminal"
    r"|tty|bold|italic|underline|dim|progress|sparkline|prompt|highlight"
    r"|syntax|rule|box|align|truncate|section.line|messaging|error|warning"
    r"|info|success|subtle|apply_style|OutputContext|dry.run|dry_run"
    r")\b"
    r"|ui/|_ui/|ui\\.py|color\\.py|layout\\.py|font\\.py|syntax\\.py"
    r"|output\\.py|glyphs\\.py",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Static violation patterns — things that must never appear in command files
# ---------------------------------------------------------------------------

# Each entry: (pattern, severity, human-readable description)
_VIOLATIONS: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(r"\\x1b\[|\\033\[|\x1b\["),
        "HARD",
        "raw ANSI escape — use ui/ functions instead",
    ),
    (
        re.compile(r'\bprint\s*\(\s*f?".*\\x1b'),
        "HARD",
        "print() with inline ANSI escape",
    ),
    (
        re.compile(r"\boutput\s*\.\s*(banner|panel)\s*\("),
        "MIGRATE",
        "output.banner()/output.panel() is deprecated — use ui/box() or success()+rule()",
    ),
    (
        re.compile(r"\boutput\s*\.\s*(ok|info|action|section|dry_run)\s*\("),
        "MIGRATE",
        "output.ok/info/action/section/dry_run() — migrate to ui/ equivalents",
    ),
    (
        re.compile(r"from repo_release_tools import output\b"),
        "WARN",
        "importing output.py — prefer 'from repo_release_tools.ui import …'",
    ),
    (
        re.compile(r"import output\b"),
        "WARN",
        "importing output.py directly — prefer 'from repo_release_tools.ui import …'",
    ),
]

_SEVERITY_LABEL = {
    "HARD": "🚫 HARD VIOLATION",
    "MIGRATE": "⚠️  MIGRATE",
    "WARN": "ℹ️  WARN",
}

# ---------------------------------------------------------------------------
# File path extraction from a prompt string
# ---------------------------------------------------------------------------

_PY_PATH = re.compile(
    r"(?:src/repo_release_tools|tests)/[\w/]+\.py"
    r"|(?:commands|ui)/[\w]+\.py"
    r"|output\.py",
)


def _extract_paths(prompt: str) -> list[Path]:
    """Return existing Python files mentioned in the prompt."""
    raw = _PY_PATH.findall(prompt)
    found: list[Path] = []
    root = Path.cwd()
    for p in raw:
        candidate = root / p
        if candidate.exists():
            found.append(candidate)
    return found


# ---------------------------------------------------------------------------
# File scanner
# ---------------------------------------------------------------------------


def _scan_file(path: Path) -> list[tuple[int, str, str, str]]:
    """Return list of (lineno, severity, description, line_text) for violations."""
    hits: list[tuple[int, str, str, str]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return hits
    for i, line in enumerate(lines, 1):
        for pattern, severity, desc in _VIOLATIONS:
            if pattern.search(line):
                hits.append((i, severity, desc, line.strip()))
                break  # one report per line
    return hits


def _format_scan_report(paths: list[Path]) -> str:
    sections: list[str] = []
    total = 0
    for path in paths:
        hits = _scan_file(path)
        if not hits:
            continue
        total += len(hits)
        lines = [f"  {path}:"]
        for lineno, severity, desc, text in hits:
            label = _SEVERITY_LABEL.get(severity, severity)
            lines.append(f"    line {lineno:>4}  {label}")
            lines.append(f"              rule: {desc}")
            lines.append(f"              code: {text[:120]}")
        sections.append("\n".join(lines))

    if not sections:
        return ""

    header = (
        f"[rrt-ux-contract] Static scan found {total} violation(s) in {len(sections)} file(s):\n"
    )
    return header + "\n".join(sections)


# ---------------------------------------------------------------------------
# Contract reminder (injected whenever UI keywords are present)
# ---------------------------------------------------------------------------

_CONTRACT_REMINDER = """\
[rrt-ux-contract] Terminal output rules — read before writing any output code:

ARCHITECTURE
  output.py is DEPRECATED. All new output goes through repo_release_tools.ui.
  Migration map:
    output.banner()        → success() + rule()
    output.panel()         → box()
    output.ok()            → success()
    output.info()          → info()
    output.action()        → info()
    output.section()       → rule() / section_line()
    output.dry_run()       → subtle() + "⊙ [dry-run] …" prefix

GLYPH VOCABULARY (use only these in dry-run output)
  ✓  success/header line   → success()
  →  metadata / context    → info()
  ⊙  dry-run would-do      → subtle()
  •  list item             → subtle()
  ─  section separator     → rule()

DRY-RUN STRUCTURE (every subcommand must follow this exactly)
  ✓ [DRY RUN] <Title>      ← success(title)
  → Key: value             ← info(f"Key: {value}")
                           ← blank line
  ── Section ──────────    ← rule("Section", width=terminal_width())
  ⊙ [dry-run] Would run: … ← subtle(f"⊙ [dry-run] Would run: {cmd}")
  ✓ Done. …                ← success("Done. …")
                           ← blank line
  ⊙ [dry-run] complete …  ← subtle("⊙ [dry-run] complete – no changes made")

SYNTAX HIGHLIGHTING
  File paths inline        → underline(path)
  Version strings inline   → apply_style(ver, bold=True, color="success")
  TOML/env blocks          → highlight_terminal(text, "toml")
  Changelog preview lines  → highlight_terminal(line, "md")

HARD RULES
  Never write raw \\x1b[...] escapes in subcommand code.
  Never add new functions to output.py.
  Every new ui/ function needs a TestXxx class in test_user_experience_simulator.py.
  All widths via terminal_width() — never hard-code column counts.
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Main entry point for the rrt-ux-design guard."""
    payload = json.loads(sys.stdin.read())
    prompt: str = payload.get("prompt", "") or ""

    parts: list[str] = []

    # 1. Static scan on any mentioned files
    paths = _extract_paths(prompt)
    if paths:
        report = _format_scan_report(paths)
        if report:
            parts.append(report)

    # 2. Keyword-triggered contract reminder
    if _UI_KEYWORDS.search(prompt):
        parts.append(_CONTRACT_REMINDER)

    if parts:
        additional_context = "\n\n".join(parts)
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptSubmit",
                        "additionalContext": additional_context,
                    }
                }
            )
        )

    # Always exit 0 — this hook never blocks.


if __name__ == "__main__":
    main()
