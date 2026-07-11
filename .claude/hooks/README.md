# Claude coverage hooks

This project uses local Claude hooks for workflow safety:

- `completeness_guard.py` (`Stop`): blocks completion when required hooks, agents, or skills are missing.
- `drift_guard.py` (`Stop`): blocks completion when `rrt drift check` detects stale agent-facing surfaces.
- `check_push_coverage.py` (`PreToolUse`, matcher `Bash`, fires on any `git push`): **the hard PR-submission gate.** Always re-runs `uv run pytest -q -m "not runtime"` from scratch and blocks the push if coverage is below 100.00%. Threshold is hardcoded (`THRESHOLD = 100.0`) and not configurable via environment — this is intentional, do not weaken it.
- `coverage_non_regression.py` (`Stop`, fires after every assistant turn): blocks completion when current coverage is below policy floor and/or below baseline thresholds. See "Local allowance band" below — this hook is intentionally looser than `check_push_coverage.py`.
- `refresh_coverage_baseline.py` (`PostToolUse`): auto-refreshes `.claude/coverage-baseline.json` from `coverage.xml` after successful `pytest` commands.

## Local allowance band (Stop hook only)

`coverage_non_regression.py` reads whichever `coverage.xml` happens to be on disk — it does **not** re-run
pytest itself. In a repo where multiple worktrees/agents can run narrower or mid-refactor test subsets
concurrently, a stale or partial `coverage.xml` left behind by an unrelated process can make this Stop
hook fire a false "coverage regressed" block on a turn that never touched coverage at all.

To absorb that noise without weakening enforcement anywhere it matters, `.claude/settings.json` passes
this hook a wider allowance than its own defaults, via the env vars it already supports:

```
TARGET_COVERAGE_PCT=90 MAX_ABSOLUTE_DROP_PCT=10 MAX_RELATIVE_DROP_PCT=10
```

- The hook's own defaults (used if these env vars are absent, e.g. when run standalone) are
  `TARGET_COVERAGE_PCT=100.0`, `MAX_ABSOLUTE_DROP_PCT=0.0`, `MAX_RELATIVE_DROP_PCT=0.0` — a hard,
  zero-tolerance gate.
- With the settings.json overrides, the **local Stop hook** only blocks completion when current
  coverage drops below 90%, or falls more than 10 percentage points (absolute or relative) below the
  recorded baseline. This is real but bounded breathing room — a single mid-refactor turn or a
  narrow/partial concurrent test run within ~10pp of baseline no longer trips a false block.
- A genuinely severe drop (e.g. a stale `coverage.xml` reading far below baseline, or coverage actually
  collapsing) still blocks, because it exceeds both the 90% floor and the 10pp/10% drop allowance.

**This does not weaken what actually gates a PR.** `check_push_coverage.py` (`PreToolUse` on `git push`)
always re-runs the full suite fresh and hard-blocks below 100.00% — unaffected by this change. CI enforces
the same hard 100% via `--cov-fail-under=100` in `pyproject.toml`'s `[tool.pytest.ini_options]` and the
codecov checks in `.github/workflows/cicd.yml` — also unaffected. A PR reaching `git push` or CI is
guaranteed a fresh, hard 100% check regardless of how noisy the local Stop hook was during iteration.

## Auto-refresh behavior

`refresh_coverage_baseline.py` is intentionally non-blocking:

- Runs after tool execution (`PostToolUse`).
- Updates baseline only when:
  - command includes `pytest`, and
  - tool execution reports success, and
  - `coverage.xml` exists and can be parsed, and
  - the new value is not a large drop from the existing baseline (see below).
- If event payload is unknown, malformed, or missing success metadata, it **does not write**.

**Large-drop guard:** a narrow/partial `pytest` invocation (e.g. one test file, or a mid-refactor run)
can succeed while covering far less of the codebase than a full run. If it were allowed to freely
overwrite the baseline, that partial result would silently become the new floor for
`coverage_non_regression.py`, ratcheting enforcement down over time. To prevent that,
`refresh_coverage_baseline.py` refuses to write a new baseline that drops more than
`MAX_AUTO_REFRESH_DROP_PCT` (default `10.0`, override via env var) percentage points below the
currently recorded `baseline_pct` — mirroring the allowance band granted to the Stop hook itself, so
the two stay consistent. A genuine large drop in coverage is left for a human (or CI) to confirm and
update the baseline explicitly, rather than being auto-captured.

The baseline file schema is:

- `baseline_pct` — current line coverage in percent (rounded to 2 decimals)
- `source` — update source marker
- `captured_at` — ISO date (`YYYY-MM-DD`)

## Operational note

Because baseline is configured to auto-refresh after successful test runs, it can move up or down as test scope changes.
If you want stricter governance later, switch to explicit/manual refresh only.
