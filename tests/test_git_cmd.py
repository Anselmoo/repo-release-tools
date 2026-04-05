import argparse

from repo_release_tools.commands import git_cmd


def test_infer_commit_type_from_branch() -> None:
    assert git_cmd.infer_commit_type("feat/add-parser") == "feat"
    assert git_cmd.infer_commit_type("main") is None
    assert git_cmd.infer_commit_type("copilot/add-parser") is None


def test_cmd_commit_dry_run_uses_branch_type(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "feat/add-parser")
    args = argparse.Namespace(
        description=["handle", "empty", "config"],
        type=None,
        scope=None,
        breaking=False,
        dry_run=True,
    )

    assert git_cmd.cmd_commit(args) == 0

    captured = capsys.readouterr()
    assert "feat: handle empty config" in captured.out
    assert "[dry-run] complete" in captured.out


def test_cmd_status_renders_summary_and_entries(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(
        git_cmd.git,
        "status_porcelain",
        lambda cwd: [" M src/repo_release_tools/cli.py", "?? docs/git-magic.md"],
    )
    monkeypatch.setattr(git_cmd.git, "ahead_behind", lambda cwd, ref: (2, 1))
    args = argparse.Namespace()

    assert git_cmd.cmd_status(args) == 0

    captured = capsys.readouterr()
    assert "Git status" in captured.out
    assert "feat/add-parser" in captured.out
    assert "src/repo_release_tools/cli.py" in captured.out
    assert "docs/git-magic.md" in captured.out


def test_cmd_status_renders_clean_tree(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "main")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: "origin/main")
    monkeypatch.setattr(git_cmd.git, "status_porcelain", lambda cwd: [])
    monkeypatch.setattr(git_cmd.git, "ahead_behind", lambda cwd, ref: (0, 0))
    args = argparse.Namespace()

    assert git_cmd.cmd_status(args) == 0

    captured = capsys.readouterr()
    assert "Working tree is clean." in captured.out


def test_cmd_sync_dry_run_stashes_before_rebase(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "working_tree_clean", lambda cwd: False)
    monkeypatch.setattr(
        git_cmd.git, "status_porcelain", lambda cwd: [" M src/repo_release_tools/cli.py"]
    )
    monkeypatch.setattr(git_cmd.git, "ahead_behind", lambda cwd, ref: (2, 1))
    args = argparse.Namespace(merge=False, dry_run=True)

    assert git_cmd.cmd_sync(args) == 0

    captured = capsys.readouterr()
    assert "git fetch --prune" in captured.out
    assert "git stash push -u -m rrt git sync auto-stash" in captured.out
    assert "git pull --rebase" in captured.out
    assert "git stash pop" in captured.out


def test_cmd_check_dirty_tree_reports_status_lines(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "working_tree_clean", lambda cwd: False)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(
        git_cmd.git,
        "status_porcelain",
        lambda cwd: [" M src/repo_release_tools/cli.py", "?? docs/git-magic.md"],
    )
    monkeypatch.setattr(git_cmd.git, "ahead_behind", lambda cwd, ref: (2, 1))
    args = argparse.Namespace()

    assert git_cmd.cmd_check_dirty_tree(args) == 1

    captured = capsys.readouterr()
    assert "Working tree has uncommitted changes." in captured.err
    assert "feat/add-parser" in captured.err
    assert "src/repo_release_tools/cli.py" in captured.err
    assert "docs/git-magic.md" in captured.err


def test_cmd_rebootstrap_requires_confirmation(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    args = argparse.Namespace(yes_i_know_this_destroys_history=False)

    assert git_cmd.cmd_rebootstrap(args) == 1

    captured = capsys.readouterr()
    assert "--yes-i-know-this-destroys-history" in captured.err
