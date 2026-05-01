---
name: repo-release-tools CLI and coverage guidance
description: "Apply workspace-specific guidance for repo-release-tools CLI/UI improvements, coverage-aware changes, and research tool usage."
applyTo: "src/**/*.py"
---

This repository enforces coverage and CI policies through `.github/hooks/check_push_coverage.py` and the `uv run pytest -q -m "not runtime"` workflow.

When working in `repo-release-tools`, follow these rules:

- Prefer low-risk, Python-only CLI/UI improvements using existing modules.
- Do not add new runtime dependencies for command-line output or parser UX work.
- For UI and help enhancements, focus on `src/repo_release_tools/cli.py` and `src/repo_release_tools/ui/*`.
- Use `fetch_webpage` and `mcp_github_search_code` when researching external examples, issue comments, or PR context before changing behavior.
- Avoid proposing or creating PRs that lower test coverage; if a change is necessary and coverage drops, explain the coverage gap and add tests to restore it.
- The repo currently reports low coverage in `src/repo_release_tools/ui/syntax.py`.
- Use existing hook behavior as a guardrail: coverage below 85.71% should be treated as a blocker unless the user explicitly approves a follow-on test expansion.
- When making CLI errors friendlier, preserve argparse semantics and exit codes while improving help text, suggestions, and examples.
- Persist preferences and follow-up context in repo-scoped memory when they are specific to this repository's workflow.


## Canonical UI import pattern

All command files and modules **must** use a single consolidated import block from the public `ui` package. Do **not** import directly from submodules:

```python
# ✅ Correct — one import block from the public surface
from repo_release_tools.ui import (
    DryRunPrinter,
    GLYPHS,
    error as color_error,
    highlight_terminal,
    info,
    rule,
    success,
    terminal_width,
    warning,
)

# ❌ Wrong — fragmented submodule imports
from repo_release_tools.ui.color import success, info, warning, error as color_error
from repo_release_tools.ui.glyphs import GLYPHS
from repo_release_tools.ui.layout import rule, terminal_width
from repo_release_tools.ui.syntax import highlight_terminal
```

Additional helpers available via `from repo_release_tools.ui import (...)`:
- `ProgressLine`, `spinner_lines` — live terminal progress
- `subtle`, `heading`, `bold`, `italic`, `underline` — font/color helpers
- `fmt_path(p)` — underline a path (degrades on NO_COLOR)
- `fmt_version(v)` — success-color for version strings
- `fmt_cmd(c)` — shell-highlight a command
- `cli_error` — full error renderer (vs `error` which is the color function)
- `banner`, `panel`, `section`, `hyperlink` — layout blocks
- `json_highlight`, `pretty_print`, `diff_highlight` — syntax helpers
- `ask`, `confirm` — safe prompts


## Enforcing no raw print() usage

Raw `print(...)` calls are **only allowed inside `src/repo_release_tools/ui/`**. All other output must go through the UI helpers.

Quick checks and remediation:

```bash
python3 scripts/check_no_raw_prints.py
```

- Use Serena's search to inspect code in the repo:

```python
serena_agent.search_for_pattern(substring_pattern="print\\(", relative_path="src/repo_release_tools")
```

- Migration pattern:
  - Replace `print()` with `p = DryRunPrinter(dry_run=args.dry_run)` and use `p.header()`, `p.section()`, `p.ok()`, `p.warn()`, `p.footer()`.
  - For in-place progress, prefer `ProgressLine`.
  - Preserve machine-readable stdout exactly (use `sys.stdout.write(version + "\n")`).

CI enforcement:

- The `scripts/check_no_raw_prints.py` checker enforces this rule — include it in CI (pre-commit or workflow) to prevent regressions.

## DryRunPrinter method priorities

When in doubt which method to call, use this decision table (see `rrt-ux-philosophy` skill for the full API contract):

| Situation | Method |
|---|---|
| Opening a command | `p.header(title, **kw)` |
| Logical step separator | `p.section(name)` |
| Git command that would run | `p.would_run(cmd)` |
| File that would be written | `p.would_write(path, detail)` |
| Skill/asset that would be installed | `p.would_install(name, target, loc)` |
| Narrative progress line | `p.action(msg)` |
| Key: value metadata | `p.meta(key, val)` |
| File status (added/modified/removed/…) | `p.file_entry(kind, path)` |
| Bullet list item | `p.list_item(text)` |
| Step success | `p.ok(msg)` |
| Non-fatal caution | `p.warn(msg)` |
| Closing a command | `p.footer(msg)` |
| Inline error (fatal) | `p.line(msg, ok=False, stream=sys.stderr)` |
| **Never use** | `p.line(msg)` without `ok=False` — banned in new code |
