# Modernization Assessment — repo-release-tools (`src/repo_release_tools`)

*Generated 2026-07-10 by `/modernize-assess`. Tools: cloc v2.08 (scc unavailable), lizard (via uvx), pylint R0801, vulture, AST import-graph analysis by subagents. All figures reproducible from those tools.*

## Executive Summary

`repo-release-tools` (rrt) is a ~23.5 KSLOC, zero-runtime-dependency Python ≥3.12 codebase shipping three product surfaces from one core: the `rrt` CLI (27 subcommands), the `rrt-hooks` git-hook/CI policy runner, and a composite GitHub Action — plus an optional FastMCP server extra. The code is functional in production (edge-case bug fixed in issue #140) and well-tested at unit level (106 test files, ~85.7% coverage floor), but it is structurally risky: 50 functions exceed CCN 15, the three surfaces **reimplement rather than share** command logic (hooks re-declares CLI parsers with hand-synthesized defaults; MCP `rrt_bump` performs a partial bump), and rendering/filesystem side effects are welded into core logic (71 `Path.cwd()` sites, print-in-core), which is the direct cause of the missing e2e-test layer. Headline recommendation: **same-stack refactor-in-place** (`/modernize-uplift`-style phases) that extracts a headless core per command, unifies the three surfaces on it, and pins behavior with characterization/e2e tests before each extraction.

## System Inventory

### Line counts (cloc v2.08, `src/`)

| Language | Files | Blank | Comment | Code |
|---|---|---|---|---|
| Python | 121 | 5,398 | 5,602 | 23,529 |
| SVG | 170 | 170 | 0 | 1,685 |
| JSON | 2 | 0 | 0 | 574 |
| **Total** | **293** | **5,568** | **5,602** | **25,788** |

### Complexity (lizard)

- 937 functions, avg NLOC 20.8, **avg CCN 5.2** — the median function is healthy; the debt is concentrated.
- **50 functions over CCN 15.** Worst offenders:

| Function | CCN | NLOC | Location |
|---|---|---|---|
| `cmd_bump` | 62 | 248 | `commands/bump.py:271-543` |
| `cmd_tree` | 54 | 198 | `commands/tree.py:809-1052` |
| `_load_version_group` | 42 | 118 | `config/core.py:1190-1320` |
| `main` (hook dispatcher) | 40 | 535 | `workflow/hooks.py:959-1516` |
| `_extract_explicit` | 34 | 83 | `docs/extractor.py:270-366` |
| `cmd_doctor` (git) | 32 | 113 | `commands/git_inspect.py:149-272` |

- Style signals matching the modernization motivation: **233 `try:` blocks**, **1,826 `if`/`elif` branches**, 30 broad `except Exception` sites, 209 defensive `getattr(args, ...)` reads, 71 `Path.cwd()` call sites.

### Technology fingerprint

| Aspect | Evidence |
|---|---|
| Language / runtime | Python ≥3.12 (`pyproject.toml`), stdlib-only core (`dependencies = []`) — **zero-runtime-deps is policy** |
| Entry points | `rrt` → `cli.py:main`; `rrt-hooks` → `workflow/hooks.py:main`; `rrt-mcp` → `mcp/server.py:main` (optional `[mcp]` extra: FastMCP 3.x + Pydantic) |
| Build / packaging | `uv` + PEP 621 `pyproject.toml`; tox-uv matrix 3.12/3.13/3.14 mirroring CI |
| Data stores | File-based state: `[tool.rrt]` config (pyproject / `.rrt.toml` / `Cargo.toml` / `package.json`), lock files under `.rrt/` (`docs`, `health`, `tree`, `artifacts`, `drift`, `docs_map` — ownership split across `state.py` and two command modules) |
| Integrations | git via `subprocess` (list-argv, no `shell=True`); HTTPS APIs: registry.npmjs.org, crates.io, PyPI (`sync/providers.py`), endoflife.date (`eol/core.py`); GitHub Actions (`action.yml` composite, shells out to `rrt-hooks`) |
| Tests | 106 test files, unit + `runtime`-marked integration; coverage floor 85.71% (CI-enforced). **No end-to-end suite** exercising the CLI/hook/Action surfaces as a user would |

## Architecture-at-a-Glance

Eleven domains (diagram: [`ARCHITECTURE.mmd`](ARCHITECTURE.mmd)):

| # | Domain | Purpose | Key files | Depends on |
|---|---|---|---|---|
| 1 | CLI shell & assets | `rrt` argparse entrypoint; registers 27 subcommands (`cli.py:169-195`); banner/badges | `cli.py`, `__main__.py`, `commands/__init__.py`, `assets/` | 2,3,5,6,9,11 |
| 2 | Version & release engine | Semver/CalVer, version targets, changelog, bump/tag/release/sync, preflight | `version/`, `changelog.py`, `preflight.py`, `sync/`, `commands/{bump,tag,ci_version,release_*,workspace,sync_cmd,changelog_*}.py` | 7, 3, 11 |
| 3 | Git workflow | git subprocess helpers; branch/commit/inspect/publish-snapshot | `workflow/git.py`, `commands/{branch,git_*,_git_shared}.py` | 7, 11, **4 (bidirectional)** |
| 4 | Hooks & CI policy gates | All validators/auto-writers in one 2,014-line module; `action.yml` wraps it | `workflow/hooks.py`, `hooks.py` (shim), `action.yml`, `integrations/action.py`, `commands/hooks_cmd.py` | 2,3,5,6,7,8,11 — **widest fan-in: imports 15 `commands/*` modules** |
| 5 | Repo health & drift | doctor, drift lock, EOL policy, folder templates, artifact hashing, tree snapshot | `commands/{doctor,drift_cmd,eol_check,folder,artifacts_cmd,tree,_tree_fix}.py`, `eol/`, `folders/` | 7, 8, 3, 6, 11 |
| 6 | Docs engine | Docstring extraction → multi-format render, publisher, purpose maps, TOC/anchor injection | `docs/`, `tools/{inject,toc,platform}.py`, `commands/{docs_*,toc}.py` | 7, 8, 11, **1 (lazy import to break cycle)** |
| 7 | Config | Load/validate `[tool.rrt]` from 4 sources; typed model; `init`/`config` commands | `config/`, `commands/{config_cmd,init,project_cmd}.py` | 2 (one edge: `model.py` → `sync.providers`), 11 |
| 8 | State & lock store | Owns `.rrt/` read/write/currency (`state.py:16-19`) — but `drift` and `docs_map` locks name their own files elsewhere | `state.py` | 11 (near-leaf) |
| 9 | Setup & agent integrations | Install skills/agents from package assets; env; MCP scaffolder | `commands/{skill,agents_cmd,install_cmd,env_cmd,mcp_cmd}.py`, `integrations/` | 11 |
| 10 | MCP server (optional extra) | FastMCP 3.x server, 7 tool modules, Pydantic models | `mcp/` | 2,3,4,5,7,8 |
| 11 | UI layer | Canonical rendering API (color, glyphs, layout, messaging/DryRunPrinter, …) | `ui/` | pure leaf |

**Noteworthy couplings** (dotted in the diagram): (a) Git ↔ Hooks is bidirectional (`commands/git_commit.py`/`git_inspect.py` import hook validators while `workflow/hooks.py` imports command modules); (b) Docs → CLI via deliberate lazy imports to avoid a cycle (`docs/publisher.py`); (c) Config → Release via `config/model.py` importing `sync.providers.PROVIDERS`.

**Dangling/dead references:** `docs/formats/html.py:render_html` defined but absent from the `_RENDERERS` dispatch (`docs/formats/__init__.py:134-140`) — unreachable in production, kept alive only by tests. Two backward-compat shims unused in-tree: top-level `hooks.py` and `docs/markdown.py`. `mcp/resources.py` imports underscore-private `_find_repo_root` from `mcp/server.py`. Vulture found no dead code at ≥80% confidence otherwise.

## Production Runtime Profile

**No telemetry available.** This is a developer CLI/git-hook/CI tool, not a served system — there is no APM source. The nearest proxy (CI job durations for the Action) was not collected. Gap noted; not blocking for a refactor-in-place, but hook latency (pre-commit runs on every commit) should be benchmarked before/after each phase.

## Technical Debt (top 10, ranked by remediation value)

1. **`workflow/hooks.py main` is a 557-line god dispatcher that re-declares CLI parsers and hand-synthesizes defaults** — `workflow/hooks.py:959-1516` (CCN 40, 66 `add_argument` calls); dispatch arms fake CLI invocations by mutating a Namespace field-by-field (e.g. `docs-inject` at `hooks.py:1407-1416`); the `publish-snapshot` argparse spec is copy-pasted verbatim from `commands/git_sync.py:654-683` into `hooks.py:1159-1190` (pylint R0801). Flag renames silently break the hooks surface with wrong defaults — the #140 class of bug. *Fix: single parser-spec/defaults object per command consumed by both surfaces; split `main` into per-hook handlers.*
2. **MCP `rrt_bump` reimplements a partial bump** — `mcp/tools/version_tools.py:68-105` writes version targets only, skipping pin targets (`bump.py:390-414`), changelog (`416-433`), lock (`435-453`), generated assets (`455-492`), branch/commit (`494-535`), preflight (`355-360`). A non-dry-run MCP bump leaves the repo half-bumped. *Fix: extract headless `perform_bump(...) -> BumpResult` shared by all three surfaces.*
3. **Core version-write logic prints directly — the missing seam** — `version/targets.py:85-93,112-140` construct printers inside write primitives; MCP mutes them with `contextlib.redirect_stdout(io.StringIO())` (`version_tools.py:83-90`), a workaround that proves the seam is missing. *Fix: core mutators return events/changed paths; rendering moves to the command layer. Prerequisite for #2.*
4. **`cmd_bump` god function (CCN 62) with decorative progress bars** — `commands/bump.py:271-543`; the loops at `bump.py:379-388` and `393-409` animate `ProgressLine.update_bar` over items on which no work occurs (real writes happen once at `bump.py:414`). *Fix: remove/wire the bars, split into phase functions each returning a result.*
5. **Config-load error boilerplate copy-pasted across ~12 command modules** — near-identical try/except guidance blocks in `bump.py:276-299`, `release_notes.py:149-168`, `doctor.py:295-326`, `release_cmd.py:177-208`, `changelog_compare.py:167-189`, `changelog_lint.py:183-205`; the `p = VerbosePrinter(...); p.line(...); return 1` idiom occurs 117×. *Fix: one `load_config_or_exit()` helper/decorator in `commands/_common.py`.*
6. **Hand-rolled TOML validation: `config/core.py` is 1,391 lines of isinstance/raise ladders** — `_load_version_group` (CCN 42, `core.py:1190-1320`) with five consecutive identical checks at `core.py:1216-1225`; same pattern in `_load_pin_targets`, `_load_generated_assets`, `config/docs_config.py`. *Fix: in-house declarative field-spec table + one generic walker (no new dependency); collapses ~400 lines.*
7. **Broad `except Exception` as control flow; rollback that swallows failure** — 30 sites; `state.py:277-326` wraps pure comparisons in four consecutive try/excepts; worst: `version/targets.py:126-136` "atomic" rollback does `except OSError: pass` per file, so a failed rollback leaves a half-written tree silently. *Fix: type checks for pure computation; collect-and-report failed restores.*
8. **`cmd_tree` god function (CCN 54) with duplicated atomic-write machinery** — `commands/tree.py:809-1052`; two near-identical `NamedTemporaryFile` + `Path.replace` blocks (`tree.py:720-737` vs `739-756`); 8 of the 30 broad excepts; 17 `getattr(args,...)` reads. *Fix: extract `manifest.py` (read/write/diff, one parameterized atomic-write helper).*
9. **Untyped args contract: 209 `getattr(args, ..., default)` reads put each flag's default in three places** — `register()` default, `getattr` fallback, and hooks' synthesized namespaces (#1). `verbose: int = getattr(args, "verbose", 0) or 0` alone is duplicated 54×. *Fix: per-command frozen `Options.from_args(args)` dataclass — single default, typed contract for hooks/MCP.*
10. **`Path.cwd()` and `.rrt/` layout hardcoded deep in logic — the main obstacle to e2e testing** — 71 `Path.cwd()` sites; every `cmd_*` derives its own root (`bump.py:274`); `.rrt/` filename literals in 10+ files instead of `state.py` constants. Positive: exit codes are clean — `sys.exit` confined to entrypoints. *Fix: thread `root: Path` from entrypoints; centralize `.rrt/*` names in `state.py`.*

## Security Findings

No hardcoded credentials were found (grep for password/secret/token/AKIA/ghp_/xox patterns: only docs and tokenizer code) — **no SECRETS.local.md quarantine required.** No `shell=True`, `eval`, `exec`, `pickle`, or unsafe YAML anywhere in `src/`.

| ID | Severity | CWE | Finding | Evidence | Recommendation |
|---|---|---|---|---|---|
| SEC-001 | Medium | CWE-77 (Actions expression injection) | `action.yml` interpolates inputs directly into `run:` script text (`case "${{ inputs.verbose }}"`, `changelog_file="${{ inputs.changelog-file }}"`) instead of the env-var indirection the same file uses correctly elsewhere | `action.yml:108,128` (correct pattern at `:153-158,187-192`) | Pass via `env:` and reference `"$INPUT_*"` |
| SEC-002 | Medium | CWE-306 | MCP HTTP transport has no auth while tools mutate state — incl. force-push where `dry_run=False` is the only confirmation | `mcp/server.py:104-105`, `mcp/tools/publish_tools.py:35` | Auth token for HTTP transport, default host 127.0.0.1, server-side gate for force-push |
| SEC-003 | Low | CWE-22 | Changelog hook writes `cwd / changelog_file` with no containment check — config-controlled path can escape the work tree | `workflow/hooks.py:~757-769` | Reject paths not `is_relative_to(cwd)` |
| SEC-004 | Low | CWE-88 | git argv positionals without `--` separator (`git add <file>`, `git log <ref>..HEAD`, …) — option-confusion if value starts with `-` | `workflow/hooks.py:769,936`; `workflow/git.py:153,170,225` | Insert `--` before path/ref positionals |
| SEC-005 | Low | CWE-20 | Package/slug config values interpolated into API URLs without percent-encoding | `sync/providers.py:46,58,70,88`; `eol/core.py:152` | `urllib.parse.quote(..., safe="")` |
| SEC-006 | Low | CWE-116 | `health_summary` JSON built by string interpolation in `action.yml` — a `"` in the version corrupts downstream JSON | `action.yml:143-147` | Build with `jq -n --arg` |
| SEC-007 | Info | CWE-20 | MCP `rrt_init_run` forwards LLM-supplied `target` into argv without allowlist (unlike `git_tools.py:36`) | `mcp/apps.py:592-600` | Validate against known target set |

*Scan coverage gaps:* ReDoS in `changelog.py`/`version/targets.py` custom pin-target regexes (user-supplied patterns = inherent ReDoS-by-configuration surface) and `docs/extractor.py` not exhaustively reviewed; `.rrt/` lock TOCTOU not verified; `git_sync.py`/`tag.py` push paths not fully read.

## Documentation Gaps (top 5)

User-facing docs are strong (Astro site, generated command pages, MCP/Action pages; every source file has a docstring). The gaps are **internal contracts** a new engineer would need explained:

1. **`.rrt/` lock-file schema and ownership** — six lock files, but `state.py:16-19` names only four; `drift.lock.toml` and `docs_map.lock.toml` define their filenames in their own command modules. No document says what each lock guarantees or when it invalidates.
2. **Hooks↔CLI default-synthesis contract** — nothing documents that `workflow/hooks.py` dispatch arms must mirror `register()` defaults field-by-field (debt #1); the invariant exists only implicitly.
3. **MCP surface parity** — `rrt_bump`'s partial scope vs `cmd_bump` is undocumented (debt #2); an MCP client cannot know the divergence.
4. **Config source precedence & auto-detection order** — `auto_detect_config` (`config/core.py:801-923`, CCN 17) implements precedence across four config sources that is documented only by its code.
5. **Cross-surface exit-code / output contract** — hooks return-int conventions, `emit_failure` semantics, and which output stream (stderr vs stdout) each surface uses are uncodified.

## Relative Scale

**COCOMO-II index: ≈ 95** — computed as `2.94 × (23.529 KSLOC)^1.10 = 2.94 × 32.3` (nominal scale factors; cloc-measured Python SLOC only).

This is a **relative size/complexity signal** for ranking this system against others and apportioning phases — **it is not a timeline, schedule, or cost.** The COCOMO person-month model assumes human-team productivity curves that agentic transformation does not follow. No duration or budget is stated or implied here.

## Recommended Modernization Pattern

**Refactor** (in-place, same-stack) → routes to **`/modernize-uplift`-style phased execution.**

Rationale: the stack is current (Python 3.12+, uv, modern tooling) — nothing to re-platform. The product behavior is correct and well-specified by 106 unit-test files; a rebuild would discard the codebase's real asset (validated behavior) to fix its real liability (structure). The debt is concentrated and mechanical: one god dispatcher, two god commands, one imperative validation module, and three cross-cutting seams (printing-in-core, cwd-in-core, args-untyped). Each is independently extractable behind characterization tests, leaf-first (UI/state/version primitives already near-leaf → config → commands → hooks/MCP surfaces last), which also matches the requirement that phases be executable by smaller agents (Sonnet/Haiku) with tight scopes. The missing e2e suite must come *first* — it is both the biggest stated gap and the safety net for every subsequent phase.
