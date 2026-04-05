# pre-commit

`repo-release-tools` publishes reusable hooks in `.pre-commit-hooks.yaml`.

## Minimal config

```yaml
default_install_hook_types: [pre-commit, commit-msg]

repos:
  - repo: https://github.com/Anselmoo/repo-release-tools
    rev: v0.1.6
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
    rev: v0.1.6
    hooks:
      - id: rrt-dirty-tree
        stages: [pre-push]
```

You can also run the same logic directly:

```bash
rrt-hooks check-dirty-tree
```
