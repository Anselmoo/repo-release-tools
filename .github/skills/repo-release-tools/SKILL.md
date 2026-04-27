---
name: repo-release-tools
description: 'Guide release workflows with the installed rrt CLI. Use when: checking branch naming rules, setting up pre-commit or lefthook hooks, configuring GitHub Action policy checks, running rrt doctor/config, planning changelog workflow, or previewing version bumps in a repo where rrt is already installed.'
argument-hint: 'What repo-release-tools task do you need help with? (branch naming, hooks, doctor/config, GitHub Action, changelog workflow, or release bump)'
---

# repo-release-tools — installed CLI workflow skill

Use this skill when the machine already has the `rrt` command available.

Prefer this skill over the `repo-release-tools-uvx` skill when you want advice
and commands that assume a persistent local install such as:

- `rrt branch ...`
- `rrt bump ...`
- `rrt doctor`
- `rrt config`
- `rrt init`
- `rrt skill install`
- `rrt-hooks ...`

## Quick command map

```bash
rrt init
rrt config
rrt doctor
rrt branch new feat "add parser"
rrt branch rename --type fix --scope api
rrt bump patch --dry-run
rrt bump minor
rrt skill install --target copilot-local
```

## Branch naming guidance

Use conventional prefixes such as:

- `feat/add-parser`
- `fix/api-timeout`
- `docs/release-playbook`
- `chore/update-hooks`

Helpful commands:

```bash
rrt branch new feat "add parser"
rrt branch rename --type fix
rrt branch rename --scope cli
rrt branch rename fix "repair config loader" --scope cli
```

If the repo uses extra branch prefixes, check or add them in config:

```toml
[tool.rrt]
extra_branch_types = ["greenkeeper", "snyk"]
```

## Changelog workflow guidance

`repo-release-tools` supports two changelog workflows:

- `incremental` *(default)* — maintain `[Unreleased]` during development
- `squash` — skip per-commit changelog enforcement and generate/correct at release time

Minimal config:

```toml
[tool.rrt]
release_branch = "release/v{version}"
changelog_file = "CHANGELOG.md"
changelog_workflow = "incremental"  # or "squash"

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"
```

Helpful checks:

```bash
rrt config
rrt doctor
```

## Hook setup

### pre-commit

For the default incremental workflow, use the auto-write setup:

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

Install:

```bash
pre-commit install --hook-type pre-commit --hook-type commit-msg
```

If the repo prefers manual changelog edits, replace `rrt-update-unreleased`
with `rrt-changelog` instead of enabling both.

### lefthook

Requires `rrt-hooks` on `PATH`, which comes from the installed package.

```yaml
pre-commit:
  commands:
    rrt-branch-name:
      run: rrt-hooks pre-commit

commit-msg:
  commands:
    rrt-update-unreleased:
      run: rrt-hooks update-unreleased --message-file {1}
    rrt-commit-subject:
      run: rrt-hooks commit-msg {1}
```

## GitHub Action usage

Use the action when the user wants CI policy checks instead of local workflow automation:

```yaml
- uses: actions/checkout@v6

- uses: Anselmoo/repo-release-tools@v1.0.0
  with:
    check-branch-name: "true"
    check-commit-subject: "true"
    check-changelog: "true"
    changelog-strategy: "auto"
    check-doctor: "true"
```

## Release bump workflow

Always suggest `rrt doctor` before a release bump.

```bash
rrt doctor
rrt bump patch --dry-run
rrt bump patch
```

Useful flags:

- `--dry-run` to preview
- `--no-changelog` to skip changelog generation/update
- `--no-commit` to stage without committing
- `--force` to recreate an existing release branch
- `--no-pin-sync` to skip `pin_targets`

## Skill installation

This repository also ships an installed-CLI skill for Copilot, Claude, and Codex.
Install it into an agent skills directory with:

```bash
rrt skill install --target copilot-local
rrt skill install --target claude-local --target codex-local
rrt skill install --target copilot-global --dry-run
rrt skill install --target codex-global --force
```

Supported targets:

- `copilot-local` → `.copilot/skills`
- `claude-local` → `.claude/skills`
- `codex-local` → `.codex/skills`
- `copilot-global` → `~/.copilot/skills`
- `claude-global` → `~/.claude/skills`
- `codex-global` → `~/.codex/skills`

## Troubleshooting

### "rrt doctor" fails

Run:

```bash
rrt doctor
rrt config
```

Look for:

- missing `version_targets` files
- missing changelog file
- invalid `pin_targets` regexes
- version files that disagree in zero-config mode

### "Missing configuration"

Generate a starter config:

```bash
rrt init
rrt init --target pyproject
rrt init --target node
rrt init --target cargo
rrt init --target go
```

### "Which skill should I use?"

- Use `repo-release-tools` when `rrt` is already installed and you want local CLI commands.
- Use `repo-release-tools-uvx` when you want zero-install `uvx repo-release-tools ...` guidance.
