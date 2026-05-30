from pathlib import Path
from typing import cast

import pytest

from repo_release_tools import state as rstate


def test_short_hash_raises_returns_question() -> None:
    class Bad:
        def __bool__(self) -> bool:  # type: ignore[override]
            raise RuntimeError("boom")

    # _short_hash expects a str; cast to silence the type checker while
    # still exercising the exception path when __bool__ raises.
    assert rstate._short_hash(cast(str, Bad())) == "?"


def test_tree_lock_counts_equal_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    class BadEq:
        def __eq__(self, other: object) -> bool:  # pragma: no cover - triggers exception
            raise RuntimeError("eq-bad")

    def fake_read(lock_path: Path) -> dict:
        return {"snapshot": {"entry_count": BadEq(), "tree_hash": "sha256:old"}}

    monkeypatch.setattr(rstate, "read_lock", fake_read)

    current, drifted = rstate.tree_lock_is_current(
        Path("/nope"), {"entry_count": 1, "tree_hash": "sha256:new"}
    )
    assert not current
    assert any("Tree structure changed since snapshot" in m for m in drifted)


def test_tree_lock_delta_and_signed_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    class BadInt(int):
        def __sub__(self, other: object) -> int:  # pragma: no cover - force exception
            raise RuntimeError("sub-bad")

    def fake_read(lock_path: Path) -> dict:
        return {"snapshot": {"entry_count": 1, "tree_hash": "sha256:old"}}

    monkeypatch.setattr(rstate, "read_lock", fake_read)

    # new_count is a BadInt which will raise on subtraction
    current, drifted = rstate.tree_lock_is_current(
        Path("/nope"), {"entry_count": BadInt(3), "tree_hash": "sha256:new"}
    )
    assert not current
    # delta should have fallen back to '?'
    assert any("Δ ?" in m or "Δ ?" in m for m in drifted)


def test_tree_lock_glyph_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    # Make GLYPHS.arrow.up access raise to exercise the glyph except branch
    class BadArrow:
        @property
        def up(self) -> str:
            raise RuntimeError("glyph-bad")

        @property
        def down(self) -> str:
            raise RuntimeError("glyph-bad")

    class BadGlyphs:
        arrow = BadArrow()

    def fake_read(lock_path: Path) -> dict:
        return {"snapshot": {"entry_count": 1, "tree_hash": "sha256:old"}}

    monkeypatch.setattr(rstate, "read_lock", fake_read)
    monkeypatch.setattr(rstate, "GLYPHS", BadGlyphs())

    current, drifted = rstate.tree_lock_is_current(
        Path("/nope"), {"entry_count": 3, "tree_hash": "sha256:new"}
    )
    assert not current
    # glyph access failure should not break the diagnostic
    assert any("Tree structure changed since snapshot" in m for m in drifted)


def test_tree_lock_counts_equal_suggestion_appended(tmp_path: Path) -> None:
    # Write a snapshot where entry_count equals the current tree_meta but hashes differ
    lock_path = rstate.tree_lock_path(tmp_path)
    rstate.write_lock(
        lock_path, rstate.build_tree_lock({"entry_count": 5, "tree_hash": "sha256:old"})
    )

    current, drifted = rstate.tree_lock_is_current(
        lock_path, {"entry_count": 5, "tree_hash": "sha256:new"}
    )
    assert not current
    assert any("suggestion: run 'rrt tree --snapshot' to refresh" in m for m in drifted)


def test_tree_lock_negative_delta_uses_down_glyph(tmp_path: Path) -> None:
    # Create a snapshot with a larger entry_count than the current tree
    lock_path = rstate.tree_lock_path(tmp_path)
    rstate.write_lock(
        lock_path, rstate.build_tree_lock({"entry_count": 5, "tree_hash": "sha256:old"})
    )

    current, drifted = rstate.tree_lock_is_current(
        lock_path, {"entry_count": 3, "tree_hash": "sha256:new"}
    )
    assert not current
    # Expect the delta to be negative and the diagnostic to mention the delta
    assert any("Δ -" in m or "Δ -" in m for m in drifted)
