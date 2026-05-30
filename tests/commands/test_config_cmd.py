"""Tests for rrt config command."""

from __future__ import annotations

import argparse
from collections.abc import Iterator
from pathlib import Path

import pytest

from repo_release_tools.commands import config_cmd
from repo_release_tools.config import (
    RrtConfig,
    VersionGroup,
    VersionTarget,
)

_MINIMAL_CONFIG = """\
[tool.rrt]
release_branch = "release/v{version}"

[[tool.rrt.version_targets]]
path = "src/pkg/__init__.py"
kind = "python_version"
"""

_ARGS = argparse.Namespace()


def _make_config(tmp_path: Path, *, autodetected: bool = False) -> RrtConfig:
    target = VersionTarget(
        path=tmp_path / "src" / "pkg" / "__init__.py",
        kind="python_version",
    )
    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=tmp_path / "CHANGELOG.md",
        lock_command=["uv", "lock"],
        generated_files=[tmp_path / "uv.lock"],
        version_targets=[target],
    )
    return RrtConfig(
        root=tmp_path,
        config_file=tmp_path / "pyproject.toml",
        version_groups=[group],
        default_group_name="default",
        autodetected=autodetected,
    )


def test_cmd_config_no_config_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    rc = config_cmd.cmd_config(_ARGS)

    assert rc == 1
    assert capsys.readouterr().err  # some guidance printed to stderr


def test_cmd_config_renders_panel_header(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    monkeypatch.setattr(config_cmd.cfg, "load_or_autodetect_config", lambda _: conf)

    rc = config_cmd.cmd_config(_ARGS)

    captured = capsys.readouterr().out
    assert rc == 0
    assert "rrt config" in captured
    assert "Version groups" in captured


def test_cmd_config_shows_autodetected_label(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path, autodetected=True)
    monkeypatch.setattr(config_cmd.cfg, "load_or_autodetect_config", lambda _: conf)

    rc = config_cmd.cmd_config(_ARGS)

    assert rc == 0
    assert "(auto-detected)" in capsys.readouterr().out


def test_cmd_config_shows_explicit_config_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path, autodetected=False)
    monkeypatch.setattr(config_cmd.cfg, "load_or_autodetect_config", lambda _: conf)

    rc = config_cmd.cmd_config(_ARGS)

    assert rc == 0
    out = capsys.readouterr().out
    assert "pyproject.toml" in out


def test_cmd_config_from_subdir_uses_repo_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Resolves config from a nested working directory back to the repo root."""
    repo_root = tmp_path / "repo"
    nested = repo_root / "src" / "pkg"
    nested.mkdir(parents=True)
    (repo_root / "pyproject.toml").write_text("", encoding="utf-8")
    conf = _make_config(repo_root)
    monkeypatch.chdir(nested)

    def _load(root: Path) -> RrtConfig:
        assert root == repo_root
        return conf

    monkeypatch.setattr(config_cmd.cfg, "load_or_autodetect_config", _load)

    rc = config_cmd.cmd_config(_ARGS)

    out = capsys.readouterr().out
    assert rc == 0
    assert "pyproject.toml" in out


def test_cmd_config_tree_shows_release_branch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    monkeypatch.setattr(config_cmd.cfg, "load_or_autodetect_config", lambda _: conf)

    config_cmd.cmd_config(_ARGS)

    out = capsys.readouterr().out
    assert "release/v{version}" in out


def test_cmd_config_tree_shows_lock_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    monkeypatch.setattr(config_cmd.cfg, "load_or_autodetect_config", lambda _: conf)

    config_cmd.cmd_config(_ARGS)

    out = capsys.readouterr().out
    assert "uv lock" in out


def test_cmd_config_tree_shows_version_targets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    monkeypatch.setattr(config_cmd.cfg, "load_or_autodetect_config", lambda _: conf)

    config_cmd.cmd_config(_ARGS)

    out = capsys.readouterr().out
    assert "__version__" in out


def test_cmd_config_tree_shows_generated_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    monkeypatch.setattr(config_cmd.cfg, "load_or_autodetect_config", lambda _: conf)

    config_cmd.cmd_config(_ARGS)

    out = capsys.readouterr().out
    assert "uv.lock" in out


def test_cmd_config_tree_describes_pattern_target_without_none_label(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    target = VersionTarget(path=tmp_path / "VERSION.txt", pattern=r"^(version=)(.+)$")
    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=tmp_path / "CHANGELOG.md",
        lock_command=[],
        generated_files=[],
        version_targets=[target],
    )
    conf = RrtConfig(root=tmp_path, config_file=tmp_path / ".rrt.toml", version_groups=[group])
    monkeypatch.setattr(config_cmd.cfg, "load_or_autodetect_config", lambda _: conf)

    rc = config_cmd.cmd_config(_ARGS)

    out = capsys.readouterr().out
    assert rc == 0
    assert "VERSION.txt (pattern)" in out
    assert "[None]" not in out


def test_cmd_config_multiple_groups(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src" / "pkg").mkdir(parents=True)

    target_a = VersionTarget(path=tmp_path / "src" / "pkg" / "__init__.py", kind="python_version")
    target_b = VersionTarget(path=tmp_path / "package.json", kind="package_json")

    group_a = VersionGroup(
        name="python",
        release_branch="release/py-v{version}",
        changelog_file=tmp_path / "CHANGELOG.md",
        lock_command=[],
        generated_files=[],
        version_targets=[target_a],
    )
    group_b = VersionGroup(
        name="node",
        release_branch="release/node-v{version}",
        changelog_file=tmp_path / "CHANGELOG.md",
        lock_command=[],
        generated_files=[],
        version_targets=[target_b],
    )
    conf = RrtConfig(
        root=tmp_path,
        config_file=tmp_path / "pyproject.toml",
        version_groups=[group_a, group_b],
    )
    monkeypatch.setattr(config_cmd.cfg, "load_or_autodetect_config", lambda _: conf)

    rc = config_cmd.cmd_config(_ARGS)

    out = capsys.readouterr().out
    assert rc == 0
    assert "[python]" in out
    assert "[node]" in out
    assert "2 groups" in out


def test_cmd_config_value_error_shows_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    def raise_value_error(_root: object) -> None:
        raise ValueError("bad config format")

    monkeypatch.setattr(config_cmd.cfg, "load_or_autodetect_config", raise_value_error)

    rc = config_cmd.cmd_config(_ARGS)

    assert rc == 1
    assert "bad config format" in capsys.readouterr().err


def test_register_adds_config_subparser() -> None:
    import argparse as ap

    root_parser = ap.ArgumentParser()
    subs = root_parser.add_subparsers(dest="command")
    config_cmd.register(subs)
    parsed = root_parser.parse_args(["config"])
    assert parsed.command == "config"
    assert callable(parsed.handler)


def test_register_adds_raw_flag() -> None:
    import argparse as ap

    root_parser = ap.ArgumentParser()
    subs = root_parser.add_subparsers(dest="command")
    config_cmd.register(subs)
    parsed = root_parser.parse_args(["config", "--raw"])
    assert parsed.raw is True


def test_cmd_config_raw_prints_toml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from repo_release_tools.commands import config_cmd

    toml_content = '[tool.rrt]\nrelease_branch = "release/v{version}"\n'
    config_path = tmp_path / "pyproject.toml"
    config_path.write_text(toml_content)

    conf = _make_config(tmp_path)
    # Override config_file to point at our temp file
    from dataclasses import replace

    conf = replace(conf, config_file=config_path)

    import repo_release_tools.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "load_or_autodetect_config", lambda _: conf)
    monkeypatch.setattr(
        "repo_release_tools.commands.config_cmd.highlight_terminal",
        lambda code, lang, **kw: code,
    )
    monkeypatch.chdir(tmp_path)

    args = argparse.Namespace(raw=True)
    rc = config_cmd.cmd_config(args)
    captured = capsys.readouterr()
    assert rc == 0
    assert "tool.rrt" in captured.out


def test_cmd_config_raw_unreadable_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    conf = _make_config(tmp_path)
    # Don't create the file so OSError is raised
    import repo_release_tools.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "load_or_autodetect_config", lambda _: conf)
    monkeypatch.chdir(tmp_path)

    args = argparse.Namespace(raw=True)
    rc = config_cmd.cmd_config(args)
    assert rc == 1


def test_cmd_config_panel_uses_rule_separator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    conf = _make_config(tmp_path)
    import repo_release_tools.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "load_or_autodetect_config", lambda _: conf)
    monkeypatch.chdir(tmp_path)

    args = argparse.Namespace(raw=False)
    rc = config_cmd.cmd_config(args)
    captured = capsys.readouterr()
    assert rc == 0
    assert "Version groups" in captured.out


def test_cmd_config_aligns_tree_details(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    conf = _make_config(tmp_path)
    import repo_release_tools.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "load_or_autodetect_config", lambda _: conf)
    monkeypatch.chdir(tmp_path)

    rc = config_cmd.cmd_config(argparse.Namespace(raw=False))
    captured = capsys.readouterr()

    assert rc == 0
    assert "release_branch: release/v{version}" in captured.out
    assert "changelog: CHANGELOG.md" in captured.out
    assert "lock_command: uv lock" in captured.out


# ---------------------------------------------------------------------------
# cmd_config --schema (lines 215-225)
# ---------------------------------------------------------------------------


def test_cmd_config_schema_not_found_returns_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 when _load_schema returns an empty dict."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_cmd, "_load_schema", lambda: {})
    rc = config_cmd.cmd_config(argparse.Namespace(schema=True))
    assert rc == 1
    assert capsys.readouterr().err


def test_cmd_config_schema_prints_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 0 and writes JSON when schema is found."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_cmd, "_load_schema", lambda: {"title": "rrt config"})
    rc = config_cmd.cmd_config(argparse.Namespace(schema=True))
    assert rc == 0
    assert "rrt config" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# cmd_config --validate (line 228) and _cmd_validate (lines 142-207)
# ---------------------------------------------------------------------------


def test_cmd_config_validate_calls_cmd_validate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--validate triggers _cmd_validate and returns its exit code."""
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    conf.version_groups[0].version_targets[0].path.parent.mkdir(parents=True, exist_ok=True)
    conf.version_groups[0].version_targets[0].path.write_text('__version__ = "1.0.0"\n')
    monkeypatch.setattr(config_cmd.cfg, "load_or_autodetect_config", lambda _: conf)
    rc = config_cmd.cmd_config(argparse.Namespace(validate=True))
    assert rc == 0
    assert "validation checks passed" in capsys.readouterr().out


def test_cmd_validate_no_config_returns_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 when load_or_autodetect_config raises FileNotFoundError."""
    monkeypatch.chdir(tmp_path)
    rc = config_cmd._cmd_validate(tmp_path)
    assert rc == 1
    assert capsys.readouterr().err


def test_cmd_validate_value_error_returns_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 when load_or_autodetect_config raises ValueError."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        config_cmd.cfg,
        "load_or_autodetect_config",
        lambda _: (_ for _ in ()).throw(ValueError("bad")),
    )
    rc = config_cmd._cmd_validate(tmp_path)
    assert rc == 1
    assert capsys.readouterr().err


def test_cmd_validate_with_errors_returns_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 when a pin target's validate() raises ValueError."""
    from repo_release_tools.config import PinTarget

    monkeypatch.chdir(tmp_path)
    pin = PinTarget(
        path=tmp_path / "README.md",
        pattern=r"(version=)(\d+\.\d+\.\d+)",  # only 2 groups → invalid
    )
    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=tmp_path / "CHANGELOG.md",
        lock_command=[],
        generated_files=[],
        version_targets=[],
        pin_targets=[pin],
    )
    conf = RrtConfig(root=tmp_path, config_file=tmp_path / "pyproject.toml", version_groups=[group])
    monkeypatch.setattr(config_cmd.cfg, "load_or_autodetect_config", lambda _: conf)
    rc = config_cmd._cmd_validate(tmp_path)
    assert rc == 1
    captured = capsys.readouterr()
    assert "validation error" in captured.out


# ---------------------------------------------------------------------------
# _load_schema – fallback path (lines 125-137)
# ---------------------------------------------------------------------------


def test_load_schema_fallback_reads_repo_root_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Falls back to repo-root schema when importlib.resources raises."""
    import importlib.resources
    from contextlib import contextmanager

    import repo_release_tools.commands.config_cmd as _mod

    @contextmanager
    def _failing_as_file(ref: object) -> Iterator[object]:
        raise FileNotFoundError("no bundled data")
        yield  # pragma: no cover

    monkeypatch.setattr(importlib.resources, "as_file", _failing_as_file)
    fake_file = tmp_path / "repo" / "src" / "repo_release_tools" / "commands" / "config_cmd.py"
    fake_file.parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "repo" / "rrt-config.schema.json").write_text(
        '{"title": "repo-root schema"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(_mod, "__file__", str(fake_file))
    result = config_cmd._load_schema()
    assert result == {"title": "repo-root schema"}


def test_load_schema_fallback_returns_empty_when_no_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Returns {} when importlib fails and no fallback schema file exists."""
    import importlib.resources
    from contextlib import contextmanager

    import repo_release_tools.commands.config_cmd as _mod

    @contextmanager
    def _failing_as_file(ref: object) -> Iterator[object]:
        raise TypeError("no bundled data")
        yield  # pragma: no cover

    monkeypatch.setattr(importlib.resources, "as_file", _failing_as_file)
    # Redirect __file__ so the fallback path points at tmp_path (no schema there)
    monkeypatch.setattr(
        _mod,
        "__file__",
        str(tmp_path / "commands" / "config_cmd.py"),
    )
    result = config_cmd._load_schema()
    assert result == {}


def test_load_schema_success_returns_dict() -> None:
    """Returns a non-empty dict from the bundled schema resource."""
    result = config_cmd._load_schema()
    assert isinstance(result, dict)
    assert result  # bundled schema is non-empty


# ---------------------------------------------------------------------------
# _cmd_validate – remaining branch coverage (165, 174-175, 180, 185-196)
# ---------------------------------------------------------------------------


def test_cmd_validate_no_version_groups(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Returns 1 and reports error when config has no version groups."""
    monkeypatch.chdir(tmp_path)
    conf = RrtConfig(root=tmp_path, config_file=tmp_path / "pyproject.toml", version_groups=[])
    monkeypatch.setattr(config_cmd.cfg, "load_or_autodetect_config", lambda _: conf)
    rc = config_cmd._cmd_validate(tmp_path)
    assert rc == 1
    assert "No version groups" in capsys.readouterr().out


def test_cmd_validate_version_target_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Appends error when a version target's validate() raises ValueError."""
    from unittest.mock import MagicMock

    monkeypatch.chdir(tmp_path)
    mock_target = MagicMock()
    mock_target.validate.side_effect = ValueError("invalid kind")
    mock_target.path = tmp_path / "__init__.py"

    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=tmp_path / "CHANGELOG.md",
        lock_command=[],
        generated_files=[],
        version_targets=[mock_target],
        pin_targets=[],
    )
    conf = RrtConfig(root=tmp_path, config_file=tmp_path / "pyproject.toml", version_groups=[group])
    monkeypatch.setattr(config_cmd.cfg, "load_or_autodetect_config", lambda _: conf)
    rc = config_cmd._cmd_validate(tmp_path)
    assert rc == 1
    assert "validation error" in capsys.readouterr().out


def test_cmd_validate_valid_pin_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Prints ok message for a valid pin target."""
    from repo_release_tools.config import PinTarget

    monkeypatch.chdir(tmp_path)
    pin = PinTarget(
        path=tmp_path / "README.md",
        pattern=r"(version=)(\d+\.\d+\.\d+)(extra)",  # 3 groups → valid
    )
    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=tmp_path / "CHANGELOG.md",
        lock_command=[],
        generated_files=[],
        version_targets=[],
        pin_targets=[pin],
    )
    conf = RrtConfig(root=tmp_path, config_file=tmp_path / "pyproject.toml", version_groups=[group])
    monkeypatch.setattr(config_cmd.cfg, "load_or_autodetect_config", lambda _: conf)
    rc = config_cmd._cmd_validate(tmp_path)
    assert rc == 0
    assert "pin_target" in capsys.readouterr().out


def test_cmd_validate_docs_validate_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Appends error when docs.validate() raises ValueError."""
    from unittest.mock import MagicMock

    monkeypatch.chdir(tmp_path)
    mock_docs = MagicMock()
    mock_docs.validate.side_effect = ValueError("invalid docs config")

    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=tmp_path / "CHANGELOG.md",
        lock_command=[],
        generated_files=[],
        version_targets=[],
        pin_targets=[],
    )
    conf = RrtConfig(root=tmp_path, config_file=tmp_path / "pyproject.toml", version_groups=[group])
    object.__setattr__(conf, "docs", mock_docs)
    monkeypatch.setattr(config_cmd.cfg, "load_or_autodetect_config", lambda _: conf)
    rc = config_cmd._cmd_validate(tmp_path)
    assert rc == 1
    assert "docs config" in capsys.readouterr().out


def test_cmd_validate_folders_validate_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Appends error when folders.validate() raises ValueError."""
    from unittest.mock import MagicMock

    monkeypatch.chdir(tmp_path)
    mock_folders = MagicMock()
    mock_folders.validate.side_effect = ValueError("invalid folders config")

    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=tmp_path / "CHANGELOG.md",
        lock_command=[],
        generated_files=[],
        version_targets=[],
        pin_targets=[],
    )
    conf = RrtConfig(root=tmp_path, config_file=tmp_path / "pyproject.toml", version_groups=[group])
    object.__setattr__(conf, "folders", mock_folders)
    monkeypatch.setattr(config_cmd.cfg, "load_or_autodetect_config", lambda _: conf)
    rc = config_cmd._cmd_validate(tmp_path)
    assert rc == 1
    assert "folders config" in capsys.readouterr().out


def test_cmd_validate_docs_validate_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Prints ok message when docs.validate() succeeds."""
    from unittest.mock import MagicMock

    monkeypatch.chdir(tmp_path)
    mock_docs = MagicMock()
    mock_docs.validate.return_value = None

    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=tmp_path / "CHANGELOG.md",
        lock_command=[],
        generated_files=[],
        version_targets=[],
        pin_targets=[],
    )
    conf = RrtConfig(root=tmp_path, config_file=tmp_path / "pyproject.toml", version_groups=[group])
    object.__setattr__(conf, "docs", mock_docs)
    monkeypatch.setattr(config_cmd.cfg, "load_or_autodetect_config", lambda _: conf)
    rc = config_cmd._cmd_validate(tmp_path)
    assert rc == 0
    assert "docs config: valid" in capsys.readouterr().out


def test_cmd_validate_folders_validate_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Prints ok message when folders.validate() succeeds."""
    from unittest.mock import MagicMock

    monkeypatch.chdir(tmp_path)
    mock_folders = MagicMock()
    mock_folders.validate.return_value = None

    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=tmp_path / "CHANGELOG.md",
        lock_command=[],
        generated_files=[],
        version_targets=[],
        pin_targets=[],
    )
    conf = RrtConfig(root=tmp_path, config_file=tmp_path / "pyproject.toml", version_groups=[group])
    object.__setattr__(conf, "folders", mock_folders)
    monkeypatch.setattr(config_cmd.cfg, "load_or_autodetect_config", lambda _: conf)
    rc = config_cmd._cmd_validate(tmp_path)
    assert rc == 0
    assert "folders config: valid" in capsys.readouterr().out
