"""Tests for rrt config command."""

from __future__ import annotations

import argparse
from pathlib import Path

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


def test_cmd_config_no_config_file(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)

    rc = config_cmd.cmd_config(_ARGS)

    assert rc == 1
    assert capsys.readouterr().err  # some guidance printed to stderr


def test_cmd_config_renders_panel_header(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    monkeypatch.setattr(config_cmd.cfg, "load_or_autodetect_config", lambda _: conf)

    rc = config_cmd.cmd_config(_ARGS)

    captured = capsys.readouterr().out
    assert rc == 0
    assert "rrt config" in captured
    assert "version groups" in captured


def test_cmd_config_shows_autodetected_label(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path, autodetected=True)
    monkeypatch.setattr(config_cmd.cfg, "load_or_autodetect_config", lambda _: conf)

    rc = config_cmd.cmd_config(_ARGS)

    assert rc == 0
    assert "(auto-detected)" in capsys.readouterr().out


def test_cmd_config_shows_explicit_config_file(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path, autodetected=False)
    monkeypatch.setattr(config_cmd.cfg, "load_or_autodetect_config", lambda _: conf)

    rc = config_cmd.cmd_config(_ARGS)

    assert rc == 0
    out = capsys.readouterr().out
    assert "pyproject.toml" in out


def test_cmd_config_tree_shows_release_branch(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    monkeypatch.setattr(config_cmd.cfg, "load_or_autodetect_config", lambda _: conf)

    config_cmd.cmd_config(_ARGS)

    out = capsys.readouterr().out
    assert "release/v{version}" in out


def test_cmd_config_tree_shows_lock_command(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    monkeypatch.setattr(config_cmd.cfg, "load_or_autodetect_config", lambda _: conf)

    config_cmd.cmd_config(_ARGS)

    out = capsys.readouterr().out
    assert "uv lock" in out


def test_cmd_config_tree_shows_version_targets(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    monkeypatch.setattr(config_cmd.cfg, "load_or_autodetect_config", lambda _: conf)

    config_cmd.cmd_config(_ARGS)

    out = capsys.readouterr().out
    assert "__version__" in out


def test_cmd_config_tree_shows_generated_files(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    conf = _make_config(tmp_path)
    monkeypatch.setattr(config_cmd.cfg, "load_or_autodetect_config", lambda _: conf)

    config_cmd.cmd_config(_ARGS)

    out = capsys.readouterr().out
    assert "uv.lock" in out


def test_cmd_config_tree_describes_pattern_target_without_none_label(
    tmp_path: Path, monkeypatch, capsys
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


def test_cmd_config_multiple_groups(tmp_path: Path, monkeypatch, capsys) -> None:
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


def test_cmd_config_value_error_shows_message(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)

    def raise_value_error(_root):
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


def test_cmd_config_raw_prints_toml(tmp_path: Path, monkeypatch, capsys) -> None:
    from repo_release_tools.commands import config_cmd
    from repo_release_tools import output

    toml_content = '[tool.rrt]\nrelease_branch = "release/v{version}"\n'
    config_path = tmp_path / "pyproject.toml"
    config_path.write_text(toml_content)

    conf = _make_config(tmp_path)
    # Override config_file to point at our temp file
    from dataclasses import replace

    conf = replace(conf, config_file=config_path)

    import repo_release_tools.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "load_or_autodetect_config", lambda _: conf)
    monkeypatch.setattr(output, "highlight_terminal", lambda code, lang, **kw: code)
    monkeypatch.chdir(tmp_path)

    args = argparse.Namespace(raw=True)
    rc = config_cmd.cmd_config(args)
    captured = capsys.readouterr()
    assert rc == 0
    assert "tool.rrt" in captured.out


def test_cmd_config_raw_unreadable_file(tmp_path: Path, monkeypatch, capsys) -> None:
    conf = _make_config(tmp_path)
    # Don't create the file so OSError is raised
    import repo_release_tools.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "load_or_autodetect_config", lambda _: conf)
    monkeypatch.chdir(tmp_path)

    args = argparse.Namespace(raw=True)
    rc = config_cmd.cmd_config(args)
    assert rc == 1


def test_cmd_config_panel_uses_rule_separator(tmp_path: Path, monkeypatch, capsys) -> None:
    conf = _make_config(tmp_path)
    import repo_release_tools.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "load_or_autodetect_config", lambda _: conf)
    monkeypatch.chdir(tmp_path)

    args = argparse.Namespace(raw=False)
    rc = config_cmd.cmd_config(args)
    captured = capsys.readouterr()
    assert rc == 0
    assert "Version groups" in captured.out


def test_cmd_config_aligns_tree_details(tmp_path: Path, monkeypatch, capsys) -> None:
    conf = _make_config(tmp_path)
    import repo_release_tools.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "load_or_autodetect_config", lambda _: conf)
    monkeypatch.chdir(tmp_path)

    rc = config_cmd.cmd_config(argparse.Namespace(raw=False))
    captured = capsys.readouterr()

    assert rc == 0
    assert "release_branch  release/v{version}" in captured.out
    assert "changelog       CHANGELOG.md" in captured.out
    assert "lock_command    uv lock" in captured.out
