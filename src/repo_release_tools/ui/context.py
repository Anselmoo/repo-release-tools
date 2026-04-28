"""Rendering context dataclass for repo-release-tools output functions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import IO, Literal


@dataclass
class OutputContext:
    """Rendering context threaded through all output functions.

    Create one instance from the parsed global CLI flags and pass it
    to every command ``run()`` function so that format, color, and
    stream can be switched centrally without touching every call-site.
    """

    format: Literal["text", "json"] = "text"
    no_color: bool = False
    stream: IO[str] | None = None
    _extras: dict[str, object] = field(default_factory=dict, repr=False)

    def is_json(self) -> bool:
        """Return True when the output format is JSON."""
        return self.format == "json"
