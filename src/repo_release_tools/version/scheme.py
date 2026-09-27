"""Version schemes a version group can be read, bumped and written in.

A *version scheme* names the grammar a group's version follows:

* ``semver`` - Semantic Versioning 2.0 (``1.2.3-rc.1``), see :mod:`.semver`
* ``pep440`` - PEP 440 spellings (``1.2.3rc1``), parsed by :mod:`.semver`
  through the :mod:`.pep440` grammar
* ``calver`` - calendar versions (``2026.05.15``), see :mod:`.calver`

The ``[tool.rrt]`` ``version_scheme`` key, the ``rrt bump --scheme`` flag and
the MCP ``rrt_bump(scheme=...)`` parameter all validate against
:data:`VERSION_SCHEMES` (decision D-4). Leaving the key unset means the scheme
is inferred from the group's primary target by :func:`infer_version_scheme`.

This module is a dependency-free leaf: it imports only :mod:`.calver` (which
itself imports only :mod:`.semver`) and never the config layer, so
``repo_release_tools.config`` can import it without creating a cycle.
"""

from __future__ import annotations

from typing import Final

from repo_release_tools.version.calver import CalVersion

VERSION_SCHEMES: Final[tuple[str, ...]] = ("semver", "pep440", "calver")
"""Every accepted ``version_scheme`` value, in documentation order."""

PEP440_TARGET_KINDS: Final[frozenset[str]] = frozenset({"pep621", "python_version"})
"""Version-target kinds whose files hold a Python (PEP 440) version."""


def infer_version_scheme(kind: str | None, current: str) -> str:
    """Return the scheme an unset ``version_scheme`` resolves to for a primary target.

    *kind* is the primary target's ``kind`` (``None`` for section/field or
    pattern targets) and *current* is the version string it holds.

    * a calendar-shaped version (``YYYY.MM``, ``YYYY.MM.DD`` or ``YYYY.M.D``,
      optionally with a micro counter) is ``calver``
    * otherwise a ``pep621`` or ``python_version`` target is ``pep440``
    * everything else is ``semver``
    """
    try:
        CalVersion.parse(current)
    except ValueError:
        pass
    else:
        return "calver"
    if kind in PEP440_TARGET_KINDS:
        return "pep440"
    return "semver"


__all__ = ["PEP440_TARGET_KINDS", "VERSION_SCHEMES", "infer_version_scheme"]
