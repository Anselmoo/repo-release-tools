"""Smoke test proving the e2e harness itself works on all surfaces."""

from __future__ import annotations

from pathlib import Path

import pytest
from harness import rrt, rrt_hooks

pytestmark = pytest.mark.e2e


def test_cli_surface_reachable(e2e_repo: Path) -> None:
    """The rrt CLI runs as a subprocess inside a fixture repo."""
    result = rrt("bump", "patch", "--dry-run", cwd=e2e_repo)
    assert result.returncode == 0, result.stderr
    assert "0.1.1" in result.stdout


def test_hooks_surface_reachable(e2e_repo: Path) -> None:
    """The rrt-hooks surface validates a compliant branch name."""
    result = rrt_hooks("check-branch-name", "--branch", "feat/add-parser", cwd=e2e_repo)
    assert result.returncode == 0, result.stderr
