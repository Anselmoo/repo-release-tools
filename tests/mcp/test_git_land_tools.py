"""MCP tools for issue #258: dirty-tree, commits-since, land and gate-run.

Each tool shares its core with the CLI (`split_generated_dirt`, `commits_since`,
`plan_land`/`apply_land`, `run_gates`), so these tests drive real repositories
and check the typed result shape the client relies on.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from repo_fixtures import init_git_repo

pytest.importorskip("fastmcp", reason="[mcp] extra not installed")

from repo_release_tools.mcp.tools.gate_tools import register as register_gate  # noqa: E402
from repo_release_tools.mcp.tools.git_tools import register as register_git  # noqa: E402

pytestmark = pytest.mark.mcp

_PYPROJECT = """\
[project]
name = "x"
version = "0.1.0"

[tool.rrt]

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[tool.rrt.git]
generated = ["HANDOFF.md"]
{gates}"""

_GATES = """
[[tool.rrt.gates]]
name = "ok"
run = "true"

[[tool.rrt.gates]]
name = "seeded"
run = "exit 3"
expect = 3
"""


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _commit(root: Path, rel: str, text: str, message: str) -> None:
    (root / rel).write_text(text, encoding="utf-8")
    _git(root, "add", "--", rel)
    _git(root, "commit", "-q", "-m", message)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    main = tmp_path / "main"
    main.mkdir()
    init_git_repo(main, branch="main")
    _commit(main, "pyproject.toml", _PYPROJECT.format(gates=_GATES), "chore: init")
    _commit(main, "HANDOFF.md", "head: one\n", "docs: handoff")
    _git(main, "worktree", "add", "-q", str(tmp_path / "wt"), "-b", "feat/x")
    _commit(tmp_path / "wt", "feature.txt", "work\n", "feat: x")
    return main


def _ctx(root: Path) -> MagicMock:
    ctx = MagicMock()
    ctx.lifespan_context = {"root": root, "config": None}
    ctx.info = AsyncMock()
    ctx.warning = AsyncMock()
    return ctx


@pytest.fixture
def tools(capture_mcp: Any) -> dict[str, Any]:
    register_git(capture_mcp)
    register_gate(capture_mcp)
    return capture_mcp._tools


def _call(tools: dict[str, Any], name: str, root: Path, **kwargs: Any) -> Any:
    result = tools[name](_ctx(root), **kwargs)
    return asyncio.run(result) if asyncio.iscoroutine(result) else result


# ── rrt_git_dirty_tree ───────────────────────────────────────────────────────


def test_dirty_tree_marks_generated_entries(tools: dict[str, Any], repo: Path) -> None:
    (repo / "HANDOFF.md").write_text("head: two\n")
    (repo / "notes.txt").write_text("x\n")

    strict = _call(tools, "rrt_git_dirty_tree", repo)
    lenient = _call(tools, "rrt_git_dirty_tree", repo, ignore_generated=True)

    assert strict.clean is False and lenient.clean is False
    assert {(e.path, e.generated) for e in strict.entries} == {
        ("HANDOFF.md", True),
        ("notes.txt", False),
    }
    assert strict.patterns == ["HANDOFF.md"]


def test_dirty_tree_generated_only(tools: dict[str, Any], repo: Path) -> None:
    (repo / "HANDOFF.md").write_text("head: two\n")
    assert _call(tools, "rrt_git_dirty_tree", repo).clean is False
    assert _call(tools, "rrt_git_dirty_tree", repo, ignore_generated=True).clean is True


def test_dirty_tree_error(tools: dict[str, Any], tmp_path: Path) -> None:
    result = _call(tools, "rrt_git_dirty_tree", tmp_path)
    assert result.clean is False
    assert result.error is not None


# ── rrt_git_commits_since ────────────────────────────────────────────────────


def test_commits_since_excludes_generated(tools: dict[str, Any], repo: Path) -> None:
    base = _git(repo, "rev-list", "--max-parents=0", "HEAD")
    everything = _call(tools, "rrt_git_commits_since", repo, ref=base)
    without = _call(tools, "rrt_git_commits_since", repo, ref=base, exclude_generated=True)
    assert everything.count == 1
    assert without.count == 0
    assert without.exclude == ["HANDOFF.md"]


def test_commits_since_bad_ref_is_an_error_not_zero(tools: dict[str, Any], repo: Path) -> None:
    result = _call(tools, "rrt_git_commits_since", repo, ref="missing", exclude=["a"])
    assert result.error is not None
    assert result.count == 0
    assert result.exclude == ["a"]


# ── rrt_git_land ─────────────────────────────────────────────────────────────


def test_land_defaults_to_dry_run(tools: dict[str, Any], repo: Path) -> None:
    before = _git(repo, "rev-parse", "main")
    result = _call(tools, "rrt_git_land", repo, branch="feat/x")
    assert result.dry_run is True
    assert result.landed is False
    assert [step.status for step in result.steps] == ["would-run", "would-run", "would-run"]
    assert _git(repo, "rev-parse", "main") == before
    assert result.worktrees_before == 2 and result.worktrees_after is None


def test_land_applies_from_inside_the_worktree(tools: dict[str, Any], repo: Path) -> None:
    wt = repo.parent / "wt"
    result = _call(tools, "rrt_git_land", wt, branch="feat/x", dry_run=False)
    assert result.error is None
    assert result.landed is True
    assert result.cwd_removed is True
    assert (result.worktrees_after, result.branches_after) == (1, 1)
    assert not wt.exists()


def test_land_precondition_error_carries_details(tools: dict[str, Any], repo: Path) -> None:
    (repo.parent / "wt" / "HANDOFF.md").write_text("head: two\n")
    result = _call(tools, "rrt_git_land", repo, branch="feat/x")
    assert result.error is not None and "generated paths only" in result.error
    assert any("--restore-generated" in detail for detail in result.details)
    assert result.steps == []


def test_land_git_error_during_planning(
    tools: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from repo_release_tools.commands import git_land

    monkeypatch.setattr(git_land.git, "is_git_repository", lambda cwd: True)

    def boom(cwd: Path) -> list[object]:
        raise RuntimeError("git worktree list failed")

    monkeypatch.setattr(git_land.git, "worktree_list", boom)
    result = _call(tools, "rrt_git_land", tmp_path, branch="feat/x")
    assert result.error == "git worktree list failed"


def test_land_step_failure_is_reported(tools: dict[str, Any], repo: Path) -> None:
    (repo / "feature.txt").write_text("in the way\n")
    result = _call(tools, "rrt_git_land", repo, branch="feat/x", dry_run=False)
    assert result.landed is False
    assert result.error is not None
    assert result.steps[0].status == "failed"
    assert result.notes


# ── rrt_gate_run ─────────────────────────────────────────────────────────────


def test_gate_run_defaults_to_dry_run(tools: dict[str, Any], repo: Path) -> None:
    result = _call(tools, "rrt_gate_run", repo)
    assert result.dry_run is True
    assert result.ok is False
    assert [(line.name, line.exit) for line in result.lines] == [("ok", None), ("seeded", None)]


def test_gate_run_reports_expected_vs_actual(tools: dict[str, Any], repo: Path) -> None:
    result = _call(tools, "rrt_gate_run", repo, dry_run=False)
    assert result.ok is True
    seeded = result.lines[1]
    assert (seeded.exit, seeded.expected_exit, seeded.ok) == (3, 3, True)


def test_gate_run_unknown_name(tools: dict[str, Any], repo: Path) -> None:
    result = _call(tools, "rrt_gate_run", repo, names=["nope"])
    assert result.ok is False
    assert result.error is not None and "Unknown gate(s): nope" in result.error


def test_gate_run_nothing_configured(tools: dict[str, Any], tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT.format(gates=""))
    result = _call(tools, "rrt_gate_run", tmp_path)
    assert result.error == "No [[tool.rrt.gates]] lines are configured."
