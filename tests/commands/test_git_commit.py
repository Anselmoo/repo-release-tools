from __future__ import annotations

import argparse
import pathlib

import pytest

from repo_release_tools.commands import git_commit


def test_infer_commit_type_from_branch() -> None:
    assert git_commit.infer_commit_type("feat/add-parser") == "feat"
    assert git_commit.infer_commit_type("main") is None
    assert git_commit.infer_commit_type("copilot/add-parser") is None
    assert git_commit.infer_commit_type("release/v1.2.3") is None


def test_cmd_commit_dry_run_uses_branch_type(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_commit.git, "current_branch", lambda cwd: "feat/add-parser")
    args = argparse.Namespace(
        description=["handle", "empty", "config"],
        type=None,
        scope=None,
        breaking=False,
        dry_run=True,
    )

    assert git_commit.cmd_commit(args) == 0

    captured = capsys.readouterr()
    assert "feat: handle empty config" in captured.out
    assert "[dry-run] complete" in captured.out


def test_commit_subject_render_includes_scope_and_breaking_marker() -> None:
    subject = git_commit.CommitSubject(
        type="feat",
        description="ship parser",
        scope="cli",
        breaking=True,
    )

    assert subject.render() == "feat(cli)!: ship parser"


def test_normalize_commit_subject_type_accepts_and_rejects_values() -> None:
    assert git_commit.normalize_commit_subject_type("FIX") == "fix"
    assert git_commit.infer_commit_type("wizard/add-parser") is None

    with pytest.raises(argparse.ArgumentTypeError, match="invalid commit type"):
        git_commit.normalize_commit_subject_type("wizard")


def test_resolve_commit_subject_requires_explicit_type_for_uninferable_branch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    monkeypatch.setattr(git_commit.git, "current_branch", lambda cwd: "main")
    args = argparse.Namespace(description=["ship", "it"], type=None, scope=None, breaking=False)

    with pytest.raises(ValueError, match="Use --type explicitly"):
        git_commit.resolve_commit_subject(args, tmp_path)


def test_cmd_commit_requires_explicit_type_when_branch_not_inferable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(git_commit.git, "current_branch", lambda cwd: "main")
    args = argparse.Namespace(
        description=["ship", "parser"],
        type=None,
        scope=None,
        breaking=False,
        dry_run=False,
    )

    assert git_commit.cmd_commit(args) == 1
    assert "Use --type explicitly" in capsys.readouterr().err


def test_cmd_commit_all_stages_and_commits(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(git_commit.git, "current_branch", lambda cwd: "feat/add-parser")
    commands: list[list[str]] = []
    monkeypatch.setattr(
        git_commit.git,
        "run",
        lambda cmd, cwd, *, dry_run, label: commands.append(cmd) or "",
    )
    args = argparse.Namespace(
        description=["ship", "parser"],
        type=None,
        scope=None,
        breaking=False,
        dry_run=False,
    )

    assert git_commit.cmd_commit_all(args) == 0
    assert commands == [["git", "add", "."], ["git", "commit", "-m", "feat: ship parser"]]


def test_cmd_squash_local_rejects_dirty_tree(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_commit.git, "working_tree_clean", lambda cwd: False)

    result = git_commit.cmd_squash_local(
        argparse.Namespace(
            base_ref=None,
            description=["squash"],
            type="feat",
            scope=None,
            breaking=False,
            dry_run=False,
        ),
    )

    assert result == 1
    assert "Working tree has uncommitted changes" in capsys.readouterr().err


def test_cmd_squash_local_requires_upstream_or_base(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_commit.git, "working_tree_clean", lambda cwd: True)
    monkeypatch.setattr(git_commit.git, "upstream_branch", lambda cwd: None)

    result = git_commit.cmd_squash_local(
        argparse.Namespace(
            base_ref=None,
            description=["squash"],
            type="feat",
            scope=None,
            breaking=False,
            dry_run=False,
        ),
    )

    assert result == 1
    assert "No upstream branch is configured" in capsys.readouterr().err


def test_cmd_squash_local_requires_commits_ahead(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_commit.git, "working_tree_clean", lambda cwd: True)
    monkeypatch.setattr(
        git_commit,
        "resolve_commit_subject",
        lambda args, root: ("feat/add", "feat: add"),
    )
    monkeypatch.setattr(git_commit.git, "commits_ahead", lambda cwd, base_ref: [])

    result = git_commit.cmd_squash_local(
        argparse.Namespace(
            base_ref="origin/main",
            description=["squash"],
            type="feat",
            scope=None,
            breaking=False,
            dry_run=False,
        ),
    )

    assert result == 1
    assert "Nothing to squash" in capsys.readouterr().err


def test_cmd_squash_local_reports_clean_error_for_dash_prefixed_base_ref(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A --base-ref value starting with '-' must produce a clean CLI error, not a traceback."""
    monkeypatch.setattr(git_commit.git, "working_tree_clean", lambda cwd: True)
    monkeypatch.setattr(
        git_commit,
        "resolve_commit_subject",
        lambda args, root: ("feat/add", "feat: add"),
    )

    result = git_commit.cmd_squash_local(
        argparse.Namespace(
            base_ref="--upload-pack=evil",
            description=["squash"],
            type="feat",
            scope=None,
            breaking=False,
            dry_run=False,
        ),
    )

    assert result == 1
    assert "must not start with '-'" in capsys.readouterr().err


def test_cmd_squash_local_requires_merge_base(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_commit.git, "working_tree_clean", lambda cwd: True)
    monkeypatch.setattr(
        git_commit,
        "resolve_commit_subject",
        lambda args, root: ("feat/add", "feat: add"),
    )
    monkeypatch.setattr(git_commit.git, "commits_ahead", lambda cwd, base_ref: ["abc123 feat: add"])
    monkeypatch.setattr(git_commit.git, "merge_base", lambda cwd, base_ref: None)

    result = git_commit.cmd_squash_local(
        argparse.Namespace(
            base_ref="origin/main",
            description=["squash"],
            type="feat",
            scope=None,
            breaking=False,
            dry_run=False,
        ),
    )

    assert result == 1
    assert "Could not determine merge-base" in capsys.readouterr().err


def test_cmd_squash_local_reports_commit_subject_resolution_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(git_commit.git, "working_tree_clean", lambda cwd: True)
    monkeypatch.setattr(
        git_commit,
        "resolve_commit_subject",
        lambda args, root: (_ for _ in ()).throw(ValueError("bad subject")),
    )

    result = git_commit.cmd_squash_local(
        argparse.Namespace(
            base_ref="origin/main",
            description=["squash"],
            type="feat",
            scope=None,
            breaking=False,
            dry_run=False,
        ),
    )

    assert result == 1
    assert "bad subject" in capsys.readouterr().err


def test_cmd_squash_local_dry_run_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        git_commit,
        "resolve_commit_subject",
        lambda args, root: ("feat/add", "feat: add"),
    )
    monkeypatch.setattr(
        git_commit.git,
        "commits_ahead",
        lambda cwd, base_ref: ["a1 feat: one", "b2 fix: two"],
    )
    monkeypatch.setattr(git_commit.git, "merge_base", lambda cwd, base_ref: "abc123")
    commands: list[list[str]] = []
    monkeypatch.setattr(
        git_commit.git,
        "run",
        lambda cmd, cwd, *, dry_run, label: commands.append(cmd) or "",
    )

    result = git_commit.cmd_squash_local(
        argparse.Namespace(
            base_ref="origin/main",
            description=["squash"],
            type="feat",
            scope=None,
            breaking=False,
            dry_run=True,
        ),
    )

    assert result == 0
    assert commands == [["git", "reset", "--soft", "abc123"], ["git", "commit", "-m", "feat: add"]]
    assert "dry-run" in capsys.readouterr().out
