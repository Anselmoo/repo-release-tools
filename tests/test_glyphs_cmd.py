"""Tests for glyphs_cmd.py — tree, progress, diff, panel, glyph-preview."""

from __future__ import annotations

import argparse

from pathlib import Path
from unittest.mock import patch

import pytest

from repo_release_tools.commands.glyphs_cmd import (
    _build_tree,
    _parse_diff_line,
    _parse_key_value_pairs,
    _should_skip,
    cmd_diff,
    cmd_glyph_preview,
    cmd_panel,
    cmd_progress,
    cmd_tree,
)
from repo_release_tools.cli import build_parser


# ---------------------------------------------------------------------------
# _should_skip
# ---------------------------------------------------------------------------


def test_should_skip_git_dir() -> None:
    assert _should_skip(".git") is True


def test_should_skip_pycache() -> None:
    assert _should_skip("__pycache__") is True


def test_should_skip_egg_info() -> None:
    assert _should_skip("my_package.egg-info") is True


def test_should_not_skip_src() -> None:
    assert _should_skip("src") is False


def test_should_not_skip_readme() -> None:
    assert _should_skip("README.md") is False


# ---------------------------------------------------------------------------
# _build_tree
# ---------------------------------------------------------------------------


def test_build_tree_basic(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("# a")
    (tmp_path / "b.py").write_text("# b")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.py").write_text("# c")

    entries = _build_tree(tmp_path, max_depth=3, show_hidden=False)
    names = [e[0] for e in entries]
    assert "sub" in names
    assert "a.py" in names

    sub_entries = next(e[2] for e in entries if e[0] == "sub")
    assert sub_entries is not None
    assert any(e[0] == "c.py" for e in sub_entries)


def test_build_tree_respects_depth(tmp_path: Path) -> None:
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    (deep / "file.txt").write_text("x")

    entries = _build_tree(tmp_path, max_depth=1, show_hidden=False)
    a_entry = next((e for e in entries if e[0] == "a"), None)
    assert a_entry is not None
    # at depth 1 sub-children of `a` should be present but `c` should be None/missing
    b_entry_children = a_entry[2]
    assert b_entry_children is not None
    b_entry = next((e for e in b_entry_children if e[0] == "b"), None)
    # b exists but its children were cut at depth 1 — children will be None
    assert b_entry is not None
    assert b_entry[2] is None


def test_build_tree_hides_dotfiles_by_default(tmp_path: Path) -> None:
    (tmp_path / ".hidden").write_text("h")
    (tmp_path / "visible.py").write_text("v")
    entries = _build_tree(tmp_path, max_depth=1, show_hidden=False)
    names = [e[0] for e in entries]
    assert ".hidden" not in names
    assert "visible.py" in names


def test_build_tree_shows_dotfiles_when_flagged(tmp_path: Path) -> None:
    (tmp_path / ".hidden").write_text("h")
    entries = _build_tree(tmp_path, max_depth=1, show_hidden=True)
    names = [e[0] for e in entries]
    assert ".hidden" in names


# ---------------------------------------------------------------------------
# cmd_tree
# ---------------------------------------------------------------------------


def _ns(**kwargs: object) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


def test_cmd_tree_renders(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "foo.py").write_text("x")
    rc = cmd_tree(_ns(path=str(tmp_path), depth=4, all=False))
    assert rc == 0
    out = capsys.readouterr().out
    assert "foo.py" in out


def test_cmd_tree_missing_path(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cmd_tree(_ns(path="/no/such/path/xyz", depth=4, all=False))
    assert rc == 1


def test_cmd_tree_empty_dir(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = cmd_tree(_ns(path=str(tmp_path), depth=4, all=False))
    assert rc == 0
    out = capsys.readouterr().out
    assert "empty" in out.lower()


# ---------------------------------------------------------------------------
# cmd_progress
# ---------------------------------------------------------------------------


def test_cmd_progress_zero(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cmd_progress(_ns(value="0.0", width=10))
    assert rc == 0
    out = capsys.readouterr().out
    assert "0%" in out


def test_cmd_progress_full(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cmd_progress(_ns(value="1.0", width=10))
    assert rc == 0
    out = capsys.readouterr().out
    assert "100%" in out


def test_cmd_progress_half(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cmd_progress(_ns(value="0.5", width=10))
    assert rc == 0
    out = capsys.readouterr().out
    assert "50%" in out


def test_cmd_progress_invalid_value(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cmd_progress(_ns(value="banana", width=20))
    assert rc == 1


def test_cmd_progress_out_of_range(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cmd_progress(_ns(value="1.5", width=20))
    assert rc == 1


# ---------------------------------------------------------------------------
# _parse_diff_line
# ---------------------------------------------------------------------------


def test_parse_diff_line_added() -> None:
    kind, text, lineno = _parse_diff_line("+new line")
    assert kind == "added"
    assert text == "new line"
    assert lineno is None


def test_parse_diff_line_removed() -> None:
    kind, text, lineno = _parse_diff_line("-old line")
    assert kind == "removed"
    assert text == "old line"


def test_parse_diff_line_context() -> None:
    kind, text, lineno = _parse_diff_line(" context line")
    assert kind == "unchanged"
    assert text == "context line"


def test_parse_diff_line_hunk_header() -> None:
    kind, text, lineno = _parse_diff_line("@@ -1,3 +10,5 @@ def foo():")
    assert lineno == 10


def test_parse_diff_line_triple_plus_header() -> None:
    kind, text, lineno = _parse_diff_line("+++ b/src/foo.py")
    assert kind == "unchanged"


# ---------------------------------------------------------------------------
# cmd_diff
# ---------------------------------------------------------------------------


def test_cmd_diff_not_a_git_repo(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with (
        patch("repo_release_tools.commands.glyphs_cmd.git.is_git_repository", return_value=False),
        patch("repo_release_tools.commands.glyphs_cmd.Path.cwd", return_value=tmp_path),
    ):
        rc = cmd_diff(_ns(staged=False, against=None))
    assert rc == 1


def test_cmd_diff_empty_diff(capsys: pytest.CaptureFixture[str]) -> None:
    with (
        patch("repo_release_tools.commands.glyphs_cmd.git.is_git_repository", return_value=True),
        patch("repo_release_tools.commands.glyphs_cmd.git.capture", return_value=""),
    ):
        rc = cmd_diff(_ns(staged=False, against=None))
    assert rc == 0
    out = capsys.readouterr().out
    assert "No diff" in out


def test_cmd_diff_renders_changes(capsys: pytest.CaptureFixture[str]) -> None:
    fake_diff = (
        "diff --git a/foo.py b/foo.py\n"
        "--- a/foo.py\n"
        "+++ b/foo.py\n"
        "@@ -1,2 +1,3 @@ class Foo:\n"
        " context\n"
        "+added line\n"
        "-removed line\n"
    )
    with (
        patch("repo_release_tools.commands.glyphs_cmd.git.is_git_repository", return_value=True),
        patch("repo_release_tools.commands.glyphs_cmd.git.capture", return_value=fake_diff),
    ):
        rc = cmd_diff(_ns(staged=False, against=None))
    assert rc == 0
    out = capsys.readouterr().out
    assert "foo.py" in out
    assert "added line" in out
    assert "removed line" in out


# ---------------------------------------------------------------------------
# _parse_key_value_pairs
# ---------------------------------------------------------------------------


def test_parse_key_value_pairs_even() -> None:
    result = _parse_key_value_pairs(["Key", "Val", "Key2", "Val2"])
    assert result == [("Key", "Val"), ("Key2", "Val2")]


def test_parse_key_value_pairs_empty() -> None:
    assert _parse_key_value_pairs([]) == []


def test_parse_key_value_pairs_odd_raises() -> None:
    with pytest.raises(ValueError, match="even"):
        _parse_key_value_pairs(["Key"])


# ---------------------------------------------------------------------------
# cmd_panel
# ---------------------------------------------------------------------------


def test_cmd_panel_single(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cmd_panel(_ns(title="Test", style="single", pairs=["Key", "Value"]))
    assert rc == 0
    out = capsys.readouterr().out
    assert "Test" in out
    assert "Key" in out
    assert "Value" in out


def test_cmd_panel_rounded(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cmd_panel(_ns(title="R", style="rounded", pairs=["A", "B"]))
    assert rc == 0
    out = capsys.readouterr().out
    # rounded corners
    assert "╭" in out or "A" in out


def test_cmd_panel_bold(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cmd_panel(_ns(title="B", style="bold", pairs=["X", "Y"]))
    assert rc == 0
    out = capsys.readouterr().out
    assert "┏" in out or "X" in out


def test_cmd_panel_mixed(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cmd_panel(_ns(title="M", style="mixed", pairs=["K", "V"]))
    assert rc == 0


def test_cmd_panel_odd_pairs(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cmd_panel(_ns(title="T", style="single", pairs=["OnlyKey"]))
    assert rc == 1


def test_cmd_panel_no_rows(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cmd_panel(_ns(title="T", style="single", pairs=[]))
    assert rc == 0
    out = capsys.readouterr().out
    assert "No rows" in out


# ---------------------------------------------------------------------------
# cmd_glyph_preview
# ---------------------------------------------------------------------------


def test_cmd_glyph_preview_runs(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cmd_glyph_preview(argparse.Namespace())
    assert rc == 0
    out = capsys.readouterr().out
    assert "Box styles" in out
    assert "Bullets" in out
    assert "Progress" in out
    assert "Tree" in out
    assert "Diff" in out
    assert "Git" in out
    assert "Terminal" in out


# ---------------------------------------------------------------------------
# CLI registration smoke tests
# ---------------------------------------------------------------------------


def test_cli_has_tree_command() -> None:
    parser = build_parser()
    try:
        parser.parse_args(["tree", "--help"])
    except SystemExit as exc:
        assert exc.code == 0


@pytest.mark.parametrize("cmd", ["tree", "progress", "diff", "panel", "glyph-preview"])
def test_register_registers_all_commands(cmd: str) -> None:
    """All five commands appear as valid subcommands."""
    parser = build_parser()
    # parse --help to confirm the subcommand exists without executing it
    try:
        parser.parse_args([cmd, "--help"])
    except SystemExit as exc:
        assert exc.code == 0
