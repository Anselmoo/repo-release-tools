"""Version-related helpers for repo-release-tools.

``semver``, ``pep440`` and ``calver`` depend only on each other (``semver`` reads
PEP 440 through ``pep440``'s grammar, ``calver`` shares ``semver``'s sort-key
shape), so importing them never pulls in the config layer. The file-target helpers in ``targets`` depend on
``repo_release_tools.config`` (which itself imports ``semver`` constants), so they
are resolved lazily on first attribute access to keep that import acyclic.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

from .calver import CALVER_SCHEMES, CalVersion
from .semver import Version

if TYPE_CHECKING:
    from .targets import (
        VersionWriteEvent,
        check_autodetected_version_consistency,
        read_current_version,
        read_group_current_version,
        read_group_current_version_for_scheme,
        read_group_version_strings,
        read_version_string,
        replace_pin_in_file,
        replace_version_in_file,
    )

_LAZY_TARGET_EXPORTS = frozenset(
    {
        "VersionWriteEvent",
        "check_autodetected_version_consistency",
        "read_current_version",
        "read_group_current_version",
        "read_group_current_version_for_scheme",
        "read_group_version_strings",
        "read_version_string",
        "replace_pin_in_file",
        "replace_version_in_file",
    }
)


def __getattr__(name: str) -> Any:
    """Resolve the ``targets`` re-exports on first access (PEP 562)."""
    if name in _LAZY_TARGET_EXPORTS:
        value = getattr(importlib.import_module(f"{__name__}.targets"), name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "CALVER_SCHEMES",
    "CalVersion",
    "Version",
    "VersionWriteEvent",
    "check_autodetected_version_consistency",
    "read_current_version",
    "read_group_current_version",
    "read_group_current_version_for_scheme",
    "read_group_version_strings",
    "read_version_string",
    "replace_pin_in_file",
    "replace_version_in_file",
]
