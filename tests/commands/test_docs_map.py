"""Unit tests for the per-directory purpose-doc generator core."""

from __future__ import annotations

from pathlib import Path

import pytest

from repo_release_tools.commands.docs_map import (
    MAP_ANCHOR_ID,
    TREE_ANCHOR_ID,
    MapResult,
    apply_to_file,
    build_full_block,
    build_prompts_section,
    build_purpose_section,
    build_tree_section,
    generate,
    iter_target_directories,
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
# iter_target_directories
# ---------------------------------------------------------------------------


def test_iter_target_directories_lists_source_bearing_dirs(tmp_path: Path) -> None:
    """Directories containing at least one source file are returned, sorted."""
    repo = _make_repo(
        tmp_path,
        {
            "src/a/mod_a.py": "x = 1\n",
            "src/b/mod_b.py": "y = 2\n",
            "src/c/notes.md": "# just markdown\n",  # no source file
        },
    )
    cfg = MapConfig(root="src")
    dirs = iter_target_directories(cfg, repo)
    rels = [d.relative_to(repo).as_posix() for d in dirs]
    assert rels == ["src/a", "src/b"]


def test_iter_target_directories_skips_ignored_names(tmp_path: Path) -> None:
    """__pycache__ and dotted directories are skipped."""
    repo = _make_repo(
        tmp_path,
        {
            "src/a/mod.py": "x = 1\n",
            "src/__pycache__/x.cpython-312.pyc": "binary",
            "src/.hidden/y.py": "z = 1\n",
        },
    )
    cfg = MapConfig(root="src")
    dirs = iter_target_directories(cfg, repo)
    rels = [d.relative_to(repo).as_posix() for d in dirs]
    assert rels == ["src/a"]


def test_iter_target_directories_respects_exclude(tmp_path: Path) -> None:
    """Directories matching exclude globs are filtered out."""
    repo = _make_repo(
        tmp_path,
        {
            "src/a/mod_a.py": "x = 1\n",
            "src/vendor/v.py": "v = 1\n",
        },
    )
    cfg = MapConfig(root="src", exclude=("src/vendor",))
    dirs = iter_target_directories(cfg, repo)
    rels = [d.relative_to(repo).as_posix() for d in dirs]
    assert rels == ["src/a"]


def test_iter_target_directories_respects_include(tmp_path: Path) -> None:
    """When include globs are set, only matching directories are returned."""
    repo = _make_repo(
        tmp_path,
        {
            "src/a/mod_a.py": "x = 1\n",
            "src/b/mod_b.py": "y = 1\n",
        },
    )
    cfg = MapConfig(root="src", include=("src/a",))
    dirs = iter_target_directories(cfg, repo)
    rels = [d.relative_to(repo).as_posix() for d in dirs]
    assert rels == ["src/a"]


def test_iter_target_directories_missing_root_returns_empty(tmp_path: Path) -> None:
    """A configured root that does not exist returns no directories."""
    cfg = MapConfig(root="does/not/exist")
    assert iter_target_directories(cfg, tmp_path) == []


# ---------------------------------------------------------------------------
# build_purpose_section
# ---------------------------------------------------------------------------


def test_build_purpose_section_uses_configured_text(tmp_path: Path) -> None:
    """The configured purpose text is rendered under the Purpose header."""
    repo = _make_repo(tmp_path, {"src/a/m.py": ""})
    cfg = MapConfig(root="src", purpose={"src/a": "Holds the A module."})
    section = build_purpose_section(repo / "src" / "a", cfg, repo)
    assert "## Purpose" in section
    assert "Holds the A module." in section


def test_build_purpose_section_falls_back_to_placeholder(tmp_path: Path) -> None:
    """When no purpose is configured, a placeholder noting the path is rendered."""
    repo = _make_repo(tmp_path, {"src/a/m.py": ""})
    cfg = MapConfig(root="src")
    section = build_purpose_section(repo / "src" / "a", cfg, repo)
    assert "No purpose configured" in section
    assert "`src/a`" in section


# ---------------------------------------------------------------------------
# build_tree_section
# ---------------------------------------------------------------------------


def test_build_tree_section_emits_anchored_block(tmp_path: Path) -> None:
    """The Tree section wraps an ASCII tree in its own inner anchor pair."""
    repo = _make_repo(tmp_path, {"src/a/m.py": "", "src/a/sub/n.py": ""})
    cfg = MapConfig(root="src", tree_max_depth=2)
    section = build_tree_section(repo / "src" / "a", cfg)
    assert f"<!-- rrt:auto:start:{TREE_ANCHOR_ID} -->" in section
    assert f"<!-- rrt:auto:end:{TREE_ANCHOR_ID} -->" in section
    assert "m.py" in section
    assert "sub/" in section


def test_build_tree_section_respects_max_depth_zero(tmp_path: Path) -> None:
    """tree_max_depth=0 emits an empty tree body (just the header)."""
    repo = _make_repo(tmp_path, {"src/a/m.py": ""})
    cfg = MapConfig(root="src", tree_max_depth=0)
    section = build_tree_section(repo / "src" / "a", cfg)
    assert "m.py" not in section
    assert "```text" in section


def test_render_directory_tree_swallows_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unreadable subdirectories should not crash the renderer."""
    repo = _make_repo(tmp_path, {"src/a/m.py": "", "src/a/sub/n.py": ""})
    original = Path.iterdir

    def _flaky(self: Path) -> object:
        if self.name == "sub":
            raise PermissionError("denied")
        return original(self)

    monkeypatch.setattr(Path, "iterdir", _flaky)
    cfg = MapConfig(root="src", tree_max_depth=3)
    section = build_tree_section(repo / "src" / "a", cfg)
    # The unreadable subdir is still listed at the parent level; its body is empty.
    assert "sub/" in section


# ---------------------------------------------------------------------------
# build_prompts_section
# ---------------------------------------------------------------------------


def test_build_prompts_section_empty_when_unconfigured() -> None:
    """No configured prompts means no prompt section at all."""
    assert build_prompts_section(MapConfig()) == ""


def test_build_prompts_section_includes_self_check() -> None:
    """self-check prompt is rendered when configured."""
    section = build_prompts_section(MapConfig(prompts=("self-check",)))
    assert "self-check" in section.lower()
    assert "auto-update" not in section.lower()


def test_build_prompts_section_includes_both() -> None:
    """Both prompts are rendered when both are configured, in order."""
    section = build_prompts_section(MapConfig(prompts=("self-check", "auto-update")))
    assert section.index("self-check") < section.index("Auto-update")


# ---------------------------------------------------------------------------
# build_full_block
# ---------------------------------------------------------------------------


def test_build_full_block_includes_all_sections(tmp_path: Path) -> None:
    """The full block contains Purpose, Tree, and Prompts when configured."""
    repo = _make_repo(tmp_path, {"src/a/m.py": ""})
    cfg = MapConfig(
        root="src",
        purpose={"src/a": "A purpose."},
        prompts=("self-check",),
    )
    block = build_full_block(repo / "src" / "a", cfg, repo)
    assert "## Purpose" in block
    assert "## Tree" in block
    assert "## LLM prompts" in block


def test_build_full_block_omits_prompts_when_not_configured(tmp_path: Path) -> None:
    """No prompts configured → no Prompts header in the block."""
    repo = _make_repo(tmp_path, {"src/a/m.py": ""})
    cfg = MapConfig(root="src")
    block = build_full_block(repo / "src" / "a", cfg, repo)
    assert "## LLM prompts" not in block


# ---------------------------------------------------------------------------
# apply_to_file
# ---------------------------------------------------------------------------


def test_apply_to_file_creates_when_missing(tmp_path: Path) -> None:
    """A missing file is created with the outer anchor pair and content."""
    target = tmp_path / "README.md"
    result = apply_to_file(target, "PURPOSE BODY\n", on_conflict="merge")
    assert result.status == "created"
    text = target.read_text(encoding="utf-8")
    assert f"<!-- rrt:auto:start:{MAP_ANCHOR_ID} -->" in text
    assert "PURPOSE BODY" in text


def test_apply_to_file_dry_run_creates_no_file(tmp_path: Path) -> None:
    """dry_run=True returns a 'created' result but never writes."""
    target = tmp_path / "README.md"
    result = apply_to_file(target, "X\n", on_conflict="merge", dry_run=True)
    assert result.status == "created"
    assert not target.exists()


def test_apply_to_file_updates_existing_anchor(tmp_path: Path) -> None:
    """Existing files with our anchor have their body replaced."""
    target = tmp_path / "README.md"
    target.write_text(
        "# Top prose\n"
        f"<!-- rrt:auto:start:{MAP_ANCHOR_ID} -->\nOLD\n<!-- rrt:auto:end:{MAP_ANCHOR_ID} -->\n"
        "# Bottom prose\n",
        encoding="utf-8",
    )
    result = apply_to_file(target, "NEW BODY\n", on_conflict="merge")
    assert result.status == "updated"
    text = target.read_text(encoding="utf-8")
    assert "NEW BODY" in text
    assert "# Top prose" in text
    assert "# Bottom prose" in text
    assert "OLD" not in text


def test_apply_to_file_inserts_anchor_into_existing_file(tmp_path: Path) -> None:
    """In merge mode, a file without our anchor gets the anchor appended."""
    target = tmp_path / "README.md"
    target.write_text("# Hand-curated\n", encoding="utf-8")
    result = apply_to_file(target, "PURPOSE\n", on_conflict="merge")
    assert result.status == "updated"
    text = target.read_text(encoding="utf-8")
    assert "# Hand-curated" in text
    assert "PURPOSE" in text


def test_apply_to_file_uptodate_when_block_unchanged(tmp_path: Path) -> None:
    """No-op when the desired content already matches what is on disk."""
    target = tmp_path / "README.md"
    apply_to_file(target, "BODY\n", on_conflict="merge")
    result = apply_to_file(target, "BODY\n", on_conflict="merge")
    assert result.status == "uptodate"


def test_apply_to_file_skip_does_not_touch_existing(tmp_path: Path) -> None:
    """skip mode leaves an existing file alone."""
    target = tmp_path / "README.md"
    original = "# Curated\n"
    target.write_text(original, encoding="utf-8")
    result = apply_to_file(target, "GENERATED\n", on_conflict="skip")
    assert result.status == "skipped"
    assert target.read_text(encoding="utf-8") == original


def test_apply_to_file_skip_creates_when_missing(tmp_path: Path) -> None:
    """skip mode still creates the file when it does not exist."""
    target = tmp_path / "README.md"
    result = apply_to_file(target, "BODY\n", on_conflict="skip")
    assert result.status == "created"
    assert target.exists()


def test_apply_to_file_error_raises_without_anchor(tmp_path: Path) -> None:
    """error mode refuses to touch a file that lacks the outer anchor."""
    target = tmp_path / "README.md"
    target.write_text("# Curated\n", encoding="utf-8")
    with pytest.raises(ValueError, match="exists without the"):
        apply_to_file(target, "X\n", on_conflict="error")


def test_apply_to_file_error_updates_when_anchor_present(tmp_path: Path) -> None:
    """error mode allows updates when the anchor is already in place."""
    target = tmp_path / "README.md"
    target.write_text(
        f"<!-- rrt:auto:start:{MAP_ANCHOR_ID} -->\nOLD\n<!-- rrt:auto:end:{MAP_ANCHOR_ID} -->\n",
        encoding="utf-8",
    )
    result = apply_to_file(target, "NEW\n", on_conflict="error")
    assert result.status == "updated"


# ---------------------------------------------------------------------------
# generate (end-to-end orchestrator)
# ---------------------------------------------------------------------------


def test_generate_returns_one_result_per_target_directory(tmp_path: Path) -> None:
    """One MapResult per discovered directory is returned."""
    repo = _make_repo(tmp_path, {"src/a/m.py": "", "src/b/m.py": ""})
    cfg = MapConfig(root="src")
    results = generate(cfg, repo)
    assert len(results) == 2
    assert all(isinstance(r, MapResult) for r in results)
    assert {r.directory.name for r in results} == {"a", "b"}


def test_generate_dry_run_writes_nothing(tmp_path: Path) -> None:
    """dry_run=True returns results without creating any files."""
    repo = _make_repo(tmp_path, {"src/a/m.py": ""})
    cfg = MapConfig(root="src")
    results = generate(cfg, repo, dry_run=True)
    assert results[0].status == "created"
    assert not (repo / "src" / "a" / "README.md").exists()


def test_generate_uses_configured_file_name(tmp_path: Path) -> None:
    """generate honors MapConfig.file_name when materializing the doc."""
    repo = _make_repo(tmp_path, {"src/a/m.py": ""})
    cfg = MapConfig(root="src", file_name="PURPOSE.md")
    results = generate(cfg, repo)
    assert results[0].file_path.name == "PURPOSE.md"
    assert (repo / "src" / "a" / "PURPOSE.md").exists()
