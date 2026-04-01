# pre-commit

`repo-release-tools` publishes reusable hooks in `.pre-commit-hooks.yaml`.

## Minimal config

```yaml
default_install_hook_types: [pre-commit, commit-msg]

repos:
  - repo: https://github.com/Anselmoo/repo-release-tools
    rev: v0.1.0
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
