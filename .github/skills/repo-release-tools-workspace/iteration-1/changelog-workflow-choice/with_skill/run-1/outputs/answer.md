# Choosing between incremental and squash changelog workflows for repo-release-tools

For **this repo**, I would keep **`incremental`** unless you plan to squash-merge most PRs and want to stop maintaining `[Unreleased]` during day-to-day development.

Why: the current `lefthook.yml` already matches an incremental flow (`rrt-update-unreleased` on `commit-msg` plus a pre-push changelog guard), and the repo currently has **no explicit `changelog_workflow`**, so repo-release-tools already treats it as **`incremental` by default**.

## Quick choice

- **Choose `incremental`** if you want `[Unreleased]` kept current as you work.
- **Choose `squash`** if you squash-merge lots of commits and want changelog work to happen mainly at release time or via post-correction.

## Which hooks stay active in each mode?

| Workflow | Keep active | Notes |
|---|---|---|
| `incremental` | `rrt-branch-name`, `rrt-commit-subject`, and **one primary changelog hook**: either `rrt-update-unreleased` **or** `rrt-changelog` | `rrt-update-unreleased` auto-writes `[Unreleased]`; `rrt-changelog` requires a staged changelog edit instead. Optional: `rrt-dirty-tree`, `rrt-doctor`. |
| `squash` | `rrt-branch-name`, `rrt-commit-subject` | `rrt-update-unreleased` and `rrt-changelog` intentionally **skip** changelog enforcement when `changelog_workflow = "squash"`. You can leave them configured during migration, but the cleaner setup is to remove them. Optional: `rrt-dirty-tree`, `rrt-doctor`. |

### Repo-specific note

This repo’s current `lefthook.yml` is effectively **incremental-style**:

- `rrt-update-unreleased` on `commit-msg`
- `rrt-commit-subject` on `commit-msg`
- `rrt-branch-name` on `pre-commit`
- `rrt-hooks check-changelog --strategy unreleased` on `pre-push`

That means staying on `incremental` is the least disruptive choice.

## How GitHub Action `changelog-strategy: auto` behaves

`auto` reads `changelog_workflow` from repo config and resolves like this:

| `changelog_workflow` | `changelog-strategy: auto` resolves to |
|---|---|
| `incremental` | `per-commit` |
| `squash` | `release-only` |
| not configured | `per-commit` |

So for this repo **today**, Action `auto` would behave like **`per-commit`**.

### Important implication

If you want CI to validate **“`[Unreleased]` is non-empty”** instead of **“`CHANGELOG.md` changed in this commit”**, do **not** use `auto`; set:

```yaml
changelog-strategy: "unreleased"
```

That is the best fit when you use `rrt-update-unreleased` locally and want CI to follow the same `[Unreleased]`-based policy.

## Minimal config to add

Because `pyproject.toml` already has `[tool.rrt]`, the **smallest repo-specific change** is just one line:

```toml
[tool.rrt]
changelog_workflow = "incremental"  # or "squash"
```

If you want the fuller minimal shape for a new repo, use:

```toml
[tool.rrt]
release_branch = "release/v{version}"
changelog_file = "CHANGELOG.md"
changelog_workflow = "incremental"  # or "squash"

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"
```

## My recommendation for repo-release-tools

- **Stay with `incremental`** if you want to preserve the current hook-driven workflow.
- **Switch to `squash`** only if you want fewer intermediate changelog edits and are comfortable relying on release-time changelog generation/post-correction.

If you stay incremental, I would make the config explicit with:

```toml
[tool.rrt]
changelog_workflow = "incremental"
```

and, if you want CI to match the current local workflow more closely, use:

```yaml
changelog-strategy: "unreleased"
```

instead of `auto`.
