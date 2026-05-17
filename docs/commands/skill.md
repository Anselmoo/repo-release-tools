---
title: "rrt skill"
permalink: "/commands/skill/"
---
<!-- rrt:auto:start:page-header -->
[![GitHub](../assets/badges/github.svg)](https://github.com/Anselmoo/repo-release-tools)
<!-- rrt:auto:end:page-header -->


# rrt skill

Install bundled rrt user workflow skills.

## Overview

`rrt skill` manages installation of the packaged user-facing `rrt` skills into
tool-specific skill directories. The only implemented subcommand is `install`.

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

## Target surfaces

The install command can write to local or global skill roots for:

- Claude: `.claude/skills`
- Codex: `.codex/skills`
- Copilot: `.github/skills` (local), `~/.copilot/skills` (global)
- Gemini: `.gemini/skills`

Each target receives one directory per bundled skill, each containing a
`SKILL.md`.

## Behavior

- Accepts one or more `--target` values; duplicates are ignored after first use.
- Resolves local targets relative to the current working directory and global
  targets relative to the home directory.
- Refuses to overwrite an existing skill directory unless `--force` is provided.
- Supports `--dry-run` previews that show the resolved destination paths
  without writing files.

## Examples

- `rrt skill install --target copilot-local`
- `rrt skill install --target claude-local --target codex-local`
- `rrt skill install --target gemini-local`
- `rrt skill install --target copilot-global --force --dry-run`

## Caveats

- `rrt skill` requires a subcommand; use `rrt skill install ...`.
- Without `--target`, the command prints available destinations in dry-run
  mode and otherwise fails.
- Existing symlinks, files, or directories at the destination are replaced
  only when `--force` is used.

<!-- rrt:auto:start:doc-footer -->
---

[↑ Docs index](https://github.com/Anselmoo/repo-release-tools/blob/main/docs/index.md) · [CLI reference](https://github.com/Anselmoo/repo-release-tools/blob/main/docs/commands/rrt-cli.md) · [Changelog](https://github.com/Anselmoo/repo-release-tools/blob/main/CHANGELOG.md) · [GitHub](https://github.com/Anselmoo/repo-release-tools)
<!-- rrt:auto:end:doc-footer -->
