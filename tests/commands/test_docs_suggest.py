"""Tests for the docs docstring suggestion feature."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from repo_release_tools.commands.docs_suggest import (
    DEFAULT_MIN_CHARS,
    build_scaffold,
    cmd_docs_suggest,
    scan,
)

MIN_DEFAULT = DEFAULT_MIN_CHARS
STRICT_MIN_CHARS = 200
SHORT_MIN_CHARS = 10


def _load_min_chars() -> int:
    raw = os.getenv("RRT_DOCSTRING_MIN_CHARS")
    if raw is None:
        return MIN_DEFAULT
    try:
        return int(raw)
    except ValueError:
        pytest.fail(f"RRT_DOCSTRING_MIN_CHARS must be an integer; got {raw!r}")


def test_build_scaffold_mentions_command_name() -> None:
    scaffold = build_scaffold(Path("src/repo_release_tools/commands/ci_version.py"))
    assert "rrt ci-version" in scaffold
    assert "## Overview" in scaffold


def test_build_scaffold_strips_cmd_suffix() -> None:
    scaffold = build_scaffold(Path("src/repo_release_tools/commands/folder_cmd.py"))
    assert "rrt folder" in scaffold


def test_scan_detects_missing_docstring(tmp_path: Path) -> None:
    target = tmp_path / "example.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")

    findings = scan([tmp_path])

    assert findings
    assert findings[0].path == target


def test_scan_ignores_exempt_init_files(tmp_path: Path) -> None:
    target = tmp_path / "__init__.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")

    findings = scan([tmp_path])

    assert findings == []


def test_scan_skips_healthy_docstring(tmp_path: Path) -> None:
    target = tmp_path / "example.py"
    target.write_text('"""Long enough docstring.\n\nBody text.\n"""\n', encoding="utf-8")

    findings = scan([tmp_path], min_chars=SHORT_MIN_CHARS)

    assert findings == []


def test_scan_ignores_rrt_docs_exempt_marker(tmp_path: Path) -> None:
    target = tmp_path / "example.py"
    target.write_text(
        '# rrt:docs-exempt\n"""Short docstring."""\nVALUE = 1\n',
        encoding="utf-8",
    )

    findings = scan([tmp_path], min_chars=STRICT_MIN_CHARS)

    assert findings == []


def test_cmd_docs_suggest_applies_scaffold(tmp_path: Path) -> None:
    target = tmp_path / "example.py"
    target.write_text("from __future__ import annotations\n\nVALUE = 1\n", encoding="utf-8")

    args = argparse.Namespace(
        root=str(tmp_path),
        paths=[str(target)],
        min_chars=MIN_DEFAULT,
        apply=True,
    )

    result = cmd_docs_suggest(args)

    assert result == 0
    assert target.read_text(encoding="utf-8").startswith('"""')


def test_cmd_docs_suggest_replaces_existing_docstring(tmp_path: Path) -> None:
    target = tmp_path / "example.py"
    target.write_text('"""Short docstring.\n\nBody.\n"""\nVALUE = 1\n', encoding="utf-8")

    args = argparse.Namespace(
        root=str(tmp_path),
        paths=[str(target)],
        min_chars=STRICT_MIN_CHARS,
        apply=True,
    )

    result = cmd_docs_suggest(args)

    assert result == 0
    rewritten = target.read_text(encoding="utf-8")
    assert rewritten.startswith('"""')
    assert "Short docstring" not in rewritten


def test_cmd_docs_suggest_inserts_after_shebang_and_encoding_comment(tmp_path: Path) -> None:
    target = tmp_path / "example.py"
    target.write_text(
        "#!/usr/bin/env python3\n# coding: utf-8\nVALUE = 1\n",
        encoding="utf-8",
    )

    args = argparse.Namespace(
        root=str(tmp_path),
        paths=[str(target)],
        min_chars=STRICT_MIN_CHARS,
        apply=True,
    )

    result = cmd_docs_suggest(args)

    assert result == 0
    lines = target.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "#!/usr/bin/env python3"
    assert lines[1] == "# coding: utf-8"
    assert lines[2].startswith('"""')


def test_cmd_docs_suggest_resolves_relative_paths_against_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo_src = repo / "src"
    repo_src.mkdir(parents=True)
    target = repo_src / "example.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    args = argparse.Namespace(
        root=str(repo),
        paths=["src/example.py"],
        min_chars=MIN_DEFAULT,
        apply=True,
    )

    result = cmd_docs_suggest(args)

    assert result == 0
    assert target.read_text(encoding="utf-8").startswith('"""')


def test_cmd_docs_suggest_skips_unparseable_apply_targets(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "broken.py"
    target.write_text("def broken(\n", encoding="utf-8")

    args = argparse.Namespace(
        root=str(tmp_path),
        paths=[str(target)],
        min_chars=MIN_DEFAULT,
        apply=True,
    )

    result = cmd_docs_suggest(args)
    captured = capsys.readouterr()

    assert result == 0
    assert "failed to parse" in captured.err
    assert target.read_text(encoding="utf-8") == "def broken(\n"


def test_cmd_docs_suggest_handles_paths_outside_root(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    target = tmp_path / "outside.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")

    args = argparse.Namespace(
        root=str(root),
        paths=[str(target)],
        min_chars=STRICT_MIN_CHARS,
        apply=False,
    )

    result = cmd_docs_suggest(args)
    captured = capsys.readouterr()

    assert result == 0
    assert str(target) in captured.out


def test_cmd_docs_suggest_no_findings(tmp_path: Path) -> None:
    target = tmp_path / "example.py"
    target.write_text('"""Long enough docstring.\n\nBody text.\n"""\n', encoding="utf-8")

    args = argparse.Namespace(
        root=str(tmp_path),
        paths=[str(target)],
        min_chars=SHORT_MIN_CHARS,
        apply=False,
    )

    result = cmd_docs_suggest(args)

    assert result == 0
    assert target.read_text(encoding="utf-8").startswith('"""')


def test_cmd_docs_suggest_uses_config_min_chars_when_arg_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "repo_release_tools.config.load_config",
        lambda root: SimpleNamespace(
            docs=SimpleNamespace(
                suggest_roots=(),
                src_dir=".",
                suggest_exempt=(),
                suggest_min_chars=10,
            ),
        ),
    )
    target = tmp_path / "example.py"
    target.write_text(
        '"""Short docstring with enough chars for config.\n\nbody"""\nVALUE = 1\n',
        encoding="utf-8",
    )
    args = argparse.Namespace(root=str(tmp_path), paths=[str(target)], min_chars=None, apply=False)

    result = cmd_docs_suggest(args)
    captured = capsys.readouterr()

    assert result == 0
    assert "No docstring scaffolds needed." in captured.out


def test_load_min_chars_rejects_invalid_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RRT_DOCSTRING_MIN_CHARS", "oops")

    with pytest.raises(pytest.fail.Exception, match="must be an integer"):
        _load_min_chars()
