"""Rich/ANSI terminal format renderer for rrt docs generate."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from repo_release_tools.config.core import DocsConfig
    from repo_release_tools.docs.extractor import DocEntry

from .markdown import has_markdown_headings, parse_markdown_lines


def render_structured_rich(content: str) -> str:
    """Render heading-structured Markdown using semantic terminal styling."""
    from repo_release_tools.ui import bold, heading, info, subtle  # noqa: PLC0415

    parsed = parse_markdown_lines(content)
    heading_levels = [
        line.level for line in parsed if line.kind == "heading" and line.level is not None
    ]
    if not heading_levels:
        return content.strip()
    shallowest = min(heading_levels)
    parts: list[str] = []
    for line in parsed:
        if line.kind == "heading" and line.level is not None:
            level = line.level - shallowest + 1
            indent = "  " + ("  " * max(level - 1, 0))
            match level:
                case 1:
                    parts.append(heading(f"{indent}{line.text}"))
                case 2:
                    parts.append(bold(f"{indent}{line.text}"))
                case _:
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


def render_rich(entries: list[DocEntry], config: DocsConfig) -> str:
    """Render entries with ANSI colour via ui helpers."""
    from repo_release_tools.ui import bold, info, subtle  # noqa: PLC0415

    from ._shared import _source_reference, _source_url  # noqa: PLC0415

    parts: list[str] = []
    for entry in entries:
        source_url = _source_url(entry, config)
        source_reference = _source_reference(entry)
        source_line = subtle(f"  {source_reference}" + (f" — {source_url}" if source_url else ""))
        parts.extend([f"{bold(f'  {entry.name}')}  [{entry.lang}]", source_line, ""])
        if has_markdown_headings(entry.content):
            parts.extend(render_structured_rich(entry.content).splitlines())
        else:
            parts.extend(f"  {info(line)}" for line in entry.content.splitlines())
        parts.append("")
    return "\n".join(parts)
