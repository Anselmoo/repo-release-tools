# GitHub Action

`repo-release-tools` ships a reusable composite action in `action.yml`.

## Minimal usage

```yaml
- uses: actions/checkout@v6

- uses: Anselmoo/repo-release-tools@v0.1.0
  with:
    check-branch-name: "true"
    check-changelog: "true"
    check-commit-subject: "true"
```

## What it checks

- branch naming
- changelog updates for feature/fix/breaking work
- conventional commit subjects

## Important behavior

- Tag-triggered workflows skip branch-name validation automatically.
- The action installs `repo-release-tools` from the action checkout, not from
  the consumer repository.

## Useful inputs

- `check-branch-name`
- `check-changelog`
- `check-commit-subject`
- `branch-name`
- `branch-ref-type`
- `commit-subject`
- `changelog-file`

## Docs publishing

This repository also ships a minimal Pages workflow that publishes `docs/`
directly. No extra docs framework is required for the current interface.
