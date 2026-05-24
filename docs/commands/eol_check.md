---
title: "rrt eol"
permalink: "/commands/eol_check/"
---
<!-- rrt:auto:start:page-header -->
<p><a href="https://github.com/Anselmoo/repo-release-tools"><picture>
  <source media="(prefers-color-scheme: dark)" srcset="../../assets/badges/github-reto-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="../../assets/badges/github-reto-light.svg">
  <img alt="GitHub" src="../../assets/badges/github-reto-dark.svg">
</picture></a></p>
<!-- rrt:auto:end:page-header -->


# rrt eol

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
warn_days   = 180
error_days  = 0
allow_eol   = false
fetch_live  = false

[[tool.rrt.eol.overrides]]
language = "python"
cycle    = "3.9"
eol      = "2026-06-01"
```

## Related docs

- [rrt eol (CLI)](rrt-cli.md)
- [rrt doctor](doctor.md)
- [GitHub Action](action.md)
- [pre-commit / lefthook](hooks.md)

<!-- rrt:auto:start:doc-footer -->
---

[↑ Docs index](https://github.com/Anselmoo/repo-release-tools/blob/main/docs/index.md) · [CLI reference](https://github.com/Anselmoo/repo-release-tools/blob/main/docs/commands/rrt-cli.md) · [Changelog](https://github.com/Anselmoo/repo-release-tools/blob/main/CHANGELOG.md) · [GitHub](https://github.com/Anselmoo/repo-release-tools)
<!-- rrt:auto:end:doc-footer -->
