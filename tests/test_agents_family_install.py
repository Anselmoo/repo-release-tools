
from repo_release_tools.commands.agents_cmd import cmd_install
from repo_release_tools.integrations.agent_assets import BUNDLED_AGENTS


def test_agent_family_install(tmp_path, monkeypatch, capsys):
    # create a fake repo cwd with .github/agents containing a single agent file
    repo = tmp_path / "repo"
    repo.mkdir()
    gh = repo / ".github" / "agents"
    gh.mkdir(parents=True)
    # pick an agent that has family metadata
    agent = next(a for a in BUNDLED_AGENTS if a.family)
    (gh / f"{agent.name}.agent.md").write_text(agent.markdown)

    # run install targeting claude-local inside the fake repo
    monkeypatch.chdir(repo)
    class Args: pass
    args = Args()
    args.targets = ["claude-local"]
    args.dry_run = False
    args.force = True
    # install
    rc = cmd_install(args)
    assert rc == 0
    # verify file copied to .claude/agents
    dst = repo / ".claude" / "agents" / f"{agent.name}.agent.md"
    assert dst.exists()
    # verify family members are also present
    if agent.family:
        family_members = [a for a in BUNDLED_AGENTS if a.family == agent.family]
        for member in family_members:
            assert (repo / ".claude" / "agents" / f"{member.name}.agent.md").exists()
