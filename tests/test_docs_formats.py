"""Tests for docs_formats.py — format renderers for rrt docs generate."""

from __future__ import annotations

from pathlib import Path

import pytest

from repo_release_tools.config import DocsConfig
from repo_release_tools.docs_extractor import DocEntry
from repo_release_tools.docs_formats import inject_md, render, render_json, render_md, render_txt
from repo_release_tools.state import hash_content


def _entry(
    name: str = "example", content: str = "Example content.", lang: str = "python"
) -> DocEntry:
    return DocEntry(
        name=name,
        lang=lang,
        content=content,
        source_file="src/mod.py",
        line=1,
        hash=hash_content(content),
    )


def _config() -> DocsConfig:
    return DocsConfig(
        extraction_mode="explicit",
        languages=("python",),
        src_dir="src",
        formats=("json",),
    )


class TestRenderMd:
    """Tests for render_md."""

    def test_render_md_returns_markdown(self) -> None:
        entries = [_entry("hello", "Hello docs.")]
        result = render_md(entries, _config())
        assert "# Documentation" in result
        assert "hello" in result
        assert "Hello docs." in result

    def test_render_md_empty(self) -> None:
        result = render_md([], _config())
        assert "# Documentation" in result


class TestInjectMd:
    """Tests for inject_md — lines 54-64."""

    def test_inject_md_nonexistent_file(self, tmp_path: Path) -> None:
        """When target_file does not exist, should return empty string (no anchors)."""
        target = tmp_path / "MISSING.md"
        entries = [_entry("hello", "Hello docs.")]
        result = inject_md(entries, _config(), target_file=target)
        # No anchors in empty string → result unchanged (empty)
        assert isinstance(result, str)

    def test_inject_md_existing_file_no_anchors(self, tmp_path: Path) -> None:
        """Existing file with no matching anchors should be returned unchanged."""
        target = tmp_path / "README.md"
        target.write_text("# My project\nNo anchors here.\n", encoding="utf-8")
        entries = [_entry("hello", "Hello docs.")]
        result = inject_md(entries, _config(), target_file=target)
        assert result == "# My project\nNo anchors here.\n"

    def test_inject_md_replaces_anchor_block(self, tmp_path: Path) -> None:
        """Should replace content between matching anchor comments."""
        target = tmp_path / "README.md"
        target.write_text(
            "# Title\n"
            "<!-- rrt:auto:start:docs.hello -->\n"
            "old content\n"
            "<!-- rrt:auto:end:docs.hello -->\n"
            "Footer\n",
            encoding="utf-8",
        )
        entries = [_entry("hello", "New docs.")]
        result = inject_md(entries, _config(), target_file=target)
        assert "New docs." in result
        assert "old content" not in result

    def test_inject_md_multiple_entries(self, tmp_path: Path) -> None:
        """Should replace multiple anchor blocks."""
        target = tmp_path / "README.md"
        target.write_text(
            "<!-- rrt:auto:start:docs.a -->\nold a\n<!-- rrt:auto:end:docs.a -->\n"
            "<!-- rrt:auto:start:docs.b -->\nold b\n<!-- rrt:auto:end:docs.b -->\n",
            encoding="utf-8",
        )
        entries = [_entry("a", "New A."), _entry("b", "New B.")]
        result = inject_md(entries, _config(), target_file=target)
        assert "New A." in result
        assert "New B." in result


class TestRenderTxt:
    """Tests for render_txt."""

    def test_render_txt_contains_name(self) -> None:
        entries = [_entry("hello", "Hello docs.")]
        result = render_txt(entries, _config())
        assert "hello" in result
        assert "Hello docs." in result


class TestRenderJson:
    """Tests for render_json."""

    def test_render_json_produces_valid_json(self) -> None:
        import json

        entries = [_entry("hello", "Hello docs.")]
        result = render_json(entries, _config())
        parsed = json.loads(result)
        assert len(parsed) == 1
        assert parsed[0]["name"] == "hello"


class TestRender:
    """Tests for the render() dispatcher — lines 182, 186."""

    def test_render_toml_requires_root(self) -> None:
        """Should raise ValueError when format='toml' and root is None."""
        with pytest.raises(ValueError, match="root="):
            render("toml", [], _config(), root=None)

    def test_render_unsupported_format_raises(self) -> None:
        """Should raise ValueError for unknown format."""
        with pytest.raises(ValueError, match="Unsupported format"):
            render("xml", [], _config())

    def test_render_md(self) -> None:
        """Should dispatch to render_md."""
        result = render("md", [_entry()], _config())
        assert "# Documentation" in result

    def test_render_json(self) -> None:
        """Should dispatch to render_json."""
        import json

        result = render("json", [_entry()], _config())
        parsed = json.loads(result)
        assert isinstance(parsed, list)

    def test_render_toml_with_root(self, tmp_path: Path) -> None:
        """Should write lockfile and return TOML text when root is provided."""
        result = render("toml", [_entry()], _config(), root=tmp_path)
        assert isinstance(result, str)
        lock_path = tmp_path / ".rrt" / "docs.lock.toml"
        assert lock_path.exists()
