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
