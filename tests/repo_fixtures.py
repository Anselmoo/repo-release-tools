"""Shared repo-bootstrap helpers used by two or more test modules.

`init_git_repo` and `make_repo` were each reimplemented under a different
private name (or, for `make_repo`, copy-pasted verbatim) across several test
files. They live here instead so tests build synthetic repos the same way.
This module holds no tests of its own; it is not collected by pytest.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def init_git_repo(root: Path, *, branch: str | None = None) -> None:
    """Initialize a minimal git repo with a committer identity for tests."""
    init_cmd = ["git", "init", "-q"] if branch is None else ["git", "init", "-b", branch]
    subprocess.run(init_cmd, cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@example.com"], cwd=root, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Tester"], cwd=root, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "commit.gpgsign", "false"], cwd=root, check=True, capture_output=True
    )


def make_repo(tmp_path: Path, layout: dict[str, str]) -> Path:
    """Build a synthetic (non-git) project under tmp_path; return repo root."""
    for rel, contents in layout.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(contents, encoding="utf-8")
    return tmp_path
