# repo-release-tools docs

`repo-release-tools` has two main entry points:

- **GitHub Action** for CI policy checks
- **Python CLI + hooks** for local release automation

This docs set is organized around those entry points first, then around the
workflow details behind them.

## Start by platform

- [GitHub Action](github-action.md) — CI checks for branch names, commit
	subjects, changelog policy, and optional doctor/dirty-tree gates
- [RRT CLI](rrt-cli.md) — installable or `uvx`-driven local commands for
	branches, bumps, config inspection, and Git helpers
- [pre-commit / lefthook](pre-commit.md) — local hook setup for incremental or
	squash-based changelog workflows

## Start by workflow

- [Conventional branches](semantic-branches.md) — naming model and allowed
	branch types
- [Git magic](git-magic.md) — opinionated Git helpers and workflow shortcuts
- [Skill](skill.md) — Copilot CLI usage via `uvx`

## Choose your changelog workflow

`repo-release-tools` supports two changelog styles:

- `incremental` *(default)* — maintain changelog state during development
- `squash` — skip per-commit changelog enforcement and generate or correct
	changelog entries when changes are squashed together

If you are unsure where to start:

1. Read [`rrt-cli.md`](rrt-cli.md) to configure `changelog_workflow`
2. Read [`pre-commit.md`](pre-commit.md) for the matching local hook setup
3. Read [`github-action.md`](github-action.md) to see how
	 `changelog-strategy: auto` follows that workflow in CI
