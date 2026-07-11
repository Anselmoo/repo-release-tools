# Phase 4 Scope — Command-Core Extraction

*Scoped 2026-07-11 against `refactor/config-options-p3` (PR #154, pending merge). All line
numbers/CCN below are current-state, post Phase 1–3, not the original assessment snapshot.*

## Status — Phase 4 complete (closed out 2026-07-11)

All originally-scoped Phase 4 work has landed on `main` across two PRs (#155, #157).

- **P1a (`bump.py`) — done.** `cmd_bump` CCN 48 → 25 (at the exit threshold). All four stages
  extracted with direct unit tests: `resolve_bump_target`, `apply_bump_files`,
  `refresh_bump_lockfile`, `refresh_bump_generated_assets`, `finalize_bump_git`.
- **P1b (`tree.py`) — done, reasonable stopping point.** `cmd_tree` CCN 53 → 29 (above
  threshold but ~45% reduction). Extracted: `_atomic_write` (collapses the two duplicate
  temp-file blocks), `_append_manifest_diff_summary` (the check-mode diagnostic), and
  `render_tree_content` (the format-dispatch `match`). Remaining CCN is genuine 7-way mode
  dispatch (fix-empty-dirs / strict-empty / manifest / snapshot / check / inject / default),
  not further-extractable logic.
- **P2 (`doctor.py`, `git_inspect.py`, `release_cmd.py`) — done.** All three brief-named
  "next-worst" functions now well under the CCN-25 threshold: `doctor.cmd_doctor` 28→18,
  `git_inspect.cmd_doctor` 31→17, `git_inspect.cmd_sync_status` 22→14, `git_inspect.cmd_diff`
  28→6, `release_cmd.cmd_release_check` 25→10.
- **Folded-in Phase 3 remainder — done.** `docs_cmd.py` (8 command classes), `eol_check.py`,
  `ci_version.py`, `sync_cmd.py`, `config_cmd.py`, `artifacts_cmd.py`, `folder.py` all
  converted to typed `Options` dataclasses. `git_inspect.py` and `git_sync.py` were confirmed
  already fully converted before this pass (a naive `grep -c getattr` overstates debt —
  docstring prose describing the pattern inflates the count; always verify real code hits).

### New hotspots visible post-Phase-4 (out of scope, flagged for later)

Not part of the original Phase 4 brief and **not addressed here** — a fresh `lizard` sweep
after all the above landed surfaces CCN hotspots that weren't previously the "next-worst"
(the brief's snapshot predates this phase's own refactoring shuffling which functions rank
highest): `agents_cmd.cmd_install` (26), `git_sync.cmd_rebootstrap` (23), `sync_cmd.cmd_sync`
(21), `artifacts_cmd.cmd_artifacts` (20). Candidates for a Phase 4c or folding into Phase 5
scope — needs a fresh scoping pass, not assumed to be a straightforward repeat of this
phase's pattern.

## Entry gate

Blocked on **PR #154 merging into `main`** (Phase 3 — `Options` dataclasses are the typed
input every `perform_*` function below takes). Do not start writing code until then, per the
merge-order lesson from #152.

## Current complexity hotspots in `commands/` (lizard, CCN > 15)

| Function | CCN | NLOC | Priority |
|---|---|---|---|
| `tree.cmd_tree` | 53 | 198 | **P1 — named in brief** |
| `bump.cmd_bump` | 48 | 214 | **P1 — named in brief** |
| `git_inspect.cmd_doctor` | 31 | 114 | P2 — named in brief |
| `git_inspect.cmd_diff` | 28 | 95 | P2 — adjacent, same file |
| `doctor.cmd_doctor` | 28 | 112 | P2 — named in brief |
| `agents_cmd.cmd_install` | 26 | 77 | P3 — not named, over threshold |
| `release_cmd.cmd_release_check` | 25 | 80 | P2 — named in brief, at threshold |

Exit criterion: **no function in `commands/` over CCN 25.** `workflow/hooks.py:main` (CCN 40)
is explicitly Phase 5's problem, not Phase 4's — excluded here.

## P1a — `bump.py`: `perform_bump() -> BumpResult`

`cmd_bump` (`commands/bump.py:326-564`) already has `Options.from_args()` from Phase 3.
Printing is interleaved throughout via `p.section()`/`p.header()`/error `p.line()` calls —
following Phase 2's established pattern (`version/targets.py` returns events, callers render),
`perform_bump()` returns a structured result; `cmd_bump` becomes the thin renderer.

**Four natural stage boundaries** (already implicit in the current section headers):

1. **`resolve_bump(config, group_opts) -> BumpPlan`** — lines 332–423: load config, resolve
   group, compute new version (major/minor/patch/calver/explicit-string branches), compute
   branch name, run preflight. Returns `current`, `new`, `branch_name`, `base` or raises a
   typed error (`BumpResolutionError` or similar) the renderer maps to today's exact messages.
2. **`apply_bump_files(plan, group, config, *, dry_run) -> list[VersionWriteEvent]`** —
   lines 425–435: delegates to the existing `apply_version()` (already extracted, untouched).
   Thin wrapper, mostly a naming/grouping step.
3. **`refresh_bump_assets(plan, group, config, opts, *, dry_run) -> AssetRefreshResult`** —
   lines 437–513: changelog update, lock command, generated-assets loop. This is the stage
   with the most branching (changelog mode resolution, per-asset error handling with
   dry-run-vs-real divergent behavior) — highest risk of the four, do it stage-isolated with
   its own e2e re-run before moving on.
4. **`finalize_bump_git(plan, changed_paths, opts, *, dry_run) -> GitFinalizeResult`** —
   lines 515–564: checkout branch, stage files, commit (with the pre-commit-hook-retry
   special case at 549–554). **Ordering is contract** — branch→commit — pin this explicitly
   with the brief's §4 Flow 1 e2e walkthrough before/after.

`BumpResult` composes the four stage results; `cmd_bump` renders each stage's result through
the *existing* `p.section()`/`p.header()` calls, unchanged in wording — e2e output must stay
byte-identical (dry-run and real).

**Risk (per brief, confirmed real):** stage 3 (assets/changelog) has the densest branching and
the dry-run/real divergence in error handling — extract it last, alone, with its own gate pass.

## P1b — `tree.py`: `manifest.py` extraction

Less green-field than it looked in the original assessment — `_write_tree_manifest`
(`commands/tree.py:684-754`) is already a separate function. What's NOT done yet, confirmed
by reading current source:

- **Two near-identical `NamedTemporaryFile` + `Path.replace` blocks remain** (lines 725–732
  compressed, 741–750 plain) — collapse to one `_atomic_write(data: bytes | str, target: Path,
  target_dir: Path, *, mode: str)` helper.
- `cmd_tree` (`commands/tree.py:896-1139`, CCN 53) is a genuine mode-dispatch god function:
  build entries → format-render `match` (already clean, low CCN contributor) → early-return
  `--fix-empty-dirs` → `--strict-empty-dirs` gate → `--manifest`/`--compressed` write →
  (continues past line 1015 into snapshot/check/inject modes, not yet read in detail this pass).

**Target shape:** new `commands/_tree_manifest.py` (mirroring the `_version_render.py` /
`_common.py` naming convention from Phases 2–3) owning `_flatten_entries_for_manifest`,
`_write_tree_manifest` (with the collapsed atomic-write helper), and manifest diff logic.
`cmd_tree` reduces to: build entries → render (unchanged) → dispatch to mode handlers, each a
top-level function taking `entries`/`root`/`opts`. Read the full 896–1139 range before writing
code — this doc only confirms the first ~120 lines; snapshot/check/inject modes need the same
line-by-line pass P1a got.

## P2 — `git_inspect.py`, `doctor.py`, `release_cmd.py`

Lighter lift than P1: `doctor.py` and `release_cmd.py` already have substantial helper
extraction — a `_check_*(...) -> tuple[str, bool, str]` (name, ok, message) convention used by
~6 functions in `doctor.py` alone. Their `cmd_doctor`/`cmd_release_check` CCN comes from
**aggregating and branching on check results**, not from unextracted logic. Likely fix: a
`CheckResult` dataclass (formalizing the existing tuple convention) and a small
`run_checks(checks: list[Callable[[], CheckResult]]) -> list[CheckResult]` runner, rather than
a full stage-pipeline rebuild like `perform_bump`. `git_inspect.cmd_doctor` (CCN 31) and
`cmd_diff` (CCN 28) are less pre-decomposed — read in full before scoping their extraction;
not done in this pass.

## Folded-in Phase 3 remainder

Per the user's 2026-07-10 decision, the ~14 files that didn't get a typed `Options` dataclass
in Phase 3 fold into Phase 4, since this phase touches most of them anyway:
`docs_cmd.py`, `eol_check.py`, `ci_version.py`, `sync_cmd.py`, `config_cmd.py`,
`artifacts_cmd.py`, `folder.py`, `doctor.py`, `git_inspect.py`, `git_sync.py`, +smaller files.
**`doctor.py` and `git_inspect.py` overlap directly with P2 above** — do the `Options`
conversion and the check-result formalization in the same pass for those two files.

## Validation plan (per brief §3 Phase 4)

- `perform_*` functions get **direct unit tests** (new — they didn't exist as isolable units
  before).
- e2e suite (71 tests) re-run after **every stage extraction**, not just at the end — stage 3
  of `perform_bump` is the named risk.
- §4 Flow 1 (release walkthrough) e2e coverage specifically pins `finalize_bump_git`'s
  branch→commit ordering.
- Exit gate: `uvx lizard -s cyclomatic_complexity src/repo_release_tools/commands` shows zero
  entries over CCN 25.

## Suggested execution order

1. `bump.py` stages 1–2 (lower risk) → gate → commit
2. `bump.py` stages 3–4 (higher risk, isolated) → gate → commit
3. `tree.py` manifest extraction + atomic-write collapse → gate → commit
4. `tree.py` mode-dispatch reduction (needs the unread 1015+ range scoped first) → gate → commit
5. `doctor.py` + `git_inspect.py`: `CheckResult` formalization + folded Options sweep → gate → commit
6. `release_cmd.py`: same `CheckResult` pattern → gate → commit
7. Remaining folded-in Options sweep (`docs_cmd.py`, `eol_check.py`, `ci_version.py`,
   `sync_cmd.py`, `config_cmd.py`, `artifacts_cmd.py`, `folder.py`, `git_sync.py`) — mechanical,
   Haiku-suitable per the brief's executor guidance
