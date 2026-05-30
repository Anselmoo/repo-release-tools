import argparse
import gzip
import json
from pathlib import Path
from typing import Any

import pytest

from repo_release_tools.commands.tree import (
    _inject_rendered_tree,
    _render_rich_tree,
    _write_tree_manifest,
    cmd_tree,
)
from repo_release_tools.state import build_tree_lock, tree_lock_path, write_lock
from repo_release_tools.ui import DryRunPrinter


def test_render_rich_falls_back_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    # Simulate rich not being importable -> should return None
    import importlib

    def fake_import(name: str, package: str | None = None) -> Any:
        if name.startswith("rich."):
            raise ImportError("no rich")
        return importlib.import_module(name, package=package)

    monkeypatch.setattr(importlib, "import_module", fake_import)

    res = _render_rich_tree([("a", False, None)])
    assert res is None


def test_write_tree_manifest_creates_gz(tmp_path: Path) -> None:
    root = tmp_path
    (root / "f.txt").write_text("x")
    entries: list[Any] = [("f.txt", False, None)]
    p = DryRunPrinter(False)
    warnings: list[str] = []

    _write_tree_manifest(entries, root, p, hash_files=False, warnings=warnings, compressed=True)
    gz = root / ".rrt" / "tree.manifest.json.gz"
    assert gz.exists()


def test_manifest_then_snapshot_creates_lock_and_manifest(tmp_path: Path) -> None:
    root = tmp_path
    (root / "a.txt").write_text("hello")
    args = argparse.Namespace(
        root=str(root),
        format="classic",
        max_depth=None,
        dirs_only=False,
        show_hidden=False,
        snapshot=True,
        check=False,
        manifest=True,
        compressed=False,
        strict=False,
        dry_run=False,
        inject=None,
        anchor=None,
    )

    rc = cmd_tree(args)
    assert rc == 0
    assert (root / ".rrt" / "tree.manifest.json").exists()
    assert (root / ".rrt" / "tree.lock.toml").exists()


def test_check_strict_mode_returns_nonzero(tmp_path: Path) -> None:
    root = tmp_path
    # write a lock with no tree_hash to force the 'missing snapshot' path
    lock = tree_lock_path(root)
    write_lock(lock, {"meta": {}, "snapshot": {}})

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
        strict=True,
        dry_run=False,
        inject=None,
        anchor=None,
    )

    rc = cmd_tree(args)
    assert rc == 1


def test_check_reads_compressed_manifest_and_reports(tmp_path: Path) -> None:
    root = tmp_path
    # create current tree
    (root / "x.txt").write_text("1")

    # create previous manifest.gz with an old entry
    manifest_dir = root / ".rrt"
    manifest_dir.mkdir()
    prev = {"files": [{"path": "old.txt", "is_dir": False}]}
    gz_path = manifest_dir / "tree.manifest.json.gz"
    gz_path.write_bytes(gzip.compress(json.dumps(prev).encode("utf-8")))

    # previous snapshot that will be considered stale
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
    assert rc == 0


def test_inject_rendered_tree_success_dry_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "README.md"
    # create anchor markers
    target.write_text(
        "top\n<!-- rrt:auto:start:tree -->\nold\n<!-- rrt:auto:end:tree -->\nbottom\n"
    )
    p = DryRunPrinter(True)
    rc = _inject_rendered_tree(p, inject_file=str(target), anchor_id="tree", rendered="newcontent")
    assert rc == 0
    out = capsys.readouterr().out
    assert "newcontent" in out
