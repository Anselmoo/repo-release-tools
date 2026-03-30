import argparse

from repo_release_tools.commands.branch import BranchName
from repo_release_tools.commands.branch import cmd_new


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
