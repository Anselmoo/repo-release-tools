---
title: "rrt skill"
permalink: "/commands/skill/"
---
<!-- rrt:auto:start:page-header -->
[![GitHub](../assets/badges/github.svg)](https://github.com/Anselmoo/repo-release-tools)
<!-- rrt:auto:end:page-header -->


# rrt skill

This repository bundles ten user workflow skills:

- `rrt-user-bootstrap`
- `rrt-user-versioning`
- `rrt-user-release-flow`
- `rrt-user-branch-strategy`
- `rrt-user-commit-quality`
- `rrt-user-changelog-automation`
- `rrt-user-docs-consistency`
- `rrt-user-config-safety`
- `rrt-user-ci-readiness`
- `rrt-user-migration-uvx-to-installed`

If you need the exact CLI syntax for branch, Git, or skill commands, use the
[rrt CLI reference](rrt-cli.md) first.

## What the skill bundle covers

Use this bundle when you want shipped help for setup, versioning, release flow,
branch naming, commit quality, changelog automation, docs consistency, config
safety, CI readiness, and migration from `uvx` to installed workflows.

## Installing the bundled user skills

Install into one or more agent skill locations with:

```bash
rrt skill install --target copilot-local
rrt skill install --target claude-local --target codex-local
rrt skill install --target copilot-global --dry-run
rrt skill install --target codex-global --force
```

Supported targets:

| Target | Directory |
|---|---|
| `copilot-local` | `.github/skills` |
| `claude-local` | `.claude/skills` |
| `codex-local` | `.codex/skills` |
| `copilot-global` | `~/.copilot/skills` |
| `claude-global` | `~/.claude/skills` |
| `codex-global` | `~/.codex/skills` |
| `gemini-local` | `.gemini/skills` |
| `gemini-global` | `~/.gemini/skills` |

The installer writes one directory per bundled skill. It refuses to overwrite an
existing skill directory unless you pass `--force`. Use `--dry-run` to preview
the destination paths first.

## Related docs

- [rrt CLI](rrt-cli.md)
- [pre-commit / lefthook](hooks.md)
- [GitHub Action](action.md)
- [rrt git](git_cmd.md)

## Install surfaces

- Claude: `./.claude/skills` and `~/.claude/skills`
- Codex: `./.codex/skills` and `~/.codex/skills`
- Gemini: `./.gemini/skills` and `~/.gemini/skills`
- Copilot: `./.github/skills` and `~/.copilot/skills`

<!-- rrt:auto:start:doc-footer -->
---

[↑ Docs index](https://github.com/Anselmoo/repo-release-tools/blob/main/docs/index.md) · [CLI reference](https://github.com/Anselmoo/repo-release-tools/blob/main/docs/commands/rrt-cli.md) · [Changelog](https://github.com/Anselmoo/repo-release-tools/blob/main/CHANGELOG.md) · [GitHub](https://github.com/Anselmoo/repo-release-tools)
<!-- rrt:auto:end:doc-footer -->
