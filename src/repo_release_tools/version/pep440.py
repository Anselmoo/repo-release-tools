"""PEP 440 version identifier validation and PEP 440 <-> SemVer conversion helpers.

Kept separate from :mod:`repo_release_tools.version.semver` deliberately: SemVer
2.0 and PEP 440 are different grammars with different precedence rules (see
PEP 440), and rrt's canonical ``Version`` type stays plain SemVer. This module
holds the PEP 440-specific concerns -- checking that a string is syntactically
valid PEP 440 (:func:`is_valid`; this does *not* imply it's publishable -- a
local-version segment is syntactically valid PEP 440 but rejected by PyPI on
upload, which is what :func:`has_local_segment` exists to flag separately),
and converting a PEP 440 dev-release into the SemVer shape a
``ci_format = "semver_pre"`` target expects -- so nothing else in the
codebase has to know PEP 440 grammar.
"""

from __future__ import annotations

import re

# Canonical PEP 440 version-identifier grammar, verbatim from the reference
# regex published in the PEP 440 spec (see "Appendix B: Parsing version
# strings with regular expressions" at packaging.python.org).
_VERSION_PATTERN = r"""
    v?
    (?:
        (?:(?P<epoch>[0-9]+)!)?                           # epoch
        (?P<release>[0-9]+(?:\.[0-9]+)*)                  # release segment
        (?P<pre>                                          # pre-release
            [-_\.]?
            (?P<pre_l>(a|b|c|rc|alpha|beta|pre|preview))
            [-_\.]?
            (?P<pre_n>[0-9]+)?
        )?
        (?P<post>                                         # post release
            (?:-(?P<post_n1>[0-9]+))
            |
            (?:
                [-_\.]?
                (?P<post_l>post|rev|r)
                [-_\.]?
                (?P<post_n2>[0-9]+)?
            )
        )?
        (?P<dev>                                          # dev release
            [-_\.]?
            (?P<dev_l>dev)
            [-_\.]?
            (?P<dev_n>[0-9]+)?
        )?
    )
    (?:\+(?P<local>[a-z0-9]+(?:[-_\.][a-z0-9]+)*))?       # local version
"""

_PEP440_RE = re.compile(
    r"^\s*" + _VERSION_PATTERN + r"\s*$",
    re.VERBOSE | re.IGNORECASE,
)

# PEP 440 `.devN` suffix, used to translate a PEP 440 dev-release into a
# Cargo-compatible SemVer prerelease identifier for `ci_format = "semver_pre"`
# targets.
_DEV_SUFFIX_RE = re.compile(r"\.dev(?P<build>\d+)$")


def is_valid(version: str) -> bool:
    """Return True when *version* is a syntactically valid PEP 440 version identifier."""
    return _PEP440_RE.match(version) is not None


def has_local_segment(version: str) -> bool:
    """Return True when *version* carries a PEP 440 local-version segment (``+...``).

    A local segment is syntactically valid PEP 440 but is explicitly rejected by
    PyPI (and most public indexes) on upload -- see PEP 440's "Local version
    identifiers". It looks deceptively similar to SemVer build metadata
    (``+build.N``), which is why an automated version bump can produce one
    without anyone intending a PyPI-unpublishable version.

    Returns False for a string that isn't valid PEP 440 at all; callers should
    check :func:`is_valid` first if that distinction matters.
    """
    match = _PEP440_RE.match(version)
    return bool(match and match.group("local"))


def pep440_dev_to_semver(version: str) -> str:
    """Convert a PEP 440 dev-release string to a Cargo-compatible SemVer prerelease.

    ``0.2.0.dev12345601`` -> ``0.2.0-dev.12345601``

    Release versions (no ``.dev`` suffix) are returned unchanged. When *version*
    already carries a SemVer prerelease segment before the dev suffix (e.g.
    ``1.2.3-beta.1.dev42``), ``dev.N`` is appended to that same segment
    (``1.2.3-beta.1.dev.42``) rather than introducing a second ``-``, which
    rrt's SemVer grammar (one ``-`` introduces the whole prerelease identifier
    list) would reject.
    """
    match = _DEV_SUFFIX_RE.search(version)
    if match is None:
        return version
    prefix = version[: match.start()]
    separator = "." if "-" in prefix else "-"
    return f"{prefix}{separator}dev.{match.group('build')}"
