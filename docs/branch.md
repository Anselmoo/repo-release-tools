# Conventional branches for trunk-based publishing

`repo-release-tools` uses conventional branches to keep trunk-based publishing
predictable for humans, hooks, and automation.

This page is generated from `repo_release_tools.commands.branch.SEMANTIC_BRANCHES_DOC`.
The canonical command reference is [docs/rrt-cli.md](rrt-cli.md). This page
summarizes the naming rules that the CLI and hooks enforce.

## Standard format

```text
<type>/<kebab-case-description>
```

Examples:

- `feat/add-config-discovery`
- `fix/handle-tag-workflows`
- `docs/split-readme-into-docs`

## Built-in branch types

Conventional branch types are accepted out of the box:

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

## Special names

These branch names are also valid:

- `main`
- `master`
- `develop`
- `release/v<semver>`

`release/v<semver>` is validated as a semver-aware special case, not as a free
form `type/slug` branch.

## AI helper branches

Branches created by assistant-driven workflows are accepted with these prefixes:

- `claude/...`
- `codex/...`
- `copilot/...`

They still use normal slug validation, so the suffix should stay lowercase and
kebab-cased.

## Bot and custom branches

Branches created by dependency bots are accepted too:

- `dependabot/...`
- `renovate/...`

Custom prefixes can be added through configuration:

```toml
[tool.rrt]
extra_branch_types = ["greenkeeper", "snyk"]
```

Bot and custom prefixes are treated as passthrough types. Their suffixes are
only required to be non-empty, because upstream tools often generate slugs with
slashes or underscores.

## Why the rules matter

- branch names stay readable in review queues
- commit subjects and branch types stay aligned
- release automation can distinguish ordinary work from release branches
- hooks and CI can apply one consistent policy across local and remote checks

## Related commands

- `rrt branch new`
- `rrt branch rescue`
- `rrt branch rename`
- `rrt git commit`
- `rrt git doctor`
