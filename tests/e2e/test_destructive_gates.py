"""e2e characterization: gates in front of destructive/irreversible git operations.

Pins MODERNIZATION_BRIEF.md §5 contract items:

- C3  `rrt git publish-snapshot` safety gates
      (src/repo_release_tools/commands/git_sync.py:393-503, workflow/git.py:255-342)
- C4  `rrt git rebootstrap` explicit-confirmation + remote guard
      (commands/git_sync.py:235-274)
- C5  tag/branch overwrite refusal (commands/tag.py:132-176, commands/branch.py:191-197)
- C12 auto-stash lifecycle in `rrt git move` / `rrt git sync`
      (commands/git_sync.py:70-209)

All remotes are local bare repositories - no network is touched.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from harness import git, rrt, rrt_env, run

pytestmark = pytest.mark.e2e

CONFIRM_PUSH = "--yes-i-know-this-overwrites-remote-history"
CONFIRM_DESTROY = "--yes-i-know-this-destroys-history"


def _out(result: subprocess.CompletedProcess[str]) -> str:
    """Assertion-message payload: always show both streams on failure."""
    return f"rc={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"


def _bare_repo(path: Path) -> Path:
    """Create a local bare repository to stand in for a remote."""
    git("init", "--bare", "-b", "main", str(path), cwd=path.parent)
    return path


def _add_origin(repo: Path, bare: Path) -> None:
    """Wire *bare* as origin and push main with upstream tracking."""
    git("remote", "add", "origin", str(bare), cwd=repo)
    git("push", "-u", "origin", "main", cwd=repo)


def _bare_refs(bare: Path) -> str:
    """All refs currently present in a bare remote (empty string = nothing pushed)."""
    return run(["git", "for-each-ref"], cwd=bare).stdout.strip()


# ---------------------------------------------------------------------------
# C3 - publish-snapshot safety gates
# ---------------------------------------------------------------------------


def test_c3_publish_snapshot_without_confirm_downgrades_to_dry_run(
    e2e_repo: Path, tmp_path: Path
) -> None:
    """Without the confirm flag the command exits 0 as a preview and pushes nothing."""
    snap = _bare_repo(tmp_path / "snap.git")
    _add_origin(e2e_repo, _bare_repo(tmp_path / "origin.git"))

    result = rrt("git", "publish-snapshot", "--remote", str(snap), cwd=e2e_repo)

    # NOTE(P1): the downgrade is *silent success* - exit 0, not an error. A user
    # scripting `rrt git publish-snapshot && deploy` gets a green pipeline with
    # nothing actually published. Pinned as-is per the brief (C3a).
    assert result.returncode == 0, _out(result)
    assert "[DRY RUN]" in result.stdout, _out(result)
    assert f"Refusing to push without {CONFIRM_PUSH}" in result.stdout, _out(result)
    assert "nothing was pushed" in result.stdout, _out(result)
    assert _bare_refs(snap) == "", (
        f"snapshot remote gained refs:\n{_bare_refs(snap)}\n{_out(result)}"
    )


def test_c3_publish_snapshot_with_confirm_pushes_single_commit_snapshot(
    e2e_repo: Path, tmp_path: Path
) -> None:
    """With the confirm flag: one-commit snapshot pushed; local repo fully restored."""
    snap = _bare_repo(tmp_path / "snap.git")
    _add_origin(e2e_repo, _bare_repo(tmp_path / "origin.git"))

    result = rrt("git", "publish-snapshot", "--remote", str(snap), CONFIRM_PUSH, cwd=e2e_repo)

    assert result.returncode == 0, _out(result)
    assert "Pushed a single-commit snapshot" in result.stdout, _out(result)
    assert "refs/heads/main" in _bare_refs(snap), f"{_bare_refs(snap)}\n{_out(result)}"
    count = run(["git", "rev-list", "--count", "refs/heads/main"], cwd=snap)
    assert count.stdout.strip() == "1", _out(count)
    # local repo restored: back on main, temp snapshot branch deleted
    branch = git("branch", "--show-current", cwd=e2e_repo)
    assert branch.stdout.strip() == "main", _out(branch)
    branches = git("branch", "--list", "rrt-snapshot-tmp-*", cwd=e2e_repo)
    assert branches.stdout.strip() == "", _out(branches)


def test_c3_publish_snapshot_refuses_remote_with_same_url_as_origin(
    e2e_repo: Path, tmp_path: Path
) -> None:
    """A remote that resolves to origin's URL is refused even when confirmed."""
    origin = _bare_repo(tmp_path / "origin.git")
    _add_origin(e2e_repo, origin)
    git("remote", "add", "mirror", str(origin), cwd=e2e_repo)
    before = _bare_refs(origin)

    result = rrt("git", "publish-snapshot", "--remote", "mirror", CONFIRM_PUSH, cwd=e2e_repo)

    assert result.returncode == 1, _out(result)
    assert "Refusing to publish" in result.stderr, _out(result)
    assert "resolves to the same URL as origin" in result.stderr, _out(result)
    assert _bare_refs(origin) == before, f"origin refs changed\n{_out(result)}"


def test_c3_publish_snapshot_refuses_during_in_progress_merge(
    e2e_repo: Path, tmp_path: Path
) -> None:
    """An in-progress merge blocks publishing even with the confirm flag."""
    snap = _bare_repo(tmp_path / "snap.git")
    _add_origin(e2e_repo, _bare_repo(tmp_path / "origin.git"))
    # diverge two branches, then stop a merge before committing (MERGE_HEAD exists)
    git("checkout", "-b", "feat/side", cwd=e2e_repo)
    (e2e_repo / "side.txt").write_text("side\n", encoding="utf-8")
    git("add", ".", cwd=e2e_repo)
    git("commit", "-m", "feat: side", cwd=e2e_repo)
    git("checkout", "main", cwd=e2e_repo)
    (e2e_repo / "mainline.txt").write_text("mainline\n", encoding="utf-8")
    git("add", ".", cwd=e2e_repo)
    git("commit", "-m", "feat: mainline", cwd=e2e_repo)
    git("merge", "--no-commit", "--no-ff", "feat/side", cwd=e2e_repo)

    result = rrt("git", "publish-snapshot", "--remote", str(snap), CONFIRM_PUSH, cwd=e2e_repo)

    assert result.returncode == 1, _out(result)
    assert "Cannot publish while a merge is in progress" in result.stderr, _out(result)
    assert _bare_refs(snap) == "", f"snapshot remote gained refs\n{_out(result)}"


def test_c3_publish_snapshot_refuses_during_in_progress_rebase(
    e2e_repo: Path, tmp_path: Path
) -> None:
    """An in-progress (conflicted) rebase blocks publishing even with the confirm flag."""
    snap = _bare_repo(tmp_path / "snap.git")
    _add_origin(e2e_repo, _bare_repo(tmp_path / "origin.git"))
    conflict = e2e_repo / "conflict.txt"
    conflict.write_text("base\n", encoding="utf-8")
    git("add", ".", cwd=e2e_repo)
    git("commit", "-m", "feat: base", cwd=e2e_repo)
    git("checkout", "-b", "feat/conflicting", cwd=e2e_repo)
    conflict.write_text("feature\n", encoding="utf-8")
    git("commit", "-am", "feat: feature side", cwd=e2e_repo)
    git("checkout", "main", cwd=e2e_repo)
    conflict.write_text("mainline\n", encoding="utf-8")
    git("commit", "-am", "feat: mainline side", cwd=e2e_repo)
    git("checkout", "feat/conflicting", cwd=e2e_repo)
    rebase = run(["git", "rebase", "main"], cwd=e2e_repo)
    assert rebase.returncode != 0, f"expected conflicted rebase\n{_out(rebase)}"

    result = rrt("git", "publish-snapshot", "--remote", str(snap), CONFIRM_PUSH, cwd=e2e_repo)

    assert result.returncode == 1, _out(result)
    assert "Cannot publish while a rebase is in progress" in result.stderr, _out(result)
    assert _bare_refs(snap) == "", f"snapshot remote gained refs\n{_out(result)}"


# ---------------------------------------------------------------------------
# C4 - rebootstrap explicit confirmation + remote guard
# ---------------------------------------------------------------------------


def test_c4_rebootstrap_refuses_without_destroy_history_confirmation(e2e_repo: Path) -> None:
    """No confirm flag -> exit 1, history untouched. The gate applies even to --dry-run."""
    head_before = git("rev-parse", "HEAD", cwd=e2e_repo).stdout.strip()

    for extra in ((), ("--dry-run",)):
        result = rrt("git", "rebootstrap", *extra, cwd=e2e_repo)
        assert result.returncode == 1, _out(result)
        assert (
            f"Refusing to destroy repository history without {CONFIRM_DESTROY}" in result.stderr
        ), _out(result)

    head_after = git("rev-parse", "HEAD", cwd=e2e_repo).stdout.strip()
    assert head_after == head_before, f"history changed: {head_before} -> {head_after}"
    assert (e2e_repo / ".git").is_dir(), ".git directory disappeared"


def test_c4_rebootstrap_refuses_configured_remotes_without_allow_remote(
    e2e_repo: Path, tmp_path: Path
) -> None:
    """Confirmed rebootstrap still refuses when any remote is configured."""
    _add_origin(e2e_repo, _bare_repo(tmp_path / "origin.git"))
    head_before = git("rev-parse", "HEAD", cwd=e2e_repo).stdout.strip()

    result = rrt("git", "rebootstrap", CONFIRM_DESTROY, cwd=e2e_repo)

    assert result.returncode == 1, _out(result)
    assert "Refusing to rebootstrap a repository with configured remotes" in result.stderr, _out(
        result
    )
    assert "--allow-remote" in result.stderr, _out(result)
    head_after = git("rev-parse", "HEAD", cwd=e2e_repo).stdout.strip()
    assert head_after == head_before, f"history changed: {head_before} -> {head_after}"


def test_c4_rebootstrap_confirmed_with_allow_remote_rewrites_history_with_backup(
    e2e_repo: Path, tmp_path: Path
) -> None:
    """Fully confirmed rebootstrap: fresh single-commit history, old .git backed up."""
    _add_origin(e2e_repo, _bare_repo(tmp_path / "origin.git"))
    # the re-init loses repo-local identity config; supply it via environment
    env = rrt_env(
        GIT_AUTHOR_NAME="Repo Release Tools",
        GIT_AUTHOR_EMAIL="rrt@example.invalid",
        GIT_COMMITTER_NAME="Repo Release Tools",
        GIT_COMMITTER_EMAIL="rrt@example.invalid",
    )

    result = rrt("git", "rebootstrap", CONFIRM_DESTROY, "--allow-remote", cwd=e2e_repo, env=env)

    assert result.returncode == 0, _out(result)
    assert "Repository history reinitialized on 'main'" in result.stdout, _out(result)
    count = git("rev-list", "--count", "HEAD", cwd=e2e_repo)
    assert count.stdout.strip() == "1", _out(count)
    backups = list(e2e_repo.parent.glob(f".{e2e_repo.name}.git-backup-*"))
    assert backups, f"no .git backup created next to the repo\n{_out(result)}"
    assert (e2e_repo / "pyproject.toml").is_file(), "tracked files lost by rebootstrap"


# ---------------------------------------------------------------------------
# C5 - tag / branch overwrite refusal
# ---------------------------------------------------------------------------


def test_c5_tag_create_refuses_existing_tag_without_force(e2e_repo: Path) -> None:
    """`rrt tag create` exits 1 when the version tag already exists (config version 0.1.0)."""
    git("tag", "-a", "v0.1.0", "-m", "original annotation", cwd=e2e_repo)

    result = rrt("tag", "create", cwd=e2e_repo)

    assert result.returncode == 1, _out(result)
    assert "Tag 'v0.1.0' already exists. Use --force to overwrite." in result.stderr, _out(result)
    subject = git("tag", "-l", "--format=%(contents:subject)", "v0.1.0", cwd=e2e_repo)
    assert subject.stdout.strip() == "original annotation", _out(subject)


def test_c5_tag_create_force_deletes_then_recreates_existing_tag(e2e_repo: Path) -> None:
    """With --force the existing tag is deleted and recreated with the new annotation."""
    git("tag", "-a", "v0.1.0", "-m", "original annotation", cwd=e2e_repo)

    result = rrt("tag", "create", "--force", "--message", "replaced annotation", cwd=e2e_repo)

    assert result.returncode == 0, _out(result)
    assert "Created tag 'v0.1.0'" in result.stdout, _out(result)
    subject = git("tag", "-l", "--format=%(contents:subject)", "v0.1.0", cwd=e2e_repo)
    assert subject.stdout.strip() == "replaced annotation", _out(subject)
    tags = git("tag", "--list", cwd=e2e_repo)
    assert tags.stdout.split() == ["v0.1.0"], _out(tags)


def test_c5_branch_new_refuses_existing_branch_name(e2e_repo: Path) -> None:
    """`rrt branch new` exits 1 when the computed branch name already exists."""
    first = rrt("branch", "new", "feat", "add parser", cwd=e2e_repo)
    assert first.returncode == 0, _out(first)
    git("checkout", "main", cwd=e2e_repo)

    result = rrt("branch", "new", "feat", "add parser", cwd=e2e_repo)

    assert result.returncode == 1, _out(result)
    assert "Branch 'feat/add-parser' already exists." in result.stderr, _out(result)
    branch = git("branch", "--show-current", cwd=e2e_repo)
    assert branch.stdout.strip() == "main", _out(branch)


# ---------------------------------------------------------------------------
# C12 - auto-stash lifecycle (move / sync)
# ---------------------------------------------------------------------------

TRACKED_DIRTY = "# Changelog\n\nlocal edit \t with tabs\nand a second line\n"
UNTRACKED_BYTES = b"\x00\x01 binary-ish untracked payload\nline2\r\nno trailing newline"


def test_c12_git_move_auto_stash_restores_uncommitted_changes_byte_identical(
    e2e_repo: Path,
) -> None:
    """`rrt git move -b` stashes dirty changes, switches, and restores them exactly."""
    (e2e_repo / "CHANGELOG.md").write_text(TRACKED_DIRTY, encoding="utf-8")
    (e2e_repo / "untracked.bin").write_bytes(UNTRACKED_BYTES)

    result = rrt("git", "move", "-b", "feat/stash-lifecycle", cwd=e2e_repo)

    assert result.returncode == 0, _out(result)
    branch = git("branch", "--show-current", cwd=e2e_repo)
    assert branch.stdout.strip() == "feat/stash-lifecycle", _out(branch)
    assert (e2e_repo / "CHANGELOG.md").read_text(encoding="utf-8") == TRACKED_DIRTY
    assert (e2e_repo / "untracked.bin").read_bytes() == UNTRACKED_BYTES
    stash = git("stash", "list", cwd=e2e_repo)
    assert stash.stdout.strip() == "", f"auto-stash left on the stack\n{_out(stash)}"


def test_c12_git_sync_auto_stash_restores_uncommitted_changes_byte_identical(
    e2e_repo: Path, tmp_path: Path
) -> None:
    """`rrt git sync` stashes dirty changes, pulls the upstream commit, restores exactly."""
    origin = _bare_repo(tmp_path / "origin.git")
    _add_origin(e2e_repo, origin)
    # land a new commit upstream via a second clone
    writer = tmp_path / "writer"
    git("clone", str(origin), str(writer), cwd=tmp_path)
    git("config", "user.name", "Writer", cwd=writer)
    git("config", "user.email", "writer@example.invalid", cwd=writer)
    git("config", "commit.gpgsign", "false", cwd=writer)
    (writer / "upstream_file.txt").write_text("from upstream\n", encoding="utf-8")
    git("add", ".", cwd=writer)
    git("commit", "-m", "feat: upstream change", cwd=writer)
    git("push", "origin", "main", cwd=writer)
    # dirty the local repo (disjoint files from the upstream commit)
    (e2e_repo / "CHANGELOG.md").write_text(TRACKED_DIRTY, encoding="utf-8")
    (e2e_repo / "untracked.bin").write_bytes(UNTRACKED_BYTES)

    result = rrt("git", "sync", cwd=e2e_repo)

    assert result.returncode == 0, _out(result)
    assert (e2e_repo / "upstream_file.txt").is_file(), f"upstream commit not pulled\n{_out(result)}"
    assert (e2e_repo / "CHANGELOG.md").read_text(encoding="utf-8") == TRACKED_DIRTY
    assert (e2e_repo / "untracked.bin").read_bytes() == UNTRACKED_BYTES
    stash = git("stash", "list", cwd=e2e_repo)
    assert stash.stdout.strip() == "", f"auto-stash left on the stack\n{_out(stash)}"
