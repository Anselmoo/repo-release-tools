"""Tests for rrt doctor command."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from repo_release_tools.commands import doctor
from repo_release_tools.config import (
    DocsConfig,
    EolConfig,
    RrtConfig,
    VersionGroup,
    VersionTarget,
)

_ARGS = argparse.Namespace()


def _make_config(
    tmp_path: Path,
    *,
    autodetected: bool = False,
    docs: DocsConfig | None = None,
    eol: EolConfig | None = None,
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
        pin_targets=[],
    )
    return RrtConfig(
        root=tmp_path,
        config_file=tmp_path / "pyproject.toml",
        version_groups=[group],
        default_group_name="default",
        autodetected=autodetected,
        global_pin_targets=[],
        docs=docs,
        eol=eol,
    )


# ---------------------------------------------------------------------------
# Config loading errors
# ---------------------------------------------------------------------------


def test_doctor_no_config_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 and prints guidance when no config file is found."""
    monkeypatch.chdir(tmp_path)

    rc = doctor.cmd_doctor(_ARGS)

    assert rc == 1
    assert capsys.readouterr().err


def test_doctor_no_rrt_section(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 when config exists but has no [tool.rrt] section."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[tool.something]\nfoo = 1\n", encoding="utf-8")

    rc = doctor.cmd_doctor(_ARGS)

    assert rc == 1
    assert capsys.readouterr().err


def test_doctor_generic_value_error_returns_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Unexpected ValueError is surfaced to stderr."""
    monkeypatch.chdir(tmp_path)

    def _boom(_: Path) -> RrtConfig:
        raise ValueError("bad config")

    monkeypatch.setattr(doctor, "load_or_autodetect_config", _boom)

    rc = doctor.cmd_doctor(_ARGS)

    assert rc == 1
    assert "bad config" in capsys.readouterr().err


def test_doctor_runtime_error_returns_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
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


def test_doctor_all_healthy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 0 and reports core automation warnings as non-fatal."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    rc = doctor.cmd_doctor(_ARGS)

    out = capsys.readouterr().out
    assert rc == 0
    assert "rrt doctor" in out
    assert "Core automation checks passed" in out
    assert "rrt release check" in out


def test_doctor_panel_shows_config_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Panel header shows the config file path."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    doctor.cmd_doctor(_ARGS)

    out = capsys.readouterr().out
    assert "pyproject.toml" in out


def test_doctor_panel_shows_group_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Panel header shows version group count."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    doctor.cmd_doctor(_ARGS)

    out = capsys.readouterr().out
    assert "1 group" in out


def test_doctor_autodetected_warns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Autodetected config prints a warning to stderr."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path, autodetected=True)
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    doctor.cmd_doctor(_ARGS)

    assert capsys.readouterr().err


def test_doctor_pre_commit_surface_detected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A repo-managed pre-commit config is reported as OK."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    (tmp_path / ".pre-commit-config.yaml").write_text(
        "repos:\n  - repo: https://github.com/Anselmoo/repo-release-tools\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    rc = doctor.cmd_doctor(_ARGS)
    out = capsys.readouterr().out
    assert rc == 0
    assert "includes repo-release-tools hooks" in out


def test_doctor_pre_commit_surface_missing_markers_warns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A generic pre-commit config warns but does not fail doctor."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    (tmp_path / ".pre-commit-config.yaml").write_text(
        "repos:\n  - repo: https://github.com/pre-commit/pre-commit-hooks\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    rc = doctor.cmd_doctor(_ARGS)

    assert rc == 0
    assert "no repo-release-tools hooks were detected" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Core automation checks
# ---------------------------------------------------------------------------


def test_doctor_lefthook_surface_detected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A lefthook config with rrt-hooks is reported as OK."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    (tmp_path / "lefthook.yml").write_text(
        "pre-commit:\n  commands:\n    lint:\n      run: rrt-hooks pre-commit\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    rc = doctor.cmd_doctor(_ARGS)

    assert rc == 0
    assert "lefthook.yml includes repo-release-tools hooks" in capsys.readouterr().out


def test_doctor_husky_surface_detected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A Husky hook script with rrt-hooks is reported as OK."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    husky_dir = tmp_path / ".husky"
    husky_dir.mkdir()
    (husky_dir / "pre-commit").write_text("rrt-hooks pre-commit\n", encoding="utf-8")
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    rc = doctor.cmd_doctor(_ARGS)

    assert rc == 0
    assert ".husky includes repo-release-tools hooks (pre-commit)" in capsys.readouterr().out


def test_doctor_husky_surface_missing_markers_warns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A Husky hook script without rrt markers warns but does not fail doctor."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    husky_dir = tmp_path / ".husky"
    husky_dir.mkdir()
    (husky_dir / "pre-commit").write_text("npm test\n", encoding="utf-8")
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    rc = doctor.cmd_doctor(_ARGS)

    assert rc == 0
    assert "no repo-release-tools hooks were detected" in capsys.readouterr().out


def test_doctor_husky_dir_without_hook_scripts_warns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A Husky directory without top-level hook scripts warns but does not fail doctor."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    (tmp_path / ".husky" / "_").mkdir(parents=True)
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    rc = doctor.cmd_doctor(_ARGS)

    assert rc == 0
    assert ".husky contains no hook scripts" in capsys.readouterr().out


def test_doctor_husky_dir_unreadable_returns_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """.husky exists as a file (not a directory) so iterdir() raises OSError — doctor fails."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    # Create .husky as a regular file; iterdir() on a file raises NotADirectoryError (OSError)
    (tmp_path / ".husky").write_text("not a directory\n", encoding="utf-8")
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    rc = doctor.cmd_doctor(_ARGS)

    assert rc == 1
    out = capsys.readouterr().out
    assert ".husky unreadable" in out
    assert "One or more core automation checks failed" in out


def test_doctor_husky_hook_file_unreadable_returns_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A hook file inside .husky that cannot be read causes doctor to fail."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    husky_dir = tmp_path / ".husky"
    husky_dir.mkdir()
    (husky_dir / "pre-commit").write_text("rrt-hooks pre-commit\n", encoding="utf-8")
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)
    # Patch _read_text so reading any hook file raises OSError
    monkeypatch.setattr(
        doctor, "_read_text", lambda _path: (_ for _ in ()).throw(OSError("permission denied"))
    )

    rc = doctor.cmd_doctor(_ARGS)

    assert rc == 1
    out = capsys.readouterr().out
    assert "pre-commit unreadable" in out
    assert "One or more core automation checks failed" in out


def test_doctor_github_actions_surface_detected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A workflow using repo-release-tools is reported as OK."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "ci.yml").write_text(
        "uses: Anselmoo/repo-release-tools@v1.1.0\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    rc = doctor.cmd_doctor(_ARGS)

    assert rc == 0
    assert "includes repo-release-tools policy checks" in capsys.readouterr().out


def test_doctor_github_actions_surface_without_rrt_markers_warns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A generic workflow file warns when no repo-release-tools step is present."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "ci.yml").write_text("uses: actions/checkout@v6\n", encoding="utf-8")
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    rc = doctor.cmd_doctor(_ARGS)

    assert rc == 0
    assert "no repo-release-tools policy step detected" in capsys.readouterr().out


def test_doctor_empty_workflows_dir_warns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An empty workflows directory warns but does not fail doctor."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    rc = doctor.cmd_doctor(_ARGS)

    assert rc == 0
    assert "contains no workflow files" in capsys.readouterr().out


def test_doctor_unreadable_workflow_file_returns_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Unreadable workflow entries fail doctor."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "ci.yml").mkdir()
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    rc = doctor.cmd_doctor(_ARGS)

    assert rc == 1
    assert "ci.yml unreadable" in capsys.readouterr().out


def test_doctor_unreadable_automation_file_returns_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Unreadable automation files fail doctor."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    (tmp_path / ".pre-commit-config.yaml").mkdir()
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    rc = doctor.cmd_doctor(_ARGS)

    assert rc == 1
    out = capsys.readouterr().out
    assert "unreadable" in out
    assert "One or more core automation checks failed" in out


def test_doctor_feature_specific_hints_follow_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Doctor points configured features to their dedicated commands."""
    monkeypatch.chdir(tmp_path)
    docs = DocsConfig(lock_file=".rrt/docs.lock.toml", src_dir="src")
    eol = EolConfig(
        languages=("python",),
        warn_days=180,
        error_days=0,
        fetch_live=False,
        allow_eol=False,
        overrides=(),
    )
    conf = _make_config(tmp_path, docs=docs, eol=eol)
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    doctor.cmd_doctor(_ARGS)

    out = capsys.readouterr().out
    assert "rrt docs check" in out
    assert "rrt eol" in out


# ---------------------------------------------------------------------------
# --fix and --fix-dry-run tests
# ---------------------------------------------------------------------------


def _args_fix(*, fix: bool = False, fix_dry_run: bool = False) -> argparse.Namespace:
    return argparse.Namespace(fix=fix, fix_dry_run=fix_dry_run)


def test_doctor_fix_inserts_missing_unreleased(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--fix adds [Unreleased] section when changelog exists but is missing it."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    changelog = conf.resolve_group().changelog_file
    changelog.write_text("## [1.0.0] - 2025-01-01\n\n### Added\n- initial\n", encoding="utf-8")
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    rc = doctor.cmd_doctor(_args_fix(fix=True))

    assert rc == 0
    result = changelog.read_text(encoding="utf-8")
    assert "## [Unreleased]" in result
    out = capsys.readouterr().out
    assert "Inserted" in out


def test_doctor_fix_dry_run_does_not_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--fix-dry-run reports what would change without writing files."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    changelog = conf.resolve_group().changelog_file
    original = "## [1.0.0] - 2025-01-01\n\n### Added\n- initial\n"
    changelog.write_text(original, encoding="utf-8")
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    rc = doctor.cmd_doctor(_args_fix(fix_dry_run=True))

    assert rc == 0
    assert changelog.read_text(encoding="utf-8") == original
    out = capsys.readouterr().out
    assert "Would insert" in out


def test_doctor_fix_nothing_to_fix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--fix reports 'nothing to fix' when everything is already correct."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    changelog = conf.resolve_group().changelog_file
    changelog.write_text("## [Unreleased]\n\n## [1.0.0] - 2025-01-01\n", encoding="utf-8")
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    rc = doctor.cmd_doctor(_args_fix(fix=True))

    assert rc == 0
    assert "Nothing to fix" in capsys.readouterr().out


def test_doctor_fix_no_changelog_file_skips_gracefully(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--fix silently skips groups whose changelog file does not exist."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    # Changelog file intentionally not created
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    rc = doctor.cmd_doctor(_args_fix(fix=True))

    assert rc == 0
    assert "Nothing to fix" in capsys.readouterr().out


def test_fix_missing_unreleased_ignores_non_rrt_config(tmp_path: Path) -> None:
    """_fix_missing_unreleased returns empty list for non-RrtConfig input."""
    from repo_release_tools.commands.doctor import _fix_missing_unreleased

    result = _fix_missing_unreleased(tmp_path, object(), dry_run=False)
    assert result == []


def test_doctor_fix_rst_changelog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--fix inserts RST-format Unreleased section into .rst changelogs."""
    monkeypatch.chdir(tmp_path)
    from repo_release_tools.config import VersionGroup, VersionTarget

    init_file = tmp_path / "src" / "__init__.py"
    init_file.parent.mkdir(parents=True, exist_ok=True)
    init_file.write_text('__version__ = "1.0.0"\n', encoding="utf-8")
    changelog = tmp_path / "CHANGELOG.rst"
    changelog.write_text("1.0.0\n-----\n\n- initial\n", encoding="utf-8")

    from repo_release_tools.config import RrtConfig

    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=changelog,
        lock_command=[],
        generated_files=[],
        version_targets=[VersionTarget(path=init_file, kind="python_version")],
        pin_targets=[],
    )
    conf = RrtConfig(
        root=tmp_path,
        config_file=tmp_path / "pyproject.toml",
        version_groups=[group],
        default_group_name="default",
    )
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    rc = doctor.cmd_doctor(_args_fix(fix=True))

    assert rc == 0
    result = changelog.read_text(encoding="utf-8")
    assert "Unreleased" in result
    assert "--------" in result


# ---------------------------------------------------------------------------
# --snapshot / --check / --strict
# ---------------------------------------------------------------------------


def _args_snapshot(
    *, snapshot: bool = False, check: bool = False, strict: bool = False
) -> argparse.Namespace:
    return argparse.Namespace(snapshot=snapshot, check=check, strict=strict)


def test_doctor_snapshot_writes_health_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--snapshot writes .rrt/health.lock.toml and exits 0."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    rc = doctor.cmd_doctor(_args_snapshot(snapshot=True))

    assert rc == 0
    lock_path = tmp_path / ".rrt" / "health.lock.toml"
    assert lock_path.exists()
    import tomllib

    data = tomllib.loads(lock_path.read_text())
    assert "meta" in data
    assert "checks" in data
    assert "pre_commit" in data["checks"]


def test_doctor_check_exits_0_when_no_regression(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--check exits 0 when check statuses match the snapshot."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    # Write baseline first
    doctor.cmd_doctor(_args_snapshot(snapshot=True))
    # Check against the same baseline
    rc = doctor.cmd_doctor(_args_snapshot(check=True))

    assert rc == 0


def test_doctor_check_advisory_exits_0_on_regression(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--check without --strict exits 0 even when regression found."""
    from repo_release_tools.state import build_health_lock, write_lock

    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    # Write a snapshot with all checks as "ok"
    lock_path = tmp_path / ".rrt" / "health.lock.toml"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    write_lock(
        lock_path,
        build_health_lock(
            [
                {"name": "pre_commit", "status": "ok"},
                {"name": "lefthook", "status": "ok"},
                {"name": "husky", "status": "ok"},
                {"name": "workflows", "status": "ok"},
            ]
        ),
    )

    rc = doctor.cmd_doctor(_args_snapshot(check=True))

    # Advisory: may detect regressions (missing markers etc.) but exits 0
    assert rc == 0
    out = capsys.readouterr().out
    # Either "no regressions" or advisory warning — both are exit 0
    assert "regression" in out.lower() or "No health regressions" in out


def test_doctor_check_strict_exits_1_on_regression(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--check --strict exits 1 when a regression is detected."""
    from repo_release_tools.state import build_health_lock, write_lock

    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    # Write a snapshot where pre_commit was "ok" (better than real state)
    lock_path = tmp_path / ".rrt" / "health.lock.toml"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    write_lock(
        lock_path,
        build_health_lock(
            [
                {"name": "pre_commit", "status": "ok"},
                {"name": "lefthook", "status": "ok"},
                {"name": "husky", "status": "ok"},
                {"name": "workflows", "status": "ok"},
            ]
        ),
    )

    # In tmp_path there's no .pre-commit-config.yaml → actual check will be "warning"
    rc = doctor.cmd_doctor(_args_snapshot(check=True, strict=True))

    # Strict mode: regression found → exit 1
    assert rc == 1


def test_doctor_check_missing_lock_exits_1_strict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--check --strict exits 1 when no health.lock.toml exists (no baseline)."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    monkeypatch.setattr(doctor, "load_or_autodetect_config", lambda _: conf)

    rc = doctor.cmd_doctor(_args_snapshot(check=True, strict=True))

    assert rc == 1
