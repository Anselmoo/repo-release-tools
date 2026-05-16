"""Tests for `rrt tag create` and `rrt tag check`."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from repo_release_tools.commands.tag import (
    _existing_tags,
    _git,
    _load_config_and_version,
    _tag_name,
    cmd_tag_check,
    cmd_tag_create,
)
from repo_release_tools.config import RrtConfig, VersionGroup, VersionTarget


def _make_config(tmp_path: Path, version: str = "1.2.3") -> RrtConfig:
    init_file = tmp_path / "src" / "pkg" / "__init__.py"
    init_file.parent.mkdir(parents=True, exist_ok=True)
    init_file.write_text(f'__version__ = "{version}"\n', encoding="utf-8")
    target = VersionTarget(path=init_file, kind="python_version")
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


def _args_create(
    prefix: str = "v",
    message: str | None = None,
    push: bool = False,
    force: bool = False,
    dry_run: bool = False,
    group: str | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        prefix=prefix,
        message=message,
        push=push,
        force=force,
        dry_run=dry_run,
        group=group,
    )


def _args_check(
    prefix: str = "v",
    strict: bool = False,
    group: str | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(prefix=prefix, strict=strict, group=group)


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------


def test_tag_name_with_prefix() -> None:
    assert _tag_name("1.2.3", "v") == "v1.2.3"


def test_tag_name_no_prefix() -> None:
    assert _tag_name("1.2.3", "") == "1.2.3"


def test_existing_tags_returns_list(tmp_path: Path) -> None:
    """Returns empty list when git is unavailable."""
    with patch("repo_release_tools.commands.tag._git") as mock_git:
        mock_git.side_effect = FileNotFoundError()
        assert _existing_tags(tmp_path) == []


def test_existing_tags_parses_output(tmp_path: Path) -> None:
    """Parses newline-separated tag output correctly."""
    mock = MagicMock()
    mock.stdout = "v2.0.0\nv1.1.0\nv1.0.0\n"
    with patch("repo_release_tools.commands.tag._git", return_value=mock):
        assert _existing_tags(tmp_path) == ["v2.0.0", "v1.1.0", "v1.0.0"]


# ---------------------------------------------------------------------------
# cmd_tag_create tests
# ---------------------------------------------------------------------------


def test_tag_create_no_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 when no rrt config is found."""
    monkeypatch.chdir(tmp_path)
    rc = cmd_tag_create(_args_create())
    assert rc == 1
    assert capsys.readouterr().err


def test_tag_create_dry_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dry-run prints intent and returns 0 without running git."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    monkeypatch.setattr("repo_release_tools.commands.tag.load_or_autodetect_config", lambda _: conf)
    monkeypatch.setattr("repo_release_tools.commands.tag._existing_tags", lambda _: [])

    rc = cmd_tag_create(_args_create(dry_run=True))

    assert rc == 0
    out = capsys.readouterr().out
    assert "v1.2.3" in out
    assert "no changes were made" in out


def test_tag_create_tag_exists_no_force(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 when tag already exists and --force is not set."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    monkeypatch.setattr("repo_release_tools.commands.tag.load_or_autodetect_config", lambda _: conf)
    monkeypatch.setattr("repo_release_tools.commands.tag._existing_tags", lambda _: ["v1.2.3"])

    rc = cmd_tag_create(_args_create())

    assert rc == 1
    assert "already exists" in capsys.readouterr().err


def test_tag_create_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 0 and calls git tag -a when preconditions are met."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    monkeypatch.setattr("repo_release_tools.commands.tag.load_or_autodetect_config", lambda _: conf)
    monkeypatch.setattr("repo_release_tools.commands.tag._existing_tags", lambda _: [])

    git_calls: list[list[str]] = []

    def _fake_git(cmd: list[str], _root: Path, **kwargs: object) -> MagicMock:
        git_calls.append(cmd)
        m = MagicMock()
        m.stderr = ""
        return m

    monkeypatch.setattr("repo_release_tools.commands.tag._git", _fake_git)

    rc = cmd_tag_create(_args_create())

    assert rc == 0
    assert any("tag" in c and "-a" in c and "v1.2.3" in c for c in git_calls)
    assert "Created tag" in capsys.readouterr().out


def test_tag_create_with_push(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--push triggers a git push after tag creation."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    monkeypatch.setattr("repo_release_tools.commands.tag.load_or_autodetect_config", lambda _: conf)
    monkeypatch.setattr("repo_release_tools.commands.tag._existing_tags", lambda _: [])

    git_calls: list[list[str]] = []

    def _fake_git(cmd: list[str], _root: Path, **kwargs: object) -> MagicMock:
        git_calls.append(cmd)
        m = MagicMock()
        m.stderr = ""
        return m

    monkeypatch.setattr("repo_release_tools.commands.tag._git", _fake_git)

    rc = cmd_tag_create(_args_create(push=True))

    assert rc == 0
    push_calls = [c for c in git_calls if "push" in c]
    assert push_calls, "Expected a git push call"
    out = capsys.readouterr().out
    assert "Pushed" in out


def test_tag_create_git_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 when git tag command fails."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    monkeypatch.setattr("repo_release_tools.commands.tag.load_or_autodetect_config", lambda _: conf)
    monkeypatch.setattr("repo_release_tools.commands.tag._existing_tags", lambda _: [])

    def _fail(cmd: list[str], _root: Path, **kwargs: object) -> None:
        exc = subprocess.CalledProcessError(1, cmd)
        exc.stderr = "permission denied"
        raise exc

    monkeypatch.setattr("repo_release_tools.commands.tag._git", _fail)

    rc = cmd_tag_create(_args_create())

    assert rc == 1
    assert "git tag failed" in capsys.readouterr().err


def test_tag_create_no_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Empty prefix creates tag without 'v' prefix."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    monkeypatch.setattr("repo_release_tools.commands.tag.load_or_autodetect_config", lambda _: conf)
    monkeypatch.setattr("repo_release_tools.commands.tag._existing_tags", lambda _: [])

    git_calls: list[list[str]] = []

    def _fake_git(cmd: list[str], _root: Path, **kwargs: object) -> MagicMock:
        git_calls.append(cmd)
        m = MagicMock()
        m.stderr = ""
        return m

    monkeypatch.setattr("repo_release_tools.commands.tag._git", _fake_git)

    rc = cmd_tag_create(_args_create(prefix=""))

    assert rc == 0
    assert any("1.2.3" in c and "v1.2.3" not in " ".join(c) for c in git_calls if "tag" in c)


# ---------------------------------------------------------------------------
# cmd_tag_check tests
# ---------------------------------------------------------------------------


def test_tag_check_no_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 when no rrt config is found."""
    monkeypatch.chdir(tmp_path)
    rc = cmd_tag_check(_args_check())
    assert rc == 1
    assert capsys.readouterr().err


def test_tag_check_tag_present(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 0 when expected tag exists."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    monkeypatch.setattr("repo_release_tools.commands.tag.load_or_autodetect_config", lambda _: conf)
    monkeypatch.setattr("repo_release_tools.commands.tag._existing_tags", lambda _: ["v1.2.3"])

    rc = cmd_tag_check(_args_check())

    assert rc == 0
    assert "v1.2.3" in capsys.readouterr().out


def test_tag_check_tag_missing_not_strict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 0 (non-strict) when expected tag is absent but no prefix mismatches."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    monkeypatch.setattr("repo_release_tools.commands.tag.load_or_autodetect_config", lambda _: conf)
    monkeypatch.setattr("repo_release_tools.commands.tag._existing_tags", lambda _: ["v1.0.0"])

    rc = cmd_tag_check(_args_check(strict=False))

    assert rc == 0
    assert "v1.2.3" in capsys.readouterr().out


def test_tag_check_tag_missing_strict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 in strict mode when expected tag is missing."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    monkeypatch.setattr("repo_release_tools.commands.tag.load_or_autodetect_config", lambda _: conf)
    monkeypatch.setattr("repo_release_tools.commands.tag._existing_tags", lambda _: ["v1.0.0"])

    rc = cmd_tag_check(_args_check(strict=True))

    assert rc == 1


def test_tag_check_prefix_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 when an existing tag does not match the expected prefix."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    monkeypatch.setattr("repo_release_tools.commands.tag.load_or_autodetect_config", lambda _: conf)
    monkeypatch.setattr(
        "repo_release_tools.commands.tag._existing_tags", lambda _: ["v1.2.3", "1.0.0"]
    )

    rc = cmd_tag_check(_args_check(prefix="v"))

    assert rc == 1
    out = capsys.readouterr().out
    assert "does not match prefix" in out


# ---------------------------------------------------------------------------
# _load_config_and_version error paths
# ---------------------------------------------------------------------------


def test_tag_create_is_missing_rrt_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 when config ValueError signals missing [tool.rrt] config."""
    from repo_release_tools.config import MissingRrtConfigError

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.tag.load_or_autodetect_config",
        lambda _: (_ for _ in ()).throw(MissingRrtConfigError("no rrt")),
    )
    rc = cmd_tag_create(_args_create())
    assert rc == 1
    assert capsys.readouterr().err


def test_tag_create_value_error_non_rrt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 when config raises a generic ValueError."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.tag.load_or_autodetect_config",
        lambda _: (_ for _ in ()).throw(ValueError("generic error")),
    )
    rc = cmd_tag_create(_args_create())
    assert rc == 1
    assert capsys.readouterr().err


def test_tag_create_runtime_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 when config raises a RuntimeError."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.tag.load_or_autodetect_config",
        lambda _: (_ for _ in ()).throw(RuntimeError("runtime problem")),
    )
    rc = cmd_tag_create(_args_create())
    assert rc == 1
    assert capsys.readouterr().err


def test_tag_create_force_deletes_and_recreates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--force deletes the existing tag and recreates it."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    monkeypatch.setattr("repo_release_tools.commands.tag.load_or_autodetect_config", lambda _: conf)
    monkeypatch.setattr("repo_release_tools.commands.tag._existing_tags", lambda _: ["v1.2.3"])

    git_calls: list[list[str]] = []

    def _fake_git(cmd: list[str], _root: Path, **kwargs: object) -> MagicMock:
        git_calls.append(cmd)
        m = MagicMock()
        m.stderr = ""
        return m

    monkeypatch.setattr("repo_release_tools.commands.tag._git", _fake_git)

    rc = cmd_tag_create(_args_create(force=True))

    assert rc == 0
    delete_calls = [c for c in git_calls if "tag" in c and "-d" in c]
    assert delete_calls, "Expected a git tag -d call for force delete"


def test_tag_create_push_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 when git push fails."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    monkeypatch.setattr("repo_release_tools.commands.tag.load_or_autodetect_config", lambda _: conf)
    monkeypatch.setattr("repo_release_tools.commands.tag._existing_tags", lambda _: [])

    call_count = [0]

    def _fail_on_push(cmd: list[str], _root: Path, **kwargs: object) -> MagicMock:
        call_count[0] += 1
        if "push" in cmd:
            exc = subprocess.CalledProcessError(1, cmd)
            exc.stderr = "remote: repository not found"
            raise exc
        m = MagicMock()
        m.stderr = ""
        return m

    monkeypatch.setattr("repo_release_tools.commands.tag._git", _fail_on_push)

    rc = cmd_tag_create(_args_create(push=True))

    assert rc == 1
    assert "git push failed" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# _git helper – direct invocation (line 46)
# ---------------------------------------------------------------------------


def test_git_helper_calls_subprocess_run(tmp_path: Path) -> None:
    """_git wraps subprocess.run with capture_output=True, text=True, check=True."""
    mock_result = MagicMock()
    with patch("subprocess.run", return_value=mock_result) as mock_run:
        result = _git(["git", "--version"], tmp_path)
    assert result is mock_result
    mock_run.assert_called_once_with(
        ["git", "--version"],
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )


# ---------------------------------------------------------------------------
# _load_config_and_version – resolve_group ValueError (lines 76-79)
# ---------------------------------------------------------------------------


def test_load_config_and_version_resolve_group_value_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns None and prints error when resolve_group raises ValueError."""
    mock_config = MagicMock()
    mock_config.resolve_group.side_effect = ValueError("unknown group 'staging'")
    monkeypatch.setattr(
        "repo_release_tools.commands.tag.load_or_autodetect_config",
        lambda _: mock_config,
    )
    result = _load_config_and_version(tmp_path, "staging")
    assert result is None
    assert "unknown group 'staging'" in capsys.readouterr().err
