"""Comprehensive tests for the top-level repo_release_tools.hooks module."""

from __future__ import annotations

from pathlib import Path

import pytest

import repo_release_tools.hooks as hooks

# ---------------------------------------------------------------------------
# validate_branch_name — all branches
# ---------------------------------------------------------------------------


def test_validate_branch_name_empty() -> None:
    assert hooks.validate_branch_name("") is None


def test_validate_branch_name_allowed_name_main() -> None:
    assert hooks.validate_branch_name("main") is None


def test_validate_branch_name_allowed_name_develop() -> None:
    assert hooks.validate_branch_name("develop") is None


def test_validate_branch_name_release_valid_semver() -> None:
    assert hooks.validate_branch_name("release/v1.2.3") is None


def test_validate_branch_name_release_invalid_semver() -> None:
    result = hooks.validate_branch_name("release/vnotasemver")
    assert result is not None
    assert "release/v<semver>" in result


def test_validate_branch_name_no_slash() -> None:
    result = hooks.validate_branch_name("mybranch")
    assert result is not None
    assert "<type>/<kebab-case-description>" in result


def test_validate_branch_name_invalid_type() -> None:
    result = hooks.validate_branch_name("unknown/add-stuff")
    assert result is not None
    assert "invalid" in result.lower()


def test_validate_branch_name_bot_branch_with_slug() -> None:
    assert hooks.validate_branch_name("dependabot/npm/lodash-4.17.21") is None


def test_validate_branch_name_bot_branch_empty_slug() -> None:
    result = hooks.validate_branch_name("dependabot/")
    assert result is not None
    assert "non-empty slug" in result


def test_validate_branch_name_extra_type_accepted() -> None:
    assert hooks.validate_branch_name("snyk/fix-vuln", extra_types=("snyk",)) is None


def test_validate_branch_name_extra_type_empty_slug() -> None:
    result = hooks.validate_branch_name("snyk/", extra_types=("snyk",))
    assert result is not None
    assert "non-empty slug" in result


def test_validate_branch_name_magic_type() -> None:
    assert hooks.validate_branch_name("claude/improve-output") is None


def test_validate_branch_name_slug_too_long() -> None:
    long_slug = "a" * 200
    result = hooks.validate_branch_name(f"feat/{long_slug}")
    assert result is not None
    assert "too long" in result


def test_validate_branch_name_slug_bad_format() -> None:
    result = hooks.validate_branch_name("feat/ADD_STUFF")
    assert result is not None
    assert "kebab-case" in result


def test_validate_branch_name_feature_branch() -> None:
    assert hooks.validate_branch_name("feat/add-hook-checks") is None


# ---------------------------------------------------------------------------
# read_commit_subject
# ---------------------------------------------------------------------------


def test_read_commit_subject_returns_first_non_empty_line(tmp_path: Path) -> None:
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text("\n\n  \nfeat(cli): add parser\n\n# comment\n", encoding="utf-8")
    assert hooks.read_commit_subject(msg) == "feat(cli): add parser"


def test_read_commit_subject_empty_file(tmp_path: Path) -> None:
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text("", encoding="utf-8")
    assert hooks.read_commit_subject(msg) == ""


# ---------------------------------------------------------------------------
# validate_commit_subject — all branches
# ---------------------------------------------------------------------------


def test_validate_commit_subject_empty() -> None:
    assert hooks.validate_commit_subject("") == "Commit message is empty."


def test_validate_commit_subject_merge() -> None:
    assert hooks.validate_commit_subject("Merge pull request #1") is None


def test_validate_commit_subject_fixup_valid() -> None:
    assert hooks.validate_commit_subject("fixup! feat(cli): add parser") is None


def test_validate_commit_subject_squash_valid() -> None:
    assert hooks.validate_commit_subject("squash! fix: repair config") is None


def test_validate_commit_subject_fixup_invalid() -> None:
    # fixup! prefix with non-conventional body → should fail
    result = hooks.validate_commit_subject("fixup! not-a-conventional-commit")
    assert result is not None


def test_validate_commit_subject_valid_conventional() -> None:
    assert hooks.validate_commit_subject("feat(cli): add hook checks") is None


def test_validate_commit_subject_invalid() -> None:
    result = hooks.validate_commit_subject("WIP stuff")
    assert result is not None
    assert "Conventional Commits" in result


# ---------------------------------------------------------------------------
# commit_type_requires_changelog / branch_requires_changelog /
# commit_subject_requires_changelog / is_changelog_meta_commit
# ---------------------------------------------------------------------------


def test_commit_type_requires_changelog_breaking() -> None:
    assert hooks.commit_type_requires_changelog("chore", breaking=True) is True


def test_commit_type_requires_changelog_maintenance() -> None:
    assert hooks.commit_type_requires_changelog("chore") is False


def test_commit_type_requires_changelog_feat() -> None:
    assert hooks.commit_type_requires_changelog("feat") is True


def test_branch_requires_changelog_empty() -> None:
    assert hooks.branch_requires_changelog("") is False


def test_branch_requires_changelog_main() -> None:
    assert hooks.branch_requires_changelog("main") is False


def test_branch_requires_changelog_release() -> None:
    assert hooks.branch_requires_changelog("release/v1.0.0") is False


def test_branch_requires_changelog_no_slash() -> None:
    assert hooks.branch_requires_changelog("myfeature") is False


def test_branch_requires_changelog_invalid_type() -> None:
    assert hooks.branch_requires_changelog("unknown/stuff") is False


def test_branch_requires_changelog_chore() -> None:
    assert hooks.branch_requires_changelog("chore/update-deps") is False


def test_branch_requires_changelog_feat() -> None:
    assert hooks.branch_requires_changelog("feat/add-parser") is True


def test_commit_subject_requires_changelog_unparseable() -> None:
    assert hooks.commit_subject_requires_changelog("WIP: stuff") is False


def test_commit_subject_requires_changelog_feat() -> None:
    assert hooks.commit_subject_requires_changelog("feat: add parser") is True


def test_commit_subject_requires_changelog_chore() -> None:
    assert hooks.commit_subject_requires_changelog("chore: update deps") is False


def test_is_changelog_meta_commit_unparseable() -> None:
    assert hooks.is_changelog_meta_commit("WIP stuff") is False


def test_is_changelog_meta_commit_matches() -> None:
    assert hooks.is_changelog_meta_commit("fix: update changelog entries") is True


def test_is_changelog_meta_commit_no_match() -> None:
    assert hooks.is_changelog_meta_commit("feat: add changelog parser") is False


def test_parse_subject_for_changelog_strips_fixup_prefix() -> None:
    # Covers _parse_subject_for_changelog line 133 (the partition branch).
    # commit_subject_requires_changelog calls _parse_subject_for_changelog internally.
    assert hooks.commit_subject_requires_changelog("fixup! feat: add parser") is True


def test_parse_subject_for_changelog_strips_squash_prefix() -> None:
    assert hooks.is_changelog_meta_commit("squash! fix: update changelog entries") is True


# ---------------------------------------------------------------------------
# _normalize_repo_path
# ---------------------------------------------------------------------------


def test_normalize_repo_path_relative() -> None:
    cwd = Path("/some/project")
    result = hooks._normalize_repo_path("CHANGELOG.md", cwd=cwd)
    assert result == "CHANGELOG.md"


def test_normalize_repo_path_absolute_within_cwd() -> None:
    cwd = Path("/some/project")
    result = hooks._normalize_repo_path("/some/project/CHANGELOG.md", cwd=cwd)
    assert result == "CHANGELOG.md"


def test_normalize_repo_path_absolute_outside_cwd() -> None:
    cwd = Path("/some/project")
    result = hooks._normalize_repo_path("/other/path/CHANGELOG.md", cwd=cwd)
    assert result == "/other/path/CHANGELOG.md"


# ---------------------------------------------------------------------------
# staged_files / changed_files_for_ref / changelog_is_updated
# ---------------------------------------------------------------------------


def test_staged_files_returns_parsed_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hooks.git, "capture", lambda cmd, cwd: "CHANGELOG.md\nhooks.py\n")
    result = hooks.staged_files(Path.cwd())
    assert result == ["CHANGELOG.md", "hooks.py"]


def test_staged_files_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hooks.git, "capture", lambda cmd, cwd: "")
    assert hooks.staged_files(Path.cwd()) == []


def test_changed_files_for_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hooks.git, "capture", lambda cmd, cwd: "src/foo.py\n")
    result = hooks.changed_files_for_ref(Path.cwd(), "HEAD")
    assert result == ["src/foo.py"]


def test_changelog_is_updated_true() -> None:
    result = hooks.changelog_is_updated(
        ["CHANGELOG.md", "src/foo.py"], changelog_file="CHANGELOG.md", cwd=Path.cwd()
    )
    assert result is True


def test_changelog_is_updated_false() -> None:
    result = hooks.changelog_is_updated(
        ["src/foo.py"], changelog_file="CHANGELOG.md", cwd=Path.cwd()
    )
    assert result is False


# ---------------------------------------------------------------------------
# _detect_changelog_workflow / _resolve_changelog_strategy
# ---------------------------------------------------------------------------


def test_detect_changelog_workflow_file_not_found(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        hooks,
        "load_or_autodetect_config",
        lambda cwd: (_ for _ in ()).throw(FileNotFoundError("no config")),
    )
    result = hooks._detect_changelog_workflow(tmp_path)
    assert result == hooks.DEFAULT_CHANGELOG_WORKFLOW


def test_detect_changelog_workflow_missing_tool_rrt_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(hooks, "is_missing_tool_rrt_error", lambda exc: True)
    monkeypatch.setattr(
        hooks,
        "load_or_autodetect_config",
        lambda cwd: (_ for _ in ()).throw(ValueError("missing [tool.rrt]")),
    )
    result = hooks._detect_changelog_workflow(tmp_path)
    assert result == hooks.DEFAULT_CHANGELOG_WORKFLOW


def test_detect_changelog_workflow_unhandled_value_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(hooks, "is_missing_tool_rrt_error", lambda exc: False)
    monkeypatch.setattr(
        hooks,
        "load_or_autodetect_config",
        lambda cwd: (_ for _ in ()).throw(ValueError("bad config")),
    )
    with pytest.raises(RuntimeError, match="Failed to load changelog_workflow"):
        hooks._detect_changelog_workflow(tmp_path)


def test_resolve_changelog_strategy_explicit() -> None:
    result = hooks._resolve_changelog_strategy(Path.cwd(), "per-commit")
    assert result == "per-commit"


def test_resolve_changelog_strategy_auto_squash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hooks, "_detect_changelog_workflow", lambda cwd: "squash")
    assert hooks._resolve_changelog_strategy(Path.cwd(), "auto") == "release-only"


def test_resolve_changelog_strategy_auto_incremental(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hooks, "_detect_changelog_workflow", lambda cwd: "incremental")
    assert hooks._resolve_changelog_strategy(Path.cwd(), "auto") == "per-commit"


# ---------------------------------------------------------------------------
# emit_failure / run_branch_name_check / run_commit_subject_check
# ---------------------------------------------------------------------------


def test_emit_failure_returns_1() -> None:
    result = hooks.emit_failure("Hook failed.", ["detail one", "detail two"])
    assert result == 1


def test_run_branch_name_check_valid() -> None:
    assert hooks.run_branch_name_check("feat/add-parser", title="Branch check failed.") == 0


def test_run_branch_name_check_invalid() -> None:
    assert hooks.run_branch_name_check("bad_branch", title="Branch check failed.") == 1


def test_run_branch_name_check_with_extra_types() -> None:
    assert (
        hooks.run_branch_name_check(
            "snyk/fix-dep", title="Branch check failed.", extra_types=("snyk",)
        )
        == 0
    )


def test_run_commit_subject_check_valid() -> None:
    assert hooks.run_commit_subject_check("fix: repair config", title="Subject check failed.") == 0


def test_run_commit_subject_check_invalid() -> None:
    assert hooks.run_commit_subject_check("WIP stuff", title="Subject check failed.") == 1


# ---------------------------------------------------------------------------
# run_dirty_tree_check — failure paths
# ---------------------------------------------------------------------------


def test_run_dirty_tree_check_not_git_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hooks.git, "is_git_repository", lambda cwd: False)
    assert hooks.run_dirty_tree_check(Path.cwd(), title="Dirty tree check.") == 1


def test_run_dirty_tree_check_dirty_tree_with_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hooks.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(hooks.git, "working_tree_clean", lambda cwd: False)
    monkeypatch.setattr(hooks.git, "status_porcelain", lambda cwd: ["M  src/foo.py"])
    assert hooks.run_dirty_tree_check(Path.cwd(), title="Dirty tree check.") == 1


def test_run_dirty_tree_check_dirty_tree_status_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hooks.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(hooks.git, "working_tree_clean", lambda cwd: False)
    monkeypatch.setattr(
        hooks.git,
        "status_porcelain",
        lambda cwd: (_ for _ in ()).throw(RuntimeError("git status failed")),
    )
    assert hooks.run_dirty_tree_check(Path.cwd(), title="Dirty tree check.") == 1


def test_run_dirty_tree_check_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hooks.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(hooks.git, "working_tree_clean", lambda cwd: True)
    assert hooks.run_dirty_tree_check(Path.cwd(), title="Dirty tree check.") == 0


# ---------------------------------------------------------------------------
# run_pre_commit_changelog
# ---------------------------------------------------------------------------


def test_run_pre_commit_changelog_squash_workflow_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hooks, "_detect_changelog_workflow", lambda cwd: "squash")
    assert hooks.run_pre_commit_changelog(Path.cwd()) == 0


def test_run_pre_commit_changelog_workflow_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        hooks,
        "_detect_changelog_workflow",
        lambda cwd: (_ for _ in ()).throw(RuntimeError("bad config")),
    )
    assert hooks.run_pre_commit_changelog(Path.cwd()) == 1


def test_run_pre_commit_changelog_non_changelog_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hooks, "_detect_changelog_workflow", lambda cwd: "incremental")
    monkeypatch.setattr(hooks.git, "current_branch", lambda cwd: "chore/tidy-up")
    assert hooks.run_pre_commit_changelog(Path.cwd()) == 0


def test_run_pre_commit_changelog_staged_changelog_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hooks, "_detect_changelog_workflow", lambda cwd: "incremental")
    monkeypatch.setattr(hooks.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(hooks, "staged_files", lambda cwd: ["CHANGELOG.md", "src/foo.py"])
    assert hooks.run_pre_commit_changelog(Path.cwd()) == 0


def test_run_pre_commit_changelog_missing_staged_changelog(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hooks, "_detect_changelog_workflow", lambda cwd: "incremental")
    monkeypatch.setattr(hooks.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(hooks, "staged_files", lambda cwd: ["src/foo.py"])
    assert hooks.run_pre_commit_changelog(Path.cwd()) == 1


# ---------------------------------------------------------------------------
# run_commit_msg
# ---------------------------------------------------------------------------


def test_run_commit_msg_valid(tmp_path: Path) -> None:
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text("feat(cli): add hook\n", encoding="utf-8")
    assert hooks.run_commit_msg(msg) == 0


def test_run_commit_msg_invalid(tmp_path: Path) -> None:
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text("WIP stuff\n", encoding="utf-8")
    assert hooks.run_commit_msg(msg) == 1


# ---------------------------------------------------------------------------
# run_update_unreleased
# ---------------------------------------------------------------------------


def test_run_update_unreleased_squash_skips(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(hooks, "_detect_changelog_workflow", lambda cwd: "squash")
    assert hooks.run_update_unreleased(tmp_path, subject="feat: add parser") == 0


def test_run_update_unreleased_workflow_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        hooks,
        "_detect_changelog_workflow",
        lambda cwd: (_ for _ in ()).throw(RuntimeError("bad cfg")),
    )
    assert hooks.run_update_unreleased(tmp_path, subject="feat: add parser") == 1


def test_run_update_unreleased_non_changelog_subject(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(hooks, "_detect_changelog_workflow", lambda cwd: "incremental")
    assert hooks.run_update_unreleased(tmp_path, subject="chore: tidy up") == 0


def test_run_update_unreleased_meta_commit_skips(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(hooks, "_detect_changelog_workflow", lambda cwd: "incremental")
    assert hooks.run_update_unreleased(tmp_path, subject="fix: update changelog entries") == 0


def test_run_update_unreleased_missing_changelog(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(hooks, "_detect_changelog_workflow", lambda cwd: "incremental")
    result = hooks.run_update_unreleased(tmp_path, subject="feat: add parser")
    assert result == 1


def test_run_update_unreleased_writes_bullet(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(hooks, "_detect_changelog_workflow", lambda cwd: "incremental")
    monkeypatch.setattr(hooks.git, "run", lambda cmd, cwd, dry_run, label: None)
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## [Unreleased]\n\n", encoding="utf-8")
    result = hooks.run_update_unreleased(tmp_path, subject="feat: add parser")
    assert result == 0
    assert "add parser" in changelog.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# run_changelog_check
# ---------------------------------------------------------------------------


def test_run_changelog_check_non_changelog_subject() -> None:
    assert (
        hooks.run_changelog_check(
            "chore: tidy", cwd=Path.cwd(), changed_files=[], title="Changelog check."
        )
        == 0
    )


def test_run_changelog_check_bot_branch_skips() -> None:
    assert (
        hooks.run_changelog_check(
            "feat: add parser",
            cwd=Path.cwd(),
            changed_files=[],
            title="Changelog check.",
            branch="dependabot/npm/lodash",
        )
        == 0
    )


def test_run_changelog_check_strategy_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        hooks,
        "_resolve_changelog_strategy",
        lambda cwd, strategy: (_ for _ in ()).throw(RuntimeError("bad cfg")),
    )
    assert (
        hooks.run_changelog_check(
            "feat: add parser", cwd=Path.cwd(), changed_files=[], title="Changelog check."
        )
        == 1
    )


def test_run_changelog_check_release_only_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hooks, "_resolve_changelog_strategy", lambda cwd, s: "release-only")
    assert (
        hooks.run_changelog_check(
            "feat: add parser", cwd=Path.cwd(), changed_files=[], title="Changelog check."
        )
        == 0
    )


def test_run_changelog_check_per_commit_ok() -> None:
    assert (
        hooks.run_changelog_check(
            "feat: add parser",
            cwd=Path.cwd(),
            changed_files=["CHANGELOG.md"],
            title="Changelog check.",
            strategy="per-commit",
        )
        == 0
    )


def test_run_changelog_check_per_commit_missing() -> None:
    assert (
        hooks.run_changelog_check(
            "feat: add parser",
            cwd=Path.cwd(),
            changed_files=["src/foo.py"],
            title="Changelog check.",
            strategy="per-commit",
        )
        == 1
    )


def test_run_changelog_check_unreleased_ok(tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## [Unreleased]\n\n- feat: something\n", encoding="utf-8")
    assert (
        hooks.run_changelog_check(
            "feat: add parser",
            cwd=tmp_path,
            changed_files=[],
            title="Changelog check.",
            strategy="unreleased",
        )
        == 0
    )


def test_run_changelog_check_unreleased_empty(tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## [Unreleased]\n\n", encoding="utf-8")
    assert (
        hooks.run_changelog_check(
            "feat: add parser",
            cwd=tmp_path,
            changed_files=[],
            title="Changelog check.",
            strategy="unreleased",
        )
        == 1
    )


def test_run_changelog_check_unreleased_no_file(tmp_path: Path) -> None:
    assert (
        hooks.run_changelog_check(
            "feat: add parser",
            cwd=tmp_path,
            changed_files=[],
            title="Changelog check.",
            strategy="unreleased",
        )
        == 1
    )


# ---------------------------------------------------------------------------
# run_post_correct
# ---------------------------------------------------------------------------


def test_run_post_correct_missing_changelog(tmp_path: Path) -> None:
    assert hooks.run_post_correct(tmp_path) == 1


def test_run_post_correct_git_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n", encoding="utf-8")
    monkeypatch.setattr(
        hooks,
        "collect_squash_changelog_hunks",
        lambda cwd, ref, changelog_file: (_ for _ in ()).throw(RuntimeError("git error")),
    )
    assert hooks.run_post_correct(tmp_path) == 1


def test_run_post_correct_no_added_lines(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n", encoding="utf-8")
    monkeypatch.setattr(
        hooks,
        "collect_squash_changelog_hunks",
        lambda cwd, ref, changelog_file: ([], frozenset()),
    )
    assert hooks.run_post_correct(tmp_path) == 0


def test_run_post_correct_already_clean(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n- fix typo\n", encoding="utf-8")
    monkeypatch.setattr(
        hooks,
        "collect_squash_changelog_hunks",
        lambda cwd, ref, changelog_file: (["- fix typo"], frozenset({3})),
    )
    # dedup_changelog_entries returns same list → apply_dedup returns False
    assert hooks.run_post_correct(tmp_path) == 0


def test_run_post_correct_removes_duplicates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n- add Node 26\n- remove Node 26\n- fix typo\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        hooks,
        "collect_squash_changelog_hunks",
        lambda cwd, ref, changelog_file: (
            ["- add Node 26", "- remove Node 26", "- fix typo"],
            frozenset({3, 4, 5}),
        ),
    )
    assert hooks.run_post_correct(tmp_path) == 0


def test_run_post_correct_commit_flag(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n- add Node 26\n- remove Node 26\n- fix typo\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        hooks,
        "collect_squash_changelog_hunks",
        lambda cwd, ref, changelog_file: (
            ["- add Node 26", "- remove Node 26", "- fix typo"],
            frozenset({3, 4, 5}),
        ),
    )
    monkeypatch.setattr(hooks.git, "run", lambda cmd, cwd, dry_run, label: None)
    assert hooks.run_post_correct(tmp_path, commit=True) == 0


def test_run_post_correct_commit_git_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n- add Node 26\n- remove Node 26\n- fix typo\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        hooks,
        "collect_squash_changelog_hunks",
        lambda cwd, ref, changelog_file: (
            ["- add Node 26", "- remove Node 26", "- fix typo"],
            frozenset({3, 4, 5}),
        ),
    )
    monkeypatch.setattr(
        hooks.git,
        "run",
        lambda cmd, cwd, dry_run, label: (_ for _ in ()).throw(RuntimeError("git add failed")),
    )
    assert hooks.run_post_correct(tmp_path, commit=True) == 1


# ---------------------------------------------------------------------------
# main() — all subcommand dispatch branches
# ---------------------------------------------------------------------------


def test_main_pre_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hooks, "run_pre_commit", lambda cwd: 0)
    assert hooks.main(["pre-commit"]) == 0


def test_main_pre_commit_changelog(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hooks, "run_pre_commit_changelog", lambda cwd, changelog_file: 0)
    assert hooks.main(["pre-commit-changelog"]) == 0


def test_main_pre_commit_changelog_custom_file(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[str] = []
    monkeypatch.setattr(
        hooks,
        "run_pre_commit_changelog",
        lambda cwd, changelog_file: captured.append(changelog_file) or 0,
    )
    assert hooks.main(["pre-commit-changelog", "--changelog-file", "CHANGES.md"]) == 0
    assert captured == ["CHANGES.md"]


def test_main_commit_msg(tmp_path: Path) -> None:
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text("feat(cli): add parser\n", encoding="utf-8")
    assert hooks.main(["commit-msg", str(msg)]) == 0


def test_main_check_branch_name_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hooks, "load_extra_branch_types", lambda cwd: ())
    assert hooks.main(["check-branch-name", "--branch", "feat/add-parser"]) == 0


def test_main_check_branch_name_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hooks, "load_extra_branch_types", lambda cwd: ())
    assert hooks.main(["check-branch-name", "--branch", "bad_branch"]) == 1


def test_main_check_commit_subject_valid() -> None:
    assert hooks.main(["check-commit-subject", "--subject", "fix: repair config"]) == 0


def test_main_check_commit_subject_invalid() -> None:
    assert hooks.main(["check-commit-subject", "--subject", "WIP stuff"]) == 1


def test_main_check_dirty_tree(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hooks.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(hooks.git, "working_tree_clean", lambda cwd: True)
    assert hooks.main(["check-dirty-tree"]) == 0


def test_main_check_docs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hooks, "run_docs_check", lambda cwd: 0)
    assert hooks.main(["check-docs"]) == 0


def test_main_doctor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hooks, "cmd_doctor", lambda args: 0)
    assert hooks.main(["doctor"]) == 0


def test_main_release_check(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hooks, "cmd_release_check", lambda args: 0)
    assert hooks.main(["release-check"]) == 0


def test_main_check_eol(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hooks, "cmd_eol_check", lambda args: 0)
    assert hooks.main(["check-eol"]) == 0


def test_main_update_unreleased_with_subject(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(hooks, "run_update_unreleased", lambda cwd, subject, changelog_file: 0)
    assert hooks.main(["update-unreleased", "--subject", "feat: add parser"]) == 0


def test_main_update_unreleased_with_message_file(tmp_path: Path) -> None:
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text("chore: tidy up\n", encoding="utf-8")
    assert hooks.main(["update-unreleased", "--message-file", str(msg)]) == 0


def test_main_update_unreleased_missing_message_file(tmp_path: Path) -> None:
    missing = tmp_path / "NO_SUCH_FILE"
    assert hooks.main(["update-unreleased", "--message-file", str(missing)]) == 1


def test_main_update_unreleased_fallback_no_editmsg(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # No --subject and no .git/COMMIT_EDITMSG → subject=""
    monkeypatch.setattr(hooks, "run_update_unreleased", lambda cwd, subject, changelog_file: 0)
    monkeypatch.chdir(tmp_path)
    assert hooks.main(["update-unreleased"]) == 0


def test_main_changelog_post_correct(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hooks, "run_post_correct", lambda cwd, ref, changelog_file, commit: 0)
    assert hooks.main(["changelog", "post-correct"]) == 0


def test_main_changelog_post_correct_with_sha(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        hooks,
        "run_post_correct",
        lambda cwd, ref, changelog_file, commit: captured.update({"ref": ref}) or 0,
    )
    assert hooks.main(["changelog", "post-correct", "--squash-commit", "abc1234"]) == 0
    assert captured["ref"] == "abc1234"


def test_main_check_changelog_accepts_changed_file() -> None:
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


def test_main_check_changelog_missing_changelog() -> None:
    assert (
        hooks.main(
            [
                "check-changelog",
                "--subject",
                "feat(cli): add hook checks",
                "--changed-file",
                "src/foo.py",
                "--strategy",
                "per-commit",
            ]
        )
        == 1
    )


def test_main_check_changelog_strategy_release_only() -> None:
    assert (
        hooks.main(
            [
                "check-changelog",
                "--subject",
                "feat(cli): add hook checks",
                "--strategy",
                "release-only",
            ]
        )
        == 0
    )


def test_main_check_changelog_bot_branch() -> None:
    assert (
        hooks.main(
            [
                "check-changelog",
                "--subject",
                "feat(cli): add hook checks",
                "--branch",
                "dependabot/npm/lodash",
            ]
        )
        == 0
    )


# ---------------------------------------------------------------------------
# previously existing tests preserved
# ---------------------------------------------------------------------------


def test_entries_cancel_out_different_scopes() -> None:
    # Line 334: a_scope != b_scope → return False
    assert hooks._entries_cancel_out("CI: add X", "Deps: remove X") is False


def test_entries_cancel_out_no_verb_match() -> None:
    # Line 347: end of loop → return False when no verb pair matches
    assert hooks._entries_cancel_out("add X", "fix Y") is False


# ---------------------------------------------------------------------------
# collect_squash_changelog_hunks — parse diff output
# ---------------------------------------------------------------------------


def test_collect_squash_changelog_hunks_parses_diff(monkeypatch: pytest.MonkeyPatch) -> None:
    # Covers lines 295-319 (the diff-parsing loop body)
    fake_diff = (
        "diff --git a/CHANGELOG.md b/CHANGELOG.md\n"
        "index abc..def 100644\n"
        "--- a/CHANGELOG.md\n"
        "+++ b/CHANGELOG.md\n"
        "@@ -1,3 +1,4 @@\n"
        " # Changelog\n"
        "+- feat: add parser\n"
        " \n"
        "-old line\n"
    )
    monkeypatch.setattr(hooks.git, "capture_checked", lambda cmd, cwd: fake_diff)
    added, positions = hooks.collect_squash_changelog_hunks(Path.cwd())
    assert "- feat: add parser" in added
    assert 2 in positions  # line 2 in the new file (after @@  -1,3 +1,4 @@  = new line starts at 1)


# ---------------------------------------------------------------------------
# dedup_changelog_entries — inner continue (j already cancelled)
# ---------------------------------------------------------------------------


def test_dedup_changelog_entries_inner_continue() -> None:
    # Line 391: inner `if j in cancelled_indices: continue`
    # A(add X) cancels C(remove X); then B(fix bug) sees C already cancelled.
    lines = ["- add X", "- fix bug", "- remove X", "- update deps"]
    result = hooks.dedup_changelog_entries(lines)
    # add X and remove X should be removed; fix bug and update deps should remain
    assert "- add X" not in result
    assert "- remove X" not in result
    assert "- fix bug" in result
    assert "- update deps" in result


def test_dedup_changelog_entries_blank_line_collapse() -> None:
    # Line 410: `continue` inside consecutive-blank-line collapse after removing entries
    lines = ["- add X", "", "", "- remove X", "- keep this"]
    result = hooks.dedup_changelog_entries(lines)
    # After removing add X / remove X, consecutive blanks should be collapsed
    blank_count = result.count("")
    assert blank_count <= 1


# ---------------------------------------------------------------------------
# apply_dedup_to_changelog — unchanged content path
# ---------------------------------------------------------------------------


def test_apply_dedup_to_changelog_unchanged_when_not_in_hunk(tmp_path: Path) -> None:
    # Line 466: return False when new_content == content (lines restricted to hunk positions
    # that don't match any actual file lines)
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n- keep this\n", encoding="utf-8")
    # added_lines has items to remove, but added_line_positions restricts to position 999
    # which doesn't exist in the file → nothing removed → new_content == content
    changed = hooks.apply_dedup_to_changelog(
        changelog,
        added_lines=["- keep this"],
        deduped_lines=[],
        added_line_positions=frozenset({999}),
    )
    assert changed is False


def test_apply_dedup_to_changelog_blank_line_collapse(tmp_path: Path) -> None:
    # Line 460: consecutive blank lines in apply_dedup_to_changelog
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n- remove me\n\n\n- keep\n", encoding="utf-8")
    changed = hooks.apply_dedup_to_changelog(
        changelog,
        added_lines=["- remove me"],
        deduped_lines=[],
    )
    assert changed is True
    content = changelog.read_text(encoding="utf-8")
    # Consecutive blank lines collapsed
    assert "\n\n\n" not in content


# ---------------------------------------------------------------------------
# run_docs_check — real execution (covers import lines and config handling)
# ---------------------------------------------------------------------------


def test_run_docs_check_with_missing_rrt_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Covers lines 549-592 by executing the full function body.
    # Patch load_config to raise a MissingRrtConfigError-equivalent so we go
    # through the is_missing_tool_rrt_error branch → defaults.
    # extract_docs_from_dir(tmp_path, DocsConfig()) returns [] for an empty dir.
    # lock_is_current(non_existent_lock, []) returns (True, []) → return 0.
    from repo_release_tools.config import MissingRrtConfigError

    monkeypatch.setattr(
        "repo_release_tools.config.load_config",
        lambda cwd: (_ for _ in ()).throw(MissingRrtConfigError("no rrt config")),
    )
    result = hooks.run_docs_check(tmp_path)
    assert result == 0


def test_run_docs_check_with_entries(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Covers the entry processing loop inside run_docs_check (lines ~571-592).
    from repo_release_tools.config import MissingRrtConfigError

    monkeypatch.setattr(
        "repo_release_tools.config.load_config",
        lambda cwd: (_ for _ in ()).throw(MissingRrtConfigError("no rrt config")),
    )

    # Create a fake DocEntry to return from extract_docs_from_dir
    class _FakeEntry:
        source_file = "README.md"
        hash = "abc123"
        name = "intro"
        lang = "markdown"

    monkeypatch.setattr(
        "repo_release_tools.docs.extractor.extract_docs_from_dir",
        lambda cwd, cfg: [_FakeEntry()],
    )
    monkeypatch.setattr(
        "repo_release_tools.state.lock_is_current",
        lambda lock_path, sources: (True, []),
    )
    result = hooks.run_docs_check(tmp_path)
    assert result == 0


def test_run_docs_check_stale_lock(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Covers the emit_failure path at end of run_docs_check.
    from repo_release_tools.config import MissingRrtConfigError

    monkeypatch.setattr(
        "repo_release_tools.config.load_config",
        lambda cwd: (_ for _ in ()).throw(MissingRrtConfigError("no rrt config")),
    )
    monkeypatch.setattr(
        "repo_release_tools.state.lock_is_current",
        lambda lock_path, sources: (False, ["README.md: hash mismatch"]),
    )
    result = hooks.run_docs_check(tmp_path)
    assert result == 1


def test_run_docs_check_successful_config_load(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Lines 559-560: load_config succeeds → cfg.docs is None → DocsConfig() used.
    from unittest.mock import MagicMock

    mock_cfg = MagicMock()
    mock_cfg.docs = None
    monkeypatch.setattr("repo_release_tools.config.load_config", lambda cwd: mock_cfg)
    result = hooks.run_docs_check(tmp_path)
    assert result == 0


def test_run_docs_check_non_missing_tool_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Line 566: load_config raises non-missing-tool error → emit_failure.
    monkeypatch.setattr(
        "repo_release_tools.config.load_config",
        lambda cwd: (_ for _ in ()).throw(ValueError("bad TOML syntax")),
    )
    monkeypatch.setattr(hooks, "is_missing_tool_rrt_error", lambda exc: False)
    result = hooks.run_docs_check(tmp_path)
    assert result == 1


# ---------------------------------------------------------------------------
# main() update-unreleased — OSError and COMMIT_EDITMSG fallback paths
# ---------------------------------------------------------------------------


def test_main_update_unreleased_message_file_oserror(tmp_path: Path) -> None:
    # Lines 1049-1050: OSError reading message file
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_bytes(b"\xff\xfe bad utf-8")  # invalid UTF-8
    assert hooks.main(["update-unreleased", "--message-file", str(msg)]) == 1


def test_main_update_unreleased_commit_editmsg_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Line 1059: .git/COMMIT_EDITMSG exists → read subject from it
    monkeypatch.setattr(hooks, "run_update_unreleased", lambda cwd, subject, changelog_file: 0)
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    commit_editmsg = git_dir / "COMMIT_EDITMSG"
    commit_editmsg.write_text("chore: tidy up\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert hooks.main(["update-unreleased"]) == 0
    assert hooks._entries_cancel_out("add Node 26", "remove Node 26") is True
    assert hooks._entries_cancel_out("remove Node 26", "add Node 26") is True
    assert hooks._entries_cancel_out("CI: add Node 26", "CI: remove Node 26") is True


def test_dedup_changelog_entries_removes_duplicates_top() -> None:
    lines = [
        "### Maintenance",
        "- CI: fix typo in workflow",
        "- CI: fix typo in workflow",
    ]
    result = hooks.dedup_changelog_entries(lines)
    assert result.count("- CI: fix typo in workflow") == 1


def test_apply_dedup_to_changelog_removes_cancelled_entries_top(tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Maintenance\n- add Node 26\n- remove Node 26\n- fix typo\n",
        encoding="utf-8",
    )
    added_lines = ["### Maintenance", "- add Node 26", "- remove Node 26", "- fix typo"]
    deduped_lines = ["### Maintenance", "- fix typo"]

    changed = hooks.apply_dedup_to_changelog(changelog, added_lines, deduped_lines)

    assert changed is True
    content = changelog.read_text(encoding="utf-8")
    assert "- add Node 26" not in content
    assert "- remove Node 26" not in content
    assert "- fix typo" in content


def test_run_dirty_tree_check_accepts_clean_tree_top(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hooks.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(hooks.git, "working_tree_clean", lambda cwd: True)

    assert hooks.run_dirty_tree_check(Path.cwd(), title="Dirty tree validation failed.") == 0


def test_run_pre_commit_top_uses_current_branch_and_extra_types(
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
