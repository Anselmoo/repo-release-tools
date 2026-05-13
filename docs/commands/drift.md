---
title: "rrt drift"
permalink: "/commands/drift/"
---

# rrt drift

`rrt drift` locks and checks agent-facing repository surfaces such as Claude
settings, hooks, agent instructions, shared instructions, and bundled skills.

Use `rrt drift generate` to write `.rrt/drift.lock.toml` and `rrt drift check`
to verify that the current surfaces still match the lockfile.

## What it tracks

- `.claude/settings.json`
- `.claude/hooks/*.py`
- `.github/agents/*.agent.md`
- `.github/copilot-instructions.md`
- `.github/instructions/*.md`
- `.github/skills/*/SKILL.md`

## Examples

```text
rrt drift generate --dry-run
rrt drift generate
rrt drift check
```

## See also

- [rrt CLI](rrt-cli.md)
- [GitHub Action](../action.md)
