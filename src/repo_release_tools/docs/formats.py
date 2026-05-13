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
from urllib.parse import quote

if TYPE_CHECKING:
    from repo_release_tools.config.core import DocsConfig
    from repo_release_tools.docs.extractor import DocEntry

from repo_release_tools.state import build_lock, docs_lock_path, write_lock

from .markdown import has_markdown_headings, parse_markdown_lines


def _render_structured_txt(content: str) -> str:
    """Render heading-structured Markdown as readable plain text."""
    parsed = parse_markdown_lines(content)
    heading_levels = [
        line.level for line in parsed if line.kind == "heading" and line.level is not None
    ]
    if not heading_levels:
        return content

    shallowest = min(heading_levels)
    parts: list[str] = []
    for line in parsed:
        if line.kind == "heading" and line.level is not None:
            level = line.level - shallowest + 1
            if parts and parts[-1] != "":
                parts.append("")
            if level == 1:
                parts.extend([line.text.upper(), "=" * len(line.text)])
            elif level == 2:
                parts.extend([line.text, "-" * len(line.text)])
            else:
                indent = "  " * max(level - 3, 0)
                parts.append(f"{indent}* {line.text}")
            continue
        parts.append(line.text)
    return "\n".join(parts).strip()


def _render_structured_rich(content: str) -> str:
    """Render heading-structured Markdown using semantic terminal styling."""
    from repo_release_tools.ui import bold, heading, info, subtle

    parsed = parse_markdown_lines(content)
    heading_levels = [
        line.level for line in parsed if line.kind == "heading" and line.level is not None
    ]
    shallowest = min(heading_levels)
    parts: list[str] = []
    for line in parsed:
        if line.kind == "heading" and line.level is not None:
            level = line.level - shallowest + 1
            indent = "  " + ("  " * max(level - 1, 0))
            if level == 1:
                parts.append(heading(f"{indent}{line.text}"))
            elif level == 2:
                parts.append(bold(f"{indent}{line.text}"))
            else:
                parts.append(bold(f"{indent}• {line.text}"))
            continue
        if line.text == "":
            parts.append("")
            continue
        if line.kind == "fence":
            parts.append(f"  {subtle(line.text)}")
            continue
        parts.append(f"  {info(line.text)}")
    return "\n".join(parts).strip()


def _source_path(entry: DocEntry) -> str:
    return entry.source_file.replace("\\", "/")


def _source_reference(entry: DocEntry) -> str:
    return f"{_source_path(entry)}:{entry.line}"


def _source_url(entry: DocEntry, config: DocsConfig) -> str | None:
    repo_url = getattr(config, "source_repo_url", None)
    template = getattr(config, "source_url_template", None)
    ref = getattr(config, "source_ref", None) or "main"
    if not repo_url and not template:
        return None

    path = quote(_source_path(entry), safe="/-._~")
    mapping = {
        "repo_url": repo_url or "",
        "ref": ref,
        "path": path,
        "source_file": path,
        "line": entry.line,
        "name": entry.name,
        "lang": entry.lang,
    }
    if template:
        placeholders = ", ".join(sorted(mapping))
        try:
            return template.format(**mapping)
        except (KeyError, ValueError) as exc:
            raise ValueError(
                "Invalid source_url_template "
                f"{template!r}: {exc}. Supported placeholders: {placeholders}.",
            ) from exc
    repo_base = repo_url.rstrip("/") if repo_url else ""
    return f"{repo_base}/blob/{ref}/{path}#L{entry.line}"


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def render_md(entries: list[DocEntry], config: DocsConfig) -> str:
    """Render entries as a Markdown document."""
    parts: list[str] = ["# Documentation\n"]
    for entry in entries:
        anchor = entry.name.lower().replace(" ", "-")
        source_url = _source_url(entry, config)
        source_reference = _source_reference(entry)
        if source_url:
            source_line = f"*Source: [{source_reference}]({source_url}) · lang: {entry.lang}*\n"
        else:
            source_line = f"*Source: `{source_reference}` · lang: {entry.lang}*\n"
        parts.extend([f"\n## {entry.name} {{#{anchor}}}\n", source_line, f"\n{entry.content}\n"])
    return "\n".join(parts)


def inject_md(
    entries: list[DocEntry],
    config: DocsConfig,
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
        anchor_id = f"docs.{entry.name}"
        block = entry.content
        updated = replace_anchored_block(result, anchor_id=anchor_id, content=block)
        if updated is not None:
            result = updated
    return result


# ---------------------------------------------------------------------------
# Plain text
# ---------------------------------------------------------------------------


def render_txt(entries: list[DocEntry], config: DocsConfig) -> str:
    """Render entries as plain text."""
    parts: list[str] = []
    for entry in entries:
        source_url = _source_url(entry, config)
        source_reference = _source_reference(entry)
        source_line = f"Source: {source_reference}" + (f" — {source_url}" if source_url else "")
        parts.extend(
            [
                f"=== {entry.name} ({entry.lang}) ===",
                source_line,
                "",
                _render_structured_txt(entry.content),
                "",
            ],
        )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Rich (ANSI terminal output)
# ---------------------------------------------------------------------------


def render_rich(entries: list[DocEntry], config: DocsConfig) -> str:
    """Render entries with ANSI colour via ui helpers."""
    from repo_release_tools.ui import bold, info, subtle

    parts: list[str] = []
    for entry in entries:
        source_url = _source_url(entry, config)
        source_reference = _source_reference(entry)
        source_line = subtle(f"  {source_reference}" + (f" — {source_url}" if source_url else ""))
        parts.extend([f"{bold(f'  {entry.name}')}  [{entry.lang}]", source_line, ""])
        if has_markdown_headings(entry.content):
            parts.extend(_render_structured_rich(entry.content).splitlines())
        else:
            parts.extend(f"  {info(line)}" for line in entry.content.splitlines())
        parts.append("")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------


def render_json(entries: list[DocEntry], config: DocsConfig) -> str:
    """Render entries as a JSON array."""
    payload = []
    for entry in entries:
        item = entry.to_dict()
        if source_url := _source_url(entry, config):
            item["source_url"] = source_url
        payload.append(item)
    return json.dumps(payload, indent=2)


# ---------------------------------------------------------------------------
# TOML lockfile (via state.py)
# ---------------------------------------------------------------------------


def render_toml(
    entries: list[DocEntry],
    config: DocsConfig,
    *,
    root: Path,
) -> str:
    """Write a .rrt/docs.lock.toml and return the TOML text."""
    from collections import defaultdict

    from repo_release_tools.state import _dict_to_toml

    by_file: dict[str, list[DocEntry]] = defaultdict(list)
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
            },
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
    entries: list[DocEntry],
    config: DocsConfig,
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
