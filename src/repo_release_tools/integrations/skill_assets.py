"""Bundled user skills shipped with repo-release-tools."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from sysconfig import get_path


@dataclass(frozen=True)
class BundledSkill:
    """A bundled agent skill distributed with the CLI."""

    name: str
    markdown: str


# Names of all user-facing skills bundled in the package assets.
_SKILL_NAMES: tuple[str, ...] = (
    "rrt-user-bootstrap",
    "rrt-user-versioning",
    "rrt-user-release-flow",
    "rrt-user-branch-strategy",
    "rrt-user-commit-quality",
    "rrt-user-changelog-automation",
    "rrt-user-docs-consistency",
    "rrt-user-config-safety",
    "rrt-user-ci-readiness",
    "rrt-user-migration-uvx-to-installed",
)


def _load_skill(name: str) -> BundledSkill:
    """Load a skill's SKILL.md from wheel data or source-owned assets."""
    repo_root = Path(__file__).resolve().parents[3]
    path_candidates = [
        Path(get_path("purelib", vars={})) / name / "SKILL.md",
        Path(get_path("purelib", vars={})) / "skills" / name / "SKILL.md",
        Path(get_path("purelib", vars={})) / ".github" / "skills" / name / "SKILL.md",
        repo_root / ".github" / "skills" / name / "SKILL.md",
    ]

    candidate = next((p for p in path_candidates if p.is_file()), None)
    if candidate is not None:
        return BundledSkill(name=name, markdown=candidate.read_text(encoding="utf-8"))

    searched = ", ".join(str(p) for p in path_candidates)
    raise FileNotFoundError(f"Could not locate bundled skill {name!r}. Searched: {searched}")


# All bundled skills, in name-sorted order.
BUNDLED_SKILLS: list[BundledSkill] = [_load_skill(name) for name in _SKILL_NAMES]
