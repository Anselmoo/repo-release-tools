from pathlib import Path

from repo_release_tools import hooks
from repo_release_tools.hooks import branch_requires_changelog
from repo_release_tools.hooks import changelog_is_updated
from repo_release_tools.hooks import commit_subject_requires_changelog
from repo_release_tools.hooks import read_commit_subject
from repo_release_tools.hooks import run_changelog_check
from repo_release_tools.hooks import run_pre_commit_changelog
from repo_release_tools.hooks import validate_branch_name
from repo_release_tools.hooks import validate_commit_subject


def test_validate_branch_name_accepts_feature_branch() -> None:
    assert validate_branch_name("feat/add-hook-checks") is None


def test_validate_branch_name_accepts_release_branch() -> None:
    assert validate_branch_name("release/v1.2.3") is None


def test_validate_branch_name_accepts_magic_ai_branch() -> None:
    assert validate_branch_name("claude/update-hook-checks") is None


def test_validate_branch_name_rejects_invalid_slug() -> None:
    problem = validate_branch_name("feat/Add Hook Checks")

    assert problem is not None
    assert "lowercase letters, digits, and hyphens" in problem


def test_validate_branch_name_lists_magic_ai_types_in_error() -> None:
    problem = validate_branch_name("wizard/add-hook-checks")

    assert problem is not None
    assert "claude" in problem
    assert "codex" in problem
    assert "copilot" in problem


def test_validate_commit_subject_accepts_conventional_commit() -> None:
    assert validate_commit_subject("feat(cli): add hook checks") is None


def test_validate_commit_subject_accepts_fixup_commit() -> None:
    assert validate_commit_subject("fixup! feat(cli): add hook checks") is None


def test_validate_commit_subject_rejects_invalid_commit() -> None:
    problem = validate_commit_subject("update stuff")

    assert problem is not None
    assert "Conventional Commits" in problem


def test_branch_requires_changelog_for_feature_branch() -> None:
    assert branch_requires_changelog("feat/add-hook-checks") is True


def test_branch_requires_changelog_skips_maintenance_branch() -> None:
    assert branch_requires_changelog("chore/update-tooling") is False


def test_commit_subject_requires_changelog_for_breaking_change() -> None:
    assert commit_subject_requires_changelog("chore!: remove deprecated flow") is True


def test_commit_subject_requires_changelog_skips_chore_commit() -> None:
    assert commit_subject_requires_changelog("chore: update tooling") is False


def test_changelog_is_updated_accepts_relative_and_absolute_paths(tmp_path: Path) -> None:
    changelog = tmp_path / "docs" / "CHANGELOG.md"
    changelog.parent.mkdir()
    changelog.write_text("", encoding="utf-8")

    assert changelog_is_updated(
        ["./docs/CHANGELOG.md", str(changelog)],
        changelog_file="docs/CHANGELOG.md",
        cwd=tmp_path,
    )


def test_read_commit_subject_uses_first_non_empty_line(tmp_path: Path) -> None:
    message_file = tmp_path / "COMMIT_EDITMSG"
    message_file.write_text("\n\nfeat: add hooks\n\nbody", encoding="utf-8")

    assert read_commit_subject(message_file) == "feat: add hooks"


def test_main_check_branch_name_accepts_explicit_branch() -> None:
    assert hooks.main(["check-branch-name", "--branch", "feat/add-hook-checks"]) == 0


def test_main_check_branch_name_accepts_magic_ai_branch() -> None:
    assert hooks.main(["check-branch-name", "--branch", "copilot/add-hook-checks"]) == 0


def test_main_check_commit_subject_rejects_invalid_subject() -> None:
    assert hooks.main(["check-commit-subject", "--subject", "update stuff"]) == 1


def test_run_pre_commit_changelog_rejects_missing_staged_changelog(monkeypatch) -> None:
    monkeypatch.setattr(hooks.git, "current_branch", lambda cwd: "feat/add-hook-checks")
    monkeypatch.setattr(hooks, "staged_files", lambda cwd: ["src/repo_release_tools/hooks.py"])

    assert run_pre_commit_changelog(Path.cwd()) == 1


def test_run_pre_commit_changelog_accepts_staged_changelog(monkeypatch) -> None:
    monkeypatch.setattr(hooks.git, "current_branch", lambda cwd: "feat/add-hook-checks")
    monkeypatch.setattr(
        hooks,
        "staged_files",
        lambda cwd: ["src/repo_release_tools/hooks.py", "CHANGELOG.md"],
    )

    assert run_pre_commit_changelog(Path.cwd()) == 0


def test_run_changelog_check_accepts_commit_with_changelog_file() -> None:
    assert (
        run_changelog_check(
            "feat(cli): add hook checks",
            cwd=Path.cwd(),
            changed_files=["CHANGELOG.md", "src/repo_release_tools/hooks.py"],
            title="Changelog validation failed.",
        )
        == 0
    )


def test_run_changelog_check_rejects_missing_changelog_file() -> None:
    assert (
        run_changelog_check(
            "fix(cli): tighten validation",
            cwd=Path.cwd(),
            changed_files=["src/repo_release_tools/hooks.py"],
            title="Changelog validation failed.",
        )
        == 1
    )


def test_main_check_changelog_accepts_explicit_changed_file() -> None:
    assert (
        hooks.main(
            [
                "check-changelog",
                "--subject",
                "feat(cli): add hook checks",
                "--changed-file",
                "CHANGELOG.md",
            ]
        )
        == 0
    )


def test_main_commit_msg_accepts_valid_message_file(tmp_path: Path) -> None:
    message_file = tmp_path / "COMMIT_EDITMSG"
    message_file.write_text("feat(cli): add hook installer\n", encoding="utf-8")

    assert hooks.main(["commit-msg", str(message_file)]) == 0


def test_pre_commit_hooks_use_console_script_entrypoints() -> None:
    manifest = Path(".pre-commit-hooks.yaml").read_text(encoding="utf-8")

    assert "entry: rrt-hooks pre-commit" in manifest
    assert "entry: rrt-hooks pre-commit-changelog" in manifest
    assert "entry: rrt-hooks commit-msg" in manifest


def test_action_installs_from_action_path_and_runs_hooks() -> None:
    action_text = Path("action.yml").read_text(encoding="utf-8")

    assert "working-directory: ${{ github.action_path }}" in action_text
    assert "branch-ref-type:" in action_text
    assert 'if [[ "$ref_type" == "tag" ]]; then' in action_text
    assert 'Skipping branch-name validation for tag refs.' in action_text
    assert "rrt-hooks check-branch-name --branch" in action_text
    assert "rrt-hooks check-commit-subject --subject" in action_text
    assert "check-changelog:" in action_text
    assert "changelog-file:" in action_text
    assert "rrt-hooks check-changelog" in action_text
    assert "--changelog-file \"$INPUT_CHANGELOG_FILE\"" in action_text
    assert "--ref HEAD" in action_text
