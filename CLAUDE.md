# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & test

```bash
uv sync --all-groups                              # install deps (Python ≥ 3.12 required)
uv run pytest -q -m "not runtime"                # unit tests (fast)
uv run pytest -q -m runtime tests/test_runtime_hybrid.py  # integration tests
uvx pre-commit run --all-files                    # lint with ruff (line-length 100)

# Single test file
uv run pytest tests/test_cli.py -xvs

# Multi-Python matrix (3.12, 3.13, 3.14) — mirrors CI
uvx --with tox-uv tox -p auto
uvx --with tox-uv tox -e 3.14 -- tests/test_cli.py -xvs
```

## Architecture

Three product surfaces share the same codebase:

1. **`rrt` CLI** (`src/repo_release_tools/cli.py` → `commands/`) — developer workflow: `branch new`, `bump`, `git commit`, `init`, `skill install`
2. **`rrt-hooks`** (`hooks.py`) — git hook runners invoked by pre-commit or lefthook; branch/commit/changelog validators and auto-writers
3. **GitHub Action** (`action.yml`) — composite action wrapping `rrt-hooks` for CI policy gates

### Key modules

| Module | Role |
|---|---|
| `cli.py` | Argparse entrypoint; custom help formatter with ANSI color |
| `commands/` | One file per subcommand: `branch`, `bump`, `ci_version`, `config_cmd`, `doctor`, `env_cmd`, `git_cmd`, `init`, `skill` |
| `hooks.py` | All `rrt-hooks` subcommands — runs during git hooks |
| `changelog.py` | Changelog parsing, `[Unreleased]` management, conventional commit → Keep-a-Changelog bullet. `SECTION_MAP` controls which commit type lands in which section (`chore/ci/build/test/deps` → Maintenance, which does **not** require a changelog entry) |
| `config.py` | Config loading from `pyproject.toml` / `.rrt.toml` / `Cargo.toml` / `package.json` |
| `version_targets.py` | Read/write versions across pep621, package.json, go_version, python_version, and custom regex targets |
| `versioning.py` | Semver bump logic |
| `git.py` | Low-level git helpers |
| `ui/` | Terminal rendering: `color`, `font`, `glyphs`, `layout`, `syntax`, `prompt`, `messaging`, `progress` |
| `output.py` | **Legacy shim** — re-exports from `ui/` for backwards compatibility with `git.py`, `hooks.py`, and `version_targets.py`. Do not import from here in new code; use `ui` submodules directly |

### UI layer

`src/repo_release_tools/ui/` is the canonical terminal rendering API. `output.py` is a deprecated compatibility shim retained until `git.py`, `hooks.py`, and `version_targets.py` are migrated. New CLI output uses `DryRunPrinter` from `ui/messaging.py`.

## Key conventions

- **Branch naming**: `<type>/<kebab-slug>` — types: `feat`, `fix`, `refactor`, `perf`, `docs`, `chore`, `ci`, `build`, `test`, `deps`, `claude`, `codex`, `copilot`, `dependabot`, `renovate`
- **Conventional Commits** enforced: same type list as branches
- **Changelog**: Keep-a-Changelog format; `[Unreleased]` is auto-managed by `rrt-update-unreleased` — never edit it manually when the hook is active
- **Dry-run**: all mutating commands accept `--dry-run`; prototype with it first
- **No new runtime dependencies** for CLI/UI work
- **Coverage floor**: 85.71% — treat drops as a blocker; add tests before opening a PR. Low-coverage files: `ui/syntax.py`, `ui/color.py`, `ui/layout.py`, `ui/font.py`, `cli.py`, `output.py`

## Config

`[tool.rrt]` in `pyproject.toml` (also supported: `package.json` `"rrt"` key, `Cargo.toml` `[package.metadata.rrt]`, `.rrt.toml`). This repo uses `pep621` + `python_version` version targets and several `pin_targets` to keep doc version strings in sync with `rrt bump`.
