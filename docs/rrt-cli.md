# RRT CLI

The installed command is `rrt`.

Use the CLI when you want the local developer workflow: branch helpers, version
bumps, config inspection, Git shortcuts, and release automation.

## Install

```bash
pip install repo-release-tools
```

Or run it without installing:

```bash
uvx repo-release-tools branch new feat "add parser"
```

## Quickstart

```bash
rrt init
rrt config
rrt skill install --target copilot-local
rrt branch new feat "add parser"
rrt git commit "add parser"
rrt git doctor
rrt bump patch
```

If your repo already has a simple `pyproject.toml`, `package.json`, or
`Cargo.toml`, `rrt bump` and `rrt ci-version` can often work without explicit
config. Run `rrt init` when you want `rrt` to write the current recommendation
into `.rrt.toml` or a native manifest file.

## Core commands

```bash
rrt init
rrt config
rrt skill install --target copilot-local
rrt branch new feat "add parser"
rrt branch rescue fix "recover release work"
rrt branch rename --type feat
rrt branch rename --scope cli
rrt branch rename fix "add helper" --scope utils
rrt git commit "add parser"
rrt git sync
rrt git diff
rrt git diff --staged
rrt bump patch
rrt bump patch --force
rrt bump minor --dry-run
rrt bump 1.2.3 --no-changelog
```

Use `rrt bump ... --force` when you need to recreate an existing release branch
from the chosen base after last-minute fixes, without deleting the branch by
hand first.

## Branch rename

Rename the **current** branch, updating any combination of type, scope, and
description without leaving the repo in a broken state.

```bash
# Change only the type — slug is kept as-is
rrt branch rename --type feat

# Prepend a scope to the existing slug
rrt branch rename --scope cli

# Change type + scope (slug kept)
rrt branch rename --type feat --scope cli

# Full rebuild: type inferred from current branch, new description
rrt branch rename fix add helper --scope utils

# Remove scope and restate description
rrt branch rename --no-scope feat "add parser"

# Preview without touching git
rrt branch rename --type docs --dry-run
```

### How it works

| What you provide | Behaviour |
|---|---|
| `--type` only | Replaces the `type/` prefix; slug unchanged |
| `--scope` only | Prepends `{scope}-` to the existing slug |
| description words | Rebuilds from scratch using `BranchName(type, description, scope)` |
| `--no-scope` + words | Rebuilds without any scope prefix |

`rrt branch rename` calls `git branch -m <old> <new>` — only a local rename,
no remote tracking branches are moved. Push the new name with
`git push origin :<old> <new>` or `git push --set-upstream origin <new>` as
needed.

## Git workflows

`rrt git` is intentionally not a full alias layer over raw Git. It focuses on
repeatable workflows that match `repo-release-tools` policy:

- `rrt git status` shows a compact branch summary and typed worktree entries
- `rrt git log` shows recent history in a compact `rrt`-styled view
- `rrt git doctor` checks branch policy, upstream state, dirty tree,
  merge/rebase blockers, sync drift, latest commit subject, and changelog risk
  in one report
- `rrt git sync-status` is the focused sync preflight view: it analyzes whether a
  merge/rebase is already in progress, whether unresolved conflicts remain, and
  whether the branch is behind or diverged from its sync base
- `rrt git diff` renders the working-tree diff with `rrt` glyph formatting —
  added, removed, and unchanged lines are styled distinctly. Use `--staged` to
  inspect staged changes before a commit, or `--against <ref>` to diff against
  any commit or ref
- `rrt git commit "message"` builds a conventional commit and infers the type
  from the current branch when possible
- `rrt git commit-all "message"` stages all files first, then creates the
  conventional commit
- `rrt git sync` fetches, auto-stashes when needed, then pulls with rebase by
  default, showing a compact branch/worktree summary in the preview panel
- `rrt git move <branch>` switches branches without dropping local changes
- `rrt git squash-local "message"` squashes local commits since upstream into
  one conventional commit
- `rrt git undo-safe` rewinds a commit while keeping work staged or unstaged
- `rrt git check-dirty-tree` exits non-zero when the working tree is dirty, for
  use in hooks and CI, with typed entries for dirty paths
- `rrt git rebootstrap` destroys history and creates a fresh initial history,
  guarded by an explicit confirmation flag; add `--hard-init` to recreate git
  metadata from scratch while leaving the working tree untracked behind one
  empty initial commit

See [Git magic](git-magic.md) for the design rationale and the full workflow
catalog.

## Config inspection

```bash
rrt config
```

`rrt config` reads the resolved configuration for the current repository and
prints it as a tree. It covers every version group: release branch, changelog
path, lock command, version targets (file path and detection kind), and
generated files.

When no explicit config exists, `rrt config` shows what `rrt` would auto-detect
in zero-config mode — the same picture that `bump` and `ci-version` would act
on. When a `[tool.rrt]` section is found, the output reflects the explicit
configuration as loaded.

```
┌ rrt config ────────────────────────┐
│ config file    │ (auto-detected)   │
├────────────────┼───────────────────┤
│ version groups │ 1 group           │
└────────────────┴───────────────────┘

└── [default]/
    ├── release_branch  release/v{version}
    ├── changelog       CHANGELOG.md
    ├── lock_command    uv lock -U
    ├── version_targets/
    │   ├── pyproject.toml ([project].version)
    │   └── src/pkg/__init__.py (__version__)
    └── generated_files/
        └── uv.lock
```

Run `rrt config` to answer "what does rrt know about this repo?" before your
first `rrt bump`.

## Zero-config mode

For basic versioning, `rrt` can work without `[tool.rrt]`.

- `bump` and `ci-version` auto-detect root-level `pyproject.toml`, `package.json`,
  and `Cargo.toml`
- If multiple version files are found, they are updated together
- Auto-detected files must already agree on the current version before `bump`
- Go does not have a standard in-file project version, so Go repos still need
  explicit config for file updates

Add `[tool.rrt]` later only when you want fine-tuning such as grouped releases,
custom release branches, changelog paths, lock commands, generated files, or
pattern-based targets. Run `rrt init` when you want `rrt` to write a
recommended `.rrt.toml` for the current repo shape.

## Init

```bash
rrt init
rrt init --dry-run
rrt init --force
rrt init --target pyproject
rrt init --target cargo
rrt init --target node
rrt init --target go
rrt init --target pyproject --dry-run
```

`rrt init` writes a recommended rrt configuration block for the current repository.

### Targets

| Flag | Output |
|---|---|
| *(default)* | Creates `.rrt.toml` in the repo root |
| `--target pyproject` | Appends `[tool.rrt]` to an existing `pyproject.toml` |
| `--target cargo` | Appends `[package.metadata.rrt]` to an existing `Cargo.toml` |
| `--target node` | Merges `"rrt": { ... }` into an existing `package.json` |
| `--target go` | Creates `.rrt.toml` with the recommended Go config, falling back to auto-detected targets when available |

`--target pyproject`, `--target cargo`, and `--target node` require the manifest file to already
exist. All targets auto-detect current version files to produce a tailored
config block. Use `--force` to overwrite `.rrt.toml` or the `package.json`
`"rrt"` key. Existing `pyproject.toml` and `Cargo.toml` rrt sections must be
edited manually instead of appending a duplicate table.

For **Node / JS / TS** repositories, `--target node` reads the existing `package.json`,
adds a top-level `"rrt"` key, and writes the file back with 2-space JSON indentation.

For **Go** repositories there is no standard extensible manifest section; both
`--target go` and the default `rrt init` write `.rrt.toml`. `--target go` uses
the Go-specific starter template when no existing version targets can be
auto-detected.

## Configuration files

`rrt` discovers configuration in this order:

1. `pyproject.toml`
2. `package.json`
3. `Cargo.toml`
4. `.rrt.toml`
5. `.config/rrt.toml`

Each file stores equivalent `rrt` config in its native format.
Use `.rrt.toml` or `.config/rrt.toml` for local repo config if you do not want
to keep release-tool settings in `pyproject.toml`.

- `pyproject.toml`, `.rrt.toml`, `.config/rrt.toml`: `[tool.rrt]`
- `package.json`: top-level `"rrt": { ... }`
- `Cargo.toml`: `[package.metadata.rrt]` or `[workspace.metadata.rrt]`

Go does not have a standard extensible manifest section like `package.json` or
`Cargo.toml`, so Go repos should use `.rrt.toml` or `.config/rrt.toml`.

## Skill install

Use `rrt skill install` to copy the bundled installed-CLI skill into an agent
skill directory:

```bash
rrt skill install --target copilot-local
rrt skill install --target claude-local --target codex-local
rrt skill install --target copilot-global --dry-run
rrt skill install --target codex-global --force
```

### Targets

| Target | Directory |
|---|---|
| `copilot-local` | `.copilot/skills` |
| `claude-local` | `.claude/skills` |
| `codex-local` | `.codex/skills` |
| `copilot-global` | `~/.copilot/skills` |
| `claude-global` | `~/.claude/skills` |
| `codex-global` | `~/.codex/skills` |

The command installs the bundled `repo-release-tools` skill. It refuses to
overwrite an existing installation unless `--force` is provided.

## Minimal config

```toml
[tool.rrt]
release_branch = "release/v{version}"
changelog_file = "CHANGELOG.md"
changelog_workflow = "incremental"  # or "squash"

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"
```

## Changelog workflows

`rrt` supports two changelog workflows so the CLI can match how a repository
actually merges work.

### `incremental` (default)

Use `incremental` when the repository maintains changelog state during regular
development.

- works well with `rrt-update-unreleased` or `rrt-changelog`
- keeps `[Unreleased]` current as changes land
- makes `rrt bump` default to the normal `auto` changelog behavior

### `squash`

Use `squash` when pull requests are squash-merged and per-commit changelog
updates would create noisy or misleading release notes.

- local changelog hooks skip changelog enforcement
- GitHub Action `changelog-strategy: auto` resolves to `release-only`
- `rrt bump` defaults to `generate` so release notes are built at release time

Set it in repo config:

```toml
[tool.rrt]
changelog_workflow = "squash"
```

## Custom branch types

By default the branch name validator accepts the standard conventional types
(`feat`, `fix`, `chore`, …), AI helper prefixes (`claude`, `codex`, `copilot`),
and bot prefixes (`dependabot`, `renovate`). To allow additional prefixes:

```toml
[tool.rrt]
extra_branch_types = ["greenkeeper", "snyk"]
```

Custom types follow the same passthrough rules as bot branches — their slugs
are not validated for kebab-case format or length.

Equivalent native examples:

```json
{
  "name": "example",
  "version": "1.2.3",
  "rrt": {
    "version_targets": [
      {
        "path": "package.json",
        "kind": "package_json"
      }
    ]
  }
}
```

```toml
[package]
name = "example"
version = "1.2.3"

[package.metadata.rrt]

[[package.metadata.rrt.version_targets]]
path = "Cargo.toml"
section = "package"
field = "version"
```

## Version target modes

- `kind = "pep621"` for `[project].version`
- `kind = "package_json"` for the top-level `version` in `package.json`
- `pattern` for regex-driven replacements
- `section` + `field` for TOML field updates

## Generated files

Use `generated_files` for lockfiles or other generated artifacts that should be
staged with a bump:

```toml
[tool.rrt]
lock_command = ["pnpm", "install", "--lockfile-only"]
generated_files = ["pnpm-lock.yaml"]
```

Default lock refresh is auto-detected when possible:

- `package.json`: `pnpm install`, `yarn install`, or `npm install`
- Poetry: `poetry lock`
- Rust: `cargo update --workspace` when `Cargo.lock` is present
- Go-targeted repos: `go mod tidy`, staging `go.mod` and `go.sum`

## Hybrid repositories

For repos with multiple release surfaces, use `version_groups` and select the
group explicitly with `--group` when needed.

```toml
[tool.rrt]
default_group = "python"

[[tool.rrt.version_groups]]
name = "python"
release_branch = "release/python/v{version}"
generated_files = ["uv.lock"]
version_source = "pyproject.toml"

[[tool.rrt.version_groups.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[[tool.rrt.version_groups]]
name = "web"
release_branch = "release/web/v{version}"
generated_files = ["pnpm-lock.yaml"]
version_source = "package.json"

[[tool.rrt.version_groups.version_targets]]
path = "package.json"
kind = "package_json"
ci_format = "pep440"
```

Examples:

```bash
rrt bump patch --group web
rrt ci-version compute --group python
rrt ci-version apply 1.4.0.dev1201 --group web
```

## Pin targets — auto-sync doc/CI version pins

`pin_targets` lets you declare files that contain version pins (e.g. GitHub Action refs, pre-commit `rev:` tags) and have `rrt bump` update them automatically alongside the main version bump.

### Config

Add entries to `pyproject.toml` (or `.rrt.toml`) using a 3-group capture pattern:
`(prefix)(bare_semver)(suffix)` — groups 1 and 3 are kept verbatim; group 2 is replaced.

```toml
# Global — applies to all version groups
[[tool.rrt.pin_targets]]
path = "docs/github-action.md"
pattern = '(Anselmoo/repo-release-tools@v)(\d+\.\d+\.\d+)()'

[[tool.rrt.pin_targets]]
path = "docs/pre-commit.md"
pattern = '(rev: v)(\d+\.\d+\.\d+)()'

# Per-group — only applied when bumping that group
[[tool.rrt.version_groups.pin_targets]]
path = "README.md"
pattern = '(badge/version-v)(\d+\.\d+\.\d+)(-blue)'
```

### Behavior

- Runs after version string updates, before changelog and git commit.
- Files are staged alongside the main version files.
- If a pattern matches multiple lines, all occurrences are updated.
- A warning is printed when the pattern produces no match.
- Already-current pins are left unchanged and a status line is printed.

### Skip flag

```bash
rrt bump minor --no-pin-sync   # skip pin_targets for this run
```

## Health checks — rrt doctor

`rrt doctor` verifies that the current `[tool.rrt]` configuration is internally
consistent and all referenced files are reachable:

```bash
rrt doctor
```

It produces a tree report — green `✔` for passing checks, red `✖` for failures.

### What it checks

| Check | Pass condition | Failure condition |
|---|---|---|
| Version target files | File exists at the declared path | File not found → exits 1 |
| Version target readability | Version string can be read from the file | Unreadable → warning only, exits 0 |
| Pin target files | File exists at the declared path | File not found → exits 1 |
| Pin target patterns | Pattern compiles and matches in the file | No match → warning only, exits 0 |
| Changelog file | File exists at `changelog_file` | File not found → exits 1 |

### Exit behavior

- Exits `0` when all checks pass.
- Exits `1` when any check fails. Failing checks print a message under `✖`.

### Usage in CI

```yaml
- uses: Anselmoo/repo-release-tools@v0.1.10
  with:
    check-doctor: "true"
```

Or run directly in a workflow step:

```bash
uvx --from repo-release-tools rrt doctor
```

Run `rrt doctor` before `rrt bump` to confirm targets are set up correctly.
