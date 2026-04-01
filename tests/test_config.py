from __future__ import annotations

from pathlib import Path

import pytest

from repo_release_tools.config import VersionTarget, find_config_file, load_config


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
    (tmp_path / ".rrt.toml").write_text(_RRT_CONFIG.replace("release/v{version}", "ignored"), encoding="utf-8")

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
        match=r"Missing \[tool\.rrt\] configuration in supported config files: "
        r"pyproject\.toml, \.rrt\.toml, \.config/rrt\.toml",
    ):
        load_config(tmp_path)


def test_find_config_file_reports_supported_locations(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="pyproject.toml, .rrt.toml, .config/rrt.toml"):
        find_config_file(tmp_path)


@pytest.mark.parametrize(
    ("target", "message"),
    [
        (
            VersionTarget(path=Path("x.toml"), kind="pep621", pattern=r"(version = \")([^\"]+)(\")"),
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
        (VersionTarget(path=Path("x.toml"), section="project"), "section and field must be configured together"),
        (VersionTarget(path=Path("x.toml"), field="version"), "section and field must be configured together"),
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
