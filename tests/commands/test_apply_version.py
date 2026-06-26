"""Tests for the apply_version helper in commands/bump.py."""

from __future__ import annotations

from pathlib import Path

from repo_release_tools.commands.bump import apply_version
from repo_release_tools.config import PinTarget, RrtConfig, VersionGroup, VersionTarget

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PEP621_CONTENT = """\
[project]
name = "example"
version = "0.5.0"
"""

_PIN_CONTENT = """\
# some config file
uses: example@v0.5.0
"""


def _make_version_target(tmp_path: Path, filename: str = "pyproject.toml") -> VersionTarget:
    path = tmp_path / filename
    path.write_text(_PEP621_CONTENT, encoding="utf-8")
    return VersionTarget(path=path, kind="pep621")


def _make_pin_target(tmp_path: Path, filename: str = "ci.yml") -> PinTarget:
    path = tmp_path / filename
    path.write_text(_PIN_CONTENT, encoding="utf-8")
    return PinTarget(path=path, pattern=r"(example@v)(\d+\.\d+\.\d+)()")


def _make_config(
    tmp_path: Path,
    group: VersionGroup,
    *,
    global_pin_targets: list[PinTarget] | None = None,
    pin_target_missing: str = "error",
) -> RrtConfig:
    return RrtConfig(
        root=tmp_path,
        config_file=tmp_path / "pyproject.toml",
        version_groups=[group],
        default_group_name=group.name,
        global_pin_targets=global_pin_targets or [],
        pin_target_missing=pin_target_missing,
    )


def _make_group(
    tmp_path: Path,
    version_target: VersionTarget,
    pin_targets: list[PinTarget] | None = None,
) -> VersionGroup:
    return VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=tmp_path / "CHANGELOG.md",
        lock_command=[],
        generated_files=[],
        version_targets=[version_target],
        pin_targets=pin_targets or [],
    )


# ---------------------------------------------------------------------------
# Test 1: rewrites a pep621 version target and returns its path
# ---------------------------------------------------------------------------


def test_apply_version_updates_version_target_file(tmp_path: Path) -> None:
    """apply_version rewrites the pep621 target to the given version and returns its path."""
    version_target = _make_version_target(tmp_path)
    group = _make_group(tmp_path, version_target)
    config = _make_config(tmp_path, group)

    changed = apply_version(group, "0.6.0", config)

    # The version target path is returned.
    assert version_target.path in changed
    # The file was actually rewritten.
    content = version_target.path.read_text(encoding="utf-8")
    assert 'version = "0.6.0"' in content
    assert 'version = "0.5.0"' not in content


# ---------------------------------------------------------------------------
# Test 2: also rewrites a configured pin target and returns that path
# ---------------------------------------------------------------------------


def test_apply_version_updates_pin_target_file(tmp_path: Path) -> None:
    """apply_version rewrites a group pin target and includes its path in the result."""
    version_target = _make_version_target(tmp_path)
    pin_target = _make_pin_target(tmp_path)
    group = _make_group(tmp_path, version_target, pin_targets=[pin_target])
    config = _make_config(tmp_path, group)

    changed = apply_version(group, "0.6.0", config)

    assert pin_target.path in changed
    content = pin_target.path.read_text(encoding="utf-8")
    assert "example@v0.6.0" in content


def test_apply_version_updates_global_pin_target(tmp_path: Path) -> None:
    """apply_version also applies config.global_pin_targets."""
    version_target = _make_version_target(tmp_path)
    global_pin = _make_pin_target(tmp_path, "global_ci.yml")
    group = _make_group(tmp_path, version_target)
    config = _make_config(tmp_path, group, global_pin_targets=[global_pin])

    changed = apply_version(group, "0.6.0", config)

    assert global_pin.path in changed
    content = global_pin.path.read_text(encoding="utf-8")
    assert "example@v0.6.0" in content


# ---------------------------------------------------------------------------
# Test 3: dry_run=True writes nothing but returns the would-change paths
# ---------------------------------------------------------------------------


def test_apply_version_dry_run_does_not_write_files(tmp_path: Path) -> None:
    """apply_version with dry_run=True returns paths but does not modify any file."""
    version_target = _make_version_target(tmp_path)
    pin_target = _make_pin_target(tmp_path)
    group = _make_group(tmp_path, version_target, pin_targets=[pin_target])
    config = _make_config(tmp_path, group)

    original_version_content = version_target.path.read_text(encoding="utf-8")
    original_pin_content = pin_target.path.read_text(encoding="utf-8")

    changed = apply_version(group, "0.6.0", config, dry_run=True)

    # Paths are still returned (callers need them for dry-run staging output).
    assert version_target.path in changed
    assert pin_target.path in changed

    # Files must NOT have been modified.
    assert version_target.path.read_text(encoding="utf-8") == original_version_content
    assert pin_target.path.read_text(encoding="utf-8") == original_pin_content


# ---------------------------------------------------------------------------
# Test: duplicate pins are deduplicated in the returned list
# ---------------------------------------------------------------------------


def test_apply_version_deduplicates_pin_paths(tmp_path: Path) -> None:
    """When a pin path/pattern appears in both group.pin_targets and global_pin_targets, the path
    appears only once in the returned list."""
    version_target = _make_version_target(tmp_path)
    pin_target = _make_pin_target(tmp_path)
    # Same path+pattern duplicated across group and global.
    group = _make_group(tmp_path, version_target, pin_targets=[pin_target])
    config = _make_config(tmp_path, group, global_pin_targets=[pin_target])

    changed = apply_version(group, "0.6.0", config)

    # Path should appear only once.
    assert changed.count(pin_target.path) == 1


# ---------------------------------------------------------------------------
# Test: pin_target_missing="warn" does not raise for a non-matching pin
# ---------------------------------------------------------------------------


def test_apply_version_pin_target_missing_warn_does_not_raise(tmp_path: Path) -> None:
    """When pin_target_missing='warn', a non-matching pin file is skipped without error."""
    version_target = _make_version_target(tmp_path)
    # Pin file exists but the pattern will not match its content.
    pin_path = tmp_path / "no_match.yml"
    pin_path.write_text("# nothing here\n", encoding="utf-8")
    pin_target = PinTarget(path=pin_path, pattern=r"(example@v)(\d+\.\d+\.\d+)()")
    group = _make_group(tmp_path, version_target, pin_targets=[pin_target])
    config = _make_config(tmp_path, group, pin_target_missing="warn")

    # Should not raise.
    changed = apply_version(group, "0.6.0", config)

    # Version target still updated.
    assert version_target.path in changed


# ---------------------------------------------------------------------------
# Test: return type is list[Path]
# ---------------------------------------------------------------------------


def test_apply_version_returns_list_of_path(tmp_path: Path) -> None:
    """apply_version return value is a list of Path objects."""
    version_target = _make_version_target(tmp_path)
    group = _make_group(tmp_path, version_target)
    config = _make_config(tmp_path, group)

    changed = apply_version(group, "0.6.0", config)

    assert isinstance(changed, list)
    assert all(isinstance(p, Path) for p in changed)
