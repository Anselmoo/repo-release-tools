"""Run opinionated Git workflow helpers for rrt.

`rrt git` bundles the repository workflows that are used most often while
developing and releasing this project. The command group favors compact,
human-readable summaries with explicit safety checks before any destructive
operation.

Most commands are designed to run from a Git work tree and emit a short
summary first, followed by the details needed to act on the result.

## Command families

### Inspection

- `status` shows the current branch, upstream, and a compact view of worktree
  changes.
- `diff` renders a condensed diff for the working tree, staged changes, or a
  specific ref.
- `log` shows recent commits with short SHAs, subjects, and refs.
- `doctor` runs a repository health report for common rrt workflow rules.
- `sync-status` reports unresolved conflicts and ahead/behind drift against a
  sync base.
- `check-dirty-tree` exits non-zero when the worktree is dirty, which makes it
  useful for hooks and CI.

### Commit drafting

- `commit` creates one conventional commit and infers the type from the current
  branch when possible.
- `commit-all` stages all tracked and untracked files before creating the
  commit.
- `squash-local` squashes commits ahead of an upstream branch or `--base-ref`
  into one conventional commit.

### Branch maintenance and synchronization

- `sync` fetches, auto-stashes dirty changes when needed, and pulls from the
  upstream branch.
- `move` switches branches safely and can create the target branch first.
- `undo-safe` resets to another ref while keeping changes staged or in the
  working tree.
- `rebootstrap` backs up `.git`, reinitializes the repository, and creates a
  fresh history snapshot or empty bootstrap commit.
- `purge-cache` expires reflogs and runs `git gc` to reclaim local cache space.

### Publish

- `publish-snapshot` force-pushes a single-commit, no-history snapshot of tracked
  content to a secondary remote (e.g. a public mirror).
- `backport-from-target` is the read-only counterpart: it fetches a publish
  target and lists commits present there but not on the primary, along with the
  exact commands to cherry-pick them back manually.

## Behavior details

- Commit subjects use conventional commit syntax with optional scope and
  breaking markers.
- Commands that support `--dry-run` preview the git operations without making
  changes.
- Several commands refuse to continue when the repository is in an unsafe
  state, such as unresolved conflicts, an in-progress merge or rebase, or a
  missing upstream branch.
- `rebootstrap` requires explicit confirmation before it can destroy history.
- `purge-cache` is safe for normal worktrees but can take time on large repos;
    use `--dry-run` first to preview the maintenance commands.

## Examples

```text
$ rrt git status
$ rrt git commit "refresh help examples"
$ rrt git sync --dry-run
$ rrt git squash-local --base-ref origin/main "ship parser"
$ rrt git rebootstrap --yes-i-know-this-destroys-history --dry-run
$ rrt git purge-cache --dry-run
$ rrt git backport-from-target demo
```

## Safety notes

- `sync` and `move` auto-stash local changes, but a failed pull or checkout can
  leave the stash on the stack.
- `undo-safe` and `rebootstrap` can rewrite repository history; use them only
  when that is intended.
- `rebootstrap` also guards against accidental use on repositories with
  configured remotes unless explicitly allowed.
"""

from __future__ import annotations

import argparse

from repo_release_tools.commands.git_backport import register_backport
from repo_release_tools.commands.git_commit import register_commit
from repo_release_tools.commands.git_inspect import register_inspect
from repo_release_tools.commands.git_sync import register_sync

GIT_EPILOG = (
    "  $ rrt git status\n"
    "  $ rrt git diff --against HEAD~1\n"
    '  $ rrt git commit --type fix "make output clearer"\n'
    "  $ rrt git sync\n"
    "  $ rrt git undo-safe\n"
    "  $ rrt git publish-snapshot --remote mirror --dry-run\n"
    "  $ rrt git backport-from-target demo"
)


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the git command group."""
    parser = subparsers.add_parser(
        "git",
        help="Git workflow helpers.",
        description="Git workflow helpers for repository status, commit, sync, and history operations.",
        epilog=GIT_EPILOG,
    )
    git_sub = parser.add_subparsers(
        dest="git_command",
        metavar="<git_command>",
        parser_class=type(parser),
        required=True,
    )
    register_inspect(git_sub)
    register_commit(git_sub)
    register_sync(git_sub)
    register_backport(git_sub)
