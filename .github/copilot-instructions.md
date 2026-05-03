# repo-release-tools — Agent Instructions

Config-driven CLI + GitHub Action + pre-commit hooks for semantic versioning, conventional commits, and changelog automation across Python, Node, Rust, and Go.

## Build & test

```bash
uv sync --all-groups                      # install deps
uv run pytest -q -m "not runtime"        # unit tests (fast)
uv run pytest -q -m runtime tests/test_runtime_hybrid.py  # integration tests
uvx pre-commit run --all-files           # lint (ruff, line-length 100)

# Multi-Python matrix (3.12, 3.13, 3.14)
uvx --with tox-uv tox -p auto
uvx --with tox-uv tox -e 3.14 -- tests/test_cli.py -xvs
```

Python ≥ 3.12 required. Build system: `uv_build`. Coverage floor: **85.71%** — treat drops as a blocker.

## Module map

| Module | Role |
|---|---|
| `src/repo_release_tools/hooks.py` | All `rrt-hooks` subcommands — branch/commit/changelog validators and auto-writers |
| `src/repo_release_tools/changelog.py` | Changelog parsing, `[Unreleased]` management, conventional commit → bullet |
| `src/repo_release_tools/config.py` | Config loading from `pyproject.toml` / `.rrt.toml` / `Cargo.toml` / `package.json` |
| `src/repo_release_tools/version_targets.py` | Read/write versions in pep621, package.json, go_version, python_version, custom regex |
| `src/repo_release_tools/commands/` | `branch`, `bump`, `ci_version`, `config_cmd`, `doctor`, `env_cmd`, `eol_check`, `git_cmd`, `init`, `skill`, `tree` |
| `src/repo_release_tools/tools/inject.py` | Anchor-based file injection shared by `rrt tree --inject` and `scripts/generate_cli_docs.py` |
| `src/repo_release_tools/ui/` | Canonical rendering API — import via `from repo_release_tools.ui import ...` |
| `action.yml` | Composite GitHub Action — wraps `rrt-hooks` for CI enforcement |
| `.pre-commit-hooks.yaml` | Pre-commit hook definitions (`rrt-branch-name`, `rrt-changelog`, `rrt-update-unreleased`, `rrt-commit-subject`, `rrt-dirty-tree`) |

## UI import pattern

Always import from the public surface — never from submodules:

```python
from repo_release_tools.ui import (
    DryRunPrinter, GLYPHS, bold, error, info, rule, success, terminal_width, warning,
)
```

Raw `print()` is forbidden outside `src/repo_release_tools/ui/`. Run `python3 scripts/check_no_raw_prints.py` to audit.

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

## rrt as an agentic workflow tool

`rrt` is used explicitly inside agent sessions — not just as a CLI for humans.
Every improvement to the tool extends what agents can do autonomously. Follow
these rules whenever an agent session touches this repo:

- **Create branches via `rrt branch new <slug>`** — never `git checkout -b` directly.
  This enforces the `<type>/<kebab-slug>` naming convention and validates the type.
- **Preview bumps with `rrt bump --dry-run`** before applying any version change.
- **Run `rrt doctor`** at the start of any session that modifies config, version
  targets, or lock settings to catch misconfiguration early.
- **Use `rrt-hooks` subcommands** (`rrt-hooks check-branch`, `rrt-hooks check-commit`,
  `rrt-hooks update-unreleased`) in CI steps and pre-commit — do not reimplement
  their logic inline.
- **When adding a new agentic capability**, check whether it belongs as a subcommand
  (`commands/`), a hook (`hooks.py`), or a skill (`.github/skills/`) before writing
  ad-hoc script code.
- **Document new agent-facing commands** in `docs/commands/` and register them in
  the skill that exposes them (`rrt-ux-design`, `repo-release-tools`, etc.).

## Coverage discipline (tests)

Coverage floor: **85.71%** — treat drops as a blocker. Full rules are in
[`.github/instructions/coverage-tests.instructions.md`](instructions/coverage-tests.instructions.md).

Key invariants:
- Confirm `Missing:` is empty in `--cov-report=term-missing` before declaring a file done.
- Patch *dependencies*, not the SUT, to reach dead-code-by-construction branches.
- Assert on what the SUT produces — not the raw input (`sha[:7]` truncates, etc.).
- Import private symbols at module level if used in ≥2 tests; otherwise import inline.

## Instruction maintenance

After completing any task, check whether the session revealed a gap in the existing
workspace instructions. If yes, update instructions before closing.

- After completing a task that required a post-fix (correcting previously written code
  or tests), add an imperative rule to the relevant instruction file that would have
  prevented the mistake.
- When a new pattern, workaround, or convention is discovered mid-session, capture it
  in `.github/instructions/<domain>.instructions.md` before the session ends.
- When editing an instruction file, check for contradictions with other rules in the
  same file and with this file before saving.
- Prefer adding to an existing scoped instruction file over adding to this file —
  the scoped file loads only when relevant.
- Never add time-sensitive phrasing to any instruction file ("until date X", "currently
  in beta", "as of version Y").
- Never duplicate a rule that already exists in another instructions file in scope.

## Scoped instruction files

These files auto-apply for matching paths — do not duplicate their rules here:

| File | Applies to | Purpose |
|---|---|---|
| [`instructions/coverage-tests.instructions.md`](instructions/coverage-tests.instructions.md) | `tests/**/*.py` | Full coverage discipline: per-line verification, mock patterns, assertion rules |
| [`instructions/repo-release-tools.instructions.md`](instructions/repo-release-tools.instructions.md) | `src/**/*.py` | CLI/UI conventions, import patterns, no-raw-print rule |
| [`instructions/tox-uv.instructions.md`](instructions/tox-uv.instructions.md) | `pyproject.toml` | Multi-Python matrix testing with tox-uv |

## Docs

- [GitHub Action guide](../docs/action.md)
- [CLI reference](../docs/commands/rrt-cli.md)
- [Hook setup (pre-commit & lefthook)](../docs/commands/hooks.md)
- [Semantic branch naming](../docs/commands/branch.md)
- [Git workflow helpers](../docs/commands/git_cmd.md)
- [Agent skills](../docs/commands/skill.md)
- [Doctor / health checks](../docs/commands/doctor.md)
- [Project tree command](../docs/commands/tree.md)
