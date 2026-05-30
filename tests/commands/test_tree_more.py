import argparse
import json
from pathlib import Path
from typing import Any

import pytest

from repo_release_tools.commands.tree import (
    _inject_rendered_tree,
    _render_ascii_tree,
    _render_markdown_tree,
    _write_tree_manifest,
    cmd_tree,
    register,
)
from repo_release_tools.state import build_tree_lock, tree_lock_path, write_lock
from repo_release_tools.ui import DryRunPrinter


def test_renderers_simple() -> None:
    entries = [("a.txt", False, None), ("bdir", True, [("c.txt", False, None)])]
    ascii_out = _render_ascii_tree(entries)
    assert "a.txt" in ascii_out and "c.txt" in ascii_out and "bdir/" in ascii_out

    md_out = _render_markdown_tree(entries)
    assert "- a.txt" in md_out and "- c.txt" in md_out and "- bdir/" in md_out


def test_write_tree_manifest_dry_run_and_compressed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path
    # create an actual file so manifest flattening can stat it
    (root / "file1.txt").write_text("hello")

    entries: list[Any] = [("file1.txt", False, None)]
    p = DryRunPrinter(True)
    warnings: list[str] = []

    # dry-run + compressed should print action and the JSON manifest to stdout
    _write_tree_manifest(entries, root, p, hash_files=False, warnings=warnings, compressed=True)
    captured = capsys.readouterr()
    assert "[dry-run]" in captured.out
    assert "files" in captured.out


def test_cmd_tree_manifest_diff(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path
    # create some files to represent the current tree
    (root / "a.txt").write_text("x")
    d = root / "dir1"
    d.mkdir()
    (d / "b.txt").write_text("y")

    # create a previous manifest that differs
    manifest_dir = root / ".rrt"
    manifest_dir.mkdir()
    prev_files = [{"path": "old.txt", "is_dir": False}, {"path": "dir1", "is_dir": True}]
    manifest = {"files": prev_files}
    (manifest_dir / "tree.manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    # create a stale tree lock so cmd_tree will detect drift
    write_lock(tree_lock_path(root), build_tree_lock({"entry_count": 1, "tree_hash": "sha256:old"}))

    args = argparse.Namespace(
        root=str(root),
        format="classic",
        max_depth=None,
        dirs_only=False,
        show_hidden=False,
        snapshot=False,
        check=True,
        manifest=False,
        compressed=False,
        strict=False,
        dry_run=False,
        inject=None,
        anchor=None,
    )

    rc = cmd_tree(args)
    out = capsys.readouterr().out
    assert rc == 0
    assert "Detailed manifest diff" in out or "added (" in out or "removed (" in out


def test_inject_rendered_tree_missing_anchor_and_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    p = DryRunPrinter(False)
    # missing file
    rc = _inject_rendered_tree(
        p, inject_file=str(tmp_path / "nope.md"), anchor_id="x", rendered="r"
    )
    assert rc == 1

    # existing file but missing anchor
    target = tmp_path / "t.md"
    target.write_text("no anchors here")
    rc2 = _inject_rendered_tree(p, inject_file=str(target), anchor_id="x", rendered="r")
    assert rc2 == 1


def test_register_adds_subparser() -> None:
    parser = argparse.ArgumentParser()
    sp = parser.add_subparsers()
    register(sp)
    # parsing help for the subcommand should succeed (SystemExit with code 0)
    try:
        parser.parse_args(["tree", "--help"])
    except SystemExit as exc:
        assert exc.code == 0
