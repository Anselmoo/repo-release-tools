---
name: rrt-ux-philosophy
description: >
  Long-term design philosophy, enforcement guide, and reference for the rrt
  (repo-release-tools) CLI. ALWAYS use this skill when working on any part of
  rrt that touches terminal output, visual design, the ui/ module, output.py,
  DryRunPrinter, git.py output, version_targets.py output, hooks.py output,
  dry-run rendering, help text formatting, error messages, syntax highlighting,
  color degradation, glyphs, progress bars, or the hook enforcement system.
  Trigger on: "rrt design", "rrt output", "ui/ module", "DryRunPrinter",
  "dry-run layout", "glyph vocabulary", "color levels", "rrt
  hooks", "terminal output", "print statement", "ANSI", "styling", "section
  separator", "rule()", "info()", "success()", "subtle()", "warning()", or
  any question about how rrt output should look or be structured. Also trigger
  when reviewing, writing, or refactoring ANY file under
  src/repo_release_tools/ that contains print statements or output calls.
  This is the authoritative source — consult it before writing a single line
  of output code.
---

# rrt CLI UX Philosophy

The rrt CLI has excellent building blocks — `DryRunPrinter`, `rule()`,
`success()`, `subtle()`, `GLYPHS`, syntax highlighting — but they are used
inconsistently. Some commands use the rich toolkit; others inline raw glyphs
and naked `print()` calls that bypass color degradation and NO_COLOR support.

**The core problem is not missing tools. It is that the tools are not used.**

---

## Quick navigation

| Question | Reference |
|---|---|
| Which function do I call for X? | §Function map below |
| How does DryRunPrinter work? | `references/dry-run-system.md` |
| How do I write a new command from scratch? | `references/dry-run-system.md` |
| How do I migrate old output.py calls? | `references/migration-guide.md` |
| How do I inline-highlight a path or version? | `references/syntax-highlighting.md` |
| How does color degrade across terminals? | `references/color-levels.md` |
| How do the enforcement hooks work? | `references/hooks.md` |

---

## Architecture: two layers, one correct

```
src/repo_release_tools/
├── output.py          ← LEGACY SHIM. Module docstring says "deprecated".
│                         git.py, hooks.py, version_targets.py still use it.
│                         Do NOT add anything here. Migrate callers on touch.
└── ui/
    ├── __init__.py    ← Single public surface — one import for all commands
    ├── messaging.py   ← DryRunPrinter ← THE MAIN TOOL commands must use
    │                     + error() render function
    ├── color.py       ← success/warning/error/info/subtle/heading/chrome
    │                     apply_style(), Style, THEMES, detect_color_level()
    ├── context.py     ← OutputContext(format, no_color, stream)
    ├── font.py        ← bold(), italic(), underline()
    ├── glyphs.py      ← GLYPHS singleton — all glyph access goes here
    ├── layout.py      ← rule(), section_line(), box(), align(), truncate(),
    │                     progress_bar(), sparkline(), terminal_width()
    ├── progress.py    ← ProgressLine, spinner_lines (extracted from output.py)
    ├── prompt.py      ← ask(), confirm()
    └── syntax.py      ← highlight_terminal() — built-in, no Pygments needed
```

**Five hard rules:**
1. All new output goes through `ui/` — never write `\x1b[` in command code.
2. Every command with a dry-run mode **must** use `DryRunPrinter`.
3. `output.py` is frozen — migrate its callers, never extend it.
4. All widths come from `terminal_width()` — never hard-code column counts.
5. Color is never the only carrier of meaning — every glyph degrades to ASCII.

**Standard import block for command files:**

```python
from repo_release_tools.ui import DryRunPrinter
from repo_release_tools.ui.color import success, info, warning, error as color_error, subtle
from repo_release_tools.ui.glyphs import GLYPHS
from repo_release_tools.ui.layout import rule, terminal_width
```

---

## Design principles

| # | Principle | Concrete rule |
|---|---|---|
| 1 | **Consistent grid** | No leading indent on command output — column 0, always |
| 2 | **Consistent elements** | Same `─` separator everywhere; same glyph per semantic role |
| 3 | **Clear communication** | Header → sections → footer, every command, every time |
| 4 | **Accessibility** | `NO_COLOR` / `--no-color` / non-TTY always produces clean plain text |
| 5 | **Responsiveness** | Widths from `terminal_width()` — never hard-coded numbers |

---

## Function map

If you reach for `print(f"  {glyph} text")` directly, stop and find the entry
below that covers your case.

### DryRunPrinter — the primary tool for all commands

Already exported from `repo_release_tools.ui`. Use it in every command that
has a `--dry-run` flag — and also in commands that don't, because its header/
section/footer structure makes output consistent regardless.

```python
from repo_release_tools.ui import DryRunPrinter

p = DryRunPrinter(args.dry_run)

# Opening block — always first
p.header("New branch", Base=base, Branch=branch_name, Title=commit_title)

# Section separator — before each logical step
p.section("Creating branch")

# Dry-run would-do lines
p.would_run(f"git checkout -b {branch_name}")
p.would_write("pyproject.toml", 'version = "2.0.0"')
p.would_install("repo-release-tools", "copilot-local", ".copilot/skills/…/SKILL.md")

# Live action / metadata lines
p.action("Uncommitted changes moved to the new branch.")
p.meta("Files changed", f"{len(status_lines)}")

# Per-step success or warning
p.ok(f"Installed repo-release-tools to copilot-local: {location}")
p.warn("Branch already exists. Resetting with --force.")

# Final line — always last
p.footer("Done. Branch 'fix/cli' created.")
```

| Method | Glyph | Color | Use when |
|---|---|---|---|
| `header(title, **kw)` | `✔` header + `→` kw | success / info | Opening block of every command |
| `section(name)` | `─────────` | rule | Before each logical step |
| `would_run(cmd)` | `⊖` | subtle | Dry-run: git command that would execute |
| `would_write(path, detail)` | `⊖` | subtle | Dry-run: file that would be written/updated |
| `would_install(name, target, loc)` | `⊖` | subtle | Dry-run: skill/file that would be installed |
| `action(msg)` | `→` | info | Live informational line during execution |
| `meta(key, value)` | `→` | info | Key: value metadata line |
| `ok(msg)` | `✔` | success | A step completed successfully |
| `warn(msg)` | `▲` | warning | Non-fatal issue |
| `footer(msg)` | `✔` + completion | success | Final summary + optional dry-run completion line |

### Standalone color functions

Use these outside of DryRunPrinter — in hooks, git.py, version_targets.py, etc.

```python
from repo_release_tools.ui.color import success, warning, error, info, subtle

f"{GLYPHS.bullet.ok} {success('Done.')}"
f"{GLYPHS.bullet.warning} {warning('Skipping…')}"
f"{GLYPHS.bullet.error} {error('Failed.')}"
f"{GLYPHS.arrow.right} {info('Branch: fix/cli')}"
subtle(f"{GLYPHS.bullet.skip} [dry-run] Would run: git checkout -b fix/cli")
```

### Layout

```python
from repo_release_tools.ui.layout import rule, terminal_width

W = terminal_width()
print(rule("Updating version strings", width=W))
print(rule(width=W))  # bare rule
```

Always pass `width=terminal_width()`. `DryRunPrinter.section()` does this for you.

### Glyphs — never hardcode Unicode, always use GLYPHS

```python
from repo_release_tools.ui.glyphs import GLYPHS

GLYPHS.bullet.ok        # ✔  (→ [OK] on legacy)
GLYPHS.bullet.skip      # ⊖  (→ [-] on legacy)
GLYPHS.bullet.warning   # ▲  (→ /!\ on legacy)
GLYPHS.bullet.error     # ✖  (→ [E] on legacy)
GLYPHS.bullet.dot       # •  (→ * on legacy)
GLYPHS.arrow.right      # →  (→ -> on legacy)
GLYPHS.typography.mdash # —  (→ -- on legacy)
GLYPHS.diff.added       # +
GLYPHS.diff.removed     # -
GLYPHS.diff.modified    # ~
```

### Progress

```python
from repo_release_tools.ui.progress import ProgressLine, spinner_lines

progress = ProgressLine(file=sys.stdout)
for i, target in enumerate(targets, 1):
    replace_version_in_file(target, str(new), dry_run=args.dry_run)
    progress.update_bar(i / len(targets))
progress.clear()  # always clear before printing the next line

with spinner_lines("Running lock command…", detail="$ uv lock -U", file=sys.stdout):
    git.run(group.lock_command, root, dry_run=False, …)
```

### Syntax highlighting

```python
from repo_release_tools.ui.syntax import highlight_terminal

print(highlight_terminal(toml_text, "toml"))
print(highlight_terminal(env_text,  "env"))
print(highlight_terminal(diff_text, "diff"))
print(highlight_terminal(json_text, "json"))
print(highlight_terminal(py_text,   "python"))
```

Never guard with `if supports_color()`. The function degrades to plain text
automatically when color is unavailable.

### Prompts

```python
from repo_release_tools.ui import ask, confirm

name = ask("Project name?", default="my-project")   # CI-safe
overwrite = confirm("Overwrite?", default=True)     # CI-safe
```

---

## Glyph vocabulary (dry-run output)

These are the only five glyphs used in command output. Using raw Unicode
outside this vocabulary breaks the consistency contract.

| Glyph | Role | DryRunPrinter | Manual |
|---|---|---|---|
| `✔` | Success / header | `header()`, `ok()`, `footer()` | `f"{GLYPHS.bullet.ok} {success(msg)}"` |
| `→` | Metadata / context | `header(**kw)`, `action()`, `meta()` | `f"{GLYPHS.arrow.right} {info(msg)}"` |
| `⊖` | Dry-run would-do | `would_run()`, `would_write()` | `subtle(f"{GLYPHS.bullet.skip} [dry-run] …")` |
| `▲` | Warning | `warn()` | `f"{GLYPHS.bullet.warning} {warning(msg)}"` |
| `✖` | Error | — | `f"{GLYPHS.bullet.error} {color_error(msg)}"` |

`─` section rules are rendered by `p.section(name)` or `rule(name, width=W)`.

---

## References index

Load these when the task requires depth beyond this file.

| File | Contents |
|---|---|
| `references/dry-run-system.md` | Full output spec, DryRunPrinter internals, per-subcommand annotated examples |
| `references/syntax-highlighting.md` | Block and inline highlighting rules with code examples |
| `references/migration-guide.md` | output.py → ui/ substitution table, files still needing migration |
| `references/color-levels.md` | detect_color_level() env var priority, degradation matrix |
| `references/hooks.md` | Hook architecture, PreToolUse write guard, UserPromptSubmit scanner |
