# pre-commit

`repo-release-tools` publishes reusable hooks in `.pre-commit-hooks.yaml`.

The first decision is not *which hook do I add?* — it is *which changelog
workflow does this repo follow?*

## Choose the workflow first

| Workflow | Recommended hooks | Best for |
|---|---|---|
| `incremental` *(default)* | `rrt-branch-name`, `rrt-commit-subject`, plus `rrt-update-unreleased` **or** `rrt-changelog` | teams that maintain changelog state while developing |
| `squash` | `rrt-branch-name`, `rrt-commit-subject`, optional `rrt-dirty-tree` / `rrt-doctor` | repos that squash many commits and do changelog work at release time |

With `changelog_workflow = "squash"`, the changelog-writing and changelog-check
hooks intentionally skip changelog enforcement. You can leave them configured
during migration, but the cleaner setup is to remove them and keep only the
non-changelog policy hooks.

## Incremental workflow: keep `[Unreleased]` current

```yaml
default_install_hook_types: [pre-commit, commit-msg]

repos:
  - repo: https://github.com/Anselmoo/repo-release-tools
    rev: v1.1.0
    hooks:
      - id: rrt-branch-name
      - id: rrt-update-unreleased
      - id: rrt-commit-subject
```

Install both hook types:

```bash
pre-commit install --hook-type pre-commit --hook-type commit-msg
```

This setup keeps `CHANGELOG.md` moving with development. `rrt-update-unreleased`
auto-writes changelog bullets for changelog-relevant commit types, while
`rrt-commit-subject` enforces Conventional Commits.

If you prefer manual changelog edits instead of auto-writing them, replace
`rrt-update-unreleased` with `rrt-changelog`.

## Squash workflow: keep local policy, skip per-commit changelog noise

```yaml
default_install_hook_types: [pre-commit, commit-msg]

repos:
  - repo: https://github.com/Anselmoo/repo-release-tools
    rev: v1.1.0
    hooks:
      - id: rrt-branch-name
      - id: rrt-commit-subject
```

Use this when pull requests are squash-merged and you do not want ten tiny
commit-level changelog bullets to become one giant release footnote monster.
Pair it with:

- `changelog_workflow = "squash"` in repo config
- GitHub Action `changelog-strategy: "auto"` or `"release-only"`
- `rrt bump` to generate release-time changelog content

## Hook overview

| Hook | Stage | Description |
|---|---|---|
| `rrt-branch-name` | pre-commit | Validate branch naming convention |
| `rrt-update-unreleased` | commit-msg | Auto-write a bullet under `[Unreleased]` for changelog-relevant commits |
| `rrt-changelog` | pre-commit | Require a staged changelog update for changelog-relevant work |
| `rrt-commit-subject` | commit-msg | Validate Conventional Commit subjects |
| `rrt-dirty-tree` | pre-push / manual | Fail on uncommitted changes |
| `rrt-doctor` | manual | Run `rrt doctor` health checks on `rrt` config |

`rrt-update-unreleased` and `rrt-changelog` are alternatives for the
incremental workflow. You usually want one or the other, not both.

## Optional guards

### Dirty tree check

`rrt-dirty-tree` is not enabled in the minimal configs because a normal
`pre-commit` run happens while the working tree is intentionally dirty. It is
better suited for `pre-push` or manual execution when you want to enforce a
clean repository before publishing work:

```yaml
repos:
  - repo: https://github.com/Anselmoo/repo-release-tools
    rev: v1.1.0
    hooks:
      - id: rrt-dirty-tree
        stages: [pre-push]
```

### Doctor check

`rrt-doctor` runs `rrt doctor` health checks against every version target and
pin target in `[tool.rrt]`. It is registered at the `manual` stage so it does
not run on every commit — invoke it on demand before releases:

```bash
pre-commit run rrt-doctor --hook-stage manual
# or directly:
rrt doctor
```

You can also run the same dirty-tree logic directly:

```bash
rrt-hooks check-dirty-tree
```

## Post-correction mode (squash-merge workflows)

When a pull request is merged via **squash merge**, GitHub condenses all
per-commit changelog entries into the squash commit. The result can be
fragmented micro-commit noise in `CHANGELOG.md` — for example several
`"CI: add Node 26"` / `"CI: remove Node 26"` pairs that cancel each other out.

`rrt-hooks changelog post-correct` consolidates those entries by:

1. Inspecting the diff that the squash commit introduced to `CHANGELOG.md`.
2. Removing **exact duplicate** bullet entries (case-insensitive).
3. Removing **semantically-cancelling pairs** — e.g. `"CI: add Node 26"` followed by
   `"CI: remove Node 26"`, or bare `"add X"` / `"remove X"`.  Scope prefixes
   (e.g. `CI:`, `Deps:`) must match for entries to be considered a pair.
4. Rewriting `CHANGELOG.md` in-place with the cleaned content, restricting
   removals to the exact diff hunk so older release sections are never touched.
5. Optionally creating a follow-up commit (`--commit`).

### Quick usage

```bash
# auto mode — use HEAD as the squash commit (default when no SHA given)
rrt-hooks changelog post-correct

# explicit squash commit SHA
rrt-hooks changelog post-correct --squash-commit abc1234

# write a follow-up commit automatically
rrt-hooks changelog post-correct --commit
```

### As a GitHub Actions step (post-merge on default branch)

```yaml
- name: Consolidate changelog after squash merge
  if: github.event_name == 'push' && github.ref == 'refs/heads/main'
  run: uvx --from repo-release-tools rrt-hooks changelog post-correct --commit
```

### Options

| Flag | Description |
|---|---|
| `--squash-commit SHA` | Explicit commit SHA to inspect (defaults to `HEAD`) |
| `--output PATH` | Changelog file to rewrite (default: `CHANGELOG.md`) |
| `--commit` | Create a follow-up commit with the corrected changelog |

---

## Lefthook setup

[Lefthook](https://github.com/evilmartians/lefthook) can run the same local
policy with an installed `rrt-hooks` binary.

Install `repo-release-tools` so `rrt-hooks` is on `PATH`, then add the commands
that match your workflow.

### Incremental workflow example

```yaml
# lefthook.yml
commit-msg:
  commands:
    rrt-update-unreleased:
      run: rrt-hooks update-unreleased --message-file {1}
    rrt-commit-subject:
      run: rrt-hooks commit-msg {1}

pre-commit:
  commands:
    rrt-branch-name:
      run: rrt-hooks pre-commit

pre-push:
  commands:
    rrt-changelog:
      run: rrt-hooks check-changelog --subject "$(git log -1 --format=%s)" --strategy unreleased
```

### Squash workflow example

```yaml
# lefthook.yml
commit-msg:
  commands:
    rrt-commit-subject:
      run: rrt-hooks commit-msg {1}

pre-commit:
  commands:
    rrt-branch-name:
      run: rrt-hooks pre-commit
```

### Comparison: pre-commit vs. lefthook

| Policy | pre-commit | lefthook |
|---|---|---|
| Auto-write changelog | `rrt-update-unreleased` (commit-msg) | `rrt-update-unreleased --message-file {1}` |
| Validate commit subject | `rrt-commit-subject` (commit-msg) | `rrt-commit-subject {1}` |
| Validate branch name | `rrt-branch-name` (pre-commit) | `rrt-hooks pre-commit` |
| Pre-push unreleased guard | `rrt-changelog` or `rrt-dirty-tree` | `rrt-hooks check-changelog --strategy unreleased` |
