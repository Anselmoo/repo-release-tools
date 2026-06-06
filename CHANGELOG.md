## [Unreleased]

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
