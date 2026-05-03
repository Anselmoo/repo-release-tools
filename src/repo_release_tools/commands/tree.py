"""Render a project tree with gitignore-aware filtering.

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

## Caveats

- Symlinked directories are listed but not recursively traversed.
- The root itself is not printed as a tree node; output begins with its
    children.
- Rich formatting is optional and never required for baseline output.

## Related docs

- [Generated CLI reference](rrt-cli.md)
- [Git magic](git.md)
"""

from __future__ import annotations

import argparse
import importlib
import subprocess
import sys
from pathlib import Path
from typing import Any, TypeAlias

from repo_release_tools.config import _IGNORE_DIR_NAMES
from repo_release_tools.tools.inject import (
    ANCHOR_END_TOKEN,
    ANCHOR_START_TOKEN,
    replace_anchored_block,
)
from repo_release_tools.ui import GLYPHS, DryRunPrinter
from repo_release_tools.ui.glyphs import IS_LEGACY_TERMINAL

TREE_EPILOG = """  $ rrt tree
  $ rrt tree --format ascii
  $ rrt tree --format markdown --max-depth 3
  $ rrt tree --root src/repo_release_tools --dirs-only
  $ rrt tree --format markdown --inject README.md --anchor project-tree"""

TREE_DOC = """# Project tree

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
"""

SOURCE_OWNED_TOPIC_DOCS: tuple[tuple[str, str], ...] = (("tree", TREE_DOC),)

TreeEntry: TypeAlias = tuple[str, bool, list["TreeEntry"] | None]


def _resolve_git_root(cwd: Path) -> Path | None:
    """Return repository root when *cwd* is inside a git work tree."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    raw = result.stdout.strip()
    return Path(raw) if raw else None


def _is_ignored_by_git(path_from_repo_root: str, *, repo_root: Path) -> bool:
    """Return whether a path is ignored according to current git ignore semantics."""
    result = subprocess.run(
        ["git", "check-ignore", "--quiet", "--", path_from_repo_root],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def _sorted_children(path: Path) -> list[Path]:
    """Return deterministic children (dirs first, then files)."""
    items = sorted(path.iterdir(), key=lambda p: p.name.lower())
    return sorted(items, key=lambda p: (not p.is_dir(), p.name.lower()))


def _render_ascii_tree(entries: list[TreeEntry]) -> str:
    """Render entries as a tree with forced ASCII connectors."""
    lines: list[str] = []

    def visit(nodes: list[TreeEntry], prefix: str = "") -> None:
        for index, (name, is_dir, children) in enumerate(nodes):
            is_last = index == len(nodes) - 1
            connector = "`--" if is_last else "|--"
            suffix = "/" if is_dir else ""
            lines.append(f"{prefix}{connector} {name}{suffix}")
            if children:
                extension = "    " if is_last else "|   "
                visit(children, prefix=f"{prefix}{extension}")

    visit(entries)
    return "\n".join(lines)


def _render_markdown_tree(entries: list[TreeEntry]) -> str:
    """Render entries as markdown bullets."""
    lines: list[str] = []

    def visit(nodes: list[TreeEntry], depth: int = 0) -> None:
        indent = "  " * depth
        for name, is_dir, children in nodes:
            suffix = "/" if is_dir else ""
            lines.append(f"{indent}- {name}{suffix}")
            if children:
                visit(children, depth + 1)

    visit(entries)
    return "\n".join(lines)


def _render_rich_tree(entries: list[TreeEntry]) -> str | None:
    """Render entries through Rich when available.

    Returns ``None`` when Rich is not importable.

    ``no_color=True`` and ``highlight=False`` ensure the captured output
    contains only plain Unicode text — safe for both terminal printing and
    markdown/file injection without stray ANSI escape sequences.
    The ``IS_LEGACY_TERMINAL`` flag from the project's glyph layer is honoured:
    on legacy terminals the Rich output would be unreadable anyway, so we
    return ``None`` to fall back to the ASCII-safe classic renderer.
    """
    if IS_LEGACY_TERMINAL:
        return None

    try:
        rich_console = importlib.import_module("rich.console")
        rich_tree = importlib.import_module("rich.tree")
    except Exception:
        return None

    Console = getattr(rich_console, "Console", None)
    Tree = getattr(rich_tree, "Tree", None)
    if Console is None or Tree is None:
        return None

    def build(nodes: list[TreeEntry], tree: Any) -> None:
        for name, is_dir, children in nodes:
            label = f"{name}/" if is_dir else name
            node = tree.add(label)
            if children:
                build(children, node)

    root = Tree(".")
    build(entries, root)
    console = Console(record=True, no_color=True, highlight=False)
    with console.capture() as capture:
        getattr(console, "print")(root)
    return capture.get().rstrip("\n")


def _entry_count(entries: list[TreeEntry]) -> int:
    """Count all rendered entries recursively."""
    total = 0
    for _name, _is_dir, children in entries:
        total += 1
        if children:
            total += _entry_count(children)
    return total


def _build_entries(
    path: Path,
    *,
    root: Path,
    repo_root: Path | None,
    depth: int,
    max_depth: int | None,
    dirs_only: bool,
    show_hidden: bool,
    ignore_cache: dict[str, bool],
    warnings: list[str],
) -> list[TreeEntry]:
    """Recursively build the tree model for *path*."""
    result: list[TreeEntry] = []

    try:
        children = _sorted_children(path)
    except OSError as exc:
        warnings.append(f"Cannot read {path}: {exc}")
        return result

    for child in children:
        name = child.name
        if not show_hidden and name.startswith("."):
            continue

        if repo_root is None and name in _IGNORE_DIR_NAMES:
            continue

        try:
            relative_to_root = child.relative_to(root)
        except ValueError:
            relative_to_root = child

        if repo_root is not None:
            try:
                relative_to_repo = child.relative_to(repo_root)
                rel_text = relative_to_repo.as_posix()
            except ValueError:
                rel_text = relative_to_root.as_posix()
            if rel_text and rel_text != ".":
                ignored = ignore_cache.get(rel_text)
                if ignored is None:
                    ignored = _is_ignored_by_git(rel_text, repo_root=repo_root)
                    ignore_cache[rel_text] = ignored
                if ignored:
                    continue

        is_dir = child.is_dir()
        is_symlink = child.is_symlink()

        if dirs_only and not is_dir:
            continue

        child_nodes: list[TreeEntry] | None = None
        can_descend = is_dir and not is_symlink and (max_depth is None or depth < max_depth)
        if can_descend:
            child_nodes = _build_entries(
                child,
                root=root,
                repo_root=repo_root,
                depth=depth + 1,
                max_depth=max_depth,
                dirs_only=dirs_only,
                show_hidden=show_hidden,
                ignore_cache=ignore_cache,
                warnings=warnings,
            )

        result.append((name, is_dir, child_nodes))

    return result


def cmd_tree(args: argparse.Namespace) -> int:
    """Render a project tree from the selected root."""
    p = DryRunPrinter(getattr(args, "dry_run", False))

    inject_file: str | None = getattr(args, "inject", None)
    anchor_id: str | None = getattr(args, "anchor", None)

    if bool(inject_file) != bool(anchor_id):
        p.line(
            "--inject and --anchor must be used together.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    root = Path(args.root).resolve()
    if not root.exists():
        p.line(f"Root path does not exist: {root}", ok=False, stream=sys.stderr)
        return 1
    if not root.is_dir():
        p.line(f"Root path is not a directory: {root}", ok=False, stream=sys.stderr)
        return 1

    repo_root = _resolve_git_root(root)
    ignore_cache: dict[str, bool] = {}
    warnings: list[str] = []

    entries = _build_entries(
        root,
        root=root,
        repo_root=repo_root,
        depth=1,
        max_depth=args.max_depth,
        dirs_only=args.dirs_only,
        show_hidden=args.show_hidden,
        ignore_cache=ignore_cache,
        warnings=warnings,
    )

    fmt = args.format
    rendered: str
    if fmt == "ascii":
        rendered = _render_ascii_tree(entries)
    elif fmt == "markdown":
        rendered = _render_markdown_tree(entries)
    elif fmt == "rich":
        rich_rendered = _render_rich_tree(entries)
        if rich_rendered is None:
            p.warn("Rich format requested but Rich is unavailable; falling back to classic.")
            rendered = GLYPHS.tree.render(entries)
        else:
            rendered = rich_rendered
    else:
        rendered = GLYPHS.tree.render(entries)

    # --- inject mode: replace anchored block in a target file ---
    if inject_file and anchor_id:
        target = Path(inject_file)
        if not target.exists():
            p.line(f"Inject target does not exist: {target}", ok=False, stream=sys.stderr)
            return 1

        existing = target.read_text(encoding="utf-8")
        updated = replace_anchored_block(existing, anchor_id=anchor_id, content=rendered)
        if updated is None:
            p.line(
                f"{target} is missing anchor "
                f"<!-- {ANCHOR_START_TOKEN}{anchor_id} --> / "
                f"<!-- {ANCHOR_END_TOKEN}{anchor_id} -->.",
                ok=False,
                stream=sys.stderr,
            )
            return 1

        if p.dry_run:
            p.action(f"[dry-run] Would update anchored block {anchor_id!r} in {target}")
            p.blank_line()
            sys.stdout.write(updated)
        else:
            target.write_text(updated, encoding="utf-8")
            p.ok(f"Updated anchored block {anchor_id!r} in {target}")
        return 0

    # --- default mode: print tree to stdout ---
    p.ok("Project tree")
    p.meta("Root", str(root))
    p.meta("Format", fmt)
    if repo_root is not None:
        p.meta("Git ignore", "enabled")
    else:
        p.meta("Git ignore", "unavailable (non-git directory fallback)")
    if args.max_depth is not None:
        p.meta("Max depth", str(args.max_depth))
    p.blank_line()

    p.section("Tree")
    if rendered:
        sys.stdout.write(rendered + "\n")
    else:
        p.action("(empty)")
    p.blank_line()

    for warning in warnings:
        p.warn(warning)
    if warnings:
        p.blank_line()

    p.ok(f"Done. {_entry_count(entries)} entries shown.")
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the tree command."""
    parser = subparsers.add_parser(
        "tree",
        help="Show a project tree with gitignore-aware filtering.",
        description=(
            "Render a directory tree from the selected root while respecting gitignore rules.\n\n"
            "Formats: classic, ascii, markdown, rich. Rich output falls back to classic if "
            "the optional rich package is unavailable."
        ),
        epilog=TREE_EPILOG,
    )
    parser.add_argument(
        "--format",
        choices=["classic", "ascii", "markdown", "rich"],
        default="classic",
        help="Output format. Defaults to classic.",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=None,
        metavar="N",
        help="Maximum recursion depth (default: unlimited).",
    )
    parser.add_argument(
        "--dirs-only",
        action="store_true",
        default=False,
        help="Show directories only.",
    )
    parser.add_argument(
        "--show-hidden",
        action="store_true",
        default=False,
        help="Include dotfiles and dot-directories.",
    )
    parser.add_argument(
        "--root",
        default=".",
        metavar="PATH",
        help="Root directory to render (default: current directory).",
    )
    parser.add_argument(
        "--inject",
        default=None,
        metavar="FILE",
        help=(
            "Markdown file to update in-place. Requires --anchor. "
            "The anchored block is replaced; all other content is preserved."
        ),
    )
    parser.add_argument(
        "--anchor",
        default=None,
        metavar="ID",
        help=(
            "Anchor ID to replace inside the --inject file. "
            f"Place <!-- {ANCHOR_START_TOKEN}<ID> --> and "
            f"<!-- {ANCHOR_END_TOKEN}<ID> --> markers in the target file."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print the result instead of writing (only effective with --inject).",
    )
    parser.set_defaults(handler=cmd_tree)
