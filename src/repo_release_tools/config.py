"""Configuration loading for rrt."""

from __future__ import annotations

import re
import tomllib

from dataclasses import dataclass
from pathlib import Path


DEFAULT_RELEASE_BRANCH = "release/v{version}"
DEFAULT_CHANGELOG = "CHANGELOG.md"
DEFAULT_LOCK_COMMAND = ["uv", "lock", "-U"]


@dataclass(frozen=True)
class VersionTarget:
    """A single version target."""

    path: Path
    kind: str | None = None
    pattern: str | None = None
    section: str | None = None
    field: str | None = None

    def validate(self) -> None:
        """Validate target shape."""
        if self.kind == "pep621":
            return
        if self.pattern:
            re.compile(self.pattern)
            return
        if self.section and self.field:
            return
        raise ValueError(
            "Each version target must define either kind='pep621', pattern, or section+field"
        )


@dataclass(frozen=True)
class RrtConfig:
    """Loaded rrt configuration."""

    root: Path
    release_branch: str
    changelog_file: Path
    lock_command: list[str]
    version_targets: list[VersionTarget]


def load_config(root: Path) -> RrtConfig:
    """Load [tool.rrt] from pyproject.toml."""
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        raise FileNotFoundError(f"Missing pyproject.toml in {root}")

    with pyproject.open("rb") as handle:
        data = tomllib.load(handle)

    tool = data.get("tool", {})
    raw = tool.get("rrt")
    if raw is None:
        raise ValueError("Missing [tool.rrt] configuration in pyproject.toml")

    raw_targets = raw.get("version_targets", [])
    if not raw_targets:
        raise ValueError("Missing [[tool.rrt.version_targets]] configuration")

    targets: list[VersionTarget] = []
    for item in raw_targets:
        target = VersionTarget(
            path=root / item["path"],
            kind=item.get("kind"),
            pattern=item.get("pattern"),
            section=item.get("section"),
            field=item.get("field"),
        )
        target.validate()
        targets.append(target)

    lock_command = raw.get("lock_command", DEFAULT_LOCK_COMMAND)
    if not isinstance(lock_command, list) or not all(
        isinstance(part, str) for part in lock_command
    ):
        raise ValueError("tool.rrt.lock_command must be a list of strings")

    return RrtConfig(
        root=root,
        release_branch=raw.get("release_branch", DEFAULT_RELEASE_BRANCH),
        changelog_file=root / raw.get("changelog_file", DEFAULT_CHANGELOG),
        lock_command=lock_command,
        version_targets=targets,
    )
