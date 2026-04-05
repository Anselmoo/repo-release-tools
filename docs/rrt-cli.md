# RRT CLI

The installed command is `rrt`.

## Install

```bash
pip install repo-release-tools
```

Or run it without installing:

```bash
uvx repo-release-tools branch new feat "add parser"
```

## Core commands

```bash
rrt init
rrt branch new feat "add parser"
rrt branch rescue fix "recover release work"
rrt bump patch
rrt bump minor --dry-run
rrt bump 1.2.3 --no-changelog
```

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
```

`rrt init` writes a recommended `.rrt.toml` in the repo root. It keeps branch
creation config-free, preserves zero-config bumping, and gives you an explicit
file when you want to tune release branches, changelog paths, generated files,
or custom version targets.

## Configuration files

`rrt` discovers configuration in this order:

1. `pyproject.toml`
2. `package.json`
3. `Cargo.toml`
4. `.rrt.toml`
5. `.config/rrt.toml`

All use the same `[tool.rrt]` table.
Use `.rrt.toml` or `.config/rrt.toml` for local repo config if you do not want
to keep release-tool settings in `pyproject.toml`.

- `pyproject.toml`, `.rrt.toml`, `.config/rrt.toml`: `[tool.rrt]`
- `package.json`: top-level `"rrt": { ... }`
- `Cargo.toml`: `[package.metadata.rrt]` or `[workspace.metadata.rrt]`

Go does not have a standard extensible manifest section like `package.json` or
`Cargo.toml`, so Go repos should use `.rrt.toml` or `.config/rrt.toml`.

## Minimal config

```toml
[tool.rrt]
release_branch = "release/v{version}"
changelog_file = "CHANGELOG.md"

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"
```

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
