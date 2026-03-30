from pathlib import Path

from repo_release_tools import hooks
from repo_release_tools.hooks import read_commit_subject
from repo_release_tools.hooks import validate_branch_name
from repo_release_tools.hooks import validate_commit_subject


def test_validate_branch_name_accepts_feature_branch() -> None:
    assert validate_branch_name("feat/add-hook-checks") is None


def test_validate_branch_name_accepts_release_branch() -> None:
    assert validate_branch_name("release/v1.2.3") is None


def test_validate_branch_name_rejects_invalid_slug() -> None:
    problem = validate_branch_name("feat/Add Hook Checks")

    assert problem is not None
    assert "lowercase letters, digits, and hyphens" in problem


def test_validate_commit_subject_accepts_conventional_commit() -> None:
    assert validate_commit_subject("feat(cli): add hook checks") is None


def test_validate_commit_subject_accepts_fixup_commit() -> None:
    assert validate_commit_subject("fixup! feat(cli): add hook checks") is None


def test_validate_commit_subject_rejects_invalid_commit() -> None:
    problem = validate_commit_subject("update stuff")

    assert problem is not None
    assert "Conventional Commits" in problem


def test_read_commit_subject_uses_first_non_empty_line(tmp_path: Path) -> None:
    message_file = tmp_path / "COMMIT_EDITMSG"
    message_file.write_text("\n\nfeat: add hooks\n\nbody", encoding="utf-8")

    assert read_commit_subject(message_file) == "feat: add hooks"


def test_main_check_branch_name_accepts_explicit_branch() -> None:
    assert hooks.main(["check-branch-name", "--branch", "feat/add-hook-checks"]) == 0


def test_main_check_commit_subject_rejects_invalid_subject() -> None:
    assert hooks.main(["check-commit-subject", "--subject", "update stuff"]) == 1
