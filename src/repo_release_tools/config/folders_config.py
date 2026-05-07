"""Folder config parsing helpers for rrt."""

from __future__ import annotations

from typing import cast

from .model import (
    VALID_FOLDER_MODES,
    VALID_TEMPLATE_STRICTNESS,
    FolderPolicyConfig,
    FolderRule,
    FolderScaffoldFile,
    FolderTemplate,
)


def _load_folders_config(raw: object) -> FolderPolicyConfig | None:
    """Parse an optional ``[tool.rrt.folders]`` table into a policy config."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("tool.rrt.folders must be a table")

    d: dict[str, object] = cast(dict[str, object], raw)
    raw_mode = d.get("mode")
    mode = "strict" if raw_mode is None else raw_mode
    if not isinstance(mode, str) or mode not in VALID_FOLDER_MODES:
        allowed = ", ".join(sorted(VALID_FOLDER_MODES))
        raise ValueError(f"tool.rrt.folders.mode must be one of {allowed}")

    config = FolderPolicyConfig(
        mode=mode,
        templates=_load_folder_templates(d.get("templates")),
        rules=_load_folder_rules(d.get("rules")),
    )
    config.validate()
    return config


def _load_folder_templates(raw: object) -> tuple[FolderTemplate, ...]:
    """Parse custom folder templates."""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError("tool.rrt.folders.templates must be an array of tables")

    templates: list[FolderTemplate] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"tool.rrt.folders.templates[{index}] must be a table")
        item = cast(dict[str, object], entry)
        name = _required_string(item.get("name"), label=f"templates[{index}].name")
        description = _optional_string(item.get("description"), default="", label="description")
        strictness = _optional_string(
            item.get("strictness"),
            default="strict",
            label=f"templates[{index}].strictness",
        )
        if strictness not in VALID_TEMPLATE_STRICTNESS:
            allowed = ", ".join(sorted(VALID_TEMPLATE_STRICTNESS))
            raise ValueError(
                f"tool.rrt.folders.templates[{index}].strictness must be one of {allowed}"
            )

        templates.append(
            FolderTemplate(
                name=name,
                description=description,
                strictness=strictness,
                exact=_optional_bool(item.get("exact"), default=False, label="exact"),
                required_files=_string_tuple(item.get("required_files"), label="required_files"),
                required_dirs=_string_tuple(item.get("required_dirs"), label="required_dirs"),
                allowed_files=_string_tuple(item.get("allowed_files"), label="allowed_files"),
                allowed_dirs=_string_tuple(item.get("allowed_dirs"), label="allowed_dirs"),
                allow_patterns=_string_tuple(item.get("allow_patterns"), label="allow_patterns"),
                scaffold_dirs=_string_tuple(item.get("scaffold_dirs"), label="scaffold_dirs"),
                scaffold_files=_load_scaffold_files(
                    item.get("scaffold_files"),
                    label=f"tool.rrt.folders.templates[{index}].scaffold_files",
                ),
            )
        )
    return tuple(templates)


def _load_folder_rules(raw: object) -> tuple[FolderRule, ...]:
    """Parse folder rules."""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError("tool.rrt.folders.rules must be an array of tables")

    rules: list[FolderRule] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"tool.rrt.folders.rules[{index}] must be a table")
        item = cast(dict[str, object], entry)
        rules.append(
            FolderRule(
                name=_required_string(item.get("name"), label=f"rules[{index}].name"),
                selector=_optional_string(
                    item.get("selector"),
                    default=".",
                    label=f"rules[{index}].selector",
                ),
                mode=_optional_mode(item.get("mode"), label=f"rules[{index}].mode"),
                templates=_string_tuple(item.get("templates"), label="templates"),
                exact=_optional_optional_bool(item.get("exact"), label="exact"),
                required_files=_string_tuple(item.get("required_files"), label="required_files"),
                required_dirs=_string_tuple(item.get("required_dirs"), label="required_dirs"),
                allowed_files=_string_tuple(item.get("allowed_files"), label="allowed_files"),
                allowed_dirs=_string_tuple(item.get("allowed_dirs"), label="allowed_dirs"),
                allow_patterns=_string_tuple(item.get("allow_patterns"), label="allow_patterns"),
                scaffold_dirs=_string_tuple(item.get("scaffold_dirs"), label="scaffold_dirs"),
                scaffold_files=_load_scaffold_files(
                    item.get("scaffold_files"),
                    label=f"tool.rrt.folders.rules[{index}].scaffold_files",
                ),
            )
        )
    return tuple(rules)


def _load_scaffold_files(raw: object, *, label: str) -> tuple[FolderScaffoldFile, ...]:
    """Parse scaffold file entries."""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError(f"{label} must be a list of tables")

    scaffold_files: list[FolderScaffoldFile] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"{label}[{index}] must be a table")
        item = cast(dict[str, object], entry)
        scaffold_files.append(
            FolderScaffoldFile(
                path=_required_string(item.get("path"), label=f"{label}[{index}].path"),
                content=_optional_string(item.get("content"), default="", label="content"),
                executable=_optional_bool(
                    item.get("executable"), default=False, label="executable"
                ),
            )
        )
    return tuple(scaffold_files)


def _string_tuple(raw: object, *, label: str) -> tuple[str, ...]:
    """Parse a list of strings into a normalized tuple."""
    if raw is None:
        return ()
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise ValueError(f"tool.rrt.folders.{label} must be a list of strings")
    seen: set[str] = set()
    values: list[str] = []
    for item in cast(list[str], raw):
        stripped = item.strip()
        if not stripped:
            raise ValueError(f"tool.rrt.folders.{label} must not contain empty strings")
        if stripped not in seen:
            seen.add(stripped)
            values.append(stripped)
    return tuple(values)


def _required_string(raw: object, *, label: str) -> str:
    """Return a required non-empty string."""
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"tool.rrt.folders.{label} must be a non-empty string")
    return raw.strip()


def _optional_string(raw: object, *, default: str, label: str) -> str:
    """Return an optional string with a default."""
    if raw is None:
        return default
    if not isinstance(raw, str):
        raise ValueError(f"tool.rrt.folders.{label} must be a string")
    return raw.strip() or default


def _optional_bool(raw: object, *, default: bool, label: str) -> bool:
    """Return an optional boolean with a default."""
    if raw is None:
        return default
    if not isinstance(raw, bool):
        raise ValueError(f"tool.rrt.folders.{label} must be a boolean")
    return raw


def _optional_optional_bool(raw: object, *, label: str) -> bool | None:
    """Return an optional nullable boolean."""
    if raw is None:
        return None
    if not isinstance(raw, bool):
        raise ValueError(f"tool.rrt.folders.{label} must be a boolean")
    return raw


def _optional_mode(raw: object, *, label: str) -> str | None:
    """Return an optional folder mode."""
    if raw is None:
        return None
    if not isinstance(raw, str) or raw not in VALID_FOLDER_MODES:
        allowed = ", ".join(sorted(VALID_FOLDER_MODES))
        raise ValueError(f"tool.rrt.folders.{label} must be one of {allowed}")
    return raw
