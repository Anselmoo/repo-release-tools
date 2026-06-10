"""Tests for the `rrt release notes` command."""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from repo_release_tools.commands.release_notes import (
    _git_contributors,
    cmd_release_notes,
)


def _args(
    notes_format: str = "md",
    group: str | None = None,
    *,
    version: str | None = None,
    latest_released: bool = False,
    output: str | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        notes_format=notes_format,
        group=group,
        version=version,
        latest_released=latest_released,
        output=output,
    )


# ---------------------------------------------------------------------------
# _git_contributors – happy path (lines 58-68)
# ---------------------------------------------------------------------------


def test_git_contributors_with_tags(tmp_path: Path) -> None:
    """Returns sorted unique author names when git tag and git log succeed."""
    mock_tags = MagicMock()
    mock_tags.stdout = "v1.0.0\nv0.9.0\n"
    mock_log = MagicMock()
    mock_log.stdout = "Alice\nBob\nAlice\n"
    with patch("subprocess.run", side_effect=[mock_tags, mock_log]):
        result = _git_contributors(tmp_path)
    assert result == ["Alice", "Bob"]


def test_git_contributors_no_tags(tmp_path: Path) -> None:
    """Falls back to HEAD ref when no tags exist."""
    mock_tags = MagicMock()
    mock_tags.stdout = ""
    mock_log = MagicMock()
    mock_log.stdout = "Charlie\n"
    with patch("subprocess.run", side_effect=[mock_tags, mock_log]) as mock_run:
        result = _git_contributors(tmp_path)
    assert result == ["Charlie"]
    log_call_args = mock_run.call_args_list[1][0][0]
    assert "HEAD" in log_call_args


# ---------------------------------------------------------------------------
# cmd_release_notes – ValueError paths (lines 97-108)
# ---------------------------------------------------------------------------


def test_cmd_release_notes_missing_rrt_value_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 when config raises MissingRrtConfigError."""
    from repo_release_tools.config import MissingRrtConfigError

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.release_notes.load_or_autodetect_config",
        lambda _: (_ for _ in ()).throw(MissingRrtConfigError("no rrt")),
    )
    rc = cmd_release_notes(_args())
    assert rc == 1
    assert capsys.readouterr().err


def test_cmd_release_notes_generic_value_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 when config raises a generic ValueError."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.release_notes.load_or_autodetect_config",
        lambda _: (_ for _ in ()).throw(ValueError("bad config value")),
    )
    rc = cmd_release_notes(_args())
    assert rc == 1
    assert "bad config value" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# cmd_release_notes – resolve_group ValueError (lines 116-119)
# ---------------------------------------------------------------------------


def test_cmd_release_notes_resolve_group_value_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 when resolve_group raises ValueError."""
    monkeypatch.chdir(tmp_path)
    mock_config = MagicMock()
    mock_config.resolve_group.side_effect = ValueError("unknown group 'prod'")
    monkeypatch.setattr(
        "repo_release_tools.commands.release_notes.load_or_autodetect_config",
        lambda _: mock_config,
    )
    rc = cmd_release_notes(_args(group="prod"))
    assert rc == 1
    assert "unknown group 'prod'" in capsys.readouterr().err


def test_cmd_release_notes_from_subdir_uses_repo_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Resolves the repo root before loading config from a nested working directory."""
    repo_root = tmp_path / "repo"
    nested = repo_root / "docs" / "guide"
    nested.mkdir(parents=True)
    (repo_root / "pyproject.toml").write_text("", encoding="utf-8")
    (repo_root / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n- Added: subdir support\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(nested)

    mock_group = MagicMock()
    mock_group.changelog_file = repo_root / "CHANGELOG.md"
    mock_config = MagicMock()
    mock_config.resolve_group.return_value = mock_group

    def _load(root: Path) -> MagicMock:
        assert root == repo_root
        return mock_config

    monkeypatch.setattr(
        "repo_release_tools.commands.release_notes.load_or_autodetect_config",
        _load,
    )

    rc = cmd_release_notes(_args())

    out = capsys.readouterr().out
    assert rc == 0
    assert "Added: subdir support" in out


# ---------------------------------------------------------------------------
# --version / --latest-released / --output (F1)
# ---------------------------------------------------------------------------


_CHANGELOG_WITH_RELEASES = """# Changelog

## [Unreleased]

## [1.7.1] - 2026-06-10
### Fixed
- correct workflow pipeline for release

## [1.7.0] - 2026-06-09
### Added
- earlier feature
"""


def _stub_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    body: str,
    changelog_name: str = "CHANGELOG.md",
) -> Path:
    """Drop *body* into a CHANGELOG file and stub config loading."""
    monkeypatch.chdir(tmp_path)
    changelog_path = tmp_path / changelog_name
    changelog_path.write_text(body, encoding="utf-8")

    mock_group = MagicMock()
    mock_group.changelog_file = changelog_path
    mock_config = MagicMock()
    mock_config.resolve_group.return_value = mock_group
    monkeypatch.setattr(
        "repo_release_tools.commands.release_notes.load_or_autodetect_config",
        lambda _: mock_config,
    )
    return changelog_path


def test_release_notes_with_version_arg(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--version 1.7.0` extracts that specific section's body."""
    _stub_config(monkeypatch, tmp_path, _CHANGELOG_WITH_RELEASES)
    rc = cmd_release_notes(_args(version="1.7.0"))
    out = capsys.readouterr().out
    assert rc == 0
    assert "earlier feature" in out
    assert "correct workflow pipeline" not in out


def test_release_notes_with_v_prefix_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--version v1.7.1` matches `[1.7.1]` (v-prefix is stripped)."""
    _stub_config(monkeypatch, tmp_path, _CHANGELOG_WITH_RELEASES)
    rc = cmd_release_notes(_args(version="v1.7.1"))
    out = capsys.readouterr().out
    assert rc == 0
    assert "correct workflow pipeline" in out


def test_release_notes_with_latest_released(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--latest-released` picks the topmost versioned section."""
    _stub_config(monkeypatch, tmp_path, _CHANGELOG_WITH_RELEASES)
    rc = cmd_release_notes(_args(latest_released=True))
    out = capsys.readouterr().out
    assert rc == 0
    assert "correct workflow pipeline" in out
    assert "earlier feature" not in out


def test_release_notes_writes_output_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--output PATH` writes to a file and leaves stdout untouched."""
    _stub_config(monkeypatch, tmp_path, _CHANGELOG_WITH_RELEASES)
    target = tmp_path / "RELEASE.md"
    rc = cmd_release_notes(_args(latest_released=True, output=str(target)))
    assert rc == 0
    assert capsys.readouterr().out == ""
    assert "correct workflow pipeline" in target.read_text(encoding="utf-8")


def test_release_notes_unknown_version_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A missing release label returns 1 with a clear error."""
    _stub_config(monkeypatch, tmp_path, _CHANGELOG_WITH_RELEASES)
    rc = cmd_release_notes(_args(version="99.0.0"))
    err = capsys.readouterr().err
    assert rc == 1
    assert "[99.0.0]" in err
    assert "not found" in err


def test_release_notes_latest_released_when_only_unreleased_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--latest-released` with no released sections returns 1."""
    _stub_config(monkeypatch, tmp_path, "# Changelog\n\n## [Unreleased]\n- new thing\n")
    rc = cmd_release_notes(_args(latest_released=True))
    err = capsys.readouterr().err
    assert rc == 1
    assert "No released sections" in err


def test_release_notes_version_and_latest_released_mutually_exclusive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Passing both `--version` and `--latest-released` returns 1."""
    monkeypatch.chdir(tmp_path)
    rc = cmd_release_notes(_args(version="1.0.0", latest_released=True))
    err = capsys.readouterr().err
    assert rc == 1
    assert "mutually exclusive" in err


def test_release_notes_unreleased_empty_message_names_section(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The empty-section error names which section was requested."""
    _stub_config(monkeypatch, tmp_path, "# Changelog\n\n## [Unreleased]\n")
    rc = cmd_release_notes(_args())
    err = capsys.readouterr().err
    assert rc == 1
    assert "[Unreleased]" in err
