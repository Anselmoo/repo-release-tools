# Phase 1 hook-latency baseline

Recorded 2026-07-10 (Darwin arm64, Python 3.14, source-tree PYTHONPATH invocation,
median of 5 cold subprocess runs in a minimal fixture repo). Phases 2 and 5 must
stay within **+10%** of these (brief §3/§6); re-measure with the same method:
`python -c "<hooks shim>" <subcommand>` timed via `time.perf_counter()`.

| rrt-hooks subcommand | median wall-clock |
|---|---|
| `check-branch-name` | 137 ms |
| `check-commit-subject` | 142 ms |
| `check-dirty-tree` | 154 ms |

Interpreter startup + import dominates (~130 ms floor); the +10% budget therefore
effectively guards against import-graph growth in `workflow/hooks.py`'s fan-in —
exactly what Phase 5's per-hook handlers are expected to *reduce*.
