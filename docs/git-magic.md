# Git magic

`repo-release-tools` ships a small set of opinionated Git workflows for branch
health, commit drafting, sync, and history repair.

This page is generated from `repo_release_tools.git.GIT_MAGIC_DOC`.
This page stays workflow-oriented. For the full command surface and option
details, see [docs/rrt-cli.md](rrt-cli.md).

## Workflow map

- **Inspect** — `rrt git status`, `diff`, `log`, `doctor`, `sync-status`,
  `check-dirty-tree`
- **Draft commits** — `rrt git commit`, `commit-all`, `squash-local`
- **Move and sync** — `rrt git sync`, `move`, `undo-safe`, `rebootstrap`
- **Branch workflows** — `rrt branch new`, `rescue`, `rename`

## What the Git helpers optimize for

- compact, human-readable summaries first
- explicit safety checks before destructive actions
- conventional commit subjects and conventional branch names when possible
- reuse across local CLI, hooks, and CI

## Notable behavior

- `rrt git commit` infers the commit type from the current branch only when the
  branch is a conventional `type/slug` branch.
- Branches named `main`, `master`, `develop`, `release/v<semver>`, AI helper
  branches, bot branches, and custom branch prefixes are treated as special
  cases and may require `--type` for commit drafting.
- `sync` and `move` auto-stash local changes when needed.
- `undo-safe` and `rebootstrap` can rewrite history; `rebootstrap` also
  requires explicit confirmation before it destroys the current repository
  history.
- Commands that support `--dry-run` preview git operations without changing the
  worktree.

## Current command surface

```text
rrt git status
rrt git diff
rrt git log
rrt git doctor
rrt git sync-status
rrt git check-dirty-tree
rrt git commit "handle empty config"
rrt git commit-all "snapshot parser cleanup"
rrt git sync
rrt git move feat/new-parser
rrt git squash-local "ship parser cleanup"
rrt git undo-safe --keep-staged
rrt git rebootstrap --yes-i-know-this-destroys-history --dry-run
```

## See also

- [Conventional branches](semantic-branches.md)
- [Generated CLI reference](rrt-cli.md)
