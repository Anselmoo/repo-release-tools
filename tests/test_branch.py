import argparse

from repo_release_tools.commands.branch import BranchName
from repo_release_tools.commands.branch import cmd_new
from repo_release_tools.hooks import validate_branch_name


def test_branch_name_without_scope() -> None:
    branch = BranchName(type="feat", description="add parser")
    assert branch.slug() == "feat/add-parser"
    assert branch.commit_title() == "feat: add parser"


def test_branch_name_with_scope() -> None:
    branch = BranchName(type="fix", description="null pointer", scope="cli")
    assert branch.slug() == "fix/cli-null-pointer"
    assert branch.commit_title() == "fix(cli): null pointer"


def test_cmd_new_dry_run_uses_summary_panel(capsys) -> None:
    args = argparse.Namespace(
        type="feat",
        description=["add", "parser"],
        scope=None,
        dry_run=True,
    )

    assert cmd_new(args) == 0

    captured = capsys.readouterr()
    assert "New branch" in captured.out
    assert "Branch" in captured.out
    assert "feat/add-parser" in captured.out
    assert "[dry-run] complete" in captured.out


def test_cmd_new_existing_branch_returns_error(monkeypatch, capsys) -> None:
    args = argparse.Namespace(
        type="feat",
        description=["add", "parser"],
        scope=None,
        dry_run=False,
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.branch.git.current_branch", lambda root: "main"
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.branch.git.branch_exists", lambda root, name: True
    )

    result = cmd_new(args)

    assert result == 1
    assert "already exists" in capsys.readouterr().err


def test_cmd_new_reports_uncommitted_changes(monkeypatch, capsys) -> None:
    args = argparse.Namespace(
        type="feat",
        description=["add", "parser"],
        scope=None,
        dry_run=False,
    )
    ran: list[list[str]] = []
    monkeypatch.setattr(
        "repo_release_tools.commands.branch.git.current_branch", lambda root: "main"
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.branch.git.branch_exists", lambda root, name: False
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.branch.git.working_tree_clean", lambda root: False
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.branch.git.run",
        lambda cmd, root, *, dry_run, label: ran.append(cmd),
    )

    result = cmd_new(args)

    assert result == 0
    assert ran == [["git", "checkout", "-b", "feat/add-parser"]]
    assert "Uncommitted changes moved to the new branch" in capsys.readouterr().out


def test_branch_validation_accepts_magic_ai_types() -> None:
    assert validate_branch_name("codex/add-parser") is None


# ---------------------------------------------------------------------------
# normalize_commit_type errors
# ---------------------------------------------------------------------------


def test_normalize_commit_type_invalid_raises() -> None:
    import pytest
    from argparse import ArgumentTypeError
    from repo_release_tools.commands.branch import normalize_commit_type

    with pytest.raises((ArgumentTypeError, SystemExit)):
        normalize_commit_type("invalid_type")


def test_normalize_commit_type_uppercase_normalized() -> None:
    from repo_release_tools.commands.branch import normalize_commit_type

    assert normalize_commit_type("FEAT") == "feat"


# ---------------------------------------------------------------------------
# join_description errors
# ---------------------------------------------------------------------------


def test_join_description_empty_raises() -> None:
    import pytest
    from argparse import ArgumentTypeError
    from repo_release_tools.commands.branch import join_description

    with pytest.raises(ArgumentTypeError, match="empty"):
        join_description(["", "  "])


# ---------------------------------------------------------------------------
# cmd_rescue dry-run
# ---------------------------------------------------------------------------


def test_cmd_rescue_dry_run(capsys) -> None:
    """cmd_rescue in dry-run mode should print panel and not touch git."""
    from repo_release_tools.commands.branch import cmd_rescue

    args = argparse.Namespace(
        type="fix",
        description=["extract", "helper"],
        scope=None,
        dry_run=True,
        since=None,
    )

    result = cmd_rescue(args)

    assert result == 0
    captured = capsys.readouterr()
    assert "Rescue commits" in captured.out
    assert "fix/extract-helper" in captured.out
    assert "[dry-run] complete" in captured.out


def test_cmd_rescue_dry_run_with_since(capsys) -> None:
    """cmd_rescue with --since in dry-run mode should reference the SHA."""
    from repo_release_tools.commands.branch import cmd_rescue

    args = argparse.Namespace(
        type="refactor",
        description=["cleanup"],
        scope=None,
        dry_run=True,
        since="abc123",
    )

    result = cmd_rescue(args)

    assert result == 0
    captured = capsys.readouterr()
    assert "abc123" in captured.out


def test_cmd_rescue_no_commits_returns_error(monkeypatch, capsys) -> None:
    """Non-dry-run rescue fails when there are no commits ahead to rescue."""
    from repo_release_tools.commands.branch import cmd_rescue

    monkeypatch.setattr(
        "repo_release_tools.commands.branch.git.current_branch", lambda root: "feat/existing-work"
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.branch.git.commits_ahead", lambda root, ref: []
    )

    args = argparse.Namespace(
        type="fix",
        description=["extract", "helper"],
        scope=None,
        dry_run=False,
        since=None,
    )

    result = cmd_rescue(args)

    assert result == 1
    assert "Nothing to rescue" in capsys.readouterr().err


def test_cmd_rescue_existing_target_branch_returns_error(monkeypatch, capsys) -> None:
    """Rescue fails when the destination branch already exists."""
    from repo_release_tools.commands.branch import cmd_rescue

    monkeypatch.setattr(
        "repo_release_tools.commands.branch.git.current_branch", lambda root: "main"
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.branch.git.commits_ahead",
        lambda root, ref: ["abc123 fix: keep this change"],
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.branch.git.branch_exists", lambda root, name: True
    )

    args = argparse.Namespace(
        type="fix",
        description=["extract", "helper"],
        scope=None,
        dry_run=False,
        since=None,
    )

    result = cmd_rescue(args)

    assert result == 1
    assert "already exists" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# cmd_rename
# ---------------------------------------------------------------------------


def test_cmd_rename_type_only_dry_run(monkeypatch, capsys) -> None:
    """--type replaces only the type prefix; slug is preserved."""
    from repo_release_tools.commands.branch import cmd_rename

    monkeypatch.setattr(
        "repo_release_tools.commands.branch.git.current_branch",
        lambda root: "build/introduce-v1",
    )

    args = argparse.Namespace(
        type="feat",
        scope=None,
        no_scope=False,
        description=[],
        dry_run=True,
    )
    result = cmd_rename(args)

    assert result == 0
    out = capsys.readouterr().out
    assert "build/introduce-v1" in out
    assert "feat/introduce-v1" in out
    assert "[dry-run] complete" in out


def test_cmd_rename_scope_prepended_dry_run(monkeypatch, capsys) -> None:
    """--scope prepends the scope to the preserved slug."""
    from repo_release_tools.commands.branch import cmd_rename

    monkeypatch.setattr(
        "repo_release_tools.commands.branch.git.current_branch",
        lambda root: "feat/add-login",
    )

    args = argparse.Namespace(
        type=None,
        scope="auth",
        no_scope=False,
        description=[],
        dry_run=True,
    )
    result = cmd_rename(args)

    assert result == 0
    out = capsys.readouterr().out
    assert "feat/auth-add-login" in out


def test_cmd_rename_full_rebuild_dry_run(monkeypatch, capsys) -> None:
    """Providing description words triggers a full BranchName rebuild."""
    from repo_release_tools.commands.branch import cmd_rename

    monkeypatch.setattr(
        "repo_release_tools.commands.branch.git.current_branch",
        lambda root: "build/introduce-v1",
    )

    args = argparse.Namespace(
        type="feat",
        scope=None,
        no_scope=False,
        description=["introduce", "v2"],
        dry_run=True,
    )
    result = cmd_rename(args)

    assert result == 0
    out = capsys.readouterr().out
    assert "feat/introduce-v2" in out


def test_cmd_rename_no_change_returns_error(monkeypatch, capsys) -> None:
    """No change requested should return 1 with a helpful message."""
    from repo_release_tools.commands.branch import cmd_rename

    monkeypatch.setattr(
        "repo_release_tools.commands.branch.git.current_branch",
        lambda root: "feat/my-feature",
    )

    args = argparse.Namespace(
        type=None,
        scope=None,
        no_scope=False,
        description=[],
        dry_run=True,
    )
    result = cmd_rename(args)

    assert result == 1


def test_cmd_rename_no_scope_without_description_errors(monkeypatch) -> None:
    """--no-scope without description words is rejected."""
    from repo_release_tools.commands.branch import cmd_rename

    monkeypatch.setattr(
        "repo_release_tools.commands.branch.git.current_branch",
        lambda root: "feat/auth-add-login",
    )

    args = argparse.Namespace(
        type=None,
        scope=None,
        no_scope=True,
        description=[],
        dry_run=True,
    )
    result = cmd_rename(args)

    assert result == 1


def test_cmd_rename_type_and_description_no_scope(monkeypatch, capsys) -> None:
    """--no-scope with description rebuilds without scope."""
    from repo_release_tools.commands.branch import cmd_rename

    monkeypatch.setattr(
        "repo_release_tools.commands.branch.git.current_branch",
        lambda root: "feat/auth-add-login",
    )

    args = argparse.Namespace(
        type="fix",
        scope=None,
        no_scope=True,
        description=["patch", "login"],
        dry_run=True,
    )
    result = cmd_rename(args)

    assert result == 0
    out = capsys.readouterr().out
    assert "fix/patch-login" in out


def test_cmd_rename_non_conventional_branch_errors(monkeypatch, capsys) -> None:
    """A branch name without '/' produces a clear error."""
    from repo_release_tools.commands.branch import cmd_rename

    monkeypatch.setattr(
        "repo_release_tools.commands.branch.git.current_branch",
        lambda root: "main",
    )

    args = argparse.Namespace(
        type="feat",
        scope=None,
        no_scope=False,
        description=[],
        dry_run=True,
    )
    result = cmd_rename(args)

    assert result == 1
    err = capsys.readouterr().err
    assert "convention" in err


def test_cmd_rename_branch_already_exists_returns_error(monkeypatch, capsys) -> None:
    """When the target branch name already exists, return 1."""
    from repo_release_tools.commands.branch import cmd_rename

    monkeypatch.setattr(
        "repo_release_tools.commands.branch.git.current_branch",
        lambda root: "build/introduce-v1",
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.branch.git.branch_exists",
        lambda root, name: True,
    )

    args = argparse.Namespace(
        type="feat",
        scope=None,
        no_scope=False,
        description=[],
        dry_run=False,
    )
    result = cmd_rename(args)

    assert result == 1


def test_cmd_rename_executes_git_branch_m(monkeypatch, capsys) -> None:
    """Successful non-dry-run rename calls git branch -m."""
    from repo_release_tools.commands.branch import cmd_rename

    monkeypatch.setattr(
        "repo_release_tools.commands.branch.git.current_branch",
        lambda root: "build/introduce-v1",
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.branch.git.branch_exists",
        lambda root, name: False,
    )
    ran: list[list[str]] = []
    monkeypatch.setattr(
        "repo_release_tools.commands.branch.git.run",
        lambda cmd, root, *, dry_run, label: ran.append(cmd),
    )

    args = argparse.Namespace(
        type="feat",
        scope=None,
        no_scope=False,
        description=[],
        dry_run=False,
    )
    result = cmd_rename(args)

    assert result == 0
    assert ran == [["git", "branch", "-m", "build/introduce-v1", "feat/introduce-v1"]]
