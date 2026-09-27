"""Tests for RRT-VER-1 tier 2 config: ``format``, ``ci_format`` alias, ``post_policy``."""

from __future__ import annotations

from pathlib import Path

import pytest

from repo_release_tools.config import PinTarget, VersionTarget, load_config
from repo_release_tools.config.model import VALID_POST_POLICIES, VALID_TARGET_FORMATS

_BASE_PYPROJECT = """\
[project]
name = "example"
version = "1.0.0"

[tool.rrt]
release_branch = "release/v{{version}}"
lock_command = []
{extra}

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"
{target_extra}
"""


def _write(tmp_path: Path, *, extra: str = "", target_extra: str = "") -> None:
    (tmp_path / "pyproject.toml").write_text(
        _BASE_PYPROJECT.format(extra=extra, target_extra=target_extra), encoding="utf-8"
    )
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# VersionTarget.format
# ---------------------------------------------------------------------------


def test_version_target_format_defaults_to_none_and_resolves_to_python() -> None:
    target = VersionTarget(path=Path("pyproject.toml"), kind="pep621")
    target.validate()
    assert target.format is None
    assert target.resolved_format() == "python"


def test_version_target_format_explicit_wins() -> None:
    target = VersionTarget(path=Path("pyproject.toml"), kind="pep621", format="pep440")
    target.validate()
    assert target.resolved_format() == "pep440"


def test_version_target_format_gemspec_default_is_rubygems() -> None:
    target = VersionTarget(path=Path("x.gemspec"), kind="gemspec")
    target.validate()
    assert target.resolved_format() == "rubygems"


@pytest.mark.parametrize("fmt", sorted(VALID_TARGET_FORMATS))
def test_version_target_format_accepts_every_valid_format(fmt: str) -> None:
    VersionTarget(path=Path("x"), kind="pep621", format=fmt).validate()


def test_version_target_format_rejects_invalid_value() -> None:
    target = VersionTarget(path=Path("x"), kind="pep621", format="bogus")
    with pytest.raises(ValueError, match="format must be one of"):
        target.validate()


def test_version_target_format_rejects_non_string() -> None:
    target = VersionTarget.__new__(VersionTarget)
    object.__setattr__(target, "path", Path("x.toml"))
    object.__setattr__(target, "kind", "pep621")
    object.__setattr__(target, "pattern", None)
    object.__setattr__(target, "section", None)
    object.__setattr__(target, "field", None)
    object.__setattr__(target, "ci_format", None)
    object.__setattr__(target, "format", 123)
    with pytest.raises(ValueError, match="format must be a string"):
        target.validate()


def test_version_target_ci_format_alias_resolves_when_format_unset() -> None:
    pep440_target = VersionTarget(path=Path("x"), kind="pep621", ci_format="pep440")
    pep440_target.validate()
    assert pep440_target.resolved_format() == "pep440"

    semver_pre_target = VersionTarget(path=Path("x"), kind="package_json", ci_format="semver_pre")
    semver_pre_target.validate()
    assert semver_pre_target.resolved_format() == "semver"


def test_version_target_format_and_matching_ci_format_alias_is_fine() -> None:
    target = VersionTarget(path=Path("x"), kind="pep621", ci_format="pep440", format="pep440")
    target.validate()  # no raise
    assert target.resolved_format() == "pep440"


def test_version_target_format_conflicts_with_ci_format_alias() -> None:
    # ci_format="semver_pre" implies format="semver", which conflicts with format="pep440".
    target = VersionTarget(
        path=Path("x"), kind="package_json", ci_format="semver_pre", format="pep440"
    )
    with pytest.raises(ValueError, match="conflicts with ci_format"):
        target.validate()


# ---------------------------------------------------------------------------
# PinTarget.format
# ---------------------------------------------------------------------------


def test_pin_target_format_defaults_to_semver() -> None:
    pin = PinTarget(path=Path("README.md"), pattern=r"(v)(\d+\.\d+\.\d+)()")
    pin.validate()
    assert pin.resolved_format() == "semver"


def test_pin_target_format_explicit_wins() -> None:
    pin = PinTarget(path=Path("README.md"), pattern=r"(v)(\d+\.\d+\.\d+)()", format="rubygems")
    pin.validate()
    assert pin.resolved_format() == "rubygems"


def test_pin_target_format_rejects_invalid_value() -> None:
    pin = PinTarget(path=Path("README.md"), pattern=r"(v)(\d+\.\d+\.\d+)()", format="bogus")
    with pytest.raises(ValueError, match="format must be one of"):
        pin.validate()


def test_pin_targets_format_parsed_from_toml(tmp_path: Path) -> None:
    _write(
        tmp_path,
        extra=(
            "[[tool.rrt.pin_targets]]\n"
            'path = "README.md"\n'
            r"pattern = '(v)(\d+\.\d+\.\d+)()'"
            "\n"
            'format = "rubygems"\n'
        ),
    )
    (tmp_path / "README.md").write_text("v1.0.0\n", encoding="utf-8")

    config = load_config(tmp_path)

    pin = config.resolve_group().pin_targets[0]
    assert pin.format == "rubygems"
    assert pin.resolved_format() == "rubygems"


# ---------------------------------------------------------------------------
# format parsed from TOML on version_targets
# ---------------------------------------------------------------------------


def test_version_target_format_parsed_from_toml(tmp_path: Path) -> None:
    _write(tmp_path, target_extra='format = "pep440"\n')

    config = load_config(tmp_path)

    target = config.resolve_group().version_targets[0]
    assert target.format == "pep440"
    assert target.resolved_format() == "pep440"


def test_version_target_format_invalid_value_is_config_error(tmp_path: Path) -> None:
    _write(tmp_path, target_extra='format = "bogus"\n')

    with pytest.raises(ValueError, match="format must be one of"):
        load_config(tmp_path)


def test_version_target_format_ci_format_conflict_is_config_error(tmp_path: Path) -> None:
    _write(tmp_path, target_extra='ci_format = "semver_pre"\nformat = "pep440"\n')

    with pytest.raises(ValueError, match="conflicts with ci_format"):
        load_config(tmp_path)


# ---------------------------------------------------------------------------
# post_policy: global default, per-group override, validation
# ---------------------------------------------------------------------------


def test_post_policy_defaults_to_refuse(tmp_path: Path) -> None:
    _write(tmp_path)

    config = load_config(tmp_path)

    assert config.resolve_group().post_policy == "refuse"
    assert config.post_policy == "refuse"


def test_post_policy_global_value_applies_to_group(tmp_path: Path) -> None:
    _write(tmp_path, extra='post_policy = "patch"\n')

    config = load_config(tmp_path)

    assert config.resolve_group().post_policy == "patch"
    assert config.post_policy == "patch"


def test_post_policy_per_group_override_wins(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """\
[project]
name = "example"
version = "1.0.0"

[tool.rrt]
release_branch = "release/v{version}"
lock_command = []
post_policy = "patch"

[[tool.rrt.version_groups]]
name = "default"
post_policy = "refuse"

[[tool.rrt.version_groups.version_targets]]
path = "pyproject.toml"
kind = "pep621"
""",
        encoding="utf-8",
    )
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")

    config = load_config(tmp_path)

    assert config.resolve_group("default").post_policy == "refuse"


@pytest.mark.parametrize("policy", sorted(VALID_POST_POLICIES))
def test_post_policy_accepts_every_valid_value(tmp_path: Path, policy: str) -> None:
    _write(tmp_path, extra=f'post_policy = "{policy}"\n')
    config = load_config(tmp_path)
    assert config.resolve_group().post_policy == policy


def test_post_policy_invalid_value_is_config_error(tmp_path: Path) -> None:
    _write(tmp_path, extra='post_policy = "bogus"\n')

    with pytest.raises(ValueError, match="post_policy must be one of"):
        load_config(tmp_path)


def test_post_policy_non_string_is_config_error(tmp_path: Path) -> None:
    _write(tmp_path, extra="post_policy = 1\n")

    with pytest.raises(ValueError, match="post_policy must be a string"):
        load_config(tmp_path)
