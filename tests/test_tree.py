from __future__ import annotations

import argparse
import sys
import types
from pathlib import Path
from types import SimpleNamespace

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


# ---------------------------------------------------------------------------
# _resolve_git_root coverage
# ---------------------------------------------------------------------------


def test_resolve_git_root_returns_path_on_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Cover lines 181-182: success path when git returns a repo root."""
    expected = tmp_path

    def fake_run(cmd: list[str], **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=0, stdout=str(expected) + "\n")

    monkeypatch.setattr(tree.subprocess, "run", fake_run)

    result = tree._resolve_git_root(tmp_path)
    assert result == expected


def test_resolve_git_root_returns_none_on_empty_stdout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Cover line 182 branch: raw is empty string after strip."""

    def fake_run(cmd: list[str], **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=0, stdout="   ")

    monkeypatch.setattr(tree.subprocess, "run", fake_run)

    result = tree._resolve_git_root(tmp_path)
    assert result is None


# ---------------------------------------------------------------------------
# _is_ignored_by_git coverage
# ---------------------------------------------------------------------------


def test_is_ignored_by_git_returns_true_when_git_ignores(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Cover lines 187-194: git check-ignore exits 0 means ignored."""

    def fake_run(cmd: list[str], **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(tree.subprocess, "run", fake_run)

    assert tree._is_ignored_by_git("ignored.txt", repo_root=tmp_path) is True


def test_is_ignored_by_git_returns_false_when_not_ignored(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Cover lines 187-194: git check-ignore exits non-zero means not ignored."""

    def fake_run(cmd: list[str], **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=1, stdout="", stderr="")

    monkeypatch.setattr(tree.subprocess, "run", fake_run)

    assert tree._is_ignored_by_git("kept.txt", repo_root=tmp_path) is False


# ---------------------------------------------------------------------------
# _render_rich_tree coverage (mocked rich)
# ---------------------------------------------------------------------------


def _make_fake_rich_modules() -> tuple[types.ModuleType, types.ModuleType]:
    """Return fake rich.console and rich.tree modules."""

    class _FakeCapture:
        def __enter__(self) -> "_FakeCapture":
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def get(self) -> str:
            return "fake rich output"

    class _FakeConsole:
        def __init__(self, **kwargs: object) -> None:
            pass

        def capture(self) -> _FakeCapture:
            return _FakeCapture()

        def print(self, *args: object) -> None:  # noqa: A003
            pass

    class _FakeNode:
        def add(self, label: str) -> "_FakeNode":
            return _FakeNode()

    class _FakeTree(_FakeNode):
        def __init__(self, label: str) -> None:
            pass

    fake_console_mod = types.ModuleType("rich.console")
    setattr(fake_console_mod, "Console", _FakeConsole)

    fake_tree_mod = types.ModuleType("rich.tree")
    setattr(fake_tree_mod, "Tree", _FakeTree)

    return fake_console_mod, fake_tree_mod


def test_render_rich_tree_returns_string_when_rich_mocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cover lines 252-275: full rich rendering path."""
    fake_console_mod, fake_tree_mod = _make_fake_rich_modules()

    monkeypatch.setattr(tree, "IS_LEGACY_TERMINAL", False)
    monkeypatch.setitem(sys.modules, "rich.console", fake_console_mod)
    monkeypatch.setitem(sys.modules, "rich.tree", fake_tree_mod)

    entries: list[tree.TreeEntry] = [
        ("file.txt", False, None),
        ("src", True, [("mod.py", False, None)]),
    ]
    result = tree._render_rich_tree(entries)
    assert isinstance(result, str)


def test_render_rich_tree_returns_none_when_import_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cover lines 255-256: ImportError in rich import falls back to None."""
    monkeypatch.setattr(tree, "IS_LEGACY_TERMINAL", False)
    # Remove rich from sys.modules to force ImportError
    monkeypatch.delitem(sys.modules, "rich.console", raising=False)
    monkeypatch.delitem(sys.modules, "rich.tree", raising=False)

    import importlib as _importlib

    original_import = _importlib.import_module

    def failing_import(name: str, package: str | None = None) -> object:
        if name in {"rich.console", "rich.tree"}:
            raise ImportError(f"No module named {name!r}")
        return original_import(name, package)

    monkeypatch.setattr(tree.importlib, "import_module", failing_import)

    result = tree._render_rich_tree([("x.txt", False, None)])
    assert result is None


def test_render_rich_tree_returns_none_when_console_attr_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cover lines 260-261: getattr returns None when Console attribute is absent."""
    fake_console_mod = types.ModuleType("rich.console")
    # deliberately do NOT set .Console
    fake_tree_mod = types.ModuleType("rich.tree")

    monkeypatch.setattr(tree, "IS_LEGACY_TERMINAL", False)
    monkeypatch.setitem(sys.modules, "rich.console", fake_console_mod)
    monkeypatch.setitem(sys.modules, "rich.tree", fake_tree_mod)

    result = tree._render_rich_tree([("x.txt", False, None)])
    assert result is None


# ---------------------------------------------------------------------------
# cmd_tree: error paths for root validation
# ---------------------------------------------------------------------------


def test_cmd_tree_nonexistent_root_returns_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Cover lines 379-380: root path does not exist."""
    rc = tree.cmd_tree(_args(root=str(tmp_path / "no_such_dir")))
    assert rc == 1


def test_cmd_tree_file_root_returns_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Cover lines 382-383: root path is a file, not a directory."""
    f = tmp_path / "file.txt"
    f.write_text("content", encoding="utf-8")
    rc = tree.cmd_tree(_args(root=str(f)))
    assert rc == 1


# ---------------------------------------------------------------------------
# cmd_tree: rich format success path
# ---------------------------------------------------------------------------


def test_cmd_tree_rich_renders_successfully(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Cover line 413: rich rendering returns actual output (not None)."""
    _make_fixture_tree(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tree, "_render_rich_tree", lambda _entries: "rich rendered output")

    rc = tree.cmd_tree(_args(format="rich"))

    out = capsys.readouterr().out
    assert rc == 0
    assert "rich rendered output" in out


# ---------------------------------------------------------------------------
# cmd_tree: empty tree
# ---------------------------------------------------------------------------


def test_cmd_tree_empty_directory_shows_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Cover line 461: empty tree prints (empty) action."""
    monkeypatch.chdir(tmp_path)

    rc = tree.cmd_tree(_args())

    out = capsys.readouterr().out
    assert rc == 0
    assert "(empty)" in out


# ---------------------------------------------------------------------------
# cmd_tree: unreadable subdir triggers warning
# ---------------------------------------------------------------------------


def test_cmd_tree_reports_warnings_for_unreadable_dirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Cover lines 465, 467: warnings are printed and followed by blank line."""
    _make_fixture_tree(tmp_path)
    monkeypatch.chdir(tmp_path)

    orig_build = tree._build_entries

    def patched_build(
        path: Path,
        *,
        root: Path,
        repo_root: Path | None,
        depth: int,
        max_depth: int | None,
        dirs_only: bool,
        show_hidden: bool,
        ignore_cache: dict[str, bool],
        warnings: list[str],
    ) -> list[tree.TreeEntry]:
        result = orig_build(
            path,
            root=root,
            repo_root=repo_root,
            depth=depth,
            max_depth=max_depth,
            dirs_only=dirs_only,
            show_hidden=show_hidden,
            ignore_cache=ignore_cache,
            warnings=warnings,
        )
        warnings.append("Cannot read /secret: Permission denied")
        return result

    monkeypatch.setattr(tree, "_build_entries", patched_build)

    rc = tree.cmd_tree(_args())

    out = capsys.readouterr().out
    assert rc == 0
    assert "Cannot read /secret" in out


# ---------------------------------------------------------------------------
# _build_entries: OSError and relative_to edge cases
# ---------------------------------------------------------------------------


def test_build_entries_handles_oserror_on_sorted_children(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cover lines 305-307: OSError when listing a subdir's children."""
    subdir = tmp_path / "subdir"
    subdir.mkdir()

    call_count: list[int] = [0]

    original_sorted = tree._sorted_children

    def patched_sorted(path: Path) -> list[Path]:
        call_count[0] += 1
        if path == subdir:
            raise OSError("Permission denied")
        return original_sorted(path)

    monkeypatch.setattr(tree, "_sorted_children", patched_sorted)

    warnings: list[str] = []
    entries = tree._build_entries(
        tmp_path,
        root=tmp_path,
        repo_root=None,
        depth=1,
        max_depth=None,
        dirs_only=False,
        show_hidden=False,
        ignore_cache={},
        warnings=warnings,
    )

    assert isinstance(entries, list)
    assert any("subdir" in w or "Permission denied" in w for w in warnings)


def test_build_entries_relative_to_root_valueerror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cover lines 319-320: relative_to(root) raises ValueError falls back gracefully."""
    subdir = tmp_path / "sub"
    subdir.mkdir()
    f = subdir / "file.txt"
    f.write_text("x", encoding="utf-8")

    # Use a different path as root so relative_to raises ValueError
    other_root = tmp_path / "other"
    other_root.mkdir()

    warnings: list[str] = []
    # root != actual path where items reside → relative_to(root) will raise ValueError
    # We use repo_root=None to avoid the git ignore path
    entries = tree._build_entries(
        subdir,
        root=other_root,  # root is other_root, child is under subdir
        repo_root=None,
        depth=1,
        max_depth=None,
        dirs_only=False,
        show_hidden=False,
        ignore_cache={},
        warnings=warnings,
    )

    # Should still list entries (no crash)
    assert isinstance(entries, list)


def test_build_entries_relative_to_repo_valueerror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cover lines 326-327: relative_to(repo_root) raises ValueError falls back to relative_to_root."""
    subdir = tmp_path / "sub"
    subdir.mkdir()
    f = subdir / "file.txt"
    f.write_text("x", encoding="utf-8")

    # Make repo_root a completely different path so relative_to(repo_root) raises ValueError
    other_repo = tmp_path / "other_repo"
    other_repo.mkdir()

    # Also suppress git ignore checks
    monkeypatch.setattr(tree, "_is_ignored_by_git", lambda *a, **kw: False)

    warnings: list[str] = []
    result = tree._build_entries(
        subdir,
        root=subdir,
        repo_root=other_repo,  # child is NOT under other_repo → ValueError
        depth=1,
        max_depth=None,
        dirs_only=False,
        show_hidden=False,
        ignore_cache={},
        warnings=warnings,
    )

    assert isinstance(result, list)
