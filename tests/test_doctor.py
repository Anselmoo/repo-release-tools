"""Tests for rrt doctor command."""

from __future__ import annotations

import argparse
from pathlib import Path

from repo_release_tools.commands import doctor
from repo_release_tools.config import (
    PinTarget,
    RrtConfig,
    VersionGroup,
    VersionTarget,
)


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


# ---------------------------------------------------------------------------
# Config loading errors
# ---------------------------------------------------------------------------


def test_doctor_no_config_file(tmp_path: Path, monkeypatch, capsys) -> None:
    """Returns 1 and prints guidance when no config file is found."""
    monkeypatch.chdir(tmp_path)

    rc = doctor.cmd_doctor(_ARGS)

    assert rc == 1
    assert capsys.readouterr().err


def test_doctor_no_rrt_section(tmp_path: Path, monkeypatch, capsys) -> None:
    """Returns 1 when config exists but has no [tool.rrt] section."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[tool.something]\nfoo = 1\n", encoding="utf-8")

    rc = doctor.cmd_doctor(_ARGS)

    assert rc == 1
    assert capsys.readouterr().err


def test_doctor_generic_value_error_returns_1(tmp_path: Path, monkeypatch, capsys) -> None:
    """Unexpected ValueError is surfaced to stderr."""
    monkeypatch.chdir(tmp_path)

    def _boom(_: Path) -> RrtConfig:
        raise ValueError("bad config")

    monkeypatch.setattr(doctor, "load_or_autodetect_config", _boom)

    rc = doctor.cmd_doctor(_ARGS)

    assert rc == 1
    assert "bad config" in capsys.readouterr().err


def test_doctor_runtime_error_returns_1(tmp_path: Path, monkeypatch, capsys) -> None:
    """Runtime errors while loading config are surfaced to stderr."""
    monkeypatch.chdir(tmp_path)

    def _boom(_: Path) -> RrtConfig:
        raise RuntimeError("broken runtime")

    monkeypatch.setattr(doctor, "load_or_autodetect_config", _boom)

    rc = doctor.cmd_doctor(_ARGS)

    assert rc == 1
    assert "broken runtime" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_doctor_all_healthy(tmp_path: Path, monkeypatch, capsys) -> None:
    """Returns 0 and shows the tree when all targets are healthy."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    _write_version_file(conf.version_groups[0].version_targets[0].path)
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    rc = doctor.cmd_doctor(_ARGS)

    out = capsys.readouterr().out
    assert rc == 0
    assert "rrt doctor" in out
    assert "1.2.3" in out
    assert "All health checks passed" in out


def test_doctor_panel_shows_config_file(tmp_path: Path, monkeypatch, capsys) -> None:
    """Panel header shows the config file path."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    _write_version_file(conf.version_groups[0].version_targets[0].path)
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    doctor.cmd_doctor(_ARGS)

    out = capsys.readouterr().out
    assert "pyproject.toml" in out


def test_doctor_panel_shows_group_count(tmp_path: Path, monkeypatch, capsys) -> None:
    """Panel header shows version group count."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    _write_version_file(conf.version_groups[0].version_targets[0].path)
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    doctor.cmd_doctor(_ARGS)

    out = capsys.readouterr().out
    assert "1 group" in out


def test_doctor_changelog_exists(tmp_path: Path, monkeypatch, capsys) -> None:
    """Tree shows changelog file as exists."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    _write_version_file(conf.version_groups[0].version_targets[0].path)
    (tmp_path / "CHANGELOG.md").write_text("## [Unreleased]\n", encoding="utf-8")
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    doctor.cmd_doctor(_ARGS)

    out = capsys.readouterr().out
    assert "CHANGELOG.md" in out
    assert "exists" in out


def test_doctor_autodetected_warns(tmp_path: Path, monkeypatch, capsys) -> None:
    """Autodetected config prints a warning to stderr."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path, autodetected=True)
    _write_version_file(conf.version_groups[0].version_targets[0].path)
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    doctor.cmd_doctor(_ARGS)

    assert capsys.readouterr().err  # auto-detect warning


# ---------------------------------------------------------------------------
# Version target failures
# ---------------------------------------------------------------------------


def test_doctor_missing_version_file_returns_1(tmp_path: Path, monkeypatch, capsys) -> None:
    """Returns 1 when a version target file is missing."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    # Do NOT write the version file
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    rc = doctor.cmd_doctor(_ARGS)

    assert rc == 1
    out = capsys.readouterr().out
    assert "not found" in out
    assert "One or more health checks failed" in out


def test_doctor_unreadable_version_returns_0(tmp_path: Path, monkeypatch, capsys) -> None:
    """Unreadable version (bad content) shows warning but returns 0 (non-fatal)."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    target_path = conf.version_groups[0].version_targets[0].path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    # Write a file without the expected __version__ line
    target_path.write_text("# nothing here\n", encoding="utf-8")
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    rc = doctor.cmd_doctor(_ARGS)

    assert rc == 0
    out = capsys.readouterr().out
    assert "unreadable" in out


# ---------------------------------------------------------------------------
# Pin target checks
# ---------------------------------------------------------------------------


def test_doctor_missing_pin_file_returns_1(tmp_path: Path, monkeypatch, capsys) -> None:
    """Returns 1 when a pin target file is missing."""
    monkeypatch.chdir(tmp_path)
    pin = PinTarget(path=tmp_path / "docs" / "missing.md", pattern=_VALID_PIN_PATTERN)
    conf = _make_config(tmp_path, pin_targets=[pin])
    _write_version_file(conf.version_groups[0].version_targets[0].path)
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    rc = doctor.cmd_doctor(_ARGS)

    assert rc == 1
    out = capsys.readouterr().out
    assert "not found" in out


def test_doctor_pin_bad_pattern_returns_1(tmp_path: Path, monkeypatch, capsys) -> None:
    """Returns 1 when a pin target has an invalid regex pattern."""
    monkeypatch.chdir(tmp_path)
    pin_file = tmp_path / "docs" / "page.md"
    pin_file.parent.mkdir(parents=True)
    pin_file.write_text("some content\n", encoding="utf-8")
    pin = PinTarget(path=pin_file, pattern="([bad(regex")
    conf = _make_config(tmp_path, pin_targets=[pin])
    _write_version_file(conf.version_groups[0].version_targets[0].path)
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    rc = doctor.cmd_doctor(_ARGS)

    assert rc == 1
    out = capsys.readouterr().out
    assert "bad pattern" in out


def test_doctor_pin_no_match_warns_not_errors(tmp_path: Path, monkeypatch, capsys) -> None:
    """Pin with no match in file shows warning but returns 0."""
    monkeypatch.chdir(tmp_path)
    pin_file = tmp_path / "docs" / "page.md"
    pin_file.parent.mkdir(parents=True)
    pin_file.write_text("no version pin here\n", encoding="utf-8")
    pin = PinTarget(path=pin_file, pattern=_VALID_PIN_PATTERN)
    conf = _make_config(tmp_path, pin_targets=[pin])
    _write_version_file(conf.version_groups[0].version_targets[0].path)
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    rc = doctor.cmd_doctor(_ARGS)

    assert rc == 0
    out = capsys.readouterr().out
    assert "no match" in out


def test_doctor_pin_match_shows_healthy(tmp_path: Path, monkeypatch, capsys) -> None:
    """Pin with a match in file shows healthy indicator."""
    monkeypatch.chdir(tmp_path)
    pin_file = tmp_path / "docs" / "page.md"
    pin_file.parent.mkdir(parents=True)
    pin_file.write_text("uses: Anselmoo/repo-release-tools@v1.2.3\n", encoding="utf-8")
    pin = PinTarget(path=pin_file, pattern=_VALID_PIN_PATTERN)
    conf = _make_config(tmp_path, pin_targets=[pin])
    _write_version_file(conf.version_groups[0].version_targets[0].path)
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    rc = doctor.cmd_doctor(_ARGS)

    assert rc == 0
    out = capsys.readouterr().out
    assert "match" in out


def test_doctor_global_pins_deduplicated(tmp_path: Path, monkeypatch, capsys) -> None:
    """Same pin in group_pins + global_pins is checked only once."""
    monkeypatch.chdir(tmp_path)
    pin_file = tmp_path / "docs" / "page.md"
    pin_file.parent.mkdir(parents=True)
    pin_file.write_text("uses: Anselmoo/repo-release-tools@v1.2.3\n", encoding="utf-8")
    pin = PinTarget(path=pin_file, pattern=_VALID_PIN_PATTERN)
    conf = _make_config(tmp_path, pin_targets=[pin], global_pins=[pin])
    _write_version_file(conf.version_groups[0].version_targets[0].path)
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    doctor.cmd_doctor(_ARGS)

    out = capsys.readouterr().out
    # Pin should appear exactly once in tree output
    assert out.count("page.md") == 1
