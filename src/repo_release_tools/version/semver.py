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


@dataclass(frozen=True)
class Version:
    """Semantic version with optional pre-release and build metadata."""

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
        - ``major``, ``minor``, ``patch`` — standard semver increments (clears pre/build)
        - ``pre-release`` — increment the numeric suffix of the current pre-release label
          (requires the version to already carry a pre-release identifier)
        - ``alpha``, ``beta``, ``rc`` — start or advance a named pre-release channel
        """
        if kind == "major":
            return Version(self.major + 1, 0, 0)
        if kind == "minor":
            return Version(self.major, self.minor + 1, 0)
        if kind == "patch":
            return Version(self.major, self.minor, self.patch + 1)
        if kind == "pre-release":
            return self._bump_pre_release()
        if kind in PRE_RELEASE_CHANNELS:
            return self._set_channel(kind)
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

    def is_pre_release(self) -> bool:
        """Return True when this version carries a pre-release label."""
        return self.pre is not None

    def __str__(self) -> str:
        """Return the canonical semver string."""
        base = f"{self.major}.{self.minor}.{self.patch}"
        if self.pre:
            base = f"{base}-{self.pre}"
        if self.build:
            base = f"{base}+{self.build}"
        return base
