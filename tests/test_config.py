from __future__ import annotations

from pathlib import Path

import pytest

from repo_release_tools.config import (
    DEFAULT_CHANGELOG,
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


def test_pin_target_validate_rejects_invalid_regex(tmp_path: Path) -> None:
    """validate() raises on invalid regex."""
    from repo_release_tools.config import PinTarget

    pin = PinTarget(path=tmp_path / "file.md", pattern=r"(unclosed[")
    with pytest.raises(ValueError, match="not a valid regex"):
        pin.validate()
