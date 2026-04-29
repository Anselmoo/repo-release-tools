# Syntax Highlighting Reference

All syntax highlighting goes through `highlight_terminal()` from
`repo_release_tools.ui.syntax`. It is pure Python — no Pygments, no optional
deps. It degrades to plain text on non-TTY, NO_COLOR, or unknown language.

---

## Where to apply highlighting

| Context | Language | Call |
|---|---|---|
| `config --raw` TOML output | `"toml"` | `highlight_terminal(text, "toml")` |
| `init` dry-run preview (TOML) | `"toml"` | `highlight_terminal(section_text, "toml")` |
| `init` dry-run preview (JSON) | `"json"` | `highlight_terminal(preview, "json")` |
| `env` command output | `"env"` | `highlight_terminal(env_block, "env")` |
| Changelog section preview | `"md"` | per-line (see below) |
| `git diff` output | `"diff"` | `highlight_terminal(raw_diff, "diff")` |
| Inline file path in would-do | — | `underline(str(path))` |
| Inline version string in would-do | — | `apply_style(ver, bold=True, color="success")` |

---

## Block highlighting

Use for multi-line content rendered as its own section:

```python
from repo_release_tools.ui.syntax import highlight_terminal
from repo_release_tools.ui.layout import rule, terminal_width

W = terminal_width()
print(rule("Configuration", width=W))
raw = pathlib.Path("pyproject.toml").read_text()
print(highlight_terminal(raw, "toml"))
```

---

## Changelog preview (per-line markdown)

When showing a changelog section preview in dry-run mode, render line by line:

```python
from repo_release_tools.ui.syntax import highlight_terminal
from repo_release_tools.ui.glyphs import GLYPHS

for line in section_text.splitlines()[:PREVIEW_LINES]:
    highlighted = highlight_terminal(line, "md").rstrip()
    print(f"    > {highlighted}")
if len(section_text.splitlines()) > PREVIEW_LINES:
    print(f"    > {GLYPHS.typography.ellipsis}")
```

This is the current pattern in `bump.py`. The `"md"` language key is not yet
in `_RULES` in `syntax.py` — add it by mapping markdown headings/bullets to
the `"section"` and `"key"` token types.

---

## Inline highlighting in would-do lines

For `would_write` lines in `version_targets.py`, apply emphasis inline:

```python
from repo_release_tools.ui.font import underline
from repo_release_tools.ui.color import apply_style, subtle
from repo_release_tools.ui.glyphs import GLYPHS

path_str = underline(str(target.path))
ver_str  = apply_style(f'"{new_version}"', bold=True, color="success")
print(subtle(f"{GLYPHS.bullet.skip} [dry-run] Would update {path_str}: version = {ver_str}"))
```

This produces a dim line where the path is underlined and the version is
bold+green — two layers of meaning without needing extra glyphs.

---

## Supported language tokens

`syntax.py` supports these languages natively:

| Key | Tokens highlighted |
|---|---|
| `"toml"` | comments, `[sections]`, keys, strings, booleans, numbers |
| `"env"` | comments, `KEY=`, `=value` |
| `"python"` / `"py"` | comments, strings, booleans/None, keywords |
| `"json"` | keys, string values, booleans/null, numbers |
| `"diff"` | `@@` hunks, `---/+++` headers, `+` added, `-` removed |

---

## Degradation — never guard

`highlight_terminal()` checks `supports_color()` and `detect_color_level()`
internally. Never wrap it in a color check:

```python
# WRONG
if supports_color():
    print(highlight_terminal(text, "toml"))
else:
    print(text)

# CORRECT
print(highlight_terminal(text, "toml"))   # handles degradation automatically
```
