# repo-release-tools

`repo-release-tools` is a small product for semantic branches, changelog policy,
and version bumps across local development, CI, and Copilot workflows.

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

Minimal config:

```toml
[tool.rrt]
release_branch = "release/v{version}"
changelog_file = "CHANGELOG.md"

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"
```

## Documentation

- [Docs index](docs/index.md)
- [RRT CLI](docs/rrt-cli.md)
- [GitHub Action](docs/github-action.md)
- [pre-commit](docs/pre-commit.md)
- [Skill](docs/skill.md)
- [Semantic branches](docs/semantic-branches.md)

## License

`repo-release-tools` is released under the MIT License.

Built with ❤️ for safe, simple release automation.
