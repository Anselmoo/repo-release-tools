# Semantic branches for trunk-based development

`repo-release-tools` uses semantic branch names to keep short-lived trunk-based
work understandable to humans, hooks, and automation.

## Standard format

```text
<type>/<kebab-case-description>
```

Examples:

- `feat/add-config-discovery`
- `fix/handle-tag-workflows`
- `docs/split-readme-into-docs`

## Supported semantic types

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

Special branch names:

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
commit semantics still belong in the commit subject.

## Why this fits trunk-based development

Semantic branches help teams:

- scan review queues quickly
- align branch intent with changelog policy
- keep automation predictable
- merge small changes back to trunk with less ambiguity

## Typical workflow

1. Branch from `main`
2. Use a semantic branch name
3. Keep commits small and conventional
4. Update `CHANGELOG.md` when needed
5. Merge back quickly
