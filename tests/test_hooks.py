from __future__ import annotations

import os
from pathlib import Path

import pytest

from repo_release_tools import hooks
from repo_release_tools.hooks import (
    _detect_changelog_workflow,
    _entries_cancel_out,
    _resolve_changelog_strategy,
    apply_dedup_to_changelog,
    branch_requires_changelog,
    changelog_is_updated,
    collect_squash_changelog_hunks,
    commit_subject_requires_changelog,
    dedup_changelog_entries,
    is_changelog_meta_commit,
    read_commit_subject,
    run_changelog_check,
    run_post_correct,
    run_pre_commit_changelog,
    run_update_unreleased,
    validate_branch_name,
    validate_commit_subject,
)


def test_validate_branch_name_accepts_feature_branch() -> None:
    assert validate_branch_name("feat/add-hook-checks") is None


def test_validate_branch_name_accepts_release_branch() -> None:
    assert validate_branch_name("release/v1.2.3") is None


def test_validate_branch_name_accepts_main_branch() -> None:
    assert validate_branch_name("main") is None


def test_validate_branch_name_accepts_magic_ai_branch() -> None:
    assert validate_branch_name("claude/update-hook-checks") is None


def test_validate_branch_name_rejects_invalid_slug() -> None:
    problem = validate_branch_name("feat/Add Hook Checks")

    assert problem is not None
    assert "lowercase letters, digits, and hyphens" in problem


def test_validate_branch_name_rejects_invalid_release_version() -> None:
    problem = validate_branch_name("release/vbanana")

    assert problem is not None
    assert "release/v<semver>" in problem


def test_validate_branch_name_rejects_missing_separator() -> None:
    problem = validate_branch_name("feat-add-parser")

    assert problem is not None
    assert "<type>/<kebab-case-description>" in problem


def test_validate_branch_name_rejects_too_long_slug() -> None:
    problem = validate_branch_name(f"feat/{'a' * 65}")

    assert problem is not None
    assert "too long" in problem


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


def test_validate_commit_subject_accepts_merge_commit() -> None:
    assert validate_commit_subject("Merge branch 'feat/add-parser'") is None


def test_validate_commit_subject_rejects_empty_subject() -> None:
    assert validate_commit_subject("") == "Commit message is empty."


def test_validate_commit_subject_rejects_invalid_commit() -> None:
    problem = validate_commit_subject("update stuff")

    assert problem is not None
    assert "Conventional Commits" in problem


def test_branch_requires_changelog_for_feature_branch() -> None:
    assert branch_requires_changelog("feat/add-hook-checks") is True


def test_branch_requires_changelog_skips_maintenance_branch() -> None:
    assert branch_requires_changelog("chore/update-tooling") is False


def test_branch_requires_changelog_skips_invalid_branch_type() -> None:
    assert branch_requires_changelog("wizard/update-tooling") is False


def test_commit_subject_requires_changelog_for_breaking_change() -> None:
    assert commit_subject_requires_changelog("chore!: remove deprecated flow") is True


def test_commit_subject_requires_changelog_skips_chore_commit() -> None:
    assert commit_subject_requires_changelog("chore: update tooling") is False


def test_commit_subject_requires_changelog_skips_invalid_subject() -> None:
    assert commit_subject_requires_changelog("just do the thing") is False


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


def test_run_dirty_tree_check_accepts_clean_tree(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hooks.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(hooks.git, "working_tree_clean", lambda cwd: True)

    assert hooks.run_dirty_tree_check(Path.cwd(), title="Dirty tree validation failed.") == 0


def test_run_dirty_tree_check_rejects_non_git_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hooks.git, "is_git_repository", lambda cwd: False)

    assert hooks.run_dirty_tree_check(Path.cwd(), title="Dirty tree validation failed.") == 1


def test_run_pre_commit_uses_current_branch_and_extra_types(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(hooks.git, "current_branch", lambda cwd: "snyk/fix-vuln")
    monkeypatch.setattr(hooks, "load_extra_branch_types", lambda cwd: ("snyk",))

    def fake_run_branch_name_check(
        branch_name: str, *, title: str, extra_types: tuple[str, ...]
    ) -> int:
        captured["branch_name"] = branch_name
        captured["title"] = title
        captured["extra_types"] = extra_types
        return 7

    monkeypatch.setattr(hooks, "run_branch_name_check", fake_run_branch_name_check)

    assert hooks.run_pre_commit(Path.cwd()) == 7
    assert captured == {
        "branch_name": "snyk/fix-vuln",
        "title": "Commit blocked by branch naming policy.",
        "extra_types": ("snyk",),
    }


def test_run_dirty_tree_check_rejects_dirty_tree(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hooks.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(hooks.git, "working_tree_clean", lambda cwd: False)
    monkeypatch.setattr(
        hooks.git,
        "status_porcelain",
        lambda cwd: [" M src/repo_release_tools/cli.py", "?? docs/git-magic.md"],
    )

    assert hooks.run_dirty_tree_check(Path.cwd(), title="Dirty tree validation failed.") == 1


def test_run_dirty_tree_check_reports_status_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hooks.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(hooks.git, "working_tree_clean", lambda cwd: False)
    monkeypatch.setattr(
        hooks.git,
        "status_porcelain",
        lambda cwd: (_ for _ in ()).throw(RuntimeError("git status --short failed (exit 128)")),
    )

    assert hooks.run_dirty_tree_check(Path.cwd(), title="Dirty tree validation failed.") == 1


def test_main_check_dirty_tree_uses_hook_entrypoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hooks.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(hooks.git, "working_tree_clean", lambda cwd: True)

    assert hooks.main(["check-dirty-tree"]) == 0


def test_run_pre_commit_changelog_rejects_missing_staged_changelog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(hooks.git, "current_branch", lambda cwd: "feat/add-hook-checks")
    monkeypatch.setattr(hooks, "staged_files", lambda cwd: ["src/repo_release_tools/hooks.py"])

    assert run_pre_commit_changelog(Path.cwd()) == 1


def test_run_pre_commit_changelog_accepts_staged_changelog(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hooks.git, "current_branch", lambda cwd: "feat/add-hook-checks")
    monkeypatch.setattr(
        hooks,
        "staged_files",
        lambda cwd: ["src/repo_release_tools/hooks.py", "CHANGELOG.md"],
    )

    assert run_pre_commit_changelog(Path.cwd()) == 0


def test_run_pre_commit_changelog_skips_non_changelog_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(hooks.git, "current_branch", lambda cwd: "chore/update-guide")
    monkeypatch.setattr(
        hooks, "staged_files", lambda cwd: pytest.fail("staged_files should not run")
    )

    assert run_pre_commit_changelog(Path.cwd()) == 0


def test_run_pre_commit_changelog_reports_workflow_load_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        hooks,
        "_detect_changelog_workflow",
        lambda cwd: (_ for _ in ()).throw(RuntimeError("bad config")),
    )

    assert run_pre_commit_changelog(Path.cwd()) == 1


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


def test_run_changelog_check_skips_non_changelog_subject() -> None:
    assert (
        run_changelog_check(
            "chore: rewrite docs",
            cwd=Path.cwd(),
            changed_files=[],
            title="Changelog validation failed.",
        )
        == 0
    )


def test_run_changelog_check_reports_strategy_resolution_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        hooks,
        "_resolve_changelog_strategy",
        lambda cwd, strategy: (_ for _ in ()).throw(RuntimeError("bad workflow")),
    )

    assert (
        run_changelog_check(
            "feat: add parser",
            cwd=Path.cwd(),
            changed_files=[],
            title="Changelog validation failed.",
        )
        == 1
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
    assert "entry: rrt-hooks update-unreleased" in manifest


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
    assert "changelog-strategy:" in action_text
    assert "rrt-hooks check-changelog" in action_text
    assert "check-dirty-tree:" in action_text
    assert "rrt-hooks check-dirty-tree" in action_text
    assert '--changelog-file "$INPUT_CHANGELOG_FILE"' in action_text
    assert "--ref HEAD" in action_text
    assert '--strategy "${INPUT_CHANGELOG_STRATEGY' in action_text
    assert 'default: "auto"' in action_text
    assert "--branch" in action_text


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


def test_run_post_correct_returns_zero_when_no_diff(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n- feat: something\n", encoding="utf-8")
    monkeypatch.setattr(hooks, "collect_squash_changelog_hunks", lambda *a, **kw: ([], frozenset()))

    assert run_post_correct(tmp_path, changelog_file="CHANGELOG.md") == 0


def test_run_post_correct_returns_zero_when_already_clean(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n- fix typo\n", encoding="utf-8")
    monkeypatch.setattr(
        hooks,
        "collect_squash_changelog_hunks",
        lambda *a, **kw: (["- fix typo"], frozenset({3})),
    )

    assert run_post_correct(tmp_path, changelog_file="CHANGELOG.md") == 0


def test_run_post_correct_cleans_contradicting_entries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
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


def test_main_changelog_post_correct_no_diff(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n- fix typo\n", encoding="utf-8")
    monkeypatch.setattr(hooks, "collect_squash_changelog_hunks", lambda *a, **kw: ([], frozenset()))
    monkeypatch.chdir(tmp_path)

    assert hooks.main(["changelog", "post-correct"]) == 0


def test_main_changelog_post_correct_explicit_commit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n- fix typo\n", encoding="utf-8")
    monkeypatch.setattr(
        hooks,
        "collect_squash_changelog_hunks",
        lambda *a, **kw: (["- fix typo"], frozenset({3})),
    )
    monkeypatch.chdir(tmp_path)

    assert hooks.main(["changelog", "post-correct", "--squash-commit", "abc1234"]) == 0


# ---------------------------------------------------------------------------
# Phase 1 — --commit path tests
# ---------------------------------------------------------------------------


def test_run_post_correct_commits_when_flag_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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
    git_calls: list[list[str]] = []
    monkeypatch.setattr(hooks.git, "run", lambda cmd, *a, **kw: git_calls.append(cmd) or "")

    result = run_post_correct(tmp_path, changelog_file="CHANGELOG.md", commit=True)

    assert result == 0
    assert any(c[1] == "add" for c in git_calls)
    assert any(c[1] == "commit" for c in git_calls)


def test_run_post_correct_returns_failure_on_commit_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n### Maintenance\n- add Node 26\n- remove Node 26\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        hooks,
        "collect_squash_changelog_hunks",
        lambda *a, **kw: (
            ["### Maintenance", "- add Node 26", "- remove Node 26"],
            frozenset({3, 4, 5}),
        ),
    )
    monkeypatch.setattr(
        hooks.git,
        "run",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("git commit failed (exit 1)")),
    )

    assert run_post_correct(tmp_path, changelog_file="CHANGELOG.md", commit=True) == 1


def test_main_changelog_post_correct_with_commit_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n### Maintenance\n- add Node 26\n- remove Node 26\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        hooks,
        "collect_squash_changelog_hunks",
        lambda *a, **kw: (
            ["### Maintenance", "- add Node 26", "- remove Node 26"],
            frozenset({3, 4, 5}),
        ),
    )
    monkeypatch.setattr(hooks.git, "run", lambda *a, **kw: "")
    monkeypatch.chdir(tmp_path)

    assert hooks.main(["changelog", "post-correct", "--commit"]) == 0


# ---------------------------------------------------------------------------
# Phase 2 — collect_squash_changelog_hunks unit tests
# ---------------------------------------------------------------------------


def test_collect_squash_changelog_hunks_parses_single_hunk(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    diff = "@@ -1,3 +1,5 @@\n # Changelog\n \n+### Maintenance\n+- add Node 26\n - fix typo\n"
    monkeypatch.setattr(hooks.git, "capture_checked", lambda *a, **kw: diff)

    added, positions = collect_squash_changelog_hunks(tmp_path)

    assert added == ["### Maintenance", "- add Node 26"]
    assert positions == frozenset({3, 4})


def test_collect_squash_changelog_hunks_multi_hunk(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    diff = (
        "@@ -1,2 +1,3 @@\n"
        " # Changelog\n"
        "+## [Unreleased]\n"
        " \n"
        "@@ -5,2 +7,3 @@\n"
        " ### Added\n"
        "+- feat: new feature\n"
        " - existing\n"
    )
    monkeypatch.setattr(hooks.git, "capture_checked", lambda *a, **kw: diff)

    added, positions = collect_squash_changelog_hunks(tmp_path)

    assert added == ["## [Unreleased]", "- feat: new feature"]
    assert positions == frozenset({2, 8})


def test_collect_squash_changelog_hunks_empty_diff(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(hooks.git, "capture_checked", lambda *a, **kw: "")

    added, positions = collect_squash_changelog_hunks(tmp_path)

    assert added == []
    assert positions == frozenset()


# ---------------------------------------------------------------------------
# Phase 3 — invalid ref test
# ---------------------------------------------------------------------------


def test_run_post_correct_fails_on_invalid_ref(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n", encoding="utf-8")
    monkeypatch.setattr(
        hooks.git,
        "capture_checked",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("git show bad-ref failed (exit 128)")),
    )

    assert run_post_correct(tmp_path, ref="bad-ref", changelog_file="CHANGELOG.md") == 1


# ---------------------------------------------------------------------------
# Phase 4 — dedup_changelog_entries edge-case tests
# ---------------------------------------------------------------------------


def test_dedup_changelog_entries_empty_input() -> None:
    assert dedup_changelog_entries([]) == []


def test_dedup_changelog_entries_headers_only() -> None:
    lines = ["## [Unreleased]", "### Added", "### Fixed"]
    assert dedup_changelog_entries(lines) == lines


def test_dedup_changelog_entries_all_duplicates() -> None:
    lines = ["- fix typo", "- fix typo", "- fix typo"]
    result = dedup_changelog_entries(lines)
    assert result.count("- fix typo") == 1


# ---------------------------------------------------------------------------
# Phase 5 — Bot branch types and extra_branch_types
# ---------------------------------------------------------------------------


def test_validate_branch_name_accepts_dependabot_branch() -> None:
    assert validate_branch_name("dependabot/npm_and_yarn/lodash-4.17.21") is None


def test_validate_branch_name_accepts_renovate_branch() -> None:
    assert validate_branch_name("renovate/lodash-4.x") is None


def test_validate_branch_name_accepts_extra_type() -> None:
    assert validate_branch_name("snyk/fix-vuln", extra_types=("snyk",)) is None


def test_validate_branch_name_rejects_unknown_type_without_extra() -> None:
    problem = validate_branch_name("snyk/fix-vuln")
    assert problem is not None
    assert "snyk" in problem


def test_validate_branch_name_lists_bot_types_in_error() -> None:
    problem = validate_branch_name("wizard/fix-something")
    assert problem is not None
    assert "dependabot" in problem
    assert "renovate" in problem


def test_validate_branch_name_lists_extra_types_in_error() -> None:
    problem = validate_branch_name("wizard/fix-something", extra_types=("greenkeeper",))
    assert problem is not None
    assert "greenkeeper" in problem


def test_main_check_branch_name_accepts_dependabot_branch() -> None:
    assert hooks.main(["check-branch-name", "--branch", "dependabot/npm_and_yarn/foo-1.0"]) == 0


def test_main_check_branch_name_accepts_renovate_branch() -> None:
    assert hooks.main(["check-branch-name", "--branch", "renovate/lodash-4.x"]) == 0


def test_validate_branch_name_rejects_empty_slug_for_bot_branch() -> None:
    problem = validate_branch_name("dependabot/")
    assert problem is not None
    assert "non-empty slug" in problem


def test_validate_branch_name_rejects_empty_slug_for_extra_type() -> None:
    problem = validate_branch_name("snyk/", extra_types=("snyk",))
    assert problem is not None
    assert "non-empty slug" in problem


def test_main_check_branch_name_accepts_custom_prefix_from_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Extra branch types loaded from config are accepted without explicit --extra-types."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """\
[tool.rrt]
extra_branch_types = ["snyk"]

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    assert hooks.main(["check-branch-name", "--branch", "snyk/fix-vuln-123"]) == 0


def test_main_check_branch_name_rejects_custom_prefix_not_in_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A branch type absent from config is rejected even if other custom types are configured."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """\
[tool.rrt]
extra_branch_types = ["greenkeeper"]

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    assert hooks.main(["check-branch-name", "--branch", "snyk/fix-vuln-123"]) == 1


# ---------------------------------------------------------------------------
# run_changelog_check – strategy and branch
# ---------------------------------------------------------------------------


def test_run_changelog_check_skips_renovate_branch() -> None:
    assert (
        run_changelog_check(
            "fix(deps): update dependency foo",
            cwd=Path.cwd(),
            changed_files=[],
            title="Changelog validation failed.",
            branch="renovate/foo-1.x",
        )
        == 0
    )


def test_run_changelog_check_skips_dependabot_branch() -> None:
    assert (
        run_changelog_check(
            "fix(deps): update dependency bar",
            cwd=Path.cwd(),
            changed_files=[],
            title="Changelog validation failed.",
            branch="dependabot/npm_and_yarn/bar-2.x",
        )
        == 0
    )


def test_run_changelog_check_strategy_release_only_skips_check() -> None:
    assert (
        run_changelog_check(
            "feat: brand new feature",
            cwd=Path.cwd(),
            changed_files=[],
            title="Changelog validation failed.",
            strategy="release-only",
        )
        == 0
    )


def test_run_changelog_check_auto_uses_squash_workflow(tmp_path: Path) -> None:
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]
changelog_workflow = "squash"

[[tool.rrt.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )

    assert (
        run_changelog_check(
            "feat: brand new feature",
            cwd=tmp_path,
            changed_files=[],
            title="Changelog validation failed.",
        )
        == 0
    )


def test_run_changelog_check_strategy_unreleased_passes_when_section_nonempty(
    tmp_path: Path,
) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Fixed\n- fix null pointer\n",
        encoding="utf-8",
    )
    assert (
        run_changelog_check(
            "fix: handle null case",
            cwd=tmp_path,
            changed_files=[],
            changelog_file="CHANGELOG.md",
            title="Changelog validation failed.",
            strategy="unreleased",
        )
        == 0
    )


def test_run_changelog_check_strategy_unreleased_fails_when_section_empty(
    tmp_path: Path,
) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n## [Unreleased]\n\n## [1.0.0] - 2025-01-01\n",
        encoding="utf-8",
    )
    assert (
        run_changelog_check(
            "feat: add new widget",
            cwd=tmp_path,
            changed_files=[],
            changelog_file="CHANGELOG.md",
            title="Changelog validation failed.",
            strategy="unreleased",
        )
        == 1
    )


def test_run_changelog_check_default_strategy_still_requires_file_in_changeset() -> None:
    # per-commit strategy: changelog not in changed_files → fail
    assert (
        run_changelog_check(
            "feat: add dark mode",
            cwd=Path.cwd(),
            changed_files=["src/main.py"],
            title="Changelog validation failed.",
        )
        == 1
    )


# ---------------------------------------------------------------------------
# run_update_unreleased
# ---------------------------------------------------------------------------


def test_run_update_unreleased_appends_bullet_and_stages_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n", encoding="utf-8")
    staged: list[list[str]] = []
    monkeypatch.setattr(hooks.git, "run", lambda cmd, cwd, **kw: staged.append(cmd))

    result = run_update_unreleased(tmp_path, subject="feat: add dark mode")

    assert result == 0
    content = changelog.read_text(encoding="utf-8")
    assert "add dark mode" in content
    assert any("git" in cmd[0] and "add" in cmd for cmd in staged)


def test_run_update_unreleased_skips_non_changelog_commits(
    tmp_path: Path,
) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    original = "# Changelog\n"
    changelog.write_text(original, encoding="utf-8")

    result = run_update_unreleased(tmp_path, subject="chore: update lockfile")

    assert result == 0
    assert changelog.read_text(encoding="utf-8") == original


def test_run_update_unreleased_skips_for_squash_workflow(tmp_path: Path) -> None:
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]
changelog_workflow = "squash"

[[tool.rrt.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )
    changelog = tmp_path / "CHANGELOG.md"
    original = "# Changelog\n"
    changelog.write_text(original, encoding="utf-8")

    result = run_update_unreleased(tmp_path, subject="feat: new widget")

    assert result == 0
    assert changelog.read_text(encoding="utf-8") == original


def test_run_update_unreleased_reports_workflow_load_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        hooks,
        "_detect_changelog_workflow",
        lambda cwd: (_ for _ in ()).throw(RuntimeError("bad config")),
    )

    assert run_update_unreleased(Path.cwd(), subject="feat: parser") == 1


def test_run_pre_commit_changelog_skips_for_squash_workflow(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]
changelog_workflow = "squash"

[[tool.rrt.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(hooks.git, "current_branch", lambda cwd: "feat/add-hook-checks")
    monkeypatch.setattr(hooks, "staged_files", lambda cwd: ["src/repo_release_tools/hooks.py"])

    assert run_pre_commit_changelog(tmp_path) == 0


def test_run_update_unreleased_returns_one_when_changelog_missing(
    tmp_path: Path,
) -> None:
    result = run_update_unreleased(tmp_path, subject="feat: new widget")
    assert result == 1


def test_run_update_unreleased_no_write_when_content_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When the bullet is already present the file should not be rewritten."""
    existing = "# Changelog\n\n## [Unreleased]\n\n### Added\n- new widget\n"
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(existing, encoding="utf-8")
    staged: list[list[str]] = []
    monkeypatch.setattr(hooks.git, "run", lambda cmd, cwd, **kw: staged.append(cmd))

    result = run_update_unreleased(tmp_path, subject="feat: new widget")

    assert result == 0
    assert changelog.read_text(encoding="utf-8") == existing
    assert staged == []


def test_main_update_unreleased_accepts_explicit_subject(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n", encoding="utf-8")
    monkeypatch.setattr(hooks.git, "run", lambda *a, **kw: None)
    monkeypatch.chdir(tmp_path)

    result = hooks.main(["update-unreleased", "--subject", "feat: shiny new thing"])

    assert result == 0
    assert "shiny new thing" in changelog.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# run_update_unreleased – RST / TXT format
# ---------------------------------------------------------------------------


def test_run_update_unreleased_creates_rst_unreleased_section(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With a .rst changelog the Unreleased section must use RST underline notation."""
    changelog = tmp_path / "CHANGELOG.rst"
    changelog.write_text("Changelog\n=========\n", encoding="utf-8")
    monkeypatch.setattr(hooks.git, "run", lambda *a, **kw: None)

    result = run_update_unreleased(
        tmp_path, subject="feat: rst feature", changelog_file="CHANGELOG.rst"
    )

    assert result == 0
    content = changelog.read_text(encoding="utf-8")
    assert "## [" not in content
    assert "### " not in content
    assert "Unreleased\n" in content
    assert "~" in content  # RST subsection underline
    assert "rst feature" in content


def test_run_update_unreleased_creates_txt_unreleased_section(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With a .txt changelog the Unreleased section must use RST underline notation."""
    changelog = tmp_path / "CHANGELOG.txt"
    changelog.write_text("Changelog\n=========\n", encoding="utf-8")
    monkeypatch.setattr(hooks.git, "run", lambda *a, **kw: None)

    result = run_update_unreleased(tmp_path, subject="fix: txt fix", changelog_file="CHANGELOG.txt")

    assert result == 0
    content = changelog.read_text(encoding="utf-8")
    assert "## [" not in content
    assert "txt fix" in content
    assert "~" in content  # RST subsection underline


# ---------------------------------------------------------------------------
# run_update_unreleased – --message-file argument (lefthook integration)
# ---------------------------------------------------------------------------


def test_main_update_unreleased_reads_subject_from_message_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """--message-file takes priority and its content is used as the commit subject."""
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n", encoding="utf-8")
    monkeypatch.setattr(hooks.git, "run", lambda *a, **kw: None)
    monkeypatch.chdir(tmp_path)

    msg_file = tmp_path / "COMMIT_EDITMSG"
    msg_file.write_text("feat: add widget from file\n", encoding="utf-8")

    result = hooks.main(["update-unreleased", "--message-file", str(msg_file)])

    assert result == 0
    assert "add widget from file" in changelog.read_text(encoding="utf-8")


def test_main_update_unreleased_message_file_noop_for_maintenance_commit(
    tmp_path: Path,
) -> None:
    """--message-file with a chore commit leaves CHANGELOG.md unchanged."""
    changelog = tmp_path / "CHANGELOG.md"
    original = "# Changelog\n"
    changelog.write_text(original, encoding="utf-8")

    msg_file = tmp_path / "COMMIT_EDITMSG"
    msg_file.write_text("chore: update deps\n", encoding="utf-8")

    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        result = hooks.main(["update-unreleased", "--message-file", str(msg_file)])
    finally:
        os.chdir(old_cwd)

    assert result == 0
    assert changelog.read_text(encoding="utf-8") == original


def test_main_update_unreleased_message_file_takes_priority_over_subject(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When both --message-file and --subject are given, --message-file wins."""
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n", encoding="utf-8")
    monkeypatch.setattr(hooks.git, "run", lambda *a, **kw: None)
    monkeypatch.chdir(tmp_path)

    msg_file = tmp_path / "COMMIT_EDITMSG"
    msg_file.write_text("feat: from file wins\n", encoding="utf-8")

    result = hooks.main(
        [
            "update-unreleased",
            "--message-file",
            str(msg_file),
            "--subject",
            "feat: from subject ignored",
        ]
    )

    assert result == 0
    content = changelog.read_text(encoding="utf-8")
    assert "from file wins" in content
    assert "from subject ignored" not in content


def test_main_update_unreleased_message_file_missing(tmp_path: Path) -> None:
    """--message-file with a non-existent path returns failure exit code."""
    missing = tmp_path / "no-such-file.txt"

    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        result = hooks.main(["update-unreleased", "--message-file", str(missing)])
    finally:
        os.chdir(old_cwd)

    assert result == 1


def test_main_update_unreleased_message_file_unreadable(tmp_path: Path) -> None:
    """--message-file with an unreadable file returns failure exit code."""
    bad_file = tmp_path / "COMMIT_EDITMSG"
    bad_file.write_bytes(b"\xff\xfe invalid utf-8 \x80")

    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        result = hooks.main(["update-unreleased", "--message-file", str(bad_file)])
    finally:
        os.chdir(old_cwd)

    assert result == 1


def test_main_pre_commit_dispatch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(hooks, "run_pre_commit", lambda cwd: 11)

    assert hooks.main(["pre-commit"]) == 11


def test_main_pre_commit_changelog_dispatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(hooks, "run_pre_commit_changelog", lambda cwd, *, changelog_file: 12)

    assert hooks.main(["pre-commit-changelog", "--changelog-file", "NEWS.md"]) == 12


def test_main_update_unreleased_falls_back_to_commit_editmsg(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n", encoding="utf-8")
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "COMMIT_EDITMSG").write_text("feat: fallback subject\n", encoding="utf-8")
    monkeypatch.setattr(hooks.git, "run", lambda *a, **kw: None)
    monkeypatch.chdir(tmp_path)

    result = hooks.main(["update-unreleased"])

    assert result == 0
    assert "fallback subject" in changelog.read_text(encoding="utf-8")


def test_main_update_unreleased_uses_empty_subject_when_no_commit_editmsg(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, str] = {}
    monkeypatch.chdir(tmp_path)

    def fake_run_update_unreleased(cwd: Path, *, subject: str, changelog_file: str) -> int:
        captured["subject"] = subject
        captured["changelog_file"] = changelog_file
        return 0

    monkeypatch.setattr(hooks, "run_update_unreleased", fake_run_update_unreleased)

    assert hooks.main(["update-unreleased"]) == 0
    assert captured == {"subject": "", "changelog_file": "CHANGELOG.md"}


def test_detect_changelog_workflow_defaults_when_config_missing(tmp_path: Path) -> None:
    assert _detect_changelog_workflow(tmp_path) == "incremental"


def test_detect_changelog_workflow_defaults_for_missing_tool_rrt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        hooks,
        "load_or_autodetect_config",
        lambda cwd: (_ for _ in ()).throw(
            ValueError("Missing rrt configuration in supported config files: pyproject.toml")
        ),
    )

    assert _detect_changelog_workflow(Path.cwd()) == "incremental"


def test_detect_changelog_workflow_raises_runtime_error_for_invalid_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        hooks,
        "load_or_autodetect_config",
        lambda cwd: (_ for _ in ()).throw(ValueError("totally broken config")),
    )

    with pytest.raises(RuntimeError, match="Failed to load changelog_workflow configuration"):
        _detect_changelog_workflow(Path.cwd())


def test_resolve_changelog_strategy_returns_explicit_strategy() -> None:
    assert _resolve_changelog_strategy(Path.cwd(), "unreleased") == "unreleased"


def test_resolve_changelog_strategy_uses_incremental_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(hooks, "_detect_changelog_workflow", lambda cwd: "incremental")

    assert _resolve_changelog_strategy(Path.cwd(), "auto") == "per-commit"


# ---------------------------------------------------------------------------
# is_changelog_meta_commit
# ---------------------------------------------------------------------------


def test_is_changelog_meta_commit_true_for_fix_update_changelog() -> None:
    assert is_changelog_meta_commit("fix: update changelog entries") is True


def test_is_changelog_meta_commit_true_for_feat_with_changelog_word() -> None:
    assert is_changelog_meta_commit("feat: update changelog to reflect new api") is True


def test_is_changelog_meta_commit_true_case_insensitive() -> None:
    assert is_changelog_meta_commit("fix: correct CHANGELOG formatting") is True


def test_is_changelog_meta_commit_false_for_normal_feat() -> None:
    assert is_changelog_meta_commit("feat: add dark mode") is False


def test_is_changelog_meta_commit_false_for_normal_fix() -> None:
    assert is_changelog_meta_commit("fix: resolve login timeout") is False


def test_is_changelog_meta_commit_false_for_unparseable_subject() -> None:
    assert is_changelog_meta_commit("not a conventional commit at all") is False


def test_is_changelog_meta_commit_false_for_changelog_product_feature() -> None:
    """A commit adding a product feature named 'changelog' must NOT be skipped."""
    assert is_changelog_meta_commit("feat: add changelog parser") is False


def test_is_changelog_meta_commit_false_for_changelog_bug_fix() -> None:
    """A bug fix for a product component named 'changelog' must NOT be skipped."""
    assert is_changelog_meta_commit("fix: changelog parsing regression") is False


# ---------------------------------------------------------------------------
# run_update_unreleased – changelog-meta-commit skip guard
# ---------------------------------------------------------------------------


def test_run_update_unreleased_skips_changelog_meta_commit(
    tmp_path: Path,
) -> None:
    """A commit whose description mentions 'changelog' must not add a bullet."""
    changelog = tmp_path / "CHANGELOG.md"
    original = "# Changelog\n"
    changelog.write_text(original, encoding="utf-8")

    result = run_update_unreleased(tmp_path, subject="fix: update changelog entries")

    assert result == 0
    assert changelog.read_text(encoding="utf-8") == original


def test_run_update_unreleased_skips_changelog_meta_commit_case_insensitive(
    tmp_path: Path,
) -> None:
    """The guard is case-insensitive on 'changelog'."""
    changelog = tmp_path / "CHANGELOG.md"
    original = "# Changelog\n"
    changelog.write_text(original, encoding="utf-8")

    result = run_update_unreleased(tmp_path, subject="feat: correct CHANGELOG formatting")

    assert result == 0
    assert changelog.read_text(encoding="utf-8") == original


def test_run_update_unreleased_does_not_skip_unrelated_feat(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A normal feat commit (no 'changelog' in description) still writes a bullet."""
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n", encoding="utf-8")
    monkeypatch.setattr(hooks.git, "run", lambda *a, **kw: None)

    result = run_update_unreleased(tmp_path, subject="feat: add pagination")

    assert result == 0
    assert "add pagination" in changelog.read_text(encoding="utf-8")


def test_main_doctor_dispatches_to_cmd_doctor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hooks, "cmd_doctor", lambda parsed: 7)

    assert hooks.main(["doctor"]) == 7
