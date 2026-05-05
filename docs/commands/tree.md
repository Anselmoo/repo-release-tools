# Project tree

`rrt tree` renders a deterministic project tree with Git-aware filtering and
multiple output modes for terminal use, docs, and copy/paste workflows.

## Formats

- `classic` — platform-aware tree connectors
- `ascii` — forced ASCII connectors
- `markdown` — nested markdown bullets
- `rich` — Rich rendering with fallback to classic

## Typical usage

```text
rrt tree
rrt tree --format markdown --max-depth 3
rrt tree --dirs-only --root src/repo_release_tools
```

## Embedding a tree into a Markdown file

Use `--inject` and `--anchor` to automatically update a block inside any
Markdown document without touching the surrounding prose.

**Step 1 — add anchor markers once** (HTML comments, invisible when rendered):

```markdown
## Project layout

Some intro text above — preserved on every run.

<!-- rrt:auto:start:project-tree -->
<!-- rrt:auto:end:project-tree -->

Some text below — also preserved.
```

**Step 2 — run `rrt tree` with `--inject`**:

```bash
rrt tree --format markdown --inject README.md --anchor project-tree
```

Only the content between the markers is replaced; everything else in the file
stays untouched.

**Preview without writing (dry-run)**:

```bash
rrt tree --format markdown --inject README.md --anchor project-tree --dry-run
```

### Anchor ID rules

An anchor ID must start with an ASCII letter or digit followed by any
combination of ASCII letters, digits, dots, underscores, or hyphens.

Valid examples: `project-tree`, `src.layout`, `tree_v2`

## Notes

- In Git repos, ignore behavior follows Git via `git check-ignore`.
- Outside Git repos, fallback ignore filtering skips common transient dirs.
- Hidden files are excluded unless `--show-hidden` is provided.
- `--inject` and `--anchor` must always be used together.
