"""Tests for the extras CLI commands (tree, progress, diff, panel, glyph-preview)."""

from __future__ import annotations

import argparse

from repo_release_tools.commands import extras


# ---------------------------------------------------------------------------
# cmd_tree
# ---------------------------------------------------------------------------


def test_cmd_tree_default_cwd(tmp_path, capsys) -> None:
    (tmp_path / "file.txt").write_text("hello")
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "nested.py").write_text("")
    args = argparse.Namespace(path=str(tmp_path), depth=3, all=False)

    rc = extras.cmd_tree(args)

    assert rc == 0
    captured = capsys.readouterr()
    assert "file.txt" in captured.out
    assert "subdir" in captured.out
    assert "nested.py" in captured.out


def test_cmd_tree_depth_limits_expansion(tmp_path, capsys) -> None:
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    (deep / "deep.txt").write_text("")
    args = argparse.Namespace(path=str(tmp_path), depth=1, all=False)

    rc = extras.cmd_tree(args)

    assert rc == 0
    captured = capsys.readouterr()
    # depth=1 expands one level of directories; deep.txt should not appear
    assert "a" in captured.out
    assert "deep.txt" not in captured.out


def test_cmd_tree_all_shows_hidden(tmp_path, capsys) -> None:
    (tmp_path / ".hidden").write_text("secret")
    (tmp_path / "visible.txt").write_text("hi")
    args = argparse.Namespace(path=str(tmp_path), depth=3, all=True)

    rc = extras.cmd_tree(args)

    assert rc == 0
    captured = capsys.readouterr()
    assert ".hidden" in captured.out
    assert "visible.txt" in captured.out


def test_cmd_tree_hides_dotfiles_by_default(tmp_path, capsys) -> None:
    (tmp_path / ".hidden").write_text("secret")
    (tmp_path / "visible.txt").write_text("hi")
    args = argparse.Namespace(path=str(tmp_path), depth=3, all=False)

    rc = extras.cmd_tree(args)

    assert rc == 0
    captured = capsys.readouterr()
    assert ".hidden" not in captured.out
    assert "visible.txt" in captured.out


def test_cmd_tree_missing_path_returns_1(capsys) -> None:
    args = argparse.Namespace(path="/nonexistent/path/xyz", depth=3, all=False)

    rc = extras.cmd_tree(args)

    assert rc == 1
    captured = capsys.readouterr()
    assert "not found" in captured.err.lower() or "not" in captured.err.lower()


def test_cmd_tree_file_path_returns_1(tmp_path, capsys) -> None:
    f = tmp_path / "not_a_dir.txt"
    f.write_text("hello")
    args = argparse.Namespace(path=str(f), depth=3, all=False)

    rc = extras.cmd_tree(args)

    assert rc == 1


# ---------------------------------------------------------------------------
# _walk_directory
# ---------------------------------------------------------------------------


def test_walk_directory_empty(tmp_path) -> None:
    result = extras._walk_directory(tmp_path)
    assert result == []


def test_walk_directory_sorts_dirs_before_files(tmp_path) -> None:
    (tmp_path / "zzz.txt").write_text("")
    (tmp_path / "aaa").mkdir()
    result = extras._walk_directory(tmp_path)
    names = [name for name, _, _ in result]
    assert names.index("aaa") < names.index("zzz.txt")


# ---------------------------------------------------------------------------
# cmd_progress
# ---------------------------------------------------------------------------


def test_cmd_progress_outputs_bar(capsys) -> None:
    args = argparse.Namespace(value="0.75", width=20)

    rc = extras.cmd_progress(args)

    assert rc == 0
    captured = capsys.readouterr()
    assert "75%" in captured.out


def test_cmd_progress_zero(capsys) -> None:
    args = argparse.Namespace(value="0", width=10)

    rc = extras.cmd_progress(args)

    assert rc == 0
    captured = capsys.readouterr()
    assert "0%" in captured.out


def test_cmd_progress_one(capsys) -> None:
    args = argparse.Namespace(value="1.0", width=10)

    rc = extras.cmd_progress(args)

    assert rc == 0
    captured = capsys.readouterr()
    assert "100%" in captured.out


def test_cmd_progress_invalid_value_returns_1(capsys) -> None:
    args = argparse.Namespace(value="not-a-number", width=20)

    rc = extras.cmd_progress(args)

    assert rc == 1
    captured = capsys.readouterr()
    assert "Invalid" in captured.err or "invalid" in captured.err


def test_cmd_progress_custom_width(capsys) -> None:
    args = argparse.Namespace(value="0.5", width=40)

    rc = extras.cmd_progress(args)

    assert rc == 0
    captured = capsys.readouterr()
    assert "50%" in captured.out


# ---------------------------------------------------------------------------
# _parse_diff_entries
# ---------------------------------------------------------------------------


SAMPLE_DIFF = """\
diff --git a/example.py b/example.py
--- a/example.py
+++ b/example.py
@@ -1,3 +1,4 @@
 unchanged line
+new line added
-old line removed
 another unchanged
"""


def test_parse_diff_entries_basic() -> None:
    lines = SAMPLE_DIFF.splitlines()
    entries = extras._parse_diff_entries(lines)
    kinds = [kind for kind, _, _ in entries]
    assert "added" in kinds
    assert "removed" in kinds


def test_parse_diff_entries_lineno_tracking() -> None:
    lines = SAMPLE_DIFF.splitlines()
    entries = extras._parse_diff_entries(lines)
    added = [(kind, lineno) for kind, _, lineno in entries if kind == "added"]
    assert any(lineno is not None for _, lineno in added)


def test_parse_diff_entries_empty() -> None:
    assert extras._parse_diff_entries([]) == []


# ---------------------------------------------------------------------------
# cmd_diff
# ---------------------------------------------------------------------------


def test_cmd_diff_no_changes(monkeypatch, capsys) -> None:
    monkeypatch.setattr(extras, "_git_diff_lines", lambda *_a, **_kw: [])
    args = argparse.Namespace(staged=False, against=None)

    rc = extras.cmd_diff(args)

    assert rc == 0
    captured = capsys.readouterr()
    assert "No changes" in captured.out


def test_cmd_diff_with_changes(monkeypatch, capsys) -> None:
    diff_output = SAMPLE_DIFF.splitlines()
    monkeypatch.setattr(extras, "_git_diff_lines", lambda *_a, **_kw: diff_output)
    args = argparse.Namespace(staged=False, against=None)

    rc = extras.cmd_diff(args)

    assert rc == 0
    captured = capsys.readouterr()
    assert "+" in captured.out or "new line added" in captured.out


def test_cmd_diff_staged_flag(monkeypatch, capsys) -> None:
    calls: list[dict] = []

    def fake_diff(root, *, staged, against):
        calls.append({"staged": staged, "against": against})
        return []

    monkeypatch.setattr(extras, "_git_diff_lines", fake_diff)
    args = argparse.Namespace(staged=True, against="main")

    extras.cmd_diff(args)

    assert calls[0]["staged"] is True
    assert calls[0]["against"] == "main"


# ---------------------------------------------------------------------------
# cmd_panel
# ---------------------------------------------------------------------------


def test_cmd_panel_renders_rows(capsys) -> None:
    args = argparse.Namespace(
        title="Release summary",
        style="single",
        pairs=["Version", "1.2.3", "Branch", "release/v1.2.3"],
    )

    rc = extras.cmd_panel(args)

    assert rc == 0
    captured = capsys.readouterr()
    assert "Release summary" in captured.out
    assert "Version" in captured.out
    assert "1.2.3" in captured.out
    assert "Branch" in captured.out


def test_cmd_panel_odd_pairs_returns_1(capsys) -> None:
    args = argparse.Namespace(title="T", style="single", pairs=["Key"])

    rc = extras.cmd_panel(args)

    assert rc == 1


def test_cmd_panel_all_styles(capsys) -> None:
    for style in ("single", "rounded", "bold", "mixed"):
        args = argparse.Namespace(
            title="Test",
            style=style,
            pairs=["Key", "Value"],
        )
        rc = extras.cmd_panel(args)
        assert rc == 0, f"cmd_panel failed for style={style!r}"


# ---------------------------------------------------------------------------
# cmd_glyph_preview
# ---------------------------------------------------------------------------


def test_cmd_glyph_preview_exits_zero(capsys) -> None:
    args = argparse.Namespace()

    rc = extras.cmd_glyph_preview(args)

    assert rc == 0


def test_cmd_glyph_preview_contains_all_sections(capsys) -> None:
    args = argparse.Namespace()
    extras.cmd_glyph_preview(args)
    captured = capsys.readouterr()

    assert "Box styles" in captured.out
    assert "Bullets" in captured.out
    assert "Progress" in captured.out
    assert "Tree" in captured.out
    assert "Diff" in captured.out
    assert "Git" in captured.out
    assert "Typography" in captured.out


def test_cmd_glyph_preview_contains_glyph_samples(capsys) -> None:
    args = argparse.Namespace()
    extras.cmd_glyph_preview(args)
    captured = capsys.readouterr()

    # At minimum the glyph names / style labels should appear
    assert "single" in captured.out
    assert "rounded" in captured.out
    assert "bold" in captured.out


# ---------------------------------------------------------------------------
# CLI registration smoke test
# ---------------------------------------------------------------------------


def test_register_adds_all_commands() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="cmd")
    extras.register(subparsers)

    choices = list(subparsers.choices.keys())
    assert "tree" in choices
    assert "progress" in choices
    assert "diff" in choices
    assert "panel" in choices
    assert "glyph-preview" in choices


def test_cli_help_includes_new_commands() -> None:
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "repo_release_tools", "--help"],
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0
    assert "tree" in result.stdout
    assert "progress" in result.stdout
    assert "diff" in result.stdout
    assert "panel" in result.stdout
    assert "glyph-preview" in result.stdout
