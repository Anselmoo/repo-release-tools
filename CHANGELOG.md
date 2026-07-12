## [Unreleased]

## [1.13.0] - 2026-07-12

### Added
- **release**: warn on pin_target version drift in release check (#171)

### Fixed
- **release,mcp,docs**: polish pass on docs/MCP surface after publish-snapshot rollout (#170)
- **git**: force-remove excluded paths on orphan snapshot branch (#165) (#166)

## [1.12.0] - 2026-07-11
### Breaking Changes
- remove hooks.py legacy compat shim
- remove docs/markdown.py legacy compat shim

### Fixed
- **action**: use env-var indirection for `verbose` and `changelog-file` Action inputs instead of interpolating them directly into shell script text (SEC-001)
- **action**: correct the changelog-status grep so a populated `[Unreleased]` section is classified `dirty` instead of always falling through to `clean` (D8)
- **action**: build the `health-summary` output with `jq -nc` instead of string interpolation, preventing a `"` in the detected version from corrupting the JSON output (SEC-006)
- **mcp**: require a bearer token (`--auth-token` / `RRT_MCP_AUTH_TOKEN`) for the MCP server's `--transport http` mode, refusing to start an unauthenticated HTTP listener; `stdio` transport is unaffected (SEC-002)

## [1.11.2] - 2026-07-10
### Added
- Add exclude glob patterns to publish-snapshot targets and CLI flag
- Publish rrt-publish-snapshot pre-commit hook (manual stage)
- Add dedicated publish-snapshot GitHub composite action

## [1.11.1] - 2026-07-09

### Fixed
- **git**: make publish-snapshot's protected remote configurable (#136)
- **docs**: fix header layout collapse, missing favicon, and dead design tokens (#134)

### Documentation
- migrate Jekyll to Astro Starlight, port Reto design system (#130)

## [1.11.0] - 2026-07-05
### Added
- Add `rrt git publish-snapshot` to force-push a single-commit snapshot of tracked content to a secondary remote
- Refuse `publish-snapshot` when `--remote` resolves to the same URL as `origin`, normalized across URL forms
- Require `--yes-i-know-this-overwrites-remote-history` before `publish-snapshot` runs beyond a `--dry-run` preview
- Support `[tool.rrt.publish_targets.<name>]` config entries for `publish-snapshot` remote/branch/message defaults
- Add `rrt_publish_snapshot` MCP tool mirroring the CLI command's origin-equality safety guard

## [1.10.1] - 2026-06-26

### Added
- publish rrt-tag-check hook (pre-push)
- publish rrt-changelog-lint hook (pre-commit, hard-fail)
- publish rrt-config-validate and config-reference hooks
- add rrt-hooks config-validate and config-reference-check
- add 'rrt config reference' command and generate docs/rrt-config-reference.toml
- add schema-to-TOML config reference generator
- add rrt sync --bump mirror orchestration (commit/tag/dry-run)
- add [tool.rrt.upstream] commit_message config field
- add rrt-hooks sync wrapper, rrt-sync manifest entry, and upstream schema
- add rrt sync command for multi-provider version discovery
- parse and validate [tool.rrt.upstream] config
- add multi-provider version fetcher (npm, nuget, crates, packagist)
- add PyPI version fetcher (stdlib HTTP)
- add Version.sort_key and newer_versions helper
- publish rrt-tree-check, rrt-drift-check, and rrt-changelog-postcorrect hooks
- add rrt-hooks drift-check subcommand
- add rrt-hooks tree-check subcommand
- add check-artifacts input to GitHub Action
- add check-folder input to GitHub Action

### Fixed
- validate upstream commit_message template in rrt sync --bump
- remove double [DRY RUN] prefix in config reference dry-run header
- emit scalars before tables in config reference (correct TOML nesting)
- handle invalid --group in rrt sync with clean exit

### Changed
- move config-reference auto-update to a repo-local hook
- extract apply_version helper for bump and sync reuse
- import PROVIDERS as single source of truth for upstream validation
- remove unused _PROVIDERS set in sync providers

### Documentation
- document config-validate, config-reference, changelog-lint, and tag-check hooks
- migrate prose into source — hooks, bump, release, sync, action
- clarify pin_target_missing scope and remove misleading workspace bump note
- add dedicated rrt release check section to repo-health
- document kind='pattern' targets, pin_target_missing, and version_groups

## [1.10.0] - 2026-06-25

### Added
- pattern version target (#107)

## [1.9.1] - 2026-06-22
### Added

- `rrt release repair` — fix or recreate a release branch after a polluted PR. Verify mode (`rrt release repair`) walks every version target, pin target, and `[VERSION]`/`[Unreleased]` section and prints drift; `--yes` rewrites the drifted files and commits `chore(release): repair v{ver}`. Recreate mode (`--from BASE --yes`) rewinds the current branch to `BASE`, restores the `[VERSION]` body from HEAD (or `--changelog-from PATH`), and replays the bump as a single `chore: bump version to v{ver}` commit. Safety: writes a `repair/backup/<branch>-<ts>` ref before any destructive operation, refuses when the working tree is dirty or the branch is ahead of `origin/<branch>` (use `--force-allow-pushed`), and supports a `--hotfix` mode that implies `--yes` and tags the commit as `chore(release): repair v{ver}` for express recovery.
- `clear_unreleased_section(content, fmt)` public helper in `changelog.py` — removes every entry under `[Unreleased]` while keeping the header. Used by `rrt release repair` for the `changelog_unreleased_dirty` drift case.

### Fixed

- `rrt release repair` no longer aborts when a pin file exists but its configured pattern does not match. Both `_recreate` and `_apply_drift_fixes` now guard pin rewrites with `search_pattern`, mirroring the drift-detection rule and matching the verify-mode "no-match is not drift" policy.
- `rrt release repair` no longer duplicates the `[VERSION]` section when fixing `changelog_unreleased_dirty` drift. The two changelog drift kinds now take distinct fix paths: `changelog_missing_section` stamps a new section from the resolved body; `changelog_unreleased_dirty` clears `[Unreleased]` via the new `clear_unreleased_section` helper without touching the already-promoted versioned section below.
- `rrt release repair --yes` (verify+fix mode) now refuses to apply when the changelog lacks a `[VERSION]` section and no `--changelog-from PATH` was provided, instead of silently writing an empty release section and dropping the intended notes. The refuse message mirrors recreate mode's safety guard.

## [1.9.0] - 2026-06-10
### Added

- `rrt release notes --version VERSION` and `rrt release notes --latest-released` so CI release jobs can emit notes for the just-promoted section after `rrt bump`. Closes the failure mode where a tag-triggered release job ran `release notes` against an already-empty `[Unreleased]` section.
- `rrt release notes --output PATH` writes the rendered body to a file instead of stdout.
- `rrt tree PATH` positional argument as an ergonomic shorthand for `--root PATH`; the positional wins when both are given.
- `rrt tree --format json` emits a deterministic nested document with `name`, `is_dir`, `path`, and `children`.
- `rrt tree --format flat` emits one POSIX path per line and pairs with `--dirs-only` to render a pure folder skeleton for prompts.
- `rrt tree --absolute` switches `json` and `flat` outputs to absolute paths.
- `rrt tree --output PATH` writes the rendered tree to a file instead of stdout (warnings still surface on the printer).
- `rrt tree --fix-empty-dirs` gains a `git-rm` resolution action that stages the removal via `git rm -rf`, plus an `--auto-resolve {gitkeep,delete,hard,git-rm}` flag for unattended runs.
- `rrt project info` reads `name`, `version`, `description`, `authors`, `license`, and `urls` from `pyproject.toml`, `Cargo.toml`, or `package.json`. Supports `--format {text,json}`, `--key KEY`, and `--output PATH`.
- `rrt mcp tool new <name>` scaffolds a starter `mcp/tools/<name>_tools.py` mirroring the existing register pattern; supports `--title`, `--description`, `--into`, `--dry-run`, and `--force`.

### Changed

- `rrt release notes` empty-section error now names the requested section so CI logs make the failure obvious.

## [1.8.3] - 2026-06-06

### Added
- introduce obsolete status for hook-manager integrations and update related messaging (#95)

## [1.8.2] - 2026-06-05

### Added
- support incremental changelog strategy (#93)

## [1.8.1] - 2026-06-02

### Fixed
- readme banner reto style (#91)

## [1.8.0] - 2026-06-02
### Added

- `rrt tree --strict-empty-dirs` flag that exits 1 when untrackable empty
  directories are present (git cannot track empty directories, so these cause
  local/CI manifest drift).
- `rrt tree --fix-empty-dirs` interactive mode that adds `.gitkeep` or removes
  empty directories. Supports `--dry-run` and `--yes`.
- `phantom_empty_dirs` counter persisted in `.rrt/tree.lock.toml [snapshot]`
  for drift diagnostics.

### Changed

- `rrt tree` no longer warns about directories that already contain `.gitkeep`;
  the warning is reserved for truly untrackable empty directories.
- CI workflows now invoke `rrt tree --check --strict --strict-empty-dirs`
  so phantom-empty-dir drift fails fast in PRs.

## [1.7.0] - 2026-05-26

### Added
- **mcp**: rich Prefab UI dashboards, GenerativeUI, init form, and docs (#78)
- **docs**: add version-release documentation and implement format re… (#76)
- add artifacts integrity tracking with UI layer migration (#74)

### Fixed
- update documentation and commands to include generated-asset handling in bump process (#80)
- badge links in README.md (#79)
- tree lock (#77)
- add artifacts snapshot to resolve strict artifacts check failure
- add tree snapshot to resolve strict tree check failure
- add health snapshot to resolve strict doctor check failure (#75)

### Documentation
- add Husky v9 support to hooks.md alongside pre-commit and Lefthook (#72)

## [1.6.2] - 2026-05-20

### Added
- enhance PNG assets and improve banner rendering in banner.py (#70)

## [1.6.1] - 2026-05-19

### Added
- update and replace banner assets

### Documentation
- update ascii art (#68)

## [1.6.0] - 2026-05-18

### Added
- Enhance documentation generation and management features (#64)
- expand release workflow tooling (#63)
- **docs**: shell-language extraction (bash/fish/powershell), API index command, and extractor refactors (#62)

### Documentation
- repo injector (#61)

## [1.5.0] - 2026-05-13

### Added
- finalize hook and workspace automation updates (#58)

## [1.4.0] - 2026-05-10

### Added
- enhance documentation and add docstring checks (#55)

### Fixed
- docs minimum length (#56)

## [1.3.0] - 2026-05-08

### Added
- Enhance coverage instructions and add folder configuration tests (#52)

### Documentation
- fix all legacy H1 headers and add Jekyll frontmatter for consistent naming (#53)

## [1.2.0] - 2026-05-05
### Added
- `rrt eol` command and `rrt-hooks check-eol` hook for tracking language end-of-life (Python, Go, Node.js, Rust)
- `[tool.rrt.eol]` config block with `languages`, `warn_days`, `error_days`, `fetch_live`, `allow_eol`, and per-cycle `overrides`
- `rrt-eol-check` pre-commit hook definition and `check-eol` GitHub Action input
- EOL status integrated into `rrt doctor` when `[tool.rrt.eol]` is configured

### Changed
- `git.py` module docstring now documents all 11 workflow patterns and full command surface

## [1.1.0] - 2026-04-28

### Added
- Enhance CLI help and add mastery skill (#35)
- Add repo-release-tools CLI skill installation and evaluation features (#34)

## [1.0.0] - 2026-04-20

### Added
- enhance progress line handling with clear and overwrite functionalityru (#32)
- implement shared progress line and spinner updates for version bump and CI commands (#31)
- Add comprehensive tests for branch management and versioning features (#29)

### Fixed
- changelog squash (#30)

## [0.1.10] - 2026-04-19

### Added
- add --force option to bump command for resetting existing release branches (#26)
- enhance changelog management with unreleased section handling and coverage reporting (#24)

## [0.1.9] - 2026-04-18

### Added
- enhance glyph rendering with support for rounded and bold box styles, and improve terminal detection (#19)
- add support for python_version and go_version target kinds with… (#17)

## [0.1.8] - 2026-04-18

### Added
- add support for custom branch types and enhance validation for bot branches (#15)
- post-correction mode for changelog hook after squash merges (#13)

# Changelog

## [0.1.7] - 2026-04-06

### Added
- richer terminal glyph helpers, including table and boxed-rendering helpers
  plus tree and progress glyph groups in the shared registry
- shared display-width and right-padding utilities for terminal-safe alignment

### Changed
- panel rendering now keeps title, rows, separators, and borders at consistent
  width for branch and release summaries
- docs examples now reference `v0.1.7`

## [0.1.6] - 2026-04-05

### Added
- `rrt git` workflow commands for status, log, doctor, sync, move, commit,
  commit-all, squash-local, undo-safe, rebootstrap, and dirty-tree checks
- reusable dirty-tree enforcement through `rrt-hooks check-dirty-tree` and an
  optional GitHub Action input
- a dedicated glyph registry for compact Git and diff rendering in terminal
  output

### Changed
- CLI output now uses compact Git summaries and typed worktree entries for
  status-oriented commands
- documentation now includes a dedicated Git workflow page and a fuller
  `rrt git` command reference
