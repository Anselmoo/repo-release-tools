"""repo-release-tools package."""

__version__ = "1.1.0"

INDEX_DOC = """# repo-release-tools docs

`repo-release-tools` has three main surfaces:

- **[Generated CLI reference](rrt-cli.md)** for local release automation, Git
  helpers, config inspection, and the bundled `rrt skill install` command
- **[GitHub Action](action.md)** for CI policy checks that mirror the
  local workflow
- **Generated topic docs**:
  [Semantic branches](branch.md) and [Git magic](git.md) for
  the branch naming model and Git workflow guidance

If you need command syntax, start with the generated CLI reference first. It is
the canonical home for the current `rrt` command surface.

## Start here

- [Generated CLI reference](rrt-cli.md) — generated reference for branches, bumps, Git
  workflow helpers, config checks, and skill installation
- [GitHub Action](action.md) — CI checks for branch names, commit
  subjects, changelog policy, and optional doctor/dirty-tree gates
- [pre-commit / lefthook](hooks.md) — local hook setup for incremental or
  squash-based changelog workflows
- [Skills](skill.md) — bundled `uvx` and installed-CLI agent skills

## Then follow the workflow

- [Semantic branches](branch.md) — generated branch naming model
  and allowed branch types
- [Git magic](git.md) — generated Git helpers and workflow shortcuts

## Changelog workflow

`repo-release-tools` supports two changelog styles:

- `incremental` *(default)* — maintain changelog state during development
- `squash` — skip per-commit changelog enforcement and generate or correct
  changelog entries when changes are squashed together

If you are unsure where to start:

1. Read [`rrt-cli.md`](rrt-cli.md) to confirm the available CLI commands and
   `changelog_workflow` config
2. Read [`hooks.md`](hooks.md) for the matching local hook setup
3. Read [`action.md`](action.md) to see how
   `changelog-strategy: auto` follows that workflow in CI
"""

# Ordered source-owned topic docs for docs generation.
SOURCE_OWNED_TOPIC_DOCS: tuple[tuple[str, str], ...] = (("index", INDEX_DOC),)
