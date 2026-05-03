from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from repo_release_tools.config import (
    DEFAULT_CHANGELOG,
    DEFAULT_CHANGELOG_WORKFLOW,
    DocsConfig,
    EolConfig,
    EolOverride,
    MissingRrtConfigError,  # noqa: F401 — tested indirectly via match patterns
    RrtConfig,
    VersionGroup,
    VersionTarget,
    _autodetect_version_targets,
    _describe_version_target,
    _find_python_version_files,
    _json_string_field_exists,
    _recommended_lock_settings,
    _target_ecosystem,
    _toml_string_field_exists,
    auto_detect_config,
    autodetect_config,
    find_changelog_file,
    find_config_file,
    find_explicit_config_file,
    format_autodetected_config_notice,
    load_config,
    load_config_from_path,
    load_extra_branch_types,
    load_or_autodetect_config,
    recommend_init_config,
    recommend_init_config_for_go,
    recommend_init_section_for_cargo,
    recommend_init_section_for_node,
    recommend_init_section_for_pyproject,
)

_RRT_CONFIG = """\
[tool.rrt]
release_branch = "release/v{version}"

[[tool.rrt.version_targets]]
path = "package.json"
kind = "package_json"
"""


def test_load_config_falls_back_to_rrt_toml(tmp_path: Path) -> None:
    (tmp_path / ".rrt.toml").write_text(_RRT_CONFIG, encoding="utf-8")

    config = load_config(tmp_path)

    assert config.config_file == tmp_path / ".rrt.toml"
    assert config.lock_command == []
    assert config.generated_files == []


def test_load_config_prefers_pyproject_toml(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(_RRT_CONFIG, encoding="utf-8")
    (tmp_path / ".rrt.toml").write_text(
        _RRT_CONFIG.replace("release/v{version}", "ignored"), encoding="utf-8"
    )

    config = load_config(tmp_path)

    assert config.config_file == tmp_path / "pyproject.toml"
    assert config.release_branch == "release/v{version}"
    assert config.generated_files == [tmp_path / "uv.lock"]


def test_load_config_supports_dot_config_path(tmp_path: Path) -> None:
    config_dir = tmp_path / ".config"
    config_dir.mkdir()
    (config_dir / "rrt.toml").write_text(_RRT_CONFIG, encoding="utf-8")

    config = load_config(tmp_path)

    assert config.config_file == config_dir / "rrt.toml"


def test_autodetected_notice_mentions_init_command(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "example"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )

    config = autodetect_config(tmp_path)

    assert config is not None
    notice = format_autodetected_config_notice(config)
    assert "rrt init" in notice


def test_load_config_skips_existing_file_without_tool_rrt(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'example'\n", encoding="utf-8")
    (tmp_path / ".rrt.toml").write_text(_RRT_CONFIG, encoding="utf-8")

    config = load_config(tmp_path)

    assert config.config_file == tmp_path / ".rrt.toml"


def test_load_config_raises_after_all_candidates_lack_tool_rrt(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'example'\n", encoding="utf-8")
    (tmp_path / ".rrt.toml").write_text("[tool.other]\nvalue = 1\n", encoding="utf-8")

    config_dir = tmp_path / ".config"
    config_dir.mkdir()
    (config_dir / "rrt.toml").write_text("[tool.something]\nvalue = 2\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=r"Missing rrt configuration in supported config files: "
        r"pyproject\.toml, \.rrt\.toml, \.config/rrt\.toml",
    ):
        load_config(tmp_path)


def test_find_config_file_reports_supported_locations(tmp_path: Path) -> None:
    with pytest.raises(
        FileNotFoundError,
        match="pyproject.toml, package.json, Cargo.toml, .rrt.toml, .config/rrt.toml",
    ):
        find_config_file(tmp_path)


def test_find_explicit_config_file_returns_none_when_candidates_lack_tool_rrt(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'example'\n", encoding="utf-8")
    (tmp_path / ".rrt.toml").write_text("[tool.other]\nvalue = 1\n", encoding="utf-8")
    config_dir = tmp_path / ".config"
    config_dir.mkdir()
    (config_dir / "rrt.toml").write_text("[tool.something]\nvalue = 2\n", encoding="utf-8")

    assert find_explicit_config_file(tmp_path) is None


@pytest.mark.parametrize(
    ("target", "message"),
    [
        (
            VersionTarget(
                path=Path("x.toml"), kind="pep621", pattern=r"(version = \")([^\"]+)(\")"
            ),
            "mutually exclusive",
        ),
        (
            VersionTarget(path=Path("x.toml"), kind="pep621", section="project", field="version"),
            "mutually exclusive",
        ),
        (
            VersionTarget(
                path=Path("x.toml"),
                pattern=r"(version = \")([^\"]+)(\")",
                section="project",
                field="version",
            ),
            "mutually exclusive",
        ),
        (
            VersionTarget(path=Path("x.toml"), section="project"),
            "section and field must be configured together",
        ),
        (
            VersionTarget(path=Path("x.toml"), field="version"),
            "section and field must be configured together",
        ),
    ],
)
def test_version_target_validate_rejects_incomplete_or_conflicting_selectors(
    target: VersionTarget, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        target.validate()


def test_version_target_validate_accepts_section_and_field_selector() -> None:
    target = VersionTarget(path=Path("x.toml"), section="project", field="version")

    target.validate()


def test_load_config_accepts_explicit_generated_files(tmp_path: Path) -> None:
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]
generated_files = ["package-lock.json", "pnpm-lock.yaml"]

[[tool.rrt.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )

    config = load_config(tmp_path)

    assert config.generated_files == [tmp_path / "package-lock.json", tmp_path / "pnpm-lock.yaml"]


def test_load_config_supports_grouped_configuration(tmp_path: Path) -> None:
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]
default_group = "python"

[[tool.rrt.version_groups]]
name = "python"
generated_files = ["uv.lock"]
version_source = "pyproject.toml"

[[tool.rrt.version_groups.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[[tool.rrt.version_groups]]
name = "web"
generated_files = ["pnpm-lock.yaml"]
version_source = "package.json"

[[tool.rrt.version_groups.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )

    config = load_config(tmp_path)

    assert [group.name for group in config.version_groups] == ["python", "web"]
    assert config.resolve_group().name == "python"
    assert config.resolve_group("web").generated_files == [tmp_path / "pnpm-lock.yaml"]
    assert config.resolve_group("web").primary_target().path == tmp_path / "package.json"


def test_load_config_parses_changelog_workflow(tmp_path: Path) -> None:
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

    config = load_config(tmp_path)

    assert config.changelog_workflow == "squash"
    assert config.resolve_group().changelog_workflow == "squash"


def test_group_inherits_default_changelog_workflow(tmp_path: Path) -> None:
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]
changelog_workflow = "squash"
default_group = "python"

[[tool.rrt.version_groups]]
name = "python"

[[tool.rrt.version_groups.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[[tool.rrt.version_groups]]
name = "web"
changelog_workflow = "incremental"

[[tool.rrt.version_groups.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )

    config = load_config(tmp_path)

    assert config.resolve_group("python").changelog_workflow == "squash"
    assert config.resolve_group("web").changelog_workflow == "incremental"


def test_load_config_defaults_changelog_workflow_incremental(tmp_path: Path) -> None:
    (tmp_path / ".rrt.toml").write_text(_RRT_CONFIG, encoding="utf-8")

    config = load_config(tmp_path)

    assert config.changelog_workflow == DEFAULT_CHANGELOG_WORKFLOW


def test_load_config_rejects_invalid_changelog_workflow(tmp_path: Path) -> None:
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]
changelog_workflow = "mystery"

[[tool.rrt.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="changelog_workflow must be one of"):
        load_config(tmp_path)


def test_load_config_rejects_non_table_tool_rrt(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        'tool = { rrt = "oops" }\n[project]\nname = "example"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"\[tool\.rrt\].*must be a table"):
        load_config(tmp_path)


def test_load_config_supports_package_json_rrt(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        """{
  "name": "example",
  "version": "1.0.0",
  "rrt": {
    "release_branch": "release/web/v{version}",
    "version_targets": [
      {
        "path": "package.json",
        "kind": "package_json"
      }
    ]
  }
}
""",
        encoding="utf-8",
    )
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")

    config = load_config(tmp_path)

    assert config.config_file == tmp_path / "package.json"
    assert config.release_branch == "release/web/v{version}"
    assert config.lock_command == ["npm", "install"]
    assert config.generated_files == [tmp_path / "package-lock.json"]


def test_load_config_rejects_package_json_top_level_non_object(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="top-level object"):
        load_config(tmp_path)


def test_load_config_rejects_package_json_rrt_non_object(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"name": "example", "version": "1.0.0", "rrt": "oops"}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="rrt in package.json must be an object"):
        load_config(tmp_path)


def test_load_config_supports_cargo_package_metadata_rrt(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text(
        """\
[package]
name = "example"
version = "1.0.0"

[package.metadata.rrt]
release_branch = "release/rust/v{version}"

[[package.metadata.rrt.version_targets]]
path = "Cargo.toml"
section = "package"
field = "version"
""",
        encoding="utf-8",
    )
    (tmp_path / "Cargo.lock").write_text("# lock\n", encoding="utf-8")

    config = load_config(tmp_path)

    assert config.config_file == tmp_path / "Cargo.toml"
    assert config.release_branch == "release/rust/v{version}"
    assert config.lock_command == ["cargo", "update", "--workspace"]
    assert config.generated_files == [tmp_path / "Cargo.lock"]


def test_load_config_supports_cargo_workspace_metadata_rrt(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text(
        """\
[workspace]
members = ["crates/example"]

[workspace.package]
version = "1.0.0"

[workspace.metadata.rrt]
default_group = "rust"

[[workspace.metadata.rrt.version_groups]]
name = "rust"
version_source = "Cargo.toml"

[[workspace.metadata.rrt.version_groups.version_targets]]
path = "Cargo.toml"
section = "workspace.package"
field = "version"
""",
        encoding="utf-8",
    )

    config = load_config(tmp_path)

    assert config.config_file == tmp_path / "Cargo.toml"
    assert config.resolve_group().primary_target().section == "workspace.package"


def test_load_config_rejects_non_table_cargo_rrt_metadata(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text(
        """\
[package]
name = \"example\"
version = \"1.0.0\"

[package.metadata]
rrt = \"oops\"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must be a table"):
        load_config(tmp_path)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("release_branch = 1", "release_branch must be a string"),
        ("changelog_file = 1", "changelog_file must be a string"),
        ("changelog_workflow = 1", "changelog_workflow must be a string"),
        ('lock_command = "uv lock"', "lock_command must be a list of strings"),
        ('generated_files = "uv.lock"', "generated_files must be a list of strings"),
        ("version_source = 1", "version_source must be a string when provided"),
    ],
)
def test_load_config_rejects_invalid_group_scalar_types(
    tmp_path: Path, body: str, message: str
) -> None:
    (tmp_path / ".rrt.toml").write_text(
        f"""\
[tool.rrt]
{body}

[[tool.rrt.version_targets]]
path = \"package.json\"
kind = \"package_json\"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=message):
        load_config(tmp_path)


@pytest.mark.parametrize(
    ("target_body", "message"),
    [
        ('path = "package.json"\nkind = 1', "kind must be a string when provided"),
        ('path = "package.json"\npattern = 1', "pattern must be a string when provided"),
        (
            'path = "package.json"\nsection = 1\nfield = "version"',
            "section must be a string when provided",
        ),
        (
            'path = "package.json"\nsection = "package"\nfield = 1',
            "field must be a string when provided",
        ),
        ('path = "package.json"\nci_format = 1', "ci_format must be a string when provided"),
    ],
)
def test_load_config_rejects_invalid_target_field_types(
    tmp_path: Path, target_body: str, message: str
) -> None:
    (tmp_path / ".rrt.toml").write_text(
        f"""\
[tool.rrt]

[[tool.rrt.version_targets]]
{target_body}
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=message):
        load_config(tmp_path)


def test_load_config_rejects_missing_version_targets_in_group(tmp_path: Path) -> None:
    (tmp_path / ".rrt.toml").write_text("[tool.rrt]\nversion_targets = []\n", encoding="utf-8")

    with pytest.raises(
        ValueError, match=r"Missing \[\[tool\.rrt\.version_targets\]\] configuration"
    ):
        load_config(tmp_path)


def test_load_config_rejects_non_table_target_entry(tmp_path: Path) -> None:
    (tmp_path / ".rrt.toml").write_text(
        '[tool.rrt]\nversion_targets = ["package.json"]\n', encoding="utf-8"
    )

    with pytest.raises(ValueError, match="Each version target must be a table"):
        load_config(tmp_path)


def test_load_config_rejects_target_without_non_empty_path(tmp_path: Path) -> None:
    (tmp_path / ".rrt.toml").write_text(
        '[tool.rrt]\n\n[[tool.rrt.version_targets]]\npath = ""\nkind = "package_json"\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="non-empty 'path' string"):
        load_config(tmp_path)


def test_load_config_rejects_version_source_not_matching_any_target(tmp_path: Path) -> None:
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]
version_source = "other.json"

[[tool.rrt.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="does not match any target path"):
        load_config(tmp_path)


def test_load_config_rejects_mixing_flat_targets_and_groups(tmp_path: Path) -> None:
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[[tool.rrt.version_groups]]
name = "python"

[[tool.rrt.version_groups.version_targets]]
path = "pyproject.toml"
kind = "pep621"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Use either flat version_targets or version_groups"):
        load_config(tmp_path)


# ---------------------------------------------------------------------------
# Native auto-detection (no [tool.rrt] config)
# ---------------------------------------------------------------------------


def test_auto_detect_pep621_project(tmp_path: Path) -> None:
    """A plain PEP 621 pyproject.toml is detected without any [tool.rrt] section."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "example"\nversion = "1.2.3"\n', encoding="utf-8"
    )

    config = load_config(tmp_path)

    assert config.config_file == tmp_path / "pyproject.toml"
    assert len(config.version_groups) == 1
    group = config.resolve_group()
    assert group.version_targets[0].kind == "pep621"
    assert group.lock_command == ["uv", "lock", "-U"]
    assert group.generated_files == [tmp_path / "uv.lock"]


def test_auto_detect_poetry_project(tmp_path: Path) -> None:
    """A plain Poetry pyproject.toml is detected without any [tool.rrt] section."""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.poetry]\nname = "example"\nversion = "0.5.0"\n',
        encoding="utf-8",
    )

    config = load_config(tmp_path)

    group = config.resolve_group()
    assert group.version_targets[0].section == "tool.poetry"
    assert group.lock_command == ["poetry", "lock"]
    assert group.generated_files == [tmp_path / "poetry.lock"]


def test_auto_detect_package_json_project_no_lockfile(tmp_path: Path) -> None:
    """A package.json project without a lockfile gets no lock command."""
    (tmp_path / "package.json").write_text(
        '{"name": "example", "version": "3.0.0"}', encoding="utf-8"
    )

    config = load_config(tmp_path)

    group = config.resolve_group()
    assert group.version_targets[0].kind == "package_json"
    assert group.lock_command == []
    assert group.generated_files == []


def test_auto_detect_cargo_project(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text(
        """\
[package]
name = "example"
version = "0.5.0"
""",
        encoding="utf-8",
    )
    (tmp_path / "Cargo.lock").write_text("# lock\n", encoding="utf-8")

    config = load_config(tmp_path)

    group = config.resolve_group()
    assert config.config_file == tmp_path / "Cargo.toml"
    assert group.version_targets[0].section == "package"
    assert group.version_targets[0].field == "version"
    assert group.lock_command == ["cargo", "update", "--workspace"]
    assert group.generated_files == [tmp_path / "Cargo.lock"]


def test_go_targets_auto_detect_go_mod_tidy_defaults(tmp_path: Path) -> None:
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]

[[tool.rrt.version_targets]]
path = "internal/version/version.go"
pattern = '^(const Version = ")([^"]+)(")$'
""",
        encoding="utf-8",
    )
    (tmp_path / "go.mod").write_text("module example.com/test\n\ngo 1.24.0\n", encoding="utf-8")
    version_file = tmp_path / "internal" / "version" / "version.go"
    version_file.parent.mkdir(parents=True)
    version_file.write_text('const Version = "1.0.0"\n', encoding="utf-8")

    config = load_config(tmp_path)

    group = config.resolve_group()
    assert group.lock_command == ["go", "mod", "tidy"]
    assert group.generated_files == [tmp_path / "go.mod", tmp_path / "go.sum"]


def test_auto_detect_package_json_with_npm_lockfile(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"name": "example", "version": "3.0.0"}', encoding="utf-8"
    )
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")

    config = load_config(tmp_path)

    group = config.resolve_group()
    assert group.lock_command == ["npm", "install"]
    assert group.generated_files == [tmp_path / "package-lock.json"]


def test_auto_detect_package_json_prefers_pnpm_over_npm(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"name": "example", "version": "3.0.0"}', encoding="utf-8"
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")

    config = load_config(tmp_path)

    group = config.resolve_group()
    assert group.lock_command == ["pnpm", "install"]
    assert group.generated_files == [tmp_path / "pnpm-lock.yaml"]


def test_auto_detect_package_json_with_yarn_lockfile(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"name": "example", "version": "3.0.0"}', encoding="utf-8"
    )
    (tmp_path / "yarn.lock").write_text("# yarn lockfile v1\n", encoding="utf-8")

    config = load_config(tmp_path)

    group = config.resolve_group()
    assert group.lock_command == ["yarn", "install"]
    assert group.generated_files == [tmp_path / "yarn.lock"]


def test_auto_detect_rrt_toml_with_package_json_target_and_pnpm(tmp_path: Path) -> None:
    """An explicit .rrt.toml with package_json target auto-detects pnpm when pnpm-lock exists."""
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]

[[tool.rrt.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text(
        '{"name": "example", "version": "1.0.0"}', encoding="utf-8"
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")

    config = load_config(tmp_path)

    group = config.resolve_group()
    assert group.lock_command == ["pnpm", "install"]
    assert group.generated_files == [tmp_path / "pnpm-lock.yaml"]


def test_auto_detect_rrt_toml_explicit_lock_command_not_overridden(tmp_path: Path) -> None:
    """An explicit lock_command in .rrt.toml is never overridden by auto-detection."""
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]
lock_command = []

[[tool.rrt.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text(
        '{"name": "example", "version": "1.0.0"}', encoding="utf-8"
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")

    config = load_config(tmp_path)

    group = config.resolve_group()
    assert group.lock_command == []


def test_auto_detect_prefers_rrt_config_over_native(tmp_path: Path) -> None:
    """When [tool.rrt] exists it takes full precedence over native detection."""
    (tmp_path / "pyproject.toml").write_text(
        """\
[tool.rrt]
release_branch = "rel/v{version}"

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[project]
name = "example"
version = "9.9.9"
""",
        encoding="utf-8",
    )

    config = load_config(tmp_path)

    assert config.release_branch == "rel/v{version}"
    assert config.resolve_group().version_targets[0].kind == "pep621"


def test_load_config_parses_extra_branch_types(tmp_path: Path) -> None:
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]
extra_branch_types = ["greenkeeper", "Snyk"]

[[tool.rrt.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )

    config = load_config(tmp_path)

    assert config.extra_branch_types == ("greenkeeper", "snyk")


def test_load_config_defaults_extra_branch_types_empty(tmp_path: Path) -> None:
    (tmp_path / ".rrt.toml").write_text(_RRT_CONFIG, encoding="utf-8")

    config = load_config(tmp_path)

    assert config.extra_branch_types == ()


def test_load_config_rejects_non_list_extra_branch_types(tmp_path: Path) -> None:
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]
extra_branch_types = "not-a-list"

[[tool.rrt.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="extra_branch_types must be a list of strings"):
        load_config(tmp_path)


def test_load_config_rejects_empty_extra_branch_type_entry(tmp_path: Path) -> None:
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]
extra_branch_types = [""]

[[tool.rrt.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="non-empty identifiers"):
        load_config(tmp_path)


def test_load_config_rejects_invalid_identifier_extra_branch_type(tmp_path: Path) -> None:
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]
extra_branch_types = ["123-invalid"]

[[tool.rrt.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="not a valid identifier"):
        load_config(tmp_path)


def test_load_config_rejects_reserved_extra_branch_type(tmp_path: Path) -> None:
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]
extra_branch_types = ["feat"]

[[tool.rrt.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="overlaps with a built-in branch type"):
        load_config(tmp_path)


def test_load_config_deduplicates_extra_branch_types(tmp_path: Path) -> None:
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]
extra_branch_types = ["snyk", "Snyk", "snyk"]

[[tool.rrt.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )

    config = load_config(tmp_path)

    assert config.extra_branch_types == ("snyk",)


def test_load_extra_branch_types_returns_empty_when_no_config(tmp_path: Path) -> None:
    assert load_extra_branch_types(tmp_path) == ()


def test_load_extra_branch_types_returns_empty_when_no_rrt_section(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.other]\n", encoding="utf-8")
    assert load_extra_branch_types(tmp_path) == ()


def test_load_extra_branch_types_surfaces_invalid_config_error(tmp_path: Path) -> None:
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]
extra_branch_types = ["feat"]

[[tool.rrt.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Failed to load extra_branch_types configuration"):
        load_extra_branch_types(tmp_path)


def test_load_extra_branch_types_returns_configured_types(tmp_path: Path) -> None:
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]
extra_branch_types = ["snyk", "greenkeeper"]

[[tool.rrt.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )

    assert load_extra_branch_types(tmp_path) == ("snyk", "greenkeeper")


# ---------------------------------------------------------------------------
# find_changelog_file
# ---------------------------------------------------------------------------


def test_find_changelog_file_returns_default_when_no_file(tmp_path: Path) -> None:
    assert find_changelog_file(tmp_path) == DEFAULT_CHANGELOG


def test_find_changelog_file_returns_changelog_md(tmp_path: Path) -> None:
    (tmp_path / "CHANGELOG.md").write_text("", encoding="utf-8")
    assert find_changelog_file(tmp_path) == "CHANGELOG.md"


def test_find_changelog_file_returns_rst_when_md_absent(tmp_path: Path) -> None:
    (tmp_path / "CHANGELOG.rst").write_text("", encoding="utf-8")
    assert find_changelog_file(tmp_path) == "CHANGELOG.rst"


def test_find_changelog_file_prefers_md_over_rst(tmp_path: Path) -> None:
    (tmp_path / "CHANGELOG.md").write_text("", encoding="utf-8")
    (tmp_path / "CHANGELOG.rst").write_text("", encoding="utf-8")
    assert find_changelog_file(tmp_path) == "CHANGELOG.md"


def test_find_changelog_file_returns_plain_changelog(tmp_path: Path) -> None:
    (tmp_path / "CHANGELOG").write_text("", encoding="utf-8")
    assert find_changelog_file(tmp_path) == "CHANGELOG"


def test_autodetect_config_picks_up_rst_changelog(tmp_path: Path) -> None:
    """Zero-config autodetect should use CHANGELOG.rst when no CHANGELOG.md exists."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "example"\nversion = "1.0.0"\n', encoding="utf-8"
    )
    (tmp_path / "CHANGELOG.rst").write_text("", encoding="utf-8")

    config = autodetect_config(tmp_path)
    assert config is not None
    assert config.changelog_file.name == "CHANGELOG.rst"


# ---------------------------------------------------------------------------
# PinTarget — config parsing
# ---------------------------------------------------------------------------


def test_load_config_parses_global_pin_targets(tmp_path: Path) -> None:
    """Global [[tool.rrt.pin_targets]] are loaded onto RrtConfig.global_pin_targets."""

    doc = tmp_path / "docs.md"
    doc.write_text("rev: v0.1.0\n", encoding="utf-8")

    cfg_file = tmp_path / "pyproject.toml"
    cfg_file.write_text(
        """[tool.rrt]

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[[tool.rrt.pin_targets]]
path = "docs.md"
pattern = '(rev: v)(\\d+\\.\\d+\\.\\d+)()'

[project]
name = "example"
version = "0.1.0"
""",
        encoding="utf-8",
    )

    config = load_config_from_path(tmp_path, cfg_file)

    assert len(config.global_pin_targets) == 1
    assert config.global_pin_targets[0].path == tmp_path / "docs.md"
    assert "rev" in config.global_pin_targets[0].pattern


def test_load_config_parses_per_group_pin_targets(tmp_path: Path) -> None:
    """Per-group [[tool.rrt.version_groups.*.pin_targets]] end up on the group."""

    cfg_file = tmp_path / ".rrt.toml"
    cfg_file.write_text(
        """\
[[tool.rrt.version_groups]]
name = "frontend"
release_branch = "release/v{version}"

[[tool.rrt.version_groups.version_targets]]
path = "package.json"
kind = "package_json"

[[tool.rrt.version_groups.pin_targets]]
path = "README.md"
pattern = '(badge/v)(\\d+\\.\\d+\\.\\d+)()'
""",
        encoding="utf-8",
    )

    config = load_config_from_path(tmp_path, cfg_file)

    group = config.resolve_group("frontend")
    assert len(group.pin_targets) == 1
    assert group.pin_targets[0].path == tmp_path / "README.md"


def test_pin_target_validate_rejects_pattern_with_fewer_than_3_groups(tmp_path: Path) -> None:
    """validate() raises if the pattern has < 3 capture groups."""
    from repo_release_tools.config import PinTarget

    pin = PinTarget(path=tmp_path / "file.md", pattern=r"(prefix)(\d+\.\d+\.\d+)")
    with pytest.raises(ValueError, match="3 capture groups"):
        pin.validate()


def test_pin_target_validate_rejects_pattern_with_more_than_3_groups(tmp_path: Path) -> None:
    """validate() raises if the pattern has > 3 capture groups."""
    from repo_release_tools.config import PinTarget

    pin = PinTarget(path=tmp_path / "file.md", pattern=r"(a)(b)(\d+\.\d+\.\d+)(suffix)")
    with pytest.raises(ValueError, match="3 capture groups"):
        pin.validate()


def test_pin_target_validate_rejects_invalid_regex(tmp_path: Path) -> None:
    """validate() raises on invalid regex."""
    from repo_release_tools.config import PinTarget

    pin = PinTarget(path=tmp_path / "file.md", pattern=r"(unclosed[")
    with pytest.raises(ValueError, match="not a valid regex"):
        pin.validate()


def test_load_config_rejects_non_list_pin_targets(tmp_path: Path) -> None:

    cfg_file = tmp_path / "pyproject.toml"
    cfg_file.write_text(
        """[tool.rrt]
pin_targets = {}

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[project]
name = "example"
version = "0.1.0"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="pin_targets must be an array of tables"):
        load_config_from_path(tmp_path, cfg_file)


def test_load_config_rejects_non_table_pin_target_entry(tmp_path: Path) -> None:

    cfg_file = tmp_path / "pyproject.toml"
    cfg_file.write_text(
        """[tool.rrt]
pin_targets = ["docs.md"]

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[project]
name = "example"
version = "0.1.0"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Each pin_targets entry must be a table"):
        load_config_from_path(tmp_path, cfg_file)


def test_load_config_rejects_pin_target_without_path(tmp_path: Path) -> None:

    cfg_file = tmp_path / "pyproject.toml"
    cfg_file.write_text(
        """[tool.rrt]

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[[tool.rrt.pin_targets]]
path = ""
pattern = '(rev: v)(\\d+\\.\\d+\\.\\d+)()'

[project]
name = "example"
version = "0.1.0"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="non-empty 'path' string"):
        load_config_from_path(tmp_path, cfg_file)


def test_load_config_rejects_pin_target_without_pattern(tmp_path: Path) -> None:

    cfg_file = tmp_path / "pyproject.toml"
    cfg_file.write_text(
        """[tool.rrt]

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[[tool.rrt.pin_targets]]
path = "docs.md"
pattern = ""

[project]
name = "example"
version = "0.1.0"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="non-empty 'pattern' string"):
        load_config_from_path(tmp_path, cfg_file)


# ---------------------------------------------------------------------------
# _load_eol_config — via load_config
# ---------------------------------------------------------------------------

_BASE_RRT_CONFIG = """\
[tool.rrt]

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[project]
name = "example"
version = "0.1.0"
"""


def _write_eol_cfg(tmp_path: Path, extra: str) -> None:
    """Write a pyproject.toml with [tool.rrt.eol] appended to the base config."""
    (tmp_path / "pyproject.toml").write_text(
        _BASE_RRT_CONFIG + extra,
        encoding="utf-8",
    )


def test_load_config_eol_section_absent() -> None:
    """When no [tool.rrt.eol] key is present, config.eol is None."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        (p / "pyproject.toml").write_text(_BASE_RRT_CONFIG, encoding="utf-8")
        cfg = load_config(p)
        assert cfg.eol is None


def test_load_config_eol_defaults(tmp_path: Path) -> None:
    """[tool.rrt.eol] with no fields uses all defaults."""
    _write_eol_cfg(tmp_path, "\n[tool.rrt.eol]\n")
    cfg = load_config(tmp_path)
    assert isinstance(cfg.eol, EolConfig)
    assert cfg.eol.languages == ("python",)
    assert cfg.eol.warn_days == 180
    assert cfg.eol.error_days == 0
    assert cfg.eol.fetch_live is False
    assert cfg.eol.allow_eol is False
    assert cfg.eol.overrides == ()


def test_load_config_eol_full(tmp_path: Path) -> None:
    """[tool.rrt.eol] with all fields populated."""
    _write_eol_cfg(
        tmp_path,
        '\n[tool.rrt.eol]\nlanguages = ["python", "nodejs"]\n'
        "warn_days = 90\nerror_days = 30\nfetch_live = true\nallow_eol = true\n",
    )
    cfg = load_config(tmp_path)
    assert cfg.eol is not None
    assert cfg.eol.languages == ("python", "nodejs")
    assert cfg.eol.warn_days == 90
    assert cfg.eol.error_days == 30
    assert cfg.eol.fetch_live is True
    assert cfg.eol.allow_eol is True


def test_load_config_eol_with_overrides(tmp_path: Path) -> None:
    """[tool.rrt.eol.overrides] are parsed into EolOverride tuples."""
    _write_eol_cfg(
        tmp_path,
        '\n[tool.rrt.eol]\nlanguages = ["python"]\n\n'
        '[[tool.rrt.eol.overrides]]\nlanguage = "python"\ncycle = "3.12"\neol = "2026-12-31"\n',
    )
    cfg = load_config(tmp_path)
    assert cfg.eol is not None
    assert len(cfg.eol.overrides) == 1
    ov = cfg.eol.overrides[0]
    assert isinstance(ov, EolOverride)
    assert ov.language == "python"
    assert ov.cycle == "3.12"
    assert ov.eol == "2026-12-31"


def test_load_config_eol_languages_not_list(tmp_path: Path) -> None:
    """Non-list languages value raises ValueError."""
    _write_eol_cfg(tmp_path, '\n[tool.rrt.eol]\nlanguages = "python"\n')
    with pytest.raises(ValueError, match="languages must be a list"):
        load_config(tmp_path)


def test_load_config_eol_warn_days_not_int(tmp_path: Path) -> None:
    """Non-integer warn_days raises ValueError."""
    _write_eol_cfg(tmp_path, '\n[tool.rrt.eol]\nwarn_days = "bad"\n')
    with pytest.raises(ValueError, match="warn_days must be an integer"):
        load_config(tmp_path)


def test_load_config_eol_error_days_not_int(tmp_path: Path) -> None:
    """Non-integer error_days raises ValueError."""
    _write_eol_cfg(tmp_path, '\n[tool.rrt.eol]\nerror_days = "bad"\n')
    with pytest.raises(ValueError, match="error_days must be an integer"):
        load_config(tmp_path)


def test_load_config_eol_fetch_live_not_bool(tmp_path: Path) -> None:
    """Non-boolean fetch_live raises ValueError."""
    _write_eol_cfg(tmp_path, '\n[tool.rrt.eol]\nfetch_live = "yes"\n')
    with pytest.raises(ValueError, match="fetch_live must be a boolean"):
        load_config(tmp_path)


def test_load_config_eol_allow_eol_not_bool(tmp_path: Path) -> None:
    """Non-boolean allow_eol raises ValueError."""
    _write_eol_cfg(tmp_path, "\n[tool.rrt.eol]\nallow_eol = 1\n")
    with pytest.raises(ValueError, match="allow_eol must be a boolean"):
        load_config(tmp_path)


def test_load_config_eol_section_must_be_table(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """\
[tool.rrt]
eol = "bad"

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[project]
name = "example"
version = "0.1.0"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"tool\.rrt\.eol must be a table"):
        load_config(tmp_path)


def test_load_config_eol_overrides_not_list(tmp_path: Path) -> None:
    """Non-list overrides raises ValueError."""
    _write_eol_cfg(tmp_path, '\n[tool.rrt.eol]\noverrides = "bad"\n')
    with pytest.raises(ValueError, match="overrides must be an array"):
        load_config(tmp_path)


def test_load_config_eol_override_entry_must_be_table(tmp_path: Path) -> None:
    _write_eol_cfg(tmp_path, '\n[tool.rrt.eol]\noverrides = ["bad"]\n')

    with pytest.raises(ValueError, match="Each tool.rrt.eol.overrides entry must be a table"):
        load_config(tmp_path)


def test_load_config_eol_override_missing_language(tmp_path: Path) -> None:
    """Override entry without language raises ValueError."""
    _write_eol_cfg(
        tmp_path,
        '\n[tool.rrt.eol]\n\n[[tool.rrt.eol.overrides]]\ncycle = "3.12"\neol = "2026-12-31"\n',
    )
    with pytest.raises(ValueError, match="language must be a non-empty string"):
        load_config(tmp_path)


def test_load_config_eol_override_missing_cycle(tmp_path: Path) -> None:
    """Override entry without cycle raises ValueError."""
    _write_eol_cfg(
        tmp_path,
        '\n[tool.rrt.eol]\n\n[[tool.rrt.eol.overrides]]\nlanguage = "python"\neol = "2026-12-31"\n',
    )
    with pytest.raises(ValueError, match="cycle must be a non-empty string"):
        load_config(tmp_path)


def test_load_config_eol_override_missing_eol(tmp_path: Path) -> None:
    """Override entry without eol date raises ValueError."""
    _write_eol_cfg(
        tmp_path,
        '\n[tool.rrt.eol]\n\n[[tool.rrt.eol.overrides]]\nlanguage = "python"\ncycle = "3.12"\n',
    )
    with pytest.raises(ValueError, match=r"overrides\[\]\.eol must be a non-empty"):
        load_config(tmp_path)


# _load_docs_config — via load_config
# ---------------------------------------------------------------------------


def _write_docs_cfg(tmp_path: Path, extra: str) -> None:
    """Write a pyproject.toml with [tool.rrt.docs] appended to the base config."""
    (tmp_path / "pyproject.toml").write_text(
        _BASE_RRT_CONFIG + extra,
        encoding="utf-8",
    )


def test_load_config_docs_section_absent(tmp_path: Path) -> None:
    """When no [tool.rrt.docs] key is present, config.docs is None."""
    _write_docs_cfg(tmp_path, "")
    cfg = load_config(tmp_path)
    assert cfg.docs is None


def test_load_config_docs_defaults(tmp_path: Path) -> None:
    """[tool.rrt.docs] with no fields uses all defaults."""
    _write_docs_cfg(tmp_path, "\n[tool.rrt.docs]\n")
    cfg = load_config(tmp_path)
    assert isinstance(cfg.docs, DocsConfig)
    assert cfg.docs.mirror_src_tree is False
    assert cfg.docs.docs_dir == "docs"
    assert cfg.docs.src_dir == "src/repo_release_tools"
    assert cfg.docs.stubs == ()


def test_load_config_docs_full(tmp_path: Path) -> None:
    """[tool.rrt.docs] with all fields populated."""
    _write_docs_cfg(
        tmp_path,
        '\n[tool.rrt.docs]\nmirror_src_tree = true\ndocs_dir = "documentation"\n'
        'src_dir = "src/mypackage"\nstubs = ["commands/bump", "commands/init"]\n',
    )
    cfg = load_config(tmp_path)
    assert cfg.docs is not None
    assert cfg.docs.mirror_src_tree is True
    assert cfg.docs.docs_dir == "documentation"
    assert cfg.docs.src_dir == "src/mypackage"
    assert cfg.docs.stubs == ("commands/bump", "commands/init")


def test_load_config_docs_not_a_table(tmp_path: Path) -> None:
    """[tool.rrt.docs] must be a table, not a scalar."""
    (tmp_path / "pyproject.toml").write_text(
        """\
[tool.rrt]
docs = "bad"

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[project]
name = "example"
version = "0.1.0"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"tool\.rrt\.docs must be a table"):
        load_config(tmp_path)


def test_load_config_docs_mirror_not_bool(tmp_path: Path) -> None:
    """mirror_src_tree must be a boolean."""
    _write_docs_cfg(tmp_path, '\n[tool.rrt.docs]\nmirror_src_tree = "yes"\n')
    with pytest.raises(ValueError, match="mirror_src_tree must be a boolean"):
        load_config(tmp_path)


def test_load_config_docs_docs_dir_not_string(tmp_path: Path) -> None:
    """docs_dir must be a non-empty string."""
    _write_docs_cfg(tmp_path, "\n[tool.rrt.docs]\ndocs_dir = 123\n")
    with pytest.raises(ValueError, match="docs_dir must be a non-empty string"):
        load_config(tmp_path)


def test_load_config_docs_src_dir_not_string(tmp_path: Path) -> None:
    """src_dir must be a non-empty string."""
    _write_docs_cfg(tmp_path, "\n[tool.rrt.docs]\nsrc_dir = 123\n")
    with pytest.raises(ValueError, match="src_dir must be a non-empty string"):
        load_config(tmp_path)


def test_load_config_docs_stubs_not_list(tmp_path: Path) -> None:
    """stubs must be a list of strings."""
    _write_docs_cfg(tmp_path, '\n[tool.rrt.docs]\nstubs = "commands/bump"\n')
    with pytest.raises(ValueError, match="stubs must be a list of strings"):
        load_config(tmp_path)


def test_load_config_docs_stubs_empty_entry(tmp_path: Path) -> None:
    """stubs list must not contain empty/whitespace-only entries."""
    _write_docs_cfg(tmp_path, '\n[tool.rrt.docs]\nstubs = ["commands/bump", ""]\n')
    with pytest.raises(ValueError, match="must not contain empty entries"):
        load_config(tmp_path)


def test_load_config_docs_stubs_whitespace_entry(tmp_path: Path) -> None:
    """A whitespace-only stub entry is rejected after stripping."""
    _write_docs_cfg(tmp_path, '\n[tool.rrt.docs]\nstubs = ["commands/bump", "   "]\n')
    with pytest.raises(ValueError, match="must not contain empty entries"):
        load_config(tmp_path)


def test_load_config_docs_stubs_deduplication(tmp_path: Path) -> None:
    """Duplicate stub entries are silently removed, preserving first occurrence."""
    _write_docs_cfg(
        tmp_path,
        '\n[tool.rrt.docs]\nstubs = ["commands/bump", "commands/branch", "commands/bump"]\n',
    )
    cfg = load_config(tmp_path)
    assert cfg.docs is not None
    assert cfg.docs.stubs == ("commands/bump", "commands/branch")


def test_load_config_docs_stubs_strip_whitespace(tmp_path: Path) -> None:
    """Leading/trailing whitespace in stub entries is stripped."""
    _write_docs_cfg(tmp_path, '\n[tool.rrt.docs]\nstubs = ["  commands/bump  "]\n')
    cfg = load_config(tmp_path)
    assert cfg.docs is not None
    assert cfg.docs.stubs == ("commands/bump",)


# _load_extraction_mode / _load_docs_languages / _load_docs_lock_file / _load_docs_formats
# ---------------------------------------------------------------------------


def test_load_config_docs_extraction_mode_valid(tmp_path: Path) -> None:
    """Valid extraction_mode values are accepted."""
    for mode in ("explicit", "implicit", "both"):
        _write_docs_cfg(tmp_path, f'\n[tool.rrt.docs]\nextraction_mode = "{mode}"\n')
        cfg = load_config(tmp_path)
        assert cfg.docs is not None
        assert cfg.docs.extraction_mode == mode


def test_load_config_docs_extraction_mode_invalid(tmp_path: Path) -> None:
    """An unrecognised extraction_mode raises ValueError."""
    _write_docs_cfg(tmp_path, '\n[tool.rrt.docs]\nextraction_mode = "fancy"\n')
    with pytest.raises(ValueError, match="extraction_mode must be one of"):
        load_config(tmp_path)


def test_load_config_docs_languages_valid(tmp_path: Path) -> None:
    """A supported languages list is accepted."""
    _write_docs_cfg(tmp_path, '\n[tool.rrt.docs]\nlanguages = ["python", "go"]\n')
    cfg = load_config(tmp_path)
    assert cfg.docs is not None
    assert cfg.docs.languages == ("python", "go")


def test_load_config_docs_languages_not_list(tmp_path: Path) -> None:
    """languages must be a list of strings; a scalar raises ValueError."""
    _write_docs_cfg(tmp_path, '\n[tool.rrt.docs]\nlanguages = "python"\n')
    with pytest.raises(ValueError, match="languages must be a list of strings"):
        load_config(tmp_path)


def test_load_config_docs_languages_invalid_entry(tmp_path: Path) -> None:
    """An unrecognised language in the list raises ValueError."""
    _write_docs_cfg(tmp_path, '\n[tool.rrt.docs]\nlanguages = ["python", "cobol"]\n')
    with pytest.raises(ValueError, match="unsupported entries"):
        load_config(tmp_path)


def test_load_config_docs_lock_file_custom(tmp_path: Path) -> None:
    """A custom lock_file path is accepted and returned."""
    _write_docs_cfg(tmp_path, '\n[tool.rrt.docs]\nlock_file = ".rrt/custom.lock.toml"\n')
    cfg = load_config(tmp_path)
    assert cfg.docs is not None
    assert cfg.docs.lock_file == ".rrt/custom.lock.toml"


def test_load_config_docs_lock_file_empty_string(tmp_path: Path) -> None:
    """An empty string for lock_file raises ValueError."""
    _write_docs_cfg(tmp_path, '\n[tool.rrt.docs]\nlock_file = ""\n')
    with pytest.raises(ValueError, match="lock_file must be a non-empty string"):
        load_config(tmp_path)


def test_load_config_docs_formats_valid(tmp_path: Path) -> None:
    """Valid formats list is accepted."""
    _write_docs_cfg(tmp_path, '\n[tool.rrt.docs]\nformats = ["md", "json"]\n')
    cfg = load_config(tmp_path)
    assert cfg.docs is not None
    assert cfg.docs.formats == ("md", "json")


def test_load_config_docs_formats_not_list(tmp_path: Path) -> None:
    """formats must be a list; a scalar raises ValueError."""
    _write_docs_cfg(tmp_path, '\n[tool.rrt.docs]\nformats = "md"\n')
    with pytest.raises(ValueError, match="formats must be a list of strings"):
        load_config(tmp_path)


def test_load_config_docs_formats_empty_list(tmp_path: Path) -> None:
    """An empty formats list raises ValueError."""
    _write_docs_cfg(tmp_path, "\n[tool.rrt.docs]\nformats = []\n")
    with pytest.raises(ValueError, match="must not be empty"):
        load_config(tmp_path)


def test_load_config_docs_formats_invalid_entry(tmp_path: Path) -> None:
    """An unrecognised format raises ValueError."""
    _write_docs_cfg(tmp_path, '\n[tool.rrt.docs]\nformats = ["md", "pdf"]\n')
    with pytest.raises(ValueError, match="unsupported entries"):
        load_config(tmp_path)


# ---------------------------------------------------------------------------
# New tests targeting uncovered lines in config.py
# ---------------------------------------------------------------------------


def test_version_target_validate_rejects_non_string_ci_format() -> None:
    """ci_format that is not a string raises ValueError."""
    target = VersionTarget.__new__(VersionTarget)
    object.__setattr__(target, "path", Path("x.toml"))
    object.__setattr__(target, "kind", "pep621")
    object.__setattr__(target, "pattern", None)
    object.__setattr__(target, "section", None)
    object.__setattr__(target, "field", None)
    object.__setattr__(target, "ci_format", 123)
    with pytest.raises(ValueError, match="ci_format must be a string"):
        target.validate()


def test_version_target_validate_rejects_invalid_ci_format_value() -> None:
    """ci_format with an unrecognised string value raises ValueError."""
    target = VersionTarget(path=Path("x.toml"), kind="pep621", ci_format="invalid")
    with pytest.raises(ValueError, match="ci_format must be 'pep440' or 'semver_pre'"):
        target.validate()


def test_version_group_primary_target_raises_when_version_source_unmatched(tmp_path: Path) -> None:
    """primary_target raises when version_source does not match any target."""
    t = VersionTarget(path=tmp_path / "pyproject.toml", kind="pep621")
    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=tmp_path / "CHANGELOG.md",
        lock_command=[],
        generated_files=[],
        version_targets=[t],
        version_source=tmp_path / "other.toml",
    )
    with pytest.raises(ValueError, match="does not match any target"):
        group.primary_target()


def test_rrtconfig_resolve_group_raises_for_multiple_groups_no_selection(tmp_path: Path) -> None:
    """resolve_group() raises when multiple groups exist and no selection is made."""
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]

[[tool.rrt.version_groups]]
name = "python"

[[tool.rrt.version_groups.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[[tool.rrt.version_groups]]
name = "web"

[[tool.rrt.version_groups.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )
    config = load_config(tmp_path)
    with pytest.raises(ValueError, match="Multiple version groups configured"):
        config.resolve_group()


def test_rrtconfig_version_targets_property(tmp_path: Path) -> None:
    """version_targets property delegates to the default group."""
    (tmp_path / ".rrt.toml").write_text(_RRT_CONFIG, encoding="utf-8")
    config: RrtConfig = load_config(tmp_path)
    targets = config.version_targets
    assert len(targets) == 1
    assert targets[0].kind == "package_json"


def test_load_or_autodetect_config_raises_file_not_found_when_nothing(tmp_path: Path) -> None:
    """load_or_autodetect_config re-raises FileNotFoundError when autodetect also fails."""
    with pytest.raises(FileNotFoundError):
        load_or_autodetect_config(tmp_path)


def test_load_or_autodetect_config_falls_back_on_missing_rrt(tmp_path: Path) -> None:
    """Falls back to autodetect when config file exists but lacks [tool.rrt]."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1.0.0"\n', encoding="utf-8"
    )
    config = load_or_autodetect_config(tmp_path)
    assert config.autodetected is True


def test_load_or_autodetect_config_raises_missing_rrt_when_no_autodetect(tmp_path: Path) -> None:
    """Re-raises the missing-rrt ValueError when autodetect also returns None."""
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="Missing rrt configuration"):
        load_or_autodetect_config(tmp_path)


def test_find_python_version_files_handles_iterdir_oserror(tmp_path: Path) -> None:
    """OSError during iterdir is silently skipped."""
    (tmp_path / "src").mkdir()
    with patch("repo_release_tools.config.Path.iterdir", side_effect=OSError("perm")):
        files = _find_python_version_files(tmp_path)
    assert files == []


def test_find_python_version_files_handles_read_text_oserror(tmp_path: Path) -> None:
    """OSError during read_text is silently skipped."""
    pkg = tmp_path / "src" / "mypkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text('__version__ = "1.0.0"\n', encoding="utf-8")
    with patch("repo_release_tools.config.Path.read_text", side_effect=OSError("perm")):
        files = _find_python_version_files(tmp_path)
    assert files == []


def test_autodetect_version_targets_finds_cargo_workspace_package(tmp_path: Path) -> None:
    """Cargo.toml with [workspace.package].version is auto-detected."""
    (tmp_path / "Cargo.toml").write_text(
        '[workspace.package]\nname = "ws"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    targets = _autodetect_version_targets(tmp_path)
    assert any(t.section == "workspace.package" for t in targets)


def test_autodetect_version_targets_detects_python_version_files(tmp_path: Path) -> None:
    """__version__ files are discovered as secondary targets for pep621 projects."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1.0.0"\n', encoding="utf-8"
    )
    pkg = tmp_path / "src" / "mypkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text('__version__ = "1.0.0"\n', encoding="utf-8")
    targets = _autodetect_version_targets(tmp_path)
    assert any(t.kind == "python_version" for t in targets)


def test_toml_string_field_exists_returns_false_on_oserror(tmp_path: Path) -> None:
    """OSError while opening TOML is caught and returns False."""
    p = tmp_path / "test.toml"
    p.write_text("[project]\nversion = '1.0.0'\n", encoding="utf-8")
    with patch("repo_release_tools.config.tomllib.load", side_effect=OSError("perm")):
        assert _toml_string_field_exists(p, section="project", field="version") is False


def test_json_string_field_exists_returns_false_on_oserror(tmp_path: Path) -> None:
    """OSError while reading JSON is caught and returns False."""
    p = tmp_path / "package.json"
    p.write_text('{"version": "1.0.0"}', encoding="utf-8")
    with patch("repo_release_tools.config.Path.read_text", side_effect=OSError("perm")):
        assert _json_string_field_exists(p, field="version") is False


def test_describe_version_target_go_version(tmp_path: Path) -> None:
    target = VersionTarget(path=tmp_path / "version.go", kind="go_version")
    result = _describe_version_target(target, root=tmp_path)
    assert result == "version.go (Version)"


def test_describe_version_target_section_field(tmp_path: Path) -> None:
    target = VersionTarget(path=tmp_path / "x.toml", section="package", field="version")
    result = _describe_version_target(target, root=tmp_path)
    assert result == "x.toml ([package].version)"


def test_describe_version_target_fallback(tmp_path: Path) -> None:
    """Target with no special fields falls back to the bare relative path."""
    target = VersionTarget(path=tmp_path / "VERSION")
    result = _describe_version_target(target, root=tmp_path)
    assert result == "VERSION"


def test_recommend_init_config_with_autodetect(tmp_path: Path) -> None:
    """recommend_init_config returns rendered TOML when autodetect succeeds."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1.0.0"\n', encoding="utf-8"
    )
    result = recommend_init_config(tmp_path)
    assert "[tool.rrt]" in result
    assert "pep621" in result


def test_recommend_init_config_go_mod_fallback(tmp_path: Path) -> None:
    """recommend_init_config uses GO example when go.mod exists but no detectable version."""
    (tmp_path / "go.mod").write_text("module example.com/x\ngo 1.21\n", encoding="utf-8")
    result = recommend_init_config(tmp_path)
    assert "go_version" in result
    assert "# Edit" in result


def test_recommend_init_config_for_go_with_autodetect(tmp_path: Path) -> None:
    """recommend_init_config_for_go returns rendered TOML when autodetect succeeds."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1.0.0"\n', encoding="utf-8"
    )
    result = recommend_init_config_for_go(tmp_path)
    assert "[tool.rrt]" in result


def test_recommend_init_section_for_pyproject_with_autodetect(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1.0.0"\n', encoding="utf-8"
    )
    result = recommend_init_section_for_pyproject(tmp_path)
    assert "[tool.rrt]" in result


def test_recommend_init_section_for_cargo_with_autodetect(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "x"\nversion = "1.0.0"\n', encoding="utf-8"
    )
    (tmp_path / "Cargo.lock").write_text("", encoding="utf-8")
    result = recommend_init_section_for_cargo(tmp_path)
    assert "[package.metadata.rrt]" in result
    assert "lock_command" in result


def test_render_recommended_rrt_dict_with_lock_and_generated(tmp_path: Path) -> None:
    """recommend_init_section_for_node includes lock_command and generated_files."""
    (tmp_path / "package.json").write_text('{"name": "x", "version": "1.0.0"}', encoding="utf-8")
    (tmp_path / "pnpm-lock.yaml").write_text("", encoding="utf-8")
    result = recommend_init_section_for_node(tmp_path)
    assert isinstance(result, dict)
    assert "lock_command" in result
    assert "generated_files" in result


def test_render_recommended_rrt_dict_with_multiple_targets(tmp_path: Path) -> None:
    """recommend_init_section_for_node encodes version_source and section/field."""
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "x"\nversion = "1.0.0"\n', encoding="utf-8"
    )
    (tmp_path / "package.json").write_text('{"name": "x", "version": "1.0.0"}', encoding="utf-8")
    result = recommend_init_section_for_node(tmp_path)
    assert isinstance(result, dict)
    assert "version_source" in result
    rendered = str(result)
    assert "'section'" in rendered
    assert "'field'" in rendered
    assert "'ci_format'" in rendered


def test_render_recommended_rrt_toml_version_source_multiple_targets(tmp_path: Path) -> None:
    """_render_recommended_rrt_toml emits version_source when group has >1 targets."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1.0.0"\n', encoding="utf-8"
    )
    (tmp_path / "package.json").write_text('{"name": "x", "version": "1.0.0"}', encoding="utf-8")
    result = recommend_init_config(tmp_path)
    assert "version_source" in result


def test_recommended_lock_settings_poetry_ecosystem(tmp_path: Path) -> None:
    """recommend_init_config returns poetry lock command for poetry projects."""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.poetry]\nname = "x"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    result = recommend_init_config(tmp_path)
    assert "poetry" in result
    assert "lock_command" in result


def test_recommended_lock_settings_node_ecosystem(tmp_path: Path) -> None:
    """recommend_init_config returns pnpm lock settings for node + pnpm-lock.yaml."""
    (tmp_path / "package.json").write_text('{"name": "x", "version": "1.0.0"}', encoding="utf-8")
    (tmp_path / "pnpm-lock.yaml").write_text("", encoding="utf-8")
    result = recommend_init_config(tmp_path)
    assert "pnpm" in result
    assert "lock_command" in result


def test_target_ecosystem_go_version() -> None:
    t = VersionTarget(path=Path("version.go"), kind="go_version")
    assert _target_ecosystem(t) == "go"


def test_target_ecosystem_python_poetry() -> None:
    t = VersionTarget(path=Path("pyproject.toml"), section="tool.poetry", field="version")
    assert _target_ecosystem(t) == "python-poetry"


def test_target_ecosystem_rust() -> None:
    t = VersionTarget(path=Path("Cargo.toml"), section="package", field="version")
    assert _target_ecosystem(t) == "rust"


def test_target_ecosystem_go_mod_file() -> None:
    t = VersionTarget(path=Path("go.mod"), section="module", field="require")
    assert _target_ecosystem(t) == "go"


def test_target_ecosystem_go_suffix_file() -> None:
    t = VersionTarget(path=Path("cmd/version.go"), section=None, field=None)
    assert _target_ecosystem(t) == "go"


def test_target_ecosystem_returns_none_for_unknown() -> None:
    t = VersionTarget(path=Path("some/file.txt"), section="custom", field="ver")
    assert _target_ecosystem(t) is None


def test_load_config_from_path_rejects_non_string_default_group(tmp_path: Path) -> None:
    """default_group = integer raises ValueError."""
    p = tmp_path / ".rrt.toml"
    p.write_text(
        '[tool.rrt]\ndefault_group = 123\n\n[[tool.rrt.version_targets]]\npath = "x.toml"\nkind = "pep621"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="default_group must be a string"):
        load_config_from_path(tmp_path, p)


def test_load_config_from_path_rejects_non_list_extra_branch_types(tmp_path: Path) -> None:
    """extra_branch_types = string raises ValueError."""
    p = tmp_path / ".rrt.toml"
    p.write_text(
        '[tool.rrt]\nextra_branch_types = "oops"\n\n[[tool.rrt.version_targets]]\npath = "x.toml"\nkind = "pep621"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="extra_branch_types must be a list"):
        load_config_from_path(tmp_path, p)


def test_load_config_rejects_version_groups_not_a_list(tmp_path: Path) -> None:
    """version_groups = string raises ValueError."""
    p = tmp_path / ".rrt.toml"
    p.write_text('[tool.rrt]\nversion_groups = "invalid"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="version_groups must be an array"):
        load_config_from_path(tmp_path, p)


def test_load_config_rejects_version_group_entry_not_table(tmp_path: Path) -> None:
    """version_groups containing a string entry raises ValueError."""
    import json as _json

    p = tmp_path / "package.json"
    p.write_text(
        _json.dumps({"rrt": {"version_groups": ["string_not_table"]}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Each tool.rrt.version_groups entry must be a table"):
        load_config_from_path(tmp_path, p)


def test_load_config_rejects_version_group_missing_name(tmp_path: Path) -> None:
    """version_group entry without a non-empty name raises ValueError."""
    p = tmp_path / ".rrt.toml"
    p.write_text(
        """\
[tool.rrt]

[[tool.rrt.version_groups]]

[[tool.rrt.version_groups.version_targets]]
path = "pyproject.toml"
kind = "pep621"
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="non-empty name"):
        load_config_from_path(tmp_path, p)


def test_load_config_rejects_duplicate_version_group_names(tmp_path: Path) -> None:
    """Two version_groups with the same name raises ValueError."""
    p = tmp_path / ".rrt.toml"
    p.write_text(
        """\
[tool.rrt]

[[tool.rrt.version_groups]]
name = "python"

[[tool.rrt.version_groups.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[[tool.rrt.version_groups]]
name = "python"

[[tool.rrt.version_groups.version_targets]]
path = "pyproject.toml"
kind = "pep621"
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Duplicate version group name"):
        load_config_from_path(tmp_path, p)


def test_load_config_rejects_default_group_name_not_in_groups(tmp_path: Path) -> None:
    """default_group pointing to a non-existent group name raises ValueError."""
    p = tmp_path / ".rrt.toml"
    p.write_text(
        """\
[tool.rrt]
default_group = "nonexistent"

[[tool.rrt.version_groups]]
name = "python"

[[tool.rrt.version_groups.version_targets]]
path = "pyproject.toml"
kind = "pep621"
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="is not defined"):
        load_config_from_path(tmp_path, p)


def test_auto_detect_config_cargo_workspace_package(tmp_path: Path) -> None:
    """auto_detect_config handles Cargo.toml with [workspace.package].version."""
    (tmp_path / "Cargo.toml").write_text(
        '[workspace]\nmembers = []\n\n[workspace.package]\nname = "ws"\nversion = "0.2.0"\n',
        encoding="utf-8",
    )
    config = autodetect_config(tmp_path)
    assert config is not None
    group = config.resolve_group()
    assert any(t.section == "workspace.package" for t in group.version_targets)


# ---------------------------------------------------------------------------
# Additional tests for remaining uncovered lines
# ---------------------------------------------------------------------------


def test_version_target_validate_rejects_invalid_kind() -> None:
    """kind not in VALID_TARGET_KINDS raises ValueError."""
    target = VersionTarget(path=Path("x.toml"), kind="bogus_kind")
    with pytest.raises(ValueError, match="kind must be one of"):
        target.validate()


def test_version_target_validate_rejects_no_mode() -> None:
    """Target with no kind/pattern/section+field raises ValueError."""
    target = VersionTarget(path=Path("x"))
    with pytest.raises(ValueError, match="Each version target must define either"):
        target.validate()


def test_version_group_primary_target_returns_first_when_no_version_source(
    tmp_path: Path,
) -> None:
    """primary_target returns targets[0] when version_source is None."""
    t = VersionTarget(path=tmp_path / "pyproject.toml", kind="pep621")
    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=tmp_path / "CHANGELOG.md",
        lock_command=[],
        generated_files=[],
        version_targets=[t],
    )
    assert group.primary_target() == t


def test_rrtconfig_resolve_group_raises_unknown_name(tmp_path: Path) -> None:
    """resolve_group raises for an explicit name that does not exist."""
    (tmp_path / ".rrt.toml").write_text(_RRT_CONFIG, encoding="utf-8")
    config = load_config(tmp_path)
    with pytest.raises(ValueError, match="Unknown version group"):
        config.resolve_group("nonexistent")


def test_rrtconfig_resolve_group_returns_single_group_directly() -> None:
    """resolve_group returns the sole group when default_group_name is None."""
    t = VersionTarget(path=Path("x.toml"), kind="pep621")
    group = VersionGroup(
        name="only",
        release_branch="release/v{version}",
        changelog_file=Path("CHANGELOG.md"),
        lock_command=[],
        generated_files=[],
        version_targets=[t],
    )
    config = RrtConfig(
        root=Path("."),
        config_file=Path(".rrt.toml"),
        version_groups=[group],
        default_group_name=None,
    )
    assert config.resolve_group() is group


def test_is_missing_tool_rrt_error_with_direct_exception() -> None:
    """is_missing_tool_rrt_error returns True for MissingRrtConfigError instances."""
    from repo_release_tools.config import is_missing_tool_rrt_error

    exc = MissingRrtConfigError("Missing [tool.rrt]")  # noqa: F821 — imported above
    assert is_missing_tool_rrt_error(exc) is True


def test_format_missing_tool_rrt_guidance_with_files(tmp_path: Path) -> None:
    """format_missing_tool_rrt_guidance generates help text when checked files given."""
    from repo_release_tools.config import format_missing_tool_rrt_guidance

    result = format_missing_tool_rrt_guidance(tmp_path, checked_files=[tmp_path / "pyproject.toml"])
    assert "No rrt configuration was found" in result
    assert "Zero-config mode" in result
    assert "rrt init" in result


def test_format_missing_tool_rrt_guidance_no_files(tmp_path: Path) -> None:
    """format_missing_tool_rrt_guidance generates help text when no checked files."""
    from repo_release_tools.config import format_missing_tool_rrt_guidance

    result = format_missing_tool_rrt_guidance(tmp_path, checked_files=[])
    assert "No supported config file was found" in result
    assert "rrt init" in result


def test_describe_version_target_pep621(tmp_path: Path) -> None:
    target = VersionTarget(path=tmp_path / "pyproject.toml", kind="pep621")
    result = _describe_version_target(target, root=tmp_path)
    assert result == "pyproject.toml ([project].version)"


def test_describe_version_target_package_json(tmp_path: Path) -> None:
    target = VersionTarget(path=tmp_path / "package.json", kind="package_json")
    result = _describe_version_target(target, root=tmp_path)
    assert result == "package.json (version)"


def test_describe_version_target_python_version(tmp_path: Path) -> None:
    target = VersionTarget(path=tmp_path / "__init__.py", kind="python_version")
    result = _describe_version_target(target, root=tmp_path)
    assert result == "__init__.py (__version__)"


def test_describe_version_target_pattern(tmp_path: Path) -> None:
    target = VersionTarget(path=tmp_path / "VERSION", pattern=r'^version = "(.+)"$')
    result = _describe_version_target(target, root=tmp_path)
    assert result == "VERSION (pattern)"


def test_find_explicit_config_file_returns_path(tmp_path: Path) -> None:
    """find_explicit_config_file returns the config file that has [tool.rrt]."""
    from repo_release_tools.config import find_explicit_config_file

    (tmp_path / ".rrt.toml").write_text(_RRT_CONFIG, encoding="utf-8")
    result = find_explicit_config_file(tmp_path)
    assert result == tmp_path / ".rrt.toml"


def test_recommend_init_config_returns_generic_fallback(tmp_path: Path) -> None:
    """recommend_init_config falls back to GENERIC when no autodetect and no go.mod."""
    result = recommend_init_config(tmp_path)
    assert "rrt init" in result or "version" in result.lower()


def test_recommend_init_section_for_pyproject_fallback(tmp_path: Path) -> None:
    """recommend_init_section_for_pyproject falls back when no autodetect."""
    result = recommend_init_section_for_pyproject(tmp_path)
    assert "pep621" in result or "project" in result.lower()


def test_recommend_init_section_for_cargo_fallback(tmp_path: Path) -> None:
    """recommend_init_section_for_cargo falls back when no autodetect."""
    result = recommend_init_section_for_cargo(tmp_path)
    assert "Cargo" in result or "package" in result.lower()


def test_recommend_init_section_for_node_fallback(tmp_path: Path) -> None:
    """recommend_init_section_for_node falls back when no autodetect."""
    result = recommend_init_section_for_node(tmp_path)
    assert isinstance(result, dict)
    assert "version_targets" in result


def test_recommend_init_config_for_go_fallback(tmp_path: Path) -> None:
    """recommend_init_config_for_go falls back when no autodetect."""
    result = recommend_init_config_for_go(tmp_path)
    assert "go_version" in result


def test_render_rrt_dict_target_with_pattern(tmp_path: Path) -> None:
    """_render_recommended_rrt_dict includes pattern field in output."""
    (tmp_path / "VERSION").write_text("1.0.0\n", encoding="utf-8")
    pat = r'^version = "(.+)"$'
    target = VersionTarget(path=tmp_path / "VERSION", pattern=pat)
    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=tmp_path / "CHANGELOG.md",
        lock_command=[],
        generated_files=[],
        version_targets=[target],
    )
    from repo_release_tools.config import _render_recommended_rrt_dict

    result = _render_recommended_rrt_dict(tmp_path, group)
    assert "pattern" in str(result)


def test_render_rrt_toml_target_with_pattern(tmp_path: Path) -> None:
    """_render_recommended_rrt_toml emits pattern line for pattern targets."""
    pat = r'^version = "(.+)"$'
    target = VersionTarget(path=tmp_path / "VERSION", pattern=pat)
    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=tmp_path / "CHANGELOG.md",
        lock_command=[],
        generated_files=[],
        version_targets=[target],
    )
    from repo_release_tools.config import _render_recommended_rrt_toml

    result = _render_recommended_rrt_toml(tmp_path, group)
    assert "pattern" in result
    assert pat in result


def test_target_ecosystem_python_version_returns_none() -> None:
    """_target_ecosystem returns None for python_version targets."""
    t = VersionTarget(path=Path("src/pkg/__init__.py"), kind="python_version")
    assert _target_ecosystem(t) is None


def test_auto_detect_config_cargo_no_version(tmp_path: Path) -> None:
    """auto_detect_config returns None for Cargo.toml without package.version."""
    (tmp_path / "Cargo.toml").write_text("[workspace]\nmembers = []\n", encoding="utf-8")
    result = autodetect_config(tmp_path)
    assert result is None


def test_load_or_autodetect_config_reraises_non_missing_rrt_value_error(tmp_path: Path) -> None:
    """load_or_autodetect_config re-raises ValueError that is not a missing-rrt error (line 467)."""
    # Using both version_targets and version_groups triggers a non-missing-rrt ValueError.
    (tmp_path / "pyproject.toml").write_text(
        "[tool.rrt]\nversion_targets = []\n\n[tool.rrt.version_groups]\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Use either flat version_targets or version_groups"):
        load_or_autodetect_config(tmp_path)


def test_autodetect_version_targets_skips_duplicate_python_version_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Line 662: py_file already present in targets is skipped via continue."""
    import repo_release_tools.config as _config_mod

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "x"\nversion = "1.0.0"\n', encoding="utf-8")
    # Return the pep621 path from _find_python_version_files so it duplicates the existing target.
    monkeypatch.setattr(_config_mod, "_find_python_version_files", lambda root: [pyproject])
    targets = _autodetect_version_targets(tmp_path)
    python_version_entries = [t for t in targets if t.kind == "python_version"]
    assert len(python_version_entries) == 0


def test_load_or_autodetect_file_not_found_with_autodetect_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Line 463: load_or_autodetect_config returns autodetected when load_config raises FileNotFoundError."""
    import repo_release_tools.config as _config_mod

    fake_cfg = object()
    monkeypatch.setattr(
        _config_mod,
        "load_config",
        lambda root: (_ for _ in ()).throw(FileNotFoundError("no files")),
    )
    monkeypatch.setattr(_config_mod, "autodetect_config", lambda root: fake_cfg)
    result = load_or_autodetect_config(tmp_path)
    assert result is fake_cfg


def test_load_or_autodetect_missing_rrt_with_autodetect_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Line 470: load_or_autodetect_config returns autodetected when load_config raises missing-rrt ValueError."""
    import repo_release_tools.config as _config_mod
    from repo_release_tools.config import MissingRrtConfigError

    fake_cfg = object()
    monkeypatch.setattr(
        _config_mod,
        "load_config",
        lambda root: (_ for _ in ()).throw(MissingRrtConfigError("Missing rrt")),
    )
    monkeypatch.setattr(_config_mod, "autodetect_config", lambda root: fake_cfg)
    result = load_or_autodetect_config(tmp_path)
    assert result is fake_cfg


def test_recommended_lock_settings_unknown_ecosystem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Line 888: _recommended_lock_settings returns ([], []) for a single unknown ecosystem."""
    import repo_release_tools.config as _config_mod

    monkeypatch.setattr(_config_mod, "_target_ecosystem", lambda t: "unknown-eco")
    target = VersionTarget(path=tmp_path / "VERSION", kind="custom")
    result = _recommended_lock_settings(tmp_path, [target])
    assert result == ([], [])


def test_load_config_from_path_rejects_non_dict_raw(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Line 932: load_config_from_path raises ValueError when raw config is not a dict."""
    import repo_release_tools.config as _config_mod

    cfg_file = tmp_path / ".rrt.toml"
    cfg_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(_config_mod, "_load_raw_config", lambda path: ["not", "a", "dict"])
    with pytest.raises(ValueError, match="must be a table/object"):
        load_config_from_path(tmp_path, cfg_file)


def test_auto_detect_config_poetry_falls_back_to_default_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Lines 1302-1303: auto_detect_config sets poetry lock defaults when _detect_lock_and_files returns empty."""
    import repo_release_tools.config as _config_mod

    (tmp_path / "pyproject.toml").write_text(
        '[tool.poetry]\nname = "x"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    monkeypatch.setattr(_config_mod, "_detect_lock_and_files", lambda root, targets: ([], []))
    config = auto_detect_config(tmp_path)
    assert config is not None
    assert config.version_groups[0].lock_command == ["poetry", "lock"]
