from __future__ import annotations

from pathlib import Path

from repo_release_tools.config import (
    FolderContentCheck,
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
    content_checks: tuple[FolderContentCheck, ...] = (),
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
        content_checks=content_checks,
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


def test_check_one_target_emits_content_mismatch(tmp_path: Path) -> None:
    base = tmp_path / "project"
    base.mkdir()
    (base / "Cargo.toml").write_text('[package]\nname = "x"\n', encoding="utf-8")
    check = FolderContentCheck(path="Cargo.toml", must_match=r"workspace\s*=\s*true")
    rule = _rule(selector="project", content_checks=(check,))

    report = core._check_one_target(base_path=base, root=tmp_path, rule=rule)

    assert report.ok is False
    violation = report.violations[0]
    assert violation.code == "content-mismatch"
    assert violation.path == "project/Cargo.toml"
    assert "does not match required pattern" in violation.message


def test_check_one_target_emits_content_forbidden(tmp_path: Path) -> None:
    base = tmp_path / "project"
    base.mkdir()
    (base / "lib.rs").write_text("pub mod internal;\n", encoding="utf-8")
    check = FolderContentCheck(
        path="lib.rs",
        must_not_match=r"^pub mod ",
        message="keep modules private",
    )
    rule = _rule(selector="project", content_checks=(check,))

    report = core._check_one_target(base_path=base, root=tmp_path, rule=rule)

    assert report.ok is False
    violation = report.violations[0]
    assert violation.code == "content-forbidden"
    assert violation.message == "keep modules private"


def test_check_one_target_skips_content_check_for_missing_file(tmp_path: Path) -> None:
    base = tmp_path / "project"
    base.mkdir()
    check = FolderContentCheck(path="Cargo.toml", must_match="workspace")
    rule = _rule(selector="project", content_checks=(check,))

    report = core._check_one_target(base_path=base, root=tmp_path, rule=rule)

    # No required_files configured, so the only possible violation is
    # missing-file (not raised, since Cargo.toml isn't required) or a
    # content violation (also not raised, since content checks skip
    # missing paths entirely).
    assert report.ok is True


def test_check_one_target_passes_content_check_when_satisfied(tmp_path: Path) -> None:
    base = tmp_path / "project"
    base.mkdir()
    (base / "Cargo.toml").write_text("[lints]\nworkspace = true\n", encoding="utf-8")
    check = FolderContentCheck(path="Cargo.toml", must_match=r"workspace\s*=\s*true")
    rule = _rule(selector="project", content_checks=(check,))

    report = core._check_one_target(base_path=base, root=tmp_path, rule=rule)

    assert report.ok is True


def test_merge_rule_concatenates_template_and_rule_content_checks() -> None:
    template_check = FolderContentCheck(path="a.txt", must_match="a")
    rule_check = FolderContentCheck(path="b.txt", must_match="b")
    template = FolderTemplate(name="t", content=(template_check,))
    rule = FolderRule(name="r", templates=("t",), content=(rule_check,))

    effective = core._merge_rule(rule, policy=None, catalog={"t": template}, mode_override=None)

    assert effective.content_checks == (template_check, rule_check)


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
