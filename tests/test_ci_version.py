"""Tests for the ci-version command."""

from __future__ import annotations

import argparse

from pathlib import Path

import pytest

from repo_release_tools.commands.ci_version import (
    GitHubContext,
    cmd_ci_version_apply,
    cmd_ci_version_compute,
    cmd_ci_version_sync,
    compute_published_version,
    to_semver,
)
from repo_release_tools.config import VersionTarget


# ---------------------------------------------------------------------------
# Unit – to_semver
# ---------------------------------------------------------------------------


def test_to_semver_dev_release() -> None:
    assert to_semver("0.2.0.dev12345601") == "0.2.0-dev.12345601"


def test_to_semver_release_unchanged() -> None:
    assert to_semver("1.2.3") == "1.2.3"


def test_to_semver_large_run_id() -> None:
    assert to_semver("0.2.0.dev9999999901") == "0.2.0-dev.9999999901"


# ---------------------------------------------------------------------------
# Unit – compute_published_version
# ---------------------------------------------------------------------------


def _ctx(**kwargs: str) -> GitHubContext:
    defaults = dict(ref="", ref_name="", run_id="0", run_attempt="1")
    defaults.update(kwargs)
    return GitHubContext(**defaults)  # type: ignore[arg-type]


def test_compute_tag_build() -> None:
    ctx = _ctx(ref="refs/tags/v1.3.0", ref_name="v1.3.0")
    assert compute_published_version("0.9.0", ctx) == "1.3.0"


def test_compute_tag_strips_v_prefix() -> None:
    ctx = _ctx(ref="refs/tags/v2.0.0-rc1", ref_name="v2.0.0-rc1")
    assert compute_published_version("0.9.0", ctx) == "2.0.0-rc1"


def test_compute_main_branch() -> None:
    ctx = _ctx(ref="refs/heads/main", run_id="12345678", run_attempt="1")
    assert compute_published_version("0.2.0", ctx) == "0.2.0.dev1234567801"


def test_compute_main_branch_attempt_padding() -> None:
    ctx = _ctx(ref="refs/heads/main", run_id="100", run_attempt="2")
    assert compute_published_version("0.2.0", ctx) == "0.2.0.dev10002"


def test_compute_other_branch_returns_base() -> None:
    ctx = _ctx(ref="refs/heads/feature/my-feature")
    assert compute_published_version("0.2.0", ctx) == "0.2.0"


def test_compute_empty_ref_returns_base() -> None:
    assert compute_published_version("1.0.0", _ctx()) == "1.0.0"


# ---------------------------------------------------------------------------
# Unit – VersionTarget.ci_format validation
# ---------------------------------------------------------------------------


def test_version_target_valid_ci_formats() -> None:
    for fmt in ("pep440", "semver_pre", None):
        t = VersionTarget(path=Path("x.toml"), kind="pep621", ci_format=fmt)
        t.validate()  # must not raise


def test_version_target_invalid_ci_format_raises() -> None:
    t = VersionTarget(path=Path("x.toml"), kind="pep621", ci_format="bad")
    with pytest.raises(ValueError, match="ci_format"):
        t.validate()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_PYPROJECT_MIXED = """\
[tool.rrt]
release_branch = "release/v{version}"
changelog_file = "CHANGELOG.md"
lock_command = []

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"
ci_format = "pep440"

[[tool.rrt.version_targets]]
path = "Cargo.toml"
section = "package"
field = "version"
ci_format = "semver_pre"

[project]
name = "example"
version = "0.2.0"
"""

_CARGO_TOML = """\
[package]
name = "example"
version = "0.2.0"
"""


def _ns(**kwargs: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "base": None,
        "ref": None,
        "ref_name": None,
        "run_id": None,
        "run_attempt": None,
        "dry_run": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


@pytest.fixture()
def mixed_project(tmp_path: Path) -> Path:
    """A minimal project with one pep440 and one semver_pre version target."""
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT_MIXED, encoding="utf-8")
    (tmp_path / "Cargo.toml").write_text(_CARGO_TOML, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# cmd_ci_version_compute
# ---------------------------------------------------------------------------


def test_cmd_compute_main_branch(
    mixed_project: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(mixed_project)
    result = cmd_ci_version_compute(_ns(ref="refs/heads/main", run_id="12345678", run_attempt="1"))
    captured = capsys.readouterr()
    assert result == 0
    assert captured.out.strip() == "0.2.0.dev1234567801"


def test_cmd_compute_tag_build(
    mixed_project: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(mixed_project)
    result = cmd_ci_version_compute(_ns(ref="refs/tags/v1.0.0", ref_name="v1.0.0"))
    captured = capsys.readouterr()
    assert result == 0
    assert captured.out.strip() == "1.0.0"


def test_cmd_compute_explicit_base(
    mixed_project: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(mixed_project)
    result = cmd_ci_version_compute(
        _ns(base="1.3.0", ref="refs/heads/main", run_id="7", run_attempt="1")
    )
    captured = capsys.readouterr()
    assert result == 0
    assert captured.out.strip() == "1.3.0.dev701"


def test_cmd_compute_reads_env(
    mixed_project: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Env vars are used when no CLI flags are provided."""
    monkeypatch.chdir(mixed_project)
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setenv("GITHUB_RUN_ID", "42")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    result = cmd_ci_version_compute(_ns())
    captured = capsys.readouterr()
    assert result == 0
    assert captured.out.strip() == "0.2.0.dev4201"


def test_cmd_compute_no_config_no_base_fails(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    result = cmd_ci_version_compute(_ns())
    assert result == 1


# ---------------------------------------------------------------------------
# cmd_ci_version_apply
# ---------------------------------------------------------------------------


def test_cmd_apply_dry_run(
    mixed_project: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(mixed_project)
    result = cmd_ci_version_apply(argparse.Namespace(version="0.2.0.dev12345601", dry_run=True))
    captured = capsys.readouterr()
    assert result == 0
    assert "Would update" in captured.out
    assert "no files were modified" in captured.out
    # Files must be unchanged in dry-run mode
    assert "0.2.0" in (mixed_project / "pyproject.toml").read_text(encoding="utf-8")
    assert "0.2.0" in (mixed_project / "Cargo.toml").read_text(encoding="utf-8")


def test_cmd_apply_writes_correct_formats(
    mixed_project: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(mixed_project)
    result = cmd_ci_version_apply(argparse.Namespace(version="0.2.0.dev12345601", dry_run=False))
    assert result == 0
    pyproject_text = (mixed_project / "pyproject.toml").read_text(encoding="utf-8")
    cargo_text = (mixed_project / "Cargo.toml").read_text(encoding="utf-8")
    # Python target → PEP 440 unchanged
    assert "0.2.0.dev12345601" in pyproject_text
    # Cargo target → SemVer prerelease
    assert "0.2.0-dev.12345601" in cargo_text


def test_cmd_apply_release_version_no_conversion(
    mixed_project: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A plain release version (no .dev suffix) is written as-is to all targets."""
    monkeypatch.chdir(mixed_project)
    result = cmd_ci_version_apply(argparse.Namespace(version="1.0.0", dry_run=False))
    assert result == 0
    assert "1.0.0" in (mixed_project / "pyproject.toml").read_text(encoding="utf-8")
    assert "1.0.0" in (mixed_project / "Cargo.toml").read_text(encoding="utf-8")


def test_cmd_apply_no_ci_targets_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """\
[tool.rrt]
release_branch = "release/v{version}"
lock_command = []

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[project]
name = "example"
version = "1.0.0"
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    result = cmd_ci_version_apply(argparse.Namespace(version="1.0.0.dev1", dry_run=False))
    captured = capsys.readouterr()
    assert result == 1
    assert "ci_format" in captured.err


# ---------------------------------------------------------------------------
# cmd_ci_version_sync
# ---------------------------------------------------------------------------


def test_cmd_sync_dry_run(
    mixed_project: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(mixed_project)
    result = cmd_ci_version_sync(
        _ns(ref="refs/heads/main", run_id="77", run_attempt="1", dry_run=True)
    )
    captured = capsys.readouterr()
    assert result == 0
    # sync prints the version it is about to apply
    assert "0.2.0.dev7701" in captured.out
    # dry-run apply output
    assert "Would update" in captured.out
    assert "no files were modified" in captured.out


def test_cmd_sync_writes_files(
    mixed_project: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(mixed_project)
    result = cmd_ci_version_sync(
        _ns(ref="refs/heads/main", run_id="99", run_attempt="1", dry_run=False)
    )
    assert result == 0
    assert "0.2.0.dev9901" in (mixed_project / "pyproject.toml").read_text(encoding="utf-8")
    assert "0.2.0-dev.9901" in (mixed_project / "Cargo.toml").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI smoke test – ci-version is registered
# ---------------------------------------------------------------------------


def test_cli_ci_version_in_help() -> None:
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "repo_release_tools", "--help"],
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0
    assert "ci-version" in result.stdout


# ---------------------------------------------------------------------------
# New tests for review-comment fixes
# ---------------------------------------------------------------------------


def test_compute_tag_ref_without_ref_name() -> None:
    """--ref alone (no --ref-name) must still extract the tag version."""
    ctx = _ctx(ref="refs/tags/v1.7.2", ref_name="")
    assert compute_published_version("0.9.0", ctx) == "1.7.2"


def test_compute_tag_ref_name_takes_priority() -> None:
    """When both ref and ref_name are set, ref_name is preferred."""
    ctx = _ctx(ref="refs/tags/v1.7.2", ref_name="v1.7.2")
    assert compute_published_version("0.9.0", ctx) == "1.7.2"


def test_compute_invalid_run_attempt_raises() -> None:
    """A non-integer run_attempt must raise ValueError with a clear message."""
    ctx = _ctx(ref="refs/heads/main", run_id="1", run_attempt="not-a-number")
    with pytest.raises(ValueError, match="GITHUB_RUN_ATTEMPT"):
        compute_published_version("0.2.0", ctx)


def test_cmd_compute_invalid_run_attempt_returns_error(
    mixed_project: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(mixed_project)
    result = cmd_ci_version_compute(
        _ns(base="0.2.0", ref="refs/heads/main", run_id="1", run_attempt="bad")
    )
    captured = capsys.readouterr()
    assert result == 1
    assert "GITHUB_RUN_ATTEMPT" in captured.err


def test_cmd_sync_invalid_run_attempt_returns_error(
    mixed_project: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(mixed_project)
    result = cmd_ci_version_sync(
        _ns(ref="refs/heads/main", run_id="1", run_attempt="bad", dry_run=False)
    )
    captured = capsys.readouterr()
    assert result == 1
    assert "GITHUB_RUN_ATTEMPT" in captured.err


def test_version_target_non_string_ci_format_raises() -> None:
    """A TOML array/object value for ci_format should give a clear error."""
    # Simulate a mis-configured list value coming from TOML
    t = VersionTarget(path=Path("x.toml"), kind="pep621", ci_format=["pep440"])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="must be a string"):
        t.validate()


def test_version_target_pep621_with_pattern_validates() -> None:
    """A pep621 target with a stray pattern field must still load without error."""
    t = VersionTarget(
        path=Path("pyproject.toml"),
        kind="pep621",
        pattern=r'^(version\s*=\s*")([^"]+)(")',
    )
    t.validate()  # must not raise


def test_cmd_apply_nonstandard_dev_suffix_rejected(
    mixed_project: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Versions like '0.2.0.dev1.post2' must be rejected for semver_pre targets."""
    monkeypatch.chdir(mixed_project)
    result = cmd_ci_version_apply(argparse.Namespace(version="0.2.0.dev1.post2", dry_run=False))
    captured = capsys.readouterr()
    assert result == 1
    assert "Cannot convert" in captured.err
