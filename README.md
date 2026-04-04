# repo-release-tools

`repo-release-tools` is a small product for conventional branches, changelog
policy, and version bumps across local development, CI, and Copilot workflows.

## Product surfaces

- `rrt` CLI for branch and release commands
- [GitHub Action](https://github.com/features/actions) for policy checks in CI
- [pre-commit](https://pre-commit.com) hooks for local enforcement
- [Copilot CLI](https://github.com/features/copilot/cli) skill for zero-install guidance

## Minimal quickstart

```bash
pip install repo-release-tools
rrt branch new feat "add parser"
rrt bump patch
```

Or:

```bash
uvx repo-release-tools branch new feat "add parser"
```

For basic versioning, `bump` and `ci-version` can run without `[tool.rrt]` by
auto-detecting root-level `pyproject.toml`, `package.json`, and `Cargo.toml`.
If multiple version files are found they are updated together, and explicit
config becomes optional fine-tuning for groups, release branches, changelog
paths, lock commands, generated files, or custom patterns. Go repos still need
explicit config for file updates because Go has no standard in-file project
version.

Minimal config:

```toml
[tool.rrt]
release_branch = "release/v{version}"
changelog_file = "CHANGELOG.md"

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"
```

Native config is also supported in `package.json` (`"rrt": { ... }`) and
`Cargo.toml` (`[package.metadata.rrt]` / `[workspace.metadata.rrt]`). Go repos
should use `.rrt.toml` or `.config/rrt.toml`.

## Conventional Branching

`repo-release-tools` uses conventional branches as the next step after
trunk-based publishing. The idea is simple: keep branches short-lived, encode
intent in the branch name, and let release automation stay predictable.

The default pattern is `type/kebab-case-description`, for example
`feat/add-config-discovery` or `fix/handle-tag-workflows`.

This works well with conventional commits and changelog automation:

- branch type tells reviewers and automation what kind of change is coming
- commit subjects stay conventional for changelog generation
- release branches stay explicit, such as `release/v1.2.3`

See [Conventional branches](docs/semantic-branches.md) for the full branch model
and supported branch types.

## Documentation

- [Docs index](docs/index.md)
- [RRT CLI](docs/rrt-cli.md)
- [GitHub Action](docs/github-action.md)
- [pre-commit](docs/pre-commit.md)
- [Skill](docs/skill.md)
- [Conventional branches](docs/semantic-branches.md)

## License

`repo-release-tools` is released under the MIT License.

Built with ❤️ for safe, simple release automation.
