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
2. **`rrt-hooks`** (`workflow/hooks.py`) — git hook runners invoked by pre-commit or lefthook; branch/commit/changelog validators and auto-writers
3. **GitHub Action** (`action.yml`) — composite action wrapping `rrt-hooks` for CI policy gates

### Key modules

| Module | Role |
|---|---|
| `cli.py` | Argparse entrypoint; custom help formatter with ANSI color |
| `commands/` | One file per subcommand: `branch`, `bump`, `ci_version`, `config_cmd`, `doctor`, `env_cmd`, `git_cmd`, `init`, `skill` |
| `commands/_common.py` | Shared `ConfigLoadError` extraction and classification helpers for command error handling. Centralizes config-load error parsing across `bump.py`, `doctor.py`, `release_notes.py`, `tag.py`, and related commands. |
| `commands/_version_render.py` | Renders `version/targets.py`'s `VersionWriteEvent` records to user output. Ensures `--dry-run` / applied output is consistent across `bump.py`, `workspace.py`, `ci_version.py`, `release_repair.py`, and MCP surface. |
| `commands/_tree_fix.py` | Interactive resolver for phantom (untrackable) empty directories. Invoked by `rrt tree --fix-empty-dirs`; prompts to add `.gitkeep` or delete each directory, honoring `--dry-run`, `--yes`, and `--auto-resolve`. |
| `workflow/hooks.py` | All `rrt-hooks` subcommands — runs during git hooks |
| `changelog.py` | Changelog parsing, `[Unreleased]` management, conventional commit → Keep-a-Changelog bullet. `SECTION_MAP` controls which commit type lands in which section (`chore/ci/build/test/deps` → Maintenance, which does **not** require a changelog entry) |
| `config/` | Configuration loading and model management — loads `[tool.rrt]` from `pyproject.toml`, `.rrt.toml`, `Cargo.toml`, or `package.json`. Contains `core.py` (parsing/discovery), `model.py` (type-safe config schema), and `docs_config.py` (docs-specific rules). |
| `version/targets.py` | Read/write versions across pep621, package.json, go_version, python_version, and custom regex targets |
| `version/semver.py` | Semantic versioning bump logic (MAJOR.MINOR.PATCH with pre-release/build support per semver 2.0). |
| `version/calver.py` | Calendar versioning bump logic (YYYY.MM, YYYY.MM.DD, YYYY.M.D schemes; bumps to current date or increments micro if today's version exists). |
| `workflow/git.py` | Low-level git helpers |
| `tools/inject.py` | Anchor-based file injection — shared by `rrt tree --inject`, `rrt docs inject`, and `rrt docs map` |
| `commands/docs_map.py` | Per-directory purpose-doc generator backing `rrt docs map`. Walks `[tool.rrt.docs.map].root`, emits anchor-wrapped Purpose + Tree + optional prompt blocks into `README.md` (configurable). Pure-functional core; no I/O outside `apply_to_file`. |
| `commands/docs_map_lock.py` | Drift detection for `rrt docs map`. Hashes each generated block and tracks it in `.rrt/docs_map.lock.toml` (separate from `docs.lock.toml`). `rrt docs map --check` exits non-zero on drift. |
| `state.py` | Sole owner of every `.rrt/*` lock/manifest filename (`docs`, `health`, `tree`, `artifacts`, `drift`, `docs_map`) plus their path helpers and drift comparators. Command modules import filenames from here rather than defining their own. |
| `ui/` | **Canonical public rendering API** — `color`, `font`, `glyphs`, `layout`, `syntax`, `prompt`, `messaging`, `progress`. Import from `repo_release_tools.ui` in all new code. |
| `mcp/` | Optional FastMCP 3.x server (install with `repo-release-tools[mcp]`) — exposes version, changelog, config, and git-workflow tools as first-class MCP resources for Claude Desktop, Copilot, Cursor, and compatible hosts. |

See [Internal Contracts](docs/src/content/docs/reference/internal-contracts.mdx) for the `.rrt/` lock schema, the hooks↔CLI parser-spec sharing contract, MCP/CLI surface parity, config source precedence, and the cross-surface exit-code/output convention.

### UI layer

`src/repo_release_tools/ui/` is the canonical public rendering API. Import helpers via the single consolidated block:

```python
from repo_release_tools.ui import (
    DryRunPrinter, bold, error, info, rule, success, terminal_width, warning,
)
```

New CLI output uses `DryRunPrinter` from `ui/messaging.py` (re-exported via `ui/__init__.py`).

## Key conventions

- **Branch naming**: `<type>/<kebab-slug>` — types: `feat`, `fix`, `refactor`, `perf`, `docs`, `chore`, `ci`, `build`, `test`, `deps`, `claude`, `codex`, `copilot`, `dependabot`, `renovate`
- **Conventional Commits** enforced: same type list as branches
- **Changelog**: Keep-a-Changelog format; `[Unreleased]` is auto-managed by `rrt-update-unreleased` — never edit it manually when the hook is active
- **Dry-run**: all mutating commands accept `--dry-run`; prototype with it first
- **No new runtime dependencies** for CLI/UI work
- **Coverage floor**: 85.71% — treat drops as a blocker; add tests before opening a PR. Low-coverage files: `ui/syntax.py`, `ui/color.py`, `ui/layout.py`, `ui/font.py`, `cli.py`
  - The local Stop hook (`coverage_non_regression.py`) allows a small margin during iteration so it doesn't false-block on stale/partial coverage state; `git push` (`check_push_coverage.py`) and CI always re-verify fresh at a hard 100%. See `.claude/hooks/README.md` for details.
- **Per-directory purpose docs**: when `[tool.rrt.docs.map]` is configured, `rrt docs map` generates an anchor-wrapped README.md per source directory and writes `.rrt/docs_map.lock.toml`. CI runs `rrt docs map --check` (via the `rrt-docs-map-check` hook) to fail on drift; the `rrt-docs-map-update` hook keeps files fresh on commit. Prose outside the `rrt-docs-map` anchors is preserved verbatim.

## Config

`[tool.rrt]` in `pyproject.toml` (also supported: `package.json` `"rrt"` key, `Cargo.toml` `[package.metadata.rrt]`, `.rrt.toml`). This repo uses `pep621` + `python_version` version targets and several `pin_targets` to keep doc version strings in sync with `rrt bump`.

## tox-uv — Multi-Python testing

`tox-uv` replaces tox's default virtualenv + pip with `uv`. The test matrix (3.12, 3.13, 3.14) mirrors CI.

```bash
# All three Python versions in parallel (recommended)
uvx --with tox-uv tox -p auto

# Single version
uvx --with tox-uv tox -e 3.14

# Pass extra pytest arguments
uvx --with tox-uv tox -e 3.14 -- tests/test_cli.py -xvs

# Compare two versions side by side
uvx --with tox-uv tox -e 3.13,3.14
```

**Debugging a version-specific failure:**
```bash
uvx --with tox-uv tox -e 3.14 -- -xvs          # full output
uvx --with tox-uv tox -e 3.14 --recreate        # rebuild env from scratch
```

**Adding a new Python version:** add to `env_list` in `[tool.tox]`, add to `matrix.python-version` in `.github/workflows/cicd.yml`, add the classifier under `[project]`.

`skip_missing_interpreters = true` silently skips any version not installed locally.

## Local docs development

```bash
# Regenerate all docs and assets:
uv run poe docs

# Inject TOC into group reference pages:
uv run poe docs-toc

# Serve locally with Astro's dev server at http://localhost:4321/:
uv run poe serve

# Build and serve the production build (base-aware, via astro preview) to simulate GitHub Pages exactly:
uv run poe preview
```

The 5 auto-generated command-group reference pages live in `docs/src/content/docs/commands/`:
`version-release.md`, `repo-health.md`, `git-workflow.md`, `ci-automation.md`, `setup-tooling.md`.
Regenerate with `uv run poe docs-generate`. TOC anchor stubs are embedded in their H1; fill
them with `uv run poe docs-toc`.
