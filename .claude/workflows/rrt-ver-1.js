export const meta = {
  name: 'rrt-ver-1',
  description: 'Work through issue #259 (RRT-VER-1) one delivery tier at a time: plan, implement, adversarially review, gate, commit',
  whenToUse: 'Implementing a tier of the RRT-VER-1 roadmap from issue #259. Pass args {tier: 0..5}; optional {findings: ["F1","F8"], commit: true, maxFixRounds: 2}.',
  phases: [
    { title: 'Plan', detail: 'map the tier findings to concrete tasks, files and tests' },
    { title: 'Implement', detail: 'one agent per task, sequential on the working tree, tests first' },
    { title: 'Review', detail: 'parallel lenses try to break the diff; fix loop until clean' },
    { title: 'Gate', detail: 'run the repo checks: tests, coverage 100%, lint, docs publish --check' },
    { title: 'Commit', detail: 'conventional commit on the current branch (opt-in, never pushes)' },
  ],
}

// ---------------------------------------------------------------------------
// Source of truth: https://github.com/Anselmoo/repo-release-tools/issues/259
// The tier table below mirrors section E of that issue. When the issue and this
// file disagree, the issue wins: the Plan agent re-reads it before planning.
// ---------------------------------------------------------------------------

const ISSUE = 'Anselmoo/repo-release-tools#259'

// Decisions taken on the open questions of the issue. Each one is a default
// with a config toggle, never a hard-coded behaviour.
const DECISIONS = `
D-1  Starting a pre-release channel (alpha|beta|rc) from a FINAL version targets the
     next PATCH by default (1.0.0 -> 1.0.1-rc.1). This matches npm/node-semver
     (inc prerelease: 1.2.3 -> 1.2.4-0) and Poetry (prerelease: 1.0.2 -> 1.0.3a0).
     Toggle:  [tool.rrt] prerelease_base = "patch" | "minor" | "major" | "auto"
              (per group overridable; "auto" derives the level from Conventional
              Commits since the last FINAL tag: breaking -> major, feat -> minor,
              otherwise patch, like semantic-release).
     CLI:     rrt bump rc --base minor   (one-off override, wins over config)
     MCP:     rrt_bump(level="rc", base="minor")
     Advancing inside a channel (rc.1 -> rc.2) or switching channel on the same
     core (beta.2 -> rc.1) never changes major.minor.patch.
D-2  Changelog for pre-releases. There is no formal standard (Keep a Changelog is
     silent); the reader expectation is that the FINAL entry describes the whole
     release relative to the previous final. Default is therefore "cumulative".
     Toggle:  [tool.rrt] prerelease_changelog = "cumulative" | "fold" | "separate"
       cumulative  final section = union of all pre-release entries of that version
                   + anything new; pre-release sections stay below it (no data loss)
       fold        like cumulative, but the pre-release sections are removed and
                   replaced by one "Pre-releases: 1.2.0-rc.1, 1.2.0-rc.2" line
       separate    today's behaviour: each pre-release keeps its own section and the
                   final only lists what is new since the last pre-release
     In every mode: dev versions never create a section; post versions get their own.
     The git-log range for a final always starts at the previous FINAL tag.
D-3  version_policy defaults to "independent"; "lockstep" is opt-in.
D-4  Every new behaviour ships with the same knob on all three surfaces:
     [tool.rrt] config, CLI flag, MCP tool parameter (parity contract).
`

const TIERS = {
  0: {
    title: 'Independent bug fixes',
    findings: ['F1', 'F8', 'F9', 'F10', 'F14', 'F16'],
    scope: [
      'F1: Version.sort_key compares pre-release identifiers per SemVer 2.0 §11 (numeric < alphanumeric, numeric compared numerically, shorter prefix sorts first). newer_versions() inherits the fix. File: src/repo_release_tools/version/semver.py',
      'F8: starting alpha/beta/rc from a final version moves to the next patch by default; add prerelease_base config (patch|minor|major|auto) + `rrt bump --base` + MCP `base` parameter per decision D-1. Files: version/semver.py (_set_channel), config/model.py, config/core.py, commands/bump.py, mcp/tools/version_tools.py',
      'F9 + F10: one prefix-aware "latest tag" helper in workflow/git.py that parses tags and sorts by version precedence (final > its pre-releases), with a latest_final variant. Use it in commands/bump.py (git_log_since_latest_tag), commands/release_notes.py (_git_contributors, must honour the group tag_prefix), commands/tag.py',
      'F14: rrt workspace bump must turn a bump() ValueError into a clean error line + exit 1 during the fail-early phase, and accept `release`. File: commands/workspace.py',
      'F16: action.yml detect-version step must call `rrt ci-version compute` (not bare `rrt ci-version`). File: action.yml',
    ],
    acceptance: [
      'sorted rc.1, rc.2, rc.10 is numeric',
      'Version("1.0.0").bump("rc") == 1.0.1-rc.1 by default; with base=minor -> 1.1.0-rc.1',
      'after tags v1.0.0-rc.1, v1.0.0, v1.0.0-rc.2 the latest tag is v1.0.0',
      'release notes contributors respect tag_prefix in a v* + sdk-v* repo',
      'workspace bump pre-release on a stable package exits 1 without traceback',
    ],
  },
  1: {
    title: 'Canonical version model',
    findings: ['F2', 'F11'],
    scope: [
      'Structured Version with release/pre/post/dev/local per RRT-VER-1 §1; accepts SemVer and PEP 440 spellings as input; keep today\'s public API working',
      'version_scheme per group (semver|pep440|calver), inferred from the primary target when unset; read_group_current_version parses through the scheme so zero-padded CalVer (2026.05.15) round-trips',
      'Bump algebra table (kind x state) documented and covered by one parametrised test; invariant I5: every transition yields new > current, otherwise refuse unless --force',
      'bump kinds dev and post exist in the model (CLI wiring is tier 3)',
    ],
    acceptance: ['parametrised transition-table test passes', '2026.05.15 round-trips', 'no existing test changes behaviour'],
  },
  2: {
    title: 'Renderers per target format',
    findings: ['F3', 'F4', 'F7', 'F12'],
    scope: [
      'format field on VersionTarget and PinTarget: semver|pep440|rubygems|go-tag|oci-tag|calver; default inferred from kind; ci_format stays as deprecated alias',
      'replace_all_versions_atomic renders every target from the canonical version (renderings table in issue §2)',
      'post refused (or mapped to patch via post_policy="patch") when a group contains a target that cannot express it (F4)',
      'Conformance tests I1-I5 in Python against packaging; the multi-language comparator matrix (node-semver, x/mod/semver, semver crate, RubyGems, NuGet) as a separate CI job marked runtime',
    ],
    acceptance: ['I1-I5 pass for every built-in format', 'existing single-format repos produce byte-identical files'],
  },
  3: {
    title: 'CLI surface and holistic bumping',
    findings: ['F5', 'F13', 'F15'],
    scope: [
      'rrt version [--group] [--json]: canonical, scheme, rendered per target, pins, is_prerelease/is_devrelease/is_postrelease, next per bump kind',
      'rrt bump dev / rrt bump post wired through the CLI',
      'ci-version compute: next-patch dev on the default branch (0.1.0 -> 0.1.1.devN), toggle to legacy behaviour',
      'version_policy independent|lockstep and depends_on; one planner shared by bump --group a,b, workspace bump and sync --bump (validate all, write all atomically, one rollback domain); workspace becomes a write category',
    ],
    acceptance: ['3-group lockstep fixture bumps atomically', 'rollback test on injected write failure', 'rrt version --json schema test'],
  },
  4: {
    title: 'MCP as the second workflow',
    findings: ['F20', 'F21', 'F22', 'F23'],
    scope: [
      'Shared pure cores returning Pydantic models; CLI renders them, MCP returns them; rrt_release_check stops importing private release_cmd._* helpers',
      'rrt_bump: every CLI kind, base, calver_scheme, changelog_mode, no_changelog, no_commit; errors as ConfigError',
      'New tools: rrt_bump_plan, rrt_ci_version, rrt_tag, rrt_release_notes, rrt_release_repair, rrt_release_status, rrt_verify_dist (mutating ones dry_run=True, confirm for hard-to-undo)',
      'rrt_changelog(group=...), rrt://changelog/{group}, rrt://versions; version overview UI extended; prompts updated; server instructions CLI-only list derived from the tool list',
      'Generic CLI<->MCP parity test over every version/release command; Internal Contracts §MCP/CLI parity extended',
    ],
    acceptance: ['parity test covers every version/release command', 'instructions list test fails when a tool is added without updating it'],
  },
  5: {
    title: 'Release process versioning',
    findings: ['F6', 'F17', 'F18', 'F19'],
    scope: [
      'rrt release status [--group] [--json]: release-train node, allowed transitions, last tag per channel, Unreleased state',
      'prerelease_changelog cumulative|fold|separate per decision D-2 (default cumulative)',
      'rrt tag create validates the canonical version and tag_format; tag check --strict compares tag, primary target and pins; rrt version verify-dist',
      'action.yml outputs: version, canonical-version, is-prerelease, is-devrelease, is-postrelease, publish-channel, release-notes-path; documented reference workflow',
      'Dogfood .github/workflows/cicd.yml: ci-version sync before build, TestPyPI for dev/pre, PyPI for final/post, GitHub prerelease flag, notes from rrt release notes',
    ],
    acceptance: ['end-to-end fixture dev -> rc.1 -> rc.2 -> final -> post yields correct tags, changelog (all three modes), classification and publish channel'],
  },
}

// Checks every change must pass before it may be committed (from CLAUDE.md).
const GATE_COMMANDS = [
  'uv run pytest -q -m "not runtime"',
  'uvx pre-commit run --all-files',
  'uv run rrt docs publish --check',
]

// ---------------------------------------------------------------------------
// Schemas
// ---------------------------------------------------------------------------

const PLAN_SCHEMA = {
  type: 'object',
  properties: {
    summary: { type: 'string' },
    tasks: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string', description: 'short kebab id, e.g. f1-semver-precedence' },
          findings: { type: 'array', items: { type: 'string' } },
          goal: { type: 'string' },
          files: { type: 'array', items: { type: 'string' } },
          tests: { type: 'array', items: { type: 'string' }, description: 'test files + the cases to add' },
          docs: { type: 'array', items: { type: 'string' }, description: 'docstrings/doc pages that must change' },
          depends_on: { type: 'array', items: { type: 'string' } },
        },
        required: ['id', 'findings', 'goal', 'files', 'tests'],
      },
    },
    out_of_scope: { type: 'array', items: { type: 'string' } },
  },
  required: ['summary', 'tasks'],
}

const IMPL_SCHEMA = {
  type: 'object',
  properties: {
    id: { type: 'string' },
    status: { type: 'string', enum: ['done', 'partial', 'blocked'] },
    changed_files: { type: 'array', items: { type: 'string' } },
    tests_added: { type: 'array', items: { type: 'string' } },
    test_command: { type: 'string' },
    test_result: { type: 'string', description: 'last lines of the targeted test run' },
    notes: { type: 'string' },
  },
  required: ['id', 'status', 'changed_files', 'test_result'],
}

const REVIEW_SCHEMA = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          file: { type: 'string' },
          line: { type: 'integer' },
          severity: { type: 'string', enum: ['blocking', 'minor'] },
          problem: { type: 'string' },
          repro: { type: 'string', description: 'input/state that shows the failure' },
          fix: { type: 'string' },
        },
        required: ['file', 'severity', 'problem', 'fix'],
      },
    },
  },
  required: ['findings'],
}

const GATE_SCHEMA = {
  type: 'object',
  properties: {
    passed: { type: 'boolean' },
    results: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          command: { type: 'string' },
          ok: { type: 'boolean' },
          tail: { type: 'string', description: 'failing output, trimmed' },
        },
        required: ['command', 'ok'],
      },
    },
    coverage_percent: { type: 'number' },
  },
  required: ['passed', 'results'],
}

// ---------------------------------------------------------------------------
// Inputs
// ---------------------------------------------------------------------------

const input = args || {}
const tierNo = Number(input.tier ?? 0)
const tier = TIERS[tierNo]
if (!tier) throw new Error(`Unknown tier ${input.tier}; expected one of ${Object.keys(TIERS).join(', ')}`)
const onlyFindings = Array.isArray(input.findings) && input.findings.length ? input.findings : tier.findings
const maxFixRounds = Number(input.maxFixRounds ?? 2)
const doCommit = input.commit === true

const TIER_BRIEF = `
Issue: ${ISSUE} (RRT-VER-1), delivery tier ${tierNo}: ${tier.title}
Findings in scope: ${onlyFindings.join(', ')}
Scope:
${tier.scope.map((s) => `- ${s}`).join('\n')}
Acceptance:
${tier.acceptance.map((s) => `- ${s}`).join('\n')}
Decisions (binding):
${DECISIONS}
Repo rules that matter here: 100% coverage floor; published docstrings under commands/, workflow/ keep
their ## Overview/## Examples/## Caveats/## Related docs skeleton; CLI output goes through
repo_release_tools.ui; mutating commands keep --dry-run; no new runtime dependencies.
`

log(`RRT-VER-1 tier ${tierNo} (${tier.title}); findings ${onlyFindings.join(', ')}`)

// ---------------------------------------------------------------------------
// Plan
// ---------------------------------------------------------------------------

phase('Plan')
const plan = await agent(
  `You plan one delivery tier of ${ISSUE}.
First read the current issue body with the GitHub MCP tool issue_read (owner Anselmoo, repo
repo-release-tools, issue 259); if it is unavailable, rely on the brief below. Then read the code
the scope names and split the tier into the smallest ordered tasks that can each be implemented and
tested on their own. Put tasks that touch the same function in dependency order (depends_on).
Every task names the exact test file(s) and cases; every behaviour toggle from the decisions names
its config key, CLI flag and MCP parameter. Only plan findings listed as in scope.
${TIER_BRIEF}`,
  { label: `plan tier ${tierNo}`, schema: PLAN_SCHEMA },
)
if (!plan || !plan.tasks.length) {
  log('Planner returned no tasks; stopping.')
  return { tier: tierNo, plan, implemented: [], gate: null }
}
log(`${plan.tasks.length} task(s): ${plan.tasks.map((t) => t.id).join(', ')}`)
if (plan.out_of_scope && plan.out_of_scope.length) log(`Deferred by planner: ${plan.out_of_scope.join('; ')}`)

// ---------------------------------------------------------------------------
// Implement: sequential on purpose. Tasks share files (semver.py, bump.py,
// config/model.py); parallel worktrees would only move the conflict to merge.
// ---------------------------------------------------------------------------

phase('Implement')
const implemented = []
for (const task of plan.tasks) {
  const res = await agent(
    `Implement task "${task.id}" of RRT-VER-1 tier ${tierNo} in this working tree.
Goal: ${task.goal}
Findings: ${task.findings.join(', ')}
Files: ${task.files.join(', ')}
Tests to add: ${task.tests.join(' | ')}
Docs to update: ${(task.docs || []).join(' | ') || 'none named; update any docstring/doc page your change makes wrong'}
Already done in earlier tasks: ${implemented.map((r) => `${r.id} (${r.status})`).join(', ') || 'nothing'}

Work test-first: add the failing regression test, see it fail, then make it pass. Keep the change
minimal and in the surrounding style. Run only the targeted tests (uv run pytest <files> -q) and
report their tail. Do not commit.
${TIER_BRIEF}`,
    { label: `impl ${task.id}`, phase: 'Implement', schema: IMPL_SCHEMA },
  )
  implemented.push(res || { id: task.id, status: 'blocked', changed_files: [], test_result: 'agent failed' })
  log(`${task.id}: ${res ? res.status : 'blocked'}`)
}

// ---------------------------------------------------------------------------
// Review: distinct lenses, then fix; loop until no blocking finding survives.
// ---------------------------------------------------------------------------

const LENSES = [
  { key: 'correctness', ask: 'version precedence, bump transitions and edge cases (0.x, pre-release of pre-release, calver, empty tag list, prefixes with glob chars). Try inputs that break the new code.' },
  { key: 'parity', ask: 'CLI/MCP/config parity: every new knob exists on all three surfaces with the same default and the same name mapping (decision D-4); MCP mutating tools default dry_run=True.' },
  { key: 'compat', ask: 'backwards compatibility: existing configs, existing tests, existing CHANGELOG files and tag layouts behave exactly as before unless a decision says otherwise; defaults match the decisions.' },
  { key: 'tests-docs', ask: 'coverage of every new branch (100% floor), regression test per finding, published docstring skeleton, docs pages and CHANGELOG [Unreleased] expectations.' },
]

phase('Review')
let blocking = []
for (let round = 0; round <= maxFixRounds; round++) {
  const reviews = await parallel(
    LENSES.map((lens) => () =>
      agent(
        `Review the uncommitted diff (git diff HEAD) for RRT-VER-1 tier ${tierNo} through the ${lens.key} lens:
${lens.ask}
Report only problems you can point at with a file and line and, for blocking ones, a concrete repro.
Mark severity blocking only when behaviour is wrong, a decision is violated, or a check would fail.
${TIER_BRIEF}`,
        { label: `review ${lens.key} r${round}`, phase: 'Review', schema: REVIEW_SCHEMA },
      ),
    ),
  )
  const all = reviews.filter(Boolean).flatMap((r) => r.findings)
  blocking = all.filter((f) => f.severity === 'blocking')
  const minor = all.length - blocking.length
  log(`review round ${round}: ${blocking.length} blocking, ${minor} minor`)
  if (!blocking.length || round === maxFixRounds) break

  await agent(
    `Fix these blocking review findings on the working tree, each with a test that fails before the fix.
Verify each finding first; if one does not reproduce, leave the code alone and say so.
${blocking.map((f, i) => `${i + 1}. ${f.file}:${f.line ?? '?'} ${f.problem}\n   repro: ${f.repro ?? 'n/a'}\n   suggested fix: ${f.fix}`).join('\n')}
Do not commit.
${TIER_BRIEF}`,
    { label: `fix round ${round}`, phase: 'Review' },
  )
}
if (blocking.length) log(`Still blocking after ${maxFixRounds} fix round(s): ${blocking.length}. Not committing.`)

// ---------------------------------------------------------------------------
// Gate
// ---------------------------------------------------------------------------

phase('Gate')
const gate = await agent(
  `Run these repository checks in order and report each result honestly (do not fix anything):
${GATE_COMMANDS.map((c) => `- ${c}`).join('\n')}
passed is true only if every command succeeded and total coverage is 100%.`,
  { label: 'gate', schema: GATE_SCHEMA, effort: 'low' },
)
log(`gate: ${gate && gate.passed ? 'passed' : 'failed'}`)

// ---------------------------------------------------------------------------
// Commit (opt-in). Never pushes: pushing and PRs stay with the caller.
// ---------------------------------------------------------------------------

let commit = null
if (doCommit && gate && gate.passed && !blocking.length) {
  phase('Commit')
  commit = await agent(
    `Stage the files changed for RRT-VER-1 tier ${tierNo} and create one Conventional Commit on the
current branch (type fix for tier 0, feat otherwise; scope "version"). Subject under 72 chars, body
lists the findings closed (${onlyFindings.join(', ')}) and "Refs ${ISSUE}". Validate the subject with
the rrt MCP tool rrt_validate_commit first if it is available. Do not push. Return the commit sha
and subject.`,
    { label: 'commit', phase: 'Commit', effort: 'low' },
  )
} else if (doCommit) {
  log('Commit skipped: gate failed or blocking findings remain.')
}

return {
  tier: tierNo,
  title: tier.title,
  findings: onlyFindings,
  plan: plan.tasks.map((t) => ({ id: t.id, findings: t.findings })),
  implemented: implemented.map((r) => ({ id: r.id, status: r.status, files: r.changed_files })),
  remaining_blocking: blocking,
  gate,
  commit,
}
