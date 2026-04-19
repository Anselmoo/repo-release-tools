# pre-commit

`repo-release-tools` publishes reusable hooks in `.pre-commit-hooks.yaml`.

## Minimal config

```yaml
default_install_hook_types: [pre-commit, commit-msg]

repos:
  - repo: https://github.com/Anselmoo/repo-release-tools
    rev: v0.1.7
    hooks:
      - id: rrt-branch-name
      - id: rrt-changelog
      - id: rrt-commit-subject
```

Install both hook types:

```bash
pre-commit install --hook-type pre-commit --hook-type commit-msg
```

## Hook overview

- `rrt-branch-name` — validates branch names
- `rrt-changelog` — requires staged changelog updates for feature/fix/breaking work
- `rrt-commit-subject` — validates conventional commit subjects
- `rrt-dirty-tree` — optional manual or pre-push check that fails on uncommitted changes

## Dirty tree check

`rrt-dirty-tree` is not enabled in the minimal config because a normal
`pre-commit` run happens while the working tree is intentionally dirty. It is
better suited for `pre-push` or manual execution when you want to enforce a
clean repository before publishing work:

```yaml
repos:
  - repo: https://github.com/Anselmoo/repo-release-tools
    rev: v0.1.7
    hooks:
      - id: rrt-dirty-tree
        stages: [pre-push]
```

You can also run the same logic directly:

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

[Lefthook](https://github.com/evilmartians/lefthook) is a fast, language-agnostic
hook runner. Unlike pre-commit it does not require a Python environment, but the
reference `lefthook.yml` for `repo-release-tools` uses an installed `rrt-hooks`
binary provided by `uv tool install repo-release-tools`.

`repo-release-tools` ships a reference `lefthook.yml` at the repo root.

### Install

```bash
# install lefthook
# macOS
brew install lefthook

# or via npm / npx
npm install --save-dev lefthook

# install uv if needed
# macOS
brew install uv

# install repo-release-tools so `rrt-hooks` is available to lefthook
uv tool install repo-release-tools

lefthook install
```

### Reference config

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

### How the auto-write flow works

When you commit, lefthook runs two `commit-msg` commands:

1. **`rrt-update-unreleased`** — parses the commit subject, appends a bullet under
   `## [Unreleased]` in `CHANGELOG.md`, and stages the file automatically.
   This is the changelog equivalent of `ruff --fix`: `feat`, `fix`, `refactor`,
   and `perf` commits are written automatically; `chore`, `ci`, `test`, and `build`
   commits are silently skipped (they map to the Maintenance section which does not
   require an entry). The `--message-file {1}` argument tells `rrt-hooks` to read
   the subject from the file lefthook provides rather than `.git/COMMIT_EDITMSG`.
2. **`rrt-commit-subject`** — validates the subject follows Conventional Commits.
   If this fails the commit is aborted and the changelog write has no effect.

The `pre-push` guard (`rrt-hooks check-changelog --strategy unreleased`) catches the rare case
where someone committed with `--no-verify`: it checks that `## [Unreleased]` is
non-empty before the push is allowed.

### Comparison: pre-commit vs. lefthook

| Hook | pre-commit | lefthook |
|---|---|---|
| Auto-write changelog | `rrt-update-unreleased` (commit-msg) | `rrt-update-unreleased --message-file {1}` |
| Validate commit subject | `rrt-commit-subject` (commit-msg) | `rrt-commit-subject {1}` |
| Validate branch name | `rrt-branch-name` (pre-commit) | `rrt-branch-name` |
| Pre-push guard | `rrt-dirty-tree` (pre-push) | `rrt-hooks check-changelog --strategy unreleased` |
