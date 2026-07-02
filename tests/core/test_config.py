from __future__ import annotations

from pathlib import Path
from typing import cast
from unittest.mock import patch

import pytest
from _pytest.monkeypatch import MonkeyPatch

from repo_release_tools.config import (
    DEFAULT_CHANGELOG,
    DEFAULT_CHANGELOG_WORKFLOW,
    DocsConfig,
    EolConfig,
    EolOverride,
    MapConfig,
    MissingRrtConfigError,
    RrtConfig,
    SharedBlock,
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
    find_repo_root,
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
        _RRT_CONFIG.replace("release/v{version}", "ignored"),
        encoding="utf-8",
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
                path=Path("x.toml"),
                kind="pep621",
                pattern=r"(version = \")([^\"]+)(\")",
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
    target: VersionTarget,
    message: str,
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


def test_load_config_accepts_generated_assets(tmp_path: Path) -> None:
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]

[[tool.rrt.generated_assets]]
path = "docs/assets/banner.png"
command = ["python", "-m", "repo_release_tools.assets.banner", "docs/assets/banner.png", "unicode"]

[[tool.rrt.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )

    config = load_config(tmp_path)

    assert len(config.generated_assets) == 1
    assert config.generated_assets[0].path == tmp_path / "docs/assets/banner.png"
    assert config.generated_assets[0].command[0] == "python"


def test_load_config_rejects_invalid_generated_assets(tmp_path: Path) -> None:
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]

[[tool.rrt.generated_assets]]
path = ""
command = []

[[tool.rrt.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="generated_assets"):
        load_config(tmp_path)


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
    tmp_path: Path,
    body: str,
    message: str,
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
    tmp_path: Path,
    target_body: str,
    message: str,
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
        ValueError,
        match=r"Missing \[\[tool\.rrt\.version_targets\]\] configuration",
    ):
        load_config(tmp_path)


def test_load_config_rejects_non_table_target_entry(tmp_path: Path) -> None:
    (tmp_path / ".rrt.toml").write_text(
        '[tool.rrt]\nversion_targets = ["package.json"]\n',
        encoding="utf-8",
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
        '[project]\nname = "example"\nversion = "1.2.3"\n',
        encoding="utf-8",
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
        '{"name": "example", "version": "3.0.0"}',
        encoding="utf-8",
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
        '{"name": "example", "version": "3.0.0"}',
        encoding="utf-8",
    )
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")

    config = load_config(tmp_path)

    group = config.resolve_group()
    assert group.lock_command == ["npm", "install"]
    assert group.generated_files == [tmp_path / "package-lock.json"]


def test_auto_detect_package_json_prefers_pnpm_over_npm(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"name": "example", "version": "3.0.0"}',
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")

    config = load_config(tmp_path)

    group = config.resolve_group()
    assert group.lock_command == ["pnpm", "install"]
    assert group.generated_files == [tmp_path / "pnpm-lock.yaml"]


def test_auto_detect_package_json_with_yarn_lockfile(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"name": "example", "version": "3.0.0"}',
        encoding="utf-8",
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
        '{"name": "example", "version": "1.0.0"}',
        encoding="utf-8",
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
        '{"name": "example", "version": "1.0.0"}',
        encoding="utf-8",
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
        '[project]\nname = "example"\nversion = "1.0.0"\n',
        encoding="utf-8",
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


def test_load_config_parses_global_pin_targets_with_glob_path(tmp_path: Path) -> None:
    """Glob pin target paths expand to one PinTarget per matched file."""
    first = tmp_path / ".github" / "skills" / "a" / "one.md"
    second = tmp_path / ".github" / "skills" / "b" / "two.md"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    first.write_text("rev: v0.1.0\n", encoding="utf-8")
    second.write_text("rev: v0.1.0\n", encoding="utf-8")

    cfg_file = tmp_path / "pyproject.toml"
    cfg_file.write_text(
        """[tool.rrt]

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[[tool.rrt.pin_targets]]
path = ".github/skills/**/*.md"
pattern = '(rev: v)(\\d+\\.\\d+\\.\\d+)()'

[project]
name = "example"
version = "0.1.0"
""",
        encoding="utf-8",
    )

    config = load_config_from_path(tmp_path, cfg_file)

    assert len(config.global_pin_targets) == 2
    assert {pin.path for pin in config.global_pin_targets} == {first, second}


def test_load_config_rejects_glob_pin_target_without_matches(tmp_path: Path) -> None:
    """Glob pin target paths must match at least one file."""
    cfg_file = tmp_path / "pyproject.toml"
    cfg_file.write_text(
        """[tool.rrt]

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[[tool.rrt.pin_targets]]
path = ".github/skills/**/*.md"
pattern = '(rev: v)(\\d+\\.\\d+\\.\\d+)()'

[project]
name = "example"
version = "0.1.0"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="matched no files"):
        load_config_from_path(tmp_path, cfg_file)


def test_load_config_rejects_glob_matching_outside_root(tmp_path: Path) -> None:
    """Glob pin target matches that resolve outside the repo root are rejected."""
    repo = tmp_path / "repo"
    repo.mkdir()

    outside = tmp_path / "outside"
    outside.mkdir()
    outside_file = outside / "bad.md"
    outside_file.write_text("rev: v0.1.0\n", encoding="utf-8")

    inside_dir = repo / ".github" / "skills" / "a"
    inside_dir.mkdir(parents=True)
    link = inside_dir / "link.md"
    # Create a symlink inside the repo that points to a file outside the repo.
    link.symlink_to(outside_file)

    cfg_file = repo / "pyproject.toml"
    cfg_file.write_text(
        """[tool.rrt]

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[[tool.rrt.pin_targets]]
path = ".github/skills/**/*.md"
pattern = '(rev: v)(\\d+\\.\\d+\\.\\d+)()'

[project]
name = "example"
version = "0.1.0"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="outside repository root"):
        load_config_from_path(repo, cfg_file)


def test_load_config_rejects_absolute_pin_path(tmp_path: Path) -> None:
    """Absolute pin target paths are rejected as they may write outside repo."""
    outside = tmp_path / "outside"
    outside.mkdir()
    abs_target = outside / "file.md"
    abs_target.write_text("rev: v0.1.0\n", encoding="utf-8")

    cfg_file = tmp_path / "pyproject.toml"
    cfg_file.write_text(
        f"""[tool.rrt]

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[[tool.rrt.pin_targets]]
path = "{abs_target.resolve()!s}"
pattern = '(rev: v)(\\d+\\.\\d+\\.\\d+)()'

[project]
name = "example"
version = "0.1.0"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must be a relative path"):
        load_config_from_path(tmp_path, cfg_file)


def test_load_config_handles_resolve_oserror(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """If Path.resolve() raises OSError, loader falls back to the original paths.

    This exercises the except branches that guard against resolve() raising on
    unusual filesystems or permission errors.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    readme = repo / "README.md"
    readme.write_text("rev: v0.1.0\n", encoding="utf-8")

    cfg_file = repo / "pyproject.toml"
    cfg_file.write_text(
        """[tool.rrt]

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[[tool.rrt.pin_targets]]
path = "README.md"
pattern = '(rev: v)(\\d+\\.\\d+\\.\\d+)()'

[project]
name = "example"
version = "0.1.0"
""",
        encoding="utf-8",
    )

    def _raise_oserror(self: Path) -> Path:
        raise OSError("boom")

    # Monkeypatch Path.resolve to raise OSError so the except branches run.
    monkeypatch.setattr("pathlib.Path.resolve", _raise_oserror, raising=True)

    config = load_config_from_path(repo, cfg_file)
    assert len(config.global_pin_targets) == 1
    assert config.global_pin_targets[0].path == readme


def test_load_config_rejects_relative_path_escaping_root(tmp_path: Path) -> None:
    """A relative pin_targets.path that escapes the repository root is rejected."""
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_file = outside / "bad.md"
    outside_file.write_text("rev: v0.1.0\n", encoding="utf-8")

    cfg_file = repo / "pyproject.toml"
    cfg_file.write_text(
        """[tool.rrt]

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[[tool.rrt.pin_targets]]
path = "../outside/bad.md"
pattern = '(rev: v)(\\d+\\.\\d+\\.\\d+)()'

[project]
name = "example"
version = "0.1.0"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="outside repository root"):
        load_config_from_path(repo, cfg_file)


def test_load_config_glob_resolve_oserror(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """When resolving matched glob paths raises OSError, loader falls back.

    This specifically exercises the except block that assigns
    ``matched_resolved = matched_path`` when ``matched_path.resolve()`` fails.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    first = repo / ".github" / "skills" / "a" / "one.md"
    second = repo / ".github" / "skills" / "b" / "two.md"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    first.write_text("rev: v0.1.0\n", encoding="utf-8")
    second.write_text("rev: v0.1.0\n", encoding="utf-8")

    cfg_file = repo / "pyproject.toml"
    cfg_file.write_text(
        """[tool.rrt]

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[[tool.rrt.pin_targets]]
path = ".github/skills/**/*.md"
pattern = '(rev: v)(\\d+\\.\\d+\\.\\d+)()'

[project]
name = "example"
version = "0.1.0"
""",
        encoding="utf-8",
    )

    def _raise_oserror(self: Path) -> Path:
        raise OSError("boom")

    monkeypatch.setattr("pathlib.Path.resolve", _raise_oserror, raising=True)

    config = load_config_from_path(repo, cfg_file)
    assert {pin.path for pin in config.global_pin_targets} == {first, second}


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
    assert cfg.docs.src_dir == "."
    assert cfg.docs.stubs == ()


def test_load_config_docs_full(tmp_path: Path) -> None:
    """[tool.rrt.docs] with all fields populated."""
    _write_docs_cfg(
        tmp_path,
        '\n[tool.rrt.docs]\nmirror_src_tree = true\ndocs_dir = "documentation"\n'
        'src_dir = "src/mypackage"\nstubs = ["commands/bump", "commands/init"]\n'
        'source_repo_url = "https://github.com/Anselmoo/repo-release-tools"\n'
        'source_ref = "main"\n'
        'source_url_template = "{repo_url}/blob/{ref}/{path}#L{line}"\n',
    )
    cfg = load_config(tmp_path)
    assert cfg.docs is not None
    assert cfg.docs.mirror_src_tree is True
    assert cfg.docs.docs_dir == "documentation"
    assert cfg.docs.src_dir == "src/mypackage"
    assert cfg.docs.stubs == ("commands/bump", "commands/init")
    assert cfg.docs.source_repo_url == "https://github.com/Anselmoo/repo-release-tools"
    assert cfg.docs.source_ref == "main"
    assert cfg.docs.source_url_template == "{repo_url}/blob/{ref}/{path}#L{line}"


def test_load_config_docs_optional_string_rejects_non_string(tmp_path: Path) -> None:
    """Optional docs strings must be actual strings."""
    _write_docs_cfg(
        tmp_path,
        "\n[tool.rrt.docs]\nsource_repo_url = 123\n",
    )

    with pytest.raises(ValueError, match="must be a string"):
        load_config(tmp_path)


def test_load_config_docs_optional_string_rejects_empty_string(tmp_path: Path) -> None:
    """Optional docs strings must not be empty."""
    _write_docs_cfg(
        tmp_path,
        '\n[tool.rrt.docs]\nsource_ref = ""\n',
    )

    with pytest.raises(ValueError, match="must not be empty"):
        load_config(tmp_path)


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
# _load_shared_blocks
# ---------------------------------------------------------------------------


def test_load_config_docs_shared_blocks_absent(tmp_path: Path) -> None:
    """No shared_blocks key → empty tuple."""
    _write_docs_cfg(tmp_path, "\n[tool.rrt.docs]\n")
    cfg = load_config(tmp_path)
    assert cfg.docs is not None
    assert cfg.docs.shared_blocks == ()


def test_load_config_docs_shared_blocks_with_template(tmp_path: Path) -> None:
    """Legacy template-based shared blocks are supported with deprecation warning."""
    tpl = tmp_path / "scripts" / "templates" / "doc-footer.md"
    tpl.parent.mkdir(parents=True)
    tpl.write_text("---\n[Docs]({repo_url})\n", encoding="utf-8")
    _write_docs_cfg(
        tmp_path,
        "\n[tool.rrt.docs]\n\n[[tool.rrt.docs.shared_blocks]]\n"
        'anchor_id = "doc-footer"\ntemplate = "scripts/templates/doc-footer.md"\n'
        'targets = ["docs/**/*.md"]\n',
    )
    with pytest.warns(DeprecationWarning, match="template is deprecated"):
        cfg = load_config(tmp_path)
    assert cfg.docs is not None
    assert cfg.docs.shared_blocks[0].content.startswith("---")


def test_load_config_docs_shared_blocks_template_unreadable(tmp_path: Path) -> None:
    """Unreadable legacy template paths raise a descriptive ValueError."""
    _write_docs_cfg(
        tmp_path,
        "\n[tool.rrt.docs]\n\n[[tool.rrt.docs.shared_blocks]]\n"
        'anchor_id = "doc-footer"\ntemplate = "scripts/templates/missing-footer.md"\n'
        'targets = ["docs/**/*.md"]\n',
    )
    with pytest.warns(DeprecationWarning, match="template is deprecated"):
        with pytest.raises(ValueError, match=r"shared_blocks\[0\]\.template unreadable:"):
            load_config(tmp_path)


def test_load_config_docs_shared_blocks_with_inline_content(tmp_path: Path) -> None:
    """A valid shared_block with rich inline content is parsed correctly."""
    _write_docs_cfg(
        tmp_path,
        "\n[tool.rrt.docs]\n\n[[tool.rrt.docs.shared_blocks]]\n"
        'anchor_id = "doc-footer"\ncontent = """---\n[Docs]({repo_url})\n<iframe src="https://example.test/embed"></iframe>\n"""\n'
        'targets = ["docs/**/*.md"]\n',
    )
    cfg = load_config(tmp_path)
    assert cfg.docs is not None
    block = cfg.docs.shared_blocks[0]
    assert block.content.startswith("---")
    assert "[Docs]({repo_url})" in block.content
    assert '<iframe src="https://example.test/embed"></iframe>' in block.content


def test_load_config_docs_shared_blocks_with_position_and_whitespace_context(
    tmp_path: Path,
) -> None:
    """Shared block placement and whitespace context are parsed correctly."""
    _write_docs_cfg(
        tmp_path,
        "\n[tool.rrt.docs]\n\n[[tool.rrt.docs.shared_blocks]]\n"
        'anchor_id = "doc-footer"\nposition = "append"\nbefore_blank_lines = 1\nafter_blank_lines = 2\n'
        'content = "footer"\ntargets = ["docs/**/*.md"]\n',
    )
    cfg = load_config(tmp_path)
    assert cfg.docs is not None
    block = cfg.docs.shared_blocks[0]
    assert block.position == "append"
    assert block.before_blank_lines == 1
    assert block.after_blank_lines == 2


def test_load_config_docs_shared_blocks_rejects_invalid_position(tmp_path: Path) -> None:
    """Shared blocks reject unsupported position values."""
    _write_docs_cfg(
        tmp_path,
        "\n[tool.rrt.docs]\n\n[[tool.rrt.docs.shared_blocks]]\n"
        'anchor_id = "doc-footer"\nposition = "middle"\ncontent = "footer"\ntargets = ["docs/**/*.md"]\n',
    )
    with pytest.raises(ValueError, match="position must be 'prepend' or 'append'"):
        load_config(tmp_path)


def test_load_config_docs_shared_blocks_rejects_negative_before_blank_lines(
    tmp_path: Path,
) -> None:
    """Shared blocks reject negative leading blank-line counts."""
    _write_docs_cfg(
        tmp_path,
        "\n[tool.rrt.docs]\n\n[[tool.rrt.docs.shared_blocks]]\n"
        'anchor_id = "doc-footer"\nbefore_blank_lines = -1\ncontent = "footer"\ntargets = ["docs/**/*.md"]\n',
    )
    with pytest.raises(ValueError, match="before_blank_lines must be a non-negative integer"):
        load_config(tmp_path)


def test_load_config_docs_shared_blocks_rejects_negative_after_blank_lines(
    tmp_path: Path,
) -> None:
    """Shared blocks reject negative trailing blank-line counts."""
    _write_docs_cfg(
        tmp_path,
        "\n[tool.rrt.docs]\n\n[[tool.rrt.docs.shared_blocks]]\n"
        'anchor_id = "doc-footer"\nafter_blank_lines = -1\ncontent = "footer"\ntargets = ["docs/**/*.md"]\n',
    )
    with pytest.raises(ValueError, match="after_blank_lines must be a non-negative integer"):
        load_config(tmp_path)


def test_load_config_docs_shared_blocks_not_array(tmp_path: Path) -> None:
    """shared_blocks must be an array."""
    _write_docs_cfg(
        tmp_path,
        '\n[tool.rrt.docs]\nshared_blocks = "bad"\n',
    )
    with pytest.raises(ValueError, match="must be an array of tables"):
        load_config(tmp_path)


def test_load_config_docs_shared_blocks_entry_not_table(tmp_path: Path) -> None:
    """Each shared_blocks entry must be a table."""
    _write_docs_cfg(
        tmp_path,
        '\n[tool.rrt.docs]\nshared_blocks = ["bad"]\n',
    )
    with pytest.raises(ValueError, match=r"shared_blocks\[0\] must be a table"):
        load_config(tmp_path)


def test_load_config_docs_shared_blocks_missing_anchor_id(tmp_path: Path) -> None:
    """anchor_id must be present and non-empty."""
    _write_docs_cfg(
        tmp_path,
        "\n[tool.rrt.docs]\n\n[[tool.rrt.docs.shared_blocks]]\n"
        'template = "scripts/templates/doc-footer.md"\ntargets = ["docs/**/*.md"]\n',
    )
    with pytest.raises(ValueError, match="anchor_id must be a non-empty string"):
        load_config(tmp_path)


def test_load_config_docs_shared_blocks_template_not_string(tmp_path: Path) -> None:
    """The legacy template key must still be a non-empty string when provided."""
    _write_docs_cfg(
        tmp_path,
        "\n[tool.rrt.docs]\n\n[[tool.rrt.docs.shared_blocks]]\n"
        'anchor_id = "doc-footer"\ntemplate = 123\ntargets = ["docs/**/*.md"]\n',
    )
    with pytest.raises(
        ValueError,
        match=r"shared_blocks\[0\]\.template must be a non-empty string",
    ):
        load_config(tmp_path)


def test_load_config_docs_shared_blocks_content_not_string(tmp_path: Path) -> None:
    """shared_blocks content values must be strings when provided."""
    _write_docs_cfg(
        tmp_path,
        "\n[tool.rrt.docs]\n\n[[tool.rrt.docs.shared_blocks]]\n"
        'anchor_id = "doc-footer"\ncontent = 123\ntargets = ["docs/**/*.md"]\n',
    )
    with pytest.raises(ValueError, match=r"shared_blocks\[0\]\.content must be a string"):
        load_config(tmp_path)


def test_load_config_docs_shared_blocks_both_template_and_content(tmp_path: Path) -> None:
    """Inline content wins when both legacy template and content are set."""
    tpl = tmp_path / "t.md"
    tpl.write_text("legacy footer\n", encoding="utf-8")
    _write_docs_cfg(
        tmp_path,
        "\n[tool.rrt.docs]\n\n[[tool.rrt.docs.shared_blocks]]\n"
        'anchor_id = "doc-footer"\ntemplate = "t.md"\ncontent = "x"\n'
        'targets = ["docs/**/*.md"]\n',
    )
    with pytest.warns(DeprecationWarning, match="template is deprecated"):
        cfg = load_config(tmp_path)
    assert cfg.docs is not None
    assert cfg.docs.shared_blocks[0].content == "x"


def test_load_config_docs_shared_blocks_no_template_or_content(tmp_path: Path) -> None:
    """Shared blocks must define inline content."""
    _write_docs_cfg(
        tmp_path,
        "\n[tool.rrt.docs]\n\n[[tool.rrt.docs.shared_blocks]]\n"
        'anchor_id = "doc-footer"\ntargets = ["docs/**/*.md"]\n',
    )
    with pytest.raises(ValueError, match=r"shared_blocks\[0\] must define 'content'"):
        load_config(tmp_path)


def test_load_config_docs_shared_blocks_empty_targets(tmp_path: Path) -> None:
    """An empty targets list raises ValueError."""
    _write_docs_cfg(
        tmp_path,
        "\n[tool.rrt.docs]\n\n[[tool.rrt.docs.shared_blocks]]\n"
        'anchor_id = "doc-footer"\ncontent = "x"\ntargets = []\n',
    )
    with pytest.raises(ValueError, match="at least one target glob"):
        load_config(tmp_path)


def test_load_config_docs_shared_blocks_targets_not_list(tmp_path: Path) -> None:
    """targets must be a list of strings."""
    _write_docs_cfg(
        tmp_path,
        "\n[tool.rrt.docs]\n\n[[tool.rrt.docs.shared_blocks]]\n"
        'anchor_id = "doc-footer"\ncontent = "x"\ntargets = 123\n',
    )
    with pytest.raises(ValueError, match="targets must be a list of strings"):
        load_config(tmp_path)


def test_shared_block_validate_rejects_empty_anchor_id() -> None:
    """SharedBlock.validate raises ValueError for an empty anchor_id."""
    block = SharedBlock(anchor_id="", content="footer", targets=("docs/**/*.md",))
    with pytest.raises(ValueError, match="anchor_id must be a non-empty string"):
        block.validate()


def test_shared_block_validate_rejects_missing_content() -> None:
    """SharedBlock.validate raises ValueError when content is missing."""
    block = SharedBlock(
        anchor_id="doc-footer", content=cast("str", None), targets=("docs/**/*.md",)
    )
    with pytest.raises(ValueError, match=r"must define 'content'"):
        block.validate()


def test_shared_block_validate_rejects_invalid_position() -> None:
    """SharedBlock.validate raises ValueError for an unsupported position."""
    block = SharedBlock(
        anchor_id="doc-footer",
        content="footer",
        position="middle",
        targets=("docs/**/*.md",),
    )
    with pytest.raises(ValueError, match="position must be 'prepend' or 'append'"):
        block.validate()


def test_shared_block_validate_rejects_negative_blank_lines() -> None:
    """SharedBlock.validate raises ValueError for negative blank-line counts."""
    block = SharedBlock(
        anchor_id="doc-footer",
        content="footer",
        before_blank_lines=-1,
        after_blank_lines=-2,
        targets=("docs/**/*.md",),
    )
    with pytest.raises(ValueError, match="before_blank_lines must be >= 0"):
        block.validate()


def test_shared_block_validate_rejects_negative_trailing_blank_lines() -> None:
    """SharedBlock.validate raises ValueError for negative trailing blank lines."""
    block = SharedBlock(
        anchor_id="doc-footer",
        content="footer",
        after_blank_lines=-1,
        targets=("docs/**/*.md",),
    )
    with pytest.raises(ValueError, match="after_blank_lines must be >= 0"):
        block.validate()


# ---------------------------------------------------------------------------
# _load_map_config — [tool.rrt.docs.map]
# ---------------------------------------------------------------------------


def test_load_config_map_section_absent(tmp_path: Path) -> None:
    """When [tool.rrt.docs.map] is absent, docs.map is None."""
    _write_docs_cfg(tmp_path, "\n[tool.rrt.docs]\n")
    cfg = load_config(tmp_path)
    assert cfg.docs is not None
    assert cfg.docs.map is None


def test_load_config_map_defaults(tmp_path: Path) -> None:
    """Empty [tool.rrt.docs.map] table uses all defaults."""
    _write_docs_cfg(tmp_path, "\n[tool.rrt.docs]\n\n[tool.rrt.docs.map]\n")
    cfg = load_config(tmp_path)
    assert cfg.docs is not None
    assert isinstance(cfg.docs.map, MapConfig)
    assert cfg.docs.map.root == "src"
    assert cfg.docs.map.file_name == "README.md"
    assert cfg.docs.map.on_conflict == "merge"
    assert cfg.docs.map.tree_max_depth == 2
    assert cfg.docs.map.prompts == ()
    assert cfg.docs.map.purpose == {}
    assert cfg.docs.map.include == ()
    assert cfg.docs.map.exclude == ()
    assert cfg.docs.map.lock_file == ".rrt/docs_map.lock.toml"


def test_load_config_map_lock_file_override(tmp_path: Path) -> None:
    """A custom lock_file path overrides the default."""
    _write_docs_cfg(
        tmp_path,
        '\n[tool.rrt.docs.map]\nlock_file = ".rrt/custom_map.lock.toml"\n',
    )
    cfg = load_config(tmp_path)
    assert cfg.docs is not None and cfg.docs.map is not None
    assert cfg.docs.map.lock_file == ".rrt/custom_map.lock.toml"


def test_load_config_map_lock_file_empty_string(tmp_path: Path) -> None:
    """lock_file rejects an empty string."""
    _write_docs_cfg(tmp_path, '\n[tool.rrt.docs.map]\nlock_file = ""\n')
    with pytest.raises(ValueError, match="lock_file must be a non-empty string"):
        load_config(tmp_path)


def test_map_config_validate_rejects_blank_lock_file() -> None:
    """MapConfig.validate raises when lock_file is whitespace-only."""
    with pytest.raises(ValueError, match="lock_file must be a non-empty string"):
        MapConfig(lock_file="   ").validate()


def test_load_config_map_full(tmp_path: Path) -> None:
    """[tool.rrt.docs.map] with all fields populated."""
    _write_docs_cfg(
        tmp_path,
        '\n[tool.rrt.docs]\n\n[tool.rrt.docs.map]\nroot = "lib"\n'
        'file_name = "PURPOSE.md"\non_conflict = "skip"\ntree_max_depth = 4\n'
        'prompts = ["self-check", "auto-update"]\n'
        'include = ["lib/**/*.py"]\nexclude = ["lib/vendor/**"]\n'
        '\n[tool.rrt.docs.map.purpose]\n"lib/commands" = "Command handlers."\n',
    )
    cfg = load_config(tmp_path)
    assert cfg.docs is not None
    assert cfg.docs.map is not None
    assert cfg.docs.map.root == "lib"
    assert cfg.docs.map.file_name == "PURPOSE.md"
    assert cfg.docs.map.on_conflict == "skip"
    assert cfg.docs.map.tree_max_depth == 4
    assert cfg.docs.map.prompts == ("self-check", "auto-update")
    assert cfg.docs.map.include == ("lib/**/*.py",)
    assert cfg.docs.map.exclude == ("lib/vendor/**",)
    assert cfg.docs.map.purpose == {"lib/commands": "Command handlers."}


def test_load_config_map_not_a_table(tmp_path: Path) -> None:
    """[tool.rrt.docs.map] must be a table."""
    _write_docs_cfg(tmp_path, '\n[tool.rrt.docs]\nmap = "oops"\n')
    with pytest.raises(ValueError, match="tool.rrt.docs.map must be a table"):
        load_config(tmp_path)


def test_load_config_map_root_empty(tmp_path: Path) -> None:
    """root must be a non-empty string."""
    _write_docs_cfg(tmp_path, '\n[tool.rrt.docs.map]\nroot = ""\n')
    with pytest.raises(ValueError, match="map.root must be a non-empty string"):
        load_config(tmp_path)


def test_load_config_map_file_name_not_string(tmp_path: Path) -> None:
    """file_name must be a non-empty string."""
    _write_docs_cfg(tmp_path, "\n[tool.rrt.docs.map]\nfile_name = 123\n")
    with pytest.raises(ValueError, match="map.file_name must be a non-empty string"):
        load_config(tmp_path)


def test_load_config_map_on_conflict_invalid(tmp_path: Path) -> None:
    """on_conflict must be one of merge/skip/error."""
    _write_docs_cfg(tmp_path, '\n[tool.rrt.docs.map]\non_conflict = "overwrite"\n')
    with pytest.raises(ValueError, match="on_conflict must be one of"):
        load_config(tmp_path)


def test_load_config_map_tree_max_depth_not_int(tmp_path: Path) -> None:
    """tree_max_depth must be an integer."""
    _write_docs_cfg(tmp_path, '\n[tool.rrt.docs.map]\ntree_max_depth = "2"\n')
    with pytest.raises(ValueError, match="tree_max_depth must be an integer"):
        load_config(tmp_path)


def test_load_config_map_tree_max_depth_rejects_bool(tmp_path: Path) -> None:
    """tree_max_depth must reject booleans (which are int subclasses in Python)."""
    _write_docs_cfg(tmp_path, "\n[tool.rrt.docs.map]\ntree_max_depth = true\n")
    with pytest.raises(ValueError, match="tree_max_depth must be an integer"):
        load_config(tmp_path)


def test_load_config_map_tree_max_depth_negative(tmp_path: Path) -> None:
    """tree_max_depth must be non-negative."""
    _write_docs_cfg(tmp_path, "\n[tool.rrt.docs.map]\ntree_max_depth = -1\n")
    with pytest.raises(ValueError, match="tree_max_depth must be >= 0"):
        load_config(tmp_path)


def test_load_config_map_prompts_invalid_entry(tmp_path: Path) -> None:
    """Unknown prompt names are rejected."""
    _write_docs_cfg(tmp_path, '\n[tool.rrt.docs.map]\nprompts = ["mystery-block"]\n')
    with pytest.raises(ValueError, match="prompts contains unsupported entries"):
        load_config(tmp_path)


def test_load_config_map_prompts_not_a_list(tmp_path: Path) -> None:
    """prompts must be a list of strings."""
    _write_docs_cfg(tmp_path, '\n[tool.rrt.docs.map]\nprompts = "self-check"\n')
    with pytest.raises(ValueError, match="prompts must be a list of strings"):
        load_config(tmp_path)


def test_load_config_map_purpose_not_a_table(tmp_path: Path) -> None:
    """purpose must be a table."""
    _write_docs_cfg(tmp_path, '\n[tool.rrt.docs.map]\npurpose = "nope"\n')
    with pytest.raises(ValueError, match="purpose must be a table"):
        load_config(tmp_path)


def test_load_config_map_purpose_non_string_value(tmp_path: Path) -> None:
    """purpose values must be strings."""
    _write_docs_cfg(tmp_path, '\n[tool.rrt.docs.map.purpose]\n"src/commands" = 42\n')
    with pytest.raises(ValueError, match="purpose keys and values must be strings"):
        load_config(tmp_path)


def test_load_config_map_include_not_a_list(tmp_path: Path) -> None:
    """include must be a list of strings."""
    _write_docs_cfg(tmp_path, '\n[tool.rrt.docs.map]\ninclude = "src/**/*.py"\n')
    with pytest.raises(ValueError, match="include must be a list of strings"):
        load_config(tmp_path)


def test_load_config_map_exclude_not_a_list(tmp_path: Path) -> None:
    """exclude must be a list of strings."""
    _write_docs_cfg(tmp_path, '\n[tool.rrt.docs.map]\nexclude = "vendor"\n')
    with pytest.raises(ValueError, match="exclude must be a list of strings"):
        load_config(tmp_path)


def test_map_config_validate_direct() -> None:
    """MapConfig.validate raises on enum / range violations when constructed directly."""
    with pytest.raises(ValueError, match="on_conflict must be one of"):
        MapConfig(on_conflict="bogus").validate()
    with pytest.raises(ValueError, match="prompts contains unsupported entries"):
        MapConfig(prompts=("not-a-real-prompt",)).validate()
    with pytest.raises(ValueError, match="tree_max_depth must be >= 0"):
        MapConfig(tree_max_depth=-5).validate()


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
        '[project]\nname = "x"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    config = load_or_autodetect_config(tmp_path)
    assert config.autodetected is True


def test_load_or_autodetect_config_raises_missing_rrt_when_no_autodetect(tmp_path: Path) -> None:
    """Re-raises the missing-rrt ValueError when autodetect also returns None."""
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="Missing rrt configuration"):
        load_or_autodetect_config(tmp_path)


def test_find_repo_root_walks_to_parent_config(tmp_path: Path) -> None:
    """find_repo_root returns the nearest ancestor with rrt config files."""
    repo_root = tmp_path / "repo"
    nested = repo_root / "docs" / "guide"
    nested.mkdir(parents=True)
    (repo_root / ".rrt.toml").write_text(_RRT_CONFIG, encoding="utf-8")

    result = find_repo_root(nested)

    assert result == repo_root


def test_find_repo_root_prefers_nearest_ancestor(tmp_path: Path) -> None:
    """find_repo_root stops at the closest matching ancestor."""
    outer = tmp_path / "outer"
    inner = outer / "inner"
    nested = inner / "subdir"
    nested.mkdir(parents=True)
    (outer / ".rrt.toml").write_text(_RRT_CONFIG, encoding="utf-8")
    (inner / "pyproject.toml").write_text(
        '[project]\nname = "inner"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )

    result = find_repo_root(nested)

    assert result == inner


def test_find_repo_root_detects_package_json(tmp_path: Path) -> None:
    """find_repo_root recognizes JS projects via package.json."""
    repo_root = tmp_path / "repo"
    nested = repo_root / "src" / "lib"
    nested.mkdir(parents=True)
    (repo_root / "package.json").write_text(
        '{"name":"example","version":"1.0.0"}',
        encoding="utf-8",
    )

    result = find_repo_root(nested)

    assert result == repo_root


def test_find_repo_root_detects_cargo_toml(tmp_path: Path) -> None:
    """find_repo_root recognizes Rust projects via Cargo.toml."""
    repo_root = tmp_path / "repo"
    nested = repo_root / "crates" / "app"
    nested.mkdir(parents=True)
    (repo_root / "Cargo.toml").write_text(
        '[package]\nname = "example"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )

    result = find_repo_root(nested)

    assert result == repo_root


def test_find_repo_root_uses_autodetected_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """find_repo_root returns the first ancestor whose autodetect_config succeeds."""
    repo_root = tmp_path / "repo"
    nested = repo_root / "nested" / "child"
    nested.mkdir(parents=True)

    def _fake_autodetect(candidate: Path) -> object | None:
        return object() if candidate == repo_root else None

    monkeypatch.setattr("repo_release_tools.config.autodetect_config", _fake_autodetect)

    result = find_repo_root(nested)

    assert result == repo_root


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
        '[workspace.package]\nname = "ws"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    targets = _autodetect_version_targets(tmp_path)
    assert any(t.section == "workspace.package" for t in targets)


def test_autodetect_version_targets_detects_python_version_files(tmp_path: Path) -> None:
    """__version__ files are discovered as secondary targets for pep621 projects."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1.0.0"\n',
        encoding="utf-8",
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
        '[project]\nname = "x"\nversion = "1.0.0"\n',
        encoding="utf-8",
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
        '[project]\nname = "x"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    result = recommend_init_config_for_go(tmp_path)
    assert "[tool.rrt]" in result


def test_recommend_init_section_for_pyproject_with_autodetect(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    result = recommend_init_section_for_pyproject(tmp_path)
    assert "[tool.rrt]" in result


def test_recommend_init_section_for_cargo_with_autodetect(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "x"\nversion = "1.0.0"\n',
        encoding="utf-8",
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
        '[package]\nname = "x"\nversion = "1.0.0"\n',
        encoding="utf-8",
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
        '[project]\nname = "x"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text('{"name": "x", "version": "1.0.0"}', encoding="utf-8")
    result = recommend_init_config(tmp_path)
    assert "version_source" in result


def test_recommended_lock_settings_poetry_ecosystem(tmp_path: Path) -> None:
    """recommend_init_config returns poetry lock command for poetry projects."""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.poetry]\nname = "x"\nversion = "0.1.0"\n',
        encoding="utf-8",
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


def test_validate_kind_pattern_requires_pattern_field() -> None:
    target = VersionTarget(path=Path("x.toml"), kind="pattern")
    with pytest.raises(ValueError, match="kind='pattern' requires a 'pattern' field"):
        target.validate()


def test_validate_kind_pattern_rejects_section_field() -> None:
    target = VersionTarget(
        path=Path("x.toml"), kind="pattern", pattern=r"(\d+)", section="s", field="f"
    )
    with pytest.raises(ValueError, match="cannot be combined with section"):
        target.validate()


def test_validate_kind_pattern_rejects_zero_groups() -> None:
    target = VersionTarget(path=Path("x.toml"), kind="pattern", pattern=r"\d+\.\d+\.\d+")
    with pytest.raises(ValueError, match="exactly 1 capture group"):
        target.validate()


def test_validate_kind_pattern_rejects_two_groups() -> None:
    target = VersionTarget(path=Path("x.toml"), kind="pattern", pattern=r"(\d+)\.(\d+)")
    with pytest.raises(ValueError, match="exactly 1 capture group"):
        target.validate()


def test_validate_kind_pattern_rejects_three_groups() -> None:
    target = VersionTarget(path=Path("x.toml"), kind="pattern", pattern=r"(prefix)(\d+)(suffix)")
    with pytest.raises(ValueError, match="exactly 1 capture group"):
        target.validate()


def test_validate_kind_pattern_valid() -> None:
    target = VersionTarget(path=Path("x.toml"), kind="pattern", pattern=r'"ruff==(\d+\.\d+\.\d+)"')
    target.validate()  # must not raise


def test_validate_kind_pattern_invalid_regex_raises() -> None:
    target = VersionTarget(path=Path("x.toml"), kind="pattern", pattern=r"(unclosed")
    with pytest.raises(ValueError, match="not a valid regex"):
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
        root=Path(),
        config_file=Path(".rrt.toml"),
        version_groups=[group],
        default_group_name=None,
    )
    assert config.resolve_group() is group


def test_is_missing_tool_rrt_error_with_direct_exception() -> None:
    """is_missing_tool_rrt_error returns True for MissingRrtConfigError instances."""
    from repo_release_tools.config import is_missing_tool_rrt_error

    exc = MissingRrtConfigError("Missing [tool.rrt]")
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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Line 662: py_file already present in targets is skipped via continue."""
    import repo_release_tools.config as _config_mod

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "x"\nversion = "1.0.0"\n', encoding="utf-8")
    # Return the pep621 path from _find_python_version_files so it duplicates the existing target.
    monkeypatch.setattr(_config_mod, "_find_python_version_files", lambda root: [pyproject])
    targets = _autodetect_version_targets(tmp_path)
    python_version_entries = [t for t in targets if t.kind == "python_version"]
    assert not python_version_entries


def test_load_or_autodetect_file_not_found_with_autodetect_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Line 463: load_or_autodetect_config returns autodetected when load_config raises FileNotFoundError."""
    import repo_release_tools.config as _config_mod

    fake_cfg = object()

    def raise_file_not_found(root: Path) -> object:
        raise FileNotFoundError("no files")

    monkeypatch.setattr(
        _config_mod,
        "load_config",
        raise_file_not_found,
    )
    monkeypatch.setattr(_config_mod, "autodetect_config", lambda root: fake_cfg)
    result = load_or_autodetect_config(tmp_path)
    assert result is fake_cfg


def test_load_or_autodetect_missing_rrt_with_autodetect_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Line 470: load_or_autodetect_config returns autodetected when load_config raises missing-rrt ValueError."""
    import repo_release_tools.config as _config_mod
    from repo_release_tools.config import MissingRrtConfigError

    fake_cfg = object()

    def raise_missing_rrt(root: Path) -> object:
        raise MissingRrtConfigError("Missing rrt")

    monkeypatch.setattr(
        _config_mod,
        "load_config",
        raise_missing_rrt,
    )
    monkeypatch.setattr(_config_mod, "autodetect_config", lambda root: fake_cfg)
    result = load_or_autodetect_config(tmp_path)
    assert result is fake_cfg


def test_recommended_lock_settings_unknown_ecosystem(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Line 888: _recommended_lock_settings returns ([], []) for a single unknown ecosystem."""
    import repo_release_tools.config as _config_mod

    monkeypatch.setattr(_config_mod, "_target_ecosystem", lambda t: "unknown-eco")
    target = VersionTarget(path=tmp_path / "VERSION", kind="custom")
    result = _recommended_lock_settings(tmp_path, [target])
    assert result == ([], [])


def test_load_config_from_path_rejects_non_dict_raw(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Line 932: load_config_from_path raises ValueError when raw config is not a dict."""
    import repo_release_tools.config as _config_mod

    cfg_file = tmp_path / ".rrt.toml"
    cfg_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(_config_mod, "_load_raw_config", lambda path: ["not", "a", "dict"])
    with pytest.raises(ValueError, match="must be a table/object"):
        load_config_from_path(tmp_path, cfg_file)


def test_auto_detect_config_poetry_falls_back_to_default_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lines 1302-1303: auto_detect_config sets poetry lock defaults when _detect_lock_and_files returns empty."""
    import repo_release_tools.config as _config_mod

    (tmp_path / "pyproject.toml").write_text(
        '[tool.poetry]\nname = "x"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    monkeypatch.setattr(_config_mod, "_detect_lock_and_files", lambda root, targets: ([], []))
    config = auto_detect_config(tmp_path)
    assert config is not None
    assert config.version_groups[0].lock_command == ["poetry", "lock"]


def test_docs_config_validate_invalid_badge_style() -> None:
    """DocsConfig.validate should raise for unknown badge_style."""
    from dataclasses import replace as dc_replace

    from repo_release_tools.config import DocsConfig

    bad = dc_replace(DocsConfig(), badge_style="unknown")
    with pytest.raises(ValueError, match="badge_style"):
        bad.validate()


def test_load_badge_style_invalid(tmp_path: Path) -> None:
    """_load_badge_style raises for unsupported badge_style values."""
    from repo_release_tools.config.docs_config import _load_badge_style

    with pytest.raises(ValueError, match="badge_style"):
        _load_badge_style({"badge_style": "nope"})


def test_load_badge_style_valid() -> None:
    """_load_badge_style returns the value for valid badge styles."""
    from repo_release_tools.config.docs_config import _load_badge_style

    assert _load_badge_style({"badge_style": "shields"}) == "shields"


def test_load_badge_assets_dir_invalid(tmp_path: Path) -> None:
    """_load_badge_assets_dir raises when value is not a non-empty string."""
    from repo_release_tools.config.docs_config import _load_badge_assets_dir

    with pytest.raises(ValueError, match="badge_assets_dir"):
        _load_badge_assets_dir({"badge_assets_dir": 123})


def test_load_badge_assets_dir_valid() -> None:
    """_load_badge_assets_dir returns stripped path for valid string."""
    from repo_release_tools.config.docs_config import _load_badge_assets_dir

    assert _load_badge_assets_dir({"badge_assets_dir": " assets/icons "}) == "assets/icons"


def test_load_optional_docs_int_invalid() -> None:
    """_load_optional_docs_int raises when provided a non-integer."""
    from repo_release_tools.config.docs_config import _load_optional_docs_int

    with pytest.raises(ValueError, match="must be an integer"):
        _load_optional_docs_int({"suggest_min_chars": "oops"}, "suggest_min_chars")


def test_load_docs_suggest_roots_invalid() -> None:
    """_load_docs_suggest_roots raises when roots are not all strings."""
    from repo_release_tools.config.docs_config import _load_docs_suggest_roots

    with pytest.raises(ValueError, match="suggest_roots"):
        _load_docs_suggest_roots({"suggest_roots": ["src", 1]})


def test_load_docs_suggest_exempt_invalid() -> None:
    """_load_docs_suggest_exempt raises when exempt entries are not all strings."""
    from repo_release_tools.config.docs_config import _load_docs_suggest_exempt

    with pytest.raises(ValueError, match="suggest_exempt"):
        _load_docs_suggest_exempt({"suggest_exempt": ["skip.py", 1]})


def test_load_source_link_badge_invalid(tmp_path: Path) -> None:
    """_load_source_link_badge raises when value is not a boolean."""
    from repo_release_tools.config.docs_config import _load_source_link_badge

    with pytest.raises(ValueError, match="source_link_badge"):
        _load_source_link_badge({"source_link_badge": "yes"})


def test_load_source_link_badge_valid() -> None:
    """_load_source_link_badge returns True for valid bool."""
    from repo_release_tools.config.docs_config import _load_source_link_badge

    assert _load_source_link_badge({"source_link_badge": True}) is True


def test_load_badge_variant_invalid() -> None:
    """_load_badge_variant raises for unsupported values."""
    from repo_release_tools.config.docs_config import _load_badge_variant

    with pytest.raises(ValueError, match="badge_variant"):
        _load_badge_variant({"badge_variant": "neon"})


def test_load_badge_variant_valid() -> None:
    """_load_badge_variant returns the value for valid variants."""
    from repo_release_tools.config.docs_config import _load_badge_variant

    assert _load_badge_variant({"badge_variant": "dark"}) == "dark"


def test_docs_config_validate_invalid_badge_variant() -> None:
    """DocsConfig.validate should raise for unknown badge_variant."""
    from dataclasses import replace as dc_replace

    from repo_release_tools.config import DocsConfig

    bad = dc_replace(DocsConfig(), badge_variant="neon")
    with pytest.raises(ValueError, match="badge_variant"):
        bad.validate()


# ---------------------------------------------------------------------------
# _load_extra_commit_types error paths
# ---------------------------------------------------------------------------


def test_load_extra_commit_types_non_list_raises() -> None:
    from repo_release_tools.config.core import _load_extra_commit_types

    with pytest.raises(ValueError, match="list of strings"):
        _load_extra_commit_types("not-a-list")


def test_load_extra_commit_types_non_string_item_raises() -> None:
    from repo_release_tools.config.core import _load_extra_commit_types

    with pytest.raises(ValueError, match="list of strings"):
        _load_extra_commit_types([1, 2, 3])


def test_load_extra_commit_types_invalid_identifier_raises() -> None:
    from repo_release_tools.config.core import _load_extra_commit_types

    with pytest.raises(ValueError, match="valid identifier"):
        _load_extra_commit_types(["1invalid"])


def test_load_extra_commit_types_empty_string_raises() -> None:
    from repo_release_tools.config.core import _load_extra_commit_types

    with pytest.raises(ValueError, match="valid identifier"):
        _load_extra_commit_types([""])


def test_load_extra_commit_types_valid() -> None:
    from repo_release_tools.config.core import _load_extra_commit_types

    result = _load_extra_commit_types(["hotfix", "spike"])
    assert result == ("hotfix", "spike")


# ---------------------------------------------------------------------------
# _load_extra_section_map error paths
# ---------------------------------------------------------------------------


def test_load_extra_section_map_non_dict_raises() -> None:
    from repo_release_tools.config.core import _load_extra_section_map

    with pytest.raises(ValueError, match="table mapping"):
        _load_extra_section_map("not-a-dict")


def test_load_extra_section_map_non_string_key_raises() -> None:
    from repo_release_tools.config.core import _load_extra_section_map

    with pytest.raises(ValueError, match="keys and values must be strings"):
        _load_extra_section_map({1: "Added"})


def test_load_extra_section_map_valid() -> None:
    from repo_release_tools.config.core import _load_extra_section_map

    result = _load_extra_section_map({"hotfix": "Fixed"})
    assert result == {"hotfix": "Fixed"}


# ---------------------------------------------------------------------------
# _load_pin_target_missing error paths
# ---------------------------------------------------------------------------


def test_load_pin_target_missing_non_string_raises() -> None:
    from repo_release_tools.config.core import _load_pin_target_missing

    with pytest.raises(ValueError, match="must be a string"):
        _load_pin_target_missing(42)


def test_load_pin_target_missing_invalid_value_raises() -> None:
    from repo_release_tools.config.core import _load_pin_target_missing

    with pytest.raises(ValueError, match="must be one of"):
        _load_pin_target_missing("ignore")


def test_load_pin_target_missing_none_returns_error() -> None:
    from repo_release_tools.config.core import _load_pin_target_missing

    assert _load_pin_target_missing(None) == "error"


def test_load_pin_target_missing_valid() -> None:
    from repo_release_tools.config.core import _load_pin_target_missing

    assert _load_pin_target_missing("warn") == "warn"


def test_artifact_target_validate_empty_path() -> None:
    from repo_release_tools.config.model import ArtifactTarget

    with pytest.raises(ValueError, match="non-empty"):
        ArtifactTarget(path="").validate()


def test_artifact_target_validate_absolute_path() -> None:
    from repo_release_tools.config.model import ArtifactTarget

    with pytest.raises(ValueError, match="relative"):
        ArtifactTarget(path="/abs/path/*.svg").validate()


def test_load_artifact_targets_not_a_list() -> None:
    from repo_release_tools.config.core import _load_artifact_targets

    with pytest.raises(ValueError, match="array"):
        _load_artifact_targets("not-a-list")


def test_load_artifact_targets_item_not_dict() -> None:
    from repo_release_tools.config.core import _load_artifact_targets

    with pytest.raises(ValueError, match="table"):
        _load_artifact_targets(["not-a-dict"])


def test_load_artifact_targets_missing_path() -> None:
    from repo_release_tools.config.core import _load_artifact_targets

    with pytest.raises(ValueError, match="non-empty 'path'"):
        _load_artifact_targets([{"description": "no path"}])


def test_artifact_target_validate_bad_command() -> None:
    from repo_release_tools.config.model import ArtifactTarget

    with pytest.raises(ValueError, match="command"):
        ArtifactTarget(path="docs/*.md", command=["", "bad"]).validate()


def test_artifact_target_validate_absolute_input() -> None:
    from repo_release_tools.config.model import ArtifactTarget

    with pytest.raises(ValueError, match="relative"):
        ArtifactTarget(path="docs/*.md", inputs=["/abs/input.py"]).validate()


def test_artifact_target_validate_empty_input_string() -> None:
    from repo_release_tools.config.model import ArtifactTarget

    with pytest.raises(ValueError, match="non-empty"):
        ArtifactTarget(path="docs/*.md", inputs=[""]).validate()


def test_artifact_target_defaults_are_empty() -> None:
    from repo_release_tools.config.model import ArtifactTarget

    t = ArtifactTarget(path="docs/*.md")
    assert t.command == []
    assert t.inputs == []


def test_load_artifact_targets_parses_command_and_inputs() -> None:
    from repo_release_tools.config.core import _load_artifact_targets

    result = _load_artifact_targets(
        [{"path": "docs/*.md", "command": ["uv", "run", "gen.py"], "inputs": ["src/**/*.py"]}]
    )
    assert len(result) == 1
    assert result[0].command == ["uv", "run", "gen.py"]
    assert result[0].inputs == ["src/**/*.py"]


def test_load_artifact_targets_bad_command_not_list() -> None:
    from repo_release_tools.config.core import _load_artifact_targets

    with pytest.raises(ValueError, match="command"):
        _load_artifact_targets([{"path": "docs/*.md", "command": "not-a-list"}])


def test_load_artifact_targets_bad_inputs_not_list() -> None:
    from repo_release_tools.config.core import _load_artifact_targets

    with pytest.raises(ValueError, match="inputs"):
        _load_artifact_targets([{"path": "docs/*.md", "inputs": "not-a-list"}])


def test_load_artifact_targets_bad_inputs_empty_string() -> None:
    from repo_release_tools.config.core import _load_artifact_targets

    with pytest.raises(ValueError, match="inputs"):
        _load_artifact_targets([{"path": "docs/*.md", "inputs": [""]}])


# ---------------------------------------------------------------------------
# _load_command_groups / _load_topic_pages / _load_title_overrides
# ---------------------------------------------------------------------------


def test_load_command_groups_returns_empty_when_absent() -> None:
    from repo_release_tools.config.docs_config import _load_command_groups

    assert _load_command_groups({}) == ()


def test_load_command_groups_parses_valid_entry() -> None:
    from repo_release_tools.config.docs_config import _load_command_groups

    d: dict[str, object] = {
        "command_groups": [
            {"slug": "version-release", "display": "Version & Release", "commands": ["bump", "tag"]}
        ]
    }
    result = _load_command_groups(d)
    assert len(result) == 1
    assert result[0].slug == "version-release"
    assert result[0].display == "Version & Release"
    assert result[0].commands == ("bump", "tag")


def test_load_command_groups_not_a_list_raises() -> None:
    from repo_release_tools.config.docs_config import _load_command_groups

    with pytest.raises(ValueError, match="array of tables"):
        _load_command_groups({"command_groups": "not-a-list"})


def test_load_command_groups_item_not_dict_raises() -> None:
    from repo_release_tools.config.docs_config import _load_command_groups

    with pytest.raises(ValueError, match=r"command_groups\[0\] must be a table"):
        _load_command_groups({"command_groups": ["not-a-dict"]})


def test_load_command_groups_missing_slug_raises() -> None:
    from repo_release_tools.config.docs_config import _load_command_groups

    with pytest.raises(ValueError, match="slug must be a non-empty string"):
        _load_command_groups({"command_groups": [{"display": "X", "commands": ["a"]}]})


def test_load_command_groups_missing_display_raises() -> None:
    from repo_release_tools.config.docs_config import _load_command_groups

    with pytest.raises(ValueError, match="display must be a non-empty string"):
        _load_command_groups({"command_groups": [{"slug": "x", "commands": ["a"]}]})


def test_load_command_groups_commands_not_list_of_strings_raises() -> None:
    from repo_release_tools.config.docs_config import _load_command_groups

    with pytest.raises(ValueError, match="list of strings"):
        _load_command_groups({"command_groups": [{"slug": "x", "display": "X", "commands": 42}]})


def test_load_topic_pages_returns_empty_when_absent() -> None:
    from repo_release_tools.config.docs_config import _load_topic_pages

    assert _load_topic_pages({}) == ()


def test_load_topic_pages_parses_valid_entry() -> None:
    from repo_release_tools.config.docs_config import _load_topic_pages

    d: dict[str, object] = {
        "topic_pages": [{"slug": "branch", "output": "docs/commands/branch.md"}]
    }
    result = _load_topic_pages(d)
    assert len(result) == 1
    assert result[0].slug == "branch"
    assert result[0].output == "docs/commands/branch.md"


def test_load_topic_pages_not_a_list_raises() -> None:
    from repo_release_tools.config.docs_config import _load_topic_pages

    with pytest.raises(ValueError, match="array of tables"):
        _load_topic_pages({"topic_pages": "not-a-list"})


def test_load_topic_pages_item_not_dict_raises() -> None:
    from repo_release_tools.config.docs_config import _load_topic_pages

    with pytest.raises(ValueError, match=r"topic_pages\[0\] must be a table"):
        _load_topic_pages({"topic_pages": ["not-a-dict"]})


def test_load_topic_pages_missing_slug_raises() -> None:
    from repo_release_tools.config.docs_config import _load_topic_pages

    with pytest.raises(ValueError, match="slug must be a non-empty string"):
        _load_topic_pages({"topic_pages": [{"output": "docs/x.md"}]})


def test_load_topic_pages_missing_output_raises() -> None:
    from repo_release_tools.config.docs_config import _load_topic_pages

    with pytest.raises(ValueError, match="output must be a non-empty string"):
        _load_topic_pages({"topic_pages": [{"slug": "x"}]})


def test_load_title_overrides_returns_empty_when_absent() -> None:
    from repo_release_tools.config.docs_config import _load_title_overrides

    assert _load_title_overrides({}) == {}


def test_load_title_overrides_parses_valid_dict() -> None:
    from repo_release_tools.config.docs_config import _load_title_overrides

    result = _load_title_overrides({"title_overrides": {"rrt-cli": "rrt CLI"}})
    assert result == {"rrt-cli": "rrt CLI"}


def test_load_title_overrides_not_a_dict_raises() -> None:
    from repo_release_tools.config.docs_config import _load_title_overrides

    with pytest.raises(ValueError, match="must be a table"):
        _load_title_overrides({"title_overrides": ["not", "a", "dict"]})


def test_load_title_overrides_non_string_value_raises() -> None:
    from repo_release_tools.config.docs_config import _load_title_overrides

    with pytest.raises(ValueError, match="keys and values must be strings"):
        _load_title_overrides({"title_overrides": {"key": 123}})


# ---------------------------------------------------------------------------
# [tool.rrt.upstream] config
# ---------------------------------------------------------------------------


def test_upstream_config_parsed(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.rrt]\nrelease_branch = "release/v{version}"\n'
        '[[tool.rrt.version_targets]]\npath = "pyproject.toml"\nkind = "pep621"\n'
        '[tool.rrt.upstream]\npackage = "ruff"\nprovider = "pypi"\n',
        encoding="utf-8",
    )
    cfg = load_or_autodetect_config(tmp_path)
    grp = cfg.version_groups[0]
    assert grp.upstream_package == "ruff"
    assert grp.upstream_provider == "pypi"


def test_upstream_config_defaults_when_omitted(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.rrt]\nrelease_branch = "release/v{version}"\n'
        '[[tool.rrt.version_targets]]\npath = "pyproject.toml"\nkind = "pep621"\n',
        encoding="utf-8",
    )
    cfg = load_or_autodetect_config(tmp_path)
    grp = cfg.version_groups[0]
    assert grp.upstream_package is None
    assert grp.upstream_provider == "pypi"


def test_upstream_config_npm_provider_accepted(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.rrt]\nrelease_branch = "release/v{version}"\n'
        '[[tool.rrt.version_targets]]\npath = "pyproject.toml"\nkind = "pep621"\n'
        '[tool.rrt.upstream]\npackage = "lodash"\nprovider = "npm"\n',
        encoding="utf-8",
    )
    cfg = load_or_autodetect_config(tmp_path)
    grp = cfg.version_groups[0]
    assert grp.upstream_package == "lodash"
    assert grp.upstream_provider == "npm"


def test_upstream_config_rejects_invalid_provider(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.rrt]\nrelease_branch = "release/v{version}"\n'
        '[[tool.rrt.version_targets]]\npath = "pyproject.toml"\nkind = "pep621"\n'
        '[tool.rrt.upstream]\npackage = "ruff"\nprovider = "bogus"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"bogus.*must be one of|must be one of.*bogus"):
        load_or_autodetect_config(tmp_path)


def test_upstream_must_be_table(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.rrt]\nrelease_branch = "release/v{version}"\n'
        'upstream = "not-a-table"\n'
        '[[tool.rrt.version_targets]]\npath = "pyproject.toml"\nkind = "pep621"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="upstream must be a table"):
        load_or_autodetect_config(tmp_path)


def test_upstream_package_must_be_string(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.rrt]\nrelease_branch = "release/v{version}"\n'
        '[[tool.rrt.version_targets]]\npath = "pyproject.toml"\nkind = "pep621"\n'
        "[tool.rrt.upstream]\npackage = 123\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="upstream.package must be a string"):
        load_or_autodetect_config(tmp_path)


def test_upstream_provider_must_be_string(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.rrt]\nrelease_branch = "release/v{version}"\n'
        '[[tool.rrt.version_targets]]\npath = "pyproject.toml"\nkind = "pep621"\n'
        "[tool.rrt.upstream]\nprovider = 123\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="upstream.provider must be a string"):
        load_or_autodetect_config(tmp_path)


def test_upstream_commit_message_parsed(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.rrt]\nrelease_branch = "release/v{version}"\n'
        '[[tool.rrt.version_targets]]\npath = "pyproject.toml"\nkind = "pep621"\n'
        '[tool.rrt.upstream]\npackage = "ruff"\ncommit_message = "rel {version}"\n',
        encoding="utf-8",
    )
    cfg = load_or_autodetect_config(tmp_path)
    grp = cfg.version_groups[0]
    assert grp.upstream_commit_message == "rel {version}"


def test_upstream_commit_message_default_when_omitted(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.rrt]\nrelease_branch = "release/v{version}"\n'
        '[[tool.rrt.version_targets]]\npath = "pyproject.toml"\nkind = "pep621"\n',
        encoding="utf-8",
    )
    cfg = load_or_autodetect_config(tmp_path)
    grp = cfg.version_groups[0]
    assert grp.upstream_commit_message == "Mirror: {version}"


def test_upstream_commit_message_must_be_string(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.rrt]\nrelease_branch = "release/v{version}"\n'
        '[[tool.rrt.version_targets]]\npath = "pyproject.toml"\nkind = "pep621"\n'
        "[tool.rrt.upstream]\ncommit_message = 123\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="commit_message must be a string"):
        load_or_autodetect_config(tmp_path)
