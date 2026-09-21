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
    _resolve_prefix,
    _tag_name,
    _tag_name_for_group,
    cmd_tag_check,
    cmd_tag_create,
)
from repo_release_tools.config import (
    DEFAULT_TAG_PREFIX,
    RrtConfig,
    VersionGroup,
    VersionTarget,
)


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
    prefix: str | None = "v",
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
    prefix: str | None = "v",
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
    assert "rrt tag create" in capsys.readouterr().out


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


# ---------------------------------------------------------------------------
# Batch `--group a,b,c` and `{group}` prefix token (issue #191)
# ---------------------------------------------------------------------------


def _make_multi_group_config(
    tmp_path: Path,
    versions: dict[str, str],
    tag_prefixes: dict[str, str] | None = None,
) -> RrtConfig:
    groups = []
    for name, version in versions.items():
        init_file = tmp_path / name / "__init__.py"
        init_file.parent.mkdir(parents=True, exist_ok=True)
        init_file.write_text(f'__version__ = "{version}"\n', encoding="utf-8")
        target = VersionTarget(path=init_file, kind="python_version")
        groups.append(
            VersionGroup(
                name=name,
                release_branch=f"release/{name}/v{{version}}",
                changelog_file=tmp_path / name / "CHANGELOG.md",
                lock_command=[],
                generated_files=[],
                version_targets=[target],
                pin_targets=[],
                tag_prefix=(tag_prefixes or {}).get(name, DEFAULT_TAG_PREFIX),
            )
        )
    return RrtConfig(
        root=tmp_path,
        config_file=tmp_path / "pyproject.toml",
        version_groups=groups,
        default_group_name=None,
    )


def test_tag_name_for_group_renders_group_token() -> None:
    """Substitutes {group} with the group's name before the version."""
    assert _tag_name_for_group("1.2.3", "{group}-v", "alpha") == "alpha-v1.2.3"


def test_tag_name_for_group_no_op_without_token() -> None:
    """Behaves exactly like _tag_name when --prefix has no {group} token."""
    assert _tag_name_for_group("1.2.3", "v", "alpha") == "v1.2.3"


def test_tag_name_for_group_preserves_unrelated_braces() -> None:
    """A stray unrelated `{...}` in a custom prefix is left untouched (no KeyError)."""
    assert _tag_name_for_group("1.2.3", "release-{build}-", "alpha") == "release-{build}-1.2.3"


def test_cmd_tag_create_batch_creates_tags_for_all_groups(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Creates one correctly-prefixed tag per listed group in one invocation."""
    monkeypatch.chdir(tmp_path)
    conf = _make_multi_group_config(tmp_path, {"alpha": "1.0.0", "beta": "2.0.0"})
    monkeypatch.setattr("repo_release_tools.commands.tag.load_or_autodetect_config", lambda _: conf)
    monkeypatch.setattr("repo_release_tools.commands.tag._existing_tags", lambda _: [])

    git_calls: list[list[str]] = []

    def _fake_git(cmd: list[str], _root: Path, **kwargs: object) -> MagicMock:
        git_calls.append(cmd)
        m = MagicMock()
        m.stderr = ""
        return m

    monkeypatch.setattr("repo_release_tools.commands.tag._git", _fake_git)

    rc = cmd_tag_create(_args_create(prefix="{group}-v", group="alpha,beta"))

    assert rc == 0
    tag_calls = [c for c in git_calls if "tag" in c and "-a" in c]
    assert any("alpha-v1.0.0" in c for c in tag_calls)
    assert any("beta-v2.0.0" in c for c in tag_calls)
    out = capsys.readouterr().out
    assert "Created tag 'alpha-v1.0.0'" in out
    assert "Created tag 'beta-v2.0.0'" in out


def test_cmd_tag_create_batch_requires_group_token_in_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Fails fast if --prefix omits {group} while --group lists multiple groups."""
    monkeypatch.chdir(tmp_path)
    conf = _make_multi_group_config(tmp_path, {"alpha": "1.0.0", "beta": "2.0.0"})
    monkeypatch.setattr("repo_release_tools.commands.tag.load_or_autodetect_config", lambda _: conf)

    rc = cmd_tag_create(_args_create(prefix="v", group="alpha,beta"))

    assert rc == 1
    assert "must include the '{group}' placeholder" in capsys.readouterr().err


def test_cmd_tag_create_batch_unknown_group_fails_before_any_tag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An unknown group name in the list fails the whole batch before tagging anything."""
    monkeypatch.chdir(tmp_path)
    conf = _make_multi_group_config(tmp_path, {"alpha": "1.0.0"})
    monkeypatch.setattr("repo_release_tools.commands.tag.load_or_autodetect_config", lambda _: conf)
    monkeypatch.setattr("repo_release_tools.commands.tag._existing_tags", lambda _: [])

    rc = cmd_tag_create(_args_create(prefix="{group}-v", group="alpha,doesnotexist"))

    assert rc == 1
    assert "Unknown version group" in capsys.readouterr().err


def test_cmd_tag_create_batch_duplicate_group_fails_before_any_tag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A repeated group name in the list fails fast with a clear error."""
    monkeypatch.chdir(tmp_path)
    conf = _make_multi_group_config(tmp_path, {"alpha": "1.0.0", "beta": "2.0.0"})
    monkeypatch.setattr("repo_release_tools.commands.tag.load_or_autodetect_config", lambda _: conf)

    rc = cmd_tag_create(_args_create(prefix="{group}-v", group="alpha,alpha,beta"))

    assert rc == 1
    captured = capsys.readouterr().err
    assert "Duplicate group name" in captured
    assert "'alpha'" in captured


def test_cmd_tag_create_batch_existing_tag_without_force_fails_all(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A pre-existing tag for one group blocks the whole batch (validate-all-then-apply-all)."""
    monkeypatch.chdir(tmp_path)
    conf = _make_multi_group_config(tmp_path, {"alpha": "1.0.0", "beta": "2.0.0"})
    monkeypatch.setattr("repo_release_tools.commands.tag.load_or_autodetect_config", lambda _: conf)
    monkeypatch.setattr("repo_release_tools.commands.tag._existing_tags", lambda _: ["beta-v2.0.0"])

    git_calls: list[list[str]] = []
    monkeypatch.setattr(
        "repo_release_tools.commands.tag._git",
        lambda cmd, _root, **kwargs: git_calls.append(cmd),
    )

    rc = cmd_tag_create(_args_create(prefix="{group}-v", group="alpha,beta"))

    captured = capsys.readouterr()
    assert rc == 1
    assert "already exists" in captured.err
    assert not git_calls


def test_cmd_tag_create_batch_dry_run_no_tags_created(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dry-run batch previews every tag without creating any of them."""
    monkeypatch.chdir(tmp_path)
    conf = _make_multi_group_config(tmp_path, {"alpha": "1.0.0", "beta": "2.0.0"})
    monkeypatch.setattr("repo_release_tools.commands.tag.load_or_autodetect_config", lambda _: conf)
    monkeypatch.setattr("repo_release_tools.commands.tag._existing_tags", lambda _: [])

    git_calls: list[list[str]] = []
    monkeypatch.setattr(
        "repo_release_tools.commands.tag._git",
        lambda cmd, _root, **kwargs: git_calls.append(cmd),
    )

    rc = cmd_tag_create(_args_create(prefix="{group}-v", group="alpha,beta", dry_run=True))

    out = capsys.readouterr().out
    assert rc == 0
    assert not git_calls
    assert "would run: git tag -a alpha-v1.0.0" in out
    assert "would run: git tag -a beta-v2.0.0" in out
    assert "no changes were made" in out


def test_cmd_tag_check_batch_aggregates_results_across_all_groups(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Evaluates every group even when an earlier one has errors, aggregating the result."""
    monkeypatch.chdir(tmp_path)
    conf = _make_multi_group_config(tmp_path, {"alpha": "1.0.0", "beta": "2.0.0"})
    monkeypatch.setattr("repo_release_tools.commands.tag.load_or_autodetect_config", lambda _: conf)
    monkeypatch.setattr("repo_release_tools.commands.tag._existing_tags", lambda _: ["beta-v2.0.0"])

    rc = cmd_tag_check(_args_check(prefix="{group}-v", strict=True, group="alpha,beta"))

    out = capsys.readouterr().out
    assert rc == 1
    assert "alpha-v1.0.0" in out
    assert "beta-v2.0.0" in out
    assert "is present and consistent" in out


def test_cmd_tag_check_batch_requires_group_token_in_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Fails fast if --prefix omits {group} while --group lists multiple groups."""
    monkeypatch.chdir(tmp_path)
    conf = _make_multi_group_config(tmp_path, {"alpha": "1.0.0", "beta": "2.0.0"})
    monkeypatch.setattr("repo_release_tools.commands.tag.load_or_autodetect_config", lambda _: conf)

    rc = cmd_tag_check(_args_check(prefix="v", group="alpha,beta"))

    assert rc == 1
    assert "must include the '{group}' placeholder" in capsys.readouterr().err


def test_cmd_tag_create_single_group_unaffected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A single, comma-free --group value still takes the pre-existing single-group path."""
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

    rc = cmd_tag_create(_args_create(group="default"))

    assert rc == 0
    assert any("v1.2.3" in c for c in git_calls if "tag" in c and "-a" in c)


def test_cmd_tag_check_single_group_unaffected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A single, comma-free --group value still takes the pre-existing single-group path."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    monkeypatch.setattr("repo_release_tools.commands.tag.load_or_autodetect_config", lambda _: conf)
    monkeypatch.setattr("repo_release_tools.commands.tag._existing_tags", lambda _: ["v1.2.3"])

    rc = cmd_tag_check(_args_check(group="default"))

    assert rc == 0
    assert "is present and consistent" in capsys.readouterr().out


def test_cmd_tag_create_batch_no_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 when no rrt config is found for a batch invocation."""
    monkeypatch.chdir(tmp_path)
    rc = cmd_tag_create(_args_create(prefix="{group}-v", group="alpha,beta"))
    assert rc == 1
    assert capsys.readouterr().err


def test_cmd_tag_create_batch_is_missing_rrt_error(
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
    rc = cmd_tag_create(_args_create(prefix="{group}-v", group="alpha,beta"))
    assert rc == 1
    assert capsys.readouterr().err


def test_cmd_tag_create_batch_value_error_non_rrt(
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
    rc = cmd_tag_create(_args_create(prefix="{group}-v", group="alpha,beta"))
    assert rc == 1
    assert capsys.readouterr().err


def test_cmd_tag_create_batch_force_deletes_and_recreates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--force deletes and recreates an already-existing tag for one group in the batch."""
    monkeypatch.chdir(tmp_path)
    conf = _make_multi_group_config(tmp_path, {"alpha": "1.0.0", "beta": "2.0.0"})
    monkeypatch.setattr("repo_release_tools.commands.tag.load_or_autodetect_config", lambda _: conf)
    monkeypatch.setattr(
        "repo_release_tools.commands.tag._existing_tags", lambda _: ["alpha-v1.0.0"]
    )

    git_calls: list[list[str]] = []

    def _fake_git(cmd: list[str], _root: Path, **kwargs: object) -> MagicMock:
        git_calls.append(cmd)
        m = MagicMock()
        m.stderr = ""
        return m

    monkeypatch.setattr("repo_release_tools.commands.tag._git", _fake_git)

    rc = cmd_tag_create(_args_create(prefix="{group}-v", group="alpha,beta", force=True))

    assert rc == 0
    delete_calls = [c for c in git_calls if "tag" in c and "-d" in c]
    assert any("alpha-v1.0.0" in c for c in delete_calls)


def test_cmd_tag_create_batch_git_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 and stops the batch when `git tag` fails for a group."""
    monkeypatch.chdir(tmp_path)
    conf = _make_multi_group_config(tmp_path, {"alpha": "1.0.0", "beta": "2.0.0"})
    monkeypatch.setattr("repo_release_tools.commands.tag.load_or_autodetect_config", lambda _: conf)
    monkeypatch.setattr("repo_release_tools.commands.tag._existing_tags", lambda _: [])

    def _fail_git(cmd: list[str], _root: Path, **kwargs: object) -> MagicMock:
        if "-a" in cmd:
            exc = subprocess.CalledProcessError(1, cmd)
            exc.stderr = "fatal: tag already exists"
            raise exc
        m = MagicMock()
        m.stderr = ""
        return m

    monkeypatch.setattr("repo_release_tools.commands.tag._git", _fail_git)

    rc = cmd_tag_create(_args_create(prefix="{group}-v", group="alpha,beta"))

    assert rc == 1
    assert "git tag failed" in capsys.readouterr().err


def test_cmd_tag_create_batch_with_push(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--push pushes each group's tag to origin after creating it."""
    monkeypatch.chdir(tmp_path)
    conf = _make_multi_group_config(tmp_path, {"alpha": "1.0.0", "beta": "2.0.0"})
    monkeypatch.setattr("repo_release_tools.commands.tag.load_or_autodetect_config", lambda _: conf)
    monkeypatch.setattr("repo_release_tools.commands.tag._existing_tags", lambda _: [])

    git_calls: list[list[str]] = []

    def _fake_git(cmd: list[str], _root: Path, **kwargs: object) -> MagicMock:
        git_calls.append(cmd)
        m = MagicMock()
        m.stderr = ""
        return m

    monkeypatch.setattr("repo_release_tools.commands.tag._git", _fake_git)

    rc = cmd_tag_create(_args_create(prefix="{group}-v", group="alpha,beta", push=True))

    assert rc == 0
    assert any("push" in c and "alpha-v1.0.0" in c for c in git_calls)
    assert "Pushed 'alpha-v1.0.0' to origin" in capsys.readouterr().out


def test_cmd_tag_create_batch_push_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 and stops the batch when `git push` fails for a group."""
    monkeypatch.chdir(tmp_path)
    conf = _make_multi_group_config(tmp_path, {"alpha": "1.0.0", "beta": "2.0.0"})
    monkeypatch.setattr("repo_release_tools.commands.tag.load_or_autodetect_config", lambda _: conf)
    monkeypatch.setattr("repo_release_tools.commands.tag._existing_tags", lambda _: [])

    def _fake_git(cmd: list[str], _root: Path, **kwargs: object) -> MagicMock:
        if "push" in cmd:
            exc = subprocess.CalledProcessError(1, cmd)
            exc.stderr = "remote: repository not found"
            raise exc
        m = MagicMock()
        m.stderr = ""
        return m

    monkeypatch.setattr("repo_release_tools.commands.tag._git", _fake_git)

    rc = cmd_tag_create(_args_create(prefix="{group}-v", group="alpha,beta", push=True))

    assert rc == 1
    assert "git push failed" in capsys.readouterr().err


def test_cmd_tag_create_batch_empty_group_names_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A --group value that is only commas/whitespace fails before any group resolves."""
    monkeypatch.chdir(tmp_path)
    rc = cmd_tag_create(_args_create(group=" , ,"))
    assert rc == 1
    assert "no valid group names" in capsys.readouterr().err


def test_cmd_tag_check_batch_no_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 when no rrt config is found for a batch invocation."""
    monkeypatch.chdir(tmp_path)
    rc = cmd_tag_check(_args_check(prefix="{group}-v", group="alpha,beta"))
    assert rc == 1
    assert capsys.readouterr().err


def test_cmd_tag_check_batch_is_missing_rrt_error(
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
    rc = cmd_tag_check(_args_check(prefix="{group}-v", group="alpha,beta"))
    assert rc == 1
    assert capsys.readouterr().err


def test_cmd_tag_check_batch_value_error_non_rrt(
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
    rc = cmd_tag_check(_args_check(prefix="{group}-v", group="alpha,beta"))
    assert rc == 1
    assert capsys.readouterr().err


def test_cmd_tag_check_batch_unknown_group_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An unknown group name in the list fails before checking anything."""
    monkeypatch.chdir(tmp_path)
    conf = _make_multi_group_config(tmp_path, {"alpha": "1.0.0"})
    monkeypatch.setattr("repo_release_tools.commands.tag.load_or_autodetect_config", lambda _: conf)

    rc = cmd_tag_check(_args_check(prefix="{group}-v", group="alpha,doesnotexist"))

    assert rc == 1
    assert "Unknown version group" in capsys.readouterr().err


def test_cmd_tag_check_batch_reports_missing_tag_when_not_strict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Non-strict mode reports a missing expected tag without failing the group."""
    monkeypatch.chdir(tmp_path)
    conf = _make_multi_group_config(tmp_path, {"alpha": "1.0.0", "beta": "2.0.0"})
    monkeypatch.setattr("repo_release_tools.commands.tag.load_or_autodetect_config", lambda _: conf)
    monkeypatch.setattr("repo_release_tools.commands.tag._existing_tags", lambda _: [])

    rc = cmd_tag_check(_args_check(prefix="{group}-v", strict=False, group="alpha,beta"))

    out = capsys.readouterr().out
    assert rc == 0
    assert "Expected tag 'alpha-v1.0.0' not found" in out


def test_cmd_tag_check_batch_duplicate_group_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A repeated group name in the list fails fast with a clear error."""
    monkeypatch.chdir(tmp_path)
    rc = cmd_tag_check(_args_check(prefix="{group}-v", group="alpha,alpha,beta"))

    assert rc == 1
    captured = capsys.readouterr().err
    assert "Duplicate group name" in captured
    assert "'alpha'" in captured


def test_cmd_tag_check_batch_empty_group_names_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A --group value that is only commas/whitespace fails before any group resolves."""
    monkeypatch.chdir(tmp_path)
    rc = cmd_tag_check(_args_check(group=" , ,"))
    assert rc == 1
    assert "no valid group names" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# --prefix defaults to the group's configured tag_prefix (issue #251)
# ---------------------------------------------------------------------------


def test_resolve_prefix_falls_back_to_group_tag_prefix(tmp_path: Path) -> None:
    """An omitted --prefix resolves to the group's configured tag_prefix."""
    group = _make_multi_group_config(tmp_path, {"sdk": "1.0.0"}, {"sdk": "sdk-v"}).resolve_group(
        "sdk"
    )

    assert _resolve_prefix(None, group) == "sdk-v"


def test_resolve_prefix_explicit_flag_wins_over_config(tmp_path: Path) -> None:
    """An explicit --prefix overrides config, including an explicit empty prefix."""
    group = _make_multi_group_config(tmp_path, {"sdk": "1.0.0"}, {"sdk": "sdk-v"}).resolve_group(
        "sdk"
    )

    assert _resolve_prefix("rel-", group) == "rel-"
    assert _resolve_prefix("", group) == ""


def test_cmd_tag_create_uses_configured_tag_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Without --prefix, the tag is named from the group's tag_prefix."""
    monkeypatch.chdir(tmp_path)
    conf = _make_multi_group_config(tmp_path, {"sdk": "1.2.3"}, {"sdk": "sdk-v"})
    monkeypatch.setattr("repo_release_tools.commands.tag.load_or_autodetect_config", lambda _: conf)
    monkeypatch.setattr("repo_release_tools.commands.tag._existing_tags", lambda _: [])

    git_calls: list[list[str]] = []

    def _fake_git(cmd: list[str], _root: Path, **kwargs: object) -> MagicMock:
        git_calls.append(cmd)
        m = MagicMock()
        m.stderr = ""
        return m

    monkeypatch.setattr("repo_release_tools.commands.tag._git", _fake_git)

    rc = cmd_tag_create(_args_create(prefix=None, group="sdk"))

    assert rc == 0
    assert ["git", "tag", "-a", "sdk-v1.2.3", "-m", "Release sdk-v1.2.3"] in git_calls
    assert "Created tag 'sdk-v1.2.3'" in capsys.readouterr().out


def test_cmd_tag_create_explicit_prefix_overrides_configured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit --prefix still wins over the group's tag_prefix."""
    monkeypatch.chdir(tmp_path)
    conf = _make_multi_group_config(tmp_path, {"sdk": "1.2.3"}, {"sdk": "sdk-v"})
    monkeypatch.setattr("repo_release_tools.commands.tag.load_or_autodetect_config", lambda _: conf)
    monkeypatch.setattr("repo_release_tools.commands.tag._existing_tags", lambda _: [])

    git_calls: list[list[str]] = []

    def _fake_git(cmd: list[str], _root: Path, **kwargs: object) -> MagicMock:
        git_calls.append(cmd)
        m = MagicMock()
        m.stderr = ""
        return m

    monkeypatch.setattr("repo_release_tools.commands.tag._git", _fake_git)

    assert cmd_tag_create(_args_create(prefix="", group="sdk")) == 0
    assert ["git", "tag", "-a", "1.2.3", "-m", "Release 1.2.3"] in git_calls


def test_cmd_tag_check_uses_configured_tag_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A prefixed group's own tags are accepted without passing --prefix."""
    monkeypatch.chdir(tmp_path)
    conf = _make_multi_group_config(tmp_path, {"sdk": "1.2.3"}, {"sdk": "sdk-v"})
    monkeypatch.setattr("repo_release_tools.commands.tag.load_or_autodetect_config", lambda _: conf)
    monkeypatch.setattr(
        "repo_release_tools.commands.tag._existing_tags",
        lambda _: ["sdk-v1.2.3", "sdk-v1.1.0"],
    )

    rc = cmd_tag_check(_args_check(prefix=None, strict=True, group="sdk"))

    assert rc == 0
    assert "Tag 'sdk-v1.2.3' is present and consistent." in capsys.readouterr().out


def test_cmd_tag_create_batch_without_prefix_uses_each_groups_tag_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Batch mode without --prefix needs no {group} token: each group brings its own."""
    monkeypatch.chdir(tmp_path)
    conf = _make_multi_group_config(
        tmp_path,
        {"alpha": "1.0.0", "beta": "2.0.0"},
        {"alpha": "alpha-v", "beta": "beta-"},
    )
    monkeypatch.setattr("repo_release_tools.commands.tag.load_or_autodetect_config", lambda _: conf)
    monkeypatch.setattr("repo_release_tools.commands.tag._existing_tags", lambda _: [])

    git_calls: list[list[str]] = []

    def _fake_git(cmd: list[str], _root: Path, **kwargs: object) -> MagicMock:
        git_calls.append(cmd)
        m = MagicMock()
        m.stderr = ""
        return m

    monkeypatch.setattr("repo_release_tools.commands.tag._git", _fake_git)

    rc = cmd_tag_create(_args_create(prefix=None, group="alpha,beta"))

    assert rc == 0
    tagged = [c[3] for c in git_calls if c[:3] == ["git", "tag", "-a"]]
    assert tagged == ["alpha-v1.0.0", "beta-2.0.0"]


def test_cmd_tag_check_batch_without_prefix_uses_each_groups_tag_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Each group is checked against its own configured prefix."""
    monkeypatch.chdir(tmp_path)
    conf = _make_multi_group_config(
        tmp_path,
        {"alpha": "1.0.0", "beta": "2.0.0"},
        {"alpha": "alpha-v", "beta": "beta-v"},
    )
    monkeypatch.setattr("repo_release_tools.commands.tag.load_or_autodetect_config", lambda _: conf)
    monkeypatch.setattr(
        "repo_release_tools.commands.tag._existing_tags",
        lambda _: ["alpha-v1.0.0", "beta-v2.0.0"],
    )

    rc = cmd_tag_check(_args_check(prefix=None, strict=True, group="alpha,beta"))

    out = capsys.readouterr().out
    assert rc == 1  # each group flags the other group's tag as a prefix mismatch
    assert "Tag 'beta-v2.0.0' does not match prefix 'alpha-v'" in out
    assert "Tag 'alpha-v1.0.0' does not match prefix 'beta-v'" in out


def test_single_group_renders_group_token_from_configured_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A repo-wide tag_prefix of '{group}-v' renders in single-group mode too."""
    monkeypatch.chdir(tmp_path)
    conf = _make_multi_group_config(tmp_path, {"sdk": "1.2.3"}, {"sdk": "{group}-v"})
    monkeypatch.setattr("repo_release_tools.commands.tag.load_or_autodetect_config", lambda _: conf)
    monkeypatch.setattr("repo_release_tools.commands.tag._existing_tags", lambda _: ["sdk-v1.2.3"])

    assert cmd_tag_create(_args_create(prefix=None, group="sdk", dry_run=True)) == 1
    assert "Tag 'sdk-v1.2.3' already exists" in capsys.readouterr().err

    assert cmd_tag_check(_args_check(prefix=None, strict=True, group="sdk")) == 0
    assert "Tag 'sdk-v1.2.3' is present and consistent." in capsys.readouterr().out
