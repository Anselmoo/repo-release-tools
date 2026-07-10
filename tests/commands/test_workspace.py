"""Tests for the `rrt workspace bump` command."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import cast

import pytest

from repo_release_tools.commands.workspace import (
    _compute_new_version,
    _resolve_packages,
    _update_changelog_for_package,
    cmd_workspace_bump,
)
from repo_release_tools.config import RrtConfig, VersionGroup, VersionTarget
from repo_release_tools.version.calver import CalVersion
from repo_release_tools.version.semver import Version
from repo_release_tools.version.targets import VersionWriteEvent


def _make_pkg_config(pkg_path: Path, version: str = "1.0.0") -> RrtConfig:
    init_file = pkg_path / "src" / "pkg" / "__init__.py"
    init_file.parent.mkdir(parents=True, exist_ok=True)
    init_file.write_text(f'__version__ = "{version}"\n', encoding="utf-8")

    target = VersionTarget(path=init_file, kind="python_version")
    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=pkg_path / "CHANGELOG.md",
        lock_command=[],
        generated_files=[],
        version_targets=[target],
        pin_targets=[],
    )
    return RrtConfig(
        root=pkg_path,
        config_file=pkg_path / "pyproject.toml",
        version_groups=[group],
        default_group_name="default",
    )


def _write_changelog(path: Path, with_entries: bool = True) -> None:
    if with_entries:
        path.write_text(
            "# Changelog\n\n## [Unreleased]\n\n### Added\n- new feature\n\n## [1.0.0] - 2026-01-01\n- old\n",
            encoding="utf-8",
        )
    else:
        path.write_text("# Changelog\n\n## [1.0.0] - 2026-01-01\n- old\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------


def test_resolve_packages(tmp_path: Path) -> None:
    """Resolves comma-separated package names into absolute paths."""
    paths = _resolve_packages("api,sdk", tmp_path)
    assert paths == [tmp_path / "api", tmp_path / "sdk"]


def test_resolve_packages_with_spaces(tmp_path: Path) -> None:
    """Strips spaces around package names."""
    paths = _resolve_packages(" api , sdk ", tmp_path)
    assert paths == [tmp_path / "api", tmp_path / "sdk"]


def test_compute_new_version_minor() -> None:
    """minor bump increments the minor component."""
    current = Version.parse("1.2.3")
    new = _compute_new_version("minor", current)
    assert str(new) == "1.3.0"


def test_compute_new_version_explicit() -> None:
    """Explicit version string is accepted as-is."""
    current = Version.parse("1.0.0")
    new = _compute_new_version("2.0.0", current)
    assert str(new) == "2.0.0"


def test_compute_new_version_invalid_returns_none() -> None:
    """Returns None for unrecognisable bump values."""
    current = Version.parse("1.0.0")
    assert _compute_new_version("not-a-version", current) is None


# ---------------------------------------------------------------------------
# Integration tests for cmd_workspace_bump
# ---------------------------------------------------------------------------


def _args(
    bump: str = "minor",
    packages: str = "",
    dry_run: bool = False,
    no_changelog: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        bump=bump,
        packages=packages,
        dry_run=dry_run,
        no_changelog=no_changelog,
    )


def test_workspace_bump_missing_packages_arg(capsys: pytest.CaptureFixture[str]) -> None:
    """Returns 1 when --packages is empty."""
    rc = cmd_workspace_bump(_args(packages=""))
    assert rc == 1
    assert "--packages is required" in capsys.readouterr().err


def test_workspace_bump_nonexistent_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 when a package directory does not exist."""
    monkeypatch.chdir(tmp_path)
    rc = cmd_workspace_bump(_args(packages="does_not_exist"))
    assert rc == 1
    assert "not found" in capsys.readouterr().err


def test_workspace_bump_no_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 when a package has no rrt config."""
    monkeypatch.chdir(tmp_path)
    pkg = tmp_path / "api"
    pkg.mkdir()
    rc = cmd_workspace_bump(_args(packages="api"))
    assert rc == 1
    assert capsys.readouterr().err


def test_workspace_bump_invalid_bump_value(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 when the bump value is not a valid kind or version."""
    monkeypatch.chdir(tmp_path)
    pkg = tmp_path / "api"
    pkg.mkdir()
    conf = _make_pkg_config(pkg)
    monkeypatch.setattr(
        "repo_release_tools.commands.workspace.load_or_autodetect_config",
        lambda _: conf,
    )
    rc = cmd_workspace_bump(_args(bump="not-a-version", packages="api"))
    assert rc == 1
    assert "Invalid bump value" in capsys.readouterr().err


def test_workspace_bump_dry_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dry-run emits no-files-modified message and returns 0."""
    monkeypatch.chdir(tmp_path)
    pkg = tmp_path / "api"
    pkg.mkdir()
    conf = _make_pkg_config(pkg)
    monkeypatch.setattr(
        "repo_release_tools.commands.workspace.load_or_autodetect_config",
        lambda _: conf,
    )
    rc = cmd_workspace_bump(_args(packages="api", dry_run=True))
    assert rc == 0
    out = capsys.readouterr().out
    assert "no files were modified" in out


def test_workspace_bump_updates_version_targets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 0 and updates version targets in all listed packages."""
    monkeypatch.chdir(tmp_path)

    pkg_a = tmp_path / "api"
    pkg_a.mkdir()
    conf_a = _make_pkg_config(pkg_a, "1.0.0")

    pkg_b = tmp_path / "sdk"
    pkg_b.mkdir()
    conf_b = _make_pkg_config(pkg_b, "1.0.0")

    configs = {pkg_a: conf_a, pkg_b: conf_b}
    monkeypatch.setattr(
        "repo_release_tools.commands.workspace.load_or_autodetect_config",
        lambda path: configs[path],
    )

    rc = cmd_workspace_bump(_args(packages="api,sdk", no_changelog=True))

    assert rc == 0
    assert "1.1.0" in conf_a.version_groups[0].version_targets[0].path.read_text()
    assert "1.1.0" in conf_b.version_groups[0].version_targets[0].path.read_text()


def test_workspace_bump_uses_atomic_version_updates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Workspace bumps update version targets via the atomic helper."""
    monkeypatch.chdir(tmp_path)

    pkg = tmp_path / "api"
    pkg.mkdir()
    conf = _make_pkg_config(pkg, "1.0.0")
    calls: list[tuple[list[VersionTarget], str, bool]] = []

    def fake_replace_all_versions_atomic(
        targets: list[VersionTarget],
        new_version: str,
        *,
        dry_run: bool,
    ) -> list[VersionWriteEvent]:
        calls.append((targets, new_version, dry_run))
        return [
            VersionWriteEvent(path=t.path, new_version=new_version, dry_run=dry_run)
            for t in targets
        ]

    monkeypatch.setattr(
        "repo_release_tools.commands.workspace.load_or_autodetect_config",
        lambda _: conf,
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.workspace.replace_all_versions_atomic",
        fake_replace_all_versions_atomic,
    )

    rc = cmd_workspace_bump(_args(packages="api", no_changelog=True))

    assert rc == 0
    assert len(calls) == 1
    assert calls[0][1] == "1.1.0"
    assert calls[0][2] is False
    assert calls[0][0][0].path.name == "__init__.py"


def test_workspace_bump_promotes_unreleased_changelog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Promotes [Unreleased] to the new version in each changelog."""
    monkeypatch.chdir(tmp_path)
    pkg = tmp_path / "api"
    pkg.mkdir()
    conf = _make_pkg_config(pkg)
    _write_changelog(pkg / "CHANGELOG.md", with_entries=True)
    monkeypatch.setattr(
        "repo_release_tools.commands.workspace.load_or_autodetect_config",
        lambda _: conf,
    )

    rc = cmd_workspace_bump(_args(packages="api", no_changelog=False))

    assert rc == 0
    changelog_text = (pkg / "CHANGELOG.md").read_text()
    assert "[1.1.0]" in changelog_text


def test_workspace_bump_no_changelog_skips_changelog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--no-changelog leaves the changelog file untouched."""
    monkeypatch.chdir(tmp_path)
    pkg = tmp_path / "api"
    pkg.mkdir()
    conf = _make_pkg_config(pkg)
    _write_changelog(pkg / "CHANGELOG.md", with_entries=True)
    original = (pkg / "CHANGELOG.md").read_text()
    monkeypatch.setattr(
        "repo_release_tools.commands.workspace.load_or_autodetect_config",
        lambda _: conf,
    )

    rc = cmd_workspace_bump(_args(packages="api", no_changelog=True))

    assert rc == 0
    assert (pkg / "CHANGELOG.md").read_text() == original


def test_workspace_bump_runtime_error_returns_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """RuntimeError during config loading is surfaced and returns 1."""
    monkeypatch.chdir(tmp_path)
    pkg = tmp_path / "api"
    pkg.mkdir()
    monkeypatch.setattr(
        "repo_release_tools.commands.workspace.load_or_autodetect_config",
        lambda _: (_ for _ in ()).throw(RuntimeError("oops")),
    )
    rc = cmd_workspace_bump(_args(packages="api"))
    assert rc == 1
    assert "oops" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# _compute_new_version – calver paths (lines 84-87)
# ---------------------------------------------------------------------------


def test_compute_new_version_calver_from_calver() -> None:
    """calver bump on a valid CalVersion calls .bump() and returns a CalVersion."""
    current = cast(Version, CalVersion.parse("2026.05.01"))
    result = _compute_new_version("calver", current)
    assert isinstance(result, CalVersion)


def test_compute_new_version_calver_from_semver() -> None:
    """calver bump on a semver string falls back to CalVersion.today()."""
    current = Version.parse("1.0.0")
    result = _compute_new_version("calver", current)
    assert isinstance(result, CalVersion)


# ---------------------------------------------------------------------------
# _update_changelog_for_package – early-return and dry-run paths (117, 119, 124)
# ---------------------------------------------------------------------------


def test_update_changelog_no_unreleased_section(tmp_path: Path) -> None:
    """Returns early without modification when changelog has no [Unreleased] section."""
    pkg = tmp_path / "api"
    pkg.mkdir()
    conf = _make_pkg_config(pkg)
    cl = pkg / "CHANGELOG.md"
    cl.write_text("# Changelog\n\n## [1.0.0] - 2026-01-01\n- old\n", encoding="utf-8")
    original = cl.read_text()
    _update_changelog_for_package(conf, conf.resolve_group(), "1.1.0", dry_run=False)
    assert cl.read_text() == original


def test_update_changelog_empty_unreleased_entries(tmp_path: Path) -> None:
    """Returns early without modification when [Unreleased] section has no entries."""
    pkg = tmp_path / "api"
    pkg.mkdir()
    conf = _make_pkg_config(pkg)
    cl = pkg / "CHANGELOG.md"
    cl.write_text(
        "# Changelog\n\n## [Unreleased]\n\n## [1.0.0] - 2026-01-01\n- old\n",
        encoding="utf-8",
    )
    original = cl.read_text()
    _update_changelog_for_package(conf, conf.resolve_group(), "1.1.0", dry_run=False)
    assert cl.read_text() == original


def test_update_changelog_dry_run(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """dry_run=True emits a would-write message without touching the file."""
    pkg = tmp_path / "api"
    pkg.mkdir()
    conf = _make_pkg_config(pkg)
    _write_changelog(pkg / "CHANGELOG.md", with_entries=True)
    original = (pkg / "CHANGELOG.md").read_text()
    _update_changelog_for_package(conf, conf.resolve_group(), "1.1.0", dry_run=True)
    assert (pkg / "CHANGELOG.md").read_text() == original
    assert capsys.readouterr().out  # DryRunPrinter printed something


# ---------------------------------------------------------------------------
# cmd_workspace_bump – ValueError paths (lines 169-175)
# ---------------------------------------------------------------------------


def test_workspace_bump_missing_rrt_value_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 when config raises MissingRrtConfigError."""
    from repo_release_tools.config import MissingRrtConfigError

    monkeypatch.chdir(tmp_path)
    pkg = tmp_path / "api"
    pkg.mkdir()
    monkeypatch.setattr(
        "repo_release_tools.commands.workspace.load_or_autodetect_config",
        lambda _: (_ for _ in ()).throw(MissingRrtConfigError("no rrt")),
    )
    rc = cmd_workspace_bump(_args(packages="api"))
    assert rc == 1
    assert capsys.readouterr().err


def test_workspace_bump_generic_value_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 when config raises a generic ValueError."""
    monkeypatch.chdir(tmp_path)
    pkg = tmp_path / "api"
    pkg.mkdir()
    monkeypatch.setattr(
        "repo_release_tools.commands.workspace.load_or_autodetect_config",
        lambda _: (_ for _ in ()).throw(ValueError("bad config value")),
    )
    rc = cmd_workspace_bump(_args(packages="api"))
    assert rc == 1
    assert "bad config value" in capsys.readouterr().err
