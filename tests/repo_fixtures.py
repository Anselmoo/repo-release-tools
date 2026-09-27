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


def commit_as(root: Path, message: str, *, author: str = "Tester", tag: str | None = None) -> None:
    """Commit a one-line change as *author* and optionally tag the new commit.

    Each call appends a line to ``history.txt`` so every commit is non-empty,
    then creates a lightweight *tag* on it when given.
    """
    history = root / "history.txt"
    with history.open("a", encoding="utf-8") as fh:
        fh.write(f"{message}\n")
    subprocess.run(["git", "add", "history.txt"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            f"user.name={author}",
            "-c",
            f"user.email={author.lower()}@example.com",
            "commit",
            "-q",
            "-m",
            message,
        ],
        cwd=root,
        check=True,
        capture_output=True,
    )
    if tag is not None:
        subprocess.run(["git", "tag", tag], cwd=root, check=True, capture_output=True)


def init_two_prefix_history(root: Path) -> None:
    """Build a repo holding interleaved ``v*`` and ``sdk-v*`` release tags.

    History, oldest first::

        chore: seed              (Tester)  tag v1.0.0-rc.1
        fix: rc feedback         (Carol)   tag v1.0.0, sdk-v2.0.0-rc.1
        feat: core after v1      (Alice)   tag sdk-v2.0.0
        feat: sdk after sdk-v2   (Bob)     tag vnext

    The default ``v`` group's range starts at ``v1.0.0``: a final outranks its
    own ``rc.1`` and ``vnext`` is not a version.  The ``sdk-v`` group's range
    starts at ``sdk-v2.0.0``, which outranks the newer-named ``sdk-v2.0.0-rc.1``.
    """
    init_git_repo(root)
    commit_as(root, "chore: seed", tag="v1.0.0-rc.1")
    commit_as(root, "fix: rc feedback", author="Carol", tag="v1.0.0")
    subprocess.run(["git", "tag", "sdk-v2.0.0-rc.1"], cwd=root, check=True, capture_output=True)
    commit_as(root, "feat: core after v1", author="Alice", tag="sdk-v2.0.0")
    commit_as(root, "feat: sdk after sdk-v2", author="Bob", tag="vnext")
