"""Semantic version helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

SEMVER_PARTS = 3

# Matches MAJOR.MINOR.PATCH[-pre][+build] per semver 2.0.
# Pre-release: optional -alpha, -alpha.1, -beta.2, -rc.3, etc.
# Build metadata: optional +build.123
_SEMVER_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<pre>[0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*))?"
    r"(?:\+(?P<build>[0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*))?$"
)

# Channel names accepted by bump(pre_release=...)
PRE_RELEASE_CHANNELS = ("alpha", "beta", "rc")

# One pre-release identifier as a precedence key: (kind, numeric value, text).
# kind 0 = numeric identifier, kind 1 = alphanumeric identifier.
PreReleaseIdentifierKey = tuple[int, int, str]

# Full precedence key: (major, minor, patch, stable flag, pre-release identifier keys).
SortKey = tuple[int, int, int, int, tuple[PreReleaseIdentifierKey, ...]]


@dataclass(frozen=True)
class Version:
    """Semantic version with optional pre-release and build metadata.

    Equality (``==``) is structural: it comes from the dataclass and compares every
    field, including ``build``. Ordering (``<``, ``<=``, ``>``, ``>=``) follows
    SemVer 2.0 section 11 precedence via :meth:`sort_key` and ignores build metadata,
    so ``1.0.0+a`` and ``1.0.0+b`` are neither ``<`` nor ``>`` each other yet not ``==``.
    """

    major: int
    minor: int
    patch: int
    pre: str | None = field(default=None)
    build: str | None = field(default=None)

    @classmethod
    def parse(cls, raw: str) -> Version:
        """Parse a semver string (MAJOR.MINOR.PATCH[-pre][+build]) into a :class:`Version`."""
        m = _SEMVER_RE.match(raw.strip())
        if m is None:
            raise ValueError(f"Invalid semver: {raw!r}")
        return cls(
            int(m.group("major")),
            int(m.group("minor")),
            int(m.group("patch")),
            pre=m.group("pre"),
            build=m.group("build"),
        )

    def bump(self, kind: str) -> Version:
        """Return a new :class:`Version` bumped by *kind*.

        Accepted kinds:
        - ``major``, ``minor``, ``patch`` — standard semver increments (clears pre/build).
          When the version is already a pre-release whose trailing components are at
          the target boundary (e.g. ``2.0.0-beta.2`` bumping ``major``), this finalizes
          the pre-release in place instead of skipping past it -- the same rule
          node-semver's ``inc()`` uses.
        - ``release`` — finalize the current pre-release to its stable target version,
          unconditionally (requires the version to already carry a pre-release identifier)
        - ``pre-release`` — increment the numeric suffix of the current pre-release label
          (requires the version to already carry a pre-release identifier)
        - ``alpha``, ``beta``, ``rc`` — start or advance a named pre-release channel
        """
        match kind:
            case "major":
                if self.minor != 0 or self.patch != 0 or self.pre is None:
                    return Version(self.major + 1, 0, 0)
                return Version(self.major, 0, 0)
            case "minor":
                if self.patch != 0 or self.pre is None:
                    return Version(self.major, self.minor + 1, 0)
                return Version(self.major, self.minor, 0)
            case "patch":
                if self.pre is None:
                    return Version(self.major, self.minor, self.patch + 1)
                return Version(self.major, self.minor, self.patch)
            case "release":
                return self._finalize_release()
            case "pre-release":
                return self._bump_pre_release()
            case _ if kind in PRE_RELEASE_CHANNELS:
                return self._set_channel(kind)
            case _:
                raise ValueError(f"Unknown bump kind: {kind!r}")

    def _bump_pre_release(self) -> Version:
        """Increment the numeric suffix of the current pre-release label."""
        if self.pre is None:
            raise ValueError(
                "Cannot bump pre-release on a stable version. "
                "Use 'alpha', 'beta', or 'rc' to start a pre-release channel."
            )
        parts = self.pre.rsplit(".", 1)
        if len(parts) == 2 and parts[1].isdigit():
            new_pre = f"{parts[0]}.{int(parts[1]) + 1}"
        else:
            new_pre = f"{self.pre}.1"
        return Version(self.major, self.minor, self.patch, pre=new_pre)

    def _set_channel(self, channel: str) -> Version:
        """Start or advance a named pre-release channel."""
        if self.pre is None:
            # Start at channel.1 on the current patch (stable → pre-release)
            return Version(self.major, self.minor, self.patch, pre=f"{channel}.1")
        # Already on a pre-release: keep the same base version, advance the channel
        existing_channel = self.pre.split(".")[0].lower()
        if existing_channel == channel:
            return self._bump_pre_release()
        # Switch to a new channel (e.g. alpha → beta); reset the counter
        return Version(self.major, self.minor, self.patch, pre=f"{channel}.1")

    def stable(self) -> Version:
        """Return the stable release for this version (drop pre and build metadata)."""
        return Version(self.major, self.minor, self.patch)

    def _finalize_release(self) -> Version:
        """Finalize the current pre-release to its stable target version."""
        if self.pre is None:
            raise ValueError(
                "Cannot finalize a version that has no pre-release. "
                "Use 'major', 'minor', or 'patch' to start a new release cycle."
            )
        return self.stable()

    def is_pre_release(self) -> bool:
        """Return True when this version carries a pre-release label."""
        return self.pre is not None

    def sort_key(self) -> SortKey:
        """Return the SemVer 2.0 section 11 precedence key for this version.

        Precedence compares ``major``, ``minor`` and ``patch`` numerically first. On an
        equal core, a pre-release sorts before the stable release (4th element: 0 for a
        pre-release, 1 for stable), so ``1.2.0-rc.1`` < ``1.2.0``.

        Pre-release labels are split on ``.`` and compared identifier by identifier,
        left to right. Numeric identifiers compare numerically and sort before
        alphanumeric ones, which compare in ASCII order. When all preceding identifiers
        are equal, the shorter list sorts first. So ``rc.2`` < ``rc.10`` and
        ``alpha`` < ``alpha.1`` < ``alpha.beta`` < ``beta``.

        Build metadata never takes part in precedence.
        """
        return (
            self.major,
            self.minor,
            self.patch,
            0 if self.pre else 1,
            _pre_release_key(self.pre),
        )

    def __lt__(self, other: object) -> bool:
        """Return True when *self* has lower SemVer precedence than *other*."""
        if not isinstance(other, Version):
            return NotImplemented
        return self.sort_key() < other.sort_key()

    def __le__(self, other: object) -> bool:
        """Return True when *self* has lower or equal SemVer precedence than *other*."""
        if not isinstance(other, Version):
            return NotImplemented
        return self.sort_key() <= other.sort_key()

    def __gt__(self, other: object) -> bool:
        """Return True when *self* has higher SemVer precedence than *other*."""
        if not isinstance(other, Version):
            return NotImplemented
        return self.sort_key() > other.sort_key()

    def __ge__(self, other: object) -> bool:
        """Return True when *self* has higher or equal SemVer precedence than *other*."""
        if not isinstance(other, Version):
            return NotImplemented
        return self.sort_key() >= other.sort_key()

    def __str__(self) -> str:
        """Return the canonical semver string."""
        base = f"{self.major}.{self.minor}.{self.patch}"
        if self.pre:
            base = f"{base}-{self.pre}"
        if self.build:
            base = f"{base}+{self.build}"
        return base


def _pre_release_key(pre: str | None) -> tuple[PreReleaseIdentifierKey, ...]:
    """Return the per-identifier precedence key for a pre-release label.

    Numeric identifiers map to ``(0, value, "")`` and alphanumeric ones to
    ``(1, 0, text)``, so tuple comparison puts numeric before alphanumeric, compares
    numbers numerically and text in ASCII order. A stable version yields ``()``.
    """
    if not pre:
        return ()
    return tuple(
        (0, int(ident), "") if ident.isdigit() else (1, 0, ident) for ident in pre.split(".")
    )


def newer_versions(current: Version, candidates: list[Version]) -> list[Version]:
    """Return candidates strictly newer than *current*, ascending by version.

    "Newer" and the ascending order both use SemVer 2.0 section 11 precedence
    (:meth:`Version.sort_key`), so ``1.0.0-rc.10`` is newer than ``1.0.0-rc.2``.
    Build metadata is ignored, so a candidate differing only in build is not newer.
    """
    ck = current.sort_key()
    fresh = [v for v in candidates if v.sort_key() > ck]
    return sorted(fresh, key=Version.sort_key)
