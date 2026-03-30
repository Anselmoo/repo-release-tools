"""Semantic version helpers."""

from __future__ import annotations

from dataclasses import dataclass


SEMVER_PARTS = 3


@dataclass(frozen=True)
class Version:
    """Simple semantic version."""

    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, raw: str) -> "Version":
        parts = raw.strip().split(".")
        if len(parts) != SEMVER_PARTS or not all(part.isdigit() for part in parts):
            raise ValueError(f"Invalid semver: {raw!r}")
        return cls(int(parts[0]), int(parts[1]), int(parts[2]))

    def bump(self, kind: str) -> "Version":
        if kind == "major":
            return Version(self.major + 1, 0, 0)
        if kind == "minor":
            return Version(self.major, self.minor + 1, 0)
        if kind == "patch":
            return Version(self.major, self.minor, self.patch + 1)
        raise ValueError(f"Unknown bump kind: {kind!r}")

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"
