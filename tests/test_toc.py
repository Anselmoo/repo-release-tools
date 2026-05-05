"""Tests for rrt toc — tools/toc.py and commands/toc.py."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from repo_release_tools.tools.toc import heading_anchor, parse_headings, render_toc

# ---------------------------------------------------------------------------
# parse_headings — unit tests
# ---------------------------------------------------------------------------


def test_parse_headings_empty() -> None:
    assert parse_headings("") == []


def test_parse_headings_no_headings() -> None:
    assert parse_headings("Just some prose.\n\nAnother paragraph.\n") == []


def test_parse_headings_single() -> None:
    assert parse_headings("# Hello World\n") == [(1, "Hello World")]


def test_parse_headings_all_levels() -> None:
    text = "# H1\n## H2\n### H3\n#### H4\n##### H5\n###### H6\n"
    assert parse_headings(text) == [
        (1, "H1"),
        (2, "H2"),
        (3, "H3"),
        (4, "H4"),
        (5, "H5"),
        (6, "H6"),
    ]


def test_parse_headings_trailing_hashes_stripped() -> None:
    # ATX closed-form headings: "## Title ##"
    assert parse_headings("## Title ##\n") == [(2, "Title")]


def test_parse_headings_skips_fenced_code_backtick() -> None:
    text = "# Real\n```\n# Not a heading\n```\n## Also Real\n"
    assert parse_headings(text) == [(1, "Real"), (2, "Also Real")]


def test_parse_headings_skips_fenced_code_tilde() -> None:
    text = "# Real\n~~~\n# Not a heading\n~~~\n## Also Real\n"
    assert parse_headings(text) == [(1, "Real"), (2, "Also Real")]


def test_parse_headings_nested_fence_same_char() -> None:
    """Only the matching fence char closes a block."""
    text = (
        "```\n"
        "# Inside\n"
        "~~~\n"  # different char, does NOT close the ``` block
        "# Still inside\n"
        "```\n"  # closes the ``` block
        "# Outside\n"
    )
    assert parse_headings(text) == [(1, "Outside")]


def test_parse_headings_inline_code_not_fence() -> None:
    """Single-backtick inline code must not toggle fence state."""
    text = "# Title with `code`\n## Subtitle\n"
    assert parse_headings(text) == [(1, "Title with `code`"), (2, "Subtitle")]


def test_parse_headings_no_space_after_hash_is_not_heading() -> None:
    """ATX headings require at least one space after the #."""
    assert parse_headings("#NoSpace\n") == []


# ---------------------------------------------------------------------------
# heading_anchor — unit tests
# ---------------------------------------------------------------------------


def test_heading_anchor_simple() -> None:
    counts: dict[str, int] = {}
    assert heading_anchor("Hello World", counts) == "hello-world"


def test_heading_anchor_lowercases() -> None:
    counts: dict[str, int] = {}
    assert heading_anchor("My Module", counts) == "my-module"


def test_heading_anchor_strips_special_chars() -> None:
    counts: dict[str, int] = {}
    assert heading_anchor("C++ Overview", counts) == "c-overview"


def test_heading_anchor_keeps_digits() -> None:
    counts: dict[str, int] = {}
    assert heading_anchor("Python 3.12", counts) == "python-312"


def test_heading_anchor_deduplication() -> None:
    counts: dict[str, int] = {}
    first = heading_anchor("Setup", counts)
    second = heading_anchor("Setup", counts)
    third = heading_anchor("Setup", counts)
    assert first == "setup"
    assert second == "setup-1"
    assert third == "setup-2"


def test_heading_anchor_independent_counts() -> None:
    """Each unique slug has its own counter."""
    counts: dict[str, int] = {}
    assert heading_anchor("Alpha", counts) == "alpha"
    assert heading_anchor("Beta", counts) == "beta"
    assert heading_anchor("Alpha", counts) == "alpha-1"
    assert heading_anchor("Beta", counts) == "beta-1"


# ---------------------------------------------------------------------------
# render_toc — unit tests
# ---------------------------------------------------------------------------


def test_render_toc_empty_headings() -> None:
    assert render_toc([]) == ""


def test_render_toc_out_of_range() -> None:
    headings = [(1, "Top"), (2, "Sub")]
    result = render_toc(headings, min_level=3, max_level=6)
    assert result == ""


def test_render_toc_single_heading() -> None:
    headings = [(1, "Introduction")]
    assert render_toc(headings) == "- [Introduction](#introduction)"


def test_render_toc_nested() -> None:
    headings = [(1, "Top"), (2, "Sub"), (3, "Sub-sub")]
    result = render_toc(headings)
    lines = result.splitlines()
    assert lines[0] == "- [Top](#top)"
    assert lines[1] == "  - [Sub](#sub)"
    assert lines[2] == "    - [Sub-sub](#sub-sub)"


def test_render_toc_level_filter() -> None:
    headings = [(1, "H1"), (2, "H2"), (3, "H3")]
    result = render_toc(headings, min_level=2, max_level=3)
    lines = result.splitlines()
    assert len(lines) == 2
    assert lines[0] == "- [H2](#h2)"
    assert lines[1] == "  - [H3](#h3)"


def test_render_toc_max_level_filter() -> None:
    headings = [(1, "H1"), (2, "H2"), (3, "H3")]
    result = render_toc(headings, min_level=1, max_level=2)
    lines = result.splitlines()
    assert len(lines) == 2
    assert "H3" not in result


def test_render_toc_duplicate_anchors() -> None:
    headings = [(2, "Setup"), (2, "Setup")]
    result = render_toc(headings)
    assert "- [Setup](#setup)" in result
    assert "- [Setup](#setup-1)" in result


def test_render_toc_no_trailing_newline() -> None:
    headings = [(1, "Title")]
    result = render_toc(headings)
    assert not result.endswith("\n")


# ---------------------------------------------------------------------------
# cmd_toc (commands/toc.py) — integration via handler
# ---------------------------------------------------------------------------

from repo_release_tools.commands.toc import cmd_toc  # noqa: E402


def _make_args(
    file: str,
    inject: str | None = None,
    anchor: str | None = None,
    min_level: int = 1,
    max_level: int = 6,
    dry_run: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        file=file,
        inject=inject,
        anchor=anchor,
        min_level=min_level,
        max_level=max_level,
        dry_run=dry_run,
    )


def test_cmd_toc_stdout(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    md = tmp_path / "doc.md"
    md.write_text("# Title\n## Section\n", encoding="utf-8")
    rc = cmd_toc(_make_args(str(md)))
    assert rc == 0
    out = capsys.readouterr().out
    assert "- [Title](#title)" in out
    assert "  - [Section](#section)" in out


def test_cmd_toc_inject_and_anchor_must_be_together_inject_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    md = tmp_path / "doc.md"
    md.write_text("# Title\n", encoding="utf-8")
    rc = cmd_toc(_make_args(str(md), inject=str(md)))
    assert rc == 1
    err = capsys.readouterr().err
    assert "--inject and --anchor must be used together" in err


def test_cmd_toc_inject_and_anchor_must_be_together_anchor_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    md = tmp_path / "doc.md"
    md.write_text("# Title\n", encoding="utf-8")
    rc = cmd_toc(_make_args(str(md), anchor="toc"))
    assert rc == 1
    err = capsys.readouterr().err
    assert "--inject and --anchor must be used together" in err


def test_cmd_toc_source_missing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = cmd_toc(_make_args(str(tmp_path / "missing.md")))
    assert rc == 1
    err = capsys.readouterr().err
    assert "does not exist" in err


def test_cmd_toc_no_headings_in_range(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    md = tmp_path / "doc.md"
    md.write_text("# Title\n", encoding="utf-8")
    rc = cmd_toc(_make_args(str(md), min_level=3, max_level=6))
    assert rc == 1
    err = capsys.readouterr().err
    assert "No headings found" in err


def test_cmd_toc_inject_target_missing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    src = tmp_path / "src.md"
    src.write_text("# Title\n", encoding="utf-8")
    rc = cmd_toc(_make_args(str(src), inject=str(tmp_path / "missing.md"), anchor="toc"))
    assert rc == 1
    err = capsys.readouterr().err
    assert "does not exist" in err


def test_cmd_toc_inject_missing_anchor(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    src = tmp_path / "src.md"
    src.write_text("# Title\n", encoding="utf-8")
    target = tmp_path / "target.md"
    target.write_text("No anchors here.\n", encoding="utf-8")
    rc = cmd_toc(_make_args(str(src), inject=str(target), anchor="toc"))
    assert rc == 1
    err = capsys.readouterr().err
    assert "missing anchor" in err


def test_cmd_toc_inject_success(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    src = tmp_path / "src.md"
    src.write_text("# Title\n## Section\n", encoding="utf-8")
    target = tmp_path / "target.md"
    target.write_text(
        "<!-- rrt:auto:start:toc -->\n<!-- rrt:auto:end:toc -->\n",
        encoding="utf-8",
    )
    rc = cmd_toc(_make_args(str(src), inject=str(target), anchor="toc"))
    assert rc == 0
    content = target.read_text(encoding="utf-8")
    assert "- [Title](#title)" in content
    assert "  - [Section](#section)" in content


def test_cmd_toc_inject_dry_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    src = tmp_path / "src.md"
    src.write_text("# Title\n", encoding="utf-8")
    original = "<!-- rrt:auto:start:toc -->\n<!-- rrt:auto:end:toc -->\n"
    target = tmp_path / "target.md"
    target.write_text(original, encoding="utf-8")
    rc = cmd_toc(_make_args(str(src), inject=str(target), anchor="toc", dry_run=True))
    assert rc == 0
    # File must NOT be modified in dry-run mode
    assert target.read_text(encoding="utf-8") == original
    out = capsys.readouterr().out
    assert "Title" in out or "dry-run" in out


# ---------------------------------------------------------------------------
# register() — smoke-test the subparser wiring
# ---------------------------------------------------------------------------

from repo_release_tools.commands.toc import register  # noqa: E402


def test_register_creates_toc_subcommand() -> None:
    root = argparse.ArgumentParser()
    sub = root.add_subparsers(dest="command")
    register(sub)
    args = root.parse_args(["toc", "myfile.md"])
    assert args.command == "toc"
    assert args.file == "myfile.md"
    assert args.min_level == 1
    assert args.max_level == 6
    assert args.dry_run is False
    assert args.inject is None
    assert args.anchor is None


def test_register_sets_handler() -> None:
    root = argparse.ArgumentParser()
    sub = root.add_subparsers(dest="command")
    register(sub)
    args = root.parse_args(["toc", "myfile.md"])
    assert args.handler is cmd_toc
