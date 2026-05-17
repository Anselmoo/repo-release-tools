---
title: "rrt git"
permalink: "/commands/git_cmd/"
---
<!-- rrt:auto:start:page-header -->
[![GitHub](../assets/badges/github.svg)](https://github.com/Anselmoo/repo-release-tools)
<!-- rrt:auto:end:page-header -->


# rrt git

Git workflow helpers for repository status, commit, sync, and history operations.

## Overview

`repo-release-tools` ships a small set of opinionated Git workflows for branch
health, commit drafting, sync, and history repair. The tool group favors compact,
human-readable summaries with explicit safety checks before any destructive
operation.

Most commands are designed to run from a Git work tree and emit a short
summary first, followed by the details needed to act on the result.

## Workflow map

- **Inspect**: `rrt git status`, `diff`, `log`, `doctor`, `sync-status`,
  `check-dirty-tree`
- **Draft commits**: `rrt git commit`, `commit-all`, `squash-local`
- **Move and sync**: `rrt git sync`, `move`, `undo-safe`, `rebootstrap`
- **Branch workflows**: `rrt branch new`, `rescue`, `rename`

## Responsibilities

- provide a high-level API for common Git operations used in release flows
- enforce repository policies during commit drafting and branch management
- automate repetitive tasks like auto-stashing during branch switches
- generate human-friendly summaries of repository state and history
- ensure safe operation through dry-run modes and state validation

## Notable behavior

- **Commit Drafting**: `rrt git commit` infers the commit type from the current
  branch only when the branch follows the conventional `type/slug` format.
- **State Management**: `sync` and `move` automatically stash local changes
  before execution and restore them afterward.
- **History Repair**: `undo-safe` and `rebootstrap` provide controlled ways to
  rewrite history, with `rebootstrap` requiring explicit confirmation.
- **Validation**: Refuses to continue in unsafe states, such as unresolved
  conflicts or in-progress merges.

## Examples

- `rrt git status`
- `rrt git commit "refresh help examples"`
- `rrt git sync --dry-run`
- `rrt git squash-local --base-ref origin/main "ship parser"`
- `rrt git rebootstrap --yes-i-know-this-destroys-history --dry-run`

## See also

- [Conventional branches](branch.md)
- [Generated CLI reference](rrt-cli.md)

<!-- rrt:auto:start:doc-footer -->
---

[↑ Docs index](https://github.com/Anselmoo/repo-release-tools/blob/main/docs/index.md) · [CLI reference](https://github.com/Anselmoo/repo-release-tools/blob/main/docs/commands/rrt-cli.md) · [Changelog](https://github.com/Anselmoo/repo-release-tools/blob/main/CHANGELOG.md) · [GitHub](https://github.com/Anselmoo/repo-release-tools)
<!-- rrt:auto:end:doc-footer -->
