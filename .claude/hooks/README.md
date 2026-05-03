# Claude coverage hooks

This project uses two local Claude hooks for coverage safety:

- `coverage_non_regression.py` (`Stop`): blocks completion when current coverage is below policy floor and/or below baseline thresholds.
- `refresh_coverage_baseline.py` (`PostToolUse`): auto-refreshes `.claude/coverage-baseline.json` from `coverage.xml` after successful `pytest` commands.

## Auto-refresh behavior

`refresh_coverage_baseline.py` is intentionally non-blocking:

- Runs after tool execution (`PostToolUse`).
- Updates baseline only when:
  - command includes `pytest`, and
  - tool execution reports success, and
  - `coverage.xml` exists and can be parsed.
- If event payload is unknown, malformed, or missing success metadata, it **does not write**.

The baseline file schema is:

- `baseline_pct` — current line coverage in percent (rounded to 2 decimals)
- `source` — update source marker
- `captured_at` — ISO date (`YYYY-MM-DD`)

## Operational note

Because baseline is configured to auto-refresh after successful test runs, it can move up or down as test scope changes.
If you want stricter governance later, switch to explicit/manual refresh only.
