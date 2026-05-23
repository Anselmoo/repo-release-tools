---
title: "rrt drift"
permalink: "/commands/drift/"
---
<!-- rrt:auto:start:page-header -->
<a href="https://github.com/Anselmoo/repo-release-tools"><picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/badges/github-reto-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="../assets/badges/github-reto-light.svg">
  <img alt="GitHub" src="../assets/badges/github-reto-dark.svg">
</picture></a>
<!-- rrt:auto:end:page-header -->


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

<!-- rrt:auto:start:doc-footer -->
---

[↑ Docs index](https://github.com/Anselmoo/repo-release-tools/blob/main/docs/index.md) · [CLI reference](https://github.com/Anselmoo/repo-release-tools/blob/main/docs/commands/rrt-cli.md) · [Changelog](https://github.com/Anselmoo/repo-release-tools/blob/main/CHANGELOG.md) · [GitHub](https://github.com/Anselmoo/repo-release-tools)
<!-- rrt:auto:end:doc-footer -->
