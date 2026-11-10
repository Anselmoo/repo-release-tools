"""Tests for the architecture baseline helpers in ``state.py``."""

from __future__ import annotations

from pathlib import Path

from repo_release_tools.state import (
    ARCH_BASELINE_DEFAULT,
    ARCH_BASELINE_NAME,
    arch_baseline_compare,
    arch_baseline_diff,
    arch_baseline_path,
    arch_templates_dir,
    read_arch_baseline,
    write_arch_baseline,
)


def test_paths_and_names(tmp_path: Path) -> None:
    """The baseline and templates live under ``.rrt/``."""
    assert ARCH_BASELINE_NAME == "architecture.baseline.toml"
    assert ARCH_BASELINE_DEFAULT == ".rrt/architecture.baseline.toml"
    assert arch_baseline_path(tmp_path) == tmp_path / ".rrt" / "architecture.baseline.toml"
    assert arch_templates_dir(tmp_path) == tmp_path / ".rrt" / "templates"


def test_missing_baseline_reads_none_and_everything_is_new(tmp_path: Path) -> None:
    """Without a baseline every finding is new."""
    path = arch_baseline_path(tmp_path)
    assert read_arch_baseline(path) is None
    assert arch_baseline_diff(path, ["b", "a"]) == (["a", "b"], [])
    assert arch_baseline_compare(path, []) == (True, [])


def test_write_is_sorted_multiline_and_skips_unchanged(tmp_path: Path) -> None:
    """Entries are sorted, one per line, and an unchanged list is not rewritten."""
    path = arch_baseline_path(tmp_path)
    assert write_arch_baseline(path, ["b", "a", "a"]) is True
    text = path.read_text(encoding="utf-8")
    assert 'findings = [\n    "a",\n    "b",\n]' in text
    assert "rrt_version = " in text
    assert write_arch_baseline(path, ["a", "b"]) is False
    assert path.read_text(encoding="utf-8") == text
    assert read_arch_baseline(path) == ["a", "b"]


def test_write_empty_list(tmp_path: Path) -> None:
    """An empty baseline is still a baseline (it differs from none)."""
    path = arch_baseline_path(tmp_path)
    assert write_arch_baseline(path, []) is True
    assert "findings = []" in path.read_text(encoding="utf-8")
    assert read_arch_baseline(path) == []


def test_compare_reports_new_and_stale(tmp_path: Path) -> None:
    """``compare`` returns ``*_is_current``-shaped output."""
    path = arch_baseline_path(tmp_path)
    write_arch_baseline(path, ["a", "b"])
    assert arch_baseline_compare(path, ["a", "c"]) == (False, ["new: c", "stale: b"])
    assert arch_baseline_compare(path, ["b", "a"]) == (True, [])


def test_malformed_baseline_table_reads_empty(tmp_path: Path) -> None:
    """A non-table ``baseline`` key reads as an empty list."""
    path = arch_baseline_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text('baseline = "x"\n', encoding="utf-8")
    assert read_arch_baseline(path) == []
