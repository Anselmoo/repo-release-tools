"""Rendering for :class:`~repo_release_tools.version.targets.VersionWriteEvent`.

`version/targets.py`'s write primitives are headless: they return
``VersionWriteEvent`` records instead of printing. This module holds the one
rendering routine shared by every surface that consumes those events
(`bump.py`, `workspace.py`, `ci_version.py`, `release_repair.py`, and the MCP
bump tool), so the exact `--dry-run` / applied output produced before the
seam was introduced stays byte-identical no matter which command triggered
the write.
"""

from __future__ import annotations

from collections.abc import Iterable

from repo_release_tools.ui import GLYPHS, DryRunPrinter, VerbosePrinter
from repo_release_tools.version.targets import VersionWriteEvent


def render_version_write_events(events: Iterable[VersionWriteEvent]) -> None:
    """Print one line per event, matching the pre-seam ``targets.py`` output.

    Dry-run events render as ``Would update <path>: version = "<new>"``;
    applied events render as ``<path>  →  version = "<new>"``.
    """
    for event in events:
        if event.dry_run:
            p = DryRunPrinter(dry_run=True)
            p.would_write(str(event.path), detail=f'version = "{event.new_version}"')
        else:
            msg = f'{event.path}  {GLYPHS.arrow.right}  version = "{event.new_version}"'
            p = VerbosePrinter()
            p.ok(msg)
