"""Unit tests for the docs_map lockfile + drift detection."""

from __future__ import annotations

from pathlib import Path

import pytest

from repo_release_tools.commands.docs_map_lock import (
    DriftItem,
    compute_block_hash,
    compute_desired_hashes,
    detect_drift,
    read_lockfile,
    refresh_lockfile,
    write_lockfile,
)
from repo_release_tools.config import MapConfig


def _make_repo(tmp_path: Path, layout: dict[str, str]) -> Path:
    """Build a synthetic project under tmp_path; return repo root."""
    for rel, contents in layout.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(contents, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# compute_block_hash
# ---------------------------------------------------------------------------


def test_compute_block_hash_format() -> None:
    """The hash is prefixed with sha256: and contains the hex digest."""
    h = compute_block_hash("hello\n")
    assert h.startswith("sha256:")
    assert len(h) == len("sha256:") + 64


def test_compute_block_hash_deterministic() -> None:
    """Identical input yields identical hashes."""
    assert compute_block_hash("body") == compute_block_hash("body")


def test_compute_block_hash_distinguishes_inputs() -> None:
    """Different inputs yield different hashes."""
    assert compute_block_hash("a") != compute_block_hash("b")


# ---------------------------------------------------------------------------
# read_lockfile / write_lockfile (round trip + error paths)
# ---------------------------------------------------------------------------


def test_read_lockfile_missing_returns_empty(tmp_path: Path) -> None:
    """A missing lockfile read returns an empty dict, not an error."""
    assert read_lockfile(tmp_path / "missing.lock.toml") == {}


def test_write_then_read_round_trip(tmp_path: Path) -> None:
    """write_lockfile + read_lockfile preserve directory→hash mappings."""
    entries = {"src/a": "sha256:aaa", "src/b": "sha256:bbb"}
    path = tmp_path / ".rrt" / "docs_map.lock.toml"
    write_lockfile(path, entries)
    assert read_lockfile(path) == entries


def test_write_lockfile_creates_parent_directory(tmp_path: Path) -> None:
    """write_lockfile creates intermediate directories as needed."""
    path = tmp_path / "deep" / "nested" / "lock.toml"
    write_lockfile(path, {})
    assert path.exists()


def test_read_lockfile_rejects_non_table_entries(tmp_path: Path) -> None:
    """A lockfile with `entries` as a non-table raises a clear ValueError."""
    path = tmp_path / "bad.lock.toml"
    path.write_text("entries = 42\n", encoding="utf-8")
    with pytest.raises(ValueError, match="'entries' must be a table"):
        read_lockfile(path)


def test_read_lockfile_rejects_non_table_entry(tmp_path: Path) -> None:
    """Each entry must itself be a table."""
    path = tmp_path / "bad.lock.toml"
    path.write_text('[entries]\n"src/a" = "wrong-shape"\n', encoding="utf-8")
    with pytest.raises(ValueError, match=r"'entries\.src/a' must be a table"):
        read_lockfile(path)


def test_read_lockfile_rejects_missing_hash(tmp_path: Path) -> None:
    """An entry without a non-empty `hash` is rejected."""
    path = tmp_path / "bad.lock.toml"
    path.write_text('[entries."src/a"]\nhash = ""\n', encoding="utf-8")
    with pytest.raises(ValueError, match="hash' must be a non-empty string"):
        read_lockfile(path)


# ---------------------------------------------------------------------------
# compute_desired_hashes
# ---------------------------------------------------------------------------


def test_compute_desired_hashes_emits_one_entry_per_directory(tmp_path: Path) -> None:
    """One hash entry is emitted per source-bearing directory."""
    repo = _make_repo(tmp_path, {"src/a/m.py": "", "src/b/m.py": ""})
    cfg = MapConfig(root="src")
    hashes = compute_desired_hashes(cfg, repo)
    assert set(hashes.keys()) == {"src/a", "src/b"}
    assert all(v.startswith("sha256:") for v in hashes.values())


# ---------------------------------------------------------------------------
# detect_drift
# ---------------------------------------------------------------------------


def test_detect_drift_no_drift_after_refresh(tmp_path: Path) -> None:
    """refresh_lockfile leaves zero drift on the next check."""
    repo = _make_repo(tmp_path, {"src/a/m.py": ""})
    cfg = MapConfig(root="src")
    refresh_lockfile(cfg, repo)
    assert detect_drift(cfg, repo) == []


def test_detect_drift_flags_missing_entries(tmp_path: Path) -> None:
    """Directories without any lockfile record are reported as missing-entry."""
    repo = _make_repo(tmp_path, {"src/a/m.py": ""})
    cfg = MapConfig(root="src")
    drift = detect_drift(cfg, repo)
    assert len(drift) == 1
    assert drift[0].kind == "missing-entry"
    assert drift[0].directory == "src/a"
    assert drift[0].actual_hash is None


def test_detect_drift_flags_stale_hashes(tmp_path: Path) -> None:
    """A hash mismatch is reported as stale, with both hashes attached."""
    repo = _make_repo(tmp_path, {"src/a/m.py": ""})
    cfg = MapConfig(root="src")
    write_lockfile(repo / cfg.lock_file, {"src/a": "sha256:wrong-on-purpose"})
    drift = detect_drift(cfg, repo)
    assert len(drift) == 1
    assert drift[0].kind == "stale"
    assert drift[0].actual_hash == "sha256:wrong-on-purpose"
    assert drift[0].expected_hash is not None
    assert drift[0].expected_hash.startswith("sha256:")


def test_detect_drift_flags_orphan_entries(tmp_path: Path) -> None:
    """A lockfile entry without a matching directory is reported as orphan-entry."""
    repo = _make_repo(tmp_path, {"src/a/m.py": ""})
    cfg = MapConfig(root="src")
    write_lockfile(
        repo / cfg.lock_file,
        {"src/a": next(iter(compute_desired_hashes(cfg, repo).values())), "src/old": "sha256:x"},
    )
    drift = detect_drift(cfg, repo)
    assert len(drift) == 1
    assert drift[0].kind == "orphan-entry"
    assert drift[0].directory == "src/old"
    assert drift[0].expected_hash is None


def test_detect_drift_sorts_results_by_kind_then_directory(tmp_path: Path) -> None:
    """Drift items are returned in a stable order: kind then directory."""
    repo = _make_repo(tmp_path, {"src/a/m.py": "", "src/b/m.py": ""})
    cfg = MapConfig(root="src")
    # Pre-write a lockfile with one orphan and one stale entry, plus one
    # directory entirely missing from the lockfile.
    write_lockfile(
        repo / cfg.lock_file,
        {"src/a": "sha256:wrong", "src/orphan": "sha256:dead"},
    )
    drift = detect_drift(cfg, repo)
    kinds = [d.kind for d in drift]
    assert kinds == sorted(kinds)


# ---------------------------------------------------------------------------
# refresh_lockfile
# ---------------------------------------------------------------------------


def test_refresh_lockfile_returns_written_path(tmp_path: Path) -> None:
    """The returned path points at the rendered lockfile."""
    repo = _make_repo(tmp_path, {"src/a/m.py": ""})
    cfg = MapConfig(root="src")
    written = refresh_lockfile(cfg, repo)
    assert written == repo / cfg.lock_file
    assert written.exists()


def test_drift_item_fields_round_trip() -> None:
    """DriftItem stores all four fields and exposes them by attribute."""
    item = DriftItem(kind="stale", directory="src/a", expected_hash="x", actual_hash="y")
    assert item.kind == "stale"
    assert item.directory == "src/a"
    assert item.expected_hash == "x"
    assert item.actual_hash == "y"
