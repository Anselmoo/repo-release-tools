---
name: rrt-ux-design
description: >
  Enforce and guide CLI UX design for the rrt (repo-release-tools) project.
  Use this skill whenever you are: adding new terminal output to a subcommand,
  changing help text formatting, adding error or status messages, refactoring
  any file under src/repo_release_tools/ui/ or output.py, writing tests in
  test_user_experience_simulator.py, wiring a new function from the ui/ module,
  or checking whether a proposed output change respects NO_COLOR / non-TTY
  fallback. Also use it when reviewing output-related code for design consistency,
  or when asked how to render progress, sparklines, boxes, rules, or emphasis
  in the rrt CLI. Trigger even if the user only mentions "styling", "colors",
  "terminal", "ANSI", "help text", "output", "dry-run", or "fragmented" in a rrt
  context. ALWAYS use this skill when touching output.py or any ui/ module,
  even for small changes.
---

# rrt CLI UX Design Skill

This skill keeps all terminal output in `rrt` consistent, accessible, and
maintainable. Every output decision is rooted in five design principles and
channelled through **one** module so that tests, accessibility, and future
maintainability stay manageable.

---

## ⚠️ Architecture Problem: Two Output Layers in Conflict

The codebase currently has two competing output layers that must be resolved:

| Layer | Location | Status |
|---|---|---|
| **Legacy** | `src/repo_release_tools/output.py` | Active, inconsistent, being refactored away |
| **Target** | `src/repo_release_tools/ui/` | Correct architecture, not yet fully wired |

**The PR #37 situation:** Commands in the PR moved from `output.panel()`/`output.banner()` to flat `output.ok()` / `output.info()` calls — this made things *more* fragmented, not less. The correct fix is to route everything through `ui/` and deprecate `output.py`.

### Migration Rule
```
output.banner()  →  from ui import bold + rule()
output.panel()   →  from ui import box()
output.ok()      →  from ui import success()
output.info()    →  from ui import info() / subtle()
output.action()  →  from ui import info()
output.section() →  from ui import section_line() / rule()
output.dry_run() →  DryRunPrinter (see below)
output.status()  →  from ui import apply_style() with glyph
```

**Never add new functions to `output.py`.** Every new output goes in `ui/`.

---

## The Five Design Principles

| Principle | Implementation rule |
|---|---|
| **Consistent grid** | 2-space indent, fixed column offsets, thin-rule section separators |
| **Consistent UI elements** | Same separator char (`─`) everywhere; same column width per context |
| **Clear communication** | Short descriptions, collapsed synopsis in help text, examples always visible |
| **Accessibility** | Respect `NO_COLOR`, `--no-color`, and non-TTY detection; never use color as the *only* carrier of meaning |
| **Responsiveness** | All widths via `layout.terminal_width()`; truncate to terminal, never wrap mid-token |

---

## Module Quick Reference

All terminal output goes through `src/repo_release_tools/ui/`. Never write raw
ANSI escapes (`\x1b[...`) in subcommand files.

```
src/repo_release_tools/ui/
├── __init__.py        # re-exports the full public surface (one import)
├── color.py           # ANSI codes, detect_color_level(), supports_color(),
│                      #   apply(), apply_style(), error/warning/info/success/subtle
├── context.py         # OutputContext(format, no_color, stream)
├── font.py            # bold(), italic(), underline(), emphasize(), Emphasis
├── glyphs.py          # GLYPHS registry, display_width(), pad_right()
├── layout.py          # rule(), section_line(), box(), align(), truncate(),
│                      #   progress_bar(), sparkline(), terminal_width()
├── prompt.py          # ask(), confirm()
├── rich_bridge.py     # optional Rich integration
├── syntax.py          # highlight_terminal() — Pygments bridge with graceful fallback
└── tui.py             # Textual stub (optional dep)
```

Single import pattern for commands:

```python
from repo_release_tools.ui import (
    bold, error, info, rule, section_line, truncate, success, warning, subtle,
)
```

---

## Dry-Run Output Design System

The dry-run output (images from `branch new`, `bump major`, `skill install`) is the most
visible UX surface. It must be **completely consistent** across all subcommands.

### Glyph Vocabulary (use ONLY these)

| Glyph | Meaning | Function | Example |
|---|---|---|---|
| `✓` | Success / header | `success()` | `✓ [DRY RUN] New branch` |
| `→` | Metadata / context line | `info()` | `→ Branch: fix/cli` |
| `⊙` | Dry-run would-do line | `subtle()` + dim | `⊙ [dry-run] Would run: git checkout -b` |
| `•` | List item / bullet | plain `subtle()` | `• Base branch: <current>` |
| `─` | Section separator | `rule()` / `section_line()` | `── Creating branch ──────` |

**Never mix** `→` for both metadata and dry-run actions. The table above is the rule.

### Header Block (every subcommand must start with this)

```
✓ [DRY RUN] New branch          ← success(), bold, uppercase title
→ Branch: fix/cli               ← info(), italic, key: value
→ Base: <current>               ← info(), italic
→ Title: fix: cli               ← info(), italic
                                ← blank line
```

Implementation:
```python
from repo_release_tools.ui import success, info

title = "[DRY RUN] New branch" if args.dry_run else "New branch"
print(success(title))
print(info(f"Branch: {branch_name}"))
print(info(f"Base: {base}"))
print(info(f"Title: {commit_title}"))
print()
```

### Section Block

```
── Creating branch ──────────────────────────────────────────────────────
⊙ [dry-run] Would run: git checkout -b fix/cli
→ Would move uncommitted changes to the new branch.

→ Files changed: 18 | Staged: 0 | Unstaged: 18
── Changed files ────────────────────────────────────────────────────────
  M src/repo_release_tools/cli.py
```

Implementation:
```python
from repo_release_tools.ui import rule, subtle, info, terminal_width

W = terminal_width()
print(rule("Creating branch", width=W))
print(subtle(f"⊙ [dry-run] Would run: git checkout -b {branch_name}"))
```

### Footer Block (every subcommand must end with this)

```
✓ Done. Suggested commit title: fix: cli

⊙ [dry-run] complete – no changes made    ← only in dry-run mode
```

```python
print(success(f"Done. Suggested commit title: {commit_title}"))
print()
if args.dry_run:
    print(subtle("⊙ [dry-run] complete – no changes made"))
```

### DryRunPrinter — The Canonical Pattern

All subcommands should use a `DryRunPrinter` class or equivalent to guarantee
consistent formatting. The pattern:

```python
class DryRunPrinter:
    """Formats dry-run output consistently across all subcommands."""

    def __init__(self, dry_run: bool) -> None:
        self.dry_run = dry_run
        self._width = terminal_width()

    def header(self, title: str, **metadata: str) -> None:
        label = f"[DRY RUN] {title}" if self.dry_run else title
        print(success(label))
        for key, value in metadata.items():
            print(info(f"{key}: {value}"))
        print()

    def section(self, name: str) -> None:
        print(rule(name, width=self._width))

    def would_run(self, cmd: str) -> None:
        print(subtle(f"⊙ [dry-run] Would run: {cmd}"))

    def would_write(self, path: str, detail: str = "") -> None:
        suffix = f": {detail}" if detail else ""
        print(subtle(f"⊙ [dry-run] Would update {path}{suffix}"))

    def action(self, message: str) -> None:
        print(info(message))

    def footer(self, message: str) -> None:
        print(success(message))
        print()
        if self.dry_run:
            print(subtle("⊙ [dry-run] complete – no changes made"))
```

---

## Syntax Highlighting

Syntax highlighting must be applied **consistently** in these contexts:

| Context | Language | Function |
|---|---|---|
| `config` command output | `toml` | `highlight_terminal(text, "toml")` |
| `env` command output | `env`/`ini` | `highlight_terminal(text, "env")` |
| `--changelog-mode generate` output | `markdown` | `highlight_terminal(text, "md")` |
| Git commit messages in dry-run | `text` | `bold()` for the commit string |
| Version strings in dry-run | inline | `apply_style(version, bold=True, color="success")` |
| File paths in dry-run would-do lines | inline | `underline(path)` |

### Applying inline highlighting in dry-run output

Instead of:
```
⊙ [dry-run] Would update /path/to/pyproject.toml: version = "2.0.0"
```

Do:
```python
from repo_release_tools.ui import subtle, underline, apply_style
from repo_release_tools.ui.syntax import highlight_terminal

path_str = underline(str(path))
ver_str  = apply_style(f'"{new_version}"', bold=True, color="success")
print(subtle(f"⊙ [dry-run] Would update {path_str}: version = {ver_str}"))
```

This produces: `⊙ [dry-run] Would update` **`/path/to/pyproject.toml`**`: version =` **`"2.0.0"`**

### Changelog preview block

```python
# Render the would-be changelog diff with syntax highlighting
from repo_release_tools.ui.syntax import highlight_terminal
from repo_release_tools.ui import rule, terminal_width, subtle

W = terminal_width()
print(rule("Updating changelog", width=W))
raw_preview = build_changelog_preview(...)
# indent each line with "> " and highlight as markdown
for line in raw_preview.splitlines():
    print(subtle("  > ") + highlight_terminal(line, "md").rstrip())
```

---

## Function Selection Guide

### Semantic messaging
```python
error("message")     # red + bold  — use for failures
warning("message")   # yellow + bold — use for non-fatal issues
info("message")      # cyan + italic — use for metadata / context lines
success("message")   # green + bold — use for positive outcomes / headers
subtle("message")    # dim — use for dry-run would-do lines and de-emphasised text
```

### Emphasis (inline, inside longer messages)
```python
bold("text")        # \x1b[1m when color is on, plain when off
italic("text")      # \x1b[3m ...
underline("text")   # \x1b[4m ... — use for file paths
apply_style("text", bold=True, color="success")
apply_style("text", fg=(255, 100, 0), bold=True)
```

### Layout
```python
rule("Section name", width=W)    # ── Section name ─────────────────
rule(width=W)                    # ─────────────────────────────────
section_line("Build", body_width=60)

align("text", width=N, mode="left")
box("content", title="Panel", style="rounded")
truncate("very long text", width=terminal_width() - 4)
```

### Progress & sparklines
```python
progress_bar(0.6, width=20, label="Updating files")
# → [████████████░░░░░░░░] 60% Updating files

sparkline([1.0, 3.0, 2.0, 5.0, 4.0])
# → ▁▄▂█▅
```

### Interactive prompts
```python
ask("Project name?", default="my-project")   # returns str
confirm("Overwrite config?", default=True)   # returns bool
```

### Syntax highlighting
```python
from repo_release_tools.ui.syntax import highlight_terminal
highlight_terminal(toml_text, "toml")
```

Returns plain text when Pygments is not installed or terminal is non-TTY.

---

## OutputContext — The Single Source of Truth

```python
from repo_release_tools.ui.context import OutputContext
import sys

ctx = OutputContext(format="text", no_color=False, stream=sys.stdout)

if not ctx.no_color and supports_color(ctx.stream):
    print(bold("Result"), file=ctx.stream)
else:
    print("Result", file=ctx.stream)

if ctx.is_json():
    print(json.dumps(data))
```

---

## Color Level Degradation

`detect_color_level()` returns one of four levels:

| Level | Meaning |
|---|---|
| `"none"` | NO_COLOR, dumb terminal, or non-TTY — plain text only |
| `"standard"` | Basic 8-color ANSI |
| `"256"` | xterm 256-color |
| `"truecolor"` | 24-bit RGB |

Env var priority: `NO_COLOR` → `RRT_COLOR` → `TERM=dumb` → `COLORTERM=truecolor` → `TERM=*-256color`

---

## Three-Layer Enforcement Architecture

### Layer 1 — pytest hook
`tests/conftest.py` → `pytest_collection_finish` → validates entrypoints against
`test_user_experience_simulator.py` docstring. Fails before tests run if diverged.

### Layer 2 — agent hook
`.github/hooks/rrt-ux-design.json` fires on `UserPromptSubmit`. Injects system
message when UI keywords detected. Never blocks (always exits 0).

### Layer 3 — contributor rules
1. **All terminal output through `ui/`** — No `print(f"\x1b[...")` in subcommand code.
2. **No new functions in `output.py`** — It is deprecated; migrate existing callers to `ui/`.
3. **New `ui/` function → new test class** — Add `TestMyFeature` to `test_user_experience_simulator.py`.
4. **Run tests before PR** — `uv run pytest tests/test_user_experience_simulator.py -v`

---

## Test Contract

Every new `ui/` function needs:
1. A test class in `tests/test_user_experience_simulator.py`
2. A line in that file's module docstring under the matching entrypoint section

| Class | Module | Key assertions |
|---|---|---|
| `TestColors` | `color` | ANSI present with color, plain without, NO_COLOR=1 disables |
| `TestSyntaxHighlight` | `syntax` | Plain text when `color_level=none` or Pygments absent |
| `TestProgressBar` | `layout` | `█`/`░` counts, `%` label, ascii fallback with `TERM=dumb` |
| `TestSparkline` | `layout` | Min→`▁`, max→`█`, empty→`""`, ascii mode, width truncation |
| `TestPrompts` | `prompt` | Default returned on non-TTY for both `ask` and `confirm` |
| `TestLayout` | `layout` | `rule` fills width, `align` aligns, `box` has corners, `section_line` prefix |
| `TestEmphasis` | `font` | SGR 1/3/4 present with color; plain without |
| `TestApplyStyle` | `color` | Combined bold+colour; truecolor escapes; downsampled in standard |
| `TestTruncation` | `layout` | Ellipsis appended; respects display_width; zero-width → empty |
| `TestColorLevels` | `color` | Each env var → expected level string |
| `TestOutputContext` | `context` | Default format, `is_json()`, `no_color`, stream stored |
| `TestMessaging` | `color` | ANSI wrapping when color on; plain text when off |
| `TestDryRunPrinter` | `layout` + `color` | header/section/would_run/footer consistency; NO_COLOR path |

```bash
uv run pytest tests/test_user_experience_simulator.py -v
```

---

## Common Patterns

### New subcommand with dry-run output

```python
from repo_release_tools.ui import success, info, subtle, rule, terminal_width

def run(args):
    W = terminal_width()
    label = "[DRY RUN] My Command" if args.dry_run else "My Command"
    print(success(label))
    print(info(f"Target: {args.target}"))
    print()

    print(rule("Doing work", width=W))
    if args.dry_run:
        print(subtle(f"⊙ [dry-run] Would run: my-tool --flag"))
    else:
        do_actual_work()

    print(success("Done."))
    print()
    if args.dry_run:
        print(subtle("⊙ [dry-run] complete – no changes made"))
```

### Config / TOML output with syntax highlighting

```python
from repo_release_tools.ui.syntax import highlight_terminal
from repo_release_tools.ui import rule, terminal_width

W = terminal_width()
print(rule("Version groups", width=W))
raw = pathlib.Path("pyproject.toml").read_text()
print(highlight_terminal(raw, "toml"))
```

### Progress bar in a loop

```python
from repo_release_tools.ui import progress_bar
import sys

for i, item in enumerate(items, 1):
    process(item)
    bar = progress_bar(i / len(items), width=20, label=item.name)
    sys.stdout.write(f"\r{bar}")
    sys.stdout.flush()
sys.stdout.write("\n")
```

---

## Research Hooks

- `fetch_webpage` for Python docs / terminal standards:
  `https://docs.python.org/3/library/shutil.html#shutil.get_terminal_size`
- `mcp_ai-agent-guid_agent-memory` to persist patterns across sessions
- `https://no-color.org/` and `https://bixense.com/clicolors/` for env var specs
