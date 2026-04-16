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
3. Removing **semantically-cancelling pairs** — e.g. `"add X"` followed by
   `"remove X"`.
4. Rewriting `CHANGELOG.md` in-place with the cleaned content.
5. Optionally creating a follow-up commit (`--commit`).

### Quick usage

```bash
# auto mode — use HEAD as the squash commit
rrt-hooks changelog post-correct --auto

# explicit squash commit SHA
rrt-hooks changelog post-correct --squash-commit abc1234

# write a follow-up commit automatically
rrt-hooks changelog post-correct --auto --commit
```

### As a GitHub Actions step (post-merge on default branch)

```yaml
- name: Consolidate changelog after squash merge
  if: github.event_name == 'push' && github.ref == 'refs/heads/main'
  run: uvx --from repo-release-tools rrt-hooks changelog post-correct --auto --commit
```

### Options

| Flag | Description |
|---|---|
| `--auto` | Use `HEAD` as the squash commit (default) |
| `--squash-commit SHA` | Explicit commit SHA to inspect |
| `--output PATH` | Changelog file to rewrite (default: `CHANGELOG.md`) |
| `--commit` | Create a follow-up commit with the corrected changelog |
