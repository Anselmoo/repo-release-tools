from __future__ import annotations

from pathlib import Path

from repo_release_tools.config import (
    FolderPolicyConfig,
    FolderRule,
    FolderScaffoldFile,
    FolderTemplate,
)
from repo_release_tools.folders import core
from repo_release_tools.folders.data import FolderScaffoldAction, FolderScaffoldReport
from repo_release_tools.folders.templates import resolve_builtin_template


def _rule(
    *,
    name: str = "rule",
    selector: str = ".",
    mode: str = "strict",
    exact: bool = False,
    required_files: tuple[str, ...] = (),
    required_dirs: tuple[str, ...] = (),
    allowed_files: tuple[str, ...] = (),
    allowed_dirs: tuple[str, ...] = (),
    allow_patterns: tuple[str, ...] = (),
    scaffold_dirs: tuple[str, ...] = (),
    scaffold_files: tuple[FolderScaffoldFile, ...] = (),
) -> core._EffectiveRule:
    return core._EffectiveRule(
        name=name,
        selector=selector,
        mode=mode,
        exact=exact,
        required_files=required_files,
        required_dirs=required_dirs,
        allowed_files=allowed_files,
        allowed_dirs=allowed_dirs,
        allow_patterns=allow_patterns,
        scaffold_dirs=scaffold_dirs,
        scaffold_files=scaffold_files,
    )


def test_resolve_template_catalog_allows_custom_override() -> None:
    custom = FolderTemplate(name="python-package", description="custom")
    policy = FolderPolicyConfig(mode="strict", templates=(custom,))

    catalog = core.resolve_template_catalog(policy)

    assert catalog["python-package"].description == "custom"


def test_check_folders_adds_selector_no_match_violation(tmp_path: Path) -> None:
    policy = FolderPolicyConfig(
        mode="strict",
        rules=(FolderRule(name="no-match", selector="missing/*"),),
    )

    report = core.check_folders(root=tmp_path, policy=policy)

    assert report.violation_count == 1
    violation = report.targets[0].violations[0]
    assert violation.code == "selector-no-match"
    assert violation.path == "missing/*"


def test_merge_rule_raises_on_unknown_template() -> None:
    rule = FolderRule(name="x", templates=("not-real",))

    try:
        core._merge_rule(rule, policy=None, catalog={}, mode_override=None)
    except ValueError as exc:
        assert "Unknown folder template" in str(exc)
    else:
        raise AssertionError("Expected ValueError for unknown template")


def test_match_rule_targets_returns_parent_when_missing_and_requested(tmp_path: Path) -> None:
    targets = core._match_rule_targets(
        root=tmp_path,
        selector="nested/dir",
        include_root_if_missing=True,
    )

    assert targets == [tmp_path / "nested/dir"]


def test_check_one_target_allows_entries_matching_patterns(tmp_path: Path) -> None:
    base = tmp_path / "project"
    base.mkdir()
    (base / "notes.log").write_text("ok\n", encoding="utf-8")
    rule = _rule(selector="project", exact=True, allow_patterns=("*.log",))

    report = core._check_one_target(base_path=base, root=tmp_path, rule=rule)

    assert report.ok is True


def test_scaffold_one_target_skips_existing_without_force(tmp_path: Path) -> None:
    base = tmp_path / "project"
    base.mkdir()
    existing = base / "README.md"
    existing.write_text("already\n", encoding="utf-8")
    rule = _rule(required_files=("README.md",))

    actions = core._scaffold_one_target(
        base_path=base,
        root=tmp_path,
        rule=rule,
        force=False,
        dry_run=False,
    )

    assert any(action.kind == "skip" and action.detail == "exists" for action in actions)


def test_relative_text_returns_absolute_string_for_outside_path(tmp_path: Path) -> None:
    outside = Path("/") / "tmp" / "outside-file.txt"

    assert core._relative_text(outside, tmp_path) == str(outside)


def test_folder_scaffold_to_dict_helpers_and_template_lookup() -> None:
    action = FolderScaffoldAction(kind="write", path="README.md", detail="created")
    report = FolderScaffoldReport(actions=(action,))

    payload = report.to_dict()

    assert payload == {"actions": [{"kind": "write", "path": "README.md", "detail": "created"}]}
    assert resolve_builtin_template("python-package") is not None
    assert resolve_builtin_template("does-not-exist") is None
