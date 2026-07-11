"""Tests for version bumping and changelog update logic."""

from __future__ import annotations

import argparse
import os
import sys
from argparse import Namespace
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest

from repo_release_tools.commands.bump import (
    BumpResolutionError,
    Options,
    apply_bump_files,
    cmd_bump,
    git_log_since_latest_tag,
    register,
    resolve_bump_target,
    resolve_changelog_mode,
    update_changelog,
)
from repo_release_tools.config import PinTarget, RrtConfig, VersionGroup, VersionTarget
from repo_release_tools.version.calver import CalVersion
from repo_release_tools.version.semver import Version
from repo_release_tools.version.targets import VersionWriteEvent


def _options(**overrides: object) -> Options:
    """Build an Options with sensible defaults for resolve/apply tests."""
    defaults: dict[str, object] = {
        "bump": "patch",
        "group": None,
        "dry_run": False,
        "force": False,
        "no_commit": False,
        "no_verify": False,
        "no_changelog": False,
        "no_pin_sync": False,
        "no_update": False,
        "include_maintenance": False,
        "changelog_mode": None,
        "base_branch": None,
        "calver_scheme": "YYYY.MM.DD",
        "verbose": 0,
    }
    defaults.update(overrides)
    return Options(**defaults)  # type: ignore[arg-type]


def _default_group_config(tmp_path: Path) -> tuple[VersionGroup, RrtConfig]:
    target = VersionTarget(path=tmp_path / "pyproject.toml", kind="pep621")
    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=tmp_path / "CHANGELOG.md",
        lock_command=[],
        generated_files=[],
        version_targets=[target],
        changelog_workflow="incremental",
    )
    config = RrtConfig(
        root=tmp_path,
        config_file=tmp_path / ".rrt.toml",
        version_groups=[group],
        default_group_name="default",
    )
    return group, config


def test_resolve_bump_target_unknown_group_raises(tmp_path: Path) -> None:
    """resolve_bump_target raises BumpResolutionError for an unknown group name."""
    _, config = _default_group_config(tmp_path)
    (tmp_path / "pyproject.toml").write_text('version = "1.0.0"\n', encoding="utf-8")
    opts = _options(bump="patch", group="does-not-exist")

    with pytest.raises(BumpResolutionError):
        resolve_bump_target(config, opts)


def test_resolve_bump_target_computes_patch_bump(tmp_path: Path) -> None:
    """resolve_bump_target computes the new version for a plain semver kind."""
    _, config = _default_group_config(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1.2.3"\n', encoding="utf-8"
    )
    opts = _options(bump="patch")

    target = resolve_bump_target(config, opts)

    assert isinstance(target.current, Version)
    assert str(target.new) == "1.2.4"
    assert target.group.name == "default"


def test_resolve_bump_target_accepts_explicit_version_string(tmp_path: Path) -> None:
    """resolve_bump_target accepts an explicit semver string as the bump kind."""
    _, config = _default_group_config(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1.2.3"\n', encoding="utf-8"
    )
    opts = _options(bump="9.9.9")

    target = resolve_bump_target(config, opts)

    assert str(target.new) == "9.9.9"


def test_resolve_bump_target_calver_kind_bumps_to_today(tmp_path: Path) -> None:
    """resolve_bump_target's calver branch produces a CalVersion for today."""
    _, config = _default_group_config(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1.2.3"\n', encoding="utf-8"
    )
    opts = _options(bump="calver", calver_scheme="YYYY.MM.DD")

    target = resolve_bump_target(config, opts)

    # Non-calver current is treated as a fresh start (matches original inline behavior).
    assert CalVersion.parse(str(target.new)) == CalVersion.today("YYYY.MM.DD")


def test_resolve_bump_target_invalid_bump_value_raises(tmp_path: Path) -> None:
    """resolve_bump_target raises BumpResolutionError for an unparseable bump value."""
    _, config = _default_group_config(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1.2.3"\n', encoding="utf-8"
    )
    opts = _options(bump="not-a-version")

    with pytest.raises(BumpResolutionError, match="Invalid bump value"):
        resolve_bump_target(config, opts)


def test_apply_bump_files_writes_new_version(tmp_path: Path) -> None:
    """apply_bump_files writes the new version into the group's version target."""
    group, config = _default_group_config(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1.2.3"\n', encoding="utf-8"
    )

    changed = apply_bump_files(group, Version.parse("1.2.4"), config, dry_run=False)

    assert (tmp_path / "pyproject.toml") in changed
    assert '"1.2.4"' in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")


def test_apply_bump_files_dry_run_does_not_write(tmp_path: Path) -> None:
    """apply_bump_files in dry-run mode reports the target without writing it."""
    group, config = _default_group_config(tmp_path)
    original = '[project]\nname = "x"\nversion = "1.2.3"\n'
    (tmp_path / "pyproject.toml").write_text(original, encoding="utf-8")

    apply_bump_files(group, Version.parse("1.2.4"), config, dry_run=True)

    assert (tmp_path / "pyproject.toml").read_text(encoding="utf-8") == original


def test_resolve_changelog_mode_prefers_requested_mode(tmp_path: Path) -> None:
    """Test that resolve_changelog_mode returns the requested mode when provided."""
    target = VersionTarget(path=tmp_path / "pyproject.toml", kind="pep621")
    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=tmp_path / "CHANGELOG.md",
        lock_command=[],
        generated_files=[],
        version_targets=[target],
        changelog_workflow="incremental",
    )
    config = RrtConfig(
        root=tmp_path,
        config_file=tmp_path / ".rrt.toml",
        version_groups=[group],
        default_group_name="default",
    )

    assert resolve_changelog_mode(config, "promote") == "promote"


def test_resolve_changelog_mode_defaults_to_auto_for_incremental(tmp_path: Path) -> None:
    """Test that resolve_changelog_mode defaults to 'auto' for incremental workflow."""
    target = VersionTarget(path=tmp_path / "pyproject.toml", kind="pep621")
    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=tmp_path / "CHANGELOG.md",
        lock_command=[],
        generated_files=[],
        version_targets=[target],
        changelog_workflow="incremental",
    )
    config = RrtConfig(
        root=tmp_path,
        config_file=tmp_path / ".rrt.toml",
        version_groups=[group],
        default_group_name="default",
    )

    assert resolve_changelog_mode(config, None) == "auto"


def test_resolve_changelog_mode_defaults_to_generate_for_squash(tmp_path: Path) -> None:
    """Test that resolve_changelog_mode defaults to 'generate' for squash workflow."""
    target = VersionTarget(path=tmp_path / "pyproject.toml", kind="pep621")
    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=tmp_path / "CHANGELOG.md",
        lock_command=[],
        generated_files=[],
        version_targets=[target],
        changelog_workflow="squash",
    )
    config = RrtConfig(
        root=tmp_path,
        config_file=tmp_path / ".rrt.toml",
        version_groups=[group],
        default_group_name="default",
    )

    assert resolve_changelog_mode(config, None) == "generate"


def test_git_log_since_latest_tag_uses_latest_tag_range(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []

    def fake_capture(cmd: list[str], root: Path) -> str:
        calls.append(cmd)
        if cmd[:2] == ["git", "tag"]:
            return "v1.2.0\nv1.1.0\n"
        return "feat: add parser\nfix: tighten validation\n"

    monkeypatch.setattr("repo_release_tools.commands.bump.git.capture", fake_capture)

    assert git_log_since_latest_tag(tmp_path) == ["feat: add parser", "fix: tighten validation"]
    assert calls[1] == ["git", "log", "v1.2.0..HEAD", "--pretty=format:%s"]


def test_git_log_since_latest_tag_uses_head_when_no_tags(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []

    def fake_capture(cmd: list[str], root: Path) -> str:
        calls.append(cmd)
        if cmd[:2] == ["git", "tag"]:
            return ""
        return "feat: add parser\n"

    monkeypatch.setattr("repo_release_tools.commands.bump.git.capture", fake_capture)

    assert git_log_since_latest_tag(tmp_path) == ["feat: add parser"]
    assert calls[1] == ["git", "log", "HEAD", "--pretty=format:%s"]


def test_update_changelog_skips_missing_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = VersionTarget(path=tmp_path / "pyproject.toml", kind="pep621")
    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=tmp_path / "MISSING.md",
        lock_command=[],
        generated_files=[],
        version_targets=[target],
    )
    config = RrtConfig(
        root=tmp_path,
        config_file=tmp_path / ".rrt.toml",
        version_groups=[group],
        default_group_name="default",
    )

    update_changelog(config, "1.2.3", include_maintenance=False, dry_run=False)

    assert "MISSING.md not found" in capsys.readouterr().out


def test_update_changelog_promote_dry_run_shows_preview(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Added\n- parser\n\n## [1.0.0] - 2025-01-01\n",
        encoding="utf-8",
    )
    config = _make_config(tmp_path, changelog)

    update_changelog(
        config,
        "1.1.0",
        include_maintenance=False,
        dry_run=True,
        changelog_mode="promote",
    )

    output = capsys.readouterr().out
    assert "Would update" in output
    assert "promote [Unreleased]" in output
    assert "1.1.0" in output


def test_update_changelog_generate_dry_run_shows_ellipsis_for_long_preview(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git_log_since_latest_tag",
        lambda root: [f"feat: item {i}" for i in range(12)],
    )
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## [Unreleased]\n\n", encoding="utf-8")
    config = _make_config(tmp_path, changelog)

    update_changelog(
        config,
        "1.1.0",
        include_maintenance=True,
        dry_run=True,
        changelog_mode="generate",
    )

    output = capsys.readouterr().out
    assert "Would update" in output
    assert "prepend" in output
    assert "…" in output or "..." in output


def test_cmd_bump_reports_loaded_config_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.load_or_autodetect_config",
        lambda root: (_ for _ in ()).throw(ValueError("broken config")),
    )

    result = cmd_bump(Namespace(force=False))

    assert result == 1
    assert "broken config" in capsys.readouterr().err


def test_cmd_bump_rejects_autodetected_version_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = VersionTarget(path=tmp_path / "pyproject.toml", kind="pep621")
    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=tmp_path / "CHANGELOG.md",
        lock_command=[],
        generated_files=[],
        version_targets=[target],
    )
    config = RrtConfig(
        root=tmp_path,
        config_file=tmp_path / ".rrt.autodetected.toml",
        version_groups=[group],
        default_group_name="default",
        autodetected=True,
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.load_or_autodetect_config",
        lambda root: config,
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.check_autodetected_version_consistency",
        lambda config: "version mismatch",
    )

    result = cmd_bump(Namespace(force=False))

    assert result == 1
    err = capsys.readouterr().err
    assert "auto-detected" in err
    assert "version mismatch" in err


def test_cmd_bump_stages_changelog_and_commits(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]
release_branch = "release/v{version}"
lock_command = []

[[tool.rrt.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text(
        '{\n  "name": "example",\n  "version": "0.1.0"\n}\n',
        encoding="utf-8",
    )
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")

    calls: list[list[str]] = []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.working_tree_clean",
        lambda root: True,
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.branch_exists",
        lambda root, branch: False,
    )
    monkeypatch.setattr("repo_release_tools.commands.bump.git.current_branch", lambda root: "main")
    version_calls: list[tuple[list[VersionTarget], str, bool]] = []

    def fake_replace_all_versions_atomic(
        targets: list[VersionTarget],
        new_version: str,
        *,
        dry_run: bool,
    ) -> list[VersionWriteEvent]:
        version_calls.append((targets, new_version, dry_run))
        return [
            VersionWriteEvent(path=t.path, new_version=new_version, dry_run=dry_run)
            for t in targets
        ]

    monkeypatch.setattr(
        "repo_release_tools.commands.bump.replace_all_versions_atomic",
        fake_replace_all_versions_atomic,
    )
    monkeypatch.setattr("repo_release_tools.commands.bump.update_changelog", lambda *a, **k: None)

    def fake_run(
        cmd: list[str],
        root: Path,
        *,
        dry_run: bool,
        label: str,
        suppress_announce: bool = False,
    ) -> str:
        calls.append(cmd)
        return ""

    monkeypatch.setattr("repo_release_tools.commands.bump.git.run", fake_run)

    result = cmd_bump(
        Namespace(
            bump="minor",
            dry_run=False,
            no_commit=False,
            no_changelog=False,
            no_update=True,
            include_maintenance=False,
            base_branch=None,
            group=None,
        ),
    )

    assert result == 0
    assert len(version_calls) == 1
    assert version_calls[0][1] == "0.2.0"
    assert version_calls[0][2] is False
    assert version_calls[0][0][0].path.name == "package.json"
    assert ["git", "checkout", "-b", "release/v0.2.0"] in calls
    assert ["git", "add", "package.json", "CHANGELOG.md"] in calls
    assert ["git", "add", "-u"] in calls
    assert ["git", "commit", "-m", "chore: bump version to v0.2.0"] in calls


def test_cmd_bump_retries_commit_once_after_hook_auto_fix(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A pre-commit hook that auto-regenerates files (e.g. rrt-cli-docs) always
    fails its first pass even though the fix is correct. bump should re-stage
    and retry the commit once instead of aborting the release.
    """
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]
release_branch = "release/v{version}"
lock_command = []

[[tool.rrt.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text(
        '{\n  "name": "example",\n  "version": "0.1.0"\n}\n',
        encoding="utf-8",
    )
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")

    calls: list[list[str]] = []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.working_tree_clean",
        lambda root: True,
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.branch_exists",
        lambda root, branch: False,
    )
    monkeypatch.setattr("repo_release_tools.commands.bump.git.current_branch", lambda root: "main")
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.replace_all_versions_atomic",
        lambda *a, **k: [],
    )
    monkeypatch.setattr("repo_release_tools.commands.bump.update_changelog", lambda *a, **k: None)

    commit_attempts = 0

    def fake_run(
        cmd: list[str],
        root: Path,
        *,
        dry_run: bool,
        label: str,
        suppress_announce: bool = False,
    ) -> str:
        nonlocal commit_attempts
        calls.append(cmd)
        if cmd[:2] == ["git", "commit"]:
            commit_attempts += 1
            if commit_attempts == 1:
                raise RuntimeError(
                    "git commit failed (exit 1): rrt cli docs - files were modified by this hook"
                )
        return ""

    monkeypatch.setattr("repo_release_tools.commands.bump.git.run", fake_run)

    result = cmd_bump(
        Namespace(
            bump="minor",
            dry_run=False,
            no_commit=False,
            no_changelog=False,
            no_update=True,
            include_maintenance=False,
            base_branch=None,
            group=None,
        ),
    )

    assert result == 0
    assert commit_attempts == 2
    commit_calls = [c for c in calls if c[:2] == ["git", "commit"]]
    assert commit_calls == [["git", "commit", "-m", "chore: bump version to v0.2.0"]] * 2
    # A re-stage must happen between the failed attempt and the retry.
    last_commit_index = (
        len(calls) - 1 - calls[::-1].index(["git", "commit", "-m", "chore: bump version to v0.2.0"])
    )
    first_commit_index = calls.index(["git", "commit", "-m", "chore: bump version to v0.2.0"])
    assert ["git", "add", "-u"] in calls[first_commit_index + 1 : last_commit_index + 1]


def test_cmd_bump_no_verify_appends_flag(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]
release_branch = "release/v{version}"
lock_command = []

[[tool.rrt.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text(
        '{\n  "name": "example",\n  "version": "0.1.0"\n}\n',
        encoding="utf-8",
    )
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")

    calls: list[list[str]] = []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.working_tree_clean",
        lambda root: True,
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.branch_exists",
        lambda root, branch: False,
    )
    monkeypatch.setattr("repo_release_tools.commands.bump.git.current_branch", lambda root: "main")
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.replace_all_versions_atomic",
        lambda *a, **k: [],
    )
    monkeypatch.setattr("repo_release_tools.commands.bump.update_changelog", lambda *a, **k: None)

    def fake_run(
        cmd: list[str],
        root: Path,
        *,
        dry_run: bool,
        label: str,
        suppress_announce: bool = False,
    ) -> str:
        calls.append(cmd)
        return ""

    monkeypatch.setattr("repo_release_tools.commands.bump.git.run", fake_run)

    result = cmd_bump(
        Namespace(
            bump="minor",
            dry_run=False,
            no_commit=False,
            no_verify=True,
            no_changelog=False,
            no_update=True,
            include_maintenance=False,
            base_branch=None,
            group=None,
        ),
    )

    assert result == 0
    assert ["git", "commit", "-m", "chore: bump version to v0.2.0", "--no-verify"] in calls


def test_cmd_bump_dry_run_from_pep621_config(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """[tool.rrt]
release_branch = \"release/v{version}\"
changelog_file = \"CHANGELOG.md\"
lock_command = [\"uv\", \"lock\", \"-U\"]

[[tool.rrt.version_targets]]
path = \"pyproject.toml\"
kind = \"pep621\"

[project]
name = \"example\"
version = \"0.1.0\"
""",
        encoding="utf-8",
    )

    cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        args = __import__("argparse").Namespace(
            bump="minor",
            dry_run=True,
            no_commit=True,
            no_changelog=False,
            no_update=False,
            include_maintenance=False,
            base_branch=None,
            group=None,
        )
        result = cmd_bump(args)
    finally:
        os.chdir(cwd)

    captured = capsys.readouterr()
    assert result == 0
    assert "Version bump" in captured.out
    assert "release/v0.2.0" in captured.out
    assert "Would update" in captured.out
    assert "no files were modified" in captured.out


def test_register_bump_parser_sets_handler_and_defaults() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    register(subparsers)

    args = parser.parse_args(["bump", "patch"])
    assert args.command == "bump"
    assert args.bump == "patch"
    assert args.changelog_mode is None
    assert args.handler is cmd_bump


def test_cmd_bump_dry_run_from_rrt_toml_and_package_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / ".rrt.toml").write_text(
        """[tool.rrt]
release_branch = "release/v{version}"

[[tool.rrt.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text(
        """{
  "name": "example",
  "version": "0.1.0"
}
""",
        encoding="utf-8",
    )

    cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        result = cmd_bump(
            Namespace(
                bump="minor",
                dry_run=True,
                no_commit=True,
                no_changelog=False,
                no_update=False,
                include_maintenance=False,
                base_branch=None,
                group=None,
            ),
        )
    finally:
        os.chdir(cwd)

    captured = capsys.readouterr()
    assert result == 0
    assert "release/v0.2.0" in captured.out
    assert "Would update" in captured.out


def test_cmd_bump_stages_generated_files_from_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]
lock_command = []
generated_files = ["package-lock.json", "pnpm-lock.yaml"]

[[tool.rrt.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text(
        """{
  "name": "example",
  "version": "0.1.0"
}
""",
        encoding="utf-8",
    )
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")

    calls: list[list[str]] = []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.working_tree_clean",
        lambda root: True,
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.branch_exists",
        lambda root, branch: False,
    )
    monkeypatch.setattr("repo_release_tools.commands.bump.git.current_branch", lambda root: "main")

    def fake_run(cmd: list[str], root: Path, *, dry_run: bool, label: str) -> str:
        calls.append(cmd)
        return ""

    monkeypatch.setattr("repo_release_tools.commands.bump.git.run", fake_run)

    result = cmd_bump(
        Namespace(
            bump="minor",
            dry_run=False,
            no_commit=True,
            no_changelog=True,
            no_update=False,
            include_maintenance=False,
            base_branch=None,
            group=None,
        ),
    )

    add_calls = [cmd for cmd in calls if cmd[:2] == ["git", "add"]]
    assert result == 0
    assert any("package-lock.json" in cmd for cmd in add_calls)
    assert any("pnpm-lock.yaml" in cmd for cmd in add_calls)
    assert not any("uv.lock" in cmd for cmd in add_calls)


def test_cmd_bump_runs_generated_asset_commands_and_stages_outputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]
lock_command = []

[[tool.rrt.generated_assets]]
path = "docs/assets/banner-dark.png"
command = ["generate", "banner"]

[[tool.rrt.generated_assets]]
path = "docs/assets/banner-windows.png"
command = ["generate", "banner-windows"]

[[tool.rrt.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text(
        '{\n  "name": "example",\n  "version": "0.1.0"\n}\n',
        encoding="utf-8",
    )

    calls: list[list[str]] = []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.working_tree_clean",
        lambda root: True,
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.branch_exists",
        lambda root, branch: False,
    )
    monkeypatch.setattr("repo_release_tools.commands.bump.git.current_branch", lambda root: "main")

    def fake_run(
        cmd: list[str],
        root: Path,
        *,
        dry_run: bool,
        label: str,
        suppress_announce: bool = False,
    ) -> str:
        calls.append(cmd)
        if label.startswith("generated asset command"):
            if "banner-windows.png" in label:
                out = tmp_path / "docs" / "assets" / "banner-windows.png"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text("windows", encoding="utf-8")
            if "banner-dark.png" in label and "windows" not in label:
                out = tmp_path / "docs" / "assets" / "banner-dark.png"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text("unicode", encoding="utf-8")
        return ""

    monkeypatch.setattr("repo_release_tools.commands.bump.git.run", fake_run)

    result = cmd_bump(
        Namespace(
            bump="minor",
            dry_run=False,
            no_commit=True,
            no_changelog=True,
            no_update=False,
            no_pin_sync=True,
            include_maintenance=False,
            base_branch=None,
            group=None,
        ),
    )

    add_calls = [cmd for cmd in calls if cmd[:2] == ["git", "add"]]
    assert result == 0
    assert ["generate", "banner"] in calls
    assert ["generate", "banner-windows"] in calls
    assert add_calls
    assert "docs/assets/banner-dark.png" in add_calls[-1]
    assert "docs/assets/banner-windows.png" in add_calls[-1]


def test_cmd_bump_generated_asset_failure_policy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]
lock_command = []

[[tool.rrt.generated_assets]]
path = "docs/assets/banner-dark.png"
command = ["generate", "banner"]

[[tool.rrt.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text(
        '{\n  "name": "example",\n  "version": "0.1.0"\n}\n',
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.working_tree_clean",
        lambda root: True,
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.branch_exists",
        lambda root, branch: False,
    )
    monkeypatch.setattr("repo_release_tools.commands.bump.git.current_branch", lambda root: "main")

    def fake_run(
        cmd: list[str],
        root: Path,
        *,
        dry_run: bool,
        label: str,
        suppress_announce: bool = False,
    ) -> str:
        if label.startswith("generated asset command"):
            raise RuntimeError("asset generation failed")
        return ""

    monkeypatch.setattr("repo_release_tools.commands.bump.git.run", fake_run)

    dry_run_result = cmd_bump(
        Namespace(
            bump="minor",
            dry_run=True,
            no_commit=True,
            no_changelog=True,
            no_update=False,
            no_pin_sync=True,
            include_maintenance=False,
            base_branch=None,
            group=None,
        ),
    )
    dry_run_output = capsys.readouterr().out
    assert dry_run_result == 0
    assert "failed in dry-run" in dry_run_output

    real_run_result = cmd_bump(
        Namespace(
            bump="minor",
            dry_run=False,
            no_commit=True,
            no_changelog=True,
            no_update=False,
            no_pin_sync=True,
            include_maintenance=False,
            base_branch=None,
            group=None,
        ),
    )
    real_run_err = capsys.readouterr().err
    assert real_run_result == 1
    assert "asset generation failed" in real_run_err


def test_cmd_bump_generated_asset_missing_output_policy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]
lock_command = []

[[tool.rrt.generated_assets]]
path = "docs/assets/banner-dark.png"
command = ["generate", "banner"]

[[tool.rrt.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text(
        '{\n  "name": "example",\n  "version": "0.1.0"\n}\n',
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.working_tree_clean",
        lambda root: True,
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.branch_exists",
        lambda root, branch: False,
    )
    monkeypatch.setattr("repo_release_tools.commands.bump.git.current_branch", lambda root: "main")

    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.run",
        lambda cmd, root, *, dry_run, label, suppress_announce=False: "",
    )

    dry_run_result = cmd_bump(
        Namespace(
            bump="minor",
            dry_run=True,
            no_commit=True,
            no_changelog=True,
            no_update=False,
            no_pin_sync=True,
            include_maintenance=False,
            base_branch=None,
            group=None,
        ),
    )
    dry_run_output = capsys.readouterr().out
    assert dry_run_result == 0
    assert "not found after refresh command" in dry_run_output

    real_run_result = cmd_bump(
        Namespace(
            bump="minor",
            dry_run=False,
            no_commit=True,
            no_changelog=True,
            no_update=False,
            no_pin_sync=True,
            include_maintenance=False,
            base_branch=None,
            group=None,
        ),
    )
    real_run_err = capsys.readouterr().err
    assert real_run_result == 1
    assert "not found after refresh command" in real_run_err


def test_cmd_bump_refuses_existing_release_branch_without_force(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
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
        '{\n  "name": "example",\n  "version": "0.1.0"\n}\n',
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.working_tree_clean",
        lambda root: True,
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.branch_exists",
        lambda root, branch: True,
    )
    monkeypatch.setattr("repo_release_tools.commands.bump.git.current_branch", lambda root: "main")

    result = cmd_bump(
        Namespace(
            bump="patch",
            dry_run=False,
            force=False,
            no_commit=True,
            no_changelog=True,
            no_update=True,
            include_maintenance=False,
            base_branch=None,
            group=None,
        ),
    )

    captured = capsys.readouterr()
    assert result == 1
    assert "already exists" in captured.err


def test_cmd_bump_force_resets_existing_release_branch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
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
        '{\n  "name": "example",\n  "version": "0.1.0"\n}\n',
        encoding="utf-8",
    )

    calls: list[list[str]] = []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.working_tree_clean",
        lambda root: True,
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.branch_exists",
        lambda root, branch: True,
    )
    monkeypatch.setattr("repo_release_tools.commands.bump.git.current_branch", lambda root: "main")

    def fake_run(cmd: list[str], root: Path, *, dry_run: bool, label: str) -> str:
        calls.append(cmd)
        return ""

    monkeypatch.setattr("repo_release_tools.commands.bump.git.run", fake_run)

    result = cmd_bump(
        Namespace(
            bump="patch",
            dry_run=False,
            force=True,
            no_commit=True,
            no_changelog=True,
            no_update=True,
            include_maintenance=False,
            base_branch=None,
            group=None,
        ),
    )

    captured = capsys.readouterr()
    assert result == 0
    assert "Resetting it with --force" in captured.out
    assert ["git", "checkout", "-B", "release/v0.1.1"] in calls
    assert ["git", "checkout", "-b", "release/v0.1.1"] not in calls


def test_cmd_bump_accepts_legacy_double_escaped_pattern(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / ".rrt.toml").write_text(
        """[tool.rrt]
release_branch = "release/v{version}"
lock_command = []

[[tool.rrt.version_targets]]
path = "src/example/__init__.py"
pattern = '^(\\\\s*__version__\\\\s*=\\\\s*")([^"]+)(")'
""",
        encoding="utf-8",
    )
    init_file = tmp_path / "src" / "example" / "__init__.py"
    init_file.parent.mkdir(parents=True)
    init_file.write_text('__version__ = "0.1.0"\n', encoding="utf-8")

    cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        result = cmd_bump(
            Namespace(
                bump="patch",
                dry_run=True,
                no_commit=True,
                no_changelog=True,
                no_update=False,
                include_maintenance=False,
                base_branch=None,
                group=None,
            ),
        )
    finally:
        os.chdir(cwd)

    captured = capsys.readouterr()
    assert result == 0
    assert "release/v0.1.1" in captured.out
    assert "Would update" in captured.out


def test_cmd_bump_requires_group_for_multi_group_config(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
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

[project]
name = "example"
version = "0.1.0"
""",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "example"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text('{"name":"example","version":"0.1.0"}', encoding="utf-8")

    cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        result = cmd_bump(
            Namespace(
                bump="patch",
                dry_run=True,
                no_commit=True,
                no_changelog=True,
                no_update=False,
                include_maintenance=False,
                base_branch=None,
                group=None,
            ),
        )
    finally:
        os.chdir(cwd)

    captured = capsys.readouterr()
    assert result == 1
    assert "Multiple version groups configured" in captured.err


def test_cmd_bump_reports_missing_config_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.load_or_autodetect_config",
        lambda root: (_ for _ in ()).throw(FileNotFoundError("missing")),
    )

    result = cmd_bump(
        Namespace(
            bump="patch",
            dry_run=False,
            no_commit=True,
            no_changelog=True,
            no_update=True,
            no_pin_sync=True,
            include_maintenance=False,
            base_branch=None,
            group=None,
        ),
    )

    assert result == 1
    assert "No supported rrt config file found" in capsys.readouterr().err


def test_cmd_bump_reports_missing_tool_rrt_guidance(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.load_or_autodetect_config",
        lambda root: (_ for _ in ()).throw(
            ValueError("Missing rrt configuration in supported config files: pyproject.toml"),
        ),
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.iter_config_files",
        lambda root: [tmp_path / "pyproject.toml"],
    )

    result = cmd_bump(
        Namespace(
            bump="patch",
            dry_run=False,
            no_commit=True,
            no_changelog=True,
            no_update=True,
            no_pin_sync=True,
            include_maintenance=False,
            base_branch=None,
            group=None,
        ),
    )

    assert result == 1
    assert "No [tool.rrt] configuration found" in capsys.readouterr().err


def test_cmd_bump_reports_runtime_error_loading_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.load_or_autodetect_config",
        lambda root: (_ for _ in ()).throw(RuntimeError("broken environment")),
    )

    result = cmd_bump(
        Namespace(
            bump="patch",
            dry_run=False,
            no_commit=True,
            no_changelog=True,
            no_update=True,
            no_pin_sync=True,
            include_maintenance=False,
            base_branch=None,
            group=None,
        ),
    )

    assert result == 1
    assert "broken environment" in capsys.readouterr().err


def test_cmd_bump_rejects_invalid_explicit_version(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
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

    monkeypatch.chdir(tmp_path)

    result = cmd_bump(
        Namespace(
            bump="not-a-version",
            dry_run=True,
            no_commit=True,
            no_changelog=True,
            no_update=True,
            no_pin_sync=True,
            include_maintenance=False,
            base_branch=None,
            group=None,
        ),
    )

    assert result == 1
    assert "Invalid bump value" in capsys.readouterr().err


def test_cmd_bump_refuses_dirty_working_tree(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
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

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.working_tree_clean",
        lambda root: False,
    )

    result = cmd_bump(
        Namespace(
            bump="patch",
            dry_run=False,
            no_commit=True,
            no_changelog=True,
            no_update=True,
            no_pin_sync=True,
            include_maintenance=False,
            base_branch=None,
            group=None,
        ),
    )

    assert result == 1
    assert "Working tree has uncommitted changes" in capsys.readouterr().err


def test_cmd_bump_checks_out_base_branch_before_release_branch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
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

    calls: list[list[str]] = []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.working_tree_clean",
        lambda root: True,
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.branch_exists",
        lambda root, branch: False,
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.current_branch",
        lambda root: "feature/current",
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.run",
        lambda cmd, root, *, dry_run, label: calls.append(cmd),
    )

    result = cmd_bump(
        Namespace(
            bump="patch",
            dry_run=False,
            force=False,
            no_commit=True,
            no_changelog=True,
            no_update=True,
            no_pin_sync=True,
            include_maintenance=False,
            base_branch="main",
            group=None,
        ),
    )

    assert result == 0
    assert ["git", "checkout", "main"] in calls


def test_cmd_bump_updates_selected_group_only(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]

[[tool.rrt.version_groups]]
name = "python"
version_source = "pyproject.toml"

[[tool.rrt.version_groups.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[[tool.rrt.version_groups]]
name = "web"
release_branch = "release/web/v{version}"
version_source = "package.json"

[[tool.rrt.version_groups.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "example"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text('{"name":"example","version":"2.3.4"}', encoding="utf-8")

    cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        result = cmd_bump(
            Namespace(
                bump="patch",
                dry_run=True,
                no_commit=True,
                no_changelog=True,
                no_update=False,
                include_maintenance=False,
                base_branch=None,
                group="web",
            ),
        )
    finally:
        os.chdir(cwd)

    captured = capsys.readouterr()
    assert result == 0
    assert "release/web/v2.3.5" in captured.out
    assert "Would update" in captured.out


def test_cmd_bump_no_update_skips_lock_command(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """--no-update must prevent the lock command from running."""
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]
lock_command = ["npm", "install"]

[[tool.rrt.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text(
        '{\n  "name": "example",\n  "version": "1.0.0"\n}\n',
        encoding="utf-8",
    )

    calls: list[list[str]] = []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.working_tree_clean",
        lambda root: True,
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.branch_exists",
        lambda root, branch: False,
    )
    monkeypatch.setattr("repo_release_tools.commands.bump.git.current_branch", lambda root: "main")

    def fake_run(cmd: list[str], root: Path, *, dry_run: bool, label: str) -> str:
        calls.append(cmd)
        return ""

    monkeypatch.setattr("repo_release_tools.commands.bump.git.run", fake_run)

    result = cmd_bump(
        Namespace(
            bump="patch",
            dry_run=False,
            no_commit=True,
            no_changelog=True,
            no_update=True,
            include_maintenance=False,
            base_branch=None,
            group=None,
        ),
    )

    assert result == 0
    assert not any("npm" in cmd for cmd in calls)


def test_cmd_bump_native_pep621_no_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Bump works on a plain PEP 621 project without [tool.rrt] config."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "example"\nversion = "0.3.0"\n',
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.working_tree_clean",
        lambda root: True,
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.branch_exists",
        lambda root, branch: False,
    )
    monkeypatch.setattr("repo_release_tools.commands.bump.git.current_branch", lambda root: "main")
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.run",
        lambda cmd, root, *, dry_run, label: "",
    )

    result = cmd_bump(
        Namespace(
            bump="minor",
            dry_run=False,
            no_commit=True,
            no_changelog=True,
            no_update=True,
            include_maintenance=False,
            base_branch=None,
            group=None,
        ),
    )

    assert result == 0
    content = (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "0.4.0"' in content


def test_cmd_bump_native_package_json_no_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Bump works on a plain JS project (package.json only) without [tool.rrt] config."""
    (tmp_path / "package.json").write_text(
        '{\n  "name": "example",\n  "version": "2.0.0"\n}\n',
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.working_tree_clean",
        lambda root: True,
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.branch_exists",
        lambda root, branch: False,
    )
    monkeypatch.setattr("repo_release_tools.commands.bump.git.current_branch", lambda root: "main")
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.run",
        lambda cmd, root, *, dry_run, label: "",
    )

    result = cmd_bump(
        Namespace(
            bump="patch",
            dry_run=False,
            no_commit=True,
            no_changelog=True,
            no_update=True,
            include_maintenance=False,
            base_branch=None,
            group=None,
        ),
    )

    assert result == 0
    import json

    pkg = json.loads((tmp_path / "package.json").read_text(encoding="utf-8"))
    assert pkg["version"] == "2.0.1"


def test_cmd_bump_native_cargo_no_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Bump works on a plain Rust project (Cargo.toml only) without explicit rrt config."""
    (tmp_path / "Cargo.toml").write_text(
        """\
[package]
name = "example"
version = "0.3.0"
""",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.working_tree_clean",
        lambda root: True,
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.branch_exists",
        lambda root, branch: False,
    )
    monkeypatch.setattr("repo_release_tools.commands.bump.git.current_branch", lambda root: "main")
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.run",
        lambda cmd, root, *, dry_run, label: "",
    )

    result = cmd_bump(
        Namespace(
            bump="minor",
            dry_run=False,
            no_commit=True,
            no_changelog=True,
            no_update=True,
            include_maintenance=False,
            base_branch=None,
            group=None,
        ),
    )

    assert result == 0
    content = (tmp_path / "Cargo.toml").read_text(encoding="utf-8")
    assert 'version = "0.4.0"' in content


def test_cmd_bump_python_version_kind_explicit_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """bump updates __version__ in a Python file when kind='python_version' is configured."""
    init_file = tmp_path / "src" / "mypkg" / "__init__.py"
    init_file.parent.mkdir(parents=True)
    init_file.write_text('__version__ = "0.1.0"\n', encoding="utf-8")

    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]
release_branch = "release/v{version}"
lock_command = []

[[tool.rrt.version_targets]]
path = "src/mypkg/__init__.py"
kind = "python_version"
""",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.working_tree_clean",
        lambda root: True,
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.branch_exists",
        lambda root, branch: False,
    )
    monkeypatch.setattr("repo_release_tools.commands.bump.git.current_branch", lambda root: "main")
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.run",
        lambda cmd, root, *, dry_run, label: "",
    )
    result = cmd_bump(
        Namespace(
            bump="minor",
            dry_run=True,
            no_commit=True,
            no_changelog=True,
            no_update=False,
            include_maintenance=False,
            base_branch=None,
            group=None,
        ),
    )

    captured = capsys.readouterr()
    assert result == 0
    assert "release/v0.2.0" in captured.out
    assert "Would update" in captured.out


def test_cmd_bump_python_version_kind_writes_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """bump actually writes the new __version__ when not in dry-run mode."""
    init_file = tmp_path / "src" / "mypkg" / "__init__.py"
    init_file.parent.mkdir(parents=True)
    init_file.write_text('__version__ = "1.0.0"\n', encoding="utf-8")

    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]
release_branch = "release/v{version}"
lock_command = []

[[tool.rrt.version_targets]]
path = "src/mypkg/__init__.py"
kind = "python_version"
""",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.working_tree_clean",
        lambda root: True,
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.branch_exists",
        lambda root, branch: False,
    )
    monkeypatch.setattr("repo_release_tools.commands.bump.git.current_branch", lambda root: "main")
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.run",
        lambda cmd, root, *, dry_run, label: "",
    )

    result = cmd_bump(
        Namespace(
            bump="patch",
            dry_run=False,
            no_commit=True,
            no_changelog=True,
            no_update=True,
            include_maintenance=False,
            base_branch=None,
            group=None,
        ),
    )

    assert result == 0
    assert '__version__ = "1.0.1"' in init_file.read_text(encoding="utf-8")


def test_cmd_bump_autodetects_python_version_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Zero-config bump auto-detects __version__ in src/<pkg>/__init__.py."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "example"\nversion = "0.5.0"\n',
        encoding="utf-8",
    )
    init_file = tmp_path / "src" / "example" / "__init__.py"
    init_file.parent.mkdir(parents=True)
    init_file.write_text('__version__ = "0.5.0"\n', encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.working_tree_clean",
        lambda root: True,
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.branch_exists",
        lambda root, branch: False,
    )
    monkeypatch.setattr("repo_release_tools.commands.bump.git.current_branch", lambda root: "main")
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.run",
        lambda cmd, root, *, dry_run, label: "",
    )

    result = cmd_bump(
        Namespace(
            bump="minor",
            dry_run=False,
            no_commit=True,
            no_changelog=True,
            no_update=True,
            include_maintenance=False,
            base_branch=None,
            group=None,
        ),
    )

    assert result == 0
    assert 'version = "0.6.0"' in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert '__version__ = "0.6.0"' in init_file.read_text(encoding="utf-8")


def test_cmd_bump_go_version_kind(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """bump updates const Version in a Go file when kind='go_version' is configured."""
    ver_file = tmp_path / "internal" / "version" / "version.go"
    ver_file.parent.mkdir(parents=True)
    ver_file.write_text('package version\n\nconst Version = "0.1.0"\n', encoding="utf-8")

    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]
release_branch = "release/v{version}"
lock_command = []

[[tool.rrt.version_targets]]
path = "internal/version/version.go"
kind = "go_version"
""",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.working_tree_clean",
        lambda root: True,
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.branch_exists",
        lambda root, branch: False,
    )
    monkeypatch.setattr("repo_release_tools.commands.bump.git.current_branch", lambda root: "main")
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.run",
        lambda cmd, root, *, dry_run, label: "",
    )

    result = cmd_bump(
        Namespace(
            bump="major",
            dry_run=False,
            no_commit=True,
            no_changelog=True,
            no_update=True,
            include_maintenance=False,
            base_branch=None,
            group=None,
        ),
    )

    assert result == 0
    assert 'const Version = "1.0.0"' in ver_file.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# update_changelog – empty [Unreleased] and health-mode tests
# ---------------------------------------------------------------------------


def test_update_changelog_inserts_after_empty_unreleased(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """When [Unreleased] exists but is empty, the generated section goes after it."""
    from repo_release_tools.commands.bump import update_changelog
    from repo_release_tools.config import RrtConfig, VersionGroup, VersionTarget

    changelog = tmp_path / "CHANGELOG.md"
    # Simulates state left by promote_unreleased: empty [Unreleased] at the top.
    changelog.write_text(
        "# Changelog\n\n## [Unreleased]\n\n## [1.0.0] - 2025-01-01\n\n### Added\n- init\n",
        encoding="utf-8",
    )

    target = VersionTarget(path=tmp_path / "pyproject.toml", kind="pep621")
    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=changelog,
        lock_command=[],
        generated_files=[],
        version_targets=[target],
    )
    config = RrtConfig(
        root=tmp_path,
        config_file=tmp_path / "pyproject.toml",
        version_groups=[group],
        default_group_name="default",
    )

    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git_log_since_latest_tag",
        lambda root: ["feat: brand new feature"],
    )

    update_changelog(config, "1.1.0", include_maintenance=False, dry_run=False)

    content = changelog.read_text(encoding="utf-8")
    # [Unreleased] must still be at the top (after the title).
    assert content.index("## [Unreleased]") < content.index("## [1.1.0]")
    # New version must appear before the old version.
    assert content.index("## [1.1.0]") < content.index("## [1.0.0]")


def test_update_changelog_adds_unreleased_placeholder_when_absent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """When no [Unreleased] section exists the bump adds a health-mode placeholder."""
    from repo_release_tools.changelog import has_unreleased_section
    from repo_release_tools.commands.bump import update_changelog
    from repo_release_tools.config import RrtConfig, VersionGroup, VersionTarget

    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n## [1.0.0] - 2025-01-01\n\n### Added\n- init\n",
        encoding="utf-8",
    )

    target = VersionTarget(path=tmp_path / "pyproject.toml", kind="pep621")
    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=changelog,
        lock_command=[],
        generated_files=[],
        version_targets=[target],
    )
    config = RrtConfig(
        root=tmp_path,
        config_file=tmp_path / "pyproject.toml",
        version_groups=[group],
        default_group_name="default",
    )

    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git_log_since_latest_tag",
        lambda root: ["feat: something new"],
    )

    update_changelog(config, "1.1.0", include_maintenance=False, dry_run=False)

    content = changelog.read_text(encoding="utf-8")
    # A fresh [Unreleased] placeholder must now be present (health mode).
    assert has_unreleased_section(content)
    # New version must appear before the old version.
    assert content.index("## [1.1.0]") < content.index("## [1.0.0]")


# ---------------------------------------------------------------------------
# update_changelog – changelog_mode tests
# ---------------------------------------------------------------------------


def _make_config(tmp_path: Path, changelog: Path) -> RrtConfig:
    from repo_release_tools.config import RrtConfig, VersionGroup, VersionTarget

    target = VersionTarget(path=tmp_path / "pyproject.toml", kind="pep621")
    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=changelog,
        lock_command=[],
        generated_files=[],
        version_targets=[target],
    )
    return RrtConfig(
        root=tmp_path,
        config_file=tmp_path / "pyproject.toml",
        version_groups=[group],
        default_group_name="default",
    )


def test_update_changelog_mode_promote_with_entries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """promote mode promotes [Unreleased] when entries are present."""
    from repo_release_tools.commands.bump import update_changelog

    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Added\n- great thing\n\n## [1.0.0] - 2025-01-01\n",
        encoding="utf-8",
    )
    config = _make_config(tmp_path, changelog)

    update_changelog(
        config,
        "1.1.0",
        include_maintenance=False,
        dry_run=False,
        changelog_mode="promote",
    )

    content = changelog.read_text(encoding="utf-8")
    assert "## [1.1.0]" in content
    assert "great thing" in content
    assert "## [Unreleased]" in content  # fresh placeholder re-inserted


def test_update_changelog_mode_promote_empty_section_warns(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """promote mode with empty [Unreleased] prints a warning and skips writing."""
    from repo_release_tools.commands.bump import update_changelog

    changelog = tmp_path / "CHANGELOG.md"
    original = "# Changelog\n\n## [Unreleased]\n\n## [1.0.0] - 2025-01-01\n"
    changelog.write_text(original, encoding="utf-8")
    config = _make_config(tmp_path, changelog)

    update_changelog(
        config,
        "1.1.0",
        include_maintenance=False,
        dry_run=False,
        changelog_mode="promote",
    )

    assert changelog.read_text(encoding="utf-8") == original  # unchanged


def test_update_changelog_mode_promote_no_section_warns(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """promote mode with no [Unreleased] section prints a warning and skips writing."""
    from repo_release_tools.commands.bump import update_changelog

    changelog = tmp_path / "CHANGELOG.md"
    original = "# Changelog\n\n## [1.0.0] - 2025-01-01\n"
    changelog.write_text(original, encoding="utf-8")
    config = _make_config(tmp_path, changelog)

    update_changelog(
        config,
        "1.1.0",
        include_maintenance=False,
        dry_run=False,
        changelog_mode="promote",
    )

    assert changelog.read_text(encoding="utf-8") == original  # unchanged


def test_update_changelog_mode_generate_ignores_unreleased(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """generate mode always writes from git log, even with a non-empty [Unreleased]."""
    from repo_release_tools.commands.bump import update_changelog

    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git_log_since_latest_tag",
        lambda root: ["feat: from git log"],
    )
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Added\n- manual entry\n",
        encoding="utf-8",
    )
    config = _make_config(tmp_path, changelog)

    update_changelog(
        config,
        "1.1.0",
        include_maintenance=False,
        dry_run=False,
        changelog_mode="generate",
    )

    content = changelog.read_text(encoding="utf-8")
    assert "from git log" in content
    assert "## [1.1.0]" in content


def test_cmd_bump_defaults_to_generate_for_squash_workflow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = VersionTarget(path=tmp_path / "pyproject.toml", kind="pep621")
    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=tmp_path / "CHANGELOG.md",
        lock_command=[],
        generated_files=[],
        version_targets=[target],
        changelog_workflow="squash",
    )
    config = RrtConfig(
        root=tmp_path,
        config_file=tmp_path / ".rrt.toml",
        version_groups=[group],
        default_group_name="default",
    )
    changelog_modes: list[str] = []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.load_or_autodetect_config",
        lambda root: config,
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.read_group_current_version",
        lambda grp: Version.parse("1.0.0"),
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.replace_all_versions_atomic",
        lambda target, version, dry_run: [],
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.update_changelog",
        lambda config, version, *, include_maintenance, dry_run, changelog_mode: (
            changelog_modes.append(changelog_mode)
        ),
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.working_tree_clean",
        lambda root: True,
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.branch_exists",
        lambda root, branch: False,
    )
    monkeypatch.setattr("repo_release_tools.commands.bump.git.current_branch", lambda root: "main")
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.run_preflight",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.run",
        lambda cmd, root, *, dry_run, label: "",
    )

    result = cmd_bump(
        Namespace(
            bump="patch",
            dry_run=False,
            force=False,
            no_commit=True,
            no_changelog=False,
            no_update=True,
            no_pin_sync=True,
            include_maintenance=False,
            base_branch=None,
            group=None,
        ),
    )

    assert result == 0
    assert changelog_modes == ["generate"]


# ---------------------------------------------------------------------------
# update_changelog – RST format
# ---------------------------------------------------------------------------


def test_update_changelog_generates_rst_section(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """For a .rst changelog the generated section must use RST underline notation."""
    from repo_release_tools.changelog import ChangelogFormat, has_unreleased_section
    from repo_release_tools.commands.bump import update_changelog

    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git_log_since_latest_tag",
        lambda root: ["feat: rst release"],
    )
    changelog = tmp_path / "CHANGELOG.rst"
    changelog.write_text(
        "Changelog\n=========\n\n1.0.0 - 2025-01-01\n-------------------\n\nAdded\n~~~~~\n\n- init\n",
        encoding="utf-8",
    )
    config = _make_config(tmp_path, changelog)

    update_changelog(config, "1.1.0", include_maintenance=False, dry_run=False)

    content = changelog.read_text(encoding="utf-8")
    assert "## [" not in content
    assert "### " not in content
    assert "1.1.0" in content
    assert has_unreleased_section(content, ChangelogFormat.RST)
    assert content.index("Unreleased") < content.index("1.1.0") < content.index("1.0.0")


def test_update_changelog_generates_txt_section(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """For a .txt changelog the generated section must use RST underline notation."""
    from repo_release_tools.commands.bump import update_changelog

    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git_log_since_latest_tag",
        lambda root: ["fix: txt fix"],
    )
    changelog = tmp_path / "CHANGELOG.txt"
    changelog.write_text(
        "Changelog\n=========\n\n1.0.0 - 2025-01-01\n-------------------\n\n- init\n",
        encoding="utf-8",
    )
    config = _make_config(tmp_path, changelog)

    update_changelog(config, "1.1.0", include_maintenance=False, dry_run=False)

    content = changelog.read_text(encoding="utf-8")
    assert "## [" not in content
    assert "txt fix" in content


# ---------------------------------------------------------------------------
# pin_targets — integration with cmd_bump
# ---------------------------------------------------------------------------

_BUMP_CONFIG_WITH_PINS = """\
[tool.rrt]
release_branch = "release/v{{version}}"
changelog_file = "CHANGELOG.md"
lock_command = []

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[[tool.rrt.pin_targets]]
path = "docs/action.md"
pattern = '(Anselmoo/repo-release-tools@v)(\\d+\\.\\d+\\.\\d+)()'

[project]
name = "example"
version = "0.1.0"
"""


def _setup_pin_bump(tmp_path: Path) -> Path:
    """Create a minimal project with a pin_targets doc file."""
    (tmp_path / "pyproject.toml").write_text(_BUMP_CONFIG_WITH_PINS, encoding="utf-8")
    docs = tmp_path / "docs"
    docs.mkdir()
    doc = docs / "action.md"
    doc.write_text("- uses: Anselmoo/repo-release-tools@v0.1.0\n", encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Added\n- new feature\n",
        encoding="utf-8",
    )
    return doc


def test_cmd_bump_updates_pin_targets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """cmd_bump should update pin_targets files to the new version."""
    doc = _setup_pin_bump(tmp_path)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.working_tree_clean",
        lambda root: True,
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.branch_exists",
        lambda root, branch: False,
    )
    monkeypatch.setattr("repo_release_tools.commands.bump.git.current_branch", lambda root: "main")
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.run",
        lambda cmd, root, *, dry_run, label: "",
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git_log_since_latest_tag",
        lambda root: [],
    )

    args = Namespace(
        bump="minor",
        dry_run=False,
        no_commit=True,
        no_changelog=True,
        no_update=True,
        no_pin_sync=False,
        include_maintenance=False,
        base_branch=None,
        group=None,
    )
    result = cmd_bump(args)

    assert result == 0
    assert "v0.2.0" in doc.read_text(encoding="utf-8")


def test_cmd_bump_dry_run_does_not_write_pin_targets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """In dry-run mode, pin_targets files must not be modified."""
    doc = _setup_pin_bump(tmp_path)
    original_doc = doc.read_text(encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.working_tree_clean",
        lambda root: True,
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.branch_exists",
        lambda root, branch: False,
    )
    monkeypatch.setattr("repo_release_tools.commands.bump.git.current_branch", lambda root: "main")
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.run",
        lambda cmd, root, *, dry_run, label: "",
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git_log_since_latest_tag",
        lambda root: [],
    )

    args = Namespace(
        bump="minor",
        dry_run=True,
        no_commit=True,
        no_changelog=True,
        no_update=True,
        no_pin_sync=False,
        include_maintenance=False,
        base_branch=None,
        group=None,
    )
    result = cmd_bump(args)

    assert result == 0
    # File must be untouched in dry-run
    assert doc.read_text(encoding="utf-8") == original_doc
    assert "Would update" in capsys.readouterr().out


def test_cmd_bump_no_pin_sync_skips_pin_targets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """--no-pin-sync must skip all pin_targets updates."""
    doc = _setup_pin_bump(tmp_path)
    original_doc = doc.read_text(encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.working_tree_clean",
        lambda root: True,
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.branch_exists",
        lambda root, branch: False,
    )
    monkeypatch.setattr("repo_release_tools.commands.bump.git.current_branch", lambda root: "main")
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.run",
        lambda cmd, root, *, dry_run, label: "",
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git_log_since_latest_tag",
        lambda root: [],
    )

    args = Namespace(
        bump="minor",
        dry_run=False,
        no_commit=True,
        no_changelog=True,
        no_update=True,
        no_pin_sync=True,
        include_maintenance=False,
        base_branch=None,
        group=None,
    )
    result = cmd_bump(args)

    assert result == 0
    # Doc file must be untouched when --no-pin-sync is set
    assert doc.read_text(encoding="utf-8") == original_doc


def test_cmd_bump_deduplicates_pin_updates_and_stage_entries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Duplicate group/global pins should only update and stage once."""
    version_file = tmp_path / "pyproject.toml"
    version_file.write_text('[project]\nname = "example"\nversion = "1.0.0"\n', encoding="utf-8")
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n", encoding="utf-8")
    pin_file = tmp_path / "docs" / "action.md"
    pin_file.parent.mkdir(parents=True)
    pin_file.write_text("uses: Anselmoo/repo-release-tools@v1.0.0\n", encoding="utf-8")

    target = VersionTarget(path=version_file, kind="pep621")
    duplicate_pin = PinTarget(
        path=pin_file,
        pattern=r"(Anselmoo/repo-release-tools@v)(\d+\.\d+\.\d+)()",
    )
    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=changelog,
        lock_command=[],
        generated_files=[],
        version_targets=[target],
        pin_targets=[duplicate_pin],
    )
    config = RrtConfig(
        root=tmp_path,
        config_file=tmp_path / ".rrt.toml",
        version_groups=[group],
        default_group_name="default",
        global_pin_targets=[duplicate_pin],
    )

    pin_updates: list[tuple[Path, str, bool]] = []
    git_calls: list[list[str]] = []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.load_or_autodetect_config",
        lambda root: config,
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.read_group_current_version",
        lambda grp: Version.parse("1.0.0"),
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.replace_all_versions_atomic",
        lambda target, version, dry_run: [],
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.replace_pin_in_file",
        lambda pin, version, dry_run, pin_target_missing="error": pin_updates.append(
            (pin.path, version, dry_run)
        ),
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.working_tree_clean",
        lambda root: True,
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.branch_exists",
        lambda root, branch: False,
    )
    monkeypatch.setattr("repo_release_tools.commands.bump.git.current_branch", lambda root: "main")
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.run",
        lambda cmd, root, *, dry_run, label: git_calls.append(cmd),
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.run_preflight",
        lambda *args, **kwargs: None,
    )

    result = cmd_bump(
        Namespace(
            bump="patch",
            dry_run=False,
            force=False,
            no_commit=True,
            no_changelog=True,
            no_update=True,
            no_pin_sync=False,
            include_maintenance=False,
            base_branch=None,
            group=None,
        ),
    )

    assert result == 0
    assert pin_updates == [(pin_file, "1.0.1", False)]
    add_calls = [cmd for cmd in git_calls if cmd[:2] == ["git", "add"]]
    assert add_calls
    assert add_calls[-1].count("docs/action.md") == 1


def test_cmd_bump_uses_inline_lock_spinner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    version_file_a = tmp_path / "pyproject.toml"
    version_file_b = tmp_path / "src" / "example" / "__init__.py"
    version_file_b.parent.mkdir(parents=True)
    changelog = tmp_path / "CHANGELOG.md"
    pin_file = tmp_path / "docs" / "action.md"
    pin_file_two = tmp_path / "docs" / "guide.md"
    pin_file.parent.mkdir(parents=True)

    version_file_a.write_text('[project]\nname = "example"\nversion = "1.0.0"\n', encoding="utf-8")
    version_file_b.write_text('__version__ = "1.0.0"\n', encoding="utf-8")
    changelog.write_text("# Changelog\n", encoding="utf-8")
    pin_file.write_text("uses: Anselmoo/repo-release-tools@v1.0.0\n", encoding="utf-8")
    pin_file_two.write_text("uses: Anselmoo/repo-release-tools@v1.0.0\n", encoding="utf-8")

    target_a = VersionTarget(path=version_file_a, kind="pep621")
    target_b = VersionTarget(path=version_file_b, kind="python_version")
    pin_target = PinTarget(
        path=pin_file,
        pattern=r"(Anselmoo/repo-release-tools@v)(\d+\.\d+\.\d+)()",
    )
    pin_target_two = PinTarget(
        path=pin_file_two,
        pattern=r"(Anselmoo/repo-release-tools@v)(\d+\.\d+\.\d+)()",
    )
    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=changelog,
        lock_command=["uv", "lock", "-U"],
        generated_files=[],
        version_targets=[target_a, target_b],
        pin_targets=[pin_target, pin_target_two],
    )
    config = RrtConfig(
        root=tmp_path,
        config_file=tmp_path / ".rrt.toml",
        version_groups=[group],
        default_group_name="default",
    )

    spinner_calls: list[tuple[str, str | None, object]] = []
    git_calls: list[tuple[list[str], bool]] = []

    @contextmanager
    def fake_spinner_lines(
        label: str,
        *,
        detail: str | None = None,
        file: object = None,
    ) -> Generator[None, None, None]:
        spinner_calls.append((label, detail, file))
        yield

    def fake_git_run(
        cmd: list[str],
        root: Path,
        *,
        dry_run: bool,
        label: str,
        suppress_announce: bool = False,
    ) -> str:
        git_calls.append((cmd, suppress_announce))
        return ""

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.load_or_autodetect_config",
        lambda root: config,
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.read_group_current_version",
        lambda grp: Version.parse("1.0.0"),
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.working_tree_clean",
        lambda root: True,
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.branch_exists",
        lambda root, branch: False,
    )
    monkeypatch.setattr("repo_release_tools.commands.bump.git.current_branch", lambda root: "main")
    monkeypatch.setattr("repo_release_tools.commands.bump.spinner_lines", fake_spinner_lines)
    monkeypatch.setattr("repo_release_tools.commands.bump.git.run", fake_git_run)
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.run_preflight",
        lambda *args, **kwargs: None,
    )

    result = cmd_bump(
        Namespace(
            bump="patch",
            dry_run=False,
            force=False,
            no_commit=True,
            no_changelog=True,
            no_update=False,
            no_pin_sync=False,
            include_maintenance=False,
            base_branch=None,
            group=None,
        ),
    )

    assert result == 0
    assert spinner_calls == [("Running lock command…", "$ uv lock -U", sys.stdout)]
    assert (["uv", "lock", "-U"], True) in git_calls


# ---------------------------------------------------------------------------
# CalVer bump path in cmd_bump
# ---------------------------------------------------------------------------


def test_cmd_bump_calver_from_semver_version(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """bump calver from a semver-style current version uses CalVersion.today()."""
    init_file = tmp_path / "src" / "pkg" / "__init__.py"
    init_file.parent.mkdir(parents=True)
    init_file.write_text('__version__ = "1.0.0"\n', encoding="utf-8")

    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "pkg"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.working_tree_clean", lambda root: True
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.branch_exists", lambda root, branch: False
    )
    monkeypatch.setattr("repo_release_tools.commands.bump.git.current_branch", lambda root: "main")
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.run", lambda cmd, root, *, dry_run, label: ""
    )

    result = cmd_bump(
        Namespace(
            bump="calver",
            calver_scheme="YYYY.MM.DD",
            dry_run=False,
            no_commit=True,
            no_changelog=True,
            no_update=True,
            include_maintenance=False,
            base_branch=None,
            group=None,
        ),
    )

    assert result == 0
    # The version file should now contain a calver-style version
    new_content = init_file.read_text(encoding="utf-8")
    import re

    assert re.search(r"\d{4}\.\d{2}\.\d{2}", new_content), f"CalVer not found in {new_content!r}"


def test_cmd_bump_calver_from_calver_version(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """bump calver from a calver-style current version calls .bump() (else branch)."""
    init_file = tmp_path / "src" / "pkg" / "__init__.py"
    init_file.parent.mkdir(parents=True)
    init_file.write_text('__version__ = "2026.5.1"\n', encoding="utf-8")

    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "pkg"\nversion = "2026.5.1"\n',
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.working_tree_clean", lambda root: True
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.branch_exists", lambda root, branch: False
    )
    monkeypatch.setattr("repo_release_tools.commands.bump.git.current_branch", lambda root: "main")
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.run", lambda cmd, root, *, dry_run, label: ""
    )

    result = cmd_bump(
        Namespace(
            bump="calver",
            calver_scheme="YYYY.M.D",
            dry_run=False,
            no_commit=True,
            no_changelog=True,
            no_update=True,
            include_maintenance=False,
            base_branch=None,
            group=None,
        ),
    )

    assert result == 0
    new_content = init_file.read_text(encoding="utf-8")
    import re

    assert re.search(r"\d{4}\.\d+\.\d+", new_content), f"CalVer not found in {new_content!r}"
