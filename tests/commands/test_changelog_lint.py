"""Tests for `rrt changelog lint`."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import cast

import pytest

from repo_release_tools.commands.changelog_lint import (
    LintConfig,
    _extract_bullets,
    _lint_entry,
    cmd_changelog_lint,
    lint_entries,
)
from repo_release_tools.config import RrtConfig, VersionGroup, VersionTarget

_CHANGELOG = """\
# Changelog

## [Unreleased]

### Added
- Added new feature X
- added with lowercase start.
- This entry is fine

### Fixed
- Fixed a bug

## [1.0.0] - 2024-01-01

### Added
- Initial release
"""


def _make_config(tmp_path: Path, changelog_content: str | None = None) -> RrtConfig:
    init_file = tmp_path / "src" / "__init__.py"
    init_file.parent.mkdir(parents=True, exist_ok=True)
    init_file.write_text('__version__ = "1.0.0"\n', encoding="utf-8")
    changelog = tmp_path / "CHANGELOG.md"
    if changelog_content is not None:
        changelog.write_text(changelog_content, encoding="utf-8")
    target = VersionTarget(path=init_file, kind="python_version")
    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=changelog,
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


def _args(
    release: str | None = None,
    no_fail: bool = False,
    group: str | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(release=release, no_fail=no_fail, group=group)


# ---------------------------------------------------------------------------
# Unit tests for lint helpers
# ---------------------------------------------------------------------------


def test_extract_bullets_basic() -> None:
    body = "### Added\n- Feature A\n- Feature B\n\n### Fixed\n- Bug fix C\n"
    bullets = _extract_bullets(body)
    assert bullets == ["Feature A", "Feature B", "Bug fix C"]


def test_lint_entry_sentence_case_violation() -> None:
    cfg = LintConfig(
        sentence_case=True, no_trailing_period=False, max_length=0, no_duplicates=False
    )
    violations = _lint_entry("lowercase start", cfg)
    assert any(v.rule == "sentence-case" for v in violations)


def test_lint_entry_sentence_case_passes() -> None:
    cfg = LintConfig(
        sentence_case=True, no_trailing_period=False, max_length=0, no_duplicates=False
    )
    violations = _lint_entry("Uppercase start", cfg)
    assert not violations


def test_lint_entry_trailing_period_violation() -> None:
    cfg = LintConfig(
        sentence_case=False, no_trailing_period=True, max_length=0, no_duplicates=False
    )
    violations = _lint_entry("Entry ends with period.", cfg)
    assert any(v.rule == "no-trailing-period" for v in violations)


def test_lint_entry_trailing_period_passes() -> None:
    cfg = LintConfig(
        sentence_case=False, no_trailing_period=True, max_length=0, no_duplicates=False
    )
    violations = _lint_entry("Entry without period", cfg)
    assert not violations


def test_lint_entry_max_length_violation() -> None:
    cfg = LintConfig(
        sentence_case=False, no_trailing_period=False, max_length=10, no_duplicates=False
    )
    violations = _lint_entry("A" * 11, cfg)
    assert any(v.rule == "max-length" for v in violations)


def test_lint_entry_max_length_disabled() -> None:
    cfg = LintConfig(
        sentence_case=False, no_trailing_period=False, max_length=0, no_duplicates=False
    )
    violations = _lint_entry("A" * 200, cfg)
    assert not violations


def test_lint_entries_no_duplicates_violation() -> None:
    cfg = LintConfig(
        sentence_case=False, no_trailing_period=False, max_length=0, no_duplicates=True
    )
    entries = ["Feature A", "Feature B", "Feature A"]
    violations = lint_entries(entries, cfg)
    dup_violations = [v for v in violations if v.rule == "no-duplicates"]
    assert len(dup_violations) == 1
    assert "Feature A" in dup_violations[0].entry


def test_lint_entries_no_violations() -> None:
    cfg = LintConfig()
    entries = ["Feature A", "Feature B", "Fix bug C"]
    violations = lint_entries(entries, cfg)
    assert violations == []


# ---------------------------------------------------------------------------
# cmd_changelog_lint integration tests
# ---------------------------------------------------------------------------


def test_cmd_lint_no_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    rc = cmd_changelog_lint(_args())
    assert rc == 1
    assert capsys.readouterr().err


def test_cmd_lint_missing_changelog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.changelog_lint.load_or_autodetect_config",
        lambda _: conf,
    )
    rc = cmd_changelog_lint(_args())
    assert rc == 1
    assert capsys.readouterr().err


def test_cmd_lint_all_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    conf = _make_config(
        tmp_path,
        "## [Unreleased]\n\n### Added\n- Added new feature\n- Fixed a bug\n",
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.changelog_lint.load_or_autodetect_config",
        lambda _: conf,
    )
    rc = cmd_changelog_lint(_args())
    assert rc == 0
    assert "passed" in capsys.readouterr().out


def test_cmd_lint_violations_fail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    conf = _make_config(
        tmp_path,
        "## [Unreleased]\n\n### Added\n- lowercase entry.\n",
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.changelog_lint.load_or_autodetect_config",
        lambda _: conf,
    )
    rc = cmd_changelog_lint(_args())
    assert rc == 1
    err = capsys.readouterr().err
    assert "sentence-case" in err or "no-trailing-period" in err


def test_cmd_lint_violations_no_fail_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    conf = _make_config(
        tmp_path,
        "## [Unreleased]\n\n### Added\n- lowercase entry.\n",
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.changelog_lint.load_or_autodetect_config",
        lambda _: conf,
    )
    rc = cmd_changelog_lint(_args(no_fail=True))
    assert rc == 0
    out = capsys.readouterr().out
    assert "violation" in out.lower() or "no-fail" in out.lower()


def test_cmd_lint_empty_unreleased(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    conf = _make_config(
        tmp_path,
        "## [Unreleased]\n\n## [1.0.0] - 2024-01-01\n\n- Initial\n",
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.changelog_lint.load_or_autodetect_config",
        lambda _: conf,
    )
    rc = cmd_changelog_lint(_args())
    assert rc == 0
    assert "No" in capsys.readouterr().out


def test_cmd_lint_named_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    conf = _make_config(
        tmp_path,
        "## [Unreleased]\n\n## [1.0.0] - 2024-01-01\n\n### Added\n- Initial release\n",
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.changelog_lint.load_or_autodetect_config",
        lambda _: conf,
    )
    rc = cmd_changelog_lint(_args(release="1.0.0"))
    assert rc == 0
    assert "passed" in capsys.readouterr().out


def test_cmd_lint_named_release_not_found(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    conf = _make_config(
        tmp_path,
        "## [Unreleased]\n\n## [1.0.0] - 2024-01-01\n\n- Initial\n",
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.changelog_lint.load_or_autodetect_config",
        lambda _: conf,
    )
    rc = cmd_changelog_lint(_args(release="9.9.9"))
    assert rc == 1
    assert "9.9.9" in capsys.readouterr().err


def test_cmd_lint_invalid_group_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path, "## [Unreleased]\n\n- entry\n")
    monkeypatch.setattr(
        "repo_release_tools.commands.changelog_lint.load_or_autodetect_config",
        lambda _: conf,
    )
    rc = cmd_changelog_lint(_args(group="nonexistent"))
    assert rc == 1
    assert capsys.readouterr().err


def test_load_lint_config_non_dict_value(tmp_path: Path) -> None:
    """_load_lint_config falls back to defaults when changelog_lint is not a dict."""
    from repo_release_tools.commands.changelog_lint import _load_lint_config

    class FakeConfig:
        extra = {"changelog_lint": "invalid"}

    cfg = _load_lint_config(cast(RrtConfig, FakeConfig()))
    assert cfg == LintConfig()  # should fall back to defaults
