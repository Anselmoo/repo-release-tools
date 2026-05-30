from pathlib import Path

from repo_release_tools.state import (
    _short_hash,
    tree_lock_is_current,
    write_lock,
)


def test_short_hash_empty() -> None:
    assert _short_hash("") == "?"


def test_short_hash_with_prefix_and_plain() -> None:
    h = "sha256:" + "a" * 64
    assert _short_hash(h) == "a" * 8
    assert _short_hash("b" * 16) == "b" * 8


def test_tree_lock_missing_snapshot(tmp_path: Path) -> None:
    lock_path = tmp_path / "lock.toml"
    # Do not create the file — read_lock should return an empty dict
    ok, drift = tree_lock_is_current(lock_path, {"entry_count": 1, "tree_hash": "sha256:1"})
    assert not ok
    assert any("Tree snapshot not found in lockfile" in d for d in drift)


def test_tree_lock_counts_equal_suggestion(tmp_path: Path) -> None:
    lock_path = tmp_path / "lock.toml"
    write_lock(lock_path, {"snapshot": {"entry_count": 3, "tree_hash": "sha256:abc"}})
    ok, drift = tree_lock_is_current(lock_path, {"entry_count": 3, "tree_hash": "sha256:def"})
    assert not ok
    assert any("suggestion: run 'rrt tree --snapshot' to refresh" in d for d in drift)


def test_tree_lock_signed_delta_and_hashes_present(tmp_path: Path) -> None:
    lock_path = tmp_path / "lock.toml"
    write_lock(lock_path, {"snapshot": {"entry_count": 2, "tree_hash": "sha256:old"}})
    ok, drift = tree_lock_is_current(lock_path, {"entry_count": 5, "tree_hash": "sha256:new"})
    assert not ok
    msg = drift[0]
    # Delta should show +3 and both hashes should be present
    assert "+3" in msg or "Δ +3" in msg
    assert "snapshot hash" in msg and "current hash" in msg


def test_tree_lock_string_counts_delta(tmp_path: Path) -> None:
    lock_path = tmp_path / "lock.toml"
    write_lock(lock_path, {"snapshot": {"entry_count": "4", "tree_hash": "sha256:old"}})
    ok, drift = tree_lock_is_current(lock_path, {"entry_count": "6", "tree_hash": "sha256:new"})
    assert not ok
    assert any("Δ 2" in d or "Δ 2" in d for d in drift)
