"""Plain-text format renderer for rrt docs generate."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from repo_release_tools.config.core import DocsConfig
    from repo_release_tools.docs.extractor import DocEntry

from repo_release_tools.docs.markdown import parse_markdown_lines


def render_structured_txt(content: str) -> str:
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
            match level:
                case 1:
                    parts.extend([line.text.upper(), "=" * len(line.text)])
                case 2:
                    parts.extend([line.text, "-" * len(line.text)])
                case _:
                    indent = "  " * max(level - 3, 0)
                    parts.append(f"{indent}* {line.text}")
            continue
        parts.append(line.text)
    return "\n".join(parts).strip()


def render_txt(entries: list[DocEntry], config: DocsConfig) -> str:
    """Render entries as plain text."""
    from ._shared import _source_reference, _source_url  # noqa: PLC0415

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
                render_structured_txt(entry.content),
                "",
            ],
        )
    return "\n".join(parts)
