"""`check-dirty-tree --ignore-generated` on both the `rrt git` and `rrt-hooks` surfaces.

Both surfaces share `split_generated_dirt`, so each scenario runs against a
real repository and checks that the two agree.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import pytest
from repo_fixtures import init_git_repo

from repo_release_tools.commands import git_inspect
from repo_release_tools.commands._git_shared import STATUS_MAX, split_generated_dirt
from repo_release_tools.workflow import hooks

_PYPROJECT = """\
[project]
name = "example"
version = "0.1.0"

[tool.rrt]

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"
{git_section}
"""


def _repo(tmp_path: Path, *, generated: list[str] | None) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root, branch="main")
    git_section = ""
    if generated is not None:
        quoted = ", ".join(f'"{pattern}"' for pattern in generated)
        git_section = f"\n[tool.rrt.git]\ngenerated = [{quoted}]\n"
    (root / "pyproject.toml").write_text(_PYPROJECT.format(git_section=git_section))
    (root / "HANDOFF.md").write_text("head: one\n")
    (root / "app.py").write_text("print('one')\n")
    subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=root, check=True, capture_output=True)
    return root


def _cli(ignore_generated: bool = True) -> int:
    return git_inspect.cmd_check_dirty_tree(
        argparse.Namespace(verbose=0, ignore_generated=ignore_generated)
    )


def _hook(root: Path) -> int:
    return hooks.run_dirty_tree_check(root, title="Dirty tree", ignore_generated=True)


def test_only_generated_dirt_passes_on_both_surfaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path, generated=["HANDOFF.md"])
    monkeypatch.chdir(root)
    (root / "HANDOFF.md").write_text("head: two\n")

    assert _cli() == 0
    out = capsys.readouterr().out
    assert "Working tree is clean (generated paths ignored)." in out
    assert "generated (ignored): HANDOFF.md" in out

    assert _hook(root) == 0
    # Without the flag the regenerated file still reads as dirty.
    assert _cli(ignore_generated=False) == 1
    assert hooks.run_dirty_tree_check(root, title="Dirty tree") == 1


def test_untracked_generated_file_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path, generated=["build/**"])
    monkeypatch.chdir(root)
    (root / "build" / "deep").mkdir(parents=True)
    (root / "build" / "deep" / "out.json").write_text("{}\n")

    assert _cli() == 0
    assert _hook(root) == 0


def test_other_dirt_still_fails_and_lists_both_kinds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path, generated=["HANDOFF.md"])
    monkeypatch.chdir(root)
    (root / "HANDOFF.md").write_text("head: two\n")
    (root / "app.py").write_text("print('two')\n")

    assert _cli() == 1
    err = capsys.readouterr().err
    assert "Working tree has uncommitted changes." in err
    assert "app.py" in err
    assert "generated (ignored): HANDOFF.md" in err

    assert _hook(root) == 1
    hook_err = capsys.readouterr().err
    assert "M app.py" in hook_err
    assert "HANDOFF.md" not in hook_err


def test_no_patterns_configured_warns_and_ignores_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path, generated=None)
    monkeypatch.chdir(root)

    assert _cli() == 0
    captured = capsys.readouterr()
    assert "No [tool.rrt.git].generated patterns are configured" in captured.err
    assert "Working tree is clean" in captured.out

    (root / "HANDOFF.md").write_text("head: two\n")
    assert _cli() == 1
    assert _hook(root) == 1


def test_long_lists_are_truncated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path, generated=["gen/*.txt"])
    monkeypatch.chdir(root)
    for index in range(STATUS_MAX + 2):
        (root / f"other-{index}.txt").write_text("x\n")
        (root / "gen").mkdir(exist_ok=True)
        (root / "gen" / f"g-{index}.txt").write_text("x\n")

    assert _cli() == 1
    err = capsys.readouterr().err
    assert "…and 2 more" in err
    assert "…and 2 more generated" in err


def test_bad_config_is_reported_on_both_surfaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path, generated=None)
    monkeypatch.chdir(root)
    with (root / "pyproject.toml").open("a") as fh:
        fh.write("\n[tool.rrt.git]\ngenerated = 5\n")

    assert _cli() == 1
    assert "Failed to load [tool.rrt.git]" in capsys.readouterr().err
    assert _hook(root) == 1
    assert "Failed to load [tool.rrt.git]" in capsys.readouterr().err


def test_split_generated_dirt_reports_patterns(tmp_path: Path) -> None:
    root = _repo(tmp_path, generated=["HANDOFF.md"])
    (root / "HANDOFF.md").write_text("head: two\n")
    split = split_generated_dirt(root)
    assert split.patterns == ("HANDOFF.md",)
    assert [entry.path for entry in split.generated] == ["HANDOFF.md"]
    assert split.other == []


def test_hook_verbose_lists_generated_entries(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path, generated=["HANDOFF.md"])
    (root / "HANDOFF.md").write_text("head: two\n")
    assert (
        hooks.run_dirty_tree_check(root, title="Dirty tree", verbose=1, ignore_generated=True) == 0
    )
    err = capsys.readouterr().err
    assert "generated (ignored): HANDOFF.md" in err
    assert "working tree clean (generated paths ignored)" in err
