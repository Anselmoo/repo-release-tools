#!/usr/bin/env python3
"""Claude Stop hook: block when expected hooks, agents, or skills are missing."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REQUIRED_PATHS = (
    Path(".claude/hooks/coverage_non_regression.py"),
    Path(".claude/hooks/refresh_coverage_baseline.py"),
    Path(".claude/hooks/drift_guard.py"),
    Path(".claude/hooks/rrt_ux_guard.py"),
    Path(".claude/hooks/rrt_ux_write_guard.py"),
    Path(".github/agents/rrt-user-bootstrap.agent.md"),
    Path(".github/agents/rrt-user-version-planner.agent.md"),
    Path(".github/agents/rrt-user-release-readiness.agent.md"),
    Path(".github/agents/rrt-user-branch-guard.agent.md"),
    Path(".github/agents/rrt-user-commit-lint-triage.agent.md"),
    Path(".github/agents/rrt-user-changelog-curator.agent.md"),
    Path(".github/agents/rrt-user-config-validator.agent.md"),
    Path(".github/agents/rrt-user-docs-sync-auditor.agent.md"),
    Path(".github/agents/rrt-user-ci-failure-triage.agent.md"),
    Path(".github/agents/rrt-user-upgrade-assistant.agent.md"),
    Path(".github/skills/rrt-user-bootstrap/SKILL.md"),
    Path(".github/skills/rrt-user-versioning/SKILL.md"),
    Path(".github/skills/rrt-user-release-flow/SKILL.md"),
    Path(".github/skills/rrt-user-branch-strategy/SKILL.md"),
    Path(".github/skills/rrt-user-commit-quality/SKILL.md"),
    Path(".github/skills/rrt-user-changelog-automation/SKILL.md"),
    Path(".github/skills/rrt-user-docs-consistency/SKILL.md"),
    Path(".github/skills/rrt-user-config-safety/SKILL.md"),
    Path(".github/skills/rrt-user-ci-readiness/SKILL.md"),
    Path(".github/skills/rrt-user-migration-uvx-to-installed/SKILL.md"),
    Path(".github/hooks/rrt_user_branch_policy.py"),
    Path(".github/hooks/rrt_user_commit_policy.py"),
    Path(".github/hooks/rrt_user_changelog_policy.py"),
    Path(".github/hooks/rrt_user_release_readiness.py"),
    Path(".github/hooks/rrt_user_config_sanity.py"),
    Path(".github/hooks/rrt_user_docs_sync_hint.py"),
    Path(".github/hooks/rrt_user_dirty_tree_guard.py"),
    Path(".github/hooks/rrt_user_version_drift_guard.py"),
    Path(".github/hooks/rrt_user_ci_local_preflight.py"),
    Path(".github/hooks/rrt_user_security_hygiene_hint.py"),
)


def _block(reason: str) -> int:
    payload = {"decision": "block", "reason": reason}
    print(json.dumps(payload, ensure_ascii=False))
    return 2


def main() -> int:
    """Block when required shipped agent surfaces are missing."""
    _ = sys.stdin.read()

    root = Path.cwd()
    if missing := [str(path) for path in REQUIRED_PATHS if not (root / path).exists()]:
        joined = ", ".join(missing)
        return _block(f"Missing required agent surfaces: {joined}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
