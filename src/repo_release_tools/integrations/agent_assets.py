"""Bundled user agent definitions shipped with repo-release-tools."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from sysconfig import get_path
from typing import Optional


@dataclass(frozen=True)
class BundledAgent:
    """A bundled agent definition distributed with the CLI."""

    name: str
    markdown: str
    family: Optional[str] = None


# Names of all user-facing agents bundled in the package assets.
_AGENT_NAMES: tuple[str, ...] = (
    "rrt-user-bootstrap",
    "rrt-user-version-planner",
    "rrt-user-release-readiness",
    "rrt-user-branch-guard",
    "rrt-user-commit-lint-triage",
    "rrt-user-changelog-curator",
    "rrt-user-config-validator",
    "rrt-user-docs-sync-auditor",
    "rrt-user-ci-failure-triage",
    "rrt-user-upgrade-assistant",
)


def _parse_family(markdown: str) -> Optional[str]:
    r"""Extract a family name from agent markdown.

    Supports YAML frontmatter (---\nkey: val\n---) or a top-of-file
    `family: <name>` line. Returns None when not present.
    """
    lines = markdown.splitlines()
    if not lines:
        return None

    # YAML frontmatter
    if lines[0].strip() == "---":
        # find closing frontmatter
        try:
            end = lines[1:].index("---") + 1
        except ValueError:
            end = None
        if end:
            for line in lines[1:end]:
                if line.strip().startswith("family:"):
                    return line.split(":", 1)[1].strip()
    # Fallback: scan first 40 lines for `family:`
    for line in lines[:40]:
        if line.strip().startswith("family:"):
            return line.split(":", 1)[1].strip()
    return None


def _load_agent(name: str) -> BundledAgent:
    """Load an agent's .agent.md from wheel data or fallback sources."""
    filename = f"{name}.agent.md"
    repo_root = Path(__file__).resolve().parents[3]
    path_candidates = [
        Path(get_path("data", vars={})) / filename,
        repo_root / ".github" / "agents" / filename,
    ]

    candidate = next((p for p in path_candidates if p.is_file()), None)
    if candidate is not None:
        text = candidate.read_text(encoding="utf-8")
        family = _parse_family(text)
        return BundledAgent(name=name, markdown=text, family=family)

    searched = ", ".join(str(p) for p in path_candidates)
    raise FileNotFoundError(f"Could not locate bundled agent {name!r}. Searched: {searched}")


# All bundled agents, in name order.
BUNDLED_AGENTS: list[BundledAgent] = [_load_agent(name) for name in _AGENT_NAMES]
