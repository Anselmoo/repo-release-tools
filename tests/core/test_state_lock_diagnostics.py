from pathlib import Path
from typing import Any

from repo_release_tools.state import (
    _short_hash,
    build_tree_lock,
    tree_lock_is_current,
    tree_lock_path,
    write_lock,
)


def test_short_hash_variants() -> None:
    assert _short_hash("sha256:abcdef0123456789") == "abcdef01"
    assert _short_hash("") == "?"
    val: Any = None
    assert _short_hash(val) == "?"


def test_tree_lock_missing_snapshot_reports(tmp_path: Path) -> None:
    root = tmp_path
    lock = tree_lock_path(root)
    # write an empty snapshot (no tree_hash)
    write_lock(lock, {"meta": {}, "snapshot": {}})

    current, drifted = tree_lock_is_current(lock, {"entry_count": 1, "tree_hash": "sha256:x"})
    assert not current
    assert any("Tree snapshot not found" in m for m in drifted)


def test_tree_lock_counts_equal_suggestion_and_numeric_delta(tmp_path: Path) -> None:
    root = tmp_path
    lock = tree_lock_path(root)
    # locked snapshot with entry_count=1 but different hash
    write_lock(lock, build_tree_lock({"entry_count": 1, "tree_hash": "sha256:old"}))

    # same counts but different hash -> suggestion branch
    current, drifted = tree_lock_is_current(lock, {"entry_count": 1, "tree_hash": "sha256:new"})
    assert not current
    assert any("suggestion: run 'rrt tree --snapshot'" in m for m in drifted)

    # numeric delta and glyph handling
    write_lock(lock, build_tree_lock({"entry_count": 1, "tree_hash": "sha256:old2"}))
    current2, drifted2 = tree_lock_is_current(lock, {"entry_count": 3, "tree_hash": "sha256:new2"})
    assert not current2
    # expect a +2 delta in the message
    assert any("+2" in m or "Δ +2" in m or "Δ +2" in m for m in drifted2)


def test_tree_lock_string_digit_delta(tmp_path: Path) -> None:
    root = tmp_path
    lock = tree_lock_path(root)
    # craft a lockfile where entry_count values are strings
    write_lock(lock, {"meta": {}, "snapshot": {"entry_count": "2", "tree_hash": "sha256:old"}})

    current, drifted = tree_lock_is_current(lock, {"entry_count": "5", "tree_hash": "sha256:new"})
    assert not current
    # delta should be coercible to 3
    assert any("Δ 3" in m or "Δ +3" in m or "+3" in m for m in drifted)
