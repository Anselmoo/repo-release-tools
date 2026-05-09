"""Tests for the docs docstring suggestion feature."""

from __future__ import annotations

import argparse
from pathlib import Path

from repo_release_tools.commands.docs_suggest import build_scaffold, cmd_docs_suggest, scan


def test_build_scaffold_mentions_command_name() -> None:
    scaffold = build_scaffold(Path("src/repo_release_tools/commands/ci_version.py"))
    assert "rrt ci-version" in scaffold
    assert "## Overview" in scaffold


def test_scan_detects_missing_docstring(tmp_path: Path) -> None:
    target = tmp_path / "example.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")

    findings = scan([tmp_path])

    assert findings
    assert findings[0].path == target


def test_cmd_docs_suggest_applies_scaffold(tmp_path: Path) -> None:
    target = tmp_path / "example.py"
    target.write_text("from __future__ import annotations\n\nVALUE = 1\n", encoding="utf-8")

    args = argparse.Namespace(root=str(tmp_path), paths=[str(target)], min_chars=150, apply=True)

    result = cmd_docs_suggest(args)

    assert result == 0
    assert target.read_text(encoding="utf-8").startswith('"""')
