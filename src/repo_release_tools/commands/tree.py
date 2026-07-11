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

- [Generated CLI reference](/repo-release-tools/commands/rrt-cli/)
- [rrt git](/repo-release-tools/commands/git_cmd/)
"""

from __future__ import annotations

import argparse
import gzip
import importlib
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeAlias

from repo_release_tools.state import (
    build_tree_lock,
    hash_content,
    hash_file,
    now_utc,
    rrt_dir,
    tree_lock_is_current,
    tree_lock_path,
    tree_manifest_gz_path,
    tree_manifest_path,
    write_lock,
)
from repo_release_tools.tools.inject import (
    ANCHOR_END_TOKEN,
    ANCHOR_START_TOKEN,
    replace_anchored_block,
)
from repo_release_tools.ui import GLYPHS, IS_LEGACY_TERMINAL, DryRunPrinter

_TREE_FALLBACK_IGNORE_DIR_NAMES: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        "dist",
        "build",
    },
)

TREE_EPILOG = """  $ rrt tree
  $ rrt tree --format ascii
  $ rrt tree --format markdown --max-depth 3
  $ rrt tree --root src/repo_release_tools --dirs-only
  $ rrt tree --format markdown --inject README.md --anchor project-tree"""

SOURCE_OWNED_TOPIC_DOCS: tuple[tuple[str, str], ...] = (("tree", __doc__ or ""),)

TreeEntry: TypeAlias = tuple[str, bool, list["TreeEntry"] | None]


@dataclass(frozen=True)
class ManifestEntry:
    """Manifest entry metadata for the deterministic tree manifest.

    Attributes mirror the JSON schema written to `.rrt/tree.manifest.json`.
    """

    path: str
    is_dir: bool
    size: int | None
    mtime: int | None
    sha256: str | None
    mode: int | None
    uid: int | None
    gid: int | None
    symlink_target: str | None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serialisable dict for this manifest entry."""
        return {
            "path": self.path,
            "is_dir": self.is_dir,
            "size": self.size,
            "mtime": self.mtime,
            "sha256": self.sha256,
            "mode": self.mode,
            "uid": self.uid,
            "gid": self.gid,
            "symlink_target": self.symlink_target,
        }


def _canonical_entry_repr(entries: list[TreeEntry]) -> str:
    """Return a stable, format-independent JSON serialization of tree entries.

    This is used to compute a hash that is independent of rendering format
    (ascii/markdown/rich/classic) and platform-specific glyph choices.
    """

    def _to_list(nodes: list[TreeEntry]) -> list[dict[str, object]]:
        result: list[dict[str, object]] = []
        for name, is_dir, children in nodes:
            entry: dict[str, object] = {"name": name, "is_dir": is_dir}
            if children is not None:
                entry["children"] = _to_list(children)
            result.append(entry)
        return result

    return json.dumps(_to_list(entries), sort_keys=True, separators=(",", ":"))


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


def _batch_ignored_by_git(paths_from_repo_root: list[str], *, repo_root: Path) -> set[str]:
    """Return ignored paths for *paths_from_repo_root* via one git invocation.

    Uses ``git check-ignore --stdin`` to avoid one subprocess per file.
    Returns an empty set when no paths are ignored or when git reports no
    matches. Other non-zero return codes are treated conservatively as
    "no ignored paths" for this pass.
    """
    if not paths_from_repo_root:
        return set()

    payload = "\n".join(paths_from_repo_root)
    if payload:
        payload += "\n"

    result = subprocess.run(
        ["git", "check-ignore", "--stdin"],
        cwd=repo_root,
        input=payload,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode not in (0, 1):
        return set()

    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


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


def _path_string(parent_rel: str, name: str, *, root: Path, absolute: bool) -> str:
    """Build a posix-style path string for a tree entry.

    *parent_rel* is the posix path of the parent relative to *root* (or empty
    for the root's direct children). When *absolute* is True the returned path
    is rooted at the resolved *root* directory.
    """
    rel = f"{parent_rel}/{name}" if parent_rel else name
    if absolute:
        return (root / rel).as_posix()
    return rel


def _render_json_tree(
    entries: list[TreeEntry],
    *,
    root: Path,
    absolute: bool = False,
) -> str:
    """Render entries as a deterministic nested JSON document.

    Each node carries ``name``, ``is_dir``, ``path``, and (for directories)
    ``children``. Path values respect ``absolute``. The output uses stable
    separators and sorted keys to keep diffs minimal.
    """

    def visit(nodes: list[TreeEntry], parent_rel: str) -> list[dict[str, object]]:
        out: list[dict[str, object]] = []
        for name, is_dir, children in nodes:
            path_str = _path_string(parent_rel, name, root=root, absolute=absolute)
            entry: dict[str, object] = {"name": name, "is_dir": is_dir, "path": path_str}
            if children is not None:
                entry["children"] = visit(children, f"{parent_rel}/{name}" if parent_rel else name)
            out.append(entry)
        return out

    payload = visit(entries, "")
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _render_flat_tree(
    entries: list[TreeEntry],
    *,
    root: Path,
    absolute: bool = False,
) -> str:
    """Render entries as one posix path per line.

    Directories are emitted with a trailing ``/`` so they stay visually
    distinguishable from files. Honors ``absolute``; ``--dirs-only`` is
    applied earlier during tree construction.
    """
    lines: list[str] = []

    def visit(nodes: list[TreeEntry], parent_rel: str) -> None:
        for name, is_dir, children in nodes:
            path_str = _path_string(parent_rel, name, root=root, absolute=absolute)
            lines.append(f"{path_str}/" if is_dir else path_str)
            if children:
                visit(children, f"{parent_rel}/{name}" if parent_rel else name)

    visit(entries, "")
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
    except ImportError:
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

    console = Console(no_color=True, highlight=False)
    rendered: list[str] = []
    for name, is_dir, children in entries:
        top = Tree(f"{name}/" if is_dir else name)
        if children:
            build(children, top)
        lines = console.render_lines(top, pad=False, new_lines=False)
        rendered.extend("".join(segment.text for segment in line).rstrip() for line in lines)
    return "\n".join(rendered).rstrip("\n")


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

    candidates: list[tuple[Path, str, str | None]] = []
    for child in children:
        name = child.name
        if not show_hidden and name.startswith("."):
            continue

        if repo_root is None and name in _TREE_FALLBACK_IGNORE_DIR_NAMES:
            continue

        try:
            relative_to_root = child.relative_to(root)
        except ValueError:
            relative_to_root = child

        rel_text: str | None = None
        if repo_root is not None:
            try:
                relative_to_repo = child.relative_to(repo_root)
                rel_text = relative_to_repo.as_posix()
            except ValueError:
                rel_text = relative_to_root.as_posix()
            if rel_text in ("", "."):
                rel_text = None

        candidates.append((child, name, rel_text))

    if repo_root is not None:
        uncached = sorted(
            {
                rel_text
                for _child, _name, rel_text in candidates
                if rel_text is not None and rel_text not in ignore_cache
            },
        )
        ignored_set = _batch_ignored_by_git(uncached, repo_root=repo_root)
        for rel_text in uncached:
            ignore_cache[rel_text] = rel_text in ignored_set

    for child, name, rel_text in candidates:
        if rel_text is not None and ignore_cache.get(rel_text, False):
            continue

        is_dir = child.is_dir()
        is_symlink = child.is_symlink()

        if dirs_only and not is_dir:
            continue

        child_nodes: list[TreeEntry] | None = None
        if is_dir and not is_symlink and (max_depth is None or depth < max_depth):
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


def _warn_for_empty_directories(
    entries: list[TreeEntry],
    warnings: list[str],
    root: Path | None = None,
) -> list[str]:
    """Append warnings for truly-empty directories and return their paths.

    A directory containing only a ``.gitkeep`` placeholder is considered
    intentionally preserved and is silently skipped (no warning, not returned).
    A directory with no visible children is "phantom": git cannot track it,
    so it causes manifest drift between local and CI checkouts.

    When *root* is supplied, the filesystem is consulted to recognise
    ``.gitkeep`` placeholders even when the scan filtered hidden files.

    Returns the list of truly-empty (phantom) directory paths, posix-style,
    relative to the scan root. Callers can use this list to drive
    ``--strict-empty-dirs`` escalation or the ``--fix-empty-dirs`` interactive
    mode.
    """
    phantom: list[str] = []

    def visit(nodes: list[TreeEntry], prefix: str = "") -> None:
        for name, is_dir, children in nodes:
            current = f"{prefix}{name}"
            if not is_dir:
                continue
            has_only_gitkeep = (
                children is not None
                and len(children) == 1
                and children[0][0] == ".gitkeep"
                and not children[0][1]
            )
            if has_only_gitkeep:
                continue
            if children == []:
                if root is not None and (root / current).is_dir():
                    try:
                        if any((root / current).iterdir()):
                            continue
                    except OSError:
                        pass
                phantom.append(current)
                warnings.append(
                    f"Empty directory detected: {current}/. Git does not track empty directories; "
                    f"if this folder should stay in the repository and tree snapshots, "
                    f"add a .gitkeep placeholder file.",
                )
                continue
            if children:
                visit(children, prefix=f"{current}/")

    visit(entries)
    return phantom


def _compute_sha256(path: Path) -> str | None:
    """Return a stable sha256:... digest for *path* or None on error.

    Uses the shared state.hash_file helper; callers should handle exceptions
    and control when hashing runs (it's intentionally expensive).
    """
    try:
        return hash_file(path)
    except Exception:
        return None


def _flatten_entries_for_manifest(
    entries: list[TreeEntry],
    root: Path,
    *,
    hash_files: bool,
    warnings: list[str],
) -> list[ManifestEntry]:
    """Flatten the nested *entries* into a list of ManifestEntry instances.

    Each ManifestEntry contains: path (posix, relative to *root*), is_dir,
    size, mtime (int), sha256 (or null), mode, uid, gid, symlink_target (or null).
    When *hash_files* is False the sha256 field will always be null.
    """
    result: list[ManifestEntry] = []

    def visit(nodes: list[TreeEntry], parent: Path) -> None:
        for name, is_dir, children in nodes:
            rel = parent / name
            full = root / rel
            posix = rel.as_posix()

            try:
                lstat = full.lstat()
            except OSError as exc:
                warnings.append(f"Cannot stat {full}: {exc}")
                lstat = None

            is_symlink = full.is_symlink()
            symlink_target: str | None = None
            if is_symlink:
                try:
                    symlink_target = os.readlink(full)
                except OSError as exc:
                    warnings.append(f"Cannot readlink {full}: {exc}")

            size: int | None = None
            mtime: int | None = None
            sha: str | None = None

            try:
                if is_dir:
                    # directories: record size 0 and use lstat mtime when
                    # available
                    size = 0
                    if lstat is not None:
                        mtime = int(lstat.st_mtime)
                else:
                    # files: prefer stat() (follows symlink) for size/mtime
                    try:
                        statobj = full.stat()
                    except OSError:
                        statobj = lstat
                    if statobj is not None:
                        size = int(statobj.st_size)
                        mtime = int(statobj.st_mtime)

                    if hash_files:
                        # Only hash regular files (Path.is_file() follows
                        # symlinks). Broken links / non-files are skipped.
                        try:
                            if full.is_file():
                                sha = _compute_sha256(full)
                        except Exception as exc:  # pragma: no cover - defensive
                            warnings.append(f"Cannot hash {full}: {exc}")
            except Exception as exc:  # pragma: no cover - defensive
                warnings.append(f"Error collecting metadata for {full}: {exc}")

            mode = lstat.st_mode if lstat is not None else None
            uid = lstat.st_uid if lstat is not None else None
            gid = lstat.st_gid if lstat is not None else None

            entry = ManifestEntry(
                path=posix,
                is_dir=bool(is_dir),
                size=size,
                mtime=mtime,
                sha256=sha,
                mode=mode,
                uid=uid,
                gid=gid,
                symlink_target=symlink_target,
            )
            result.append(entry)

            if children:
                visit(children, rel)

    visit(entries, Path())

    # Deterministic ordering by path
    return sorted(result, key=lambda e: e.path)


def _atomic_write(
    content: bytes | str,
    target: Path,
    target_dir: Path,
    *,
    warnings: list[str],
    warning_label: str,
) -> None:
    """Write *content* to *target* atomically via a temp file in *target_dir*.

    Collapses the two near-identical (bytes vs. text) temp-file-then-replace
    blocks that used to live separately in :func:`_write_tree_manifest` for
    the compressed and plain manifest cases. On failure, appends a message
    to *warnings* using *warning_label* and re-raises -- callers propagate.
    """
    mode = "wb" if isinstance(content, bytes) else "w"
    encoding = None if isinstance(content, bytes) else "utf-8"
    try:
        fd = tempfile.NamedTemporaryFile(
            mode=mode, encoding=encoding, dir=str(target_dir), delete=False
        )
        try:
            fd.write(content)
            fd.flush()
            fd_name = fd.name
        finally:
            fd.close()
        Path(fd_name).replace(target)
    except Exception as exc:
        warnings.append(f"Failed to install {warning_label} {target}: {exc}")
        raise


def _write_tree_manifest(
    entries: list[TreeEntry],
    root: Path,
    p: DryRunPrinter,
    *,
    hash_files: bool,
    warnings: list[str],
    compressed: bool = False,
) -> None:
    """Build and write .rrt/tree.manifest.json atomically.

    The manifest is deterministic: entries are sorted by path and the JSON
    dump uses stable separators and sort_keys for inner-dict consistency.
    """
    manifest_entries = _flatten_entries_for_manifest(
        entries, root=root, hash_files=hash_files, warnings=warnings
    )

    # Convert ManifestEntry instances to plain dicts for stable JSON output.
    manifest_files = [e.to_dict() for e in manifest_entries]
    manifest: dict[str, object] = {"meta": {"generated_at": now_utc()}, "files": manifest_files}

    text = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    target_dir = rrt_dir(root)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = tree_manifest_path(root)
    gz_target = tree_manifest_gz_path(root)

    if p.dry_run:
        dest = gz_target if compressed else target
        p.action(f"[dry-run] Would write manifest to {dest}")
        p.blank_line()
        sys.stdout.write(text + "\n")
        return

    # Atomic write into same directory. Write compressed if requested,
    # otherwise write plain JSON.
    if compressed:
        compressed_bytes = gzip.compress(text.encode("utf-8"))
        _atomic_write(
            compressed_bytes,
            gz_target,
            target_dir,
            warnings=warnings,
            warning_label="compressed manifest",
        )
        p.ok(
            f"Tree manifest written to .rrt/tree.manifest.json.gz ({len(manifest_entries)} entries)"
        )
    else:
        _atomic_write(text, target, target_dir, warnings=warnings, warning_label="manifest")
        p.ok(f"Tree manifest written to .rrt/tree.manifest.json ({len(manifest_entries)} entries)")


def _report_tree_check_result(
    printer: DryRunPrinter,
    *,
    drifted: list[str],
    strict: bool,
) -> int:
    """Print tree drift messages and return the appropriate exit code."""
    for msg in drifted:
        printer.warn(f"  {msg}")
    if strict:
        printer.line("Tree structure drift detected (--strict mode).", ok=False, stream=sys.stderr)
        printer.line(
            "Run `rrt tree --snapshot` to update the snapshot.", ok=False, stream=sys.stderr
        )
        return 1
    printer.warn("Tree structure drift detected (advisory). Use --strict to block.")
    return 0


def _inject_rendered_tree(
    printer: DryRunPrinter,
    *,
    inject_file: str,
    anchor_id: str,
    rendered: str,
) -> int:
    """Replace the anchored block in a target file with rendered tree output."""
    target = Path(inject_file)
    if not target.exists():
        printer.line(f"Inject target does not exist: {target}", ok=False, stream=sys.stderr)
        return 1

    existing = target.read_text(encoding="utf-8")
    updated = replace_anchored_block(existing, anchor_id=anchor_id, content=rendered)
    if updated is None:
        printer.line(
            f"{target} is missing anchor "
            f"<!-- {ANCHOR_START_TOKEN}{anchor_id} --> / "
            f"<!-- {ANCHOR_END_TOKEN}{anchor_id} -->.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    if printer.dry_run:
        printer.action(f"[dry-run] Would update anchored block {anchor_id!r} in {target}")
        printer.blank_line()
        sys.stdout.write(updated)
    else:
        target.write_text(updated, encoding="utf-8")
        printer.ok(f"Updated anchored block {anchor_id!r} in {target}")
    return 0


@dataclass(frozen=True)
class Options:
    """Typed view of ``argparse.Namespace`` for ``rrt tree``.

    Built once via :meth:`from_args` at the top of :func:`cmd_tree` so every
    flag has a single, typed read site instead of scattered
    ``getattr(args, ..., default)`` / ``args.x`` calls throughout the
    function body.
    """

    verbose: int
    dry_run: bool
    inject: str | None
    anchor: str | None
    path: str | None
    root: str
    max_depth: int | None
    dirs_only: bool
    show_hidden: bool
    fix_empty_dirs: bool
    yes: bool
    auto_resolve: str | None
    format: str
    absolute: bool
    strict_empty_dirs: bool
    snapshot: bool
    check: bool
    strict: bool
    manifest: bool
    compressed: bool
    output: str | None

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> Options:
        """Build an :class:`Options` from a parsed ``argparse.Namespace``.

        Every flag is given a real default by tree.py's own register() (or,
        for --verbose, by cli.py's global parser), so a Namespace produced by
        argparse always carries every attribute. ``getattr`` fallbacks here
        are still required for two independent reasons:

        1. `workflow/hooks.py`'s "tree-check" case hand-builds a sparse
           Namespace(path=None, root=..., max_depth=..., dirs_only=...,
           show_hidden=..., inject=None, anchor=None, fix_empty_dirs=False,
           dry_run=False, strict_empty_dirs=False, snapshot=False,
           check=True, strict=True, verbose=verbose, format="classic") that
           omits ``manifest``, ``compressed``, ``yes``, ``auto_resolve``,
           ``absolute``, and ``output`` entirely. Plain attribute access for
           those six would raise AttributeError on the `rrt-hooks tree-check`
           path used by CI/pre-commit.
        2. Several unit tests in tests/commands/test_tree*.py construct their
           own sparse argparse.Namespace by hand (helpers like ``_args()``
           and ``_f2_args()``, plus ad-hoc Namespace(...) calls), routinely
           omitting ``path``, ``verbose``, ``strict_empty_dirs``,
           ``fix_empty_dirs``, ``yes``, and ``auto_resolve`` in addition to
           the six hooks.py never sets.

        This is the single translation point that absorbs both gaps, so the
        rest of cmd_tree can read opts.x unconditionally.
        """
        return cls(
            verbose=getattr(args, "verbose", 0) or 0,
            dry_run=getattr(args, "dry_run", False),
            inject=getattr(args, "inject", None),
            anchor=getattr(args, "anchor", None),
            path=getattr(args, "path", None),
            root=args.root,
            max_depth=args.max_depth,
            dirs_only=args.dirs_only,
            show_hidden=args.show_hidden,
            fix_empty_dirs=getattr(args, "fix_empty_dirs", False),
            yes=getattr(args, "yes", False),
            auto_resolve=getattr(args, "auto_resolve", None),
            format=args.format,
            absolute=getattr(args, "absolute", False),
            strict_empty_dirs=getattr(args, "strict_empty_dirs", False),
            snapshot=getattr(args, "snapshot", False),
            check=getattr(args, "check", False),
            strict=getattr(args, "strict", False),
            manifest=getattr(args, "manifest", False),
            compressed=getattr(args, "compressed", False),
            output=getattr(args, "output", None),
        )


def cmd_tree(args: argparse.Namespace) -> int:
    """Render a project tree from the selected root."""
    opts = Options.from_args(args)
    verbose: int = opts.verbose
    p = DryRunPrinter(opts.dry_run, verbose=verbose)

    inject_file: str | None = opts.inject
    anchor_id: str | None = opts.anchor

    if bool(inject_file) != bool(anchor_id):
        p.line(
            "--inject and --anchor must be used together.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    # The positional `path` argument, when given, takes precedence over `--root`.
    positional_path: str | None = opts.path
    root_input = positional_path if positional_path else opts.root
    root = Path(root_input).resolve()
    if not root.exists():
        p.line(f"Root path does not exist: {root}", ok=False, stream=sys.stderr)
        return 1
    if not root.is_dir():
        p.line(f"Root path is not a directory: {root}", ok=False, stream=sys.stderr)
        return 1

    p.verbose_line(f"tree: {root}", level=1)
    repo_root = _resolve_git_root(root)
    ignore_cache: dict[str, bool] = {}
    warnings: list[str] = []

    entries = _build_entries(
        root,
        root=root,
        repo_root=repo_root,
        depth=1,
        max_depth=opts.max_depth,
        dirs_only=opts.dirs_only,
        show_hidden=opts.show_hidden,
        ignore_cache=ignore_cache,
        warnings=warnings,
    )
    phantom_empty_dirs: list[str] = []
    if repo_root is not None:
        phantom_empty_dirs = _warn_for_empty_directories(entries, warnings, root=root)

    do_fix_empty_dirs: bool = opts.fix_empty_dirs
    if do_fix_empty_dirs:
        from repo_release_tools.commands._tree_fix import fix_empty_dirs

        return fix_empty_dirs(
            root,
            phantom_empty_dirs,
            printer=p,
            dry_run=opts.dry_run,
            assume_yes=opts.yes,
            auto_resolve=opts.auto_resolve,
        )

    fmt = opts.format
    absolute_paths: bool = opts.absolute
    rendered: str
    match fmt:
        case "ascii":
            rendered = _render_ascii_tree(entries)
        case "markdown":
            rendered = _render_markdown_tree(entries)
        case "rich":
            rich_rendered = _render_rich_tree(entries)
            if rich_rendered is None:
                p.warn("Rich format requested but Rich is unavailable; falling back to classic.")
                rendered = GLYPHS.tree.render(entries)
            else:
                rendered = rich_rendered
        case "json":
            rendered = _render_json_tree(entries, root=root, absolute=absolute_paths)
        case "flat":
            rendered = _render_flat_tree(entries, root=root, absolute=absolute_paths)
        case _:
            rendered = GLYPHS.tree.render(entries)

    entry_count = _entry_count(entries)
    ignored_count = sum(ignore_cache.values())
    tree_meta = {
        "entry_count": entry_count,
        "tree_hash": hash_content(_canonical_entry_repr(entries)),
        "ignored_count": ignored_count,
        "phantom_empty_dirs": [str(d) for d in phantom_empty_dirs],
    }

    strict_empty: bool = opts.strict_empty_dirs
    if strict_empty and phantom_empty_dirs:
        for path in phantom_empty_dirs:
            p.line(f"Phantom empty directory (untrackable by git): {path}/", ok=False)
        p.line(
            "Run `rrt tree --fix-empty-dirs` to add .gitkeep placeholders "
            "or remove the directories.",
            ok=False,
        )
        return 1

    do_snapshot: bool = opts.snapshot
    do_check: bool = opts.check
    strict: bool = opts.strict
    do_manifest: bool = opts.manifest
    do_compressed: bool = opts.compressed
    # --compressed implies --manifest
    if do_compressed:
        do_manifest = True

    if do_manifest:
        # Manifest generation is potentially expensive (hashing file
        # contents); only run when explicitly requested.
        _write_tree_manifest(
            entries, root, p, hash_files=True, warnings=warnings, compressed=do_compressed
        )
        # If only manifest was requested, exit now. If snapshot/check are
        # also provided, continue so they can run as well.
        if not do_snapshot and not do_check:
            return 0

    if do_snapshot:
        lock_data = build_tree_lock(tree_meta)
        write_lock(tree_lock_path(root), lock_data)
        p.ok(f"Tree snapshot written to .rrt/tree.lock.toml ({entry_count} entries)")
        return 0

    if do_check:
        current, drifted = tree_lock_is_current(tree_lock_path(root), tree_meta)
        if current:
            p.ok("No tree structure drift detected.")
            return 0

        # When structural drift is detected, try to provide a compact,
        # machine-assisted manifest diff if a previous manifest exists. This
        # avoids dumping a large JSON blob into logs while giving humans a
        # concise list of added/removed paths and file/dir counts.
        try:
            manifest_json = tree_manifest_path(root)
            manifest_gz = tree_manifest_gz_path(root)

            manifest_text: str | None = None
            if manifest_json.exists():
                try:
                    manifest_text = manifest_json.read_text(encoding="utf-8")
                except Exception as exc:
                    warnings.append(f"Failed to read manifest {manifest_json}: {exc}")
            elif manifest_gz.exists():
                try:
                    with gzip.open(str(manifest_gz), "rb") as gf:
                        manifest_text = gf.read().decode("utf-8")
                except Exception as exc:
                    warnings.append(f"Failed to read compressed manifest {manifest_gz}: {exc}")

            if manifest_text:
                prev_manifest = json.loads(manifest_text)
                prev_files = list(prev_manifest.get("files", []))
                prev_paths = {str(e.get("path", "")) for e in prev_files}

                current_files = _flatten_entries_for_manifest(
                    entries, root, hash_files=False, warnings=warnings
                )
                curr_paths = {str(e.path) for e in current_files}

                added = sorted(curr_paths - prev_paths)
                removed = sorted(prev_paths - curr_paths)

                prev_file_count = sum(not e.get("is_dir") for e in prev_files)
                prev_dir_count = sum(e.get("is_dir") for e in prev_files)
                curr_file_count = sum(not e.is_dir for e in current_files)
                curr_dir_count = sum(e.is_dir for e in current_files)

                # Build a compact multi-line manifest summary to append to the
                # drift diagnostic. Limit listed paths to a reasonable N.
                N = 10
                manifest_lines = [
                    "Detailed manifest diff (from .rrt/tree.manifest.json):",
                    f"  - files: was {prev_file_count} → now {curr_file_count} (Δ {curr_file_count - prev_file_count:+d})",
                    f"  - directories: was {prev_dir_count} → now {curr_dir_count} (Δ {curr_dir_count - prev_dir_count:+d})",
                ]

                if added:
                    manifest_lines.append(f"  - added ({len(added)}):")
                    for pth in added[:N]:
                        manifest_lines.append(f"    - {pth}")
                    if len(added) > N:
                        manifest_lines.append(f"    ... ({len(added) - N} more)")

                if removed:
                    manifest_lines.append(f"  - removed ({len(removed)}):")
                    for pth in removed[:N]:
                        manifest_lines.append(f"    - {pth}")
                    if len(removed) > N:
                        manifest_lines.append(f"    ... ({len(removed) - N} more)")

                drifted.append("\n".join(manifest_lines))
        except Exception as exc:  # pragma: no cover - best-effort diagnostics
            warnings.append(f"Failed to compute manifest diff: {exc}")

        return _report_tree_check_result(p, drifted=drifted, strict=strict)

    # --- inject mode: replace anchored block in a target file ---
    if inject_file and anchor_id:
        return _inject_rendered_tree(
            p, inject_file=inject_file, anchor_id=anchor_id, rendered=rendered
        )

    # --- default mode: print tree to stdout or write to --output ---
    output_path: str | None = opts.output
    if output_path:
        body = (rendered + "\n") if rendered else ""
        Path(output_path).write_text(body, encoding="utf-8")
        p.ok(f"Tree written to {output_path} ({entry_count} entries).")
        for warning in warnings:
            p.warn(warning)
        return 0

    p.ok("Project tree")
    p.meta("Root", str(root))
    p.meta("Format", fmt)
    if repo_root is not None:
        p.meta("Git ignore", "enabled")
    else:
        p.meta("Git ignore", "unavailable (non-git directory fallback)")
    if opts.max_depth is not None:
        p.meta("Max depth", str(opts.max_depth))
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

    p.ok(f"Done. {entry_count} entries shown.")
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the tree command."""
    parser = subparsers.add_parser(
        "tree",
        help="Show a project tree with gitignore-aware filtering.",
        description=(
            "Render a directory tree from the selected root while respecting gitignore rules.\n\n"
            "Formats: classic, ascii, markdown, rich, json, flat. Rich output falls back to "
            "classic if the optional rich package is unavailable. json/flat emit machine-"
            "consumable output (a nested document or one path per line, respectively)."
        ),
        epilog=TREE_EPILOG,
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        metavar="PATH",
        help=(
            "Root directory to render. Equivalent to --root and takes precedence "
            "when both are supplied."
        ),
    )
    parser.add_argument(
        "--format",
        choices=["classic", "ascii", "markdown", "rich", "json", "flat"],
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
        help="Print planned actions instead of writing (with --inject or --fix-empty-dirs).",
    )
    snapshot_group = parser.add_mutually_exclusive_group()
    snapshot_group.add_argument(
        "--snapshot",
        action="store_true",
        default=False,
        help="Write a tree structure snapshot to .rrt/tree.lock.toml as a baseline.",
    )
    snapshot_group.add_argument(
        "--check",
        action="store_true",
        default=False,
        help="Compare current tree against .rrt/tree.lock.toml and report structural drift.",
    )
    parser.add_argument(
        "--manifest",
        action="store_true",
        default=False,
        help=(
            "Write a machine-readable manifest to .rrt/tree.manifest.json containing per-file "
            "metadata (size, mtime, sha256, mode, uid, gid, symlink_target). This enables "
            "deterministic, atomic manifest generation and implies hashing of file contents."
        ),
    )
    parser.add_argument(
        "--compressed",
        action="store_true",
        default=False,
        help=(
            "Write the manifest as a compressed gzip file (.rrt/tree.manifest.json.gz). "
            "Implied: --manifest."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="With --check: exit 1 on structural drift (default: advisory, exit 0).",
    )
    parser.add_argument(
        "--strict-empty-dirs",
        action="store_true",
        default=False,
        help=(
            "Exit 1 when truly-empty (non-.gitkept) directories are present. "
            "Such directories cannot be tracked by git and cause local/CI manifest "
            "drift. Use --fix-empty-dirs to resolve interactively."
        ),
    )
    parser.add_argument(
        "--fix-empty-dirs",
        action="store_true",
        default=False,
        help=(
            "Interactively resolve truly-empty directories by adding a .gitkeep "
            "placeholder or removing the directory. Honors --dry-run and --yes."
        ),
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        default=False,
        help="With --fix-empty-dirs: assume yes (add .gitkeep) for every prompt.",
    )
    parser.add_argument(
        "--auto-resolve",
        choices=["gitkeep", "delete", "hard", "git-rm"],
        default=None,
        metavar="ACTION",
        help=(
            "With --fix-empty-dirs: apply ACTION to every phantom directory "
            "without prompting. 'git-rm' stages the removal via `git rm -rf`."
        ),
    )
    parser.add_argument(
        "--absolute",
        action="store_true",
        default=False,
        help=(
            "Emit absolute paths in the json and flat formats (and in the "
            "manifest). Default: paths are relative to the scan root."
        ),
    )
    parser.add_argument(
        "--output",
        default=None,
        metavar="PATH",
        help=(
            "Write the rendered tree to PATH instead of stdout. Honors --format. "
            "Ignored when --inject, --snapshot, --check, or --fix-empty-dirs is "
            "used (those have their own targets)."
        ),
    )
    parser.set_defaults(handler=cmd_tree)
