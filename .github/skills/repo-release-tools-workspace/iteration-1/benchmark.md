# Skill Benchmark: repo-release-tools

**Model**: <model-name>
**Date**: 2026-04-27T06:16:13Z
**Evals**: 0, 1, 2 (1 runs each per configuration)

## Summary

| Metric | With Skill | Without Skill | Delta |
|--------|------------|---------------|-------|
| Pass Rate | 100% ± 0% | 89% ± 19% | +0.11 |
| Time | 93.0s ± 13.9s | 126.3s ± 39.0s | -33.3s |
| Tokens | 2069 ± 1445 | 1573 ± 893 | +496 |

## Notes

- Eval 1 (changelog workflow choice) is the only discriminating eval in iteration 1: the skill run passed all assertions, while the baseline missed the incremental-vs-squash behavior explanation.
- Evals 0 and 2 passed in both configurations, so they currently validate correctness but do not strongly distinguish the skill from baseline behavior.
- With-skill runs were faster on average in this sample (93.0s vs 126.3s) despite producing longer answers and higher output-token counts.
- This benchmark uses one run per configuration, so pass-rate and timing variance are not yet meaningful stability signals.
