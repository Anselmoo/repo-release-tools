from __future__ import annotations

import argparse
from argparse import Namespace
from pathlib import Path

import pytest

from repo_release_tools.commands.drift_cmd import (
    _collect_drift_sources,
    cmd_check,
    cmd_generate,
    register,
)
from repo_release_tools.state import hash_content


def _touch(path: Path, content: str = "x\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_cmd_generate_writes_lock(tmp_path: Path) -> None:
    _touch(tmp_path / ".claude" / "settings.json", '{"hooks": {}}\n')
    _touch(tmp_path / ".claude" / "hooks" / "sample.py", "print('x')\n")
    _touch(tmp_path / ".github" / "agents" / "sample.agent.md", "---\nname: sample\n---\n")
    _touch(tmp_path / ".github" / "copilot-instructions.md", "# instructions\n")
    _touch(tmp_path / ".github" / "instructions" / "example.md", "# example\n")
    _touch(tmp_path / ".github" / "skills" / "rrt-user-bootstrap" / "SKILL.md", "name: test\n")

    result = cmd_generate(Namespace(root=str(tmp_path), lock_file="drift.lock.toml", dry_run=False))

    lock_path = tmp_path / ".rrt" / "drift.lock.toml"
    rendered = lock_path.read_text(encoding="utf-8")

    assert result == 0
    assert lock_path.exists()
    assert ".claude/settings.json" in rendered
    assert ".github/copilot-instructions.md" in rendered
    assert ".github/skills/rrt-user-bootstrap/SKILL.md" in rendered


def test_cmd_generate_dry_run_does_not_write(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _touch(tmp_path / ".claude" / "settings.json", '{"hooks": {}}\n')

    result = cmd_generate(Namespace(root=str(tmp_path), lock_file="drift.lock.toml", dry_run=True))

    captured = capsys.readouterr()
    assert result == 0
    assert not (tmp_path / ".rrt" / "drift.lock.toml").exists()
    assert "drift lockfile (dry-run, not written)" in captured.out


def test_cmd_check_reports_stale_lock(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _touch(tmp_path / ".claude" / "settings.json", '{"hooks": {}}\n')

    result = cmd_check(Namespace(root=str(tmp_path), lock_file="drift.lock.toml"))

    captured = capsys.readouterr()
    assert result == 1
    assert "drift lockfile is stale" in captured.err
    assert "Run 'rrt drift generate --dry-run'" in captured.err


def test_cmd_check_accepts_current_lock(tmp_path: Path) -> None:
    _touch(tmp_path / ".claude" / "settings.json", '{"hooks": {}}\n')
    assert (
        cmd_generate(Namespace(root=str(tmp_path), lock_file="drift.lock.toml", dry_run=False)) == 0
    )

    assert cmd_check(Namespace(root=str(tmp_path), lock_file="drift.lock.toml")) == 0


def test_register_adds_drift_generate_parser() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    register(subparsers)

    args = parser.parse_args(["drift", "generate", "--dry-run"])

    assert args.command == "drift"
    assert args.drift_command == "generate"
    assert args.handler.__name__ == "cmd_generate"


def test_collect_drift_sources_skips_dirs_and_dedupes(monkeypatch: pytest.MonkeyPatch) -> None:
    root = Path("/tmp/repo")
    file_path = root / ".claude" / "settings.json"
    dir_path = root / ".claude" / "hooks"

    monkeypatch.setattr(
        Path,
        "glob",
        lambda self, _pattern: [dir_path, file_path, file_path],
    )
    monkeypatch.setattr(Path, "is_file", lambda self: self == file_path)
    monkeypatch.setattr(Path, "read_text", lambda self, encoding="utf-8": "{}")

    sources = _collect_drift_sources(root)

    assert sources == [
        {
            "source_file": ".claude/settings.json",
            "hash": hash_content("{}"),
            "symbols": [],
            "lang": "text",
        },
    ]
