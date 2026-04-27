# Choosing between incremental and squash changelog workflows

## Short recommendation
- **Choose `incremental`** if you want `CHANGELOG.md` to stay current during development.
- **Choose `squash`** if PRs are usually squash-merged and you want changelog work to happen mainly at release time.

For **repo-release-tools specifically**, the smallest change is to set `changelog_workflow` explicitly in the existing `[tool.rrt]` section. The repo already has `version_targets`, so you do **not** need to add those again.

## Which hooks stay active?

| Workflow | Keep active | Changelog hooks |
|---|---|---|
| `incremental` | `rrt-branch-name`, `rrt-commit-subject` | Use **one** of: `rrt-update-unreleased` (auto-write `[Unreleased]`) **or** `rrt-changelog` (manual staged changelog check) |
| `squash` | `rrt-branch-name`, `rrt-commit-subject` | `rrt-update-unreleased` and `rrt-changelog` intentionally stop enforcing changelog policy; cleaner to remove them from hook config |

Optional in either mode: `rrt-dirty-tree` and `rrt-doctor`.

## How GitHub Action `changelog-strategy: auto` behaves
- `changelog_workflow = "incremental"` -> **`per-commit`**
- `changelog_workflow = "squash"` -> **`release-only`**
- not configured -> **`per-commit`**

So `auto` does **not** mean "check `[Unreleased]`". If you want CI to require a non-empty `[Unreleased]` section, set `changelog-strategy: "unreleased"` explicitly.

## Minimal config to add in this repo
Add this under the existing `[tool.rrt]` block in `pyproject.toml`:

```toml
[tool.rrt]
changelog_workflow = "incremental"  # or "squash"
```

Only add this if your changelog path is non-default:

```toml
changelog_file = "CHANGELOG.md"
```

## Practical choice guide
- Pick **`incremental`** when you want ongoing changelog maintenance and local hook help.
- Pick **`squash`** when many small commits would create noisy changelog bullets and you prefer release-time generation/cleanup.

Related default: `rrt bump` follows the workflow too — it defaults to **`auto`** for `incremental` and **`generate`** for `squash`.
