# Color Level Degradation

`detect_color_level()` in `ui/color.py` is the single source of truth for
what ANSI codes may be emitted. All `ui/` functions call it internally.
Command code never calls it directly — just use `success()`, `info()`, etc.
and degradation is automatic.

---

## The four levels

| Level | Terminal | ANSI codes used |
|---|---|---|
| `"none"` | NO_COLOR, dumb, non-TTY, Win32 without WT_SESSION | Plain text only |
| `"standard"` | Most Unix terminals | `\x1b[30–37m`, `\x1b[1m`, `\x1b[3m`, `\x1b[4m` |
| `"256"` | xterm-256color | `\x1b[38;5;Nm` |
| `"truecolor"` | Modern terminals (iTerm, Windows Terminal, etc.) | `\x1b[38;2;R;G;Bm` |

---

## Detection priority (from ui/color.py, in order)

1. `NO_COLOR` set to any value → `"none"`
2. `RRT_COLOR` override:
   - `0` / `off` / `false` / `none` → `"none"`
   - `1` / `on` / `true` / `standard` → `"standard"`
   - `256` / `8bit` → `"256"`
   - `24bit` / `truecolor` → `"truecolor"`
3. `TERM=dumb` → `"none"`
4. `COLORTERM=truecolor` or `COLORTERM=24bit` → `"truecolor"`
5. `TERM` matches `*256color*` → `"256"`
6. Win32 without `WT_SESSION` → `"none"`
7. Default → `"standard"`

The `--no-color` CLI flag sets `NO_COLOR=1` in the environment before any
output is rendered, which triggers rule 1.

---

## Semantic function degradation

| Function | `"truecolor"/"256"` | `"standard"` | `"none"` |
|---|---|---|---|
| `success(text)` | green bold | `\x1b[32;1m` | plain |
| `warning(text)` | yellow bold | `\x1b[33;1m` | plain |
| `error(text)` | red bold | `\x1b[31;1m` | plain |
| `info(text)` | cyan italic | `\x1b[36;3m` | plain |
| `subtle(text)` | dim | `\x1b[2m` | plain |
| `heading(text)` | gold bold | `\x1b[33;1m` | plain |
| `chrome(text)` | gold dim | `\x1b[33;2m` | plain |
| `bold(text)` | bold | `\x1b[1m` | plain |
| `underline(text)` | underline | `\x1b[4m` | plain |

---

## Glyph degradation (from ui/glyphs.py)

`IS_LEGACY_TERMINAL` is `True` on Win32, `TERM=dumb`, or when `NO_COLOR` is
set. When true, all glyphs return their ASCII fallback:

| Glyph | Unicode | ASCII fallback |
|---|---|---|
| `GLYPHS.bullet.ok` | ✔ | [OK] |
| `GLYPHS.bullet.skip` | ⊖ | [-] |
| `GLYPHS.bullet.warning` | ▲ | /!\ |
| `GLYPHS.bullet.error` | ✖ | [E] |
| `GLYPHS.bullet.dot` | • | * |
| `GLYPHS.arrow.right` | → | -> |
| `GLYPHS.typography.mdash` | — | -- |
| Box corners (┌┐└┘) | Unicode box | + |
| Box lines (─│) | Unicode | -\| |

---

## Rule: never gate on color in command code

```python
# WRONG — manual color check in command code
if os.environ.get("NO_COLOR"):
    print("Done.")
else:
    print(success("Done."))

# CORRECT — just call the semantic function
print(f"{GLYPHS.bullet.ok} {success('Done.')}")
# or
p.ok("Done.")
```

The functions handle degradation. Command code never needs to check.

---

## Theme system

Three built-in themes exist in `ui/color.py`:

```python
from repo_release_tools.ui.color import set_theme

set_theme("default")      # green/yellow/red/cyan/gold
set_theme("monochrome")   # bold/underline/italic only, no color
set_theme("pastel")       # softer palette for light-background terminals
```

`set_theme()` replaces the `_NAMED_STYLES` registry. All semantic functions
(`success()`, `info()`, etc.) pick up the new styles automatically.
