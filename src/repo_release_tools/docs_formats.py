"""Format renderers for the rrt docs generate command.

Each renderer takes a list of DocEntry objects and DocsConfig, and returns
a string representation in the requested format.

Supported formats:
  md         — Markdown, with optional anchor-block injection
  txt        — Plain text, suitable for terminal piping
  rich       — Rich terminal output via ui helpers (returns ANSI string)
  clipboard  — Same as txt (caller is responsible for clipboard write)
  json       — JSON array of entry dicts
  toml       — Writes .rrt/docs.lock.toml via state.build_lock()
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from repo_release_tools.config import DocsConfig
    from repo_release_tools.docs_extractor import DocEntry

from repo_release_tools.state import build_lock, docs_lock_path, write_lock

# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def render_md(entries: list["DocEntry"], config: "DocsConfig") -> str:
    """Render entries as a Markdown document."""
    parts: list[str] = ["# Documentation\n"]
    for entry in entries:
        anchor = entry.name.lower().replace(" ", "-")
        parts.append(f"\n## {entry.name} {{#{anchor}}}\n")
        parts.append(f"*Source: `{entry.source_file}` line {entry.line} · lang: {entry.lang}*\n")
        parts.append(f"\n{entry.content}\n")
    return "\n".join(parts)


def inject_md(
    entries: list["DocEntry"],
    config: "DocsConfig",
    *,
    target_file: Path,
) -> str:
    """Inject or update anchored blocks inside an existing Markdown file.

    Anchors follow the form ``<!-- docs:NAME -->…<!-- /docs:NAME -->``.
    Returns the modified document text (does not write the file).
    """
    from repo_release_tools.tools.inject import replace_anchored_block

    existing = target_file.read_text(encoding="utf-8") if target_file.exists() else ""
    result = existing
    for entry in entries:
        anchor_id = f"docs:{entry.name}"
        block = entry.content
        updated = replace_anchored_block(result, anchor_id=anchor_id, content=block)
        if updated is not None:
            result = updated
    return result


# ---------------------------------------------------------------------------
# Plain text
# ---------------------------------------------------------------------------


def render_txt(entries: list["DocEntry"], config: "DocsConfig") -> str:
    """Render entries as plain text."""
    parts: list[str] = []
    for entry in entries:
        parts.append(f"=== {entry.name} ({entry.lang}) ===")
        parts.append(f"Source: {entry.source_file}:{entry.line}")
        parts.append("")
        parts.append(entry.content)
        parts.append("")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Rich (ANSI terminal output)
# ---------------------------------------------------------------------------


def render_rich(entries: list["DocEntry"], config: "DocsConfig") -> str:
    """Render entries with ANSI colour via ui helpers."""
    from repo_release_tools.ui import bold, info, subtle

    parts: list[str] = []
    for entry in entries:
        parts.append(bold(f"  {entry.name}") + f"  [{entry.lang}]")
        parts.append(subtle(f"  {entry.source_file}:{entry.line}"))
        parts.append("")
        for line in entry.content.splitlines():
            parts.append(f"  {info(line)}")
        parts.append("")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------


def render_json(entries: list["DocEntry"], config: "DocsConfig") -> str:
    """Render entries as a JSON array."""
    return json.dumps([e.to_dict() for e in entries], indent=2)


# ---------------------------------------------------------------------------
# TOML lockfile (via state.py)
# ---------------------------------------------------------------------------


def render_toml(
    entries: list["DocEntry"],
    config: "DocsConfig",
    *,
    root: Path,
) -> str:
    """Write a .rrt/docs.lock.toml and return the TOML text."""
    from collections import defaultdict

    from repo_release_tools.state import _dict_to_toml  # noqa: PLC2701

    by_file: dict[str, list["DocEntry"]] = defaultdict(list)
    for entry in entries:
        by_file[entry.source_file].append(entry)

    sources: list[dict] = []
    for src_file, src_entries in by_file.items():
        # Combined hash of all entries in this file (stable, sorted by name)
        combined = "".join(e.hash for e in sorted(src_entries, key=lambda e: e.name))
        from repo_release_tools.state import hash_content

        sources.append(
            {
                "source_file": src_file,
                "hash": hash_content(combined),
                "symbols": [e.name for e in src_entries],
                "lang": src_entries[0].lang,
            }
        )

    lock_data = build_lock(sources)
    lock_path = docs_lock_path(root, config.lock_file)
    write_lock(lock_path, lock_data)
    return _dict_to_toml(lock_data)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_RENDERERS = {
    "md": render_md,
    "txt": render_txt,
    "rich": render_rich,
    "clipboard": render_txt,  # same as txt; caller handles clipboard
    "json": render_json,
}


def render(
    fmt: str,
    entries: list["DocEntry"],
    config: "DocsConfig",
    *,
    root: Path | None = None,
) -> str:
    """Dispatch to the correct renderer.

    For the ``toml`` format a *root* Path is required so the lock file path
    can be resolved.
    """
    if fmt == "toml":
        if root is None:
            raise ValueError("render() requires root= for format='toml'")
        return render_toml(entries, config, root=root)
    renderer = _RENDERERS.get(fmt)
    if renderer is None:
        raise ValueError(f"Unsupported format {fmt!r}. Supported: {list(_RENDERERS) + ['toml']}")
    return renderer(entries, config)
