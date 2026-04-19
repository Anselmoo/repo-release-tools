# GitHub Action

Use the GitHub Action when you want CI to enforce the same policy that
`rrt-hooks` can enforce locally.

## Minimal workflow

```yaml
- uses: actions/checkout@v6
  with:
    fetch-depth: 0

- uses: Anselmoo/repo-release-tools@v0.1.10
  with:
    check-branch-name: "true"
    check-commit-subject: "true"
    check-changelog: "true"
```

`fetch-depth: 0` is required because changelog and commit-subject checks use
`git log` and commit metadata. A shallow checkout makes those checks flaky at
best and misleading at worst — tiny chaos gremlin, large confusion.

## What it checks

- branch naming
- Conventional Commit subjects
- changelog policy
- optional clean-worktree enforcement
- optional `rrt doctor` health checks

## Important behavior

- Tag-triggered workflows skip branch-name validation automatically.
- The action installs `repo-release-tools` from the action checkout, not from
  the consumer repository.
- `changelog-strategy` defaults to `auto`, so CI can follow repository config
  instead of forcing one changelog policy everywhere.

## Changelog strategy: use `auto` unless you have a reason not to

`changelog-strategy` controls how CI decides whether a changelog is valid.

| Strategy | When to use it | What passes |
|---|---|---|
| `auto` *(default)* | most repositories | follows `changelog_workflow` from repo config |
| `per-commit` | every changelog-relevant commit must touch `CHANGELOG.md` | `CHANGELOG.md` appears in the commit's changed files |
| `unreleased` | you maintain `[Unreleased]` continuously, often via hooks | `## [Unreleased]` is non-empty |
| `release-only` | changelog is generated or reviewed only when cutting a release | check is skipped during normal CI |

### How `auto` resolves

| `changelog_workflow` | Action behavior when `changelog-strategy: auto` |
|---|---|
| `incremental` *(default)* | resolves to `per-commit` |
| `squash` | resolves to `release-only` |
| not configured | resolves to `per-commit` |

Use an explicit override only when you want CI to be stricter or looser than
the repo default. A common example is pairing local `rrt-update-unreleased`
hooks with CI `changelog-strategy: "unreleased"`.

## Common examples

### Default CI setup

```yaml
- uses: Anselmoo/repo-release-tools@v0.1.10
  with:
    check-changelog: "true"
    changelog-strategy: "auto"
```

### Hook-managed `[Unreleased]` workflow

```yaml
- uses: Anselmoo/repo-release-tools@v0.1.10
  with:
    check-changelog: "true"
    changelog-strategy: "unreleased"
```

### Release-time changelog workflow

```yaml
- uses: Anselmoo/repo-release-tools@v0.1.10
  with:
    check-changelog: "true"
    changelog-strategy: "release-only"
```

## Inputs

| Input | Default | Description |
|---|---|---|
| `check-branch-name` | `"true"` | Validate branch naming convention |
| `check-commit-subject` | `"true"` | Validate Conventional Commit subject |
| `check-changelog` | `"true"` | Validate changelog policy for changelog-relevant commits |
| `changelog-strategy` | `"auto"` | `auto` / `per-commit` / `unreleased` / `release-only` |
| `changelog-file` | `"CHANGELOG.md"` | Path to changelog file |
| `check-dirty-tree` | `"false"` | Fail when generated files leave the work tree dirty |
| `check-doctor` | `"false"` | Run `rrt doctor` health checks |
| `branch-name` | — | Override the branch name to validate |
| `branch-ref-type` | — | Override branch ref type detection |
| `commit-subject` | — | Override the commit subject to validate |

`check-dirty-tree` defaults to `"false"` because GitHub Actions checkouts are
normally clean already. Turn it on when a workflow generates files and you want
the job to assert that nothing was left uncommitted.

`check-doctor` runs `rrt doctor`, which verifies that version targets and pin
targets in repo config are reachable and well-formed. It is a good release gate
when your repository relies on config-driven version updates.
