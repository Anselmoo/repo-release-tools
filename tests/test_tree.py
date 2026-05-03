from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from repo_release_tools.commands import tree


def _args(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "format": "classic",
        "max_depth": None,
        "dirs_only": False,
        "show_hidden": False,
        "root": ".",
        "inject": None,
        "anchor": None,
        "dry_run": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _make_fixture_tree(tmp_path: Path) -> None:
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "module.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# test\n", encoding="utf-8")
    (tmp_path / ".hidden").write_text("secret\n", encoding="utf-8")


def test_cmd_tree_classic_renders_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _make_fixture_tree(tmp_path)
    monkeypatch.chdir(tmp_path)

    rc = tree.cmd_tree(_args(format="classic"))

    out = capsys.readouterr().out
    assert rc == 0
    assert "src/" in out
    assert "README.md" in out
    assert ".hidden" not in out


def test_cmd_tree_ascii_uses_ascii_connectors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _make_fixture_tree(tmp_path)
    monkeypatch.chdir(tmp_path)

    rc = tree.cmd_tree(_args(format="ascii"))

    out = capsys.readouterr().out
    assert rc == 0
    assert "|--" in out or "`--" in out


def test_cmd_tree_markdown_uses_bullets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _make_fixture_tree(tmp_path)
    monkeypatch.chdir(tmp_path)

    rc = tree.cmd_tree(_args(format="markdown"))

    out = capsys.readouterr().out
    assert rc == 0
    assert "- src/" in out
    assert "- README.md" in out


def test_render_rich_tree_returns_none_on_legacy_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tree, "IS_LEGACY_TERMINAL", True)
    result = tree._render_rich_tree([("file.txt", False, None)])
    assert result is None


def test_cmd_tree_rich_falls_back_when_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _make_fixture_tree(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tree, "_render_rich_tree", lambda entries: None)

    rc = tree.cmd_tree(_args(format="rich"))

    out = capsys.readouterr().out
    assert rc == 0
    assert "falling back to classic" in out


def test_cmd_tree_respects_max_depth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _make_fixture_tree(tmp_path)
    monkeypatch.chdir(tmp_path)

    rc = tree.cmd_tree(_args(max_depth=1))

    out = capsys.readouterr().out
    assert rc == 0
    assert "src/" in out
    assert "pkg/" not in out
    assert "module.py" not in out


def test_cmd_tree_show_hidden_includes_dotfiles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _make_fixture_tree(tmp_path)
    monkeypatch.chdir(tmp_path)

    rc = tree.cmd_tree(_args(show_hidden=True))

    out = capsys.readouterr().out
    assert rc == 0
    assert ".hidden" in out


def test_cmd_tree_dirs_only_hides_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _make_fixture_tree(tmp_path)
    monkeypatch.chdir(tmp_path)

    rc = tree.cmd_tree(_args(dirs_only=True))

    out = capsys.readouterr().out
    assert rc == 0
    assert "src/" in out
    assert "README.md" not in out


def test_cmd_tree_non_git_fallback_ignores_known_dirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "leftpad.js").write_text("x", encoding="utf-8")
    (tmp_path / "src").mkdir()
    monkeypatch.chdir(tmp_path)

    rc = tree.cmd_tree(_args())

    out = capsys.readouterr().out
    assert rc == 0
    assert "node_modules" not in out
    assert "src/" in out


def test_cmd_tree_gitignore_filtering_uses_git_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "keep.txt").write_text("keep", encoding="utf-8")
    (tmp_path / "ignored.txt").write_text("ignore", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tree, "_resolve_git_root", lambda cwd: tmp_path)
    monkeypatch.setattr(
        tree,
        "_is_ignored_by_git",
        lambda path_from_repo_root, repo_root: path_from_repo_root == "ignored.txt",
    )

    rc = tree.cmd_tree(_args())

    out = capsys.readouterr().out
    assert rc == 0
    assert "keep.txt" in out
    assert "ignored.txt" not in out


def test_register_adds_tree_subparser() -> None:
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest="command")
    tree.register(subs)

    parsed = parser.parse_args(["tree"])
    assert parsed.command == "tree"
    assert callable(parsed.handler)


# ---------------------------------------------------------------------------
# --inject / --anchor tests
# ---------------------------------------------------------------------------

_ANCHOR_TEMPLATE = """\
# My Docs

Some prose above.

<!-- rrt:auto:start:{anchor} -->
OLD CONTENT
<!-- rrt:auto:end:{anchor} -->

Some prose below.
"""


def _make_inject_file(tmp_path: Path, anchor: str = "project-tree") -> Path:
    target = tmp_path / "README.md"
    target.write_text(_ANCHOR_TEMPLATE.format(anchor=anchor), encoding="utf-8")
    return target


def test_inject_replaces_anchored_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _make_fixture_tree(tmp_path)
    target = _make_inject_file(tmp_path)
    monkeypatch.chdir(tmp_path)

    rc = tree.cmd_tree(_args(format="markdown", inject=str(target), anchor="project-tree"))

    assert rc == 0
    result = target.read_text(encoding="utf-8")
    assert "OLD CONTENT" not in result
    assert "- src/" in result
    assert "# My Docs" in result
    assert "Some prose above." in result
    assert "Some prose below." in result


def test_inject_dry_run_does_not_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _make_fixture_tree(tmp_path)
    target = _make_inject_file(tmp_path)
    original = target.read_text(encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    rc = tree.cmd_tree(
        _args(format="markdown", inject=str(target), anchor="project-tree", dry_run=True)
    )

    assert rc == 0
    assert target.read_text(encoding="utf-8") == original
    out = capsys.readouterr().out
    assert "dry-run" in out.lower()


def test_inject_missing_file_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _make_fixture_tree(tmp_path)
    monkeypatch.chdir(tmp_path)

    rc = tree.cmd_tree(
        _args(format="markdown", inject=str(tmp_path / "nonexistent.md"), anchor="project-tree")
    )

    assert rc == 1


def test_inject_missing_anchor_in_file_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _make_fixture_tree(tmp_path)
    target = _make_inject_file(tmp_path, anchor="project-tree")
    monkeypatch.chdir(tmp_path)

    rc = tree.cmd_tree(_args(format="markdown", inject=str(target), anchor="wrong-id"))

    assert rc == 1


def test_inject_without_anchor_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _make_fixture_tree(tmp_path)
    target = _make_inject_file(tmp_path)
    monkeypatch.chdir(tmp_path)

    rc = tree.cmd_tree(_args(inject=str(target), anchor=None))

    assert rc == 1


def test_anchor_without_inject_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _make_fixture_tree(tmp_path)
    monkeypatch.chdir(tmp_path)

    rc = tree.cmd_tree(_args(inject=None, anchor="project-tree"))

    assert rc == 1


def test_register_exposes_inject_and_anchor_flags() -> None:
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest="command")
    tree.register(subs)

    parsed = parser.parse_args(
        ["tree", "--format", "markdown", "--inject", "README.md", "--anchor", "my-tree"]
    )
    assert parsed.inject == "README.md"
    assert parsed.anchor == "my-tree"
