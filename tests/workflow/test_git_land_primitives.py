"""Tests for the checked git primitives behind `rrt git land` and generated-path awareness.

Every test runs against a real temporary repository: the behaviours under test
(exit 128 vs 1, ``-z`` rename pairs, prunable worktrees, pathspec magic) are
git's, so a mock would only restate the assumption being checked.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from repo_fixtures import init_git_repo

from repo_release_tools.workflow import git


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _commit(root: Path, rel: str, text: str, message: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    _git(root, "add", "--", rel)
    _git(root, "commit", "-q", "-m", message)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root, branch="main")
    _commit(root, "src/app.py", "one\n", "feat: one")
    _commit(root, "docs/HANDOFF.md", "head one\n", "docs: handoff")
    _commit(root, "src/app.py", "two\n", "feat: two")
    return root


# ── is_ancestor ──────────────────────────────────────────────────────────────


def test_is_ancestor_true_false(repo: Path) -> None:
    assert git.is_ancestor(repo, "HEAD~1", "HEAD") is True
    assert git.is_ancestor(repo, "HEAD", "HEAD") is True
    assert git.is_ancestor(repo, "HEAD", "HEAD~1") is False


def test_is_ancestor_unknown_ref_raises_instead_of_reading_as_no(repo: Path) -> None:
    with pytest.raises(RuntimeError, match=r"exit 128"):
        git.is_ancestor(repo, "does-not-exist", "HEAD")


def test_is_ancestor_rejects_option_like_ref(repo: Path) -> None:
    with pytest.raises(ValueError, match="must not start with '-'"):
        git.is_ancestor(repo, "--help", "HEAD")


def test_is_ancestor_error_without_output_has_no_detail(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        git.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 2, stdout="", stderr=""),
    )
    with pytest.raises(RuntimeError, match=r"failed \(exit 2\)$"):
        git.is_ancestor(tmp_path, "a", "b")


# ── worktree_list ────────────────────────────────────────────────────────────


def test_worktree_list_main_first_with_flags(repo: Path, tmp_path: Path) -> None:
    feature = tmp_path / "wt-feature"
    gone = tmp_path / "wt-gone"
    _git(repo, "worktree", "add", "-q", str(feature), "-b", "feat/x")
    _git(repo, "worktree", "lock", "--reason", "busy", str(feature))
    _git(repo, "worktree", "add", "-q", "--detach", str(gone))
    subprocess.run(["rm", "-rf", str(gone)], check=True)

    worktrees = git.worktree_list(repo)

    assert [wt.branch for wt in worktrees] == ["main", "feat/x", None]
    assert worktrees[0].path.resolve() == repo.resolve()
    assert worktrees[0].head == _git(repo, "rev-parse", "HEAD")
    assert worktrees[1].locked is True and worktrees[1].prunable is False
    assert worktrees[2].detached is True and worktrees[2].prunable is True


def test_worktree_list_bare_repository(tmp_path: Path) -> None:
    bare = tmp_path / "bare.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    (worktree,) = git.worktree_list(bare)
    assert worktree.bare is True
    assert worktree.branch is None


def test_worktree_list_skips_blocks_without_worktree_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(git, "capture_checked", lambda cmd, cwd: "")
    assert git.worktree_list(tmp_path) == []


def test_worktree_list_outside_repo_raises(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError):
        git.worktree_list(tmp_path)


# ── dirty_entries / split_generated ──────────────────────────────────────────


def test_dirty_entries_parses_modified_rename_and_nested_untracked(repo: Path) -> None:
    (repo / "docs" / "HANDOFF.md").write_text("head two\n", encoding="utf-8")
    _git(repo, "mv", "src/app.py", "src/main.py")
    (repo / "new" / "deep").mkdir(parents=True)
    (repo / "new" / "deep" / "x.txt").write_text("x\n", encoding="utf-8")

    entries = git.dirty_entries(repo)

    by_path = {entry.path: entry for entry in entries}
    assert by_path["docs/HANDOFF.md"].status == " M"
    assert by_path["src/main.py"].status == "R "
    assert by_path["src/main.py"].orig_path == "src/app.py"
    assert by_path["new/deep/x.txt"].untracked is True
    assert by_path["docs/HANDOFF.md"].untracked is False


def test_dirty_entries_clean_tree_is_empty(repo: Path) -> None:
    assert git.dirty_entries(repo) == []


def test_dirty_entries_outside_repo_raises(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="git status"):
        git.dirty_entries(tmp_path)


def test_split_generated_uses_git_glob_matching(repo: Path) -> None:
    (repo / "docs" / "HANDOFF.md").write_text("head two\n", encoding="utf-8")
    (repo / "src" / "app.py").write_text("three\n", encoding="utf-8")
    (repo / "docs" / "nested").mkdir()
    (repo / "docs" / "nested" / "deep.md").write_text("x\n", encoding="utf-8")

    other, generated = git.split_generated(repo, ["docs/*.md"])

    assert [entry.path for entry in generated] == ["docs/HANDOFF.md"]
    # `*` stops at `/` under glob magic, so docs/nested/deep.md stays "other".
    assert sorted(entry.path for entry in other) == ["docs/nested/deep.md", "src/app.py"]


def test_split_generated_from_subdirectory_is_root_anchored(repo: Path) -> None:
    (repo / "docs" / "HANDOFF.md").write_text("head two\n", encoding="utf-8")
    other, generated = git.split_generated(repo / "src", ["docs/HANDOFF.md"])
    assert other == []
    assert [entry.path for entry in generated] == ["docs/HANDOFF.md"]


def test_split_generated_without_patterns_marks_nothing(repo: Path) -> None:
    (repo / "docs" / "HANDOFF.md").write_text("head two\n", encoding="utf-8")
    other, generated = git.split_generated(repo, [])
    assert generated == []
    assert [entry.path for entry in other] == ["docs/HANDOFF.md"]


def test_pathspec_builders() -> None:
    assert git.generated_pathspecs(["a/*.md"]) == [":(top,glob)a/*.md"]
    assert git.generated_pathspecs(["a"], exclude=True) == [":(top,exclude,glob)a"]
    assert git.literal_pathspecs(["a[1].md"]) == [":(top,literal)a[1].md"]


# ── commits_since ────────────────────────────────────────────────────────────


def test_commits_since_excludes_the_generated_file(repo: Path) -> None:
    root_commit = _git(repo, "rev-list", "--max-parents=0", "HEAD")

    everything = git.commits_since(repo, root_commit)
    without_handoff = git.commits_since(repo, root_commit, exclude=["docs/HANDOFF.md"])

    assert [line.split(" ", 1)[1] for line in everything] == ["feat: two", "docs: handoff"]
    assert [line.split(" ", 1)[1] for line in without_handoff] == ["feat: two"]


def test_commits_since_limited_to_paths_from_subdirectory(repo: Path) -> None:
    root_commit = _git(repo, "rev-list", "--max-parents=0", "HEAD")
    lines = git.commits_since(repo / "src", root_commit, paths=["docs/**"])
    assert [line.split(" ", 1)[1] for line in lines] == ["docs: handoff"]


def test_commits_since_up_to_date_is_empty(repo: Path) -> None:
    assert git.commits_since(repo, "HEAD") == []


def test_commits_since_unknown_ref_raises_instead_of_empty(repo: Path) -> None:
    with pytest.raises(RuntimeError, match=r"exit 128"):
        git.commits_since(repo, "no-such-ref")


def test_commits_since_rejects_option_like_ref(repo: Path) -> None:
    with pytest.raises(ValueError):
        git.commits_since(repo, "--all")
