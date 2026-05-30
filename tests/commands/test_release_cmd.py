"""Tests for the `rrt release check` command."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from repo_release_tools.commands import release_cmd
from repo_release_tools.commands.release_notes import (
    _format_gh_release,
    _git_contributors,
    cmd_release_notes,
)
from repo_release_tools.config import PinTarget, RrtConfig, VersionGroup, VersionTarget

_ARGS = argparse.Namespace()

_VALID_PIN_PATTERN = r"(Anselmoo/repo-release-tools@v)(\d+\.\d+\.\d+)()"


def _make_config(
    tmp_path: Path,
    *,
    autodetected: bool = False,
    pin_targets: list[PinTarget] | None = None,
    global_pins: list[PinTarget] | None = None,
) -> RrtConfig:
    target = VersionTarget(
        path=tmp_path / "src" / "pkg" / "__init__.py",
        kind="python_version",
    )
    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=tmp_path / "CHANGELOG.md",
        lock_command=[],
        generated_files=[],
        version_targets=[target],
        pin_targets=pin_targets or [],
    )
    return RrtConfig(
        root=tmp_path,
        config_file=tmp_path / "pyproject.toml",
        version_groups=[group],
        default_group_name="default",
        autodetected=autodetected,
        global_pin_targets=global_pins or [],
    )


def _write_version_file(path: Path, version: str = "1.2.3") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'__version__ = "{version}"\n', encoding="utf-8")


def test_release_check_no_config_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 and prints guidance when no config file is found."""
    monkeypatch.chdir(tmp_path)

    rc = release_cmd.cmd_release_check(_ARGS)

    assert rc == 1
    assert capsys.readouterr().err


def test_release_check_generic_value_error_returns_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Unexpected ValueError is surfaced to stderr."""
    monkeypatch.chdir(tmp_path)

    def _boom(_: Path) -> RrtConfig:
        raise ValueError("bad config")

    monkeypatch.setattr(release_cmd, "load_or_autodetect_config", _boom)

    rc = release_cmd.cmd_release_check(_ARGS)

    assert rc == 1
    assert "bad config" in capsys.readouterr().err


def test_release_check_no_rrt_section(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 when config exists but has no [tool.rrt] section."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[tool.something]\nfoo = 1\n", encoding="utf-8")

    rc = release_cmd.cmd_release_check(_ARGS)

    assert rc == 1
    assert "No [tool.rrt] configuration found." in capsys.readouterr().err


def test_release_check_runtime_error_returns_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Runtime errors while loading config are surfaced to stderr."""
    monkeypatch.chdir(tmp_path)

    def _boom(_: Path) -> RrtConfig:
        raise RuntimeError("broken runtime")

    monkeypatch.setattr(release_cmd, "load_or_autodetect_config", _boom)

    rc = release_cmd.cmd_release_check(_ARGS)

    assert rc == 1
    assert "broken runtime" in capsys.readouterr().err


def test_release_check_all_healthy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 0 and shows healthy release targets."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    _write_version_file(conf.version_groups[0].version_targets[0].path)
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    monkeypatch.setattr(release_cmd, "load_or_autodetect_config", lambda _: conf)

    rc = release_cmd.cmd_release_check(_ARGS)

    out = capsys.readouterr().out
    assert rc == 0
    assert "rrt release check" in out
    assert "1.2.3" in out
    assert "All release checks passed" in out


def test_release_check_from_subdir_uses_repo_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Finds the repo root from a nested working directory before loading config."""
    repo_root = tmp_path / "repo"
    nested = repo_root / "docs" / "guide"
    nested.mkdir(parents=True)
    (repo_root / "pyproject.toml").write_text("", encoding="utf-8")
    conf = _make_config(repo_root)
    _write_version_file(conf.version_groups[0].version_targets[0].path)
    (repo_root / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    monkeypatch.chdir(nested)

    def _load(root: Path) -> RrtConfig:
        assert root == repo_root
        return conf

    monkeypatch.setattr(release_cmd, "load_or_autodetect_config", _load)

    rc = release_cmd.cmd_release_check(_ARGS)

    out = capsys.readouterr().out
    assert rc == 0
    assert "Config file: pyproject.toml" in out
    assert "All release checks passed" in out


def test_release_check_autodetected_warns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Autodetected config prints a warning to stderr."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path, autodetected=True)
    _write_version_file(conf.version_groups[0].version_targets[0].path)
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    monkeypatch.setattr(release_cmd, "load_or_autodetect_config", lambda _: conf)

    release_cmd.cmd_release_check(_ARGS)

    assert capsys.readouterr().err


def test_release_check_missing_version_file_returns_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 when a version target file is missing."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    monkeypatch.setattr(release_cmd, "load_or_autodetect_config", lambda _: conf)

    rc = release_cmd.cmd_release_check(_ARGS)

    assert rc == 1
    out = capsys.readouterr().out
    assert "not found" in out
    assert "One or more release checks failed" in out


def test_release_check_unreadable_version_returns_0(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Unreadable version content is a warning, not a failure."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    target_path = conf.version_groups[0].version_targets[0].path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text("# nothing here\n", encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    monkeypatch.setattr(release_cmd, "load_or_autodetect_config", lambda _: conf)

    rc = release_cmd.cmd_release_check(_ARGS)

    assert rc == 0
    assert "version unreadable" in capsys.readouterr().out


def test_release_check_missing_pin_file_returns_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 when a pin target file is missing."""
    monkeypatch.chdir(tmp_path)
    pin = PinTarget(path=tmp_path / "docs" / "missing.md", pattern=_VALID_PIN_PATTERN)
    conf = _make_config(tmp_path, pin_targets=[pin])
    _write_version_file(conf.version_groups[0].version_targets[0].path)
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    monkeypatch.setattr(release_cmd, "load_or_autodetect_config", lambda _: conf)

    rc = release_cmd.cmd_release_check(_ARGS)

    assert rc == 1
    assert "docs/missing.md not found" in capsys.readouterr().out


def test_release_check_pin_bad_pattern_returns_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 when a pin target has an invalid regex pattern."""
    monkeypatch.chdir(tmp_path)
    pin_file = tmp_path / "docs" / "page.md"
    pin_file.parent.mkdir(parents=True)
    pin_file.write_text("some content\n", encoding="utf-8")
    pin = PinTarget(path=pin_file, pattern="([bad(regex")
    conf = _make_config(tmp_path, pin_targets=[pin])
    _write_version_file(conf.version_groups[0].version_targets[0].path)
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    monkeypatch.setattr(release_cmd, "load_or_autodetect_config", lambda _: conf)

    rc = release_cmd.cmd_release_check(_ARGS)

    assert rc == 1
    assert "bad pattern" in capsys.readouterr().out


def test_release_check_pin_no_match_warns_not_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Pin with no match in file shows warning but returns 0."""
    monkeypatch.chdir(tmp_path)
    pin_file = tmp_path / "docs" / "page.md"
    pin_file.parent.mkdir(parents=True)
    pin_file.write_text("no version pin here\n", encoding="utf-8")
    pin = PinTarget(path=pin_file, pattern=_VALID_PIN_PATTERN)
    conf = _make_config(tmp_path, pin_targets=[pin])
    _write_version_file(conf.version_groups[0].version_targets[0].path)
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    monkeypatch.setattr(release_cmd, "load_or_autodetect_config", lambda _: conf)

    rc = release_cmd.cmd_release_check(_ARGS)

    assert rc == 0
    assert "no match" in capsys.readouterr().out


def test_release_check_global_pins_deduplicated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Same pin in group_pins + global_pins is checked only once."""
    monkeypatch.chdir(tmp_path)
    pin_file = tmp_path / "docs" / "page.md"
    pin_file.parent.mkdir(parents=True)
    pin_file.write_text("uses: Anselmoo/repo-release-tools@v1.2.3\n", encoding="utf-8")
    pin = PinTarget(path=pin_file, pattern=_VALID_PIN_PATTERN)
    conf = _make_config(tmp_path, pin_targets=[pin], global_pins=[pin])
    _write_version_file(conf.version_groups[0].version_targets[0].path)
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    monkeypatch.setattr(release_cmd, "load_or_autodetect_config", lambda _: conf)

    release_cmd.cmd_release_check(_ARGS)

    out = capsys.readouterr().out
    assert out.count("page.md") == 1


# ---------------------------------------------------------------------------
# release notes tests
# ---------------------------------------------------------------------------

_UNRELEASED_CONTENT = """\
# Changelog

## [Unreleased]

### Added
- new feature

### Fixed
- some bug

## [1.0.0] - 2026-01-01
- old stuff
"""


def _make_notes_config(tmp_path: Path) -> RrtConfig:
    target = VersionTarget(
        path=tmp_path / "src" / "pkg" / "__init__.py",
        kind="python_version",
    )
    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=tmp_path / "CHANGELOG.md",
        lock_command=[],
        generated_files=[],
        version_targets=[target],
        pin_targets=[],
    )
    return RrtConfig(
        root=tmp_path,
        config_file=tmp_path / "pyproject.toml",
        version_groups=[group],
        default_group_name="default",
    )


def test_release_notes_md_format(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 0 and emits the [Unreleased] body in md format."""
    monkeypatch.chdir(tmp_path)
    conf = _make_notes_config(tmp_path)
    (tmp_path / "CHANGELOG.md").write_text(_UNRELEASED_CONTENT, encoding="utf-8")
    monkeypatch.setattr(
        "repo_release_tools.commands.release_notes.load_or_autodetect_config", lambda _: conf
    )

    rc = cmd_release_notes(argparse.Namespace(notes_format="md", group=None))

    assert rc == 0
    out = capsys.readouterr().out
    assert "### Added" in out
    assert "new feature" in out
    assert "### Fixed" in out
    assert "some bug" in out
    assert "[Unreleased]" not in out


def test_release_notes_gh_release_format(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 0 and wraps output in GitHub release header for gh-release format."""
    monkeypatch.chdir(tmp_path)
    conf = _make_notes_config(tmp_path)
    (tmp_path / "CHANGELOG.md").write_text(_UNRELEASED_CONTENT, encoding="utf-8")
    monkeypatch.setattr(
        "repo_release_tools.commands.release_notes.load_or_autodetect_config", lambda _: conf
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.release_notes._git_contributors", lambda _: ["Alice", "Bob"]
    )

    rc = cmd_release_notes(argparse.Namespace(notes_format="gh-release", group=None))

    assert rc == 0
    out = capsys.readouterr().out
    assert "## What's Changed" in out
    assert "new feature" in out
    assert "## Contributors" in out
    assert "- Alice" in out
    assert "- Bob" in out


def test_release_notes_no_unreleased_returns_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 when changelog has no [Unreleased] section."""
    monkeypatch.chdir(tmp_path)
    conf = _make_notes_config(tmp_path)
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [1.0.0] - 2026-01-01\n- old\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.release_notes.load_or_autodetect_config", lambda _: conf
    )

    rc = cmd_release_notes(argparse.Namespace(notes_format="md", group=None))

    assert rc == 1
    assert "No [Unreleased]" in capsys.readouterr().err


def test_release_notes_empty_unreleased_returns_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 when [Unreleased] section exists but is empty."""
    monkeypatch.chdir(tmp_path)
    conf = _make_notes_config(tmp_path)
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n## [1.0.0] - 2026-01-01\n- old\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.release_notes.load_or_autodetect_config", lambda _: conf
    )

    rc = cmd_release_notes(argparse.Namespace(notes_format="md", group=None))

    assert rc == 1
    assert "empty" in capsys.readouterr().err


def test_release_notes_missing_changelog_returns_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 when the changelog file does not exist."""
    monkeypatch.chdir(tmp_path)
    conf = _make_notes_config(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.release_notes.load_or_autodetect_config", lambda _: conf
    )

    rc = cmd_release_notes(argparse.Namespace(notes_format="md", group=None))

    assert rc == 1
    assert "not found" in capsys.readouterr().err


def test_release_notes_no_config_returns_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 when no config file is found."""
    monkeypatch.chdir(tmp_path)

    rc = cmd_release_notes(argparse.Namespace(notes_format="md", group=None))

    assert rc == 1
    assert capsys.readouterr().err


def test_release_notes_runtime_error_returns_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """RuntimeError from config loading is reported and returns 1."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.release_notes.load_or_autodetect_config",
        lambda _: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    rc = cmd_release_notes(argparse.Namespace(notes_format="md", group=None))

    assert rc == 1
    assert "boom" in capsys.readouterr().err


def test_format_gh_release_no_contributors() -> None:
    """gh-release format with no contributors omits the Contributors section."""
    out = _format_gh_release("- one\n- two", [])
    assert "## What's Changed" in out
    assert "- one" in out
    assert "Contributors" not in out


def test_format_gh_release_with_contributors() -> None:
    """gh-release format appends a Contributors section."""
    out = _format_gh_release("- one", ["Alice", "Bob"])
    assert "## Contributors" in out
    assert "- Alice" in out
    assert "- Bob" in out


def test_git_contributors_handles_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """_git_contributors returns [] when git is not available or fails."""
    import subprocess

    monkeypatch.setattr(
        subprocess, "run", lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError())
    )
    assert _git_contributors(tmp_path) == []
