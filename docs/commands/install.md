---
title: "rrt install"
permalink: "/commands/install/"
---
<!-- rrt:auto:start:page-header -->
[![GitHub](../assets/badges/github.svg)](https://github.com/Anselmoo/repo-release-tools)
<!-- rrt:auto:end:page-header -->


# rrt install

Install bundled rrt user workflow surfaces into local/global tool roots.

## Overview

`rrt install` provides a unified, top-level entrypoint for the existing
specialized installer surfaces:

- `skill install`
- `agents install`
- `hooks install`

It is designed to simplify the initial setup and maintenance of the agentic
workflow tools by allowing users to install all (or a subset of) surfaces
into one or more target destinations in a single operation.

## Responsibilities

- coordinate the installation of multiple surface types (skills, agents, hooks)
- validate target compatibility across all requested surfaces
- provide a consistent dry-run experience for multi-surface installation
- manage local and global tool root discovery

## Target roots

Supported local/global roots include:

- **Claude**: `./.claude` (local) and `~/.claude` (global)
- **Codex**: `./.codex` (local) and `~/.codex` (global)
- **Copilot**: `./.github` (local) and `~/.copilot` (global)
- **Gemini**: `./.gemini` (local) and `~/.gemini` (global)

Each surface appends its own standardized subdirectory (e.g., `skills`,
`agents`, or `hooks`) using the internal per-surface logic.

## Behavior

- If `--surface` is omitted, all bundled surfaces are installed.
- Accepts multiple `--target` values to support parallel installation into
  different tools or both local and global roots.
- Respects `--force` to overwrite existing files across all selected surfaces.
- Supports `--dry-run` to preview the entire installation plan without modifying
  any files.
- Exits with an error if any requested target is unsupported by a selected
  surface.

## Examples

- `rrt install --target claude-local`
- `rrt install --surface skill --target copilot-local`
- `rrt install --surface agents --surface hooks --target codex-global --dry-run`
- `rrt install --target gemini-local --target gemini-global --force`

## Caveats

- Without `--target`, the command prints available destinations in dry-run
  mode and otherwise fails.
- The installation is additive by default; existing files are only replaced
  when `--force` is explicitly passed.

<!-- rrt:auto:start:doc-footer -->
---

[↑ Docs index](https://github.com/Anselmoo/repo-release-tools/blob/main/docs/index.md) · [CLI reference](https://github.com/Anselmoo/repo-release-tools/blob/main/docs/commands/rrt-cli.md) · [Changelog](https://github.com/Anselmoo/repo-release-tools/blob/main/CHANGELOG.md) · [GitHub](https://github.com/Anselmoo/repo-release-tools)
<!-- rrt:auto:end:doc-footer -->
