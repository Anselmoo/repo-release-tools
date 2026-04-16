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
from repo_release_tools.hooks import _entries_cancel_out
from repo_release_tools.hooks import dedup_changelog_entries
from repo_release_tools.hooks import apply_dedup_to_changelog
from repo_release_tools.hooks import run_post_correct


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


def test_run_dirty_tree_check_accepts_clean_tree(monkeypatch) -> None:
    monkeypatch.setattr(hooks.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(hooks.git, "working_tree_clean", lambda cwd: True)

    assert hooks.run_dirty_tree_check(Path.cwd(), title="Dirty tree validation failed.") == 0


def test_run_dirty_tree_check_rejects_dirty_tree(monkeypatch) -> None:
    monkeypatch.setattr(hooks.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(hooks.git, "working_tree_clean", lambda cwd: False)
    monkeypatch.setattr(
        hooks.git,
        "status_porcelain",
        lambda cwd: [" M src/repo_release_tools/cli.py", "?? docs/git-magic.md"],
    )

    assert hooks.run_dirty_tree_check(Path.cwd(), title="Dirty tree validation failed.") == 1


def test_run_dirty_tree_check_reports_status_failure(monkeypatch) -> None:
    monkeypatch.setattr(hooks.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(hooks.git, "working_tree_clean", lambda cwd: False)
    monkeypatch.setattr(
        hooks.git,
        "status_porcelain",
        lambda cwd: (_ for _ in ()).throw(RuntimeError("git status --short failed (exit 128)")),
    )

    assert hooks.run_dirty_tree_check(Path.cwd(), title="Dirty tree validation failed.") == 1


def test_main_check_dirty_tree_uses_hook_entrypoint(monkeypatch) -> None:
    monkeypatch.setattr(hooks.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(hooks.git, "working_tree_clean", lambda cwd: True)

    assert hooks.main(["check-dirty-tree"]) == 0


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
    assert "entry: rrt-hooks check-dirty-tree" in manifest


def test_action_installs_from_action_path_and_runs_hooks() -> None:
    action_text = Path("action.yml").read_text(encoding="utf-8")

    assert "working-directory: ${{ github.action_path }}" in action_text
    assert "branch-ref-type:" in action_text
    assert 'if [[ "$ref_type" == "tag" ]]; then' in action_text
    assert "Skipping branch-name validation for tag refs." in action_text
    assert "rrt-hooks check-branch-name --branch" in action_text
    assert "rrt-hooks check-commit-subject --subject" in action_text
    assert "check-changelog:" in action_text
    assert "changelog-file:" in action_text
    assert "rrt-hooks check-changelog" in action_text
    assert "check-dirty-tree:" in action_text
    assert "rrt-hooks check-dirty-tree" in action_text
    assert '--changelog-file "$INPUT_CHANGELOG_FILE"' in action_text
    assert "--ref HEAD" in action_text


# ---------------------------------------------------------------------------
# Post-correction tests
# ---------------------------------------------------------------------------


def test_entries_cancel_out_add_remove() -> None:
    assert _entries_cancel_out("add Node 26", "remove Node 26") is True


def test_entries_cancel_out_remove_add() -> None:
    assert _entries_cancel_out("remove Node 26", "add Node 26") is True


def test_entries_cancel_out_enable_disable() -> None:
    assert _entries_cancel_out("enable caching", "disable caching") is True


def test_entries_cancel_out_with_matching_scope_prefix() -> None:
    assert _entries_cancel_out("CI: add Node 26", "CI: remove Node 26") is True


def test_entries_cancel_out_with_matching_scope_prefix_reversed() -> None:
    assert _entries_cancel_out("CI: remove Node 26", "CI: add Node 26") is True


def test_entries_do_not_cancel_different_scope_prefix() -> None:
    assert _entries_cancel_out("CI: add Node 26", "Deps: remove Node 26") is False


def test_entries_do_not_cancel_mixed_prefix() -> None:
    assert _entries_cancel_out("CI: add Node 26", "add Node 26") is False


def test_entries_do_not_cancel_unrelated() -> None:
    assert _entries_cancel_out("add Node 26", "fix typo in workflow") is False


def test_entries_do_not_cancel_different_subjects() -> None:
    assert _entries_cancel_out("add Node 26", "add Node 18") is False


def test_dedup_changelog_entries_removes_duplicates() -> None:
    lines = [
        "### Maintenance",
        "- CI: fix typo in workflow",
        "- CI: fix typo in workflow",
    ]
    result = dedup_changelog_entries(lines)
    assert result.count("- CI: fix typo in workflow") == 1


def test_dedup_changelog_entries_removes_cancelling_pairs() -> None:
    lines = [
        "### Maintenance",
        "- add Node 26",
        "- remove Node 26",
        "- fix typo in workflow",
    ]
    result = dedup_changelog_entries(lines)
    assert "- add Node 26" not in result
    assert "- remove Node 26" not in result
    assert "- fix typo in workflow" in result


def test_dedup_changelog_entries_removes_cancelling_pairs_with_scope_prefix() -> None:
    lines = [
        "### Maintenance",
        "- CI: add Node 26",
        "- CI: remove Node 26",
        "- CI: fix typo in workflow",
    ]
    result = dedup_changelog_entries(lines)
    assert "- CI: add Node 26" not in result
    assert "- CI: remove Node 26" not in result
    assert "- CI: fix typo in workflow" in result


def test_dedup_changelog_entries_preserves_non_cancelled_entries() -> None:
    lines = [
        "### Added",
        "- feat: new command",
        "### Maintenance",
        "- CI: update workflow",
    ]
    result = dedup_changelog_entries(lines)
    assert result == lines


def test_dedup_changelog_entries_collapses_blank_lines() -> None:
    lines = [
        "### Maintenance",
        "- add Node 26",
        "",
        "- remove Node 26",
        "",
        "- fix typo",
    ]
    result = dedup_changelog_entries(lines)
    # Should not have consecutive blank lines after removal
    blank_count = sum(1 for line in result if not line.strip())
    assert blank_count <= 1


def test_apply_dedup_to_changelog_removes_cancelled_entries(tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Maintenance\n- add Node 26\n- remove Node 26\n- fix typo\n",
        encoding="utf-8",
    )
    added_lines = ["### Maintenance", "- add Node 26", "- remove Node 26", "- fix typo"]
    deduped_lines = ["### Maintenance", "- fix typo"]

    changed = apply_dedup_to_changelog(changelog, added_lines, deduped_lines)

    assert changed is True
    content = changelog.read_text(encoding="utf-8")
    assert "- add Node 26" not in content
    assert "- remove Node 26" not in content
    assert "- fix typo" in content


def test_apply_dedup_to_changelog_returns_false_when_nothing_removed(tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    original = "# Changelog\n\n## [Unreleased]\n\n- fix typo\n"
    changelog.write_text(original, encoding="utf-8")
    added_lines = ["- fix typo"]
    deduped_lines = ["- fix typo"]

    changed = apply_dedup_to_changelog(changelog, added_lines, deduped_lines)

    assert changed is False
    assert changelog.read_text(encoding="utf-8") == original


def test_apply_dedup_to_changelog_restricts_removal_to_diff_positions(tmp_path: Path) -> None:
    # Line 8 in the old section has the same content as the noisy new entries;
    # only lines 4 and 5 (the squash additions) should be removed.
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n## [0.1.8]\n- add Node 26\n- remove Node 26\n\n## [0.1.7]\n- add Node 26\n",
        encoding="utf-8",
    )
    added_lines = ["- add Node 26", "- remove Node 26"]
    deduped_lines: list[str] = []
    positions: frozenset[int] = frozenset({4, 5})  # 1-based: lines 4 and 5 are the new additions

    changed = apply_dedup_to_changelog(
        changelog, added_lines, deduped_lines, added_line_positions=positions
    )

    assert changed is True
    content = changelog.read_text(encoding="utf-8")
    assert content.count("- add Node 26") == 1  # old section entry preserved
    assert "- remove Node 26" not in content


def test_run_post_correct_returns_zero_when_no_diff(monkeypatch, tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n- feat: something\n", encoding="utf-8")
    monkeypatch.setattr(
        hooks, "collect_squash_changelog_hunks", lambda *a, **kw: ([], frozenset())
    )

    assert run_post_correct(tmp_path, changelog_file="CHANGELOG.md") == 0


def test_run_post_correct_returns_zero_when_already_clean(monkeypatch, tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n- fix typo\n", encoding="utf-8")
    monkeypatch.setattr(
        hooks,
        "collect_squash_changelog_hunks",
        lambda *a, **kw: (["- fix typo"], frozenset({3})),
    )

    assert run_post_correct(tmp_path, changelog_file="CHANGELOG.md") == 0


def test_run_post_correct_cleans_contradicting_entries(monkeypatch, tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n### Maintenance\n- add Node 26\n- remove Node 26\n- fix typo\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        hooks,
        "collect_squash_changelog_hunks",
        lambda *a, **kw: (
            ["### Maintenance", "- add Node 26", "- remove Node 26", "- fix typo"],
            frozenset({3, 4, 5, 6}),
        ),
    )

    result = run_post_correct(tmp_path, changelog_file="CHANGELOG.md")

    assert result == 0
    content = changelog.read_text(encoding="utf-8")
    assert "- add Node 26" not in content
    assert "- remove Node 26" not in content
    assert "- fix typo" in content


def test_run_post_correct_cleans_scope_prefixed_contradicting_entries(
    monkeypatch, tmp_path: Path
) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n### Maintenance\n- CI: add Node 26\n- CI: remove Node 26\n- CI: fix typo\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        hooks,
        "collect_squash_changelog_hunks",
        lambda *a, **kw: (
            ["### Maintenance", "- CI: add Node 26", "- CI: remove Node 26", "- CI: fix typo"],
            frozenset({3, 4, 5, 6}),
        ),
    )

    result = run_post_correct(tmp_path, changelog_file="CHANGELOG.md")

    assert result == 0
    content = changelog.read_text(encoding="utf-8")
    assert "- CI: add Node 26" not in content
    assert "- CI: remove Node 26" not in content
    assert "- CI: fix typo" in content


def test_run_post_correct_fails_when_changelog_missing(tmp_path: Path) -> None:
    assert run_post_correct(tmp_path, changelog_file="MISSING.md") == 1


def test_main_changelog_post_correct_no_diff(monkeypatch, tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n- fix typo\n", encoding="utf-8")
    monkeypatch.setattr(
        hooks, "collect_squash_changelog_hunks", lambda *a, **kw: ([], frozenset())
    )
    monkeypatch.chdir(tmp_path)

    assert hooks.main(["changelog", "post-correct"]) == 0


def test_main_changelog_post_correct_explicit_commit(monkeypatch, tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n- fix typo\n", encoding="utf-8")
    monkeypatch.setattr(
        hooks,
        "collect_squash_changelog_hunks",
        lambda *a, **kw: (["- fix typo"], frozenset({3})),
    )
    monkeypatch.chdir(tmp_path)

    assert hooks.main(["changelog", "post-correct", "--squash-commit", "abc1234"]) == 0
