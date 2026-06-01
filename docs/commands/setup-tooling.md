---
title: "rrt Setup & Tooling"
permalink: "/commands/setup-tooling/"
---
<!-- rrt:auto:start:page-header -->
<p><a href="https://github.com/Anselmoo/repo-release-tools"><picture>
  <source media="(prefers-color-scheme: dark)" srcset="../../assets/badges/github-reto-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="../../assets/badges/github-reto-light.svg">
  <img alt="GitHub" src="../../assets/badges/github-reto-dark.svg">
</picture></a></p>
<!-- rrt:auto:end:page-header -->


# rrt Setup & Tooling

<!-- Auto-generated from repo_release_tools.cli.build_parser(); run `rrt docs publish` to refresh. -->

<!-- rrt:auto:start:toc -->
- [`rrt install`](#rrt-install)
  - [Overview](#overview)
  - [Responsibilities](#responsibilities)
  - [Target roots](#target-roots)
  - [Behavior](#behavior)
  - [Examples](#examples)
  - [Caveats](#caveats)
- [`rrt init`](#rrt-init)
  - [Overview](#overview-1)
  - [Responsibilities](#responsibilities-1)
  - [Target Surfaces](#target-surfaces)
  - [Behavior](#behavior-1)
  - [Examples](#examples-1)
  - [Caveats](#caveats-1)
- [`rrt skill`](#rrt-skill)
  - [Overview](#overview-2)
  - [Target surfaces](#target-surfaces-1)
  - [Behavior](#behavior-2)
  - [Examples](#examples-2)
  - [Caveats](#caveats-2)
  - [`rrt skill install`](#rrt-skill-install)
- [`rrt agents`](#rrt-agents)
  - [Overview](#overview-3)
  - [Target surfaces](#target-surfaces-2)
  - [Behavior](#behavior-3)
  - [Examples](#examples-3)
  - [Caveats](#caveats-3)
  - [`rrt agents install`](#rrt-agents-install)
- [`rrt hooks`](#rrt-hooks)
  - [Overview](#overview-4)
  - [Target surfaces](#target-surfaces-3)
  - [Behavior](#behavior-4)
  - [Examples](#examples-4)
  - [Caveats](#caveats-4)
  - [`rrt hooks install`](#rrt-hooks-install)
<!-- rrt:auto:end:toc -->

## `rrt install`

Install bundled rrt user workflow surfaces into local/global tool roots.

### Overview

`rrt install` provides a unified, top-level entrypoint for the existing
specialized installer surfaces:

- `skill install`
- `agents install`
- `hooks install`

It is designed to simplify the initial setup and maintenance of the agentic
workflow tools by allowing users to install all (or a subset of) surfaces
into one or more target destinations in a single operation.

### Responsibilities

- coordinate the installation of multiple surface types (skills, agents, hooks)
- validate target compatibility across all requested surfaces
- provide a consistent dry-run experience for multi-surface installation
- manage local and global tool root discovery

### Target roots

Supported local/global roots include:

- **Claude**: `./.claude` (local) and `~/.claude` (global)
- **Codex**: `./.codex` (local) and `~/.codex` (global)
- **Copilot**: `./.github` (local) and `~/.copilot` (global)
- **Gemini**: `./.gemini` (local) and `~/.gemini` (global)

Each surface appends its own standardized subdirectory (e.g., `skills`,
`agents`, or `hooks`) using the internal per-surface logic.

### Behavior

- If `--surface` is omitted, all bundled surfaces are installed.
- Accepts multiple `--target` values to support parallel installation into
  different tools or both local and global roots.
- Respects `--force` to overwrite existing files across all selected surfaces.
- Supports `--dry-run` to preview the entire installation plan without modifying
  any files.
- Exits with an error if any requested target is unsupported by a selected
  surface.

### Examples

- `rrt install --target claude-local`
- `rrt install --surface skill --target copilot-local`
- `rrt install --surface agents --surface hooks --target codex-global --dry-run`
- `rrt install --target gemini-local --target gemini-global --force`

### Caveats

- Without `--target`, the command prints available destinations in dry-run
  mode and otherwise fails.
- The installation is additive by default; existing files are only replaced
  when `--force` is explicitly passed.

```text
Usage:  rrt install [OPTIONS]

Install one or more bundled rrt agent surfaces (skill, agents, hooks) into one or more local/global targets.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help         Show this message and exit.
  --surface SURFACE  Surface to install. Repeat for multiple values. Defaults to all: skill, agents, hooks.
  --target DEST      Install target. Repeat to install into multiple locations. Use --dry-run with no targets to inspect supported values.
  --dry-run          Preview without writing files.
  --force            Overwrite existing installed files.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt install --target claude-local
  $ rrt install --surface skill --target copilot-local
  $ rrt install --surface agents --surface hooks --target codex-global --dry-run
```

## `rrt init`

Initialize repo-release-tools configuration for a repository.

### Overview

`rrt init` provides a streamlined onboarding experience for new repositories.
It generates a recommended starter configuration tailored to the project's
language and structure, allowing developers to quickly adopt standard release
and documentation workflows.

The command can either create a standalone `.rrt.toml` file—which is the
preferred method for most projects—or merge the configuration into existing
project manifests like `pyproject.toml`, `Cargo.toml`, or `package.json`.

### Responsibilities

- discover the repository root and identify the primary project language
- generate high-quality, documented starter configurations for multiple targets
- provide language-specific recommendations (e.g., Python, Node.js, Go, Rust)
- ensure safe initialization with dry-run and overwrite protections
- guide the user through the configuration discovery process

### Target Surfaces

- **.rrt.toml** (default): Creates a new, standalone configuration file with
  rich comments and recommended defaults for generic or multi-language projects.
- **pyproject.toml**: Appends a `[tool.rrt]` section to the Python project
  manifest.
- **Cargo.toml**: Appends a `[package.metadata.rrt]` section to the Rust
  crate manifest.
- **package.json**: Merges an `"rrt"` key into the Node.js project manifest.
- **go**: Generates a `.rrt.toml` file pre-configured with Go-oriented
  version targets and release patterns.

### Behavior

- **Safety**: Refuses to overwrite an existing configuration unless `--force`
  is explicitly provided.
- **Discovery**: Warns the user if an existing configuration is found in a
  different location (e.g., if `.rrt.toml` is created but `pyproject.toml`
  already has an `rrt` section).
- **Templates**: Uses internal recommendation engines to populate the starter
  config with sensible `version_targets`, `changelog_file`, and `release_branch`
  patterns.
- **Preview**: Supports `--dry-run` to show the exact content and target path
  before any changes are made.

### Examples

- `rrt init`
- `rrt init --dry-run`
- `rrt init --target pyproject`
- `rrt init --target node --force`
- `rrt init --target go`
- `rrt init --target cargo --dry-run`

### Caveats

- For `pyproject.toml` and `Cargo.toml`, the command only appends to existing
  files; it will not create the manifest if it is missing.
- Standalone `.rrt.toml` files take precedence over manifest-embedded
  configurations during standard tool discovery.

```text
Usage:  rrt init [OPTIONS]

Generate a starter rrt configuration for the current repository or manifest.

By default this writes .rrt.toml. Use --target to append or merge equivalent configuration into pyproject.toml, Cargo.toml, package.json, or a Go-oriented .rrt.toml template.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help       Show this message and exit.
  --dry-run        Preview without writing files.
  --force          Overwrite an existing .rrt.toml or package.json "rrt" key when writing those targets.
  --target FORMAT  Where to write the rrt configuration. rrt-toml (default): write .rrt.toml; pyproject: append [tool.rrt] to pyproject.toml; cargo: append [package.metadata.rrt] to Cargo.toml; node: merge or replace the "rrt" key in package.json; go: write .rrt.toml with the recommended Go template.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt init --dry-run
  $ rrt init --target pyproject
  $ rrt init --target node --force
  $ rrt init --target go
```

## `rrt skill`

Install bundled rrt user workflow skills.

### Overview

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

### Target surfaces

The install command can write to local or global skill roots for:

- Claude: `.claude/skills`
- Codex: `.codex/skills`
- Copilot: `.github/skills` (local), `~/.copilot/skills` (global)
- Gemini: `.gemini/skills`

Each target receives one directory per bundled skill, each containing a
`SKILL.md`.

### Behavior

- Accepts one or more `--target` values; duplicates are ignored after first use.
- Resolves local targets relative to the current working directory and global
  targets relative to the home directory.
- Refuses to overwrite an existing skill directory unless `--force` is provided.
- Supports `--dry-run` previews that show the resolved destination paths
  without writing files.

### Examples

- `rrt skill install --target copilot-local`
- `rrt skill install --target claude-local --target codex-local`
- `rrt skill install --target gemini-local`
- `rrt skill install --target copilot-global --force --dry-run`

### Caveats

- `rrt skill` requires a subcommand; use `rrt skill install ...`.
- Without `--target`, the command prints available destinations in dry-run
  mode and otherwise fails.
- Existing symlinks, files, or directories at the destination are replaced
  only when `--force` is used.

```text
Usage:  rrt skill [OPTIONS] <skill_command>

Install the bundled rrt user workflow skills.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  install     Install bundled rrt user skills into agent skill directories.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help  Show this message and exit.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt skill install --target copilot-local
  $ rrt skill install --target claude-local --target codex-local
  $ rrt skill install --target gemini-local
```

### `rrt skill install`

```text
Usage:  rrt skill install [OPTIONS]

Install the bundled rrt user skills into one or more local or global agent skill directories.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help     Show this message and exit.
  --target DEST  Install target. Repeat to install into multiple locations: copilot-local, claude-local, codex-local, gemini-local, copilot-global, claude-global, codex-global, gemini-global.
  --dry-run      Preview without writing files.
  --force        Overwrite existing installed skill directories.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt skill install --target copilot-local
  $ rrt skill install --target claude-local --target codex-local
  $ rrt skill install --target copilot-global --force --dry-run
  $ rrt skill install --target gemini-global
```

## `rrt agents`

Install bundled rrt user agent definitions (.agent.md files).

### Overview

`rrt agents` manages installation of the packaged user-facing agent definitions
into tool-specific agent directories. The only implemented subcommand is `install`.

### Target surfaces

The install command can write to local or global agent roots for:

- Claude: `.claude/agents`
- Codex: `.codex/agents`
- Copilot: `.github/agents` (local), `~/.copilot/agents` (global)
- Gemini: `.gemini/agents`

Each target receives one flat `.agent.md` file per bundled user agent.

### Behavior

- Accepts one or more `--target` values; duplicates are ignored after first use.
- Resolves local targets relative to the current working directory and global
  targets relative to the home directory.
- Refuses to overwrite an existing file unless `--force` is provided.
- Supports `--dry-run` previews that show the resolved destination paths
  without writing files.

### Examples

- `rrt agents install --target claude-local`
- `rrt agents install --target claude-local --target codex-local`
- `rrt agents install --target claude-global --force`
- `rrt agents install --dry-run`

### Caveats

- `rrt agents` requires a subcommand; use `rrt agents install ...`.
- Without `--target`, the command prints available destinations in dry-run
  mode and otherwise fails.
- Existing files at the destination are replaced only when `--force` is used.

```text
Usage:  rrt agents [OPTIONS] <agents_command>

Install bundled rrt user agents into one or more local or global agent directories.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  install     Install bundled rrt user agents into agent directories.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help  Show this message and exit.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt agents install --target claude-local
  $ rrt agents install --target claude-local --target codex-local
  $ rrt agents install --target copilot-local
  $ rrt agents install --target claude-global --force
```

### `rrt agents install`

```text
Usage:  rrt agents install [OPTIONS]

Install bundled .agent.md user agents into one or more local or global agent directories.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help     Show this message and exit.
  --target DEST  Install target. Repeat to install into multiple locations: claude-local, claude-global, codex-local, codex-global, copilot-local, copilot-global, gemini-local, gemini-global.
  --agent AGENT  Install a specific agent by name. When the agent declares a `family:` metadata, the entire family will be installed. Repeat for multiple agents.
  --dry-run      Preview without writing files.
  --force        Overwrite existing agent files.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt agents install --target claude-local
  $ rrt agents install --target claude-local --target codex-local
  $ rrt agents install --target gemini-local
  $ rrt agents install --target claude-global --force --dry-run
  $ rrt agents install --target copilot-global
```

## `rrt hooks`

Install bundled rrt user workflow hook scripts and register them automatically.

### Overview

`rrt hooks` manages installation of the packaged user-facing hook scripts into
tool-specific hook directories and writes managed hook-registration config for
the selected surface. The only implemented subcommand is `install`.

### Target surfaces

The install command can write to local or global hook roots for:

- Claude: `.claude/hooks`
- Codex: `.codex/hooks`
- Copilot: `.github/hooks` (local), `~/.copilot/hooks` (global)
- Gemini: `.gemini/hooks`

Each target receives the same bundled `.py` hook scripts for user-facing `rrt`
workflow checks and a managed hook-registration file in the surface's native
JSON format.

### Behavior

- Accepts one or more `--target` values; duplicates are ignored after first use.
- Resolves local targets relative to the current working directory.
- Refuses to overwrite an existing script file unless `--force` is provided.
- Supports `--dry-run` previews that show the resolved destination paths
    without writing files.
- Merges managed hook registrations additively, preserving unrelated settings.

### Examples

- `rrt hooks install --target claude-local`
- `rrt hooks install --target claude-local --force`
- `rrt hooks install --dry-run`

### Caveats

- `rrt hooks` requires a subcommand; use `rrt hooks install ...`.
- Without `--target`, the command prints available destinations in dry-run
  mode and otherwise fails.
- Hook registration happens automatically during installation.

```text
Usage:  rrt hooks [OPTIONS] <hooks_command>

Install bundled rrt user workflow hook scripts into one or more local hook directories and update the surface's hook registration JSON.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  install     Install bundled rrt hook scripts into hook directories and register them.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help  Show this message and exit.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt hooks install --target claude-local
  $ rrt hooks install --target codex-local
  $ rrt hooks install --target gemini-local
  $ rrt hooks install --target claude-local --force
```

### `rrt hooks install`

```text
Usage:  rrt hooks install [OPTIONS]

Install bundled rrt user workflow hook .py scripts into one or more local hook directories and update the native hook-registration JSON for that surface.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help     Show this message and exit.
  --target DEST  Install target. Repeat to install into multiple locations: claude-local, claude-global, codex-local, codex-global, copilot-local, copilot-global, gemini-local, gemini-global.
  --dry-run      Preview without writing files.
  --force        Overwrite existing hook files.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt hooks install --target claude-local
  $ rrt hooks install --target claude-local --force --dry-run
  $ rrt hooks install --target codex-global
  $ rrt hooks install --target copilot-local
```

<!-- rrt:auto:start:doc-footer -->
---

[↑ Docs index](https://github.com/Anselmoo/repo-release-tools/blob/main/docs/index.md) · [CLI reference](https://github.com/Anselmoo/repo-release-tools/blob/main/docs/commands/rrt-cli.md) · [Changelog](https://github.com/Anselmoo/repo-release-tools/blob/main/CHANGELOG.md) · [GitHub](https://github.com/Anselmoo/repo-release-tools)
<!-- rrt:auto:end:doc-footer -->
