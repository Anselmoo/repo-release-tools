import argparse
from pathlib import Path
from typing import Any

from repo_release_tools.commands.agents_cmd import cmd_install
from repo_release_tools.integrations.agent_assets import BUNDLED_AGENTS


def test_agent_family_install(tmp_path: Path, monkeypatch: Any) -> None:
    # create a fake repo cwd with .github/agents containing a single agent file
    repo = tmp_path / "repo"
    repo.mkdir()
    gh = repo / ".github" / "agents"
    gh.mkdir(parents=True)
    # pick an agent that has family metadata
    agent = next(a for a in BUNDLED_AGENTS if a.family)
    (gh / f"{agent.name}.agent.md").write_text(agent.markdown)

    monkeypatch.chdir(repo)
    args = argparse.Namespace(
        targets=["claude-local"], dry_run=False, force=True, agents=[agent.name]
    )
    rc = cmd_install(args)
    assert rc == 0
    dst = repo / ".claude" / "agents" / f"{agent.name}.agent.md"
    assert dst.exists()
    # verify family members are also installed
    if agent.family:
        family_members = [a for a in BUNDLED_AGENTS if a.family == agent.family]
        for member in family_members:
            assert (repo / ".claude" / "agents" / f"{member.name}.agent.md").exists()
    # verify agents outside the family are NOT installed (proves --agent filtering worked)
    non_family = [a for a in BUNDLED_AGENTS if a.family != agent.family]
    for non_member in non_family:
        assert not (repo / ".claude" / "agents" / f"{non_member.name}.agent.md").exists()
