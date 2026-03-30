---
name: repo-release-tools-uvx
description: 'Automate Git releases with semantic versioning and conventional commits. Use when: managing release branches, bumping versions safely, automating release workflows without local installation. Use uvx for zero-install access.'
argument-hint: 'What release task? (branch new|rescue, bump patch|minor|major, or dry-run preview)'
---

# Automated Release Workflows with repo-release-tools

## The Problem

Manual releases are error-prone: inconsistent branch names, version bumps in wrong places, forgotten changelog entries, accidental commits to production branches. Teams need a consistent, repeatable, auditable pipeline from feature work through release.

## The Solution

`repo-release-tools` (`rrt`) enforces **semantic versioning** + **conventional commits** through a CLI that:
- Creates properly-named feature/fix branches with conventional types (`feat`, `fix`, `chore`, etc.)
- Bumps versions atomically across multiple files (Python `__version__`, TOML, Cargo)
- Updates changelogs from git history
- Creates release branches with proper naming (`release/v1.2.3`)
- Integrates with git hooks and CI/CD for upstream validation

The philosophy: releases should be **declarative** (one command), **auditable** (dry-run before executing), and **consistent** (same workflow everywhere).

## Why Use This Skill

- **Zero-install**: `uvx` runs the tool without pip/homebrew/npm installation
- **Atomic operations**: Version bumps happen across all targets simultaneously
- **Pre-commit integration**: Validate branch names and commit messages automatically
- **CI/CD ready**: GitHub Actions support for automated release validation
- **Dry-run first**: Preview changes before modifying repository state

## Installation Methods

### Recommended: uvx (Zero-Install)

Best for: CI/CD, scripts, temporary workflows, trying the tool

```bash
uvx repo-release-tools branch new feat "add parser"
uvx repo-release-tools bump minor --dry-run
```

**Why**: No installation step, no version conflicts, always runs the latest version.

### Alternative: pip (Global Install)

Best for: Daily use, team standardization, local development

```bash
pip install repo-release-tools
rrt branch new feat "add parser"
rrt bump patch
```

**Why**: Single command `rrt` available anywhere; pin version in requirements for reproducibility.

### Development: uv tool (Project-Local)

Best for: Repository maintainers, complex lock commands, development

```bash
uv tool install .
rrt --help
```

**Why**: Project-local installation; lock command uses same `uv` environment as the project.

## When to Use This Skill

✅ **You should use this skill when:**
- Starting a feature or bug fix (need conventional branch naming)
- Preparing a release (need to bump versions consistently)
- Setting up CI/CD validators (branch name, commit message checks)
- Running dry-run previews before touching production branches
- Integrating with pre-commit hooks (automatic branch/commit validation)

❌ **You might not need this if:**
- Your team doesn't use semantic versioning
- Manual releases work fine and rarely have errors
- Testing version bump logic in multiple files simultaneously isn't a concern

## Core Workflows

### Workflow 1: Starting a Feature

**Goal**: Create a branch with proper conventional naming (`feat/`, `fix/`, etc.)

**Why**: Standardized names enable automated changelog generation from branch history.

```bash
# Preview the branch (won't create it)
uvx repo-release-tools branch new feat "add user authentication" --dry-run

# Output shows: Branch: feat/add-user-authentication, Commit: feat: add user authentication

# Create the real branch
uvx repo-release-tools branch new feat "add user authentication"
git push -u origin

# Now work, commit, push normally
```

### Workflow 2: Preparing a Release

**Goal**: Atomically bump versions, update changelog, create release branch

**Why**: Keeps version numbers in sync across files and creates an auditable record of changes

```bash
# Step 1: Preview what will happen
uvx repo-release-tools bump patch --dry-run

# Output shows:
#   Current: 1.0.0 → 1.0.1
#   Branch: release/v1.0.1
#   Would update: pyproject.toml, src/__init__.py, uv.lock
#   Would prepend CHANGELOG.md

# Step 2: Execute (for real)
uvx repo-release-tools bump patch

# Step 3: Push the release branch for review/merge
git push -u origin release/v1.0.1
```

**Options**:
- `bump patch` / `bump minor` / `bump major` — semantic version increments
- `bump 1.2.3` — explicit version
- `--dry-run` — preview without changes
- `--no-changelog` — skip changelog update
- `--no-commit` — stage files but don't commit (for manual review)

### Workflow 3: Emergency Hotfixes

**Goal**: Create a rescue branch for critical fixes

```bash
uvx repo-release-tools branch rescue fix "critical authentication bypass"

# Creates: rescue/fix/critical-authentication-bypass
# Commit message: fix: critical authentication bypass
```

**Why**: "rescue" branches signal urgent work; they're tracked separately from feature work.


## Release Philosophy: Principles

This tool embodies three core principles:

**1. Atomicity**
A release succeeds completely or fails completely. No partial updates, no forgotten files, no drift between version strings.

**2. Auditability**
Every release creates a git commit and branch with a clear history. The changelog is part of the repository. Anyone can review what changed and when.

**3. Consistency**
The same workflow works across all your projects. Feature naming, version increments, changelog format—standardized everywhere.

Add to `.pre-commit-config.yaml` for branch/commit validation:

```yaml
repos:
  - repo: https://github.com/Anselmoo/repo-release-tools
    rev: v0.1.0
    hooks:
      - id: rrt-branch-name
      - id: rrt-commit-subject
```

Then install and run:

```bash
pre-commit install
pre-commit run --all-files
```

## GitHub Action Integration

**What it does**: Validate release branches and commit messages in CI/CD.

**Why**: Catch policy violations before merge. Run version bump validations on pull requests.

```yaml
- uses: Anselmoo/repo-release-tools@v0.1.0
  with:
    check-branch-name: "true"
    check-commit-subject: "true"
```

**Use case**: Ensure only properly-formatted release PRs merge to `main`.

## Configuring Your Repository

Each repository that uses `repo-release-tools` needs a `[tool.rrt]` section in `pyproject.toml`.

**Why**: Version bumps must touch every place the version appears—Python files, lock files, package manifests. This config specifies all those targets.

```toml
[tool.rrt]
# Release branch naming pattern
release_branch = "release/v{version}"

# Changelog file (created by the tool)
changelog_file = "CHANGELOG.md"

# Lock command run during bump (optional; useful for projects with lock files)
lock_command = ["uv", "lock", "-U"]

# Version targets: every place version needs to appear
[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[[tool.rrt.version_targets]]
path = "src/my_package/__init__.py"
pattern = '^(\s*__version__\s*=\s*")([^"]+)(")'

[[tool.rrt.version_targets]]
path = "Cargo.toml"
section = "workspace.package"
field = "version"
```

### Version Target Modes

- **`kind = "pep621"`**: Update `[project].version` in `pyproject.toml` (Python standard)
- **`pattern`**: Regex with capture groups—updates any file format. Groups 1 & 3 are preserved; group 2 is replaced with new version
- **`section` + `field`**: TOML path lookup (e.g., `workspace.package` → `[workspace.package]`)

**Design principle**: All targets are atomic—either all succeed or all fail. This prevents partial updates.

## Common Commands

| Task | Command |
|------|---------|
| Create feature branch | `uvx repo-release-tools branch new feat "description"` |
| Create fix branch | `uvx repo-release-tools branch rescue fix "description"` |
| Bump patch version | `uvx repo-release-tools bump patch` |
| Bump minor version | `uvx repo-release-tools bump minor` |
| Bump major version | `uvx repo-release-tools bump major` |
| Set explicit version | `uvx repo-release-tools bump 1.2.3` |
| Dry-run any command | Add `--dry-run` flag |
| Skip changelog | Add `--no-changelog` flag |
| Skip commit | Add `--no-commit` flag |

## Troubleshooting & Common Issues

### "Missing [tool.rrt] configuration"

**What happened**: The tool couldn't find `[tool.rrt]` in your `pyproject.toml`.

**Fix**: Add the configuration section (see "Configuring Your Repository"). Even a minimal config works:

```toml
[tool.rrt]
[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"
```

### "Branch already exists"

**What happened**: You tried to create a release branch that already exists.

**Options**:
- Delete the old branch: `git branch -d release/v1.0.1`
- Choose a different version: `uvx repo-release-tools bump minor`
- Learn what happened: `git log release/v1.0.1 -1`

### "Version replacement had no effect"

**What happened**: The regex pattern didn't match the file format.

**Debug**:
```bash
# Check what the file actually looks like
cat src/my_package/__init__.py

# Verify your pattern matches (test in Python)
import re
pattern = r'^(\s*__version__\s*=\s*")([^"]+)(")'
with open("src/my_package/__init__.py") as f:
    if re.search(pattern, f.read(), re.MULTILINE):
        print("✓ Pattern matches!")
    else:
        print("✗ Pattern doesn't match—adjust it")
```

### "Working tree has uncommitted changes"

**What happened**: Your git repository has uncommitted files; the tool won't overwrite them.

**Options**:
- Commit your work: `git add . && git commit -m "..."`
- Stash it temporarily: `git stash`
- Preview first: `uvx repo-release-tools bump patch --dry-run`

## Next Steps

- **Read more**: https://github.com/Anselmoo/repo-release-tools
- **Set up pre-commit**: Add hooks to enforce branch naming automatically
- **Integrate with CI**: Use the GitHub Action for release validation
- **Customize**: Adjust `[tool.rrt]` to match your versioning needs
