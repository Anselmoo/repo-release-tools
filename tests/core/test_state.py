"""Tests for state.py — lockfile state management and TOML serialisation."""

from __future__ import annotations

from pathlib import Path

import pytest

from repo_release_tools.state import (
    _dict_to_toml,
    _toml_value,
    artifacts_lock_is_current,
    artifacts_lock_path,
    build_artifacts_lock,
    build_health_lock,
    build_lock,
    build_tree_lock,
    docs_lock_path,
    hash_content,
    hash_file,
    health_lock_is_current,
    health_lock_path,
    lock_is_current,
    now_utc,
    read_lock,
    rrt_dir,
    tree_lock_is_current,
    tree_lock_path,
    upsert_health_lock_checks,
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
            {"source_file": "b.py", "hash": "sha256:def", "lang": "python"},
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


class TestBuildHealthLock:
    """Test build_health_lock."""

    def test_structure(self) -> None:
        """Should produce meta and checks sections."""
        checks = [{"name": "pre_commit", "status": "ok", "message": "all good"}]
        result = build_health_lock(checks)
        assert "meta" in result
        assert "checks" in result
        assert "pre_commit" in result["checks"]

    def test_empty_checks(self) -> None:
        """Should handle empty check list gracefully."""
        result = build_health_lock([])
        assert result["checks"] == {}

    def test_status_stored(self) -> None:
        """Should preserve ok/obsolete/warning/error status values."""
        checks = [
            {"name": "a", "status": "ok"},
            {"name": "b", "status": "obsolete"},
            {"name": "c", "status": "warning"},
            {"name": "d", "status": "error"},
        ]
        result = build_health_lock(checks)
        assert result["checks"]["a"]["status"] == "ok"
        assert result["checks"]["b"]["status"] == "obsolete"
        assert result["checks"]["c"]["status"] == "warning"
        assert result["checks"]["d"]["status"] == "error"

    def test_message_preserved(self) -> None:
        """Should store the optional message field."""
        checks = [{"name": "x", "status": "ok", "message": "looks good"}]
        result = build_health_lock(checks)
        assert result["checks"]["x"]["message"] == "looks good"

    def test_missing_message_defaults_empty(self) -> None:
        """Should default message to empty string when absent."""
        checks = [{"name": "x", "status": "ok"}]
        result = build_health_lock(checks)
        assert result["checks"]["x"]["message"] == ""


class TestHealthLockIsCurrent:
    """Test health_lock_is_current."""

    def test_no_regression(self, tmp_path: Path) -> None:
        """Same status as snapshot → no regression."""
        lock_path = tmp_path / "health.lock.toml"
        checks = [{"name": "pre_commit", "status": "ok"}]
        write_lock(lock_path, build_health_lock(checks))
        ok, msgs = health_lock_is_current(lock_path, checks)
        assert ok
        assert msgs == []

    def test_regression_ok_to_error(self, tmp_path: Path) -> None:
        """ok → error is a regression."""
        lock_path = tmp_path / "health.lock.toml"
        old = [{"name": "pre_commit", "status": "ok"}]
        write_lock(lock_path, build_health_lock(old))
        current = [{"name": "pre_commit", "status": "error"}]
        ok, msgs = health_lock_is_current(lock_path, current)
        assert not ok
        assert any("pre_commit" in m for m in msgs)

    def test_regression_ok_to_warning(self, tmp_path: Path) -> None:
        """ok → warning is a regression."""
        lock_path = tmp_path / "health.lock.toml"
        write_lock(lock_path, build_health_lock([{"name": "x", "status": "ok"}]))
        ok, msgs = health_lock_is_current(lock_path, [{"name": "x", "status": "warning"}])
        assert not ok
        assert any("x" in m for m in msgs)

    def test_obsolete_is_not_regression_from_ok(self, tmp_path: Path) -> None:
        """ok → obsolete is not a regression."""
        lock_path = tmp_path / "health.lock.toml"
        write_lock(lock_path, build_health_lock([{"name": "x", "status": "ok"}]))
        ok, msgs = health_lock_is_current(lock_path, [{"name": "x", "status": "obsolete"}])
        assert ok
        assert msgs == []

    def test_obsolete_to_warning_is_regression(self, tmp_path: Path) -> None:
        """obsolete → warning is a regression."""
        lock_path = tmp_path / "health.lock.toml"
        write_lock(lock_path, build_health_lock([{"name": "x", "status": "obsolete"}]))
        ok, msgs = health_lock_is_current(lock_path, [{"name": "x", "status": "warning"}])
        assert not ok
        assert any("x" in m for m in msgs)

    def test_improvement_not_regression(self, tmp_path: Path) -> None:
        """warning → ok is an improvement, not a regression."""
        lock_path = tmp_path / "health.lock.toml"
        write_lock(lock_path, build_health_lock([{"name": "x", "status": "warning"}]))
        ok, msgs = health_lock_is_current(lock_path, [{"name": "x", "status": "ok"}])
        assert ok
        assert msgs == []

    def test_new_check_is_regression(self, tmp_path: Path) -> None:
        """A check not present in the snapshot is treated as a regression."""
        lock_path = tmp_path / "health.lock.toml"
        write_lock(lock_path, build_health_lock([{"name": "a", "status": "ok"}]))
        ok, msgs = health_lock_is_current(
            lock_path,
            [{"name": "a", "status": "ok"}, {"name": "b", "status": "error"}],
        )
        assert not ok
        assert any("b" in m for m in msgs)

    def test_missing_lock_file(self, tmp_path: Path) -> None:
        """Missing lockfile → all checks are 'new', treated as regressions."""
        lock_path = tmp_path / "health.lock.toml"
        ok, msgs = health_lock_is_current(lock_path, [{"name": "x", "status": "ok"}])
        assert not ok
        assert any("x" in m for m in msgs)


class TestUpsertHealthLockChecks:
    """Test upsert_health_lock_checks."""

    def test_creates_lock_when_missing(self, tmp_path: Path) -> None:
        """Should create .rrt/health.lock.toml when it does not exist."""
        lock_path = tmp_path / ".rrt" / "health.lock.toml"
        upsert_health_lock_checks(lock_path, [{"name": "x", "status": "ok"}])
        data = read_lock(lock_path)
        assert data["checks"]["x"]["status"] == "ok"

    def test_preserves_other_subsystem_checks(self, tmp_path: Path) -> None:
        """Should not clobber checks from other subsystems."""
        lock_path = tmp_path / ".rrt" / "health.lock.toml"
        upsert_health_lock_checks(lock_path, [{"name": "doctor.pre_commit", "status": "ok"}])
        upsert_health_lock_checks(lock_path, [{"name": "eol.python.host", "status": "warning"}])
        data = read_lock(lock_path)
        assert "doctor.pre_commit" in data["checks"]
        assert "eol.python.host" in data["checks"]

    def test_updates_existing_entry(self, tmp_path: Path) -> None:
        """Should overwrite the same check name on second call."""
        lock_path = tmp_path / ".rrt" / "health.lock.toml"
        upsert_health_lock_checks(lock_path, [{"name": "x", "status": "ok"}])
        upsert_health_lock_checks(lock_path, [{"name": "x", "status": "error"}])
        data = read_lock(lock_path)
        assert data["checks"]["x"]["status"] == "error"


class TestHealthLockPath:
    """Test health_lock_path helper."""

    def test_returns_health_lock_toml(self, tmp_path: Path) -> None:
        assert health_lock_path(tmp_path) == tmp_path / ".rrt" / "health.lock.toml"


class TestBuildTreeLock:
    """Test build_tree_lock."""

    def test_structure(self) -> None:
        """Should produce meta and snapshot sections."""
        meta = {"entry_count": 42, "tree_hash": "sha256:abc"}
        result = build_tree_lock(meta)
        assert "meta" in result
        assert "snapshot" in result
        assert result["snapshot"]["entry_count"] == 42

    def test_hash_stored(self) -> None:
        """Should store the tree_hash verbatim."""
        meta = {"entry_count": 10, "tree_hash": "sha256:xyz"}
        result = build_tree_lock(meta)
        assert result["snapshot"]["tree_hash"] == "sha256:xyz"

    def test_ignored_count_optional(self) -> None:
        """ignored_count is included when present."""
        meta = {"entry_count": 5, "tree_hash": "sha256:abc", "ignored_count": 3}
        result = build_tree_lock(meta)
        assert result["snapshot"]["ignored_count"] == 3

    def test_ignored_count_absent(self) -> None:
        """ignored_count is absent when not provided."""
        meta = {"entry_count": 5, "tree_hash": "sha256:abc"}
        result = build_tree_lock(meta)
        assert "ignored_count" not in result["snapshot"]


class TestTreeLockIsCurrent:
    """Test tree_lock_is_current."""

    def test_same_hash(self, tmp_path: Path) -> None:
        """Same hash as snapshot → no drift."""
        lock_path = tmp_path / "tree.lock.toml"
        meta = {"entry_count": 10, "tree_hash": "sha256:abc"}
        write_lock(lock_path, build_tree_lock(meta))
        ok, msgs = tree_lock_is_current(lock_path, meta)
        assert ok
        assert msgs == []

    def test_hash_changed(self, tmp_path: Path) -> None:
        """Different hash → drift detected."""
        lock_path = tmp_path / "tree.lock.toml"
        write_lock(lock_path, build_tree_lock({"entry_count": 10, "tree_hash": "sha256:old"}))
        ok, msgs = tree_lock_is_current(lock_path, {"entry_count": 12, "tree_hash": "sha256:new"})
        assert not ok
        assert any("changed" in m for m in msgs)

    def test_hash_changed_counts_equal_reports_bullets(self, tmp_path: Path) -> None:
        """When counts are equal but hashes differ, report bulleted hashes and suggestion."""
        lock_path = tmp_path / "tree.lock.toml"
        write_lock(lock_path, build_tree_lock({"entry_count": 10, "tree_hash": "sha256:oldhash"}))
        ok, msgs = tree_lock_is_current(
            lock_path, {"entry_count": 10, "tree_hash": "sha256:newhash"}
        )
        assert not ok
        assert len(msgs) == 1
        msg = msgs[0]
        assert msg.startswith("Tree structure changed since snapshot:")
        assert "  - entry count: was 10 → now 10" in msg
        assert "(Δ 0" in msg
        assert "  - snapshot hash: oldhash (sha256:oldhash)" in msg
        assert "  - current hash: newhash (sha256:newhash)" in msg
        assert "run 'rrt tree --snapshot' to refresh" in msg

    def test_hash_changed_counts_differ_reports_bullets(self, tmp_path: Path) -> None:
        """When counts differ, report was/now bullet and both hashes."""
        lock_path = tmp_path / "tree.lock.toml"
        write_lock(lock_path, build_tree_lock({"entry_count": 7, "tree_hash": "sha256:old2"}))
        ok, msgs = tree_lock_is_current(lock_path, {"entry_count": 9, "tree_hash": "sha256:new2"})
        assert not ok
        assert len(msgs) == 1
        msg = msgs[0]
        assert msg.startswith("Tree structure changed since snapshot:")
        assert "  - entry count: was 7 → now 9" in msg
        assert "Δ +2" in msg
        assert "  - snapshot hash: old2 (sha256:old2)" in msg
        assert "  - current hash: new2 (sha256:new2)" in msg

    def test_missing_lock_file(self, tmp_path: Path) -> None:
        """Missing lockfile → drift reported."""
        lock_path = tmp_path / "tree.lock.toml"
        ok, msgs = tree_lock_is_current(lock_path, {"entry_count": 5, "tree_hash": "sha256:x"})
        assert not ok
        assert any("snapshot" in m.lower() for m in msgs)


class TestTreeLockPath:
    """Test tree_lock_path helper."""

    def test_returns_tree_lock_toml(self, tmp_path: Path) -> None:
        assert tree_lock_path(tmp_path) == tmp_path / ".rrt" / "tree.lock.toml"


class TestArtifactsLockPath:
    """Test artifacts_lock_path helper."""

    def test_returns_artifacts_lock_toml(self, tmp_path: Path) -> None:
        assert artifacts_lock_path(tmp_path) == tmp_path / ".rrt" / "artifacts.lock.toml"


class TestHashFile:
    """Test hash_file helper."""

    def test_returns_sha256_prefix(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_bytes(b"hello")
        result = hash_file(f)
        assert result.startswith("sha256:")
        assert len(result) > 7

    def test_same_content_same_hash(self, tmp_path: Path) -> None:
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        a.write_bytes(b"same")
        b.write_bytes(b"same")
        assert hash_file(a) == hash_file(b)

    def test_different_content_different_hash(self, tmp_path: Path) -> None:
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        a.write_bytes(b"foo")
        b.write_bytes(b"bar")
        assert hash_file(a) != hash_file(b)


class TestBuildArtifactsLock:
    """Test build_artifacts_lock structure and glob expansion."""

    def test_structure(self, tmp_path: Path) -> None:
        (tmp_path / "a.svg").write_text("<svg/>", encoding="utf-8")
        targets = [{"path": "*.svg", "description": "SVG files"}]
        result = build_artifacts_lock(targets, tmp_path)
        assert "meta" in result
        assert "rrt_version" in result["meta"]
        assert "files" in result
        assert "a.svg" in result["files"]

    def test_hash_stored(self, tmp_path: Path) -> None:
        (tmp_path / "b.svg").write_text("<svg>x</svg>", encoding="utf-8")
        targets = [{"path": "*.svg", "description": ""}]
        result = build_artifacts_lock(targets, tmp_path)
        entry = result["files"]["b.svg"]
        assert entry["hash"].startswith("sha256:")
        assert entry["size"] > 0

    def test_empty_glob_no_files(self, tmp_path: Path) -> None:
        targets = [{"path": "*.png", "description": "PNGs"}]
        result = build_artifacts_lock(targets, tmp_path)
        assert result["files"] == {}

    def test_multiple_targets(self, tmp_path: Path) -> None:
        (tmp_path / "x.svg").write_text("<svg/>", encoding="utf-8")
        (tmp_path / "y.txt").write_text("text", encoding="utf-8")
        targets = [
            {"path": "*.svg", "description": "SVG"},
            {"path": "*.txt", "description": "TXT"},
        ]
        result = build_artifacts_lock(targets, tmp_path)
        assert "x.svg" in result["files"]
        assert "y.txt" in result["files"]


class TestArtifactsLockIsCurrent:
    """Test artifacts_lock_is_current drift detection."""

    def test_no_drift_when_hashes_match(self, tmp_path: Path) -> None:
        (tmp_path / "a.svg").write_text("<svg/>", encoding="utf-8")
        targets = [{"path": "*.svg", "description": ""}]
        lock_path = tmp_path / "artifacts.lock.toml"
        write_lock(lock_path, build_artifacts_lock(targets, tmp_path))
        ok, msgs = artifacts_lock_is_current(lock_path, targets, tmp_path)
        assert ok
        assert msgs == []

    def test_drift_on_content_change(self, tmp_path: Path) -> None:
        f = tmp_path / "a.svg"
        f.write_text("<svg/>", encoding="utf-8")
        targets = [{"path": "*.svg", "description": ""}]
        lock_path = tmp_path / "artifacts.lock.toml"
        write_lock(lock_path, build_artifacts_lock(targets, tmp_path))
        f.write_text("<svg>changed</svg>", encoding="utf-8")
        ok, msgs = artifacts_lock_is_current(lock_path, targets, tmp_path)
        assert not ok
        assert any("mismatch" in m.lower() for m in msgs)

    def test_drift_on_new_file_not_in_lock(self, tmp_path: Path) -> None:
        (tmp_path / "a.svg").write_text("<svg/>", encoding="utf-8")
        targets = [{"path": "*.svg", "description": ""}]
        lock_path = tmp_path / "artifacts.lock.toml"
        write_lock(lock_path, build_artifacts_lock(targets, tmp_path))
        (tmp_path / "b.svg").write_text("<svg>new</svg>", encoding="utf-8")
        ok, msgs = artifacts_lock_is_current(lock_path, targets, tmp_path)
        assert not ok
        assert any("b.svg" in m for m in msgs)

    def test_drift_on_file_in_lock_but_deleted(self, tmp_path: Path) -> None:
        f = tmp_path / "a.svg"
        f.write_text("<svg/>", encoding="utf-8")
        targets = [{"path": "*.svg", "description": ""}]
        lock_path = tmp_path / "artifacts.lock.toml"
        write_lock(lock_path, build_artifacts_lock(targets, tmp_path))
        f.unlink()
        ok, msgs = artifacts_lock_is_current(lock_path, targets, tmp_path)
        assert not ok
        assert any("missing" in m.lower() for m in msgs)

    def test_no_drift_empty_lock_empty_files(self, tmp_path: Path) -> None:
        targets = [{"path": "*.png", "description": ""}]
        lock_path = tmp_path / "artifacts.lock.toml"
        write_lock(lock_path, build_artifacts_lock(targets, tmp_path))
        ok, msgs = artifacts_lock_is_current(lock_path, targets, tmp_path)
        assert ok
        assert msgs == []

    def test_skips_directories_in_build(self, tmp_path: Path) -> None:
        (tmp_path / "subdir.svg").mkdir()
        (tmp_path / "real.svg").write_text("<svg/>", encoding="utf-8")
        targets = [{"path": "*.svg", "description": ""}]
        result = build_artifacts_lock(targets, tmp_path)
        assert "real.svg" in result["files"]
        assert "subdir.svg" not in result["files"]

    def test_skips_directories_in_is_current(self, tmp_path: Path) -> None:
        (tmp_path / "real.svg").write_text("<svg/>", encoding="utf-8")
        targets = [{"path": "*.svg", "description": ""}]
        lock_path = tmp_path / "artifacts.lock.toml"
        write_lock(lock_path, build_artifacts_lock(targets, tmp_path))
        (tmp_path / "dir.svg").mkdir()
        ok, msgs = artifacts_lock_is_current(lock_path, targets, tmp_path)
        assert ok


class TestComputeInputsHash:
    """Tests for _compute_inputs_hash helper."""

    def test_returns_none_for_empty_globs(self, tmp_path: Path) -> None:
        from repo_release_tools.state import _compute_inputs_hash

        assert _compute_inputs_hash([], tmp_path) is None

    def test_returns_none_when_no_files_match(self, tmp_path: Path) -> None:
        from repo_release_tools.state import _compute_inputs_hash

        assert _compute_inputs_hash(["*.nonexistent"], tmp_path) is None

    def test_returns_sha256_prefixed_string(self, tmp_path: Path) -> None:
        from repo_release_tools.state import _compute_inputs_hash

        (tmp_path / "gen.py").write_text("print('hello')")
        result = _compute_inputs_hash(["*.py"], tmp_path)
        assert result is not None
        assert result.startswith("sha256:")

    def test_deterministic_across_calls(self, tmp_path: Path) -> None:
        from repo_release_tools.state import _compute_inputs_hash

        (tmp_path / "gen.py").write_text("x = 1")
        r1 = _compute_inputs_hash(["*.py"], tmp_path)
        r2 = _compute_inputs_hash(["*.py"], tmp_path)
        assert r1 == r2

    def test_changes_when_input_content_changes(self, tmp_path: Path) -> None:
        from repo_release_tools.state import _compute_inputs_hash

        f = tmp_path / "gen.py"
        f.write_text("x = 1")
        h1 = _compute_inputs_hash(["*.py"], tmp_path)
        f.write_text("x = 2")
        h2 = _compute_inputs_hash(["*.py"], tmp_path)
        assert h1 != h2

    def test_different_file_splits_with_same_concat_produce_different_hashes(
        self, tmp_path: Path
    ) -> None:
        from repo_release_tools.state import _compute_inputs_hash

        # File boundary regression: ["ab","c"] vs ["a","bc"] concatenate to the
        # same byte string "abc" — the hash must differ because paths are included.
        (tmp_path / "ab").write_text("ab")
        (tmp_path / "c").write_text("c")
        h1 = _compute_inputs_hash(["ab", "c"], tmp_path)

        (tmp_path / "ab").unlink()
        (tmp_path / "c").unlink()
        (tmp_path / "a").write_text("a")
        (tmp_path / "bc").write_text("bc")
        h2 = _compute_inputs_hash(["a", "bc"], tmp_path)

        assert h1 != h2


class TestBuildArtifactsLockWithInputs:
    """Tests for build_artifacts_lock with inputs field."""

    def test_targets_section_absent_when_no_inputs(self, tmp_path: Path) -> None:
        (tmp_path / "out.svg").write_bytes(b"<svg/>")
        targets = [{"path": "*.svg", "description": "", "command": [], "inputs": []}]
        result = build_artifacts_lock(targets, tmp_path)
        assert "targets" not in result

    def test_targets_section_present_when_inputs_configured(self, tmp_path: Path) -> None:
        (tmp_path / "out.svg").write_bytes(b"<svg/>")
        (tmp_path / "gen.py").write_text("# generator")
        targets = [{"path": "*.svg", "description": "", "command": [], "inputs": ["*.py"]}]
        result = build_artifacts_lock(targets, tmp_path)
        assert "targets" in result
        assert "*.svg" in result["targets"]
        assert result["targets"]["*.svg"]["inputs_hash"].startswith("sha256:")

    def test_targets_section_omitted_when_no_input_files_match(self, tmp_path: Path) -> None:
        (tmp_path / "out.svg").write_bytes(b"<svg/>")
        targets = [{"path": "*.svg", "description": "", "command": [], "inputs": ["*.nonexistent"]}]
        result = build_artifacts_lock(targets, tmp_path)
        # No matching input files → no inputs_hash stored
        assert "targets" not in result or "*.svg" not in result.get("targets", {})

    def test_bare_glob_key_round_trips_through_toml(self, tmp_path: Path) -> None:
        """Bare-glob paths like '*' must produce valid TOML (quoted keys)."""
        import tomllib

        (tmp_path / "out").write_bytes(b"data")
        (tmp_path / "gen.py").write_text("# generator")
        # '*' has no '.', '/', '"', or '\\', so was previously unquoted → invalid TOML
        targets = [{"path": "*", "description": "", "command": [], "inputs": ["*.py"]}]
        lock_path = tmp_path / ".rrt" / "artifacts.lock.toml"
        data = build_artifacts_lock(targets, tmp_path)
        write_lock(lock_path, data)
        parsed = tomllib.loads(lock_path.read_text())
        assert "*" in parsed.get("targets", {})


class TestArtifactsLockIsCurrentWithInputs:
    """Tests for input-staleness detection in artifacts_lock_is_current."""

    def _make_lock_with_inputs(self, tmp_path: Path, inputs_hash: str) -> Path:
        lock = {
            "meta": {"generated_at": "2026-01-01T00:00:00+00:00", "rrt_version": "1.0.0"},
            "targets": {"*.svg": {"inputs_hash": inputs_hash}},
            "files": {},
        }
        lock_path = tmp_path / ".rrt" / "artifacts.lock.toml"
        write_lock(lock_path, lock)
        return lock_path

    def test_detects_changed_inputs(self, tmp_path: Path) -> None:
        (tmp_path / "gen.py").write_text("x = 1")
        lock_path = self._make_lock_with_inputs(tmp_path, "sha256:stale_hash")
        targets = [{"path": "*.svg", "description": "", "command": [], "inputs": ["*.py"]}]
        is_ok, msgs = artifacts_lock_is_current(lock_path, targets, tmp_path)
        assert not is_ok
        assert any("stale" in m.lower() or "input" in m.lower() for m in msgs)

    def test_passes_when_inputs_unchanged(self, tmp_path: Path) -> None:
        from repo_release_tools.state import _compute_inputs_hash

        (tmp_path / "gen.py").write_text("x = 1")
        current_hash = _compute_inputs_hash(["*.py"], tmp_path)
        assert current_hash is not None
        lock_path = self._make_lock_with_inputs(tmp_path, current_hash)
        targets = [{"path": "*.svg", "description": "", "command": [], "inputs": ["*.py"]}]
        is_ok, msgs = artifacts_lock_is_current(lock_path, targets, tmp_path)
        assert is_ok
        assert msgs == []

    def test_warns_when_inputs_configured_but_not_in_lock(self, tmp_path: Path) -> None:
        (tmp_path / "gen.py").write_text("x = 1")
        # Lock with no [targets] section
        lock = {
            "meta": {"generated_at": "2026-01-01T00:00:00+00:00", "rrt_version": "1.0.0"},
            "files": {},
        }
        lock_path = tmp_path / ".rrt" / "artifacts.lock.toml"
        write_lock(lock_path, lock)
        targets = [{"path": "*.svg", "description": "", "command": [], "inputs": ["*.py"]}]
        is_ok, msgs = artifacts_lock_is_current(lock_path, targets, tmp_path)
        assert not is_ok
        assert any("snapshot" in m.lower() or "input" in m.lower() for m in msgs)
