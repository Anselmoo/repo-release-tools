from __future__ import annotations

from pathlib import Path

import pytest

from repo_release_tools.config import (
    DEFAULT_CHANGELOG,
    DEFAULT_CHANGELOG_WORKFLOW,
    EolConfig,
    EolOverride,
    VersionTarget,
    autodetect_config,
    find_changelog_file,
    find_config_file,
    format_autodetected_config_notice,
    load_config,
    load_extra_branch_types,
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
    from repo_release_tools.config import load_config_from_path

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
    from repo_release_tools.config import load_config_from_path

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
    from repo_release_tools.config import load_config_from_path

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
    from repo_release_tools.config import load_config_from_path

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
    from repo_release_tools.config import load_config_from_path

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
    from repo_release_tools.config import load_config_from_path

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


def test_load_config_eol_overrides_not_list(tmp_path: Path) -> None:
    """Non-list overrides raises ValueError."""
    _write_eol_cfg(tmp_path, '\n[tool.rrt.eol]\noverrides = "bad"\n')
    with pytest.raises(ValueError, match="overrides must be an array"):
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
