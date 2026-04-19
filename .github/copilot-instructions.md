# repo-release-tools — Agent Instructions

Config-driven CLI + GitHub Action + pre-commit hooks for semantic versioning, conventional commits, and changelog automation across Python, Node, Rust, and Go.

## Build & test

```bash
uv sync --all-groups                      # install deps
uv run pytest -q -m "not runtime"        # unit tests (fast)
uv run pytest -q -m runtime tests/test_runtime_hybrid.py  # integration tests
uvx pre-commit run --all-files           # lint (ruff, line-length 100)
```

Python ≥ 3.12 required. Build system: `uv_build`.

## Module map

| Module | Role |
|---|---|
| `src/repo_release_tools/hooks.py` | All `rrt-hooks` subcommands — branch/commit/changelog validators and auto-writers |
| `src/repo_release_tools/changelog.py` | Changelog parsing, `[Unreleased]` management, conventional commit → bullet |
| `src/repo_release_tools/config.py` | Config loading from `pyproject.toml` / `.rrt.toml` / `Cargo.toml` / `package.json` |
| `src/repo_release_tools/version_targets.py` | Read/write versions in pep621, package.json, go_version, python_version, custom regex |
| `src/repo_release_tools/commands/` | `branch`, `bump`, `ci-version`, `config`, `git`, `init` command implementations |
| `action.yml` | Composite GitHub Action — wraps `rrt-hooks` for CI enforcement |
| `.pre-commit-hooks.yaml` | Pre-commit hook definitions (`rrt-branch-name`, `rrt-changelog`, `rrt-update-unreleased`, `rrt-commit-subject`, `rrt-dirty-tree`) |

## Key conventions

- **Conventional Commits** enforced: `feat`, `fix`, `refactor`, `perf`, `docs`, `chore`, `ci`, `build`, `test`, `deps`.
- **Branch naming**: `<type>/<kebab-slug>` — types match commit types plus `claude`, `codex`, `copilot`, `dependabot`, `renovate`.
- **Changelog**: Keep‑a‑Changelog format. `[Unreleased]` section is auto-managed; never edit it manually when using `rrt-update-unreleased`.
- **Version targets**: configured in `[tool.rrt.version_groups]` in `pyproject.toml`; auto-detected for single-file projects.
- **Dry-run first**: all mutating commands accept `--dry-run`. Always prototype with dry-run before executing.
- `SECTION_MAP` in `changelog.py` defines which commit types go to which changelog section (`feat` → Added, `fix` → Fixed, `chore/ci/build/test/deps` → Maintenance — Maintenance commits do **not** require a changelog entry).

## Three product surfaces

1. **`rrt` CLI** — developer workflow (`branch new`, `bump`, `git commit`, `init`)
2. **`rrt-hooks`** — git hook runners invoked by pre-commit or lefthook
3. **GitHub Action** (`Anselmoo/repo-release-tools@v…`) — CI policy gates

See [docs/](../docs/) for detailed usage of each surface.

## Docs

- [Pre-commit & lefthook hooks](../docs/pre-commit.md)
- [GitHub Action](../docs/github-action.md)
- [CLI reference](../docs/rrt-cli.md)
- [Semantic branch naming](../docs/semantic-branches.md)
- [Git workflow helpers](../docs/git-magic.md)
- [Agent implementation guide](../docs/agent-intructions.md)
