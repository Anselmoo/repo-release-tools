"""`rrt git land` against real repositories with real worktrees.

The hazards `land` exists for (fast-forward location, `branch -d` merged-ness,
running inside the worktree being removed, hooks re-dirtying a tree) are git
behaviours, so these tests drive git rather than mocking it. Monkeypatching
is limited to failure branches git will not produce on demand.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import pytest
from repo_fixtures import init_git_repo

from repo_release_tools.commands import git_land
from repo_release_tools.commands.git_land import LandError, LandOptions, apply_land, plan_land
from repo_release_tools.workflow import git

_PYPROJECT = """\
[project]
name = "x"
version = "0.1.0"

[tool.rrt]

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[tool.rrt.git]
generated = ["HANDOFF.md", "tmp/**"]
"""


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _commit(root: Path, rel: str, text: str, message: str) -> None:
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_text(text, encoding="utf-8")
    _git(root, "add", "--", rel)
    _git(root, "commit", "-q", "-m", message)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Main worktree on `main` plus a `feat/x` worktree one commit ahead."""
    main = tmp_path / "main"
    main.mkdir()
    init_git_repo(main, branch="main")
    _commit(main, "pyproject.toml", _PYPROJECT, "chore: init")
    _commit(main, "HANDOFF.md", "head: one\n", "docs: handoff")
    _git(main, "worktree", "add", "-q", str(tmp_path / "wt"), "-b", "feat/x")
    _commit(tmp_path / "wt", "feature.txt", "work\n", "feat: x")
    return main


def _wt(repo: Path) -> Path:
    return repo.parent / "wt"


def _args(branch: str = "feat/x", **overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "branch": branch,
        "onto": "main",
        "restore_generated": False,
        "keep_branch": False,
        "dry_run": False,
        "verbose": 0,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _heads(repo: Path) -> set[str]:
    return set(_git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads").split())


# ── happy paths ──────────────────────────────────────────────────────────────


def test_land_from_inside_the_worktree_it_removes(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    feature_sha = _git(_wt(repo), "rev-parse", "HEAD")
    monkeypatch.chdir(_wt(repo))

    assert git_land.cmd_land(_args()) == 0

    assert _git(repo, "rev-parse", "main") == feature_sha
    assert not _wt(repo).exists()
    assert _heads(repo) == {"main"}
    out = capsys.readouterr().out
    assert "fast-forward: git merge --ff-only" in out
    assert "Worktrees: 2 → 1" in out
    assert "Branches: 2 → 1" in out
    assert "Your working directory was removed" in out
    assert "Done." in out


def test_onto_checked_out_nowhere_uses_compare_and_swap(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _git(repo, "checkout", "-q", "-b", "parking")
    feature_sha = _git(_wt(repo), "rev-parse", "HEAD")
    monkeypatch.chdir(repo)

    assert git_land.cmd_land(_args()) == 0

    assert _git(repo, "rev-parse", "main") == feature_sha
    out = capsys.readouterr().out
    assert "git update-ref refs/heads/main" in out
    assert "Your working directory was removed" not in out


def test_restore_generated_restores_tracked_and_deletes_untracked(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (_wt(repo) / "HANDOFF.md").write_text("head: regenerated\n")
    (_wt(repo) / "tmp" / "deep").mkdir(parents=True)
    (_wt(repo) / "tmp" / "deep" / "cache.json").write_text("{}\n")
    monkeypatch.chdir(repo)

    assert git_land.cmd_land(_args(restore_generated=True)) == 0
    assert not _wt(repo).exists()


def test_restore_generated_handles_staged_new_file(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A staged-but-new generated file (status `A `) is absent from HEAD yet restorable."""
    (_wt(repo) / "tmp").mkdir()
    (_wt(repo) / "tmp" / "staged.json").write_text("{}\n")
    _git(_wt(repo), "add", "tmp/staged.json")
    monkeypatch.chdir(repo)

    assert git_land.cmd_land(_args(restore_generated=True)) == 0
    assert not _wt(repo).exists()


def test_rename_into_generated_path_is_refused(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _git(_wt(repo), "mv", "feature.txt", "HANDOFF.md", "-f")
    monkeypatch.chdir(repo)
    _refused(capsys, _args(restore_generated=True), "has uncommitted changes")


def test_dry_run_changes_nothing(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (_wt(repo) / "HANDOFF.md").write_text("head: regenerated\n")
    (_wt(repo) / "tmp").mkdir()
    (_wt(repo) / "tmp" / "x").write_text("x\n")
    main_before = _git(repo, "rev-parse", "main")
    monkeypatch.chdir(repo)

    assert git_land.cmd_land(_args(restore_generated=True, dry_run=True)) == 0

    assert _git(repo, "rev-parse", "main") == main_before
    assert _wt(repo).exists() and (_wt(repo) / "tmp" / "x").exists()
    assert _heads(repo) == {"main", "feat/x"}
    out = capsys.readouterr().out
    assert "[DRY RUN] Land feat/x onto main" in out
    assert "Would run: git restore" in out
    assert "Would run: rm --" in out
    assert "[dry-run] complete" in out
    assert "Worktrees:" not in out


def test_keep_branch(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(repo)
    assert git_land.cmd_land(_args(keep_branch=True)) == 0
    assert _heads(repo) == {"main", "feat/x"}
    assert not _wt(repo).exists()


def test_rerun_after_partial_failure_skips_finished_steps(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Fast-forward done, worktree gone: a re-run only deletes the branch."""
    _git(repo, "merge", "-q", "--ff-only", "feat/x")
    _git(repo, "worktree", "remove", str(_wt(repo)))
    monkeypatch.chdir(repo)

    assert git_land.cmd_land(_args()) == 0

    out = capsys.readouterr().out
    assert "fast-forward: skipped (main already contains feat/x)" in out
    assert "remove-worktree: skipped (no worktree for feat/x)" in out
    assert _heads(repo) == {"main"}


def test_prunable_worktree_is_pruned(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    subprocess.run(["rm", "-rf", str(_wt(repo))], check=True)
    monkeypatch.chdir(repo)
    assert git_land.cmd_land(_args()) == 0
    assert len(git.worktree_list(repo)) == 1


# ── refusals before any change ───────────────────────────────────────────────


def _refused(capsys: pytest.CaptureFixture[str], args: argparse.Namespace, *expected: str) -> None:
    assert git_land.cmd_land(args) == 1
    err = capsys.readouterr().err
    for text in expected:
        assert text in err


def test_refuses_non_fast_forward(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _commit(repo, "other.txt", "x\n", "feat: diverge")
    monkeypatch.chdir(repo)
    _refused(capsys, _args(), "cannot be fast-forwarded", "Rebase 'feat/x' onto 'main' first")
    assert _wt(repo).exists()


def test_refuses_non_generated_dirt(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (_wt(repo) / "feature.txt").write_text("uncommitted\n")
    (_wt(repo) / "HANDOFF.md").write_text("head: regenerated\n")
    monkeypatch.chdir(repo)
    _refused(capsys, _args(restore_generated=True), "has uncommitted changes", "M feature.txt")
    assert (_wt(repo) / "HANDOFF.md").read_text() == "head: regenerated\n"


def test_refuses_generated_dirt_without_flag(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (_wt(repo) / "HANDOFF.md").write_text("head: regenerated\n")
    monkeypatch.chdir(repo)
    _refused(capsys, _args(), "generated paths only", "Pass --restore-generated")


def test_refuses_locked_worktree(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _git(repo, "worktree", "lock", str(_wt(repo)))
    monkeypatch.chdir(repo)
    _refused(capsys, _args(), "is locked", "git worktree unlock")


def test_refuses_in_progress_operation(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    git_dir = Path(_git(_wt(repo), "rev-parse", "--absolute-git-dir"))
    (git_dir / "MERGE_HEAD").write_text(_git(repo, "rev-parse", "main") + "\n")
    monkeypatch.chdir(repo)
    _refused(capsys, _args(), "A merge is in progress")


def test_refuses_branch_checked_out_in_main_worktree(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _git(repo, "checkout", "-q", "-b", "feat/y")
    monkeypatch.chdir(repo)
    _refused(capsys, _args("feat/y"), "is checked out in the main worktree")


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (_args("main"), "Cannot land 'main' onto itself"),
        (_args("feat/missing"), "Local branch 'feat/missing' not found"),
        (_args(onto="develop"), "Local branch 'develop' not found"),
        (_args("-x"), "must not start with '-'"),
    ],
)
def test_refuses_bad_names(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    args: argparse.Namespace,
    message: str,
) -> None:
    monkeypatch.chdir(repo)
    _refused(capsys, args, message)


def test_refuses_outside_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    _refused(capsys, _args(), "is not inside a Git work tree")


def test_refuses_bad_generated_config(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (_wt(repo) / "pyproject.toml").write_text(_PYPROJECT.replace('["HANDOFF.md", "tmp/**"]', "5"))
    _git(_wt(repo), "commit", "-qam", "chore: break config")
    monkeypatch.chdir(repo)
    _refused(capsys, _args(), "Failed to load [tool.rrt.git]")


def test_git_error_during_planning_exits_1(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(repo)

    def boom(cwd: Path) -> list[git.Worktree]:
        raise RuntimeError("git worktree list failed (exit 128)")

    monkeypatch.setattr(git_land.git, "worktree_list", boom)
    _refused(capsys, _args(), "git worktree list failed")


# ── failures while applying ──────────────────────────────────────────────────


def test_failed_step_stops_and_reports_rerun_hint(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`merge --ff-only` refuses when main's dirt overlaps the incoming file."""
    (repo / "feature.txt").write_text("in the way\n")
    monkeypatch.chdir(repo)

    assert git_land.cmd_land(_args()) == 1

    captured = capsys.readouterr()
    assert "fast-forward:" in captured.err
    assert "remove-worktree: not run" in captured.err
    assert "run the same command again" in captured.err
    assert _wt(repo).exists()
    assert _heads(repo) == {"main", "feat/x"}


def test_delete_branch_rechecks_containment(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = plan_land(repo, LandOptions(branch="feat/x"))
    real = git.is_ancestor
    monkeypatch.setattr(
        git_land.git,
        "is_ancestor",
        lambda cwd, a, d: False if a == "refs/heads/feat/x" else real(cwd, a, d),
    )

    outcome = apply_land(plan, dry_run=False)

    assert outcome.ok is False
    assert outcome.results[-1].status == "failed"
    assert "not contained in 'main'" in (outcome.error or "")
    assert _heads(repo) == {"main", "feat/x"}


def test_counts_are_none_when_git_fails_after_apply(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = plan_land(repo, LandOptions(branch="feat/x", keep_branch=True))

    def boom(cwd: Path) -> list[git.Worktree]:
        raise RuntimeError("gone")

    monkeypatch.setattr(git_land.git, "worktree_list", boom)
    outcome = apply_land(plan, dry_run=False)
    assert outcome.ok is True
    assert outcome.worktrees_after is None
    assert outcome.branches_after is None


def test_land_error_details_default_to_empty() -> None:
    assert LandError("x").details == []


def test_parser_wiring() -> None:
    from repo_release_tools.cli import build_parser

    args = build_parser().parse_args(
        ["git", "land", "feat/x", "--onto", "develop", "--restore-generated", "--dry-run"]
    )
    assert args.handler is git_land.cmd_land
    opts = LandOptions.from_args(args)
    assert (opts.branch, opts.onto, opts.restore_generated, opts.keep_branch, opts.dry_run) == (
        "feat/x",
        "develop",
        True,
        False,
        True,
    )
