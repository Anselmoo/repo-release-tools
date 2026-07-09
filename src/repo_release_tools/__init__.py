"""repo-release-tools package."""

__version__ = "1.11.1"

INDEX_DOC = """# repo-release-tools

`repo-release-tools` has three main surfaces:

- **[Generated CLI reference](/repo-release-tools/commands/rrt-cli/)** for local release
  automation, Git helpers, config inspection, and the bundled `rrt skill install` command
- **[GitHub Action](/repo-release-tools/action/)** for CI policy checks that mirror the
  local workflow
- **Generated topic docs**:
  [Semantic branches](/repo-release-tools/commands/branch/) and
  [rrt git](/repo-release-tools/commands/git_cmd/) for the branch naming model and Git
  workflow guidance

If you need command syntax, start with the generated CLI reference first. It is
the canonical home for the current `rrt` command surface.

## Start here

- [Generated CLI reference](/repo-release-tools/commands/rrt-cli/) — generated reference for
  branches, bumps, Git workflow helpers, config checks, and skill installation
- [GitHub Action](/repo-release-tools/action/) — CI checks for branch names, commit
  subjects, changelog policy, and optional doctor/dirty-tree gates
- [pre-commit / lefthook](/repo-release-tools/commands/hooks/) — local hook setup for
  incremental or squash-based changelog workflows
- [Skills](/repo-release-tools/commands/skill/) — bundled `uvx` and installed-CLI agent skills

## Then follow the workflow

- [Semantic branches](/repo-release-tools/commands/branch/) — generated branch naming model
  and allowed branch types
- [rrt git](/repo-release-tools/commands/git_cmd/) — generated Git helpers and workflow
  shortcuts

## Changelog workflow

`repo-release-tools` supports two changelog styles:

- `incremental` *(default)* — maintain changelog state during development
- `squash` — skip per-commit changelog enforcement and generate or correct
  changelog entries when changes are squashed together

If you are unsure where to start:

1. Read [the CLI reference](/repo-release-tools/commands/rrt-cli/) to confirm the available
   CLI commands and `changelog_workflow` config
2. Read [the hooks guide](/repo-release-tools/commands/hooks/) for the matching local hook
   setup
3. Read [the GitHub Action guide](/repo-release-tools/action/) to see how
   `changelog-strategy: auto` follows that workflow in CI
"""

# Ordered source-owned topic docs for docs generation.
SOURCE_OWNED_TOPIC_DOCS: tuple[tuple[str, str], ...] = (("index", INDEX_DOC),)
