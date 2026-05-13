from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from repo_release_tools.commands import install_cmd


def _mock_home(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    monkeypatch.setattr("repo_release_tools.commands.skill.Path.home", lambda: home)
    monkeypatch.setattr("repo_release_tools.commands.agents_cmd.Path.home", lambda: home)
    monkeypatch.setattr("repo_release_tools.commands.hooks_cmd.Path.home", lambda: home)


def test_install_defaults_to_all_surfaces(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    _mock_home(monkeypatch, tmp_path / "home")

    result = install_cmd.cmd_install(
        Namespace(surfaces=None, targets=["claude-local"], dry_run=True, force=False),
    )

    assert result == 0


def test_install_rejects_unsupported_surface_target_combo(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    _mock_home(monkeypatch, tmp_path / "home")

    result = install_cmd.cmd_install(
        Namespace(surfaces=["hooks"], targets=["invalid-target"], dry_run=False, force=False),
    )

    assert result == 1


def test_install_dry_run_without_targets_is_allowed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    _mock_home(monkeypatch, tmp_path / "home")

    result = install_cmd.cmd_install(
        Namespace(surfaces=["skill"], targets=None, dry_run=True, force=False),
    )

    assert result == 0


def test_install_without_targets_errors_when_not_dry_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    _mock_home(monkeypatch, tmp_path / "home")

    result = install_cmd.cmd_install(
        Namespace(surfaces=["skill"], targets=None, dry_run=False, force=False),
    )

    assert result == 1


def test_resolve_surfaces_prefers_all_when_present() -> None:
    assert install_cmd._resolve_surfaces(["all", "skill"]) == ["skill", "agents", "hooks"]


def test_resolve_surfaces_returns_explicit_subset_without_all() -> None:
    assert install_cmd._resolve_surfaces(["skill", "hooks", "skill"]) == ["skill", "hooks"]


def test_install_returns_non_zero_when_surface_handler_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    _mock_home(monkeypatch, tmp_path / "home")

    def _ok(_args: Namespace) -> int:
        return 0

    def _fail(_args: Namespace) -> int:
        return 1

    monkeypatch.setattr(
        install_cmd,
        "_surface_registry",
        lambda: {
            "skill": ({"claude-local": object()}, _ok),
            "agents": ({"claude-local": object()}, _fail),
            "hooks": ({"claude-local": object()}, _ok),
        },
    )

    result = install_cmd.cmd_install(
        Namespace(
            surfaces=["skill", "agents", "hooks"],
            targets=["claude-local"],
            dry_run=False,
            force=False,
        ),
    )

    assert result == 1
