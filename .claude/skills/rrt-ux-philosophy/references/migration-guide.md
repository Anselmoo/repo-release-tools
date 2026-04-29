# output.py → ui/ Migration Guide

`output.py` is a legacy compatibility shim. Its module docstring says
"deprecated". No new code goes there. This page is the complete substitution
reference.

---

## Files still using output.py (priority order)

Migrate these when they are next touched. Each file currently imports `output`
at the top level:

| File | Main output.py calls used | Priority |
|---|---|---|
| `git.py` | `output.dry_run()`, `output.status()`, `output.ok()`, `output.warning()`, `output.error()` | HIGH — called by every command |
| `version_targets.py` | `output.dry_run()`, `output.ok()`, `output.warning()`, `output.status()` | HIGH — called by bump, ci-version |
| `hooks.py` | `output.warning()`, `output.status()`, `output.ok()` | MEDIUM |

Commands already migrated to `ui/` directly:
- `branch.py` ✔ (uses DryRunPrinter)
- `bump.py` ✔ (uses rule/success/subtle directly — DryRunPrinter partial)
- `ci_version.py` ✔
- `config_cmd.py` ✔
- `doctor.py` ✔
- `env_cmd.py` ✔
- `git_cmd.py` ✔ (uses _print_summary helper — DryRunPrinter partial)
- `init.py` ✔ (uses DryRunPrinter fully)
- `skill.py` ✔ (uses DryRunPrinter fully)

---

## Function substitution table

| `output.py` call | Correct `ui/` replacement |
|---|---|
| `output.banner(title, style="bold")` | `p.header(title)` — or `f"{GLYPHS.bullet.ok} {success(title)}"` |
| `output.panel(title, rows)` | `p.header(title, **{k:v for k,v in rows})` |
| `output.ok(msg)` | `f"{GLYPHS.bullet.ok} {success(msg)}"` — or `p.ok(msg)` |
| `output.info(msg)` | `f"{GLYPHS.arrow.right} {info(msg)}"` — or `p.action(msg)` |
| `output.action(msg)` | `f"{GLYPHS.arrow.right} {info(msg)}"` — or `p.action(msg)` |
| `output.section(title)` | `rule(title, width=terminal_width())` — or `p.section(title)` |
| `output.dry_run(msg)` | `subtle(f"{GLYPHS.bullet.skip} [dry-run] {msg}")` — or `p.would_run(cmd)` / `p.would_write(path)` |
| `output.dry_run_complete(msg)` | Automatic via `p.footer(…)` when `dry_run=True` |
| `output.warning(msg)` | `f"{GLYPHS.bullet.warning} {warning(msg)}"` — or `p.warn(msg)` |
| `output.error(msg)` | `f"{GLYPHS.bullet.error} {color_error(msg)}"` |
| `output.status(sym, msg, indent=N)` | `f"{'  '*N}{sym} {msg}"` directly |
| `output.hint(msg)` | `subtle(msg)` |
| `output.syntax(text, lang)` | `highlight_terminal(text, lang)` |
| `output.dry_run_complete(msg)` | `p.footer(…)` handles this automatically |
| `output.GLYPHS` | `from repo_release_tools.ui.glyphs import GLYPHS` |
| `output.highlight_terminal(text, lang)` | `from repo_release_tools.ui.syntax import highlight_terminal` |
| `output.ProgressLine(…)` | `from repo_release_tools.ui.progress import ProgressLine` |
| `output.spinner_lines(…)` | `from repo_release_tools.ui.progress import spinner_lines` |
| `output.OutputContext` | `from repo_release_tools.ui.context import OutputContext` |

---

## Import swap

Before:
```python
from repo_release_tools import output
# usage: output.ok(…), output.GLYPHS, output.dry_run(…)
```

After:
```python
from repo_release_tools.ui import DryRunPrinter
from repo_release_tools.ui.color import success, info, warning, error as color_error, subtle
from repo_release_tools.ui.glyphs import GLYPHS
from repo_release_tools.ui.layout import rule, terminal_width
from repo_release_tools.ui.syntax import highlight_terminal
from repo_release_tools.ui.progress import ProgressLine, spinner_lines
```

---

## Worked examples

### git.py: dry_run line

Before (`output.py`):
```python
print(output.dry_run(f"Would run: {pretty}"))
```

After (`ui/`):
```python
print(subtle(f"{GLYPHS.bullet.skip} [dry-run] Would run: {pretty}"))
```

Or with path/version emphasis:
```python
from repo_release_tools.ui.font import underline
from repo_release_tools.ui.color import apply_style
path_str = underline(str(path))
ver_str  = apply_style(f'"{new_version}"', bold=True, color="success")
print(subtle(f"{GLYPHS.bullet.skip} [dry-run] Would update {path_str}: version = {ver_str}"))
```

### git.py: status line ($ git checkout …)

Before:
```python
print(output.status("$", pretty))
```

After (git.py is the right place to keep this pattern since it's a raw
subprocess runner, not a command):
```python
print(f"  $ {pretty}")
# or keep using output.status() since git.py still imports output
# and will be migrated separately
```

### hooks.py: emit_failure

Before:
```python
print(output.warning(title, indent=0), file=sys.stderr)
for detail in details:
    print(output.status(output.GLYPHS.bullet.dot, detail), file=sys.stderr)
```

After:
```python
print(f"{GLYPHS.bullet.warning} {warning(title)}", file=sys.stderr)
for detail in details:
    print(f"  {GLYPHS.bullet.dot} {detail}", file=sys.stderr)
```

### bump.py: completing the DryRunPrinter migration

The bump command uses `DryRunPrinter` for its header but then switches to
`rule()` + direct `subtle()` calls for sections. This is acceptable as an
intermediate state. The full migration is:

```python
# Replace:
print(rule("Updating version strings", width=terminal_width()))
# With:
p.section("Updating version strings")

# Replace:
print(subtle(f"{GLYPHS.bullet.skip} [dry-run] Would promote [Unreleased]…"))
# With:
p.would_write(str(path), f"promote [Unreleased] to [{version}]")

# Replace the footer block:
print(f"{GLYPHS.bullet.ok} {success(done_msg)}")
print(f"  {GLYPHS.bullet.dot} Base branch: {base}")
print(subtle(f"{GLYPHS.bullet.skip} [dry-run] complete …"))
# With:
p.footer(done_msg)
# (p.footer() handles the blank line and dry-run completion automatically)
```

---

## Migration checklist

When migrating a command file:

- [ ] Replace `from repo_release_tools import output` with `ui/` imports
- [ ] Replace every `output.*` call using the table above
- [ ] Introduce `DryRunPrinter` for the header/section/footer structure
- [ ] Replace hard-coded widths with `terminal_width()`
- [ ] Test `NO_COLOR=1 uv run rrt <subcommand> --dry-run` → plain text only
- [ ] Run `uv run pytest tests/ -v`
