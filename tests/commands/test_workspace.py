"""Tests for the `rrt workspace bump` command."""

from __future__ import annotations

import argparse
import dataclasses
import subprocess
from pathlib import Path
from typing import cast

import pytest
from repo_fixtures import init_git_repo

from repo_release_tools import cli
from repo_release_tools.commands.workspace import (
    _compute_new_version,
    _resolve_packages,
    _update_changelog_for_package,
    cmd_workspace_bump,
)
from repo_release_tools.config import RrtConfig, VersionGroup, VersionTarget
from repo_release_tools.ui import GLYPHS
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
    prerelease_base: str | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        bump=bump,
        packages=packages,
        dry_run=dry_run,
        no_changelog=no_changelog,
        prerelease_base=prerelease_base,
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


def test_compute_new_version_keyword_kind_on_calver_current_raises() -> None:
    """A keyword kind (e.g. 'patch') on a calver-scheme current version is a clean error.

    Covers RRT-VER-1 T1.2: read_group_current_version_for_scheme() returns a
    CalVersion for a calver-scheme package, so _compute_new_version must refuse
    non-'calver' keyword kinds instead of calling .bump("patch") on it.
    """
    current = CalVersion.parse("2026.05.15")
    with pytest.raises(ValueError, match=r"'calver'.*only supports the 'calver' bump kind"):
        _compute_new_version("patch", current)


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


# ---------------------------------------------------------------------------
# Impossible bumps abort before any write; `release` finalizes pre-releases
# ---------------------------------------------------------------------------


def _patch_configs(monkeypatch: pytest.MonkeyPatch, configs: dict[Path, RrtConfig]) -> None:
    monkeypatch.setattr(
        "repo_release_tools.commands.workspace.load_or_autodetect_config",
        lambda path: configs[path],
    )


def test_compute_new_version_release_finalizes_pre_release() -> None:
    """`release` is an accepted bump kind and drops the pre-release suffix."""
    assert str(_compute_new_version("release", Version.parse("1.2.0-rc.1"))) == "1.2.0"


def test_workspace_bump_pre_release_on_stable_package_exits_1_and_writes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An impossible bump in any package aborts cleanly before any file is written."""
    monkeypatch.chdir(tmp_path)
    pkg_a = tmp_path / "api"
    pkg_a.mkdir()
    conf_a = _make_pkg_config(pkg_a, "1.2.0-rc.1")
    _write_changelog(pkg_a / "CHANGELOG.md", with_entries=True)
    pkg_b = tmp_path / "sdk"
    pkg_b.mkdir()
    conf_b = _make_pkg_config(pkg_b, "1.0.0")
    _write_changelog(pkg_b / "CHANGELOG.md", with_entries=True)
    _patch_configs(monkeypatch, {pkg_a: conf_a, pkg_b: conf_b})

    files = [
        conf_a.version_groups[0].version_targets[0].path,
        conf_b.version_groups[0].version_targets[0].path,
        pkg_a / "CHANGELOG.md",
        pkg_b / "CHANGELOG.md",
    ]
    before = {f: f.read_bytes() for f in files}

    rc = cmd_workspace_bump(_args(bump="pre-release", packages="api,sdk"))

    assert rc == 1
    captured = capsys.readouterr()
    assert "Cannot bump pre-release on a stable version" in captured.err
    assert "sdk" in captured.err
    assert "Traceback" not in captured.err
    assert "Workspace bump" not in captured.out
    assert {f: f.read_bytes() for f in files} == before


def test_workspace_bump_release_finalizes_pre_release_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`workspace bump release` turns 1.2.0-rc.1 into 1.2.0."""
    monkeypatch.chdir(tmp_path)
    pkg = tmp_path / "api"
    pkg.mkdir()
    conf = _make_pkg_config(pkg, "1.2.0-rc.1")
    _patch_configs(monkeypatch, {pkg: conf})

    rc = cmd_workspace_bump(_args(bump="release", packages="api", no_changelog=True))

    assert rc == 0
    target = conf.version_groups[0].version_targets[0].path
    assert target.read_text(encoding="utf-8") == '__version__ = "1.2.0"\n'


def test_workspace_bump_release_dry_run_writes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`workspace bump release --dry-run` previews 1.2.0 without touching files."""
    monkeypatch.chdir(tmp_path)
    pkg = tmp_path / "api"
    pkg.mkdir()
    conf = _make_pkg_config(pkg, "1.2.0-rc.1")
    _write_changelog(pkg / "CHANGELOG.md", with_entries=True)
    _patch_configs(monkeypatch, {pkg: conf})
    target = conf.version_groups[0].version_targets[0].path
    before = (target.read_bytes(), (pkg / "CHANGELOG.md").read_bytes())

    rc = cmd_workspace_bump(_args(bump="release", packages="api", dry_run=True))

    assert rc == 0
    out = capsys.readouterr().out
    assert "1.2.0" in out
    assert "no files were modified" in out
    assert (target.read_bytes(), (pkg / "CHANGELOG.md").read_bytes()) == before


def test_workspace_bump_release_on_stable_package_exits_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`workspace bump release` on a stable version fails with the finalize reason."""
    monkeypatch.chdir(tmp_path)
    pkg = tmp_path / "api"
    pkg.mkdir()
    conf = _make_pkg_config(pkg, "1.0.0")
    _patch_configs(monkeypatch, {pkg: conf})
    target = conf.version_groups[0].version_targets[0].path
    before = target.read_bytes()

    rc = cmd_workspace_bump(_args(bump="release", packages="api"))

    assert rc == 1
    err = capsys.readouterr().err
    assert "Cannot finalize" in err
    assert "api" in err
    assert target.read_bytes() == before


# ---------------------------------------------------------------------------
# Pre-release base pass-through (issue #259, T0.2, D-1)
# ---------------------------------------------------------------------------


def _with_base(config: RrtConfig, base: str) -> RrtConfig:
    group = dataclasses.replace(config.version_groups[0], prerelease_base=base)
    return dataclasses.replace(config, version_groups=[group])


@pytest.mark.parametrize(
    ("config_base", "base_flag", "expected"),
    [
        pytest.param("minor", None, "1.1.0-rc.1", id="config_minor"),
        pytest.param("minor", "major", "2.0.0-rc.1", id="flag_overrides"),
        pytest.param(None, None, "1.0.1-rc.1", id="default_patch"),
    ],
)
def test_workspace_bump_rc_honours_prerelease_base(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    config_base: str | None,
    base_flag: str | None,
    expected: str,
) -> None:
    """Config prerelease_base applies per package; --base overrides it."""
    monkeypatch.chdir(tmp_path)
    pkg = tmp_path / "api"
    pkg.mkdir()
    conf = _make_pkg_config(pkg, "1.0.0")
    if config_base is not None:
        conf = _with_base(conf, config_base)
    _patch_configs(monkeypatch, {pkg: conf})

    rc = cmd_workspace_bump(
        _args(bump="rc", packages="api", no_changelog=True, prerelease_base=base_flag)
    )

    assert rc == 0
    target = conf.version_groups[0].version_targets[0].path
    assert target.read_text(encoding="utf-8") == f'__version__ = "{expected}"\n'


def test_workspace_bump_rc_auto_base_reads_each_package_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """'auto' resolves from the package's own repo and group tag_prefix."""
    monkeypatch.chdir(tmp_path)
    pkg = tmp_path / "api"
    pkg.mkdir()
    init_git_repo(pkg)
    conf = _with_base(_make_pkg_config(pkg, "1.0.0"), "auto")
    _patch_configs(monkeypatch, {pkg: conf})
    for message, tag in (("feat!: ancient", None), ("chore: release", "v1.0.0"), ("feat: x", None)):
        (pkg / "history.txt").open("a", encoding="utf-8").write(f"{message}\n")
        subprocess.run(["git", "add", "-A"], cwd=pkg, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-q", "-m", message], cwd=pkg, check=True)
        if tag:
            subprocess.run(["git", "tag", tag], cwd=pkg, check=True)

    rc = cmd_workspace_bump(_args(bump="rc", packages="api", dry_run=True))

    assert rc == 0
    assert f"1.0.0 {GLYPHS.arrow.right} 1.1.0-rc.1" in capsys.readouterr().out


def test_workspace_bump_prerelease_base_ignored_for_core_and_prerelease() -> None:
    """A base never changes a core bump or a version already on a pre-release."""
    assert str(_compute_new_version("minor", Version.parse("1.0.0"), "major")) == "1.1.0"
    assert str(_compute_new_version("rc", Version.parse("1.0.1-rc.1"), "major")) == "1.0.1-rc.2"
    assert str(_compute_new_version("rc", Version.parse("1.0.0"), "minor")) == "1.1.0-rc.1"


def test_workspace_bump_parser_accepts_base_flag() -> None:
    """`rrt workspace bump --base` is registered with the D-1 choices."""
    parser = cli.build_parser()
    args = parser.parse_args(["workspace", "bump", "rc", "--packages", "api", "--base", "minor"])
    assert args.prerelease_base == "minor"
    assert (
        parser.parse_args(["workspace", "bump", "rc", "--packages", "api"]).prerelease_base is None
    )
    with pytest.raises(SystemExit):
        parser.parse_args(["workspace", "bump", "rc", "--packages", "api", "--base", "bogus"])
