---
title: "rrt branch"
permalink: "/commands/branch/"
---
<!-- rrt:auto:start:page-header -->
<p><a href="https://github.com/Anselmoo/repo-release-tools"><picture>
  <source media="(prefers-color-scheme: dark)" srcset="/repo-release-tools/assets/badges/github-reto-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="/repo-release-tools/assets/badges/github-reto-light.svg">
  <img alt="GitHub" src="/repo-release-tools/assets/badges/github-reto-dark.svg">
</picture></a></p>
<!-- rrt:auto:end:page-header -->


# rrt branch

Branch command helpers and utilities for conventional branches.

## Overview

The `rrt branch` command family provides a suite of helpers for managing
semantic, conventionally-named Git branches. By enforcing a consistent naming
structure—such as `feat/add-parser` or `fix/config-loader`—the tool ensures
that the repository's branch history remains searchable, readable, and
aligned with standard `conventional-commits` policies.

These helpers are particularly useful for teams practicing trunk-based
development, where branch names often serve as the primary signal for
automated release notes and CI workflow routing.

## Responsibilities

- validate branch names against project-specific prefix and slug rules
- scaffold new branches using the canonical `<type>/<kebab-slug>` format
- automate the renaming of branches while preserving description context
- "rescue" uncommitted work or divergent commits into new, semantic branches
- provide actionable suggestions when a branch name violates repository policy

## Standard Format

```text
<type>/[<scope>-]<kebab-case-description>
```

Example branches:
- `feat/add-config-discovery`
- `fix/handle-tag-workflows`
- `docs/split-readme-into-docs`

## Built-in branch types

Conventional branch types are accepted out of the box:
- `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `ci`, `perf`, `style`, `build`

## Special names

These branch names are also valid:
- `main`, `master`, `develop`
- `release/v<semver>` (validated as a semver-aware special case)

## AI helper and Bot branches

Branches created by assistant-driven workflows or dependency bots are accepted with these prefixes:
- `claude/...`, `codex/...`, `copilot/...`
- `dependabot/...`, `renovate/...`

Custom prefixes can be added via the `extra_branch_types` config key.

## Behavior

- **new**: Creates and switches to a new branch. Moves dirty changes if requested.
- **rename**: Rebuilds the current branch name based on new type, scope, or description.
- **rescue**: Moves commits ahead of upstream to a fresh semantic branch.
- **dry-run**: Previews all Git operations without modifying the repository.

## Examples

- `rrt branch new feat "add parser"`
- `rrt branch new fix "repair config loader" --scope api`
- `rrt branch rename --type fix --scope api "fix config loader"`
- `rrt branch rescue feat "rescue work in progress"`

## Caveats

- Branch slugs are limited to 60 characters by default.
- Custom branch types can be added via configuration.

<!-- rrt:auto:start:doc-footer -->
---

[↑ Docs index](https://github.com/Anselmoo/repo-release-tools/blob/main/docs/index.md) · [CLI reference](https://github.com/Anselmoo/repo-release-tools/blob/main/docs/commands/rrt-cli.md) · [Changelog](https://github.com/Anselmoo/repo-release-tools/blob/main/CHANGELOG.md) · [GitHub](https://github.com/Anselmoo/repo-release-tools)
<!-- rrt:auto:end:doc-footer -->
