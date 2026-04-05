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


def test_cmd_status_reports_status_failure(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "main")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: "origin/main")
    monkeypatch.setattr(
        git_cmd.git,
        "status_porcelain",
        lambda cwd: (_ for _ in ()).throw(RuntimeError("git status --short failed (exit 128)")),
    )
    args = argparse.Namespace()

    assert git_cmd.cmd_status(args) == 1

    captured = capsys.readouterr()
    assert "git status --short failed" in captured.err


def test_cmd_log_renders_compact_history(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(
        git_cmd.git,
        "capture",
        lambda cmd, cwd: (
            "abc1234\tfeat: add parser\tHEAD -> feat/add-parser, origin/feat/add-parser\n"
            "def5678\tfix: handle empty input\t"
        ),
    )
    args = argparse.Namespace(limit=2)

    assert git_cmd.cmd_log(args) == 0

    captured = capsys.readouterr()
    assert "Git log" in captured.out
    assert "abc1234" in captured.out
    assert "feat: add parser" in captured.out
    assert "origin/feat/add-parser" in captured.out


def test_cmd_doctor_reports_failures(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: None)
    monkeypatch.setattr(
        git_cmd.git, "status_porcelain", lambda cwd: [" M src/repo_release_tools/cli.py"]
    )
    monkeypatch.setattr(git_cmd.git, "ahead_behind", lambda cwd, ref: (0, 0))

    def fake_capture(cmd, cwd):
        if cmd[:4] == ["git", "log", "-1", "--pretty=%s"]:
            return "update stuff"
        if cmd[:5] == ["git", "diff-tree", "--no-commit-id", "--name-only", "--root"]:
            return "src/repo_release_tools/cli.py"
        raise AssertionError(cmd)

    monkeypatch.setattr(git_cmd.git, "capture", fake_capture)
    args = argparse.Namespace(changelog_file="CHANGELOG.md")

    assert git_cmd.cmd_doctor(args) == 1

    captured = capsys.readouterr()
    assert "Git doctor" in captured.out
    assert "No upstream branch configured." in captured.out
    assert "Working tree has uncommitted changes." in captured.out
    assert "update stuff" in captured.out


def test_cmd_doctor_reports_success(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "status_porcelain", lambda cwd: [])
    monkeypatch.setattr(git_cmd.git, "ahead_behind", lambda cwd, ref: (2, 1))

    def fake_capture(cmd, cwd):
        if cmd[:4] == ["git", "log", "-1", "--pretty=%s"]:
            return "feat: add parser"
        if cmd[:5] == ["git", "diff-tree", "--no-commit-id", "--name-only", "--root"]:
            return "CHANGELOG.md\nsrc/repo_release_tools/cli.py"
        raise AssertionError(cmd)

    monkeypatch.setattr(git_cmd.git, "capture", fake_capture)
    args = argparse.Namespace(changelog_file="CHANGELOG.md")

    assert git_cmd.cmd_doctor(args) == 0

    captured = capsys.readouterr()
    assert "Doctor checks passed." in captured.out


def test_cmd_doctor_uses_commit_subject_for_changelog_risk(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "status_porcelain", lambda cwd: [])
    monkeypatch.setattr(git_cmd.git, "ahead_behind", lambda cwd, ref: (0, 0))

    def fake_capture(cmd, cwd):
        if cmd[:4] == ["git", "log", "-1", "--pretty=%s"]:
            return "chore: update docs tooling"
        if cmd[:5] == ["git", "diff-tree", "--no-commit-id", "--name-only", "--root"]:
            raise AssertionError("changelog diff should not be queried for chore commits")
        raise AssertionError(cmd)

    monkeypatch.setattr(git_cmd.git, "capture", fake_capture)
    args = argparse.Namespace(changelog_file="CHANGELOG.md")

    assert git_cmd.cmd_doctor(args) == 0

    captured = capsys.readouterr()
    assert "Doctor checks passed." in captured.out


def test_cmd_sync_requires_git_repository(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: False)
    args = argparse.Namespace(merge=False, dry_run=True)

    assert git_cmd.cmd_sync(args) == 1

    captured = capsys.readouterr()
    assert "is not inside a Git work tree" in captured.err


def test_cmd_move_requires_git_repository(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: False)
    args = argparse.Namespace(target="feat/add-parser", create=False, dry_run=True)

    assert git_cmd.cmd_move(args) == 1

    captured = capsys.readouterr()
    assert "is not inside a Git work tree" in captured.err


def test_cmd_sync_dry_run_stashes_before_rebase(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
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


def test_cmd_check_dirty_tree_reports_status_failure(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "working_tree_clean", lambda cwd: False)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(git_cmd.git, "upstream_branch", lambda cwd: "origin/feat/add-parser")
    monkeypatch.setattr(
        git_cmd.git,
        "status_porcelain",
        lambda cwd: (_ for _ in ()).throw(RuntimeError("git status --short failed (exit 128)")),
    )
    args = argparse.Namespace()

    assert git_cmd.cmd_check_dirty_tree(args) == 1

    captured = capsys.readouterr()
    assert "git status --short failed" in captured.err


def test_cmd_move_dry_run_stashes_before_checkout(monkeypatch, capsys) -> None:
    monkeypatch.setattr(git_cmd.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(git_cmd.git, "current_branch", lambda cwd: "main")
    monkeypatch.setattr(git_cmd.git, "working_tree_clean", lambda cwd: False)
    args = argparse.Namespace(target="feat/add-parser", create=False, dry_run=True)

    assert git_cmd.cmd_move(args) == 0

    captured = capsys.readouterr()
    assert "git stash push -u -m rrt git move auto-stash" in captured.out
    assert "git checkout feat/add-parser" in captured.out
    assert "git stash pop" in captured.out


def test_cmd_rebootstrap_requires_confirmation(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    args = argparse.Namespace(yes_i_know_this_destroys_history=False)

    assert git_cmd.cmd_rebootstrap(args) == 1

    captured = capsys.readouterr()
    assert "--yes-i-know-this-destroys-history" in captured.err
