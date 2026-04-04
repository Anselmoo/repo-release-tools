# Conventional branches for trunk-based publishing

`repo-release-tools` uses conventional branches to keep short-lived trunk-based
publishing understandable to humans, hooks, and automation.

This is a thin naming layer over trunk-based development. The repository stays
centered on small branches and fast merges, but branch names carry intent so
release automation can stay deterministic.

## Standard format

```text
<type>/<kebab-case-description>
```

Examples:

- `feat/add-config-discovery`
- `fix/handle-tag-workflows`
- `docs/split-readme-into-docs`

## Supported branch types

- `feat`
- `fix`
- `chore`
- `docs`
- `refactor`
- `test`
- `ci`
- `perf`
- `style`
- `build`

Special branch names still supported:

- `main`
- `master`
- `develop`
- `release/v<semver>`

## AI helper branches

For AI-assisted delivery flows, `repo-release-tools` also accepts:

- `claude/...`
- `codex/...`
- `copilot/...`

These are compatibility prefixes for assistant-managed branches. Conventional
commit semantics still belong in the commit subject, because changelog policy
and release notes are driven from commit messages.

## Why this fits trunk-based publishing

Conventional branches help teams:

- scan review queues quickly
- align branch intent with changelog policy
- keep automation predictable
- merge small changes back to trunk with less ambiguity
- keep release branches explicit when a version cut is being prepared

In practice this means:

- `feat/*` for feature work that should land back on trunk quickly
- `fix/*` for corrective changes
- `chore/*`, `docs/*`, `ci/*`, and similar types for supporting work
- `release/v<semver>` when you are preparing a publishable release branch

## Typical workflow

1. Branch from `main`
2. Use a conventional branch name
3. Keep commits small and conventional
4. Update `CHANGELOG.md` when needed
5. Merge back quickly
