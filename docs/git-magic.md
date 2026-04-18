# Git magic

`repo-release-tools` does not want to become a generic Git alias pack. The
goal is narrower: ship a set of opinionated commit and branch workflows that
protect release hygiene and stay reusable across CLI, hooks, and GitHub
Actions.

Some early workflow discussions were inspired by
[`joseluisq/gitnow`](https://github.com/joseluisq/gitnow), but `rrt` reshapes
the surface around conventional branches, commit policy, and release safety.

## 10 magic commit frameworks

1. Branch-driven commit drafting
   Use `rrt git commit "message"` to infer the conventional commit type from the
   current branch, keeping branch intent and commit intent aligned.
2. Stage-and-commit sweep
   Use `rrt git commit-all "message"` when you want one explicit snapshot
   commit, but still want `rrt` to build the conventional subject.
3. Dirty-tree sync
   Use `rrt git sync` to fetch, auto-stash local work, pull, then restore the
   worktree. Rebase is the default path because the product assumes linear
   history where possible.
4. Safe branch move
   Use `rrt git move <branch>` to switch branches without manually juggling a
   stash.
5. Wrong-branch rescue
   Use `rrt branch rescue <type> "description"` when commits landed on the wrong
   branch and need to be moved into a correctly named branch.
6. Local story squash
   Use `rrt git squash-local "message"` to collapse a local branch into one
   reviewable conventional commit before push.
7. Safe undo
   Use `rrt git undo-safe` or `rrt git undo-safe --keep-staged` to rewind a bad
   commit without losing the work.
8. Dirty-tree gate
   Use `rrt git check-dirty-tree` when a hook, script, or CI job should fail if
   the repo is not clean. The command now prints a compact branch status line
   plus typed change entries for modified, added, removed, renamed, conflicted,
   and untracked paths.
9. Release bump envelope
   Use `rrt bump ...` when the workflow should create the branch, stage the
   version files, refresh generated files, and create the release commit in one
   pass.
10. History rebootstrap
    Use `rrt git rebootstrap` only for deliberate history replacement, such as
    templates or pre-publication cleanup. It stays behind a destructive
    confirmation flag and remote guard.

## Current command surface

```bash
rrt git status
rrt git log -n 12
rrt git doctor
rrt git check-dirty-tree
rrt git commit "handle empty config"
rrt git commit-all "snapshot parser cleanup"
rrt git sync
rrt git diff
rrt git diff --staged
rrt git diff --against HEAD~3
rrt git move feat/new-parser
rrt git squash-local "ship parser cleanup"
rrt git undo-safe --keep-staged
rrt git rebootstrap --yes-i-know-this-destroys-history --dry-run
```

## Reuse in hooks and Actions

Yes. These workflows can later back both local hooks and GitHub Actions.

The important point is to reuse the same low-level signals everywhere:

- current branch name and inferred branch type
- current commit subject and conventional-commit validity
- dirty vs clean working tree
- upstream configured vs missing
- commits ahead of a base ref
- changelog required vs missing

`repo_release_tools.git.working_tree_clean()` already gives the dirty-tree
signal, and the existing hook layer already validates branch names, commit
subjects, and changelog requirements. `rrt-hooks check-dirty-tree` now exposes
the same clean-worktree signal for reuse in hooks and GitHub Actions. The next
step is to keep adding small, shared predicates like these instead of burying
policy inside one CLI command.

That gives one policy model with several entrypoints:

- `rrt git ...` for interactive workflow
- `rrt-hooks ...` for local enforcement
- GitHub Actions for CI enforcement
- `rrt git doctor` for one-shot cross-checks of branch state, commit subject,
  dirty tree status, upstream wiring, and changelog risk

## Design rules

- Prefer workflows over aliases.
- Prefer validation and preview over hidden Git side effects.
- Keep destructive operations explicit and hard to trigger accidentally.
- Keep commit generation aligned with conventional branches and release policy.
