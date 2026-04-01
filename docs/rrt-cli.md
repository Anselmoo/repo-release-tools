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
rrt branch new feat "add parser"
rrt branch rescue fix "recover release work"
rrt bump patch
rrt bump minor --dry-run
rrt bump 1.2.3 --no-changelog
```

## Configuration files

`rrt` discovers configuration in this order:

1. `pyproject.toml`
2. `.rrt.toml`
3. `.config/rrt.toml`

All use the same `[tool.rrt]` table.

## Minimal config

```toml
[tool.rrt]
release_branch = "release/v{version}"
changelog_file = "CHANGELOG.md"

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"
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
