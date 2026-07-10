# Data Objects — repo-release-tools

*Generated 2026-07-10. Status: **partial** — the workflow's DTO-catalog agent hit a
usage limit; this catalog lists the verified core types (class names and locations
confirmed by grep) without full field-level detail. Re-run the dto-catalog stage of
`modernize-extract-rules` for field tables if needed; in practice the frozen
dataclasses are self-documenting at the cited locations.*

## Core value types (frozen dataclasses, stdlib-only)

| Type | Location | Role | Consumed by rule areas |
|---|---|---|---|
| `Version` | `src/repo_release_tools/version/semver.py:24` | Parsed semver (major/minor/patch/pre/build); bump + sort-key logic | Semver bump math, version ordering, tag/release naming |
| `CalVersion` | `src/repo_release_tools/version/calver.py:31` | Parsed CalVer with inferred scheme | CalVer bump, scheme-inference heuristic |
| `EolRecord` | `src/repo_release_tools/eol/core.py:90` | One EOL cycle (release/eol dates, days-until) | EOL policy thresholds, exit codes |

## Config model (frozen dataclasses in `config/model.py`)

| Type | Location | Role |
|---|---|---|
| `VersionTarget` | `config/model.py:200` | One file+kind (pep621/package.json/go/python/pattern) whose version string `rrt bump` rewrites |
| `PinTarget` | `config/model.py:274` | Regex-pinned version string in docs/config kept in sync at bump |
| `GeneratedAsset` | `config/model.py:305` | Asset regenerated during bump |
| `ArtifactTarget` | `config/model.py:322` | Hashed artifact tracked in `.rrt/artifacts.lock.toml` |
| `PublishTarget` | `config/model.py:356` | Snapshot force-push destination (remote+branch) — P0 gate input |
| `VersionGroup` | `config/model.py:373` | Named group of targets bumped together |
| `EolOverride` / `EolConfig` | `config/model.py:405/414` | EOL policy configuration |
| `CommandGroupEntry` / `TopicPageEntry` / `SharedBlock` / `MapConfig` | `config/model.py:426-482` | Docs-engine configuration |

## Persistence schemas (TOML, file-based)

| Store | Owner | Notes |
|---|---|---|
| `[tool.rrt]` in pyproject / `.rrt.toml` / `Cargo.toml` / `package.json` | `config/core.py` (read), `commands/init.py` (write) | Four-source precedence — see BUSINESS_RULES.md config rules |
| `.rrt/docs.lock.toml`, `health.lock.toml`, `tree.lock.toml`, `artifacts.lock.toml` | `state.py:16-19` | Currency/staleness checks |
| `.rrt/drift.lock.toml` | `commands/drift_cmd.py:76` | **Ownership split** — filename defined outside state.py |
| `.rrt/docs_map.lock.toml` | `commands/docs_map_lock.py` | Same split |
| `CHANGELOG.md` (Keep-a-Changelog) | `changelog.py` (parse), `workflow/hooks.py` + `commands/bump.py` (write) | `[Unreleased]` is machine-managed |

## MCP response models (Pydantic, optional `[mcp]` extra)

12 model classes in `src/repo_release_tools/mcp/models.py` (e.g. `CommitValidationResult`,
publish-snapshot preview/force-push result) — the typed boundary of the MCP surface.
Per project convention (memory: pydantic-in-mcp), MCP tools return these, never raw dicts.

## The missing type (modernization target)

There is **no `BumpResult` / command-result type today** — commands print and return
`int`. The assessment's debt findings #2/#3/#9 and the brief's target architecture
introduce typed result objects (`BumpResult`, per-command `Options` dataclasses) as
the seam that unifies CLI/hooks/MCP and enables e2e assertion.
