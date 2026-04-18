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
