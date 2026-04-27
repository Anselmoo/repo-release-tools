Since `rrt` is already installed locally, use the **incremental** changelog workflow so hooks validate branch names, validate Conventional Commit subjects, and keep `[Unreleased]` updated.

## pre-commit setup

Create `.pre-commit-config.yaml`:

```yaml
default_install_hook_types: [pre-commit, commit-msg]

repos:
  - repo: https://github.com/Anselmoo/repo-release-tools
    rev: v1.0.0
    hooks:
      - id: rrt-branch-name
      - id: rrt-update-unreleased
      - id: rrt-commit-subject
```

Install the hooks:

```bash
pre-commit install --hook-type pre-commit --hook-type commit-msg
```

What this enforces:
- `rrt-branch-name` → branch names like `feat/add-parser`
- `rrt-commit-subject` → Conventional Commits
- `rrt-update-unreleased` → auto-appends changelog bullets to `CHANGELOG.md`

If you prefer **manual** changelog edits, replace `rrt-update-unreleased` with `rrt-changelog` — don’t enable both at the same time.

## lefthook setup

Create `lefthook.yml`:

```yaml
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

Install lefthook:

```bash
lefthook install
```

## When `rrt-hooks` must be on `PATH`

`rrt-hooks` **must be on `PATH` for lefthook**, because lefthook runs the binary directly. That comes from the installed `repo-release-tools` package.

For the standard `pre-commit` setup above, you reference the published hook IDs from the repo, so you do **not** need to put `rrt-hooks` on `PATH` separately for those hooks.

## Helpful checks

```bash
rrt config
rrt doctor
command -v rrt-hooks
```
