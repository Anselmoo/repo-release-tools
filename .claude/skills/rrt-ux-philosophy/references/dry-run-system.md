# Dry-Run Output System

This is the canonical specification for how every rrt subcommand structures
its output. Deviation from this spec is a bug, not a style choice.

---

## Why this matters

The screenshots that prompted this skill showed commands with five different
output styles in the same session — mixed box-drawing panels, flat arrow
lines, raw Unicode glyphs, inconsistent indentation, and dry-run markers with
no consistent prefix. The `DryRunPrinter` class in `ui/messaging.py` was
written specifically to solve this. The problem is it was only used in the
refactored commands (`branch.py`, `init.py`, `skill.py`) while `bump.py`,
`git_cmd.py`, and others still used `output.panel()` / `output.banner()` or
ad-hoc `print()` calls.

**Every command must use DryRunPrinter.**

---

## The three-block structure

Every command output follows this exact structure:

```
BLOCK 1 — HEADER       ← p.header(…)       always present
BLOCK 2 — SECTION(S)   ← p.section(…) + step output
BLOCK 3 — FOOTER       ← p.footer(…)       always present
```

### Block 1 — Header

```
✔ [DRY RUN] New branch
→ Base: <current>
→ Branch: fix/cli
→ Title: fix: cli
                         ← blank line (DryRunPrinter.header() prints this)
```

```python
p = DryRunPrinter(args.dry_run)
p.header("New branch", Base=base, Branch=branch_name, Title=commit_title)
# → prints blank line automatically
```

Rules:
- Title is `[DRY RUN] <Verb Noun>` when dry-run; just `<Verb Noun>` otherwise.
- DryRunPrinter prepends `[DRY RUN]` for you when `dry_run=True`.
- Every relevant input parameter becomes a `→ Key: value` line.
- The trailing blank line is printed automatically by `header()`.
- Never use `output.panel()` or `output.banner()` for this block.

### Block 2 — Section

```
── Creating branch ────────────────────────────────────────────────────────
⊖ [dry-run] Would run: git checkout -b fix/cli
→ Would move uncommitted changes to the new branch.
                         ← blank line before next section
```

```python
p.section("Creating branch")
p.would_run(f"git checkout -b {branch_name}")
p.action("Would move uncommitted changes to the new branch.")
print()
```

Rules:
- `p.section(name)` calls `rule(name, width=terminal_width())` automatically.
- Dry-run lines use `would_run()`, `would_write()`, `would_install()`.
- Live action lines use `p.action()` (cyan `→`).
- Print a blank line between sections manually — DryRunPrinter does not auto-space sections.

### Block 3 — Footer

```
✔ Done. Suggested commit title: fix: cli

⊖ [dry-run] complete — no changes made     ← only when dry_run=True
```

```python
p.footer("Done. Suggested commit title: {commit_title}")
# DryRunPrinter.footer() prints blank line + dry-run completion automatically
```

Rules:
- `footer()` always prints a blank line before the completion line.
- The `⊖ [dry-run] complete —` line is printed automatically when `dry_run=True`.
- Nothing after `footer()` — it is always the last thing printed.

---

## DryRunPrinter internals (from ui/messaging.py)

```python
class DryRunPrinter:
    def __init__(self, dry_run: bool) -> None:
        self.dry_run = dry_run
        self._width = terminal_width()

    def header(self, title: str, **metadata: str) -> None:
        label = f"[DRY RUN] {title}" if self.dry_run else title
        print(f"{GLYPHS.bullet.ok} {success(label)}")
        for key, value in metadata.items():
            print(f"{GLYPHS.arrow.right} {info(f'{key}: {value}')}")
        print()

    def section(self, name: str) -> None:
        print(rule(name, width=self._width))

    def would_run(self, cmd: str) -> None:
        print(subtle(f"{GLYPHS.bullet.skip} [dry-run] Would run: {cmd}"))

    def would_write(self, path: str, detail: str = "") -> None:
        suffix = f": {detail}" if detail else ""
        print(subtle(f"{GLYPHS.bullet.skip} [dry-run] Would update {path}{suffix}"))

    def would_install(self, name: str, target: str, location: str) -> None:
        print(subtle(f"{GLYPHS.bullet.skip} [dry-run] Would install {name} to {target}: {location}"))

    def action(self, message: str) -> None:
        print(f"{GLYPHS.arrow.right} {info(message)}")

    def meta(self, key: str, value: str) -> None:
        print(f"{GLYPHS.arrow.right} {info(f'{key}: {value}')}")

    def ok(self, message: str) -> None:
        print(f"{GLYPHS.bullet.ok} {success(message)}")

    def warn(self, message: str) -> None:
        print(f"{GLYPHS.bullet.warning} {warning(message)}")

    def footer(self, message: str) -> None:
        print(f"{GLYPHS.bullet.ok} {success(message)}")
        print()
        if self.dry_run:
            print(subtle(f"{GLYPHS.bullet.skip} [dry-run] complete {GLYPHS.typography.mdash} no changes made"))
```

---

## Per-subcommand annotated examples

### rrt branch new / --dry-run

```
✔ [DRY RUN] New branch          ← p.header("New branch", Base=…, Branch=…, Title=…)
→ Base: <current>
→ Branch: fix/cli
→ Title: fix: cli
                                 ← header() prints this blank line

── Creating branch ──────────   ← p.section("Creating branch")
⊖ [dry-run] Would run: git checkout -b fix/cli   ← p.would_run(…)
→ Would move uncommitted changes to the new branch.  ← p.action(…)

→ Files changed: 18 | Staged: 0 | Unstaged: 18   ← p.action(…) or print(info(…))
── Changed files ────────────   ← p.section("Changed files")
  M src/repo_release_tools/cli.py    ← plain print, 2-space indent
  M src/repo_release_tools/commands/branch.py

✔ Done. Suggested commit title: fix: cli   ← p.footer(…)

⊖ [dry-run] complete — no changes made    ← footer() prints this when dry_run=True
```

### rrt bump major --dry-run

```
✔ [DRY RUN] Version bump         ← p.header("Version bump", Current=…, Branch=…, Base=…)
→ Current: 1.1.0 → 2.0.0
→ Branch: release/v2.0.0
→ Base: <current>

── Updating version strings ──   ← rule("Updating version strings", width=W)
⊖ [dry-run] Would update /path/pyproject.toml: version = "2.0.0"   ← p.would_write(…)
⊖ [dry-run] Would update /path/__init__.py: version = "2.0.0"

── Updating doc pins ─────────   ← rule(…)
⊖ [dry-run] Would update /path/docs/github-action.md: pin = "2.0.0"

── Updating changelog ────────
⊖ [dry-run] Would prepend to /path/CHANGELOG.md:
    > ## [2.0.0] – 2026-04-29
    >
    > _No notable changes recorded._

── Refreshing lockfiles ──────
⊖ [dry-run] Would run: uv lock -U               ← p.would_run(…)

── Git ───────────────────────
⊖ [dry-run] Would run: git checkout -b release/v2.0.0
⊖ [dry-run] Would run: git add pyproject.toml …
⊖ [dry-run] Would run: git commit -m chore: bump version to v2.0.0

✔ Done. Branch 'release/v2.0.0' created with commit: 'chore: bump version to v2.0.0'
• Base branch: <current>

⊖ [dry-run] complete — no files were modified
```

Note: `bump.py` uses `rule()` directly instead of `DryRunPrinter.section()` because
it was partially migrated. Both approaches produce identical visual output —
the difference is that `rule()` doesn't track `_width` automatically. When
completing the migration, switch to `DryRunPrinter` throughout.

### rrt git commit --dry-run

```
✔ [DRY RUN] Commit               ← _print_summary(title, rows) — migrate to p.header()
→ Branch: fix/cli-tool-enhancment
→ Mode: commit only
→ Subject: fix!: hap

── Git ───────────────────────   ← rule("Git", width=W)
⊖ [dry-run] Would run: git commit -m fix!: hap

✔ Done. Created commit: 'fix!: hap'
⊖ [dry-run] complete — no changes made
```

`_print_summary()` in `git_cmd.py` pre-dates `DryRunPrinter` and should be
replaced with `p.header()` when that file is migrated.

---

## Changelog preview rendering

When showing what would be prepended to CHANGELOG.md, render each line with
a `>` prefix and apply markdown syntax highlighting:

```python
from repo_release_tools.ui.syntax import highlight_terminal

print(p.would_write(str(path)))
for line in section_text.splitlines()[:PREVIEW_LINES]:
    highlighted = highlight_terminal(line, "md").rstrip()
    print(f"    > {highlighted}")
if len(section_text.splitlines()) > PREVIEW_LINES:
    print(f"    > {GLYPHS.typography.ellipsis}")
```

---

## Version strings and paths inline in would-do lines

When a would-do line mentions a file path or version string inline, apply
emphasis so they stand out:

```python
from repo_release_tools.ui.font import underline
from repo_release_tools.ui.color import apply_style, subtle
from repo_release_tools.ui.glyphs import GLYPHS

path_str = underline(str(target.path))
ver_str  = apply_style(f'"{new_version}"', bold=True, color="success")
print(subtle(f"{GLYPHS.bullet.skip} [dry-run] Would update {path_str}: version = {ver_str}"))
```

This makes the path underlined and the version bold-green inside a dim line.
`version_targets.py` uses plain `output.dry_run(…)` today — this is the
correct replacement.
