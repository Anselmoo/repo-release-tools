"""Folder supervision and scaffold orchestration."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path

from repo_release_tools.config import (
    FolderPolicyConfig,
    FolderRule,
    FolderScaffoldFile,
    FolderTemplate,
)
from repo_release_tools.folders.data import (
    FolderCheckReport,
    FolderScaffoldAction,
    FolderScaffoldReport,
    FolderTargetReport,
    FolderViolation,
)
from repo_release_tools.folders.templates import BUILTIN_FOLDER_TEMPLATES


@dataclass(frozen=True)
class _EffectiveRule:
    """Resolved runtime rule after merging templates and rule overrides."""

    name: str
    selector: str
    mode: str
    exact: bool
    required_files: tuple[str, ...]
    required_dirs: tuple[str, ...]
    allowed_files: tuple[str, ...]
    allowed_dirs: tuple[str, ...]
    allow_patterns: tuple[str, ...]
    scaffold_dirs: tuple[str, ...]
    scaffold_files: tuple[FolderScaffoldFile, ...]


def resolve_template_catalog(policy: FolderPolicyConfig | None = None) -> dict[str, FolderTemplate]:
    """Return built-in templates merged with any custom templates."""
    catalog = dict(BUILTIN_FOLDER_TEMPLATES)
    if policy is None:
        return catalog
    for template in policy.templates:
        catalog[template.name] = template
    return catalog


def check_folders(
    *,
    root: Path,
    policy: FolderPolicyConfig | None,
    template_names: tuple[str, ...] = (),
    mode_override: str | None = None,
) -> FolderCheckReport:
    """Check folder structure under *root*."""
    rules = _resolve_rules(
        policy=policy, template_names=template_names, mode_override=mode_override
    )
    target_reports: list[FolderTargetReport] = []

    for rule in rules:
        matched_paths = _match_rule_targets(root=root, selector=rule.selector)
        if not matched_paths:
            target_reports.append(
                FolderTargetReport(
                    rule_name=rule.name,
                    selector=rule.selector,
                    base_path=_relative_text(root, root),
                    violations=(
                        FolderViolation(
                            code="selector-no-match",
                            path=rule.selector,
                            message=f"Selector {rule.selector!r} matched no directories.",
                            severity=_severity_for_mode(rule.mode),
                        ),
                    ),
                )
            )
            continue

        for base_path in matched_paths:
            target_reports.append(_check_one_target(base_path=base_path, root=root, rule=rule))

    return FolderCheckReport(
        mode=mode_override or (policy.mode if policy else "strict"), targets=tuple(target_reports)
    )


def scaffold_folders(
    *,
    root: Path,
    policy: FolderPolicyConfig | None,
    template_names: tuple[str, ...] = (),
    mode_override: str | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> FolderScaffoldReport:
    """Scaffold directories and files under *root*."""
    rules = _resolve_rules(
        policy=policy, template_names=template_names, mode_override=mode_override
    )
    actions: list[FolderScaffoldAction] = []

    for rule in rules:
        for base_path in _match_rule_targets(
            root=root,
            selector=rule.selector,
            include_root_if_missing=True,
        ):
            actions.extend(
                _scaffold_one_target(
                    base_path=base_path,
                    root=root,
                    rule=rule,
                    force=force,
                    dry_run=dry_run,
                )
            )

    return FolderScaffoldReport(actions=tuple(actions))


def _resolve_rules(
    *,
    policy: FolderPolicyConfig | None,
    template_names: tuple[str, ...],
    mode_override: str | None,
) -> list[_EffectiveRule]:
    """Resolve runtime rules from config and ad-hoc template selection."""
    catalog = resolve_template_catalog(policy)
    rules: list[_EffectiveRule] = []

    if template_names:
        adhoc_rule = FolderRule(name="adhoc", selector=".", templates=template_names)
        rules.append(
            _merge_rule(adhoc_rule, policy=policy, catalog=catalog, mode_override=mode_override)
        )

    if policy is not None:
        for rule in policy.rules:
            rules.append(
                _merge_rule(rule, policy=policy, catalog=catalog, mode_override=mode_override)
            )

    return rules


def _merge_rule(
    rule: FolderRule,
    *,
    policy: FolderPolicyConfig | None,
    catalog: dict[str, FolderTemplate],
    mode_override: str | None,
) -> _EffectiveRule:
    """Merge templates and direct rule fields into one effective rule."""
    resolved_templates: list[FolderTemplate] = []
    for template_name in rule.templates:
        template = catalog.get(template_name)
        if template is None:
            raise ValueError(f"Unknown folder template {template_name!r}")
        resolved_templates.append(template)

    effective_mode = mode_override or rule.mode or (policy.mode if policy else "strict")
    effective_exact = bool(
        rule.exact
        if rule.exact is not None
        else any(
            template.exact and template.strictness == "strict" for template in resolved_templates
        )
    )

    return _EffectiveRule(
        name=rule.name,
        selector=rule.selector,
        mode=effective_mode,
        exact=effective_exact,
        required_files=_merge_string_fields(
            *(template.required_files for template in resolved_templates), rule.required_files
        ),
        required_dirs=_merge_string_fields(
            *(template.required_dirs for template in resolved_templates), rule.required_dirs
        ),
        allowed_files=_merge_string_fields(
            *(template.allowed_files for template in resolved_templates), rule.allowed_files
        ),
        allowed_dirs=_merge_string_fields(
            *(template.allowed_dirs for template in resolved_templates), rule.allowed_dirs
        ),
        allow_patterns=_merge_string_fields(
            *(template.allow_patterns for template in resolved_templates), rule.allow_patterns
        ),
        scaffold_dirs=_merge_string_fields(
            *(template.scaffold_dirs for template in resolved_templates), rule.scaffold_dirs
        ),
        scaffold_files=_merge_scaffold_files(
            *(template.scaffold_files for template in resolved_templates),
            rule.scaffold_files,
        ),
    )


def _merge_string_fields(*groups: tuple[str, ...]) -> tuple[str, ...]:
    """Merge ordered string tuples without duplicates."""
    values: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for entry in group:
            if entry not in seen:
                seen.add(entry)
                values.append(entry)
    return tuple(values)


def _merge_scaffold_files(
    *groups: tuple[FolderScaffoldFile, ...],
) -> tuple[FolderScaffoldFile, ...]:
    """Merge scaffold files by path, later entries winning."""
    merged: dict[str, FolderScaffoldFile] = {}
    for group in groups:
        for scaffold_file in group:
            merged[scaffold_file.path] = scaffold_file
    return tuple(merged[path] for path in sorted(merged))


def _match_rule_targets(
    *,
    root: Path,
    selector: str,
    include_root_if_missing: bool = False,
) -> list[Path]:
    """Return directories matched by one selector."""
    if selector in {".", "./"}:
        return [root]

    matches = sorted(path for path in root.glob(selector) if path.is_dir())
    if matches or not include_root_if_missing:
        return matches

    parent = root / selector
    return [parent]


def _check_one_target(*, base_path: Path, root: Path, rule: _EffectiveRule) -> FolderTargetReport:
    """Check one matched directory target."""
    violations: list[FolderViolation] = []

    for required_dir in rule.required_dirs:
        path = base_path / required_dir
        if not path.is_dir():
            violations.append(
                FolderViolation(
                    code="missing-dir",
                    path=_relative_text(path, root),
                    message=f"Missing required directory {required_dir!r}.",
                    severity=_severity_for_mode(rule.mode),
                )
            )

    for required_file in rule.required_files:
        path = base_path / required_file
        if not path.is_file():
            violations.append(
                FolderViolation(
                    code="missing-file",
                    path=_relative_text(path, root),
                    message=f"Missing required file {required_file!r}.",
                    severity=_severity_for_mode(rule.mode),
                )
            )

    if rule.exact and base_path.exists() and base_path.is_dir():
        allowed_names = _allowed_top_level_names(rule)
        for child in sorted(base_path.iterdir(), key=lambda item: item.name.lower()):
            child_name = child.name
            if child_name in allowed_names:
                continue
            if any(fnmatch.fnmatch(child_name, pattern) for pattern in rule.allow_patterns):
                continue
            violations.append(
                FolderViolation(
                    code="unexpected-entry",
                    path=_relative_text(child, root),
                    message=f"Unexpected entry {child_name!r} under exact rule {rule.name!r}.",
                    severity=_severity_for_mode(rule.mode),
                )
            )

    return FolderTargetReport(
        rule_name=rule.name,
        selector=rule.selector,
        base_path=_relative_text(base_path, root),
        violations=tuple(violations),
    )


def _scaffold_one_target(
    *,
    base_path: Path,
    root: Path,
    rule: _EffectiveRule,
    force: bool,
    dry_run: bool,
) -> list[FolderScaffoldAction]:
    """Apply one scaffold rule to one base path."""
    actions: list[FolderScaffoldAction] = []

    for directory in _merge_string_fields(rule.required_dirs, rule.scaffold_dirs):
        directory_path = base_path / directory
        if not dry_run:
            directory_path.mkdir(parents=True, exist_ok=True)
        actions.append(
            FolderScaffoldAction(kind="mkdir", path=_relative_text(directory_path, root))
        )

    scaffold_files = {scaffold.path: scaffold for scaffold in rule.scaffold_files}
    for required_file in rule.required_files:
        scaffold_files.setdefault(required_file, FolderScaffoldFile(path=required_file, content=""))

    for relative_path, scaffold in sorted(scaffold_files.items()):
        file_path = base_path / relative_path
        existed_before = file_path.exists()
        if file_path.exists() and not force:
            actions.append(
                FolderScaffoldAction(
                    kind="skip",
                    path=_relative_text(file_path, root),
                    detail="exists",
                )
            )
            continue
        if not dry_run:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(scaffold.content, encoding="utf-8")
        actions.append(
            FolderScaffoldAction(
                kind="write",
                path=_relative_text(file_path, root),
                detail="overwritten" if existed_before and force else "created",
            )
        )

    return actions


def _allowed_top_level_names(rule: _EffectiveRule) -> set[str]:
    """Return allowed immediate child names for exact-mode enforcement."""
    names: set[str] = set()
    for group in (
        rule.required_files,
        rule.required_dirs,
        rule.allowed_files,
        rule.allowed_dirs,
        rule.scaffold_dirs,
        tuple(scaffold.path for scaffold in rule.scaffold_files),
    ):
        for entry in group:
            top = entry.split("/", 1)[0]
            if top:
                names.add(top)
    return names


def _severity_for_mode(mode: str) -> str:
    """Map rule mode to violation severity."""
    return "warning" if mode == "warn" else "error"


def _relative_text(path: Path, root: Path) -> str:
    """Return a stable relative path string."""
    try:
        return path.relative_to(root).as_posix() or "."
    except ValueError:
        return str(path)
