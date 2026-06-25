"""Tests for the rrt sync command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from repo_release_tools.commands import sync_cmd

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PYPROJECT_BASE = (
    '[tool.rrt]\nrelease_branch = "release/v{version}"\n'
    '[[tool.rrt.version_targets]]\npath = "pyproject.toml"\nkind = "pep621"\n'
    '[project]\nname = "x"\nversion = "0.5.0"\n'
)

_PYPROJECT_WITH_UPSTREAM = _PYPROJECT_BASE + '[tool.rrt.upstream]\npackage = "ruff"\n'

_PYPROJECT_WITH_PROVIDER = (
    '[tool.rrt]\nrelease_branch = "release/v{version}"\n'
    '[[tool.rrt.version_targets]]\npath = "pyproject.toml"\nkind = "pep621"\n'
    '[project]\nname = "x"\nversion = "0.5.0"\n'
    '[tool.rrt.upstream]\npackage = "mypackage"\nprovider = "npm"\n'
)


def _ns(**kwargs: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "dry_run": False,
        "group": None,
        "json": False,
        "verbose": 0,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


# ---------------------------------------------------------------------------
# Test 1: lists newer versions, filters out older/equal
# ---------------------------------------------------------------------------


def test_cmd_sync_lists_newer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        _PYPROJECT_WITH_UPSTREAM,
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sync_cmd,
        "fetch_versions",
        lambda pkg, provider: ["0.4.0", "0.5.0", "0.6.0", "0.5.1"],
    )
    rc = sync_cmd.cmd_sync(_ns())
    out = capsys.readouterr().out
    assert rc == 0
    assert "0.5.1" in out
    assert "0.6.0" in out
    assert "0.4.0" not in out
    assert "0.5.0" not in out


# ---------------------------------------------------------------------------
# Test 2: --json emits a JSON array
# ---------------------------------------------------------------------------


def test_cmd_sync_json_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        _PYPROJECT_WITH_UPSTREAM,
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sync_cmd,
        "fetch_versions",
        lambda pkg, provider: ["0.4.0", "0.5.0", "0.6.0", "0.5.1"],
    )
    rc = sync_cmd.cmd_sync(_ns(json=True))
    out = capsys.readouterr().out.strip()
    assert rc == 0
    data = json.loads(out)
    assert isinstance(data, list)
    assert "0.5.1" in data
    assert "0.6.0" in data
    assert "0.4.0" not in data


# ---------------------------------------------------------------------------
# Test 3: no upstream_package configured → returns 1
# ---------------------------------------------------------------------------


def test_cmd_sync_errors_without_upstream(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        _PYPROJECT_BASE,
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    assert sync_cmd.cmd_sync(_ns()) == 1


# ---------------------------------------------------------------------------
# Test 4: provider other than pypi is passed through to fetch_versions
# ---------------------------------------------------------------------------


def test_cmd_sync_passes_provider_to_fetch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        _PYPROJECT_WITH_PROVIDER,
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    received: list[tuple[str, str]] = []

    def _fake_fetch(pkg: str, provider: str) -> list[str]:
        received.append((pkg, provider))
        return ["0.6.0"]

    monkeypatch.setattr(sync_cmd, "fetch_versions", _fake_fetch)

    rc = sync_cmd.cmd_sync(_ns())
    capsys.readouterr()  # consume output
    assert rc == 0
    assert len(received) == 1
    assert received[0] == ("mypackage", "npm")


# ---------------------------------------------------------------------------
# Test 5: empty result when no newer versions → still returns 0
# ---------------------------------------------------------------------------


def test_cmd_sync_no_newer_exits_0(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        _PYPROJECT_WITH_UPSTREAM,
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sync_cmd,
        "fetch_versions",
        lambda pkg, provider: ["0.4.0", "0.3.0"],
    )
    rc = sync_cmd.cmd_sync(_ns())
    out = capsys.readouterr().out
    assert rc == 0
    assert out.strip() == ""


# ---------------------------------------------------------------------------
# Test 6: non-semver tags are skipped without error
# ---------------------------------------------------------------------------


def test_cmd_sync_skips_non_semver(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        _PYPROJECT_WITH_UPSTREAM,
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sync_cmd,
        "fetch_versions",
        lambda pkg, provider: ["0.6.0rc1", "not-a-version", "0.7.0", "1.0.0a1"],
    )
    rc = sync_cmd.cmd_sync(_ns())
    out = capsys.readouterr().out
    assert rc == 0
    assert "0.7.0" in out
    # non-semver entries silently dropped
    assert "not-a-version" not in out


# ---------------------------------------------------------------------------
# Test 7: unknown --group name → returns 1, does not raise
# ---------------------------------------------------------------------------


def test_cmd_sync_bad_group_returns_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        _PYPROJECT_WITH_UPSTREAM,
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    rc = sync_cmd.cmd_sync(_ns(group="nonexistent"))
    assert rc == 1
