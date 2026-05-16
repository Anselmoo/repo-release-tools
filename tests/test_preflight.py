"""Tests for preflight validation helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from repo_release_tools.config import RrtConfig, VersionGroup, VersionTarget
from repo_release_tools.preflight import (
    PreflightError,
    check_config_consistent,
    check_version_targets_readable,
    check_working_tree_clean,
)


def _make_target(tmp_path: Path, version: str = "1.0.0") -> tuple[VersionTarget, VersionGroup]:
    f = tmp_path / "__init__.py"
    f.write_text(f'__version__ = "{version}"\n', encoding="utf-8")
    target = VersionTarget(path=f, kind="python_version")
    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=tmp_path / "CHANGELOG.md",
        lock_command=[],
        generated_files=[],
        version_targets=[target],
        pin_targets=[],
    )
    return target, group


def _make_config(tmp_path: Path, version: str = "1.0.0") -> RrtConfig:
    _, group = _make_target(tmp_path, version)
    return RrtConfig(
        root=tmp_path,
        config_file=tmp_path / "pyproject.toml",
        version_groups=[group],
        default_group_name="default",
    )


def test_check_working_tree_clean_raises_when_dirty(tmp_path: Path) -> None:
    with patch("repo_release_tools.preflight.git.working_tree_clean", return_value=False):
        with pytest.raises(PreflightError, match="Working tree has uncommitted changes"):
            check_working_tree_clean(tmp_path)


def test_check_working_tree_clean_passes_when_clean(tmp_path: Path) -> None:
    with patch("repo_release_tools.preflight.git.working_tree_clean", return_value=True):
        check_working_tree_clean(tmp_path)  # should not raise


def test_check_version_targets_readable_missing_file(tmp_path: Path) -> None:
    target = VersionTarget(path=tmp_path / "nonexistent.py", kind="python_version")
    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=tmp_path / "CHANGELOG.md",
        lock_command=[],
        generated_files=[],
        version_targets=[target],
        pin_targets=[],
    )
    with pytest.raises(PreflightError, match="does not exist"):
        check_version_targets_readable(group)


def test_check_version_targets_readable_unreadable_file(tmp_path: Path) -> None:
    f = tmp_path / "__init__.py"
    f.write_text("no version here\n", encoding="utf-8")
    target = VersionTarget(path=f, kind="python_version")
    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=tmp_path / "CHANGELOG.md",
        lock_command=[],
        generated_files=[],
        version_targets=[target],
        pin_targets=[],
    )
    with pytest.raises(PreflightError, match="pre-flight checks failed"):
        check_version_targets_readable(group)


def test_check_config_consistent_raises_when_no_groups(tmp_path: Path) -> None:
    config = RrtConfig(
        root=tmp_path,
        config_file=tmp_path / "pyproject.toml",
        version_groups=[],
        default_group_name="",
    )
    with pytest.raises(PreflightError, match="No version groups"):
        check_config_consistent(config)


def test_check_config_consistent_passes_with_groups(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    check_config_consistent(config)  # should not raise
