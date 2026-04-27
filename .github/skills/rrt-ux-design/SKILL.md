---
name: rrt-ux-design
description: >
  Enforce and guide CLI UX design for the rrt (repo-release-tools) project.
  Use this skill whenever you are: adding new terminal output to a subcommand,
  changing help text formatting, adding error or status messages, refactoring
  any file under src/repo_release_tools/ui/, writing tests in
  test_user_experience_simulator.py, wiring a new function from the ui/ module,
  or checking whether a proposed output change respects NO_COLOR / non-TTY
  fallback. Also use it when reviewing output-related code for design consistency,
  or when asked how to render progress, sparklines, boxes, rules, or emphasis
  in the rrt CLI. Trigger even if the user only mentions "styling", "colors",
  "terminal", "ANSI", "help text", or "output" in a rrt context.
---

# rrt CLI UX Design Skill

This skill keeps all terminal output in `rrt` consistent, accessible, and
maintainable. Every output decision is rooted in five design principles and
channelled through a single module layer so that tests, accessibility, and
future maintainability stay manageable.

---

## The Five Design Principles

| Principle | Implementation rule |
|---|---|
| **Design principles** | Consistent grid: 2-space indent, fixed column offsets, thin-rule section separators |
| **Consistent UI elements** | Same separator character (`─`) everywhere; same column width per context |
| **Clear communication** | Short descriptions, collapsed synopsis in help text, examples always visible |
| **Accessibility** | Respect `NO_COLOR`, `--no-color`, and non-TTY detection; never use color as the *only* carrier of meaning |
| **Responsiveness** | All widths via `layout.terminal_width()`; truncate to terminal, never wrap mid-token |

When adding output, check each principle before finalising.

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
    bold, error, info, rule, section_line, truncate, success, warning,
)
```

---

## OutputContext — The Single Source of Truth

`OutputContext` is the control knob threaded through commands. Build it once at
startup, pass it everywhere. This is what makes the test matrix tractable: set
`no_color=True` and every rendering function becomes deterministic.

```python
from repo_release_tools.ui.context import OutputContext
import sys

ctx = OutputContext(format="text", no_color=False, stream=sys.stdout)

# Gate all styled output on the context:
if not ctx.no_color and supports_color(ctx.stream):
    print(bold("Result"), file=ctx.stream)
else:
    print("Result", file=ctx.stream)

if ctx.is_json():
    print(json.dumps(data))
```

---

## Function Selection Guide

### Semantic messaging
Use these for user-facing status lines. They apply the theme colour and
degrade to plain text automatically when `supports_color()` is False.

```python
error("message")     # red + bold  — use for failures
warning("message")   # yellow + bold — use for non-fatal issues
info("message")      # cyan + italic — use for neutral notes
success("message")   # green + bold — use for positive outcomes
subtle("message")    # dim — use for de-emphasised secondary text
```

### Emphasis
For inline emphasis inside longer messages:

```python
bold("text")        # \x1b[1m when color is on, plain when off
italic("text")      # \x1b[3m ...
underline("text")   # \x1b[4m ...
```

For combined styles (e.g. bold + custom colour):

```python
apply_style("text", bold=True, color="success")
apply_style("text", fg=(255, 100, 0), bold=True)   # truecolor / 256 / 8 auto-mapped
```

### Layout
Section rules in help text and panel output:

```python
rule("Section name", width=ctx_width)    # ── Section name ─────────────────
rule(width=ctx_width)                    # ─────────────────────────────────
section_line("Build", body_width=60)     # ── Build ──────────────────────
```

Two-column table (help text, key-value panels):

```python
align("text", width=N, mode="left")      # pad right
align("text", width=N, mode="center")    # center
align("text", width=N, mode="right")     # pad left
```

Bordered blocks (doctor, config):

```python
box("content", title="Panel", style="rounded")
box(["line 1", "line 2"], style="single")
```

Truncation (single-line display of branch names, paths):

```python
truncate("very long text", width=terminal_width() - 4)
```

### Progress & sparklines
Shown in `bump` (multi-file) and `git` status summary:

```python
progress_bar(0.6, width=20, label="Updating files")
# → [████████████░░░░░░░░] 60% Updating files

sparkline([1.0, 3.0, 2.0, 5.0, 4.0])
# → ▁▄▂█▅
```

### Interactive prompts
Used in `init` and `skill`:

```python
ask("Project name?", default="my-project")   # returns str
confirm("Overwrite config?", default=True)   # returns bool
```

Both fall back gracefully to their default in non-interactive (CI) contexts.

### Syntax highlighting
Used in `config` and `env` output for TOML / env values:

```python
from repo_release_tools.ui.syntax import highlight_terminal
highlight_terminal(toml_text, "toml")
```

Returns plain text when Pygments is not installed or the terminal is non-TTY.

---

## Color Level Degradation

`detect_color_level()` returns one of four string levels:

| Level | Meaning | ANSI codes used |
|---|---|---|
| `"none"` | No color (NO_COLOR, dumb, non-TTY) | Plain text only |
| `"standard"` | Basic 8-color ANSI (most terminals) | `\x1b[30–37m` |
| `"256"` | xterm 256-color | `\x1b[38;5;Nm` |
| `"truecolor"` | 24-bit RGB | `\x1b[38;2;R;G;Bm` |

Env vars that control detection (in priority order):
1. `NO_COLOR` — any value → `"none"`
2. `RRT_COLOR` — override: `0/off/none` → `"none"`, `truecolor` → `"truecolor"`, etc.
3. `TERM=dumb` → `"none"`
4. `COLORTERM=truecolor` or `COLORTERM=24bit` → `"truecolor"`
5. `TERM=*-256color` → `"256"`

---

## Three-Layer Enforcement Architecture

The UX contract is enforced at three layers. All three must stay in sync.

### Layer 1 — pytest hook (strongest: machine-checked contract)

`tests/conftest.py` implements `pytest_collection_finish`. It parses the
module docstring of `test_user_experience_simulator.py` to extract the
"Affected entrypoints" list and compares it against the live `ArgumentParser`
subcommand names from `cli.build_parser()`. If they diverge, the suite fails
before a single test runs with exit code 2:

```
[rrt-ux-contract] Entrypoint mismatch — fix before running tests.
  CLI subcommands missing from the test docstring: audit
  → Add them under 'Affected entrypoints' in tests/test_user_experience_simulator.py
```

**What triggers it:** adding a new subcommand to `cli.build_parser()` without
updating the docstring, or removing a subcommand without updating the
docstring.

### Layer 2 — agent hook (context injection)

`.github/hooks/rrt-ux-design.json` fires on every `UserPromptSubmit` event.
The companion script `.github/hooks/rrt_ux_guard.py` reads the user prompt,
and when it detects UI-related keywords (`color`, `output`, `ANSI`, `bold`,
`progress`, `ui/`, etc.) it injects a `systemMessage` that recaps the contract
rules before the agent takes any action. The hook never blocks (always exits 0).

### Layer 3 — contributor instructions (human-readable contract)

Three rules for every contributor adding CLI output:
1. **All terminal output through `ui/`** — No `print(f"\x1b[...")` in subcommand code.
2. **New `ui/` function → new test class** — Add a `TestMyFeature` class to
   `tests/test_user_experience_simulator.py` and a line under the matching
   section in that file's docstring.
3. **Run tests before opening a PR** — `uv run pytest tests/test_user_experience_simulator.py -v`

---

## Test Contract

Every new `ui/` function needs:
1. A test class in `tests/test_user_experience_simulator.py` (`TestMyFeature`)
2. A line in that file's module docstring under the matching entrypoint section

The test classes and what they verify:

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

Run the UX simulator tests:

```bash
uv run pytest tests/test_user_experience_simulator.py -v
```

---

## Research Hooks

When you need stdlib examples or want to look up terminal escape codes:

- Use `fetch_webpage` to fetch Python docs or terminal standards pages (e.g.
  `https://docs.python.org/3/library/shutil.html#shutil.get_terminal_size`).
- Use `mcp_ai-agent-guid_agent-memory` to persist patterns you discover across
  sessions — e.g. the exact `detect_color_level()` env-var priority order, or
  recurring patterns from `conftest.py` that affect UI tests.

Example: look up the `COLORTERM` environment variable spec:

```
fetch_webpage(["https://no-color.org/", "https://bixense.com/clicolors/"],
              query="COLORTERM truecolor terminal detection")
```

---

## Common Patterns

### Adding a status line to a new subcommand

```python
# In commands/mycommand.py
from repo_release_tools.ui import success, error, rule, terminal_width

def run(args, ctx):
    width = terminal_width()
    print(rule("My Command", width=width))
    try:
        result = do_work()
        print(success(f"Done: {result}"))
    except MyError as exc:
        print(error(str(exc)))
        raise SystemExit(1)
```

### Adding a progress bar to a loop

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

### Syntax-highlighted config dump

```python
from repo_release_tools.ui.syntax import highlight_terminal
import pathlib

raw = pathlib.Path("pyproject.toml").read_text()
print(highlight_terminal(raw, "toml"))
```

# rrt CLI UX Design Skill

This skill keeps all terminal output in `rrt` consistent, accessible, and
maintainable. Every output decision is rooted in five design principles and
channelled through a single module layer so that tests, accessibility, and
future maintainability stay manageable.

---

## The Five Design Principles

| Principle | Implementation rule |
|---|---|
| **Design principles** | Consistent grid: 2-space indent, fixed column offsets, thin-rule section separators |
| **Consistent UI elements** | Same separator character (`─`) everywhere; same column width per context |
| **Clear communication** | Short descriptions, collapsed synopsis in help text, examples always visible |
| **Accessibility** | Respect `NO_COLOR`, `--no-color`, and non-TTY detection; never use color as the *only* carrier of meaning |
| **Responsiveness** | All widths via `layout.terminal_width()`; truncate to terminal, never wrap mid-token |

When adding output, check each principle before finalising.

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
    bold, error, info, rule, section_line, truncate, success, warning,
)
```

---

## Function Selection Guide

### Semantic messaging
Use these for user-facing status lines. They apply the theme colour and
degrade to plain text automatically when `supports_color()` is False.

```python
error("message")     # red + bold  — use for failures
warning("message")   # yellow + bold — use for non-fatal issues
info("message")      # cyan + italic — use for neutral notes
success("message")   # green + bold — use for positive outcomes
subtle("message")    # dim — use for de-emphasised secondary text
```

### Emphasis
For inline emphasis inside longer messages:

```python
bold("text")        # \x1b[1m when color is on, plain when off
italic("text")      # \x1b[3m ...
underline("text")   # \x1b[4m ...
```

For combined styles (e.g. bold + custom colour):

```python
apply_style("text", bold=True, color="success")
apply_style("text", fg=(255, 100, 0), bold=True)   # truecolor / 256 / 8 auto-mapped
```

### Layout
Section rules in help text and panel output:

```python
rule("Section name", width=ctx_width)    # ── Section name ─────────────────
rule(width=ctx_width)                    # ─────────────────────────────────
section_line("Build", body_width=60)     # ── Build ──────────────────────
```

Two-column table (help text, key-value panels):

```python
align("text", width=N, mode="left")      # pad right
align("text", width=N, mode="center")    # center
align("text", width=N, mode="right")     # pad left
```

Bordered blocks (doctor, config):

```python
box("content", title="Panel", style="rounded")
box(["line 1", "line 2"], style="single")
```

Truncation (single-line display of branch names, paths):

```python
truncate("very long text", width=terminal_width() - 4)
```

### Progress & sparklines
Shown in `bump` (multi-file) and `git` status summary:

```python
progress_bar(0.6, width=20, label="Updating files")
# → [████████████░░░░░░░░] 60% Updating files

sparkline([1.0, 3.0, 2.0, 5.0, 4.0])
# → ▁▄▂█▅
```

### Interactive prompts
Used in `init` and `skill`:

```python
ask("Project name?", default="my-project")   # returns str
confirm("Overwrite config?", default=True)   # returns bool
```

Both fall back gracefully to their default in non-interactive (CI) contexts.

### Syntax highlighting
Used in `config` and `env` output for TOML / env values:

```python
from repo_release_tools.ui.syntax import highlight_terminal
highlight_terminal(toml_text, "toml")
```

Returns plain text when Pygments is not installed or the terminal is non-TTY.

---

## OutputContext

`OutputContext` is the control knob threaded through commands. It is not yet
used as a direct parameter by most `ui/` primitives (they read env globals
directly), but it should be checked in command-level code to decide whether to
emit decorated vs. plain output:

```python
from repo_release_tools.ui.context import OutputContext

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

`detect_color_level()` returns one of four string levels:

| Level | Meaning | ANSI codes used |
|---|---|---|
| `"none"` | No color (NO_COLOR, dumb, non-TTY) | Plain text only |
| `"standard"` | Basic 8-color ANSI (most terminals) | `\x1b[30–37m` |
| `"256"` | xterm 256-color | `\x1b[38;5;Nm` |
| `"truecolor"` | 24-bit RGB | `\x1b[38;2;R;G;Bm` |

Env vars that control detection (in priority order):
1. `NO_COLOR` — any value → `"none"`
2. `RRT_COLOR` — override: `0/off/none` → `"none"`, `truecolor` → `"truecolor"`, etc.
3. `TERM=dumb` → `"none"`
4. `COLORTERM=truecolor` or `COLORTERM=24bit` → `"truecolor"`
5. `TERM=*-256color` → `"256"`

---

## Test Contract

Every new `ui/` function needs:
1. A test class in `tests/test_user_experience_simulator.py` (`TestMyFeature`)
2. A line in that file's module docstring under the matching entrypoint section

The test classes and what they verify:

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

Run the UX simulator tests:

```bash
uv run pytest tests/test_user_experience_simulator.py -v
```

---

## Design Enforcement Rules

1. **All terminal output through `ui/`** — No `print(f"\x1b[...")` in subcommand code.
2. **New `ui/` function → new test class** — And a line in the docstring's entrypoints list.
3. **Always test the NO_COLOR / non-TTY path** — Every public output function must degrade gracefully.
4. **Width from `terminal_width()`** — Never hard-code column widths in subcommand code.

---

## Research Hooks

When you need stdlib examples or want to look up terminal escape codes:

- Use `fetch_webpage` to fetch Python docs or terminal standards pages (e.g.
  `https://docs.python.org/3/library/shutil.html#shutil.get_terminal_size`).
- Use `mcp_ai-agent-guid_agent-memory` to persist patterns you discover across
  sessions — e.g. the exact `detect_color_level()` env-var priority order, or
  recurring patterns from `conftest.py` that affect UI tests.

Example: look up the `COLORTERM` environment variable spec:

```
fetch_webpage(["https://no-color.org/", "https://bixense.com/clicolors/"],
              query="COLORTERM truecolor terminal detection")
```

---

## Common Patterns

### Adding a status line to a new subcommand

```python
# In commands/mycommand.py
from repo_release_tools.ui import success, error, rule, terminal_width

def run(args, ctx):
    width = terminal_width()
    print(rule("My Command", width=width))
    try:
        result = do_work()
        print(success(f"Done: {result}"))
    except MyError as exc:
        print(error(str(exc)))
        raise SystemExit(1)
```

### Adding a progress bar to a loop

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

### Syntax-highlighted config dump

```python
from repo_release_tools.ui.syntax import highlight_terminal
import tomllib

raw = pathlib.Path("pyproject.toml").read_text()
print(highlight_terminal(raw, "toml"))
```
