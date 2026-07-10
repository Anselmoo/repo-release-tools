"""Subprocess helpers for the e2e characterization suite.

Import from tests as ``from harness import rrt, rrt_hooks, ...`` (the test dir
is on sys.path under pytest's prepend import mode). Fixtures live in
``conftest.py``; this module holds everything importable.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "src"

CHANGELOG_TEMPLATE = """\
# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

- Seed feature entry

## [0.1.0] - 2026-01-01

### Added

- Initial release
"""

PYPROJECT_TEMPLATE = """\
[tool.rrt]
changelog_file = "CHANGELOG.md"

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[project]
name = "e2e-fixture"
version = "0.1.0"
requires-python = ">=3.12"
"""


def run(
    cmd: list[str] | tuple[str, ...],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a command, returning the completed process without asserting rc.

    Contract tests assert exit codes explicitly - gate tests need non-zero.
    """
    return subprocess.run(
        list(cmd),
        cwd=cwd,
        env=env if env is not None else rrt_env(),
        capture_output=True,
        text=True,
        check=False,
    )


def run_ok(
    cmd: list[str] | tuple[str, ...],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a command and fail the test with full output if it exits non-zero."""
    result = run(cmd, cwd=cwd, env=env)
    if result.returncode != 0:
        raise AssertionError(
            f"Command failed: {' '.join(cmd)}\n"
            f"cwd={cwd}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}",
        )
    return result


def rrt_env(**extra: str) -> dict[str, str]:
    """Environment for invoking rrt from source in a subprocess."""
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(SRC) if not existing else f"{SRC}{os.pathsep}{existing}"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.update(extra)
    return env


def rrt(
    *args: str,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Invoke the ``rrt`` CLI surface as a user would."""
    return run(
        [sys.executable, "-m", "repo_release_tools", *args],
        cwd=cwd,
        env=env,
    )


_HOOKS_SHIM = (
    "import sys; from repo_release_tools.workflow.hooks import main; sys.exit(main(sys.argv[1:]))"
)


def rrt_hooks(
    *args: str,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Invoke the ``rrt-hooks`` surface (git-hook / GitHub Action entrypoint)."""
    return run([sys.executable, "-c", _HOOKS_SHIM, *args], cwd=cwd, env=env)


def git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run git inside a fixture repo."""
    return run_ok(["git", *args], cwd=cwd)


def init_git_repo(repo: Path, *, initial_branch: str = "main") -> None:
    """git-init a fixture repo with hooks and signing disabled, and commit all."""
    git("init", "-b", initial_branch, cwd=repo)
    git("config", "user.name", "Repo Release Tools", cwd=repo)
    git("config", "user.email", "rrt@example.invalid", cwd=repo)
    git("config", "commit.gpgsign", "false", cwd=repo)
    git("config", "core.hooksPath", "/dev/null", cwd=repo)
    git("add", ".", cwd=repo)
    git("commit", "-m", "feat: initial fixture project", cwd=repo)


def make_project(repo: Path, *, pyproject: str = PYPROJECT_TEMPLATE) -> None:
    """Write the minimal rrt-configured project files into ``repo``."""
    (repo / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    (repo / "CHANGELOG.md").write_text(CHANGELOG_TEMPLATE, encoding="utf-8")
