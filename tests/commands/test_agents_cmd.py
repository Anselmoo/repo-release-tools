from __future__ import annotations

import argparse
from argparse import Namespace
from pathlib import Path

import pytest

from repo_release_tools.commands.agents_cmd import (
    _dedupe_targets,
    _display_path,
    _resolve_install_plan,
    cmd_install,
    main,
    register,
)
from repo_release_tools.integrations.agent_assets import BUNDLED_AGENTS, _parse_family

EXPECTED_AGENT_NAMES = {
    "rrt-user-bootstrap",
    "rrt-user-version-planner",
    "rrt-user-release-readiness",
    "rrt-user-branch-guard",
    "rrt-user-commit-lint-triage",
    "rrt-user-changelog-curator",
    "rrt-user-config-validator",
    "rrt-user-docs-sync-auditor",
    "rrt-user-ci-failure-triage",
    "rrt-user-upgrade-assistant",
}


def _mock_home(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    monkeypatch.setattr("repo_release_tools.commands.agents_cmd.Path.home", lambda: home)


def test_bundled_agents_match_checked_in_agent_files() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    for agent in BUNDLED_AGENTS:
        checked_in = repo_root / ".github" / "agents" / f"{agent.name}.agent.md"
        assert checked_in.read_text(encoding="utf-8") == agent.markdown.rstrip() + "\n"


def test_bundled_agents_contains_expected_names() -> None:
    assert {agent.name for agent in BUNDLED_AGENTS} == EXPECTED_AGENT_NAMES


def test_cmd_install_writes_local_agents(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    monkeypatch.chdir(tmp_path)
    _mock_home(monkeypatch, home)
    args = Namespace(targets=["claude-local"], dry_run=False, force=False)

    result = cmd_install(args)

    assert result == 0
    agents_dir = tmp_path / ".claude" / "agents"
    for agent in BUNDLED_AGENTS:
        installed = agents_dir / f"{agent.name}.agent.md"
        assert installed.exists()
        assert installed.read_text(encoding="utf-8") == agent.markdown.rstrip() + "\n"


def test_cmd_install_dry_run_does_not_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    monkeypatch.chdir(tmp_path)
    _mock_home(monkeypatch, home)
    args = Namespace(targets=["claude-local"], dry_run=True, force=False)

    result = cmd_install(args)

    assert result == 0
    assert not (tmp_path / ".claude" / "agents").exists()


def test_cmd_install_no_targets_dry_run_shows_available(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _mock_home(monkeypatch, tmp_path / "home")
    args = Namespace(targets=None, dry_run=True, force=False)

    result = cmd_install(args)

    assert result == 0
    out = capsys.readouterr().out
    assert "claude-local" in out


def test_cmd_install_no_targets_without_dry_run_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    _mock_home(monkeypatch, tmp_path / "home")
    args = Namespace(targets=None, dry_run=False, force=False)

    result = cmd_install(args)

    assert result == 1


def test_cmd_install_refuses_existing_agent_without_force(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    monkeypatch.chdir(tmp_path)
    _mock_home(monkeypatch, home)

    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    existing = agents_dir / "rrt-user-bootstrap.agent.md"
    existing.write_text("existing content", encoding="utf-8")

    args = Namespace(targets=["claude-local"], dry_run=False, force=False)
    result = cmd_install(args)

    assert result == 1
    assert existing.read_text(encoding="utf-8") == "existing content"


def test_cmd_install_force_overwrites_existing_agent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    monkeypatch.chdir(tmp_path)
    _mock_home(monkeypatch, home)

    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    existing = agents_dir / "rrt-user-bootstrap.agent.md"
    existing.write_text("old content", encoding="utf-8")

    args = Namespace(targets=["claude-local"], dry_run=False, force=True)
    result = cmd_install(args)

    first_agent = next(agent for agent in BUNDLED_AGENTS if agent.name == "rrt-user-bootstrap")
    assert result == 0
    assert existing.read_text(encoding="utf-8") == first_agent.markdown.rstrip() + "\n"


def test_cmd_install_global_target_uses_home_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    monkeypatch.chdir(
        tmp_path / "workspace" if (tmp_path / "workspace").mkdir() or True else tmp_path,
    )
    _mock_home(monkeypatch, home)
    args = Namespace(targets=["claude-global"], dry_run=False, force=False)

    result = cmd_install(args)

    assert result == 0
    agents_dir = home / ".claude" / "agents"
    for agent in BUNDLED_AGENTS:
        assert (agents_dir / f"{agent.name}.agent.md").exists()


def test_cmd_install_returns_one_for_os_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    monkeypatch.chdir(tmp_path)
    _mock_home(monkeypatch, home)

    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    blocker = agents_dir / "rrt-user-bootstrap.agent.md"
    blocker.mkdir()

    args = Namespace(targets=["claude-local"], dry_run=False, force=True)
    result = cmd_install(args)

    assert result == 1


def test_dedupe_targets_preserves_order_and_drops_duplicates() -> None:
    result = _dedupe_targets(["claude-local", "codex-local", "claude-local"])
    assert result == ["claude-local", "codex-local"]


def test_display_path_uses_cwd_home_and_absolute(tmp_path: Path) -> None:
    cwd = tmp_path / "project"
    home = tmp_path / "home"
    local_path = cwd / ".claude" / "agents" / "foo.agent.md"
    home_path = home / ".claude" / "agents" / "foo.agent.md"
    abs_path = tmp_path / "other" / "foo.agent.md"

    assert _display_path(local_path, cwd=cwd, home=home) == ".claude/agents/foo.agent.md"
    assert _display_path(home_path, cwd=cwd, home=home) == "~/.claude/agents/foo.agent.md"
    assert _display_path(abs_path, cwd=cwd, home=home) == str(abs_path)


def test_resolve_install_plan_uses_target_mappings(tmp_path: Path) -> None:
    cwd = tmp_path / "project"
    home = tmp_path / "home"
    plan = _resolve_install_plan(
        ["claude-local", "codex-global", "copilot-local", "gemini-global"],
        cwd=cwd,
        home=home,
    )
    target_names = [target for target, _ in plan]
    assert target_names == ["claude-local", "codex-global", "copilot-local", "gemini-global"]
    dirs = dict(plan)
    assert dirs["claude-local"] == cwd / ".claude" / "agents"
    assert dirs["codex-global"] == home / ".codex" / "agents"
    assert dirs["copilot-local"] == cwd / ".github" / "agents"
    assert dirs["gemini-global"] == home / ".gemini" / "agents"


def test_register_adds_agents_install_parser() -> None:
    main_parser = argparse.ArgumentParser()
    subparsers = main_parser.add_subparsers(dest="command")
    register(subparsers)

    args = main_parser.parse_args(["agents", "install", "--target", "claude-local"])
    assert args.targets == ["claude-local"]
    assert not args.dry_run
    assert not args.force
    assert args.handler is cmd_install


def test_main_executes_install_and_exits_zero(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    monkeypatch.chdir(tmp_path)
    _mock_home(monkeypatch, home)
    monkeypatch.setattr(
        "sys.argv",
        ["rrt-agents", "install", "--target", "claude-local", "--dry-run"],
    )

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 0


# ---------------------------------------------------------------------------
# _parse_family edge cases
# ---------------------------------------------------------------------------


def test_parse_family_empty_markdown_returns_none() -> None:
    assert _parse_family("") is None


def test_parse_family_frontmatter_with_family_key() -> None:
    md = "---\nfamily: rrt-user\ntitle: My Agent\n---\n# body"
    assert _parse_family(md) == "rrt-user"


def test_parse_family_unclosed_frontmatter_falls_back_to_scan() -> None:
    # Frontmatter opened but never closed → ValueError, end=None, then fallback scan
    md = "---\nfamily: scan-family\ntitle: no closing"
    assert _parse_family(md) == "scan-family"


def test_parse_family_fallback_scan_finds_family_line() -> None:
    md = "# Heading\nsome content\nfamily: fallback-fam\nmore content"
    assert _parse_family(md) == "fallback-fam"


def test_parse_family_no_family_returns_none() -> None:
    md = "# Just a heading\nNo family info here."
    assert _parse_family(md) is None


# ---------------------------------------------------------------------------
# --agent filter in cmd_install
# ---------------------------------------------------------------------------


def test_cmd_install_agent_filter_selects_named_agent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    monkeypatch.chdir(tmp_path)
    _mock_home(monkeypatch, home)
    args = Namespace(
        targets=["claude-local"], dry_run=True, force=False, agents=[BUNDLED_AGENTS[0].name]
    )

    result = cmd_install(args)

    assert result == 0


def test_cmd_install_agent_filter_unknown_agent_returns_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    monkeypatch.chdir(tmp_path)
    _mock_home(monkeypatch, home)
    args = Namespace(targets=["claude-local"], dry_run=False, force=False, agents=["no-such-agent"])

    result = cmd_install(args)

    assert result == 1


def test_cmd_install_agent_filter_with_family_expands_family(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    monkeypatch.chdir(tmp_path)
    _mock_home(monkeypatch, home)
    family_agent = next((a for a in BUNDLED_AGENTS if a.family is not None), None)
    if family_agent is None:
        pytest.skip("no bundled agents with a family")
    args = Namespace(
        targets=["claude-local"], dry_run=True, force=False, agents=[family_agent.name]
    )

    result = cmd_install(args)

    assert result == 0


def test_cmd_install_agent_filter_no_family_selects_single(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Cover the else branch (line 166) for an agent with family=None."""
    import repo_release_tools.commands.agents_cmd as agents_cmd_mod
    from repo_release_tools.integrations.agent_assets import BundledAgent

    solo = BundledAgent(name="solo-agent", markdown="# Solo\n", family=None)
    monkeypatch.setattr(agents_cmd_mod, "BUNDLED_AGENTS", [solo])

    home = tmp_path / "home"
    monkeypatch.chdir(tmp_path)
    _mock_home(monkeypatch, home)
    args = Namespace(targets=["claude-local"], dry_run=True, force=False, agents=["solo-agent"])

    result = cmd_install(args)

    assert result == 0
