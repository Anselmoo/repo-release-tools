from __future__ import annotations

import pytest

from repo_release_tools.config import (
    FolderPolicyConfig,
    FolderRule,
    FolderScaffoldFile,
    FolderTemplate,
)
from repo_release_tools.config import folders_config as fc
from repo_release_tools.config.model import _validate_relative_folder_path


def test_load_folders_config_rejects_non_table() -> None:
    with pytest.raises(ValueError, match="tool.rrt.folders must be a table"):
        fc._load_folders_config("oops")


def test_load_folder_templates_parses_scaffold_entries() -> None:
    templates = fc._load_folder_templates(
        [
            {
                "name": "x",
                "description": "desc",
                "strictness": "strict",
                "exact": True,
                "required_files": ["README.md"],
                "required_dirs": ["src"],
                "allowed_files": ["LICENSE"],
                "allowed_dirs": ["docs"],
                "allow_patterns": ["*.tmp"],
                "scaffold_dirs": ["src"],
                "scaffold_files": [{"path": "src/main.py", "content": "x", "executable": False}],
            },
        ],
    )

    assert len(templates) == 1
    template = templates[0]
    assert template.name == "x"
    assert template.exact is True
    assert template.scaffold_files[0].path == "src/main.py"


def test_load_folder_templates_rejects_invalid_shapes_and_strictness() -> None:
    with pytest.raises(ValueError, match="tool.rrt.folders.templates must be an array of tables"):
        fc._load_folder_templates("oops")

    with pytest.raises(ValueError, match=r"tool\.rrt\.folders\.templates\[0\] must be a table"):
        fc._load_folder_templates(["oops"])

    with pytest.raises(ValueError, match="strictness must be one of"):
        fc._load_folder_templates([{"name": "x", "strictness": "chaos"}])


def test_load_folder_rules_rejects_non_list_and_non_table() -> None:
    assert fc._load_folder_rules(None) == ()

    with pytest.raises(ValueError, match="tool.rrt.folders.rules must be an array of tables"):
        fc._load_folder_rules("oops")

    with pytest.raises(ValueError, match=r"tool\.rrt\.folders\.rules\[0\] must be a table"):
        fc._load_folder_rules(["oops"])


def test_load_scaffold_files_rejects_invalid_shapes() -> None:
    with pytest.raises(ValueError, match="must be a list of tables"):
        fc._load_scaffold_files("oops", label="x")

    with pytest.raises(ValueError, match=r"x\[0\] must be a table"):
        fc._load_scaffold_files(["oops"], label="x")


def test_string_tuple_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="must be a list of strings"):
        fc._string_tuple([1], label="required_files")

    with pytest.raises(ValueError, match="must not contain empty strings"):
        fc._string_tuple(["   "], label="required_files")


def test_required_and_optional_helpers_cover_error_paths() -> None:
    with pytest.raises(ValueError, match="must be a non-empty string"):
        fc._required_string("   ", label="name")

    assert fc._optional_string(None, default="d", label="description") == "d"

    with pytest.raises(ValueError, match="must be a string"):
        fc._optional_string(1, default="d", label="description")

    assert fc._optional_bool(None, default=True, label="exact") is True

    with pytest.raises(ValueError, match="must be a boolean"):
        fc._optional_bool("yes", default=False, label="exact")

    assert fc._optional_optional_bool(None, label="exact") is None

    with pytest.raises(ValueError, match="must be a boolean"):
        fc._optional_optional_bool("yes", label="exact")

    assert fc._optional_mode(None, label="mode") is None

    assert fc._optional_mode("strict", label="mode") == "strict"

    with pytest.raises(ValueError, match="must be one of"):
        fc._optional_mode("chaos", label="mode")


def test_folder_model_validation_guards() -> None:
    with pytest.raises(ValueError, match="must be a non-empty string"):
        _validate_relative_folder_path("", label="folder path")

    with pytest.raises(ValueError, match="must be a non-empty string"):
        FolderTemplate(name=" ").validate()

    with pytest.raises(ValueError, match="strictness must be one of"):
        FolderTemplate(name="x", strictness="chaos").validate()

    with pytest.raises(ValueError, match="must be a relative path"):
        FolderTemplate(name="x", required_files=("/abs",)).validate()

    FolderTemplate(
        name="valid",
        scaffold_files=(FolderScaffoldFile(path="scripts/run.sh", content="#!/bin/sh\n"),),
    ).validate()

    with pytest.raises(ValueError, match="must be a non-empty string"):
        FolderRule(name=" ").validate()

    with pytest.raises(ValueError, match="selector must be a non-empty string"):
        FolderRule(name="x", selector=" ").validate()

    with pytest.raises(ValueError, match="mode must be one of"):
        FolderRule(name="x", mode="chaos").validate()

    with pytest.raises(ValueError, match="must not escape the repository root"):
        FolderRule(name="x", required_files=("../escape",)).validate()

    FolderRule(
        name="valid",
        scaffold_files=(FolderScaffoldFile(path="scripts/run.sh", content="#!/bin/sh\n"),),
    ).validate()

    with pytest.raises(ValueError, match="tool.rrt.folders.mode must be one of"):
        FolderPolicyConfig(mode="chaos").validate()

    duplicate_templates = (
        FolderTemplate(name="dup"),
        FolderTemplate(name="dup"),
    )
    with pytest.raises(ValueError, match="Duplicate folder template name"):
        FolderPolicyConfig(mode="strict", templates=duplicate_templates).validate()

    duplicate_rules = (
        FolderRule(name="dup"),
        FolderRule(name="dup"),
    )
    with pytest.raises(ValueError, match="Duplicate folder rule name"):
        FolderPolicyConfig(mode="strict", rules=duplicate_rules).validate()


def test_folder_scaffold_file_validate_requires_string_content() -> None:
    invalid = FolderScaffoldFile(path="x.txt", content="")
    object.__setattr__(invalid, "content", 123)
    with pytest.raises(ValueError, match="content must be a string"):
        invalid.validate()
