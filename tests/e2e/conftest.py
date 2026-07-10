"""Shared fixtures for end-to-end characterization tests (modernization Phase 1).

These tests pin the behavior contract from ``analysis/the/MODERNIZATION_BRIEF.md``
§5 (items C1-C12) by exercising the product surfaces the way users do: the
``rrt`` CLI and the ``rrt-hooks`` runner as subprocesses inside temporary git
repositories. They are the safety net every later modernization phase must keep
green - a red test here means user-visible behavior changed.

Conventions:

- Every test carries ``@pytest.mark.e2e``.
- Subprocess helpers live in ``harness.py`` (``from harness import rrt, ...``).
- Subprocess coverage is not collected; run the slice alone with
  ``uv run pytest -m e2e --no-cov`` (the default full run keeps the 100%
  coverage gate because these tests add no uncovered source lines).
- Suspected defects D1-D9 (see MODERNIZATION_BRIEF.md §5) are pinned AS-IS and
  marked with a ``D<n>:`` comment at the assertion. Later phases flip those
  assertions deliberately (D8 in Phase 6a, D4/D6/D9 in Phase 5) - never
  "fix" one silently.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from harness import PYPROJECT_TEMPLATE, init_git_repo, make_project


@pytest.fixture
def e2e_repo(tmp_path: Path) -> Path:
    """A committed, rrt-configured git repository on ``main``."""
    repo = tmp_path / "project"
    repo.mkdir()
    make_project(repo)
    init_git_repo(repo)
    return repo


@pytest.fixture
def e2e_repo_factory(tmp_path: Path) -> Callable[..., Path]:
    """Factory for tests needing several repos or custom pyproject content."""

    counter = {"n": 0}

    def _make(*, pyproject: str = PYPROJECT_TEMPLATE, initial_branch: str = "main") -> Path:
        counter["n"] += 1
        repo = tmp_path / f"project{counter['n']}"
        repo.mkdir()
        make_project(repo, pyproject=pyproject)
        init_git_repo(repo, initial_branch=initial_branch)
        return repo

    return _make
