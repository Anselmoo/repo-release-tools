"""Tests for `rrt release repair` (verify-and-fix + recreate modes)."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from repo_release_tools.changelog import ChangelogFormat
from repo_release_tools.commands import release_repair
from repo_release_tools.config import PinTarget, RrtConfig, VersionGroup, VersionTarget

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_RRT_TOML = """\
[tool.rrt]
release_branch = "release/v{version}"
lock_command = []

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[[tool.rrt.pin_targets]]
path = "docs/install.md"
pattern = '(rrt@v)(\\d+\\.\\d+\\.\\d+)()'
"""

_CHANGELOG = """\
# Changelog

## [Unreleased]

## [1.9.0] - 2026-06-10
### Added
- release-notes selector
- tree json/flat formats
- project info

## [1.8.3] - 2026-06-06
"""


def _args(**overrides: object) -> argparse.Namespace:
    """Build a Namespace with every CLI flag defaulted, then override."""
    base: dict[str, object] = {
        "from_ref": None,
        "yes": False,
        "hotfix": False,
        "changelog_from": None,
        "force_allow_pushed": False,
        "no_backup": False,
        "group": None,
        "verbose": 0,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def _seed_repo(
    tmp_path: Path,
    *,
    pyproject_version: str = "1.9.0",
    install_pin_version: str = "1.9.0",
    changelog: str = _CHANGELOG,
) -> None:
    """Write a self-contained mini-repo to *tmp_path*."""
    (tmp_path / ".rrt.toml").write_text(_RRT_TOML, encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "demo"\nversion = "{pyproject_version}"\n',
        encoding="utf-8",
    )
    (tmp_path / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "docs" / "install.md").write_text(f"rrt@v{install_pin_version}\n", encoding="utf-8")


def _patch_git(
    monkeypatch: pytest.MonkeyPatch,
    *,
    clean: bool = True,
    current_branch: str = "release/v1.9.0",
    base_ref_exists: bool = True,
    upstream_ahead: bool = False,
    upstream_exists: bool = False,
) -> list[list[str]]:
    """Stub the git helpers used by release_repair. Returns the recorded calls."""
    calls: list[list[str]] = []

    monkeypatch.setattr(
        "repo_release_tools.commands.release_repair.git.working_tree_clean",
        lambda root: clean,
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.release_repair.git.current_branch",
        lambda root: current_branch,
    )

    def fake_ref_exists(root: Path, ref: str) -> bool:
        if ref.startswith("origin/"):
            return upstream_exists
        return base_ref_exists

    monkeypatch.setattr(
        "repo_release_tools.commands.release_repair.git.ref_exists",
        fake_ref_exists,
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.release_repair.git.commits_ahead",
        lambda root, ref: ["a1b2c3 feat: stray"] if upstream_ahead else [],
    )

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

    monkeypatch.setattr(
        "repo_release_tools.commands.release_repair.git.run",
        fake_run,
    )
    return calls


# ---------------------------------------------------------------------------
# Pre-flight blockers
# ---------------------------------------------------------------------------


def test_repair_refuses_dirty_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    _patch_git(monkeypatch, clean=False)
    rc = release_repair.cmd_release_repair(_args())
    err = capsys.readouterr().err
    assert rc == 1
    assert "Commit or stash" in err


def test_repair_refuses_when_base_ref_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    _patch_git(monkeypatch, base_ref_exists=False)
    rc = release_repair.cmd_release_repair(_args(from_ref="bogus"))
    err = capsys.readouterr().err
    assert rc == 1
    assert "base ref 'bogus' not found" in err


def test_repair_refuses_when_branch_is_ahead_of_remote(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    _patch_git(monkeypatch, upstream_exists=True, upstream_ahead=True)
    rc = release_repair.cmd_release_repair(_args(from_ref="main"))
    err = capsys.readouterr().err
    assert rc == 1
    assert "--force-allow-pushed" in err


def test_force_allow_pushed_overrides_remote_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--force-allow-pushed` lets the recreate proceed and prints the push reminder."""
    _seed_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    calls = _patch_git(monkeypatch, upstream_exists=True, upstream_ahead=True)
    rc = release_repair.cmd_release_repair(
        _args(from_ref="main", yes=True, force_allow_pushed=True, no_backup=True)
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert any(cmd[:3] == ["git", "reset", "--hard"] for cmd in calls)
    assert "force-with-lease" in out


# ---------------------------------------------------------------------------
# Verify mode
# ---------------------------------------------------------------------------


def test_verify_no_drift_reports_clean_and_exits_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No drift across version/pin/changelog → exit 0, no git mutations."""
    _seed_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    calls = _patch_git(monkeypatch)
    rc = release_repair.cmd_release_repair(_args())
    assert rc == 0
    assert "No drift detected" in capsys.readouterr().out
    assert calls == []


def test_verify_detects_version_target_drift_in_preview(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A version-target mismatch shows up in the report and exits 1."""
    _seed_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    calls = _patch_git(monkeypatch)
    # Manually demote the pyproject so the declared version (read from the
    # first target) diverges from the pin target.
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.9.0"\n', encoding="utf-8"
    )
    (tmp_path / "docs" / "install.md").write_text("rrt@v1.8.3\n", encoding="utf-8")
    rc = release_repair.cmd_release_repair(_args())
    out = capsys.readouterr().out
    assert rc == 1
    assert "pin_target" in out
    assert "install.md" in out
    assert calls == []


def test_verify_with_yes_writes_fixes_and_commits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Pin drift + `--yes` → file rewritten, repair commit recorded."""
    _seed_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs" / "install.md").write_text("rrt@v1.8.3\n", encoding="utf-8")
    calls = _patch_git(monkeypatch)
    rc = release_repair.cmd_release_repair(_args(yes=True))
    assert rc == 0
    assert "rrt@v1.9.0" in (tmp_path / "docs" / "install.md").read_text(encoding="utf-8")
    commit_calls = [c for c in calls if c[:2] == ["git", "commit"]]
    assert commit_calls
    assert commit_calls[0][-1] == "chore(release): repair v1.9.0"
    _ = capsys.readouterr()


def test_verify_detects_dirty_unreleased(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A non-empty `[Unreleased]` after a release is drift."""
    polluted = (
        "# Changelog\n\n"
        "## [Unreleased]\n"
        "- forgotten entry\n\n"
        "## [1.9.0] - 2026-06-10\n"
        "### Added\n- shipped\n"
    )
    _seed_repo(tmp_path, changelog=polluted)
    monkeypatch.chdir(tmp_path)
    _patch_git(monkeypatch)
    rc = release_repair.cmd_release_repair(_args())
    out = capsys.readouterr().out
    assert rc == 1
    assert "changelog_unreleased_dirty" in out


# ---------------------------------------------------------------------------
# Recreate mode
# ---------------------------------------------------------------------------


def test_recreate_dry_run_shows_plan_and_no_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    calls = _patch_git(monkeypatch)
    rc = release_repair.cmd_release_repair(_args(from_ref="main"))
    out = capsys.readouterr().out
    assert rc == 1
    assert "Preview only" in out
    assert calls == []


def test_recreate_creates_backup_and_resets_to_base(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    calls = _patch_git(monkeypatch)
    rc = release_repair.cmd_release_repair(_args(from_ref="main", yes=True))
    assert rc == 0
    cmd_strs = [" ".join(c) for c in calls]
    assert any(
        c.startswith("git update-ref refs/heads/repair/backup/release-v1.9.0-") for c in cmd_strs
    )
    assert ["git", "reset", "--hard", "main"] in calls
    commit_calls = [c for c in calls if c[:2] == ["git", "commit"]]
    assert commit_calls[0][-1] == "chore: bump version to v1.9.0"
    _ = capsys.readouterr()


def test_recreate_preserves_version_section_in_changelog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    _patch_git(monkeypatch)
    rc = release_repair.cmd_release_repair(_args(from_ref="main", yes=True, no_backup=True))
    assert rc == 0
    rebuilt = (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## [1.9.0]" in rebuilt
    assert "release-notes selector" in rebuilt
    assert "tree json/flat formats" in rebuilt
    _ = capsys.readouterr()


def test_recreate_uses_changelog_from_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When `--changelog-from PATH` is set, body comes from PATH not HEAD."""
    saved = tmp_path / "saved-CHANGELOG.md"
    saved.write_text(
        "# Changelog\n\n## [1.9.0] - 2026-06-10\n### Added\n- saved entry\n",
        encoding="utf-8",
    )
    # Polluted HEAD has no [1.9.0] entry — would normally fail.
    polluted = "# Changelog\n\n## [Unreleased]\n\n## [1.8.3] - 2026-06-06\n"
    _seed_repo(tmp_path, changelog=polluted)
    monkeypatch.chdir(tmp_path)
    _patch_git(monkeypatch)
    rc = release_repair.cmd_release_repair(
        _args(from_ref="main", yes=True, no_backup=True, changelog_from=str(saved))
    )
    assert rc == 0
    rebuilt = (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "saved entry" in rebuilt
    _ = capsys.readouterr()


def test_recreate_refuses_when_section_missing_no_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    polluted = "# Changelog\n\n## [Unreleased]\n\n## [1.8.3] - 2026-06-06\n"
    _seed_repo(tmp_path, changelog=polluted)
    monkeypatch.chdir(tmp_path)
    _patch_git(monkeypatch)
    rc = release_repair.cmd_release_repair(_args(from_ref="main", yes=True))
    err = capsys.readouterr().err
    assert rc == 1
    assert "no [1.9.0] section" in err.lower()


def test_recreate_refuses_when_changelog_from_file_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    _patch_git(monkeypatch)
    rc = release_repair.cmd_release_repair(
        _args(from_ref="main", yes=True, changelog_from=str(tmp_path / "nope.md"))
    )
    assert rc == 1
    err = capsys.readouterr().err
    assert "no [1.9.0] section" in err.lower()


# ---------------------------------------------------------------------------
# Modes & flags
# ---------------------------------------------------------------------------


def test_hotfix_implies_yes_and_uses_repair_commit_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    calls = _patch_git(monkeypatch)
    rc = release_repair.cmd_release_repair(_args(from_ref="main", hotfix=True, no_backup=True))
    assert rc == 0
    commit_calls = [c for c in calls if c[:2] == ["git", "commit"]]
    assert commit_calls[0][-1] == "chore(release): repair v1.9.0"
    _ = capsys.readouterr()


def test_no_backup_skips_ref_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    calls = _patch_git(monkeypatch)
    rc = release_repair.cmd_release_repair(_args(from_ref="main", yes=True, no_backup=True))
    assert rc == 0
    assert not any(c[:2] == ["git", "update-ref"] for c in calls)
    _ = capsys.readouterr()


def test_group_required_when_multiple_groups(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Multi-group config without `--group` fails before any git work."""
    multi_rrt = """\
[tool.rrt]
default_group = "api"

[[tool.rrt.version_groups]]
name = "api"
release_branch = "release/api-v{version}"
version_source = "pyproject.toml"

[[tool.rrt.version_groups.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[[tool.rrt.version_groups]]
name = "web"
release_branch = "release/web-v{version}"
version_source = "package.json"

[[tool.rrt.version_groups.version_targets]]
path = "package.json"
kind = "package_json"
"""
    (tmp_path / ".rrt.toml").write_text(multi_rrt, encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.9.0"\n', encoding="utf-8"
    )
    (tmp_path / "package.json").write_text(
        '{ "name": "demo", "version": "1.9.0" }\n', encoding="utf-8"
    )
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## [Unreleased]\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    _patch_git(monkeypatch)
    rc = release_repair.cmd_release_repair(_args())
    err = capsys.readouterr().err
    assert rc == 1
    assert "multiple version groups" in err


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_drift_dataclass_is_frozen() -> None:
    """Drift is a frozen dataclass — assignments are rejected at runtime."""
    import dataclasses

    d = release_repair.Drift("version_target", "pyproject.toml", "1.9.0", "1.8.0")
    with pytest.raises(dataclasses.FrozenInstanceError):
        object.__setattr__  # used implicitly to confirm normal assignment fails
        setattr(d, "kind", "pin_target")


def test_stamp_version_section_markdown_uses_today_and_body() -> None:
    base = "# Changelog\n\n## [Unreleased]\n\n## [1.8.3] - 2026-06-06\n"
    result = release_repair._stamp_version_section(
        base, "1.9.0", "### Added\n- thing", ChangelogFormat.MARKDOWN
    )
    assert "## [1.9.0]" in result
    assert "- thing" in result
    # The version section lands after [Unreleased] and before [1.8.3].
    unreleased_pos = result.index("[Unreleased]")
    v190_pos = result.index("[1.9.0]")
    v183_pos = result.index("[1.8.3]")
    assert unreleased_pos < v190_pos < v183_pos


def test_stamp_version_section_rst_uses_dash_underline() -> None:
    base = "Changelog\n=========\n\nUnreleased\n----------\n"
    result = release_repair._stamp_version_section(base, "1.9.0", "- thing", ChangelogFormat.RST)
    assert "1.9.0 -" in result
    assert "------------------" in result  # dashes under the new header


def test_unique_pins_dedupes_by_path_and_pattern(tmp_path: Path) -> None:
    target = VersionTarget(path=tmp_path / "pyproject.toml", kind="pep621")
    pin = PinTarget(path=tmp_path / "README.md", pattern=r"(rrt@v)(\d+\.\d+\.\d+)")
    pin_dup = PinTarget(path=tmp_path / "README.md", pattern=r"(rrt@v)(\d+\.\d+\.\d+)")
    pin_other = PinTarget(path=tmp_path / "docs.md", pattern=r"(rrt@v)(\d+\.\d+\.\d+)")
    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=tmp_path / "CHANGELOG.md",
        lock_command=[],
        generated_files=[],
        version_targets=[target],
        pin_targets=[pin, pin_dup],
    )
    config = RrtConfig(
        root=tmp_path,
        config_file=tmp_path / ".rrt.toml",
        version_groups=[group],
        default_group_name="default",
        global_pin_targets=[pin_other],
    )
    result = release_repair._unique_pins(group, config)
    assert [p.path.name for p in result] == ["README.md", "docs.md"]


def test_files_to_stage_skips_missing_files(tmp_path: Path) -> None:
    """Only files that actually exist on disk get staged."""
    target = VersionTarget(path=tmp_path / "pyproject.toml", kind="pep621")
    pin_present = PinTarget(path=tmp_path / "README.md", pattern=r"(rrt@v)(\d+\.\d+\.\d+)")
    pin_missing = PinTarget(path=tmp_path / "gone.md", pattern=r"(rrt@v)(\d+\.\d+\.\d+)")
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    (tmp_path / "README.md").write_text("", encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text("", encoding="utf-8")
    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=tmp_path / "CHANGELOG.md",
        lock_command=[],
        generated_files=[],
        version_targets=[target],
        pin_targets=[pin_present, pin_missing],
    )
    files = release_repair._files_to_stage(group, tmp_path, [pin_present, pin_missing])
    assert "pyproject.toml" in files
    assert "README.md" in files
    assert "CHANGELOG.md" in files
    assert "gone.md" not in files


def test_make_backup_ref_runs_git_update_ref(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], root: Path, **kwargs: object) -> str:
        calls.append(cmd)
        return ""

    monkeypatch.setattr("repo_release_tools.commands.release_repair.git.run", fake_run)
    name = release_repair._make_backup_ref(tmp_path, "release/v1.9.0")
    assert name.startswith("refs/heads/repair/backup/release-v1.9.0-")
    assert calls[0][:2] == ["git", "update-ref"]
    assert calls[0][2] == name


@pytest.mark.parametrize(
    ("hotfix", "mode", "expected"),
    [
        (False, "recreate", "chore: bump version to v1.9.0"),
        (True, "recreate", "chore(release): repair v1.9.0"),
        (False, "verify", "chore(release): repair v1.9.0"),
        (True, "verify", "chore(release): repair v1.9.0"),
    ],
)
def test_commit_message_variants(hotfix: bool, mode: str, expected: str) -> None:
    ns = argparse.Namespace(hotfix=hotfix)
    assert release_repair._commit_message(ns, "1.9.0", mode=mode) == expected


def test_register_subcommand_wires_handler() -> None:
    parser = argparse.ArgumentParser(prog="rrt-test")
    subparsers = parser.add_subparsers()
    release_repair.register_subcommand(subparsers)
    ns = parser.parse_args(["repair", "--from", "main", "--yes"])
    assert ns.from_ref == "main"
    assert ns.yes is True
    assert ns.handler is release_repair.cmd_release_repair


# ---------------------------------------------------------------------------
# Config / group failure paths
# ---------------------------------------------------------------------------


def test_repair_handles_missing_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Empty repo (no .rrt.toml, no pyproject) yields a guidance error."""
    monkeypatch.chdir(tmp_path)
    rc = release_repair.cmd_release_repair(_args())
    err = capsys.readouterr().err
    assert rc == 1
    assert err  # guidance lines printed


def test_repair_handles_missing_tool_rrt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """pyproject.toml without `[tool.rrt]` reports the missing-config guidance."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.9.0"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    rc = release_repair.cmd_release_repair(_args())
    err = capsys.readouterr().err
    assert rc == 1
    assert err


def test_repair_propagates_value_error_with_str(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A generic ValueError from config loading surfaces its message."""
    _seed_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.release_repair.load_or_autodetect_config",
        lambda _: (_ for _ in ()).throw(ValueError("totally bogus config")),
    )
    rc = release_repair.cmd_release_repair(_args())
    err = capsys.readouterr().err
    assert rc == 1
    assert "totally bogus config" in err


def test_repair_renders_missing_tool_rrt_guidance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When config loading raises MissingRrtConfigError, the guidance text appears."""
    from repo_release_tools.config import MissingRrtConfigError

    _seed_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.release_repair.load_or_autodetect_config",
        lambda _: (_ for _ in ()).throw(MissingRrtConfigError("missing tool rrt")),
    )
    rc = release_repair.cmd_release_repair(_args())
    err = capsys.readouterr().err
    assert rc == 1
    assert "No [tool.rrt]" in err


def test_repair_propagates_runtime_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A RuntimeError from config loading surfaces its message."""
    _seed_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.release_repair.load_or_autodetect_config",
        lambda _: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    rc = release_repair.cmd_release_repair(_args())
    err = capsys.readouterr().err
    assert rc == 1
    assert "boom" in err


def test_repair_propagates_resolve_group_value_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`resolve_group` ValueError (unknown group) surfaces to the user."""
    _seed_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = release_repair.cmd_release_repair(_args(group="missing"))
    err = capsys.readouterr().err
    assert rc == 1
    assert "missing" in err


def test_repair_refuses_group_without_version_targets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A resolved group with no version targets fails fast."""
    _seed_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.release_repair._verify_target_compatibility",
        lambda group: False,
    )
    rc = release_repair.cmd_release_repair(_args())
    err = capsys.readouterr().err
    assert rc == 1
    assert "no version targets configured" in err


# ---------------------------------------------------------------------------
# Drift coverage — extra cases
# ---------------------------------------------------------------------------


def test_verify_detects_version_target_drift_when_pyproject_lags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When the primary target version differs from declared, that drift is reported.

    The declared version is the one ``read_group_current_version`` returns
    (the primary target). To produce a version-target drift we mock the
    declared version to be different from what's on disk.
    """
    _seed_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    _patch_git(monkeypatch)
    monkeypatch.setattr(
        "repo_release_tools.commands.release_repair.read_group_current_version",
        lambda group: "9.9.9",
    )
    rc = release_repair.cmd_release_repair(_args())
    out = capsys.readouterr().out
    assert rc == 1
    assert "version_target" in out
    assert "9.9.9" in out


def test_verify_detects_unreadable_version_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An unreadable version target is reported as drift with `<unreadable>`."""
    _seed_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    _patch_git(monkeypatch)
    # Force read_version_string to raise — twice for _collect_drifts and
    # again for _targets_needing_rewrite (if invoked) so they both treat it
    # as drifted.
    monkeypatch.setattr(
        "repo_release_tools.commands.release_repair.read_version_string",
        lambda target: (_ for _ in ()).throw(RuntimeError("can't read")),
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.release_repair.read_group_current_version",
        lambda group: "1.9.0",
    )
    rc = release_repair.cmd_release_repair(_args())
    out = capsys.readouterr().out
    assert rc == 1
    assert "<unreadable>" in out


def test_verify_reports_missing_version_target_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A non-existent version-target file is reported as `<missing>`."""
    _seed_repo(tmp_path)
    (tmp_path / "pyproject.toml").unlink()
    # Bring back a stub so config can still load via .rrt.toml
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.9.0"\n', encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    _patch_git(monkeypatch)
    # After config load, mock the target's path resolver away — simulate a
    # missing file by patching `Path.exists` via a stub for the version target.
    real_exists = Path.exists

    def fake_exists(self: Path) -> bool:
        if self.name == "pyproject.toml":
            return False
        return real_exists(self)

    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr(
        "repo_release_tools.commands.release_repair.read_group_current_version",
        lambda group: "1.9.0",
    )
    rc = release_repair.cmd_release_repair(_args())
    out = capsys.readouterr().out
    assert rc == 1
    assert "<missing>" in out


def test_verify_reports_missing_pin_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A pin target whose file disappeared shows up as drift."""
    _seed_repo(tmp_path)
    (tmp_path / "docs" / "install.md").unlink()
    monkeypatch.chdir(tmp_path)
    _patch_git(monkeypatch)
    rc = release_repair.cmd_release_repair(_args())
    out = capsys.readouterr().out
    assert rc == 1
    assert "pin_target" in out
    assert "<missing>" in out


def test_verify_pin_pattern_no_match_is_silent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A pin file that exists but doesn't match the pattern is not drift."""
    _seed_repo(tmp_path)
    (tmp_path / "docs" / "install.md").write_text("no version pin here\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    _patch_git(monkeypatch)
    rc = release_repair.cmd_release_repair(_args())
    assert rc == 0
    assert "No drift" in capsys.readouterr().out


def test_verify_reports_missing_changelog_section(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A changelog with no `[VERSION]` block becomes a drift record."""
    polluted = "# Changelog\n\n## [Unreleased]\n\n## [1.8.3] - 2026-06-06\n"
    _seed_repo(tmp_path, changelog=polluted)
    monkeypatch.chdir(tmp_path)
    _patch_git(monkeypatch)
    rc = release_repair.cmd_release_repair(_args())
    out = capsys.readouterr().out
    assert rc == 1
    assert "changelog_missing_section" in out


def test_verify_with_yes_rewrites_changelog_when_section_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """In-place fix uses `--changelog-from` body to reconstruct the section."""
    polluted = "# Changelog\n\n## [Unreleased]\n\n## [1.8.3] - 2026-06-06\n"
    _seed_repo(tmp_path, changelog=polluted)
    saved = tmp_path / "saved.md"
    saved.write_text(
        "# Changelog\n\n## [1.9.0] - 2026-06-10\n### Added\n- saved\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    _patch_git(monkeypatch)
    rc = release_repair.cmd_release_repair(_args(yes=True, changelog_from=str(saved)))
    assert rc == 0
    body = (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "saved" in body
    _ = capsys.readouterr()


def test_verify_with_yes_rewrites_version_target_when_lagging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A primary version-target lagging declared version is rewritten in place."""
    _seed_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    _patch_git(monkeypatch)
    # Declared version (from primary target) is overridden to differ on purpose.
    monkeypatch.setattr(
        "repo_release_tools.commands.release_repair.read_group_current_version",
        lambda group: "9.9.9",
    )
    rc = release_repair.cmd_release_repair(_args(yes=True))
    assert rc == 0
    text = (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "9.9.9"' in text
    _ = capsys.readouterr()


def test_recreate_rewrites_version_targets_when_base_is_older(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When the rewind landed on a base where the version still lags, replay rewrites."""
    _seed_repo(tmp_path, pyproject_version="1.8.0")
    # Declared version comes from `read_group_current_version`; force it to 1.9.0
    # so the recreate replays 1.9.0 onto a base file that still says 1.8.0.
    monkeypatch.chdir(tmp_path)
    _patch_git(monkeypatch)
    monkeypatch.setattr(
        "repo_release_tools.commands.release_repair.read_group_current_version",
        lambda group: "1.9.0",
    )
    rc = release_repair.cmd_release_repair(_args(from_ref="main", yes=True, no_backup=True))
    assert rc == 0
    assert 'version = "1.9.0"' in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    _ = capsys.readouterr()


def test_resolve_version_body_empty_changelog_returns_none() -> None:
    """An empty changelog and no `--changelog-from` resolve to None."""
    ns = argparse.Namespace(changelog_from=None)
    assert release_repair._resolve_version_body(ns, "1.9.0", "", ChangelogFormat.MARKDOWN) is None


def test_targets_needing_rewrite_skips_missing_and_keeps_unreadable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing-file targets are skipped; unreadable targets are still rewritten."""
    present = VersionTarget(path=tmp_path / "py.toml", kind="pep621")
    missing = VersionTarget(path=tmp_path / "gone.toml", kind="pep621")
    unreadable = VersionTarget(path=tmp_path / "bad.toml", kind="pep621")

    (tmp_path / "py.toml").write_text('[project]\nversion = "1.9.0"\n', encoding="utf-8")
    (tmp_path / "bad.toml").write_text("garbage", encoding="utf-8")

    def fake_read(target: VersionTarget) -> str:
        if target.path.name == "py.toml":
            return "1.9.0"
        raise RuntimeError("unreadable")

    monkeypatch.setattr("repo_release_tools.commands.release_repair.read_version_string", fake_read)

    drifted = release_repair._targets_needing_rewrite([present, missing, unreadable], "1.9.0")
    names = [t.path.name for t in drifted]
    assert "py.toml" not in names  # already at declared version
    assert "gone.toml" not in names  # missing files are skipped
    assert "bad.toml" in names  # unreadable becomes drift


def test_files_to_stage_deduplicates_overlapping_paths(tmp_path: Path) -> None:
    """A path mentioned both as a version target and as a pin appears once."""
    target = VersionTarget(path=tmp_path / "pyproject.toml", kind="pep621")
    overlap_pin = PinTarget(path=tmp_path / "pyproject.toml", pattern=r"(rrt@v)(\d+\.\d+\.\d+)()")
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text("", encoding="utf-8")
    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=tmp_path / "CHANGELOG.md",
        lock_command=[],
        generated_files=[],
        version_targets=[target],
        pin_targets=[overlap_pin],
    )
    files = release_repair._files_to_stage(group, tmp_path, [overlap_pin])
    assert files.count("pyproject.toml") == 1
