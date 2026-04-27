# repo-release-tools hook setup

Because you want **branch names, commit subjects, and changelog updates enforced**, use the **incremental** changelog workflow.

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

Then install both hook types:

```bash
pre-commit install --hook-type pre-commit --hook-type commit-msg
```

What this enforces:
- `rrt-branch-name` → branch names like `feat/add-parser`
- `rrt-commit-subject` → Conventional Commit subjects like `feat: add parser`
- `rrt-update-unreleased` → auto-writes/stages `[Unreleased]` changelog bullets for changelog-relevant commits

If you want **manual** changelog edits instead of auto-writing, replace `rrt-update-unreleased` with `rrt-changelog`.

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

Then install lefthook:

```bash
lefthook install
```

What this enforces:
- `pre-commit` → branch naming
- `commit-msg` → Conventional Commit subject + changelog update
- `pre-push` → catches missing unreleased changelog state before push

## When `rrt-hooks` must be on `PATH`

- **Lefthook:** **yes** — it runs `rrt-hooks ...` directly, so the installed executable must be on `PATH`.
- **Standard published pre-commit setup:** **no separate PATH requirement** — `pre-commit` installs/runs the hook environment itself.

Since you said `rrt` is already installed locally, verify the bundled hook entrypoint is available with:

```bash
rrt-hooks --help
```

If that works, lefthook can call it.
