---
name: repo-release-tools-uvx
description: 'Automate Git releases with semantic versioning and conventional commits. Use when: managing release branches, bumping versions safely, automating release workflows without local installation, running health checks, auto-writing changelog bullets, renaming branches, or setting up lefthook. Use uvx for zero-install access.'
argument-hint: 'What release task? (branch new|rescue|rename, bump patch|minor|major, doctor, init, config, or dry-run preview)'
---

# Automated Release Workflows with repo-release-tools

## The Problem

Manual releases are error-prone: inconsistent branch names, version bumps in wrong places, forgotten changelog entries, accidental commits to production branches. Teams need a consistent, repeatable, auditable pipeline from feature work through release.

## The Solution

`repo-release-tools` (`rrt`) enforces **semantic versioning** + **conventional commits** through a CLI that:
- Creates and renames properly-named feature/fix branches with conventional types
- Bumps versions atomically across multiple files (Python `__version__`, TOML, Cargo, package.json)
- Auto-writes changelog bullets from commit subjects (`rrt-update-unreleased` hook)
- Updates pin targets (GitHub Action refs, pre-commit `rev:` tags) alongside every bump
- Creates release branches with proper naming (`release/v1.2.3`)
- Health-checks rrt configuration with `rrt doctor`
- Integrates with pre-commit, lefthook, and GitHub Actions

The philosophy: releases should be **declarative** (one command), **auditable** (dry-run before executing), and **consistent** (same workflow everywhere).

## Why Use This Skill

- **Zero-install**: `uvx` runs the tool without pip/homebrew/npm installation
- **Atomic operations**: Version bumps happen across all targets simultaneously
- **Auto-changelog**: `rrt-update-unreleased` writes bullets directly into `[Unreleased]` on every commit
- **Pin sync**: `pin_targets` keeps GitHub Action refs and pre-commit `rev:` in step with every bump
- **Health checks**: `rrt doctor` / `rrt-hooks doctor` verify all targets before you release
- **CI/CD ready**: GitHub Actions support for automated policy enforcement
- **Dry-run first**: Preview changes before modifying repository state

## Installation Methods

### Recommended: uvx (Zero-Install)

Best for: CI/CD, scripts, temporary workflows, trying the tool

```bash
uvx repo-release-tools branch new feat "add parser"
uvx repo-release-tools bump minor --dry-run
uvx repo-release-tools doctor
```

**Why**: No installation step, no version conflicts, always runs the latest version.

### Alternative: pip / uv tool (Persistent Install)

Best for: Daily use, lefthook integration, local development

```bash
pip install repo-release-tools        # or: uv tool install repo-release-tools
rrt branch new feat "add parser"
rrt bump patch
rrt doctor
```

## When to Use This Skill

✅ **Use when:**
- Starting a feature or bug fix (need conventional branch naming)
- Renaming an in-progress branch to fix type, scope, or description
- Preparing a release (need to bump versions + pins consistently)
- Setting up auto-changelog via hooks (lefthook or pre-commit)
- Setting up CI/CD validators (branch name, commit message, changelog checks)
- Running a config health check before releasing (`rrt doctor`)
- Squashing diverged changelog micro-commits after a squash merge

❌ **Skip when:**
- Your team doesn't use semantic versioning
- Manual releases work fine and rarely have errors

## Core Workflows

### Workflow 1: Starting a Feature

```bash
# Preview the branch (won't create it)
uvx repo-release-tools branch new feat "add user authentication" --dry-run

# Create it
uvx repo-release-tools branch new feat "add user authentication"
git push -u origin
```

### Workflow 2: Renaming the Current Branch

Use when you mistyped the type, forgot a scope, or need to rebuild the slug.

```bash
# Change only the type — slug kept as-is
rrt branch rename --type fix

# Add a scope to the existing slug
rrt branch rename --scope auth

# Full rebuild (type inferred from current branch)
rrt branch rename fix "repair login" --scope auth

# Remove scope and restate description
rrt branch rename --no-scope feat "add parser"

# Preview without touching git
rrt branch rename --type docs --dry-run
```

`rrt branch rename` calls `git branch -m <old> <new>` — local rename only. Push
the new name with `git push origin :<old> <new>` or `git push --set-upstream origin <new>`.

### Workflow 3: Preparing a Release

```bash
# Step 1: Health check first
rrt doctor

# Step 2: Preview the bump
uvx repo-release-tools bump patch --dry-run
# Shows: current → new version, branch name, all files that will change

# Step 3: Execute
uvx repo-release-tools bump patch

# Step 4: Push
git push -u origin release/v1.0.1
```

**`bump` options**:
- `bump patch` / `bump minor` / `bump major` / `bump 1.2.3` — version increment
- `--dry-run` — preview without changes
- `--no-changelog` — skip changelog update
- `--no-commit` — stage only, for manual review
- `--force` — recreate an existing release branch after last-minute fixes
- `--no-pin-sync` — skip `pin_targets` for this run

### Workflow 4: Emergency Hotfixes

```bash
uvx repo-release-tools branch rescue fix "critical authentication bypass"
# Creates: rescue/fix/critical-authentication-bypass
```

### Workflow 5: Health Check Before Release

```bash
rrt doctor
# or via hooks runner:
rrt-hooks doctor
```

Shows a tree of every version target (file exists + version readable), every pin
target (file exists + pattern compiles + pattern matches), and the changelog file.
Exits 0 when all checks pass, 1 when any hard check fails.

### Workflow 6: Initialising a New Repository

```bash
rrt init                   # writes .rrt.toml
rrt init --target pyproject  # appends [tool.rrt] to pyproject.toml
rrt init --target cargo      # appends to Cargo.toml
rrt init --target node       # merges "rrt": {...} into package.json
rrt init --dry-run           # preview without writing
```

### Workflow 7: Inspecting Resolved Config

```bash
rrt config
```

Prints every version group, release branch pattern, changelog path, lock command,
version targets, and generated files — exactly what `bump` would act on.

### Workflow 8: Squash-Merge Changelog Cleanup

After a squash merge, `rrt-update-unreleased` may have added per-micro-commit
bullets that cancel each other out or duplicate. Clean up with:

```bash
# Run on the default branch after the squash merge lands
rrt-hooks changelog post-correct          # dry mode — shows what would change
rrt-hooks changelog post-correct --commit  # rewrites + creates follow-up commit
```

Can also run as a GitHub Actions step post-merge:

```yaml
- name: Consolidate changelog after squash merge
  if: github.event_name == 'push' && github.ref == 'refs/heads/main'
  run: uvx --from repo-release-tools rrt-hooks changelog post-correct --commit
```

---

## Configuring Your Repository

`rrt` discovers config in this order: `pyproject.toml` → `package.json` →
`Cargo.toml` → `.rrt.toml` → `.config/rrt.toml`. Each stores the same settings
in its native format.

### Minimal config

```toml
[tool.rrt]
release_branch = "release/v{version}"
changelog_file = "CHANGELOG.md"

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"
```

### Full example with pin targets

```toml
[tool.rrt]
release_branch = "release/v{version}"
changelog_file = "CHANGELOG.md"
lock_command = ["uv", "lock", "-U"]

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[[tool.rrt.version_targets]]
path = "src/my_package/__init__.py"
pattern = '^(\s*__version__\s*=\s*")([^"]+)(")'

# Auto-update GitHub Action refs and pre-commit rev: tags on every bump
[[tool.rrt.pin_targets]]
path = "docs/github-action.md"
pattern = '(Anselmoo/repo-release-tools@v)(\d+\.\d+\.\d+)()'

[[tool.rrt.pin_targets]]
path = ".pre-commit-config.yaml"
pattern = '(rev: v)(\d+\.\d+\.\d+)()'
```

`pin_targets` use a 3-group capture pattern: group 1 and 3 are preserved verbatim;
group 2 (the bare semver) is replaced. All occurrences are updated.

### Version target modes

| Mode | Use case |
|---|---|
| `kind = "pep621"` | `[project].version` in `pyproject.toml` |
| `kind = "package_json"` | Top-level `version` in `package.json` |
| `pattern` | Regex replacement in any file format (3 groups) |
| `section` + `field` | TOML path lookup (e.g. `workspace.package`) |

### Zero-config mode

For basic versioning, `rrt` can work without `[tool.rrt]` — it auto-detects
root-level `pyproject.toml`, `package.json`, and `Cargo.toml`. Auto-detected
files must already agree on the current version before `bump`.

### Hybrid repositories (version groups)

```toml
[tool.rrt]
default_group = "python"

[[tool.rrt.version_groups]]
name = "python"
release_branch = "release/python/v{version}"

[[tool.rrt.version_groups.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[[tool.rrt.version_groups]]
name = "web"
release_branch = "release/web/v{version}"

[[tool.rrt.version_groups.version_targets]]
path = "package.json"
kind = "package_json"
```

```bash
rrt bump patch --group web
rrt ci-version compute --group python
```

---

## Hook Integration

### pre-commit (Python-native hook runner)

```yaml
# .pre-commit-config.yaml
default_install_hook_types: [pre-commit, commit-msg]

repos:
  - repo: https://github.com/Anselmoo/repo-release-tools
    rev: v0.1.10
    hooks:
      - id: rrt-branch-name        # pre-commit: validate branch name
      - id: rrt-update-unreleased  # commit-msg: auto-write changelog bullet
      - id: rrt-commit-subject     # commit-msg: validate conventional commit
      - id: rrt-changelog          # pre-commit: require staged changelog for feat/fix
```

Install:

```bash
pre-commit install --hook-type pre-commit --hook-type commit-msg
```

Optional hooks:
- `rrt-dirty-tree` — fail on uncommitted changes; best at `pre-push` or `manual` stage
- `rrt-doctor` — health-check rrt config; run as `manual` stage on demand

### lefthook (faster, language-agnostic)

Requires `uv tool install repo-release-tools` so `rrt-hooks` is on `$PATH`.

```yaml
# lefthook.yml
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

pre-push:
  commands:
    rrt-changelog:
      run: rrt-hooks check-changelog --subject "$(git log -1 --format=%s)" --strategy unreleased
```

### How `rrt-update-unreleased` works

On every `commit-msg` run it:
1. Parses the commit subject (conventional commit format).
2. For `feat`, `fix`, `refactor`, `perf`, `docs` — appends a bullet under `## [Unreleased]` in `CHANGELOG.md`.
3. For `chore`, `ci`, `build`, `test`, `deps` — **silently skips** (Maintenance section; no entry required).
4. Writes and **stages** `CHANGELOG.md` so the update is part of the same commit.

### Known issue: duplicate bullets from changelog-meta commits

If you commit a "fix:" that itself contains changelog-related text (e.g.
`fix: update changelog entries`), `rrt-update-unreleased` adds a new bullet from
that subject, which then appears in subsequent hook runs. This creates
near-duplicate or contradictory entries in `[Unreleased]`.

**Solution A — squash before push** (recommended for iterative work):
```bash
# Squash local commits since upstream into one clean commit
rrt git squash-local "feat: add authentication module"
```

**Solution B — post-correct after squash merge** (recommended for shared branches):
```bash
rrt-hooks changelog post-correct --commit
```

**Solution C — `unreleased` changelog strategy** (avoids per-commit file checks):
Use `--strategy unreleased` on the pre-push guard. The `[Unreleased]` section
only needs to be non-empty, not contain a specific file diff. This decouples
changelog presence enforcement from per-commit writes.

### Changelog strategies

| Strategy | When the check passes |
|---|---|
| `per-commit` (default) | `CHANGELOG.md` appears in the commit's changed files |
| `unreleased` | `## [Unreleased]` section is non-empty |
| `release-only` | Check always skipped (changelog updated at release time only) |

Pass via CLI: `--strategy unreleased` or via Action: `changelog-strategy: "unreleased"`.

---

## GitHub Action Integration

```yaml
- uses: actions/checkout@v6

- uses: Anselmoo/repo-release-tools@v0.1.10
  with:
    check-branch-name: "true"
    check-commit-subject: "true"
    check-changelog: "true"
    changelog-strategy: "unreleased"   # or "per-commit" / "release-only"
    check-dirty-tree: "false"
    check-doctor: "false"              # set "true" to run rrt doctor in CI
```

**All inputs**:

| Input | Default | Description |
|---|---|---|
| `check-branch-name` | `"true"` | Validate branch naming convention |
| `check-commit-subject` | `"true"` | Validate conventional commit subject |
| `check-changelog` | `"true"` | Require changelog update for feat/fix commits |
| `changelog-strategy` | `"per-commit"` | `per-commit` / `unreleased` / `release-only` |
| `check-dirty-tree` | `"false"` | Fail when work tree has uncommitted changes |
| `check-doctor` | `"false"` | Run `rrt doctor` health checks (exits 1 on failures) |
| `branch-name` | — | Override the branch name to validate |
| `commit-subject` | — | Override the commit subject to validate |
| `changelog-file` | `"CHANGELOG.md"` | Path to changelog file |

Tag-triggered workflows skip branch-name validation automatically.

---

## Common Commands Reference

| Task | Command |
|---|---|
| Create feature branch | `rrt branch new feat "description"` |
| Create rescue branch | `rrt branch rescue fix "description"` |
| Rename current branch | `rrt branch rename --type fix --scope auth` |
| Bump patch version | `rrt bump patch` |
| Bump minor / major | `rrt bump minor` / `rrt bump major` |
| Set explicit version | `rrt bump 1.2.3` |
| Dry-run any command | Add `--dry-run` |
| Skip changelog | `--no-changelog` |
| Skip commit | `--no-commit` |
| Skip pin sync | `--no-pin-sync` |
| Health check config | `rrt doctor` |
| Inspect resolved config | `rrt config` |
| Init rrt config | `rrt init` |
| Squash local commits | `rrt git squash-local "message"` |
| Stage + commit helper | `rrt git commit "message"` |
| Post-squash cleanup | `rrt-hooks changelog post-correct --commit` |

---

## Troubleshooting

### "Missing [tool.rrt] configuration"
Run `rrt init` — it generates a tailored config for the current repo. Or add a
minimal `[tool.rrt]` block manually and verify with `rrt config`.

### Health check fails (rrt doctor)
`rrt doctor` exits 1 and prints `✖` markers for missing files or broken patterns.
Fix the flagged paths, then re-run `rrt doctor` to confirm all checks pass before bumping.

### "Branch already exists"
Use `--force` to recreate it: `rrt bump patch --force`.

### "Version replacement had no effect"
Test your pattern:
```python
import re
pattern = r'^(\s*__version__\s*=\s*")([^"]+)(")'
print(bool(re.search(pattern, open("src/pkg/__init__.py").read(), re.MULTILINE)))
```

### "Working tree has uncommitted changes"
Commit or stash first, or use `--dry-run` to preview without touching the tree.

### Duplicate / cancelling changelog bullets after squash merge
Run `rrt-hooks changelog post-correct --commit` on the default branch. It removes
exact duplicates and semantically-cancelling pairs (e.g. `add Node 26` / `remove Node 26`)
from the exact diff hunk introduced by the squash commit, leaving older release
sections untouched.

---

## Next Steps

- **Read more**: https://github.com/Anselmoo/repo-release-tools
- **Docs**: https://anselmoo.github.io/repo-release-tools/
- **Set up hooks**: Add pre-commit or lefthook config for automated enforcement
- **Integrate CI**: Use the GitHub Action for policy gates on pull requests
- **Health check**: Run `rrt doctor` before every release to catch config drift early
