"""Direct unit tests for ``commands/_tree_fix`` covering branches that are
not reachable via ``cmd_tree`` (OSError handlers, delete path, prompt parsing,
empty-list early return)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from repo_release_tools.commands import _tree_fix
from repo_release_tools.ui.messaging import DryRunPrinter


def _printer() -> DryRunPrinter:
    return DryRunPrinter(dry_run=False)


def test_fix_empty_dirs_empty_list_returns_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = _tree_fix.fix_empty_dirs(tmp_path, [], printer=_printer())
    assert rc == 0
    out = capsys.readouterr().out
    assert "CI-stable" in out


def test_choose_action_assume_yes_returns_gitkeep() -> None:
    assert _tree_fix._choose_action("a", assume_yes=True) == "gitkeep"


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("d", "delete"),
        ("delete", "delete"),
        ("h", "hard-delete"),
        ("hard", "hard-delete"),
        ("hard-delete", "hard-delete"),
        ("s", "skip"),
        ("skip", "skip"),
        ("k", "gitkeep"),
        ("", "gitkeep"),
        ("anything-else", "gitkeep"),
    ],
)
def test_choose_action_parses_prompt(
    monkeypatch: pytest.MonkeyPatch, answer: str, expected: str
) -> None:
    monkeypatch.setattr(_tree_fix, "ask", lambda *_a, **_k: answer)
    assert _tree_fix._choose_action("rel/path", assume_yes=False) == expected


def test_fix_empty_dirs_delete_real(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "to_delete"
    target.mkdir()
    monkeypatch.setattr(_tree_fix, "_choose_action", lambda _rel, *, assume_yes: "delete")
    rc = _tree_fix.fix_empty_dirs(tmp_path, ["to_delete"], printer=_printer())
    assert rc == 0
    assert not target.exists()


def test_fix_empty_dirs_delete_dry_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "still_here"
    target.mkdir()
    monkeypatch.setattr(_tree_fix, "_choose_action", lambda _rel, *, assume_yes: "delete")
    rc = _tree_fix.fix_empty_dirs(
        tmp_path, ["still_here"], printer=DryRunPrinter(dry_run=True), dry_run=True
    )
    assert rc == 0
    assert target.exists()
    out = capsys.readouterr().out
    assert "Would remove still_here" in out


def test_fix_empty_dirs_skip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "leave_me").mkdir()
    monkeypatch.setattr(_tree_fix, "_choose_action", lambda _rel, *, assume_yes: "skip")
    rc = _tree_fix.fix_empty_dirs(tmp_path, ["leave_me"], printer=_printer())
    assert rc == 0
    assert (tmp_path / "leave_me").exists()
    assert "Skipped" in capsys.readouterr().out


def test_fix_empty_dirs_gitkeep_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "bad").mkdir()
    monkeypatch.setattr(_tree_fix, "_choose_action", lambda _rel, *, assume_yes: "gitkeep")

    real_write_text = Path.write_text

    def failing_write_text(self: Path, *a: Any, **k: Any) -> int:
        if self.name == ".gitkeep":
            raise OSError("disk full")
        return real_write_text(self, *a, **k)

    monkeypatch.setattr(Path, "write_text", failing_write_text)
    rc = _tree_fix.fix_empty_dirs(tmp_path, ["bad"], printer=_printer())
    assert rc == 1
    out = capsys.readouterr().out
    assert "Failed" in out


def test_fix_empty_dirs_delete_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "stubborn").mkdir()
    monkeypatch.setattr(_tree_fix, "_choose_action", lambda _rel, *, assume_yes: "delete")

    def failing_rmdir(self: Path) -> None:
        raise OSError("not empty")

    monkeypatch.setattr(Path, "rmdir", failing_rmdir)
    rc = _tree_fix.fix_empty_dirs(tmp_path, ["stubborn"], printer=_printer())
    assert rc == 1
    out = capsys.readouterr().out
    assert "Failed" in out


def test_fix_empty_dirs_gitkeep_dry_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "pending").mkdir()
    monkeypatch.setattr(_tree_fix, "_choose_action", lambda _rel, *, assume_yes: "gitkeep")
    rc = _tree_fix.fix_empty_dirs(
        tmp_path, ["pending"], printer=DryRunPrinter(dry_run=True), dry_run=True
    )
    assert rc == 0
    assert not (tmp_path / "pending" / ".gitkeep").exists()
    out = capsys.readouterr().out
    assert "Would create" in out


def test_fix_empty_dirs_singular_plural(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in ("a", "b"):
        (tmp_path / name).mkdir()
    monkeypatch.setattr(_tree_fix, "_choose_action", lambda _rel, *, assume_yes: "skip")
    rc = _tree_fix.fix_empty_dirs(tmp_path, ["a", "b"], printer=_printer())
    assert rc == 0
    assert "2 empty directories" in capsys.readouterr().out


def test_fix_empty_dirs_hard_delete_real(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "to_hard_delete"
    target.mkdir()
    (target / "ignored.pyc").write_text("", encoding="utf-8")
    monkeypatch.setattr(_tree_fix, "_choose_action", lambda _rel, *, assume_yes: "hard-delete")
    rc = _tree_fix.fix_empty_dirs(tmp_path, ["to_hard_delete"], printer=_printer())
    assert rc == 0
    assert not target.exists()


def test_fix_empty_dirs_hard_delete_dry_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "still_here"
    target.mkdir()
    (target / "ignored.pyc").write_text("", encoding="utf-8")
    monkeypatch.setattr(_tree_fix, "_choose_action", lambda _rel, *, assume_yes: "hard-delete")
    rc = _tree_fix.fix_empty_dirs(
        tmp_path, ["still_here"], printer=DryRunPrinter(dry_run=True), dry_run=True
    )
    assert rc == 0
    assert target.exists()
    assert "Would hard-remove still_here" in capsys.readouterr().out


def test_fix_empty_dirs_hard_delete_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "stubborn").mkdir()
    monkeypatch.setattr(_tree_fix, "_choose_action", lambda _rel, *, assume_yes: "hard-delete")

    def failing_rmtree(path: Path) -> None:
        raise OSError("permission denied")

    monkeypatch.setattr(_tree_fix.shutil, "rmtree", failing_rmtree)
    rc = _tree_fix.fix_empty_dirs(tmp_path, ["stubborn"], printer=_printer())
    assert rc == 1
    assert "Failed" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# F3 — git-rm action + --auto-resolve
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("g", "git-rm"),
        ("git", "git-rm"),
        ("git-rm", "git-rm"),
        ("gitrm", "git-rm"),
        ("G", "git-rm"),  # case-insensitive via .lower() in _choose_action
    ],
)
def test_choose_action_recognises_git_rm(
    monkeypatch: pytest.MonkeyPatch, answer: str, expected: str
) -> None:
    monkeypatch.setattr(_tree_fix, "ask", lambda *_a, **_k: answer)
    assert _tree_fix._choose_action("rel", assume_yes=False) == expected


def _init_git_repo(root: Path) -> None:
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=root, check=True)


def test_fix_empty_dirs_git_rm_real(tmp_path: Path) -> None:
    """`git-rm` action runs `git rm -rf` and stages the removal."""
    import subprocess

    _init_git_repo(tmp_path)
    tracked = tmp_path / "stale"
    tracked.mkdir()
    (tracked / "file.txt").write_text("doomed\n", encoding="utf-8")
    subprocess.run(["git", "add", "stale/file.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=tmp_path, check=True)

    rc = _tree_fix.fix_empty_dirs(tmp_path, ["stale"], printer=_printer(), auto_resolve="git-rm")
    assert rc == 0
    assert not tracked.exists()
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout
    assert "D  stale/file.txt" in status or "stale/file.txt" in status


def test_fix_empty_dirs_git_rm_dry_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`--auto-resolve git-rm --dry-run` only prints the planned action."""
    (tmp_path / "untouched").mkdir()
    rc = _tree_fix.fix_empty_dirs(
        tmp_path,
        ["untouched"],
        printer=DryRunPrinter(dry_run=True),
        dry_run=True,
        auto_resolve="git-rm",
    )
    assert rc == 0
    assert (tmp_path / "untouched").exists()
    assert "Would git-rm untouched" in capsys.readouterr().out


def test_fix_empty_dirs_git_rm_failure_outside_repo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Running `git-rm` outside a git repo records a failure."""
    (tmp_path / "lonely").mkdir()
    rc = _tree_fix.fix_empty_dirs(tmp_path, ["lonely"], printer=_printer(), auto_resolve="git-rm")
    assert rc == 1
    out = capsys.readouterr().out
    assert "Failed to git-rm lonely" in out


def test_auto_resolve_unknown_choice_returns_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unknown --auto-resolve value is rejected up-front."""
    rc = _tree_fix.fix_empty_dirs(tmp_path, ["anything"], printer=_printer(), auto_resolve="bogus")
    assert rc == 1
    assert "Unknown --auto-resolve" in capsys.readouterr().out


def test_auto_resolve_hard_maps_to_hard_delete(
    tmp_path: Path,
) -> None:
    """`--auto-resolve hard` is the rmtree path (alias for hard-delete)."""
    target = tmp_path / "wipe"
    target.mkdir()
    (target / "x").write_text("", encoding="utf-8")
    rc = _tree_fix.fix_empty_dirs(tmp_path, ["wipe"], printer=_printer(), auto_resolve="hard")
    assert rc == 0
    assert not target.exists()


def test_auto_resolve_gitkeep_skips_prompt(
    tmp_path: Path,
) -> None:
    """`--auto-resolve gitkeep` writes .gitkeep with no prompt and no --yes."""
    (tmp_path / "anchored").mkdir()
    rc = _tree_fix.fix_empty_dirs(
        tmp_path, ["anchored"], printer=_printer(), auto_resolve="gitkeep"
    )
    assert rc == 0
    assert (tmp_path / "anchored" / ".gitkeep").exists()
