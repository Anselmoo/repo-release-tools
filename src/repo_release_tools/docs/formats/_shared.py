"""Shared utilities for format renderers."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import quote

if TYPE_CHECKING:
    from repo_release_tools.config.core import DocsConfig
    from repo_release_tools.docs.extractor import DocEntry


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
