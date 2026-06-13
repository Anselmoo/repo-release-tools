"""Generate per-directory purpose docs for `rrt docs map`.

This module owns the pure-functional core of the generator:

- `iter_target_directories` walks the configured root and yields source-bearing
  subdirectories, honoring include/exclude globs and the project's standard
  ignore-name set.
- `build_purpose_section`, `build_tree_section`, and `build_prompts_section`
  assemble the three nested content blocks.
- `build_full_block` composes them into the body that will live between the
  outer `rrt-docs-map` anchors.
- `apply_to_file` reads the target file (or starts from empty), respects the
  configured `on_conflict` mode, and returns a `MapResult` describing what
  changed.

CLI wiring lives in `commands/docs_cmd.py` (Slice 4). Drift detection against
`docs.lock.toml` lives in a dedicated follow-up (Slice 3).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from repo_release_tools.config import ignore_dir_names
from repo_release_tools.tools.inject import (
    insert_anchor_stub_str,
    replace_anchored_block,
)

if TYPE_CHECKING:
    from repo_release_tools.config import MapConfig

MAP_ANCHOR_ID = "rrt-docs-map"
TREE_ANCHOR_ID = "rrt-docs-map-tree"

_SOURCE_EXTENSIONS = frozenset(
    {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".go", ".rs", ".sh"},
)
_PROMPT_TEXT = {
    "self-check": (
        "> **LLM self-check:** Before relying on this overview, verify that the "
        "Purpose section still describes what this directory does — read the "
        "module docstrings under it and report any drift."
    ),
    "auto-update": (
        "> **Auto-update:** To refresh this file, run `rrt docs map`. "
        "The block between the anchors above is regenerated; prose outside "
        "the anchors is preserved verbatim."
    ),
}


@dataclass(frozen=True)
class MapResult:
    """The outcome of generating one per-directory purpose doc."""

    directory: Path
    file_path: Path
    status: str  # "created" | "updated" | "uptodate" | "skipped"
    desired_block: str


def iter_target_directories(config: MapConfig, repo_root: Path) -> list[Path]:
    """Return source-bearing directories under *config.root*, sorted, repo-relative."""
    root = (repo_root / config.root).resolve()
    if not root.is_dir():
        return []

    ignored = ignore_dir_names()
    include_set = tuple(config.include)
    exclude_set = tuple(config.exclude)

    results: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_dir():
            continue
        if any(part in ignored or part.startswith(".") for part in path.relative_to(root).parts):
            continue
        rel = path.relative_to(repo_root).as_posix()
        if exclude_set and any(_match_glob(rel, pat) for pat in exclude_set):
            continue
        if include_set and not any(_match_glob(rel, pat) for pat in include_set):
            continue
        if not _has_source_files(path):
            continue
        results.append(path)
    return results


def _match_glob(rel_posix: str, pattern: str) -> bool:
    """Return True if *rel_posix* matches *pattern* via PurePath glob semantics."""
    from fnmatch import fnmatch

    return fnmatch(rel_posix, pattern)


def _has_source_files(directory: Path) -> bool:
    """Return True if *directory* directly contains at least one source file."""
    return any(
        child.is_file() and child.suffix in _SOURCE_EXTENSIONS for child in directory.iterdir()
    )


def build_purpose_section(directory: Path, config: MapConfig, repo_root: Path) -> str:
    """Return the Purpose section markdown for *directory*."""
    rel = directory.relative_to(repo_root).as_posix()
    text = config.purpose.get(rel, "").strip()
    body = text if text else f"_No purpose configured for `{rel}`._"
    return f"## Purpose\n\n{body}\n"


def build_tree_section(directory: Path, config: MapConfig) -> str:
    """Return the Tree section markdown for *directory*, with its own anchor."""
    lines = _render_directory_tree(
        directory, max_depth=config.tree_max_depth, ignored=ignore_dir_names()
    )
    block = "\n".join(lines).rstrip()
    inner_body = (
        f"```text\n{directory.name}/\n{block}\n```\n"
        if block
        else f"```text\n{directory.name}/\n```\n"
    )
    return (
        "## Tree\n\n"
        f"<!-- rrt:auto:start:{TREE_ANCHOR_ID} -->\n"
        f"{inner_body}"
        f"<!-- rrt:auto:end:{TREE_ANCHOR_ID} -->\n"
    )


def _render_directory_tree(
    directory: Path, *, max_depth: int, ignored: frozenset[str]
) -> list[str]:
    """Render *directory* as ASCII connectors, honoring *max_depth*."""

    def _walk(current: Path, prefix: str, depth: int) -> list[str]:
        if max_depth == 0 or depth >= max_depth:
            return []
        try:
            children = sorted(
                (
                    c
                    for c in current.iterdir()
                    if c.name not in ignored and not c.name.startswith(".")
                ),
                key=lambda c: (not c.is_dir(), c.name),
            )
        except OSError:
            return []
        out: list[str] = []
        for idx, child in enumerate(children):
            last = idx == len(children) - 1
            connector = "└── " if last else "├── "
            suffix = "/" if child.is_dir() else ""
            out.append(f"{prefix}{connector}{child.name}{suffix}")
            if child.is_dir():
                next_prefix = prefix + ("    " if last else "│   ")
                out.extend(_walk(child, next_prefix, depth + 1))
        return out

    return _walk(directory, "", 0)


def build_prompts_section(config: MapConfig) -> str:
    """Return the prompts section markdown, or an empty string if no prompts configured."""
    if not config.prompts:
        return ""
    parts = ["## LLM prompts\n"]
    for name in config.prompts:
        if name in _PROMPT_TEXT:
            parts.append(_PROMPT_TEXT[name])
            parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def build_full_block(directory: Path, config: MapConfig, repo_root: Path) -> str:
    """Compose the full anchor-block body (Purpose + Tree + optional Prompts)."""
    sections = [
        build_purpose_section(directory, config, repo_root),
        build_tree_section(directory, config),
    ]
    prompts = build_prompts_section(config)
    if prompts:
        sections.append(prompts)
    return "\n".join(s.rstrip() + "\n" for s in sections).rstrip() + "\n"


def apply_to_file(
    file_path: Path,
    desired_block: str,
    *,
    on_conflict: str,
    dry_run: bool = False,
) -> MapResult:
    """Apply *desired_block* to *file_path* per *on_conflict* mode.

    Returns a `MapResult` describing the outcome. Raises `ValueError` when
    ``on_conflict == 'error'`` and the file exists without the outer anchor.
    """
    directory = file_path.parent
    if not file_path.exists():
        new_content = (
            f"<!-- rrt:auto:start:{MAP_ANCHOR_ID} -->\n"
            f"{desired_block}"
            f"<!-- rrt:auto:end:{MAP_ANCHOR_ID} -->\n"
        )
        if not dry_run:
            file_path.write_text(new_content, encoding="utf-8")
        return MapResult(
            directory=directory,
            file_path=file_path,
            status="created",
            desired_block=desired_block,
        )

    if on_conflict == "skip":
        return MapResult(
            directory=directory,
            file_path=file_path,
            status="skipped",
            desired_block=desired_block,
        )

    existing = file_path.read_text(encoding="utf-8")
    has_anchor = f"<!-- rrt:auto:start:{MAP_ANCHOR_ID} -->" in existing

    if on_conflict == "error" and not has_anchor:
        raise ValueError(
            f"{file_path} exists without the {MAP_ANCHOR_ID!r} anchor; "
            "set on_conflict='merge' to inject it, or remove the file."
        )

    seeded = (
        existing
        if has_anchor
        else insert_anchor_stub_str(
            existing, MAP_ANCHOR_ID, position="append", before_blank_lines=1, after_blank_lines=0
        )
    )
    replaced = replace_anchored_block(seeded, anchor_id=MAP_ANCHOR_ID, content=desired_block)
    desired_full = replaced if replaced is not None else seeded

    if desired_full == existing:
        return MapResult(
            directory=directory,
            file_path=file_path,
            status="uptodate",
            desired_block=desired_block,
        )

    if not dry_run:
        file_path.write_text(desired_full, encoding="utf-8")
    return MapResult(
        directory=directory,
        file_path=file_path,
        status="updated",
        desired_block=desired_block,
    )


def generate(config: MapConfig, repo_root: Path, *, dry_run: bool = False) -> list[MapResult]:
    """Generate (or preview) a purpose doc for every target directory."""
    results: list[MapResult] = []
    for directory in iter_target_directories(config, repo_root):
        block = build_full_block(directory, config, repo_root)
        file_path = directory / config.file_name
        results.append(
            apply_to_file(file_path, block, on_conflict=config.on_conflict, dry_run=dry_run)
        )
    return results
