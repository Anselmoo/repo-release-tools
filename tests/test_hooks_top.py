from __future__ import annotations

from pathlib import Path

import pytest

import repo_release_tools.hooks as hooks


def test_validate_branch_name_accepts_feature_branch_top() -> None:
    assert hooks.validate_branch_name("feat/add-hook-checks") is None


def test_validate_commit_subject_accepts_conventional_commit_top() -> None:
    assert hooks.validate_commit_subject("feat(cli): add hook checks") is None


def test_entries_cancel_out_top() -> None:
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
