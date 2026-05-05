Runtime end-of-life (EOL) tracking for repo-release-tools.

Supports Python, Go, Node.js, and Rust. Bundled data provides offline
operation; pass ``fetch_live=True`` to pull fresh data from
https://endoflife.date/api/v1/products/<slug>/.

Rust uses a rolling-release model — only the latest stable is supported.
The meaningful check for Rust is how many releases behind the host/project
minimum is, not a date-based deadline.

## Supported languages

| Keyword | Checked via | EOL model |
|---|---|---|
| `python` | `python --version` / `requires-python` | Date-based |
| `go` | `go version` / `go.mod` | Date-based (two latest minors supported) |
| `nodejs` / `node` | `node --version` / `engines.node` | Date-based (LTS only) |
| `rust` | `rustc --version` / `Cargo.toml` `rust-version` | Rolling-release (lag-based) |

Pass the lowercase keyword to `--language` or `languages` in `[tool.rrt.eol]`.

## Data sources

rrt ships a bundled snapshot of EOL data (updated with each release). This
enables fully offline operation with no external requests.

Pass `--fetch-live` to pull fresh records from
[endoflife.date](https://endoflife.date/api/v1/products/python/) for the current
invocation. Live data is never cached — the bundled snapshot is always the
default.

## Rust rolling-release model

Rust does not use date-based EOL windows. The community supports only the
latest stable release. rrt models this as a lag-based check:

- `RUST_WARN_LAG = 2` — warn if the detected version is 2 or more releases
  behind the latest stable
- `RUST_ERROR_LAG = 4` — error if 4 or more releases behind

These thresholds are not configurable in `[tool.rrt.eol]`; they reflect the
upstream support model.

## `[tool.rrt.eol]` configuration

Add to `pyproject.toml` (or `.rrt.toml`):

```toml
[tool.rrt.eol]
languages = ["python", "node"]
warn_days   = 180   # warn N days before EOL (default: 180)
error_days  = 0     # error on actual EOL by default
allow_eol   = false # downgrade EOL errors to warnings (default: false)
fetch_live  = false # refresh from endoflife.date at runtime (default: false)

# Per-cycle EOL date overrides (optional)
[[tool.rrt.eol.overrides]]
language = "python"
cycle    = "3.9"
eol      = "2026-06-01"   # ISO 8601
```

| Key | Type | Default | Description |
|---|---|---|---|
| `languages` | list[str] | `["python"]` | Languages to check |
| `warn_days` | int | `180` | Days-before-EOL warning threshold |
| `error_days` | int | `0` | Days-before-EOL error threshold |
| `allow_eol` | bool | `false` | Downgrade EOL failures to warnings |
| `fetch_live` | bool | `false` | Pull fresh data from endoflife.date |
| `overrides` | list | `[]` | Per-cycle EOL date overrides |

## Version detection

For each language rrt tries to detect two versions:

- **Host runtime** — the interpreter or toolchain installed on the current
  machine (e.g. `python --version`)
- **Project minimum** — the minimum version declared in the repository (e.g.
  `requires-python` in `pyproject.toml`)

| Language | Host detection | Project minimum detection |
|---|---|---|
| Python | `sys.version` | `requires-python` in `pyproject.toml` |
| Go | `go version` | `go` directive in `go.mod` |
| Node.js | `node --version` | `engines.node` in `package.json` |
| Rust | `rustc --version` | `rust-version` in `Cargo.toml` |

When a version cannot be detected, rrt reports `not detected` without failing
that specific check.

## EOL status labels

| Status | Meaning |
|---|---|
| `ok` | Version is supported with more than `warn_days` remaining |
| `info` | Version is supported but EOL date is unknown or far future |
| `warn` | EOL within `warn_days` days |
| `error` | EOL within `error_days` days or already past EOL |
| `unknown` | Version string could not be matched to a known cycle |

## Related docs

- [rrt eol (CLI)](rrt-cli.md)
- [rrt doctor](doctor.md)
- [GitHub Action](action.md)
- [pre-commit / lefthook](hooks.md)
