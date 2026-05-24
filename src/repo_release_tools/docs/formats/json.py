"""JSON format renderer for rrt docs generate."""

from __future__ import annotations

import json as _json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from repo_release_tools.config.core import DocsConfig
    from repo_release_tools.docs.extractor import DocEntry


def render_json(entries: list[DocEntry], config: DocsConfig) -> str:
    """Render entries as a JSON array."""
    from ._shared import _source_url  # noqa: PLC0415

    payload = []
    for entry in entries:
        item = entry.to_dict()
        if source_url := _source_url(entry, config):
            item["source_url"] = source_url
        payload.append(item)
    return _json.dumps(payload, indent=2)
