# GitHub Action

`repo-release-tools` ships a reusable composite action in `action.yml`.

## Minimal usage

```yaml
- uses: actions/checkout@v6

- uses: Anselmoo/repo-release-tools@v0.1.7
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

## Important behavior

- Tag-triggered workflows skip branch-name validation automatically.
- The action installs `repo-release-tools` from the action checkout, not from
  the consumer repository.

## Useful inputs

- `check-branch-name`
- `check-changelog`
- `check-commit-subject`
- `check-dirty-tree`
- `branch-name`
- `branch-ref-type`
- `commit-subject`
- `changelog-file`

`check-dirty-tree` defaults to `false` because a GitHub Action checkout is
usually clean already. It is still useful for workflows that generate files and
want to assert that the job did not leave uncommitted changes behind.

## Docs publishing

This repository also ships a minimal Pages workflow that publishes `docs/`
directly. No extra docs framework is required for the current interface.
