# repo-release-tools docs

`repo-release-tools` has three main surfaces:

- **[Generated CLI reference](commands/rrt-cli.md)** for local release automation, Git
  helpers, config inspection, and the bundled `rrt skill install` command
- **[GitHub Action](action.md)** for CI policy checks that mirror the
  local workflow
- **Generated topic docs**:
  [Semantic branches](commands/branch.md) and [Git magic](commands/git_cmd.md) for
  the branch naming model and Git workflow guidance

If you need command syntax, start with the generated CLI reference first. It is
the canonical home for the current `rrt` command surface.

## Start here

- [Generated CLI reference](commands/rrt-cli.md) — generated reference for branches, bumps, Git
  workflow helpers, config checks, and skill installation
- [GitHub Action](action.md) — CI checks for branch names, commit
  subjects, changelog policy, and optional doctor/dirty-tree gates
- [pre-commit / lefthook](commands/hooks.md) — local hook setup for incremental or
  squash-based changelog workflows
- [Skills](commands/skill.md) — bundled `uvx` and installed-CLI agent skills

## Then follow the workflow

<!-- rrt:auto:start:index-topic-links -->
- [Semantic branches](commands/branch.md) — generated branch naming model and allowed branch types
- [Git magic](commands/git_cmd.md) — generated Git helpers and workflow shortcuts
- [Project tree](commands/tree.md) — generated guide for `rrt tree` output modes, ignore behavior, and traversal controls
<!-- rrt:auto:end:index-topic-links -->

## Commands reference

The `docs/commands/` directory mirrors `src/repo_release_tools/commands/` and
`src/repo_release_tools/hooks.py`. Each file documents one command module.

| Doc | Module | Status |
|---|---|---|
| [branch](commands/branch.md) | `commands/branch.py` | full |
| [bump](commands/bump.md) | `commands/bump.py` | stub |
| [ci_version](commands/ci_version.md) | `commands/ci_version.py` | stub |
| [config_cmd](commands/config_cmd.md) | `commands/config_cmd.py` | stub |
| [doctor](commands/doctor.md) | `commands/doctor.py` | full |
| [env_cmd](commands/env_cmd.md) | `commands/env_cmd.py` | stub |
| [eol_check](commands/eol_check.md) | `commands/eol_check.py` | full |
| [git_cmd](commands/git_cmd.md) | `commands/git_cmd.py` | full |
| [hooks](commands/hooks.md) | `hooks.py` | full |
| [init](commands/init.md) | `commands/init.py` | stub |
| [rrt-cli](commands/rrt-cli.md) | `cli.py` + all commands | auto-generated |
| [skill](commands/skill.md) | `commands/skill.py` | full |
| [tree](commands/tree.md) | `commands/tree.py` | full |

## Changelog workflow

`repo-release-tools` supports two changelog styles:

- `incremental` *(default)* — maintain changelog state during development
- `squash` — skip per-commit changelog enforcement and generate or correct
  changelog entries when changes are squashed together

If you are unsure where to start:

1. Read [`commands/rrt-cli.md`](commands/rrt-cli.md) to confirm the available CLI commands and
   `changelog_workflow` config
2. Read [`commands/hooks.md`](commands/hooks.md) for the matching local hook setup
3. Read [`action.md`](action.md) to see how
   `changelog-strategy: auto` follows that workflow in CI
