---
title: "rrt tree"
permalink: "/commands/tree/"
---
<!-- rrt:auto:start:page-header -->
<p><a href="https://github.com/Anselmoo/repo-release-tools"><picture>
  <source media="(prefers-color-scheme: dark)" srcset="/repo-release-tools/assets/badges/github-reto-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="/repo-release-tools/assets/badges/github-reto-light.svg">
  <img alt="GitHub" src="/repo-release-tools/assets/badges/github-reto-dark.svg">
</picture></a></p>
<!-- rrt:auto:end:page-header -->


# rrt tree

Render a project tree with gitignore-aware filtering.

## Overview

`rrt tree` prints a repository or directory tree suitable for terminal review,
docs snippets, and quick project orientation.

The command is read-only and intentionally deterministic:

- stable ordering (directories first, then files)
- optional depth limiting for large repositories
- optional hidden-file inclusion
- optional directories-only mode

## Ignore behavior

When the selected root is inside a Git repository, ignore checks use Git's own
exclude engine via `git check-ignore`, so matching follows active repository
rules and precedence semantics.

When the root is not in a Git worktree, the command falls back to a conservative
local skip list for well-known transient directories (for example `.git`,
`node_modules`, `.venv`) while still honoring explicit CLI flags.

## Output formats

- `classic` (default): platform-aware tree connectors through `GLYPHS.tree`
- `ascii`: forced ASCII connectors for paste-safe logs or legacy terminals
- `markdown`: nested bullet output for Markdown docs and issue comments
- `rich`: Rich tree rendering when the optional package is installed; falls
    back to `classic` with a warning when Rich is unavailable

## Common options

- `--root PATH` selects the traversal root
- `--max-depth N` limits recursion depth (unlimited by default)
- `--dirs-only` suppresses files
- `--show-hidden` includes dotfiles and dot-directories

## Failure behavior

The command exits non-zero when:

- the root path does not exist
- the root path is not a directory

Unreadable subdirectories are reported as warnings and do not fail the command.

## Examples

```bash
rrt tree
rrt tree --format ascii
rrt tree --format markdown --max-depth 3
rrt tree --root src/repo_release_tools --dirs-only
rrt tree --format markdown --inject README.md --anchor project-tree
rrt tree --format markdown --inject README.md --anchor project-tree --dry-run
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

### Anchor ID rules

An anchor ID must start with an ASCII letter or digit followed by any
combination of ASCII letters, digits, dots, underscores, or hyphens.

Valid examples: `project-tree`, `src.layout`, `tree_v2`

## Caveats

- Symlinked directories are listed but not recursively traversed.
- The root itself is not printed as a tree node; output begins with its
    children.
- Rich formatting is optional and never required for baseline output.

## Related docs

- [Generated CLI reference](rrt-cli.md)
- [rrt git](git_cmd.md)

<!-- rrt:auto:start:doc-footer -->
---

[↑ Docs index](https://github.com/Anselmoo/repo-release-tools/blob/main/docs/index.md) · [CLI reference](https://github.com/Anselmoo/repo-release-tools/blob/main/docs/commands/rrt-cli.md) · [Changelog](https://github.com/Anselmoo/repo-release-tools/blob/main/CHANGELOG.md) · [GitHub](https://github.com/Anselmoo/repo-release-tools)
<!-- rrt:auto:end:doc-footer -->
