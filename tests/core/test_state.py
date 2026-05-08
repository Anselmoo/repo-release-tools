"""Tests for state.py — lockfile state management and TOML serialisation."""

from __future__ import annotations

from pathlib import Path

import pytest

from repo_release_tools.state import (
    _dict_to_toml,
    _toml_value,
    build_lock,
    docs_lock_path,
    hash_content,
    lock_is_current,
    now_utc,
    read_lock,
    rrt_dir,
    write_lock,
)


class TestRrtDir:
    """Test rrt_dir helper."""

    def test_rrt_dir_returns_dot_rrt(self, tmp_path: Path) -> None:
        """Should return <root>/.rrt path."""
        result = rrt_dir(tmp_path)
        assert result == tmp_path / ".rrt"


class TestDocsLockPath:
    """Test docs_lock_path helper."""

    def test_default_lock_file_name(self, tmp_path: Path) -> None:
        """Should return <root>/.rrt/docs.lock.toml by default."""
        result = docs_lock_path(tmp_path)
        assert result == tmp_path / ".rrt" / "docs.lock.toml"

    def test_absolute_lock_file_path(self, tmp_path: Path) -> None:
        """Should return absolute path as-is."""
        abs_path = tmp_path / "custom.lock.toml"
        result = docs_lock_path(tmp_path, str(abs_path))
        assert result == abs_path

    def test_rrt_prefixed_lock_file(self, tmp_path: Path) -> None:
        """Should prepend root when lock_file starts with .rrt/."""
        result = docs_lock_path(tmp_path, ".rrt/custom.toml")
        assert result == tmp_path / ".rrt" / "custom.toml"

    def test_bare_filename_uses_rrt_dir(self, tmp_path: Path) -> None:
        """Should place bare filename under .rrt/."""
        result = docs_lock_path(tmp_path, "my.lock.toml")
        assert result == tmp_path / ".rrt" / "my.lock.toml"


class TestHashContent:
    """Test hash_content helper."""

    def test_hash_content_starts_with_sha256(self) -> None:
        """Should return sha256: prefixed hash."""
        result = hash_content("hello")
        assert result.startswith("sha256:")

    def test_hash_content_deterministic(self) -> None:
        """Same input should produce same hash."""
        assert hash_content("test") == hash_content("test")

    def test_hash_content_different_inputs(self) -> None:
        """Different inputs should produce different hashes."""
        assert hash_content("a") != hash_content("b")


class TestNowUtc:
    """Test now_utc helper."""

    def test_now_utc_returns_string(self) -> None:
        """Should return an ISO-8601 string."""
        result = now_utc()
        assert isinstance(result, str)
        assert "T" in result
        assert "+00:00" in result


class TestTomlValue:
    """Test _toml_value serialiser."""

    def test_bool_true(self) -> None:
        assert _toml_value(True) == "true"

    def test_bool_false(self) -> None:
        assert _toml_value(False) == "false"

    def test_int(self) -> None:
        assert _toml_value(42) == "42"

    def test_float(self) -> None:
        result = _toml_value(3.14)
        assert "3.14" in result

    def test_str(self) -> None:
        assert _toml_value("hello") == '"hello"'

    def test_str_with_special_chars(self) -> None:
        result = _toml_value('he said "hi"\nbye')
        assert '\\"' in result
        assert "\\n" in result

    def test_list(self) -> None:
        result = _toml_value(["a", "b"])
        assert result == '["a", "b"]'

    def test_unsupported_type_raises(self) -> None:
        with pytest.raises(TypeError, match="Unsupported TOML value type"):
            _toml_value(object())  # type: ignore[arg-type]


class TestDictToToml:
    """Test _dict_to_toml serialiser."""

    def test_flat_dict(self) -> None:
        result = _dict_to_toml({"key": "value", "num": 1})
        assert 'key = "value"' in result
        assert "num = 1" in result

    def test_nested_dict(self) -> None:
        result = _dict_to_toml({"section": {"a": "1"}})
        assert "[section]" in result
        assert 'a = "1"' in result

    def test_mixed_scalars_and_section(self) -> None:
        """When top-level scalars precede a flat section, a blank line is inserted (line 165)."""
        result = _dict_to_toml({"top": "val", "section": {"a": "1"}})
        assert 'top = "val"' in result
        assert "[section]" in result
        assert "\n\n[section]" in result

    def test_nested_tables_with_slash_in_key(self) -> None:
        """Keys containing '/' should be quoted in headers."""
        result = _dict_to_toml({"sources": {"src/mod.py": {"hash": "abc"}}})
        assert '"src/mod.py"' in result
        assert 'hash = "abc"' in result

    def test_plain_nested_key(self) -> None:
        """Plain nested key (no slash/dot) should not be quoted."""
        result = _dict_to_toml({"sources": {"mymod": {"hash": "abc"}}})
        assert "[sources.mymod]" in result


class TestReadWriteLock:
    """Test read_lock and write_lock."""

    def test_read_lock_missing_file(self, tmp_path: Path) -> None:
        """Should return empty dict when file does not exist."""
        result = read_lock(tmp_path / "nonexistent.toml")
        assert result == {}

    def test_write_then_read_lock(self, tmp_path: Path) -> None:
        """Should round-trip data through write then read."""
        lock_path = tmp_path / ".rrt" / "docs.lock.toml"
        data = {"meta": {"generated_at": "2024-01-01T00:00:00+00:00", "rrt_version": "1.0.0"}}
        write_lock(lock_path, data)
        result = read_lock(lock_path)
        assert result["meta"]["rrt_version"] == "1.0.0"


class TestBuildLock:
    """Test build_lock."""

    def test_build_lock_structure(self) -> None:
        """Should produce correct lock structure."""
        sources = [{"source_file": "a.py", "hash": "sha256:abc", "lang": "python"}]
        result = build_lock(sources)
        assert "meta" in result
        assert "sources" in result
        assert "a.py" in result["sources"]
        assert result["sources"]["a.py"]["hash"] == "sha256:abc"


class TestLockIsCurrent:
    """Test lock_is_current."""

    def test_current_when_matches(self, tmp_path: Path) -> None:
        """Should return True when hashes match."""
        lock_path = tmp_path / "docs.lock.toml"
        sources = [{"source_file": "a.py", "hash": "sha256:abc", "lang": "python"}]
        lock_data = build_lock(sources)
        write_lock(lock_path, lock_data)
        ok, messages = lock_is_current(lock_path, sources)
        assert ok
        assert messages == []

    def test_stale_new_source(self, tmp_path: Path) -> None:
        """Should detect new source not in lockfile."""
        lock_path = tmp_path / "docs.lock.toml"
        old_sources = [{"source_file": "a.py", "hash": "sha256:abc", "lang": "python"}]
        write_lock(lock_path, build_lock(old_sources))
        new_sources = old_sources + [
            {"source_file": "b.py", "hash": "sha256:def", "lang": "python"}
        ]
        ok, messages = lock_is_current(lock_path, new_sources)
        assert not ok
        assert any("b.py" in m for m in messages)

    def test_stale_hash_mismatch(self, tmp_path: Path) -> None:
        """Should detect hash mismatch."""
        lock_path = tmp_path / "docs.lock.toml"
        sources = [{"source_file": "a.py", "hash": "sha256:abc", "lang": "python"}]
        write_lock(lock_path, build_lock(sources))
        changed = [{"source_file": "a.py", "hash": "sha256:xyz", "lang": "python"}]
        ok, messages = lock_is_current(lock_path, changed)
        assert not ok
        assert any("mismatch" in m for m in messages)

    def test_stale_removed_source(self, tmp_path: Path) -> None:
        """Should detect source removed from disk but still in lockfile."""
        lock_path = tmp_path / "docs.lock.toml"
        old_sources = [
            {"source_file": "a.py", "hash": "sha256:abc", "lang": "python"},
            {"source_file": "b.py", "hash": "sha256:def", "lang": "python"},
        ]
        write_lock(lock_path, build_lock(old_sources))
        # Only a.py remains
        ok, messages = lock_is_current(lock_path, [old_sources[0]])
        assert not ok
        assert any("b.py" in m for m in messages)
