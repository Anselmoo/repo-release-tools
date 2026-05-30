"""Tests for `rrt changelog compare`."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from repo_release_tools.changelog import ChangelogFormat
from repo_release_tools.commands.changelog_compare import (
    _compare_sections,
    _extract_section_text,
    _parse_subsections,
    cmd_changelog_compare,
)
from repo_release_tools.config import RrtConfig, VersionGroup, VersionTarget

_CHANGELOG = """\
# Changelog

## [1.3.0] - 2025-03-01

### Added
- New feature A
- New feature B

### Fixed
- Bug fix C

## [1.2.0] - 2025-01-01

### Added
- New feature A
- Old feature Z

### Fixed
- Bug fix D

## [1.0.0] - 2024-01-01

### Added
- Initial release
"""


def _make_config(tmp_path: Path, version: str = "1.3.0") -> RrtConfig:
    init_file = tmp_path / "src" / "__init__.py"
    init_file.parent.mkdir(parents=True, exist_ok=True)
    init_file.write_text(f'__version__ = "{version}"\n', encoding="utf-8")
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(_CHANGELOG, encoding="utf-8")
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
    from_version: str = "1.2.0",
    to_version: str = "1.3.0",
    compare_format: str = "text",
    group: str | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        from_version=from_version,
        to_version=to_version,
        compare_format=compare_format,
        group=group,
    )


# ---------------------------------------------------------------------------
# Unit tests for helpers
# ---------------------------------------------------------------------------


def test_extract_section_text_found() -> None:
    text = _extract_section_text(_CHANGELOG, "1.3.0", ChangelogFormat.MARKDOWN)
    assert text is not None
    assert "New feature A" in text
    assert "Bug fix C" in text


def test_extract_section_text_not_found() -> None:
    text = _extract_section_text(_CHANGELOG, "9.9.9", ChangelogFormat.MARKDOWN)
    assert text is None


def test_extract_section_text_does_not_bleed_into_next() -> None:
    text = _extract_section_text(_CHANGELOG, "1.3.0", ChangelogFormat.MARKDOWN)
    assert text is not None
    assert "Old feature Z" not in text


def test_parse_subsections_groups_bullets() -> None:
    body = "### Added\n- Feature A\n- Feature B\n\n### Fixed\n- Fix C\n"
    result = _parse_subsections(body, ChangelogFormat.MARKDOWN)
    assert result["Added"] == ["- Feature A", "- Feature B"]
    assert result["Fixed"] == ["- Fix C"]


def test_parse_subsections_no_subsections_uses_general() -> None:
    body = "- Standalone entry\n- Another entry\n"
    result = _parse_subsections(body, ChangelogFormat.MARKDOWN)
    assert "General" in result
    assert len(result["General"]) == 2


def test_compare_sections_classifies_correctly() -> None:
    from_secs = {"Added": ["- Common A", "- Only from"]}
    to_secs = {"Added": ["- Common A", "- Only to"]}
    diff = _compare_sections(from_secs, to_secs)
    assert "- Only from" in diff["Added"]["only_from"]
    assert "- Common A" in diff["Added"]["common"]
    assert "- Only to" in diff["Added"]["only_to"]


def test_compare_sections_union_of_section_names() -> None:
    from_secs = {"Added": ["- x"]}
    to_secs = {"Fixed": ["- y"]}
    diff = _compare_sections(from_secs, to_secs)
    assert "Added" in diff
    assert "Fixed" in diff


# ---------------------------------------------------------------------------
# cmd_changelog_compare integration tests
# ---------------------------------------------------------------------------


def test_cmd_compare_no_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    rc = cmd_changelog_compare(_args())
    assert rc == 1
    assert capsys.readouterr().err


def test_cmd_compare_invalid_group(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.changelog_compare.load_or_autodetect_config",
        lambda _: conf,
    )
    rc = cmd_changelog_compare(_args(from_version="1.2.0", to_version="1.3.0", group="nonexistent"))
    assert rc == 1
    assert capsys.readouterr().err


def test_cmd_compare_missing_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.changelog_compare.load_or_autodetect_config",
        lambda _: conf,
    )
    rc = cmd_changelog_compare(_args(from_version="9.9.9"))
    assert rc == 1
    assert "9.9.9" in capsys.readouterr().err


def test_cmd_compare_text_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.changelog_compare.load_or_autodetect_config",
        lambda _: conf,
    )
    rc = cmd_changelog_compare(_args(from_version="1.2.0", to_version="1.3.0"))
    assert rc == 0
    out = capsys.readouterr().out
    assert "1.2.0" in out
    assert "1.3.0" in out


def test_cmd_compare_from_subdir_uses_repo_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Resolves the repo root before loading config from a nested working directory."""
    repo_root = tmp_path / "repo"
    nested = repo_root / "docs" / "guide"
    nested.mkdir(parents=True)
    (repo_root / ".rrt.toml").write_text("", encoding="utf-8")
    conf = _make_config(repo_root)
    monkeypatch.chdir(nested)

    def _load(root: Path) -> RrtConfig:
        assert root == repo_root
        return conf

    monkeypatch.setattr(
        "repo_release_tools.commands.changelog_compare.load_or_autodetect_config",
        _load,
    )
    rc = cmd_changelog_compare(_args(from_version="1.2.0", to_version="1.3.0"))
    assert rc == 0
    assert "Comparing 1.2.0 → 1.3.0" in capsys.readouterr().out


def test_cmd_compare_json_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.changelog_compare.load_or_autodetect_config",
        lambda _: conf,
    )
    rc = cmd_changelog_compare(
        _args(from_version="1.2.0", to_version="1.3.0", compare_format="json")
    )
    assert rc == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["from"] == "1.2.0"
    assert data["to"] == "1.3.0"
    assert "diff" in data


def test_cmd_compare_common_and_unique_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.changelog_compare.load_or_autodetect_config",
        lambda _: conf,
    )
    rc = cmd_changelog_compare(
        _args(from_version="1.2.0", to_version="1.3.0", compare_format="json")
    )
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    added = data["diff"]["Added"]
    assert "- New feature A" in added["common"]
    assert "- Old feature Z" in added["only_from"]
    assert "- New feature B" in added["only_to"]


def test_cmd_compare_missing_changelog_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    conf.resolve_group().changelog_file.unlink()
    monkeypatch.setattr(
        "repo_release_tools.commands.changelog_compare.load_or_autodetect_config",
        lambda _: conf,
    )
    rc = cmd_changelog_compare(_args())
    assert rc == 1


_RST_CHANGELOG = """\
Changelog
=========

1.3.0
-----

Added
~~~~~

- New feature A
- New feature B

Fixed
~~~~~

- Bug fix C

1.2.0
-----

Added
~~~~~

- New feature A
- Old feature Z

"""


def test_extract_section_text_rst_found() -> None:
    text = _extract_section_text(_RST_CHANGELOG, "1.3.0", ChangelogFormat.RST)
    assert text is not None
    assert "New feature A" in text


def test_extract_section_text_rst_not_found() -> None:
    text = _extract_section_text(_RST_CHANGELOG, "9.9.9", ChangelogFormat.RST)
    assert text is None


def test_parse_subsections_rst() -> None:
    body = "Added\n~~~~~\n\n- Feature A\n\nFixed\n~~~~~\n\n- Bug fix\n"
    result = _parse_subsections(body, ChangelogFormat.RST)
    assert "Added" in result
    assert "Fixed" in result


def test_compare_sections_empty_section_skipped() -> None:
    import io

    from repo_release_tools.commands.changelog_compare import _print_comparison

    diff = {
        "Added": {"only_from": [], "common": [], "only_to": []},
        "Fixed": {"only_from": ["- Bug"], "common": [], "only_to": []},
    }
    buf = io.StringIO()
    _print_comparison(diff, "1.2.0", "1.3.0", stdout=buf)
    output = buf.getvalue()
    assert "Added" not in output
    assert "Fixed" in output
