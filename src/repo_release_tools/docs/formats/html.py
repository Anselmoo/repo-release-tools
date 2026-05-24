"""HTML format renderer stub for rrt docs generate."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from repo_release_tools.config.core import DocsConfig
    from repo_release_tools.docs.extractor import DocEntry


def render_html(entries: list[DocEntry], config: DocsConfig) -> str:
    """Render entries as a standalone HTML document.

    Not yet implemented — raises NotImplementedError until a Markdown-to-HTML
    conversion library is wired up.
    """
    raise NotImplementedError("HTML format renderer is not yet implemented")
