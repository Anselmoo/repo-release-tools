from __future__ import annotations

import argparse
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _make_fixture_tree(tmp_path)
    monkeypatch.chdir(tmp_path)

    rc = tree.cmd_tree(_args(format="ascii"))

    out = capsys.readouterr().out
    assert rc == 0
    assert "|--" in out or "`--" in out


def test_cmd_tree_markdown_uses_bullets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _make_fixture_tree(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tree, "_render_rich_tree", lambda entries: None)

    rc = tree.cmd_tree(_args(format="rich"))

    out = capsys.readouterr().out
    assert rc == 0
    assert "falling back to classic" in out


def test_cmd_tree_respects_max_depth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _make_fixture_tree(tmp_path)
    monkeypatch.chdir(tmp_path)

    rc = tree.cmd_tree(_args(show_hidden=True))

    out = capsys.readouterr().out
    assert rc == 0
    assert ".hidden" in out


def test_cmd_tree_dirs_only_hides_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _make_fixture_tree(tmp_path)
    monkeypatch.chdir(tmp_path)

    rc = tree.cmd_tree(_args(dirs_only=True))

    out = capsys.readouterr().out
    assert rc == 0
    assert "src/" in out
    assert "README.md" not in out


def test_cmd_tree_non_git_fallback_ignores_known_dirs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "keep.txt").write_text("keep", encoding="utf-8")
    (tmp_path / "ignored.txt").write_text("ignore", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tree, "_resolve_git_root", lambda cwd: tmp_path)
    monkeypatch.setattr(
        tree,
        "_batch_ignored_by_git",
        lambda paths_from_repo_root, repo_root: {
            p for p in paths_from_repo_root if p == "ignored.txt"
        },
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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _make_fixture_tree(tmp_path)
    target = _make_inject_file(tmp_path)
    original = target.read_text(encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    rc = tree.cmd_tree(
        _args(format="markdown", inject=str(target), anchor="project-tree", dry_run=True),
    )

    assert rc == 0
    assert target.read_text(encoding="utf-8") == original
    out = capsys.readouterr().out
    assert "dry-run" in out.lower()


def test_inject_missing_file_returns_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _make_fixture_tree(tmp_path)
    monkeypatch.chdir(tmp_path)

    rc = tree.cmd_tree(
        _args(format="markdown", inject=str(tmp_path / "nonexistent.md"), anchor="project-tree"),
    )

    assert rc == 1


def test_inject_missing_anchor_in_file_returns_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _make_fixture_tree(tmp_path)
    target = _make_inject_file(tmp_path, anchor="project-tree")
    monkeypatch.chdir(tmp_path)

    rc = tree.cmd_tree(_args(format="markdown", inject=str(target), anchor="wrong-id"))

    assert rc == 1


def test_inject_without_anchor_returns_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _make_fixture_tree(tmp_path)
    target = _make_inject_file(tmp_path)
    monkeypatch.chdir(tmp_path)

    rc = tree.cmd_tree(_args(inject=str(target), anchor=None))

    assert rc == 1


def test_anchor_without_inject_returns_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
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
        ["tree", "--format", "markdown", "--inject", "README.md", "--anchor", "my-tree"],
    )
    assert parsed.inject == "README.md"
    assert parsed.anchor == "my-tree"


# ---------------------------------------------------------------------------
# _resolve_git_root coverage
# ---------------------------------------------------------------------------


def test_resolve_git_root_returns_path_on_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Cover lines 181-182: success path when git returns a repo root."""
    expected = tmp_path

    def fake_run(cmd: list[str], **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=0, stdout=str(expected) + "\n")

    monkeypatch.setattr(tree.subprocess, "run", fake_run)

    result = tree._resolve_git_root(tmp_path)
    assert result == expected


def test_resolve_git_root_returns_none_on_empty_stdout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
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
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Cover lines 187-194: git check-ignore exits 0 means ignored."""

    def fake_run(cmd: list[str], **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(tree.subprocess, "run", fake_run)

    assert tree._is_ignored_by_git("ignored.txt", repo_root=tmp_path) is True


def test_is_ignored_by_git_returns_false_when_not_ignored(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Cover lines 187-194: git check-ignore exits non-zero means not ignored."""

    def fake_run(cmd: list[str], **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=1, stdout="", stderr="")

    monkeypatch.setattr(tree.subprocess, "run", fake_run)

    assert tree._is_ignored_by_git("kept.txt", repo_root=tmp_path) is False


# ---------------------------------------------------------------------------
# _render_rich_tree coverage (mocked rich)
# ---------------------------------------------------------------------------


def _make_fake_rich_modules() -> tuple[Any, Any]:
    """Return fake rich.console and rich.tree modules."""

    class _FakeCapture:
        def __enter__(self) -> _FakeCapture:
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def get(self) -> str:
            return "fake rich output"

    class _FakeConsole:
        def __init__(self, **kwargs: object) -> None:
            pass

        def render_lines(
            self,
            renderable: object,
            *,
            pad: bool = True,
            new_lines: bool = False,
        ) -> list[list[SimpleNamespace]]:
            lines: list[list[SimpleNamespace]] = []

            def walk(node: object) -> None:
                lines.append([SimpleNamespace(text=getattr(node, "label", ""))])
                for child in getattr(node, "children", []):
                    walk(child)

            walk(renderable)
            return lines

    class _FakeNode:
        def __init__(self, label: str) -> None:
            self.label = label
            self.children: list[_FakeNode] = []

        def add(self, label: str) -> _FakeNode:
            child = _FakeNode(label)
            self.children.append(child)
            return child

    class _FakeTree(_FakeNode):
        def __init__(self, label: str) -> None:
            self.label = label
            self.children: list[_FakeNode] = []

    fake_console_mod = cast(Any, types.ModuleType("rich.console"))
    fake_console_mod.Console = _FakeConsole

    fake_tree_mod = cast(Any, types.ModuleType("rich.tree"))
    fake_tree_mod.Tree = _FakeTree

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


def test_render_rich_tree_does_not_emit_root_dot(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: rich rendering should not include a synthetic '.' root node."""

    class _FakeCapture:
        def __init__(self, console: _FakeConsole) -> None:
            self._console = console

        def __enter__(self) -> _FakeCapture:
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def get(self) -> str:
            return "\n".join(self._console.lines)

    class _FakeConsole:
        def __init__(self, **kwargs: object) -> None:
            self.lines: list[str] = []

        def render_lines(
            self,
            renderable: object,
            *,
            pad: bool = True,
            new_lines: bool = False,
        ) -> list[list[SimpleNamespace]]:
            lines: list[list[SimpleNamespace]] = []

            def walk(node: object) -> None:
                lines.append([SimpleNamespace(text=getattr(node, "label", ""))])
                for child in getattr(node, "children", []):
                    walk(child)

            walk(renderable)
            return lines

    class _FakeNode:
        def __init__(self, label: str) -> None:
            self.label = label
            self.children: list[_FakeNode] = []

        def add(self, label: str) -> _FakeNode:
            child = _FakeNode(label)
            self.children.append(child)
            return child

    fake_console_mod = cast(Any, types.ModuleType("rich.console"))
    fake_console_mod.Console = _FakeConsole
    fake_tree_mod = cast(Any, types.ModuleType("rich.tree"))
    fake_tree_mod.Tree = _FakeNode

    monkeypatch.setattr(tree, "IS_LEGACY_TERMINAL", False)
    monkeypatch.setitem(sys.modules, "rich.console", fake_console_mod)
    monkeypatch.setitem(sys.modules, "rich.tree", fake_tree_mod)

    rendered = tree._render_rich_tree([("src", True, None), ("README.md", False, None)])
    assert rendered is not None
    assert "." not in rendered.splitlines()


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
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Cover lines 379-380: root path does not exist."""
    rc = tree.cmd_tree(_args(root=str(tmp_path / "no_such_dir")))
    assert rc == 1


def test_cmd_tree_file_root_returns_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
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


def test_cmd_tree_silent_on_gitkeep_only_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Directories preserved via .gitkeep are intentionally tracked — no warning."""
    (tmp_path / "src" / "mcp").mkdir(parents=True)
    (tmp_path / "src" / "mcp" / ".gitkeep").write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tree, "_resolve_git_root", lambda cwd: tmp_path)
    monkeypatch.setattr(
        tree, "_batch_ignored_by_git", lambda paths_from_repo_root, repo_root: set()
    )

    rc = tree.cmd_tree(_args())

    out = capsys.readouterr().out
    assert rc == 0
    assert "Empty directory detected: src/mcp/" not in out


def test_warn_for_empty_directories_skips_inline_gitkeep_only() -> None:
    """When .gitkeep is visible in children (e.g. --show-hidden), skip silently."""
    entries: list[tree.TreeEntry] = [
        ("kept", True, [(".gitkeep", False, None)]),
    ]
    warnings: list[str] = []
    phantom = tree._warn_for_empty_directories(entries, warnings)
    assert phantom == []
    assert warnings == []


def test_warn_for_empty_directories_skips_dir_with_gitignored_content(
    tmp_path: Path,
) -> None:
    """A dir that appears empty in the tree because all its contents are gitignored
    must not be flagged as phantom — it has real files on disk."""
    pycache = tmp_path / "src" / "__pycache__"
    pycache.mkdir(parents=True)
    (pycache / "module.cpython-313.pyc").write_text("", encoding="utf-8")
    entries: list[tree.TreeEntry] = [
        ("src", True, [("__pycache__", True, [])]),
    ]
    warnings: list[str] = []
    phantom = tree._warn_for_empty_directories(entries, warnings, root=tmp_path)
    assert phantom == []
    assert warnings == []


def test_warn_for_empty_directories_handles_oserror_on_iterdir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When .iterdir() raises OSError (e.g., permission denied), treat as empty."""
    unreadable = tmp_path / "src" / "unreadable"
    unreadable.mkdir(parents=True)
    entries: list[tree.TreeEntry] = [
        ("src", True, [("unreadable", True, [])]),
    ]
    warnings: list[str] = []

    def raise_oserror(self: object) -> None:  # type: ignore[override]
        raise OSError("Permission denied")

    monkeypatch.setattr(
        "pathlib.Path.iterdir",
        raise_oserror,
    )
    phantom = tree._warn_for_empty_directories(entries, warnings, root=tmp_path)
    assert "src/unreadable" in phantom
    assert any("Empty directory detected" in w for w in warnings)


def test_cmd_tree_warns_on_truly_empty_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Directories with no children at all warn — they cause local/CI drift."""
    (tmp_path / "src" / "icons").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tree, "_resolve_git_root", lambda cwd: tmp_path)
    monkeypatch.setattr(
        tree, "_batch_ignored_by_git", lambda paths_from_repo_root, repo_root: set()
    )

    rc = tree.cmd_tree(_args())

    out = capsys.readouterr().out
    assert rc == 0
    assert "Empty directory detected: src/icons/" in out
    assert ".gitkeep" in out


# ---------------------------------------------------------------------------
# _build_entries: OSError and relative_to edge cases
# ---------------------------------------------------------------------------


def test_build_entries_handles_oserror_on_sorted_children(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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


# ---------------------------------------------------------------------------
# Additional tests for remaining uncovered lines
# ---------------------------------------------------------------------------


def test_batch_ignored_empty_list_returns_empty_set(tmp_path: Path) -> None:
    """Line 222: _batch_ignored_by_git returns set() immediately for empty input."""
    result = tree._batch_ignored_by_git([], repo_root=tmp_path)
    assert result == set()


def test_batch_ignored_returns_nonempty_set_from_stdout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Line 239: _batch_ignored_by_git returns the set of ignored paths from git stdout."""
    import subprocess as _sp

    def fake_run(cmd: object, **kw: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=0, stdout="dist/\nbuild/\n", stderr="")

    monkeypatch.setattr(_sp, "run", fake_run)
    result = tree._batch_ignored_by_git(["dist/", "build/"], repo_root=tmp_path)
    assert "dist/" in result
    assert "build/" in result


def test_render_rich_tree_recursive_children(monkeypatch: pytest.MonkeyPatch) -> None:
    """Line 313: _render_rich_tree's build() recurses for nodes whose children also have children."""
    fake_console_mod, fake_tree_mod = _make_fake_rich_modules()

    monkeypatch.setattr(tree, "IS_LEGACY_TERMINAL", False)
    monkeypatch.setitem(sys.modules, "rich.console", fake_console_mod)
    monkeypatch.setitem(sys.modules, "rich.tree", fake_tree_mod)

    # 3-level depth: src/ → utils/ → helper.py — triggers recursive build() at line 313
    nested: tree.TreeEntry = ("helper.py", False, None)
    utils: tree.TreeEntry = ("utils", True, [nested])
    src: tree.TreeEntry = ("src", True, [utils])
    entries: list[tree.TreeEntry] = [src]

    result = tree._render_rich_tree(entries)
    assert isinstance(result, str)


def test_build_entries_rel_text_set_to_none_when_equal_repo_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Line 378: rel_text is set to None when child.relative_to(repo_root) == Path('.')."""
    # Create a child directory that IS the repo_root so relative_to returns Path(".")
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "file.txt").write_text("x", encoding="utf-8")

    # _build_entries is called on tmp_path; child 'repo' relative to repo_root == "."
    import subprocess as _sp

    def fake_run(cmd: object, **kw: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=1, stdout="", stderr="")

    monkeypatch.setattr(_sp, "run", fake_run)

    warnings: list[str] = []
    result = tree._build_entries(
        tmp_path,
        root=tmp_path,
        repo_root=repo_root,
        depth=1,
        max_depth=None,
        dirs_only=False,
        show_hidden=False,
        ignore_cache={},
        warnings=warnings,
    )
    assert isinstance(result, list)
    # 'repo' entry must exist with rel_text=None so it bypasses the ignore cache check
    assert any(name == "repo" for name, _is_dir, _children in result)


# ---------------------------------------------------------------------------
# --snapshot / --check / --strict
# ---------------------------------------------------------------------------


def test_cmd_tree_snapshot_writes_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--snapshot writes .rrt/tree.lock.toml and exits 0."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    rc = tree.cmd_tree(_args(root=str(tmp_path), snapshot=True))
    assert rc == 0
    assert (tmp_path / ".rrt" / "tree.lock.toml").exists()


def test_cmd_tree_check_no_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--check exits 0 when tree matches snapshot."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    tree.cmd_tree(_args(root=str(tmp_path), snapshot=True))
    rc = tree.cmd_tree(_args(root=str(tmp_path), check=True))
    assert rc == 0


def test_cmd_tree_check_drift_advisory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """--check without --strict exits 0 on drift."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    tree.cmd_tree(_args(root=str(tmp_path), snapshot=True))
    (tmp_path / "b.txt").write_text("y", encoding="utf-8")
    rc = tree.cmd_tree(_args(root=str(tmp_path), check=True))
    assert rc == 0
    assert "drift" in capsys.readouterr().out.lower()


def test_cmd_tree_check_drift_strict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """--check --strict exits 1 on drift and shows snapshot recommendation."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    tree.cmd_tree(_args(root=str(tmp_path), snapshot=True))
    (tmp_path / "b.txt").write_text("y", encoding="utf-8")
    rc = tree.cmd_tree(_args(root=str(tmp_path), check=True, strict=True))
    assert rc == 1
    captured = capsys.readouterr()
    assert "rrt tree --snapshot" in captured.err


# ---------------------------------------------------------------------------
# _canonical_entry_repr
# ---------------------------------------------------------------------------


def test_canonical_entry_repr_is_format_independent() -> None:
    """The canonical representation is independent of rendering format."""
    import json as _json

    entries: list[tree.TreeEntry] = [
        ("README.md", False, None),
        ("src", True, [("module.py", False, None)]),
    ]
    result = tree._canonical_entry_repr(entries)
    parsed = _json.loads(result)
    assert parsed[0]["name"] == "README.md"
    assert parsed[0]["is_dir"] is False
    assert parsed[1]["name"] == "src"
    assert parsed[1]["is_dir"] is True
    assert parsed[1]["children"][0]["name"] == "module.py"


def test_canonical_entry_repr_empty_entries() -> None:
    """Empty entry list returns a JSON empty array."""
    result = tree._canonical_entry_repr([])
    assert result == "[]"


def test_canonical_entry_repr_none_children_omitted() -> None:
    """Entries with children=None do not include 'children' key."""
    import json as _json

    entries: list[tree.TreeEntry] = [("file.txt", False, None)]
    result = tree._canonical_entry_repr(entries)
    parsed = _json.loads(result)
    assert "children" not in parsed[0]


def test_canonical_entry_repr_stable_across_formats(tmp_path: Path) -> None:
    """tree_hash in snapshot is stable regardless of --format flag used."""
    import tomllib as _tomllib

    (tmp_path / "a.txt").write_text("x", encoding="utf-8")

    hashes: list[str] = []
    for fmt in ("classic", "ascii"):
        tree.cmd_tree(_args(root=str(tmp_path), snapshot=True, format=fmt))
        lock_data = _tomllib.loads(
            (tmp_path / ".rrt" / "tree.lock.toml").read_text(encoding="utf-8")
        )
        hashes.append(lock_data["snapshot"]["tree_hash"])

    assert hashes[0] == hashes[1]


# ---------------------------------------------------------------------------
# Empty-directory drift: --strict-empty-dirs, --fix-empty-dirs, lock persistence
# ---------------------------------------------------------------------------


def test_cmd_tree_strict_empty_dirs_exits_nonzero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--strict-empty-dirs returns exit 1 and names the offender when phantoms exist."""
    (tmp_path / "src" / "icons").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tree, "_resolve_git_root", lambda cwd: tmp_path)
    monkeypatch.setattr(
        tree, "_batch_ignored_by_git", lambda paths_from_repo_root, repo_root: set()
    )

    rc = tree.cmd_tree(_args(strict_empty_dirs=True))

    out = capsys.readouterr().out
    assert rc == 1
    assert "src/icons" in out
    assert "fix-empty-dirs" in out


def test_cmd_tree_strict_empty_dirs_passes_when_gitkept(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--strict-empty-dirs returns 0 when empty dirs are preserved with .gitkeep."""
    (tmp_path / "src" / "mcp").mkdir(parents=True)
    (tmp_path / "src" / "mcp" / ".gitkeep").write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tree, "_resolve_git_root", lambda cwd: tmp_path)
    monkeypatch.setattr(
        tree, "_batch_ignored_by_git", lambda paths_from_repo_root, repo_root: set()
    )

    rc = tree.cmd_tree(_args(strict_empty_dirs=True))

    assert rc == 0


def test_cmd_tree_fix_empty_dirs_dry_run_yes_previews_gitkeep(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--fix-empty-dirs --dry-run --yes previews .gitkeep creation without writing."""
    target = tmp_path / "src" / "icons"
    target.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tree, "_resolve_git_root", lambda cwd: tmp_path)
    monkeypatch.setattr(
        tree, "_batch_ignored_by_git", lambda paths_from_repo_root, repo_root: set()
    )

    rc = tree.cmd_tree(
        _args(fix_empty_dirs=True, dry_run=True, yes=True),
    )

    out = capsys.readouterr().out
    assert rc == 0
    assert "src/icons" in out
    assert "Would create" in out or "dry-run" in out.lower()
    assert not (target / ".gitkeep").exists()


def test_cmd_tree_fix_empty_dirs_yes_creates_gitkeep(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--fix-empty-dirs --yes (non dry-run) writes .gitkeep for every phantom."""
    target = tmp_path / "src" / "icons"
    target.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tree, "_resolve_git_root", lambda cwd: tmp_path)
    monkeypatch.setattr(
        tree, "_batch_ignored_by_git", lambda paths_from_repo_root, repo_root: set()
    )

    rc = tree.cmd_tree(_args(fix_empty_dirs=True, yes=True))

    assert rc == 0
    assert (target / ".gitkeep").exists()


def test_cmd_tree_snapshot_persists_phantom_empty_dirs_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """build_tree_lock writes phantom_empty_dirs into [snapshot] for CI diagnosis."""
    import tomllib as _tomllib

    (tmp_path / "src" / "icons").mkdir(parents=True)
    (tmp_path / "README.md").write_text("# x\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tree, "_resolve_git_root", lambda cwd: tmp_path)
    monkeypatch.setattr(
        tree, "_batch_ignored_by_git", lambda paths_from_repo_root, repo_root: set()
    )

    rc = tree.cmd_tree(_args(snapshot=True))

    assert rc == 0
    lock_data = _tomllib.loads(
        (tmp_path / ".rrt" / "tree.lock.toml").read_text(encoding="utf-8"),
    )
    assert lock_data["snapshot"]["phantom_empty_dirs"] == ["src/icons"]


# ---------------------------------------------------------------------------
# F2 — positional path, json/flat formats, --absolute, --output
# ---------------------------------------------------------------------------


def _f2_args(**overrides: object) -> argparse.Namespace:
    """Args factory with the F2 fields wired in."""
    base: dict[str, object] = {
        "format": "classic",
        "max_depth": None,
        "dirs_only": False,
        "show_hidden": False,
        "root": ".",
        "inject": None,
        "anchor": None,
        "dry_run": False,
        "path": None,
        "absolute": False,
        "output": None,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def test_cmd_tree_positional_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A positional path argument selects the traversal root."""
    _make_fixture_tree(tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = tree.cmd_tree(_f2_args(path=str(tmp_path / "src")))
    out = capsys.readouterr().out
    assert rc == 0
    assert "pkg" in out
    assert "README.md" not in out  # README lives at repo root, not under src/


def test_cmd_tree_positional_overrides_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When both positional path and --root are given, positional wins."""
    _make_fixture_tree(tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = tree.cmd_tree(
        _f2_args(path=str(tmp_path / "src"), root=str(tmp_path)),
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "pkg" in out
    assert "README.md" not in out


def test_cmd_tree_format_json_nested(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--format json emits a nested document with name/is_dir/path/children."""
    import json as _json

    _make_fixture_tree(tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = tree.cmd_tree(_f2_args(format="json"))
    out = capsys.readouterr().out
    assert rc == 0
    # The tree section banner precedes the JSON; strip the printed JSON line.
    json_lines = [line for line in out.splitlines() if line.startswith("[")]
    assert json_lines, f"expected a JSON line in: {out!r}"
    data = _json.loads(json_lines[0])
    names = [entry["name"] for entry in data]
    assert "src" in names
    src = next(e for e in data if e["name"] == "src")
    assert src["is_dir"] is True
    assert src["path"] == "src"
    assert any(child["name"] == "pkg" for child in src["children"])


def test_cmd_tree_format_flat_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--format flat emits one path per line, directories with trailing /."""
    _make_fixture_tree(tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = tree.cmd_tree(_f2_args(format="flat"))
    out = capsys.readouterr().out
    assert rc == 0
    assert "src/" in out
    assert "src/pkg/" in out
    assert "src/pkg/module.py" in out
    assert "README.md" in out


def test_cmd_tree_flat_dirs_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--format flat + --dirs-only produces the pure folder skeleton."""
    _make_fixture_tree(tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = tree.cmd_tree(_f2_args(format="flat", dirs_only=True))
    out = capsys.readouterr().out
    assert rc == 0
    assert "src/pkg/" in out
    assert "module.py" not in out
    assert "README.md" not in out


def test_cmd_tree_absolute_paths_flat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--absolute prefixes flat paths with the resolved root."""
    _make_fixture_tree(tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = tree.cmd_tree(_f2_args(format="flat", absolute=True))
    out = capsys.readouterr().out
    assert rc == 0
    resolved = tmp_path.resolve().as_posix()
    assert f"{resolved}/src/" in out
    assert f"{resolved}/README.md" in out


def test_cmd_tree_output_writes_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--output writes the rendered tree to a file and skips stdout."""
    _make_fixture_tree(tmp_path)
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "tree.txt"
    rc = tree.cmd_tree(_f2_args(format="flat", output=str(target)))
    assert rc == 0
    body = target.read_text(encoding="utf-8")
    assert "src/" in body
    # The "Project tree" banner is suppressed when writing to a file.
    assert "Project tree" not in capsys.readouterr().out


def test_cmd_tree_json_deterministic_ordering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--format json output is byte-stable across runs."""
    _make_fixture_tree(tmp_path)
    monkeypatch.chdir(tmp_path)
    rc1 = tree.cmd_tree(_f2_args(format="json"))
    out1 = capsys.readouterr().out
    rc2 = tree.cmd_tree(_f2_args(format="json"))
    out2 = capsys.readouterr().out
    assert rc1 == rc2 == 0
    json1 = next(line for line in out1.splitlines() if line.startswith("["))
    json2 = next(line for line in out2.splitlines() if line.startswith("["))
    assert json1 == json2


def test_cmd_tree_output_replays_warnings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--output mode forwards any warnings (e.g. phantom empty dirs) to the printer."""
    (tmp_path / "src" / "empty_widget").mkdir(parents=True)
    (tmp_path / "README.md").write_text("x", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tree, "_resolve_git_root", lambda cwd: tmp_path)
    monkeypatch.setattr(
        tree, "_batch_ignored_by_git", lambda paths_from_repo_root, repo_root: set()
    )

    target = tmp_path / "out.flat"
    rc = tree.cmd_tree(_f2_args(format="flat", output=str(target)))

    assert rc == 0
    # The warning text gets relayed via the printer even though stdout was
    # diverted to a file.
    captured = capsys.readouterr().out + capsys.readouterr().err
    assert "Empty directory" in captured or "empty_widget" in captured
