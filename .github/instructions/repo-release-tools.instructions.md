---
name: repo-release-tools CLI and coverage guidance
description: "Apply workspace-specific guidance for repo-release-tools CLI/UI improvements, coverage-aware changes, and research tool usage."
applyTo: "src/**/*.py"
---

This repository enforces Claude-session policy through `.claude/settings.json` and
the hook scripts in `.claude/hooks/`, alongside the `uv run pytest -q -m "not runtime"`
workflow.

## Hook layout

All active Claude hook registrations live in the single source of truth:
**`.claude/settings.json`**.

All active Claude hook scripts in this repository live under **`.claude/hooks/`**.
Do not create parallel activation files in `.github/hooks/`, and do not document
stale `.github/hooks/*.py` paths as if they were live.

Current hook registrations in `.claude/settings.json`:

| Event | Matcher | Script | Purpose |
|---|---|---|---|
| `UserPromptSubmit` | `""` | `.claude/hooks/rrt_ux_guard.py` | Advisory UX contract reminder |
| `PreToolUse` | `Bash` | `.claude/hooks/check_push_coverage.py` | Block `git push` below 85.71% coverage |
| `PreToolUse` | `Write\|Edit\|…` | `.claude/hooks/rrt_ux_write_guard.py` | Block raw ANSI writes in `src/` |
| `PostToolUse` | `""` | `.claude/hooks/refresh_coverage_baseline.py` | Auto-refresh baseline after pytest |
| `Stop` | `""` | `.claude/hooks/completeness_guard.py` | Block completion when required hooks, agents, or skills are missing |
| `Stop` | `""` | `.claude/hooks/coverage_non_regression.py` | Block completion on coverage regression |

## Source-of-truth boundaries

- **`.claude/settings.json` + `.claude/hooks/`** are the canonical Claude
  runtime automation surface for this repo.
- **`.github/agents/` + `.github/skills/`** are the committed source-owned
  agent/skill definitions shipped with the wheel.
- **`.github/instructions/`** and **`.github/copilot-instructions.md`** must
  mirror that Claude surface instead of describing a parallel hook layout.
- **`.github/skills/`** remains the committed source tree for repo-owned skill
  definitions and the Copilot local install target; install targets such as
  **`.claude/skills/`** are generated runtime locations, not the source-of-truth
  files to edit in this repository.
- When loading bundled hook scripts for installer commands, resolve
  source-owned files from **`.github/hooks/`** first and keep legacy
  `repo_release_tools.assets/hooks/*` paths as fallbacks only; do not assume
  `src/repo_release_tools/assets/hooks/*` exists in the checkout.
- When reading wheel-shipped files from `[tool.uv.build-backend].data`, account
  for uv_build's flattened install layout: `.github/skills/<name>/...` is
  installed under `purelib/<name>/...`, and `.github/agents/...` under the
  `data` scheme root (agent files directly under `data/`), while `.github/hooks/...`
  lands under the `headers` scheme root. These files are not nested beneath
  `.github/` prefixes after installation.
- When a Docker image installs the project with `pip install .` or `uv build`,
  keep the `Dockerfile` aligned with `[tool.uv.build-backend].source-include` by
  copying every source tree that the backend walks into the image before the
  install step; for this repo that means `.github/skills/`, `.github/agents/`,
  and `.github/hooks/` alongside `src/`.
- When updating skill installers, keep Copilot mapped to **`.github/skills/`**
  for workspace installs and **`~/.copilot/skills/`** for user-global installs.
  Keep Claude/Codex/Gemini mapped to their matching local and global roots:
  **`.claude/skills/`** / **`~/.claude/skills/`**, **`.codex/skills/`** /
  **`~/.codex/skills/`**, and **`.gemini/skills/`** / **`~/.gemini/skills/`**.
- When updating installer-generated Copilot hook registrations, write managed
  hook JSON under **`.github/hooks/*.json`** for workspace installs and
  **`~/.copilot/hooks/*.json`** for user-global installs. Do not invent or
  document a repo-local **`.github/settings.json`** hook location.

When working in `repo-release-tools`, follow these rules:

- Prefer low-risk, Python-only CLI/UI improvements using existing modules.
- Do not add new runtime dependencies for command-line output or parser UX work.
- For UI and help enhancements, focus on `src/repo_release_tools/cli.py` and `src/repo_release_tools/ui/*`.
- Keep package `__init__.py` files as facades only: re-exports, tiny aliases, or package metadata. Do not place primary implementation bodies in `__init__.py`.
- When two or more modules belong to the same domain, or one domain module mixes distinct responsibilities, group them into a semantic package (`docs/`, `config/`, `eol/`, `version/`, `workflow/`, `integrations/`) instead of leaving them flat at `src/repo_release_tools/`.
- After moving code into a semantic package, update source imports and tests to the canonical package path and delete obsolete root modules in the same change. Do not leave permanent flat-module duplicates behind.
- Inside a domain package, split logic by role (`core.py`, `data.py`, `detect.py`, `targets.py`, `semver.py`) rather than creating a new oversized sibling module.
- Anchor-based file injection lives in `src/repo_release_tools/tools/inject.py` — import from `repo_release_tools.tools.inject`, not from `repo_release_tools.inject` (old path removed).
- Prefer `match` for closed-set dispatch helpers such as hook surface selection or managed config-path resolution; keep simple guard clauses for validation and command flow.
- In `src/repo_release_tools/docs/publisher.py`, never add YAML frontmatter to content rendered for targets that use `anchor_id` (for example `docs/index.md` and `README.md`); anchored targets must render body-only fragments.
- Author docs shared blocks inline in `[tool.rrt.docs.shared_blocks].content` under `pyproject.toml` or `.rrt.toml`; do not add new scripts or template files for doc footers, headers, or shared text fragments.
- When adjusting banner or other fixed-width UI art, validate the final rendered string and normalize every line to a shared display width before asserting geometry; do not compare the raw template lines directly.
- Use `fetch_webpage` and `mcp_github_search_code` when researching external examples, issue comments, or PR context before changing behavior.
- Avoid proposing or creating PRs that lower test coverage; if a change is necessary and coverage drops, explain the coverage gap and add tests to restore it.
- The repo currently reports low coverage in `src/repo_release_tools/ui/syntax.py`.
- Use existing hook behavior as a guardrail: coverage below 85.71% should be treated as a blocker unless the user explicitly approves a follow-on test expansion.
- When making CLI errors friendlier, preserve argparse semantics and exit codes while improving help text, suggestions, and examples.
- When you add or rename a top-level `rrt` subcommand, update the `Affected entrypoints` docstring block in `tests/test_user_experience_simulator.py` in the same change so the UX contract stays aligned with the live CLI surface.
- When you add a new top-level `rrt` subcommand, update `docs/commands/rrt-cli.md` and the dedicated command doc page in the same change so the published docs stay aligned with the CLI.
- Persist preferences and follow-up context in repo-scoped memory when they are specific to this repository's workflow.
- Keep the hook-registration table in sync with `.claude/settings.json`; if the active hook path changes, update the documented path in this file immediately so contributors are not sent to a stale location.


## Canonical UI import pattern

All command files and modules **must** use a single consolidated import block from
the public `ui` package. Do **not** import directly from submodules:

```python
# ✅ Correct — one import block from the public surface
from repo_release_tools.ui import (
    DryRunPrinter,
    GLYPHS,
    bold,
    error,
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

Add extra helpers such as `highlight_terminal`, `subtle`, `fmt_cmd`, or
`ProgressLine` from the same public `repo_release_tools.ui` surface when needed.

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

## Coverage baseline refresh policy

- `.claude/hooks/refresh_coverage_baseline.py` auto-refreshes `.claude/coverage-baseline.json` after successful `pytest` tool runs.
- Auto-refresh is intentionally non-blocking and no-op on malformed payloads, failed runs, or missing `coverage.xml`.
- Keep `.claude/hooks/check_push_coverage.py` as the policy floor guardrail (85.71%) even when baseline refresh is active.
- `.claude/hooks/coverage_non_regression.py` remains the completion-time regression gate.
- Operational caveat: always-on refresh can move baseline up or down as test scope changes; prefer stricter/manual mode if governance requires explicit approvals.
