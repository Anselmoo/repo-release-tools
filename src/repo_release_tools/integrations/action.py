"""GitHub Action documentation for repo-release-tools."""

from __future__ import annotations

GITHUB_ACTION_DOC = """# GitHub Action

Use the GitHub Action when you want CI to enforce the same policy that
`rrt-hooks` can enforce locally.

## Overview

The composite Action runs `rrt-hooks` checks inside a GitHub Actions job. It
validates branch names, Conventional Commit subjects, and changelog policy.
Optional inputs add doctor, release-health, folder, and artifact checks. Reach
for it when CI has to be the gate, not just the contributor's machine.

## Minimal workflow

```yaml
- uses: actions/checkout@v6
  with:
    fetch-depth: 0

- uses: Anselmoo/repo-release-tools@v1.18.0
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
- optional `rrt doctor` core automation checks
- optional `rrt release check` release-target validation
- optional folder structure validation (`check-folder`)
- optional artifact hash integrity (`check-artifacts`)

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

## Examples

### Default CI setup

```yaml
- uses: Anselmoo/repo-release-tools@v1.18.0
  with:
    check-changelog: "true"
    changelog-strategy: "auto"
```

### Hook-managed `[Unreleased]` workflow

```yaml
- uses: Anselmoo/repo-release-tools@v1.18.0
  with:
    check-changelog: "true"
    changelog-strategy: "unreleased"
```

### Release-time changelog workflow

```yaml
- uses: Anselmoo/repo-release-tools@v1.18.0
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
| `changelog-strategy` | `"auto"` | `auto` / `incremental` / `per-commit` / `unreleased` / `release-only` |
| `changelog-file` | `"CHANGELOG.md"` | Path to changelog file |
| `check-dirty-tree` | `"false"` | Fail when generated files leave the work tree dirty |
| `check-doctor` | `"false"` | Run `rrt doctor` core automation checks |
| `check-release-health` | `"false"` | Run `rrt release check` for version targets, pin targets, and changelog files |
| `check-folder` | `"false"` | Fail if the repository folder structure violates `[tool.rrt.folders]` config |
| `check-artifacts` | `"false"` | Fail if generated artifact hashes disagree with `.rrt/artifacts.lock.toml` |
| `branch-name` | — | Override the branch name to validate |
| `branch-ref-type` | — | Override branch ref type detection |
| `commit-subject` | — | Override the commit subject to validate |

`check-dirty-tree` defaults to `"false"` because GitHub Actions checkouts are
normally clean already. Turn it on when a workflow generates files and you want
the job to assert that nothing was left uncommitted.

`check-doctor` runs `rrt doctor`, which verifies core automation wiring such as
hook and CI integration surfaces.

`check-release-health` runs `rrt release check`, which verifies that version
targets, pin targets, and changelog files in repo config are reachable and
well-formed. It is the better release gate when your repository relies on
config-driven version updates.

`check-folder` runs `rrt-hooks folder-check`, which validates the repository
directory layout against the `[tool.rrt.folders]` configuration. Use it to
enforce a consistent project structure across contributors and CI environments.

`check-artifacts` runs `rrt-hooks artifacts-check`, which compares generated
artifact hashes against the committed `.rrt/artifacts.lock.toml`. It detects
artifacts that were regenerated but not re-snapshotted, or vice versa.

## Caveats

- `fetch-depth: 0` is required. Shallow checkouts break the changelog and
  commit-subject checks.
- Tag-triggered workflows skip branch-name validation automatically.
- The action installs `repo-release-tools` from the action checkout, not from
  the consumer repository.
- `changelog-strategy` defaults to `auto`, so CI can follow repository config
  instead of forcing one changelog policy everywhere.
- Only `check-branch-name`, `check-commit-subject` and `check-changelog`
  default to `"true"`. Every other check is opt-in, including dirty-tree,
  doctor, release-health, eol, docs, folder and artifacts.
- The version pin in each example tracks the current release. Pin the tag you
  actually want.

## Related docs

- [publish-snapshot Action](/repo-release-tools/publish-snapshot-action/) for
  publishing a snapshot to a mirror remote
- [Hooks](/repo-release-tools/commands/hooks/) for running the same checks
  locally
- [`rrt doctor`](/repo-release-tools/commands/doctor/) for the checks behind
  `check-doctor`
- [`rrt branch`](/repo-release-tools/commands/branch/) for the naming
  convention CI validates
"""

GITHUB_ACTION_PUBLISH_SNAPSHOT_DOC = """# publish-snapshot Action

A dedicated composite Action for `rrt git publish-snapshot` — force-pushing a
single-commit, no-history snapshot of tracked content to a secondary remote
(e.g. a public downstream mirror of a privately developed repository).

## Overview

Use this Action to refresh a public mirror from a private repository. It
force-pushes one commit with no history to the remote named by `target`.
Resolve the remote, branch, message, and excludes from a
`[tool.rrt.publish_targets.<name>]` config entry.

It is deliberately **not** part of the main `repo-release-tools` Action.
That action is a set of read-only, idempotent policy checks meant to run on
every PR. `publish-snapshot` is destructive and belongs on a different
trigger. Use push-to-main, a schedule, or `workflow_dispatch`. Keeping it in
its own composite action isolates that risk profile.

## Examples

```yaml
name: Refresh public mirror

on:
  push:
    branches: [main]
  workflow_dispatch: {}

jobs:
  publish-snapshot:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
        with:
          fetch-depth: 0

      - uses: Anselmoo/repo-release-tools/actions/publish-snapshot@v1.18.0
        with:
          target: public-preview
          confirm: "true"
```

## Inputs

| Input | Default | Description |
|---|---|---|
| `target` | — (required) | Named `[tool.rrt.publish_targets.<name>]` entry to resolve remote/branch/message/exclude from |
| `confirm` | `"false"` | Set `"true"` to actually force-push; otherwise this only previews with `--dry-run` |
| `python-version` | `"3.12"` | Python version used to run repo-release-tools |
| `working-directory` | `"."` | Repository path to install and run repo-release-tools from |

## Caveats

Force-pushing does not immediately purge old objects on the remote host.
They can remain fetchable by direct SHA until the host runs garbage
collection. If secrets were ever committed, run `git filter-repo` or the BFG
Repo-Cleaner first. This action only controls what is visible going forward.
Clones or forks made before the force-push retain the old history locally,
which is outside this tool's control. Always run with `confirm: "false"`
(the default) first and inspect the dry-run output before flipping it on.

## Related docs

- [GitHub Action](/repo-release-tools/action/) for the read-only policy checks
  that run on every PR
- [rrt CLI](/repo-release-tools/commands/rrt-cli/) for the underlying
  `rrt git publish-snapshot` command
"""

# Ordered source-owned topic docs for docs generation.
SOURCE_OWNED_TOPIC_DOCS: tuple[tuple[str, str], ...] = (
    ("action", GITHUB_ACTION_DOC),
    ("publish-snapshot-action", GITHUB_ACTION_PUBLISH_SNAPSHOT_DOC),
)
