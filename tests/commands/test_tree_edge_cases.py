import argparse
import gzip
import json
import os
import tempfile
from pathlib import Path
from typing import Any, NoReturn

import pytest

from repo_release_tools.commands.tree import (
    _append_manifest_diff_summary,
    _build_entries,
    _compute_sha256,
    _flatten_entries_for_manifest,
    _write_tree_manifest,
    cmd_tree,
)
from repo_release_tools.state import build_tree_lock, tree_lock_path, write_lock
from repo_release_tools.ui import DryRunPrinter


def test_compute_sha256_returns_none_on_error(tmp_path: Path) -> None:
    # directories cannot be read as bytes -> hash_file will raise -> None
    assert _compute_sha256(tmp_path) is None


def test_flatten_entries_reports_missing_and_stat_errors(tmp_path: Path) -> None:
    root = tmp_path
    # do not create the file: lstat/stat will raise
    entries: list[Any] = [("missing.txt", False, None)]
    warnings: list[str] = []
    result = _flatten_entries_for_manifest(entries, root, hash_files=False, warnings=warnings)
    assert any("Cannot stat" in w for w in warnings)
    assert len(result) == 1
    assert result[0].path == "missing.txt"


def test_flatten_entries_readlink_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path
    target = root / "target"
    link = root / "link"
    # create a symlink (target need not exist)
    link.symlink_to(target)

    # force os.readlink to raise
    def fake_readlink(p: Path) -> str:
        raise OSError("boom")

    monkeypatch.setattr(os, "readlink", fake_readlink)

    entries: list[Any] = [("link", False, None)]
    warnings: list[str] = []
    _flatten_entries_for_manifest(entries, root, hash_files=False, warnings=warnings)
    assert any("Cannot readlink" in w for w in warnings)


def test_write_tree_manifest_dry_run_outputs_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path
    (root / "f.txt").write_text("x")
    entries: list[Any] = [("f.txt", False, None)]
    p = DryRunPrinter(True)
    warnings: list[str] = []

    _write_tree_manifest(entries, root, p, hash_files=False, warnings=warnings, compressed=True)
    out = capsys.readouterr().out
    assert "files" in out


def test_write_tree_manifest_compressed_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path
    (root / "f.txt").write_text("x")
    entries: list[Any] = [("f.txt", False, None)]
    p = DryRunPrinter(False)
    warnings: list[str] = []

    def raise_tmp(*args: Any, **kwargs: Any) -> NoReturn:
        raise OSError("no tmp")

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", raise_tmp)

    with pytest.raises(Exception):
        _write_tree_manifest(entries, root, p, hash_files=False, warnings=warnings, compressed=True)
    assert any("Failed to install compressed manifest" in w for w in warnings)


def test_write_tree_manifest_uncompressed_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path
    (root / "f.txt").write_text("x")
    entries: list[Any] = [("f.txt", False, None)]
    p = DryRunPrinter(False)
    warnings: list[str] = []

    def raise_tmp(*args: Any, **kwargs: Any) -> NoReturn:
        raise OSError("no tmp")

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", raise_tmp)

    with pytest.raises(Exception):
        _write_tree_manifest(
            entries, root, p, hash_files=False, warnings=warnings, compressed=False
        )
    assert any("Failed to install manifest" in w for w in warnings)


def test_cmd_tree_compressed_implies_manifest_and_returns(tmp_path: Path) -> None:
    root = tmp_path
    (root / "a.txt").write_text("hello")
    args = argparse.Namespace(
        root=str(root),
        format="classic",
        max_depth=None,
        dirs_only=False,
        show_hidden=False,
        snapshot=False,
        check=False,
        manifest=False,
        compressed=True,
        strict=False,
        dry_run=False,
        inject=None,
        anchor=None,
    )

    rc = cmd_tree(args)
    assert rc == 0
    assert (root / ".rrt" / "tree.manifest.json.gz").exists()


def test_cmd_tree_read_manifest_exceptions(tmp_path: Path) -> None:
    root = tmp_path
    (root / "x.txt").write_text("1")
    manifest_dir = root / ".rrt"
    manifest_dir.mkdir()
    # create a directory where a file is expected to cause read_text to fail
    (manifest_dir / "tree.manifest.json").mkdir()

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


def test_append_manifest_diff_summary_reports_added_and_removed(tmp_path: Path) -> None:
    """_append_manifest_diff_summary appends a summary when a prior manifest exists."""
    root = tmp_path
    (root / "new.txt").write_text("1", encoding="utf-8")
    manifest_dir = root / ".rrt"
    manifest_dir.mkdir()

    prev = {"files": [{"path": "old.txt", "is_dir": False}]}
    (manifest_dir / "tree.manifest.json").write_text(json.dumps(prev), encoding="utf-8")

    entries = _build_entries(
        root,
        root=root,
        repo_root=None,
        depth=1,
        max_depth=None,
        dirs_only=False,
        show_hidden=False,
        ignore_cache={},
        warnings=[],
    )

    drifted: list[str] = []
    warnings: list[str] = []
    _append_manifest_diff_summary(drifted, root, entries, warnings)

    assert len(drifted) == 1
    assert "Detailed manifest diff" in drifted[0]
    assert "added (1)" in drifted[0]
    assert "new.txt" in drifted[0]
    assert "removed (1)" in drifted[0]
    assert "old.txt" in drifted[0]
    assert warnings == []


def test_append_manifest_diff_summary_no_prior_manifest_is_noop(tmp_path: Path) -> None:
    """_append_manifest_diff_summary is a no-op when no prior manifest file exists."""
    drifted: list[str] = []
    warnings: list[str] = []

    _append_manifest_diff_summary(drifted, tmp_path, [], warnings)

    assert drifted == []
    assert warnings == []


def test_manifest_diff_truncation(tmp_path: Path) -> None:
    root = tmp_path
    # current tree has one file
    (root / "cur.txt").write_text("1")
    manifest_dir = root / ".rrt"
    manifest_dir.mkdir()

    # previous manifest contains many files so 'removed' will be > N
    prev_files = [{"path": f"old{i}.txt", "is_dir": False} for i in range(15)]
    prev = {"files": prev_files}
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


def test_manifest_gz_read_failure_appends_warning(tmp_path: Path) -> None:
    root = tmp_path
    (root / "x.txt").write_text("1")
    manifest_dir = root / ".rrt"
    manifest_dir.mkdir()
    # write invalid (non-gzip) content so gzip.open will raise
    gz_path = manifest_dir / "tree.manifest.json.gz"
    gz_path.write_text("not a gz file", encoding="utf-8")

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


def test_manifest_diff_added_truncation(tmp_path: Path) -> None:
    root = tmp_path
    # create many current files so 'added' will be > N
    for i in range(15):
        (root / f"new{i}.txt").write_text("x")
    manifest_dir = root / ".rrt"
    manifest_dir.mkdir()

    # previous manifest is empty
    prev = {"files": []}
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
