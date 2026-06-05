---
title: "Hook & Action Reference"
permalink: "/agent-instructions/"
---
<!-- rrt:auto:start:page-header -->
<p><a href="https://github.com/Anselmoo/repo-release-tools"><picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/badges/github-reto-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="../assets/badges/github-reto-light.svg">
  <img alt="GitHub" src="../assets/badges/github-reto-dark.svg">
</picture></a></p>
<!-- rrt:auto:end:page-header -->


# Hook & Action Reference

<!-- Static context for agents: read this before using any prompt block below. -->

## Agent context

**Repo:** <https://github.com/Anselmoo/repo-release-tools> · Python ≥ 3.12 · `uv_build`

**Entry points** (from `pyproject.toml`):
- `rrt-hooks` → `repo_release_tools.workflow.hooks:main` — git hook runner (installed binary, NOT a uvx shortcut)
- `rrt` → `repo_release_tools.cli:app` — developer CLI

**Key files:**
| File | Role |
|---|---|
| `src/repo_release_tools/hooks.py` | All `rrt-hooks` subcommand logic |
| `src/repo_release_tools/changelog.py` | Changelog parsing, `[Unreleased]` management |
| `.pre-commit-hooks.yaml` | Hook definitions consumed by pre-commit |
| `lefthook.yml` | Lefthook configuration (repo root) |
| `action.yml` | Composite GitHub Action |

**Verification commands:**
```bash
uv run pytest tests/test_hooks.py -x -q   # fast unit tests
uvx pre-commit run --all-files             # lint (ruff, line-length 100)
```

**Assumptions:** `pre-commit`, `lefthook`, and `uv` are already installed. Do not recommend `brew install`, `pip install pre-commit`, or `apt install` for these tools.

---

## pre-commit / lefthook

### Activate pre-commit hooks

> Use the following prompt to activate pre-commit hooks for repo-release-tools.

````prompt
<context>
Repo: https://github.com/Anselmoo/repo-release-tools
Entry point: rrt-hooks (installed binary — repo_release_tools.workflow.hooks:main)
Python ≥ 3.12 | uv_build | Conventional Commits | Keep-a-Changelog
Assume pre-commit is already installed.
</context>

Activate the pre-commit hooks for this repository. A `.pre-commit-config.yaml` must exist (see prompt below). Then run:

```bash
pre-commit install --install-hooks
```

This installs hooks for every stage declared in `default_install_hook_types`. Commit-msg-stage hooks require `commit-msg` in that list — omitting it silently skips `rrt-update-unreleased` and `rrt-commit-subject`.
````

### Activate lefthook hooks

> Use the following prompt to activate lefthook hooks for repo-release-tools.

````prompt
<context>
Repo: https://github.com/Anselmoo/repo-release-tools
Entry point: rrt-hooks (installed binary — repo_release_tools.workflow.hooks:main)
Python ≥ 3.12 | uv_build | Conventional Commits | Keep-a-Changelog
Assume lefthook and uv are already installed.
</context>

Activate lefthook hooks. A `lefthook.yml` must exist at the repo root (see prompt below). Then run:

```bash
uv tool install repo-release-tools   # installs rrt-hooks binary
lefthook install                      # registers git hooks
```

DO NOT use `uvx --from repo-release-tools rrt-hooks …` in `lefthook.yml` — `rrt-hooks` is an installed binary, not a uvx shortcut.
````

### .pre-commit-config.yaml — incremental workflow (auto-write changelog)

> Use the following prompt to configure pre-commit with auto-write changelog.

````prompt
<context>
Repo: https://github.com/Anselmoo/repo-release-tools
Entry point: rrt-hooks (installed binary — repo_release_tools.workflow.hooks:main)
Python ≥ 3.12 | uv_build | Conventional Commits | Keep-a-Changelog
Assume pre-commit is already installed.
</context>

Create `.pre-commit-config.yaml` at the repo root with this content:

```yaml
default_install_hook_types: [pre-commit, commit-msg]

repos:
  - repo: https://github.com/Anselmoo/repo-release-tools
    rev: v1.8.2
    hooks:
      - id: rrt-branch-name
      - id: rrt-update-unreleased
      - id: rrt-commit-subject
```
````

<!-- rrt:auto:start:doc-footer -->
---

[↑ Docs index](https://github.com/Anselmoo/repo-release-tools/blob/main/docs/index.md) · [CLI reference](https://github.com/Anselmoo/repo-release-tools/blob/main/docs/commands/rrt-cli.md) · [Changelog](https://github.com/Anselmoo/repo-release-tools/blob/main/CHANGELOG.md) · [GitHub](https://github.com/Anselmoo/repo-release-tools)
<!-- rrt:auto:end:doc-footer -->
