# repo-release-tools

`repo-release-tools` provides a small CLI for branch naming and version bumps in
Git repositories. The installed command is `rrt`.

## Install

```bash
pip install repo-release-tools
```

## Commands

```bash
rrt branch new feat "add parser"
rrt branch rescue fix "recover release work"
rrt bump patch
rrt bump minor --dry-run
rrt bump 1.2.3 --no-changelog
```

or via [`uvx`](https://docs.astral.sh/uv/concepts/tools/#tool-versions):

```bash
uvx repo-release-tools branch new feat "add parser"
```

## Configuration

Configure consumer repositories in `pyproject.toml`:

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
pattern = '^(\\s*__version__\\s*=\\s*")([^"]+)(")'

[[tool.rrt.version_targets]]
path = "Cargo.toml"
section = "workspace.package"
field = "version"
```

Version targets support two modes:

- `kind = "pep621"` for `[project].version` in `pyproject.toml`
- a regex target using `pattern`, or a TOML-style target using `section` and `field`

The `branch` commands are generic. The `bump` command is config-driven.

## pre-commit integration

This repo publishes hooks in `.pre-commit-hooks.yaml` so other repositories can reuse the naming checks directly.

Example:

```yaml
repos:
  - repo: https://github.com/Anselmoo/repo-release-tools
    rev: v0.1.0
    hooks:
      - id: rrt-branch-name
      - id: rrt-commit-subject
```

The hooks enforce:

- `rrt-branch-name`: `<type>/<kebab-case-description>`, plus `main`, `master`, `develop`, and `release/v<semver>`
- `rrt-commit-subject`: Conventional Commits such as `feat(cli): add hook checks`

## GitHub Action

This repo also ships a reusable composite action in `action.yml`.

Example:

```yaml
- uses: actions/checkout@v6

- uses: Anselmoo/repo-release-tools@v0.1.0
  with:
    check-branch-name: "true"
    check-commit-subject: "true"
```

The shared validation logic lives in `repo_release_tools.hooks`, so the pre-commit hooks and GitHub Action stay in sync.

## License

`repo-release-tools` is released under the MIT License

Built with ❤️ for safe, simple release automation.
