# GitHub Action

`repo-release-tools` ships a reusable composite action in `action.yml`.

## Minimal usage

```yaml
- uses: actions/checkout@v6

- uses: Anselmoo/repo-release-tools@v0.1.10
  with:
    check-branch-name: "true"
    check-changelog: "true"
    check-commit-subject: "true"
    check-dirty-tree: "false"
```

## What it checks

- branch naming
- changelog updates for feature/fix/breaking work
- conventional commit subjects
- optional clean-worktree enforcement
- optional `rrt doctor` config health checks

## Important behavior

- Tag-triggered workflows skip branch-name validation automatically.
- The action installs `repo-release-tools` from the action checkout, not from
  the consumer repository.

## Inputs

| Input | Default | Description |
|---|---|---|
| `check-branch-name` | `"true"` | Validate branch naming convention |
| `check-commit-subject` | `"true"` | Validate conventional commit subject |
| `check-changelog` | `"true"` | Require changelog update for feat/fix/breaking commits |
| `changelog-strategy` | `"per-commit"` | `per-commit` / `unreleased` / `release-only` |
| `check-dirty-tree` | `"false"` | Fail when work tree has uncommitted changes after checks |
| `check-doctor` | `"false"` | Run `rrt doctor` health checks (exits 1 on any failure) |
| `branch-name` | — | Override the branch name to validate |
| `branch-ref-type` | — | Override branch ref type detection |
| `commit-subject` | — | Override the commit subject to validate |
| `changelog-file` | `"CHANGELOG.md"` | Path to changelog file |

### Changelog strategies

| Strategy | When the check passes |
|---|---|
| `per-commit` (default) | `CHANGELOG.md` appears in the commit's changed files |
| `unreleased` | `## [Unreleased]` section is non-empty |
| `release-only` | Check always skipped (changelog updated only at release time) |

`check-dirty-tree` defaults to `"false"` because a GitHub Actions checkout is
usually clean already. It is still useful for workflows that generate files and
want to assert that the job did not leave uncommitted changes behind.

`check-doctor` runs `rrt doctor`, which verifies that every version target and
pin target in `[tool.rrt]` is reachable and well-formed. Recommended as a
pre-release gate.

## Docs publishing

This repository also ships a minimal Pages workflow that publishes `docs/`
directly. No extra docs framework is required for the current interface.
