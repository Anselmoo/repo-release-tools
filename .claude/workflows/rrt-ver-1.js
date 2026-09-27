export const meta = {
  name: 'rrt-ver-1',
  description: 'Work through issue #259 (RRT-VER-1) tier by tier: every scope item is a contract that is planned, implemented, independently verified and acceptance-audited',
  whenToUse: 'Implementing issue #259 (RRT-VER-1): holistic versioning/bumping, MCP as the second workflow, release-process versioning. args: {workstream?: "versioning" | "mcp" | "release" | "all" (default), tier?: 0..5 | [..] (overrides workstream), commit?: true, maxAttempts?: 2, maxFixRounds?: 2}.',
  phases: [
    { title: 'Plan', detail: 'map every scope item of the tier to tasks; re-plan until nothing is left uncovered' },
    { title: 'Implement', detail: 'per task: implement test-first, then an independent verifier checks it; retry with the gaps' },
    { title: 'Review', detail: 'parallel lenses try to break the diff; fix loop' },
    { title: 'Accept', detail: 'audit every acceptance criterion with evidence; implement what is missing' },
    { title: 'Gate', detail: 'tests with 100% coverage, pre-commit, docs publish --check' },
    { title: 'Commit', detail: 'one conventional commit per task and per fix round (opt-in, never pushes)' },
  ],
}

// ---------------------------------------------------------------------------
// Source of truth: https://github.com/Anselmoo/repo-release-tools/issues/259
// The scope items below ARE the contract. The planner may split them into
// tasks and add detail from the issue, but it may not drop, merge away or
// reinterpret one. Every item has its own acceptance criteria, and the run is
// only successful when every criterion of every item is met with evidence.
// ---------------------------------------------------------------------------

const ISSUE = 'Anselmoo/repo-release-tools#259'

const DECISIONS = `
D-1  Starting a pre-release channel (alpha|beta|rc) from a FINAL version targets the next PATCH by
     default (1.0.0 -> 1.0.1-rc.1), like npm/node-semver (inc prerelease) and Poetry (prerelease).
     Toggle: [tool.rrt] prerelease_base = "patch" | "minor" | "major" | "auto" (per group overridable;
     "auto" = level from Conventional Commits since the last FINAL tag: breaking->major, feat->minor,
     else patch). CLI one-off: rrt bump rc --base minor. MCP: rrt_bump(level="rc", base="minor").
     Advancing inside a channel (rc.1 -> rc.2) or switching channel on the same core (beta.2 -> rc.1)
     never changes major.minor.patch.
D-2  [tool.rrt] prerelease_changelog = "cumulative" (default) | "fold" | "separate".
     cumulative: final section = all entries of that version's pre-release sections + anything new;
                 pre-release sections stay below it.
     fold:       like cumulative, pre-release sections replaced by one "Pre-releases: ..." line.
     separate:   today's behaviour.
     Always: git-log range for a final starts at the previous FINAL tag; dev never gets a section;
     post gets its own section.
D-3  version_policy defaults to "independent"; "lockstep" is opt-in.
D-4  Every new knob exists as [tool.rrt] config, CLI flag and MCP tool parameter, same default.
`

const TIERS = {
  0: {
    title: 'Independent bug fixes',
    items: [
      {
        id: 'T0.1', findings: ['F1'],
        what: 'Version.sort_key / comparison follows SemVer 2.0 §11 precedence: dot-separated pre-release identifiers compared left to right, numeric identifiers numerically, numeric < alphanumeric, a shorter identifier list sorts first when all preceding identifiers are equal. newer_versions() and every caller of sort_key inherit it.',
        files: ['src/repo_release_tools/version/semver.py', 'tests/ (version tests)'],
        acceptance: [
          'sorted(rc.1, rc.10, rc.2) == rc.1, rc.2, rc.10',
          'the SemVer §11 example chain 1.0.0-alpha < 1.0.0-alpha.1 < 1.0.0-alpha.beta < 1.0.0-beta < 1.0.0-beta.2 < 1.0.0-beta.11 < 1.0.0-rc.1 < 1.0.0 holds pairwise',
          'newer_versions returns rc.10 as newer than rc.2',
        ],
      },
      {
        id: 'T0.2', findings: ['F8'],
        what: 'Starting alpha/beta/rc from a FINAL version moves to the next patch by default, configurable per decision D-1 on all three surfaces (config key prerelease_base, CLI --base, MCP base). Includes config model + parsing + validation + config reference docs, Version.bump signature, commands/bump.py, commands/workspace.py pass-through, mcp/tools/version_tools.py.',
        files: [
          'src/repo_release_tools/version/semver.py', 'src/repo_release_tools/config/model.py',
          'src/repo_release_tools/config/core.py', 'src/repo_release_tools/commands/bump.py',
          'src/repo_release_tools/mcp/tools/version_tools.py', 'docs (config reference, version-release)',
        ],
        acceptance: [
          'Version("1.0.0").bump("rc") == 1.0.1-rc.1 (default patch); same for alpha and beta',
          'base=minor -> 1.1.0-rc.1; base=major -> 2.0.0-rc.1',
          'base=auto with a feat commit since the last final tag -> 1.1.0-rc.1; with a breaking change -> 2.0.0-rc.1; otherwise 1.0.1-rc.1',
          '1.0.1-rc.1 bump rc -> 1.0.1-rc.2 and 1.0.1-beta.2 bump rc -> 1.0.1-rc.1 (core unchanged, base ignored)',
          '[tool.rrt] prerelease_base is parsed, validated (invalid value -> config error), per-group override wins over global',
          '`rrt bump rc --base minor` works and wins over config; --dry-run shows the new version',
          'MCP rrt_bump accepts base and yields the same version as the CLI for the same input',
          'every new bump result is strictly greater than the current version',
        ],
      },
      {
        id: 'T0.3', findings: ['F9', 'F10'],
        what: 'One prefix-aware "latest tag" helper in workflow/git.py: list tags, keep those starting with the group tag_prefix, parse the remainder as a version (skip unparsable), sort by version precedence (final > its pre-releases). Provide latest_tag and latest_final_tag. Replace every `git tag --sort=-v:refname` lookup in commands/bump.py (git_log_since_latest_tag), commands/release_notes.py (_git_contributors, which must now honour the group tag_prefix) and commands/tag.py.',
        files: [
          'src/repo_release_tools/workflow/git.py', 'src/repo_release_tools/commands/bump.py',
          'src/repo_release_tools/commands/release_notes.py', 'src/repo_release_tools/commands/tag.py',
        ],
        acceptance: [
          'tags v1.0.0-rc.1, v1.0.0, v1.0.0-rc.2 -> latest_tag is v1.0.0',
          'tags v1.0.0, v1.1.0-rc.1 -> latest_tag v1.1.0-rc.1, latest_final_tag v1.0.0',
          'repo with v* and sdk-v* tags: each group resolves only its own prefix (bump range and release-notes contributors)',
          'unparsable tags with the prefix are ignored, not crashing',
          'grep finds no remaining `--sort=-v:refname` in src/',
        ],
      },
      {
        id: 'T0.4', findings: ['F14'],
        what: 'rrt workspace bump: a ValueError from bump() in the fail-early phase becomes a clean error line and exit code 1 (no traceback, no file written); `release` is an accepted kind.',
        files: ['src/repo_release_tools/commands/workspace.py'],
        acceptance: [
          'workspace bump pre-release on a stable package exits 1, prints the reason, writes nothing',
          'workspace bump release on a pre-release package finalizes it',
        ],
      },
      {
        id: 'T0.5', findings: ['F16'],
        what: 'action.yml detect-version step calls `rrt ci-version compute` so the detected-version output is populated.',
        files: ['action.yml'],
        acceptance: [
          'action.yml no longer calls bare `rrt ci-version`',
          'a test (or existing action test) asserts the compute subcommand is used',
        ],
      },
    ],
  },
  1: {
    title: 'Canonical version model',
    items: [
      { id: 'T1.1', findings: ['F2'], what: 'Structured Version with release/pre/post/dev/local per RRT-VER-1 §1; parses SemVer and PEP 440 spellings; existing public API keeps working.', files: ['src/repo_release_tools/version/'], acceptance: ['0.1.0.dev1, 0.1.0a1.dev2, 0.1.0rc1, 0.1.0.post1 and their SemVer inputs parse to the same canonical values', 'canonical order equals packaging.version order for the train in the issue', 'existing Version tests unchanged and passing'] },
      { id: 'T1.2', findings: ['F11'], what: 'version_scheme per group (semver|pep440|calver), inferred from the primary target when unset; read_group_current_version parses through the scheme.', files: ['src/repo_release_tools/config/', 'src/repo_release_tools/version/targets.py'], acceptance: ['2026.05.15 reads, bumps (calver) and writes back unchanged in format', 'version_scheme invalid value -> config error'] },
      { id: 'T1.3', findings: ['F2'], what: 'Bump algebra: every kind (major minor patch alpha beta rc pre-release release dev post calver explicit) defined for every state (final, pre, dev, post); invariant I5 new > current else refuse unless --force.', files: ['src/repo_release_tools/version/', 'docs'], acceptance: ['one parametrised test covers the full kind x state table', 'a regressing explicit version is refused without --force'] },
    ],
  },
  2: {
    title: 'Renderers per target format',
    items: [
      { id: 'T2.1', findings: ['F12'], what: 'format on VersionTarget and PinTarget (semver|pep440|rubygems|go-tag|oci-tag|calver), default inferred from kind; ci_format kept as deprecated alias; replace_all_versions_atomic renders each target.', files: ['src/repo_release_tools/config/model.py', 'src/repo_release_tools/version/targets.py'], acceptance: ['a group with pep621 + cargo_toml + gemspec writes each spelling from the renderings table of the issue', 'single-format repos produce byte-identical files'] },
      { id: 'T2.2', findings: ['F3', 'F7'], what: 'Renderers semver/pep440/rubygems/go-tag/oci-tag exactly as in the issue table.', files: ['src/repo_release_tools/version/'], acceptance: ['every row of the issue renderings table is a test case', 'I1 round trip holds for every representable value'] },
      { id: 'T2.3', findings: ['F4'], what: 'post refused (or mapped to patch with post_policy="patch") when a group target cannot express it.', files: ['src/repo_release_tools/version/', 'src/repo_release_tools/config/'], acceptance: ['post in a pep621+cargo group fails with an actionable message', 'post_policy=patch maps to next patch'] },
      { id: 'T2.4', findings: ['F3', 'F4', 'F7'], what: 'Conformance suite I1-I5 in Python against packaging, plus a runtime-marked CI job for node-semver, x/mod/semver, semver crate, RubyGems, NuGet.', files: ['tests/', '.github/workflows/'], acceptance: ['Python conformance tests pass', 'CI job defined and documented'] },
    ],
  },
  3: {
    title: 'CLI surface and holistic bumping',
    items: [
      { id: 'T3.1', findings: ['F15'], what: 'rrt version [--group] [--json] with canonical, scheme, rendered per target, pins, is_prerelease/is_devrelease/is_postrelease, next per kind.', files: ['src/repo_release_tools/commands/'], acceptance: ['JSON schema test', 'text output follows the ui/ dry-run/output contract'] },
      { id: 'T3.2', findings: ['F2'], what: 'rrt bump dev / rrt bump post wired through CLI and MCP.', files: ['src/repo_release_tools/commands/bump.py', 'src/repo_release_tools/mcp/tools/version_tools.py'], acceptance: ['bump dev from 0.1.0 -> 0.1.1.dev0 (pep440 spelling per target)', 'bump post respects T2.3'] },
      { id: 'T3.3', findings: ['F5'], what: 'ci-version compute: next-patch dev on the default branch, toggle for legacy behaviour.', files: ['src/repo_release_tools/commands/ci_version.py'], acceptance: ['base 0.1.0 on main -> 0.1.1.devN > 0.1.0', 'legacy toggle reproduces 0.1.0.devN'] },
      { id: 'T3.4', findings: ['F13', 'F14'], what: 'version_policy independent|lockstep + depends_on; one planner shared by bump --group a,b, workspace bump and sync --bump; atomic write, single rollback domain; workspace becomes a write category.', files: ['src/repo_release_tools/commands/', 'src/repo_release_tools/config/'], acceptance: ['3-group lockstep fixture bumps atomically', 'injected write failure rolls back every group', 'depends_on updates dependant pins'] },
    ],
  },
  4: {
    title: 'MCP as the second workflow',
    items: [
      { id: 'T4.1', findings: ['F23'], what: 'Shared pure cores returning Pydantic models for every version/release command; rrt_release_check stops importing private release_cmd._* helpers.', files: ['src/repo_release_tools/commands/', 'src/repo_release_tools/mcp/'], acceptance: ['no mcp module imports a private (_-prefixed) command helper'] },
      { id: 'T4.2', findings: ['F20'], what: 'rrt_bump supports every CLI kind, base, calver_scheme, changelog_mode, no_changelog, no_commit; errors as ConfigError.', files: ['src/repo_release_tools/mcp/tools/version_tools.py', 'src/repo_release_tools/mcp/models.py'], acceptance: ['parametrised test over all kinds', 'config error returns ConfigError model'] },
      { id: 'T4.3', findings: ['F21'], what: 'New tools rrt_bump_plan, rrt_ci_version, rrt_tag, rrt_release_notes, rrt_release_repair, rrt_release_status, rrt_verify_dist (mutating ones dry_run=True, confirm for hard-to-undo).', files: ['src/repo_release_tools/mcp/tools/'], acceptance: ['each tool has a dry-run default test', 'server instructions CLI-only list derived from the tool list, with a test'] },
      { id: 'T4.4', findings: ['F22'], what: 'rrt_changelog(group=...), rrt://changelog/{group}, rrt://versions; version overview UI extended; prompts updated.', files: ['src/repo_release_tools/mcp/'], acceptance: ['multi-group fixture reads each changelog', 'rrt://versions lists every group'] },
      { id: 'T4.5', findings: ['F23'], what: 'Generic CLI<->MCP parity test over every version/release command; Internal Contracts §MCP/CLI parity extended.', files: ['tests/e2e/', 'docs/src/content/docs/reference/internal-contracts.mdx'], acceptance: ['parity test enumerates every version/release command and fails if one lacks an MCP tool'] },
    ],
  },
  5: {
    title: 'Release process versioning',
    items: [
      { id: 'T5.1', findings: ['F6'], what: 'rrt release status [--group] [--json]: release-train node, allowed transitions, last tag per channel, Unreleased state.', files: ['src/repo_release_tools/commands/'], acceptance: ['fixture at each node reports the right allowed transitions'] },
      { id: 'T5.2', findings: ['F17'], what: 'prerelease_changelog cumulative|fold|separate per D-2 (default cumulative), config + CLI + MCP.', files: ['src/repo_release_tools/changelog.py', 'src/repo_release_tools/commands/bump.py', 'src/repo_release_tools/config/'], acceptance: ['rc.1 -> rc.2 -> final fixture produces the expected CHANGELOG for each of the three modes', 'final range starts at the previous final tag'] },
      { id: 'T5.3', findings: ['F19'], what: 'rrt tag create validates the canonical version and tag_format; tag check --strict compares tag, primary target and pins; rrt version verify-dist.', files: ['src/repo_release_tools/commands/tag.py', 'src/repo_release_tools/commands/'], acceptance: ['mismatching tag/target fails check --strict', 'verify-dist reads wheel, sdist, crate and npm tarball versions'] },
      { id: 'T5.4', findings: ['F6', 'F16'], what: 'action.yml outputs version, canonical-version, is-prerelease, is-devrelease, is-postrelease, publish-channel, release-notes-path; reference workflow documented.', files: ['action.yml', 'docs'], acceptance: ['outputs defined and populated from rrt version --json'] },
      { id: 'T5.5', findings: ['F18'], what: 'Dogfood .github/workflows/cicd.yml: ci-version sync before build, TestPyPI for dev/pre, PyPI for final/post, GitHub prerelease flag, notes from rrt release notes.', files: ['.github/workflows/cicd.yml'], acceptance: ['rc tag routes to TestPyPI + GitHub prerelease only', 'main push builds a unique dev version'] },
    ],
  },
}

const GATE_COMMANDS = [
  'uv run pytest -q -m "not runtime"   (pyproject addopts already enforce --cov-fail-under=100)',
  'uvx pre-commit run --all-files',
  'uv run rrt docs publish --check',
]

// ---------------------------------------------------------------------------
// Schemas
// ---------------------------------------------------------------------------

const PLAN_SCHEMA = {
  type: 'object',
  properties: {
    tasks: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string', description: 'kebab id, e.g. t0-1-semver-precedence' },
          covers: { type: 'array', items: { type: 'string' }, description: 'scope item ids (e.g. T0.1) this task delivers' },
          goal: { type: 'string' },
          steps: { type: 'array', items: { type: 'string' }, description: 'concrete edits, in order' },
          files: { type: 'array', items: { type: 'string' } },
          tests: { type: 'array', items: { type: 'string' }, description: 'test file :: case, one per acceptance criterion covered' },
          acceptance: { type: 'array', items: { type: 'string' }, description: 'the criteria of the covered items this task must satisfy, verbatim' },
        },
        required: ['id', 'covers', 'goal', 'steps', 'files', 'tests', 'acceptance'],
      },
    },
  },
  required: ['tasks'],
}

const IMPL_SCHEMA = {
  type: 'object',
  properties: {
    status: { type: 'string', enum: ['done', 'blocked'] },
    changed_files: { type: 'array', items: { type: 'string' } },
    tests_added: { type: 'array', items: { type: 'string' } },
    test_output_tail: { type: 'string' },
    blocker: { type: 'string', description: 'only when blocked: what exactly prevents completion' },
  },
  required: ['status', 'changed_files', 'tests_added', 'test_output_tail'],
}

const VERIFY_SCHEMA = {
  type: 'object',
  properties: {
    pass: { type: 'boolean' },
    criteria: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          criterion: { type: 'string' },
          met: { type: 'boolean' },
          evidence: { type: 'string', description: 'test id + its result, or file:line of the change' },
        },
        required: ['criterion', 'met', 'evidence'],
      },
    },
    gaps: { type: 'array', items: { type: 'string' }, description: 'what is missing or wrong, actionable' },
  },
  required: ['pass', 'criteria', 'gaps'],
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
          repro: { type: 'string' },
          fix: { type: 'string' },
        },
        required: ['file', 'severity', 'problem', 'fix'],
      },
    },
  },
  required: ['findings'],
}

const AUDIT_SCHEMA = {
  type: 'object',
  properties: {
    items: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          criteria: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                criterion: { type: 'string' },
                met: { type: 'boolean' },
                evidence: { type: 'string' },
              },
              required: ['criterion', 'met', 'evidence'],
            },
          },
        },
        required: ['id', 'criteria'],
      },
    },
  },
  required: ['items'],
}

const GATE_SCHEMA = {
  type: 'object',
  properties: {
    passed: { type: 'boolean' },
    results: {
      type: 'array',
      items: {
        type: 'object',
        properties: { command: { type: 'string' }, ok: { type: 'boolean' }, tail: { type: 'string' } },
        required: ['command', 'ok'],
      },
    },
  },
  required: ['passed', 'results'],
}

// ---------------------------------------------------------------------------
// Inputs
// ---------------------------------------------------------------------------

// The three workstreams of the issue. Each is runnable on its own, and the
// default runs all of them in dependency order.
//   versioning : holistic versioning and bumping (canonical model, renderers,
//                bump algebra, lockstep/depends_on, rrt version)
//   mcp        : the MCP server as the second workflow (parity with the CLI)
//   release    : versioning of the release process itself (train, tags,
//                changelog modes, CI routing, dogfooding)
const WORKSTREAMS = {
  versioning: [0, 1, 2, 3],
  mcp: [4],
  release: [5],
  all: [0, 1, 2, 3, 4, 5],
}

const input = args || {}
let tierList
if (input.tier !== undefined) {
  tierList = input.tier === 'all'
    ? WORKSTREAMS.all
    : (Array.isArray(input.tier) ? input.tier : [input.tier]).map(Number)
} else {
  const ws = input.workstream ?? 'all'
  if (!WORKSTREAMS[ws]) throw new Error(`Unknown workstream ${ws}; expected ${Object.keys(WORKSTREAMS).join(', ')}`)
  tierList = WORKSTREAMS[ws]
}
for (const t of tierList) if (!TIERS[t]) throw new Error(`Unknown tier ${t}; expected 0-5, a list, or "all"`)
log(`Running tiers ${tierList.join(', ')} (${input.workstream ?? (input.tier !== undefined ? 'explicit tiers' : 'all workstreams')})`)
const maxAttempts = Number(input.maxAttempts ?? 2)
const maxFixRounds = Number(input.maxFixRounds ?? 2)
const doCommit = input.commit === true

const itemBlock = (items) => items.map((it) =>
  `${it.id} [${it.findings.join(', ')}] ${it.what}\n  files: ${it.files.join(', ')}\n  acceptance:\n${it.acceptance.map((a) => `    - ${a}`).join('\n')}`,
).join('\n')

const RULES = `
Binding rules:
- Deliver the scope item completely. No stubs, TODOs, "follow-up" notes or partial implementations.
- Test-first: add the regression test for each acceptance criterion, watch it fail, then make it pass.
- Update every docstring/doc page the change makes wrong (published docstrings keep the
  ## Overview / ## Examples / ## Caveats / ## Related docs skeleton).
- CLI output only through repo_release_tools.ui; mutating commands keep --dry-run; no new runtime deps.
- Coverage floor 100%: every new branch is tested.
- Existing tests that encode the OLD behaviour a decision changes are updated, not deleted.
- Do not commit, do not push.`

async function commitStep(message, label) {
  if (!doCommit) return null
  return agent(
    `Stage all current changes and create one commit with this Conventional Commit message (subject
line first, then a blank line, then the body). Run the commit hooks; if a hook rewrites files, stage
them and commit again (at most 3 tries). Do not push. Return the sha and subject.
---
${message}
---`,
    { label, phase: 'Commit', effort: 'low' },
  )
}

// ---------------------------------------------------------------------------
// Tier loop
// ---------------------------------------------------------------------------

const report = []

for (const tierNo of tierList) {
  const tier = TIERS[tierNo]
  const scopeIds = tier.items.map((it) => it.id)
  const BRIEF = `Issue ${ISSUE} (RRT-VER-1), tier ${tierNo}: ${tier.title}
Scope items (the contract; every one must be delivered):
${itemBlock(tier.items)}
Decisions (binding):
${DECISIONS}
${RULES}`
  log(`Tier ${tierNo} (${tier.title}): ${scopeIds.join(', ')}`)

  // ----- Plan: every scope item must be covered; re-plan until it is. -----
  phase('Plan')
  let plan = null
  let uncovered = scopeIds
  let planFeedback = ''
  for (let attempt = 0; attempt <= maxAttempts && uncovered.length; attempt++) {
    plan = await agent(
      `Plan tier ${tierNo} of ${ISSUE}. Read the scope files first. If the GitHub MCP tool issue_read is
available, read issue 259 (owner Anselmoo, repo repo-release-tools) for extra detail; the scope items
below still win over anything else.
Split the scope items into ordered tasks. Every scope item id must appear in some task's "covers",
and every acceptance criterion of an item must appear verbatim in the "acceptance" of a task that
covers it. Do not drop, defer or merge away anything. Order tasks so a task only depends on earlier ones.
${planFeedback}
${BRIEF}`,
      { label: `plan tier ${tierNo} #${attempt}`, phase: 'Plan', schema: PLAN_SCHEMA },
    )
    const covered = new Set((plan ? plan.tasks : []).flatMap((t) => t.covers))
    uncovered = scopeIds.filter((id) => !covered.has(id))
    const missingCriteria = tier.items.flatMap((it) => it.acceptance
      .filter((a) => !(plan ? plan.tasks : []).some((t) => t.covers.includes(it.id) && t.acceptance.includes(a)))
      .map((a) => `${it.id}: ${a}`))
    if (missingCriteria.length) uncovered = [...new Set([...uncovered, ...missingCriteria.map((m) => m.split(':')[0])])]
    if (uncovered.length) {
      planFeedback = `Your previous plan was rejected. Uncovered items: ${uncovered.join(', ')}.
Criteria missing verbatim: ${missingCriteria.join(' | ') || 'none'}. Produce a complete plan.`
      log(`plan attempt ${attempt} rejected; uncovered: ${uncovered.join(', ')}`)
    }
  }
  if (!plan || uncovered.length) {
    log(`Tier ${tierNo}: no complete plan after ${maxAttempts + 1} attempts; stopping.`)
    report.push({ tier: tierNo, status: 'plan-incomplete', uncovered })
    break
  }
  log(`Tier ${tierNo}: ${plan.tasks.length} task(s): ${plan.tasks.map((t) => `${t.id}[${t.covers.join(',')}]`).join(' ')}`)

  // ----- Implement + independent verify, per task, with retries. -----
  phase('Implement')
  const taskResults = []
  for (const task of plan.tasks) {
    let verdict = null
    let feedback = ''
    let impl = null
    for (let attempt = 0; attempt <= maxAttempts; attempt++) {
      impl = await agent(
        `Implement task "${task.id}" (covers ${task.covers.join(', ')}) completely on this working tree.
Goal: ${task.goal}
Steps:
${task.steps.map((s, i) => `${i + 1}. ${s}`).join('\n')}
Files: ${task.files.join(', ')}
Tests (one per criterion): ${task.tests.join(' | ')}
Acceptance criteria this task must meet:
${task.acceptance.map((a) => `- ${a}`).join('\n')}
Earlier tasks: ${taskResults.map((r) => `${r.id}=${r.pass ? 'verified' : 'NOT verified'}`).join(', ') || 'none'}
${feedback}
Run the targeted tests and report the tail of their output.
${BRIEF}`,
        { label: `impl ${task.id} #${attempt}`, phase: 'Implement', schema: IMPL_SCHEMA },
      )
      verdict = await agent(
        `You are an independent verifier. Do NOT trust the implementer's report; check the working tree.
Task "${task.id}" (covers ${task.covers.join(', ')}) claims to be done.
For EACH criterion below: find the test that proves it (read it), run it, and inspect the code change
(git diff). A criterion is met only if a real test exercises it and passes, and the production code
implements it (not just the test). Also flag stubs, TODOs, skipped tests, and any criterion that is only
partly implemented (e.g. config key added but not wired to the CLI or MCP).
Criteria:
${task.acceptance.map((a) => `- ${a}`).join('\n')}
Implementer said: ${impl ? `${impl.status}; files ${impl.changed_files.join(', ')}; tests ${impl.tests_added.join(', ')}${impl.blocker ? `; blocker: ${impl.blocker}` : ''}` : 'no report (agent failed)'}`,
        { label: `verify ${task.id} #${attempt}`, phase: 'Implement', schema: VERIFY_SCHEMA },
      )
      if (verdict && verdict.pass && verdict.criteria.every((c) => c.met)) break
      const gaps = verdict ? [...verdict.gaps, ...verdict.criteria.filter((c) => !c.met).map((c) => `unmet: ${c.criterion} (${c.evidence})`)] : ['verifier failed']
      feedback = `A verifier rejected the previous attempt. Fix ALL of these:\n${gaps.map((g) => `- ${g}`).join('\n')}`
      log(`${task.id} attempt ${attempt} rejected: ${gaps.length} gap(s)`)
    }
    const pass = !!(verdict && verdict.pass && verdict.criteria.every((c) => c.met))
    taskResults.push({ id: task.id, covers: task.covers, pass, gaps: verdict ? verdict.gaps : ['verifier failed'] })
    log(`${task.id}: ${pass ? 'verified' : 'NOT verified'}`)
    if (pass) {
      await commitStep(
        `${tierNo === 0 ? 'fix' : 'feat'}(version): ${task.goal.slice(0, 60)}\n\nImplements ${task.covers.join(', ')} of RRT-VER-1 tier ${tierNo}.\n\nRefs #259`,
        `commit ${task.id}`,
      )
    }
  }

  // ----- Review: distinct lenses, fix loop. -----
  const LENSES = [
    { key: 'correctness', ask: 'version precedence and bump transitions: 0.x, pre-release of pre-release, calver, empty tag list, prefixes with glob characters, unparsable tags. Try inputs that break the new code.' },
    { key: 'parity', ask: 'every new knob exists as config, CLI flag and MCP parameter with the same name mapping and default (D-4); MCP mutating tools default dry_run=True.' },
    { key: 'contract', ask: 'every scope item is implemented as written, not a narrower reinterpretation; defaults match the decisions; nothing is stubbed.' },
    { key: 'tests-docs', ask: '100% coverage of new branches, one regression test per acceptance criterion, published docstring skeleton, docs pages and config reference updated.' },
  ]
  phase('Review')
  let blocking = []
  for (let round = 0; round <= maxFixRounds; round++) {
    const reviews = await parallel(LENSES.map((lens) => () => agent(
      `Review the diff of this tier (git diff ${doCommit ? 'origin/main' : 'HEAD'}) through the ${lens.key} lens: ${lens.ask}
Report only problems you can point at with file and line; blocking = wrong behaviour, violated decision,
missing scope, or a check that would fail. Give a concrete repro for blocking ones.
${BRIEF}`,
      { label: `review ${lens.key} r${round}`, phase: 'Review', schema: REVIEW_SCHEMA },
    )))
    const all = reviews.filter(Boolean).flatMap((r) => r.findings)
    blocking = all.filter((f) => f.severity === 'blocking')
    log(`tier ${tierNo} review ${round}: ${blocking.length} blocking, ${all.length - blocking.length} minor`)
    if (!blocking.length || round === maxFixRounds) break
    await agent(
      `Fix these blocking findings, each with a test that fails before the fix. Verify each first; if one
does not reproduce, leave the code and say so.
${blocking.map((f, i) => `${i + 1}. ${f.file}:${f.line ?? '?'} ${f.problem}\n   repro: ${f.repro ?? 'n/a'}\n   fix: ${f.fix}`).join('\n')}
${BRIEF}`,
      { label: `review-fix r${round}`, phase: 'Review' },
    )
    await commitStep(`fix(version): address review round ${round} of RRT-VER-1 tier ${tierNo}\n\nRefs #259`, `commit review r${round}`)
  }

  // ----- Accept: audit every criterion of every scope item; implement what is missing. -----
  phase('Accept')
  let unmet = []
  for (let round = 0; round <= maxFixRounds; round++) {
    const audit = await agent(
      `Acceptance audit for tier ${tierNo}. For EVERY scope item and EVERY one of its acceptance criteria,
find the proving test, run it, and check the production code. Report met/unmet with evidence
(test id + result, or why it is missing). Be strict: partially wired features are unmet.
${itemBlock(tier.items)}`,
      { label: `audit tier ${tierNo} r${round}`, phase: 'Accept', schema: AUDIT_SCHEMA },
    )
    const reported = new Map((audit ? audit.items : []).map((it) => [it.id, it.criteria]))
    unmet = tier.items.flatMap((it) => {
      const got = reported.get(it.id)
      if (!got) return it.acceptance.map((a) => ({ id: it.id, criterion: a, evidence: 'not audited' }))
      return it.acceptance
        .filter((a) => !got.some((c) => c.met && c.criterion.trim() === a.trim()))
        .map((a) => ({ id: it.id, criterion: a, evidence: (got.find((c) => c.criterion.trim() === a.trim()) || {}).evidence || 'no evidence' }))
    })
    log(`tier ${tierNo} acceptance ${round}: ${tier.items.reduce((n, it) => n + it.acceptance.length, 0) - unmet.length} met, ${unmet.length} unmet`)
    if (!unmet.length || round === maxFixRounds) break
    await agent(
      `These acceptance criteria are NOT met. Implement each completely (production code + test), then run
the tests for them.
${unmet.map((u) => `- ${u.id}: ${u.criterion}\n  audit evidence: ${u.evidence}`).join('\n')}
${BRIEF}`,
      { label: `accept-fix r${round}`, phase: 'Accept' },
    )
    await commitStep(`fix(version): complete acceptance round ${round} of RRT-VER-1 tier ${tierNo}\n\nRefs #259`, `commit accept r${round}`)
  }

  // ----- Gate -----
  phase('Gate')
  const gate = await agent(
    `Run these checks in order from the repo root and report each honestly (do not fix anything):
${GATE_COMMANDS.map((c) => `- ${c}`).join('\n')}
passed is true only if every command exits 0.`,
    { label: `gate tier ${tierNo}`, phase: 'Gate', schema: GATE_SCHEMA, effort: 'low' },
  )

  const ok = !!(gate && gate.passed) && !blocking.length && !unmet.length && taskResults.every((t) => t.pass)
  report.push({
    tier: tierNo,
    status: ok ? 'complete' : 'incomplete',
    tasks: taskResults,
    remaining_blocking: blocking,
    unmet_acceptance: unmet,
    gate,
  })
  log(`Tier ${tierNo}: ${ok ? 'COMPLETE' : 'INCOMPLETE'}`)
  if (!ok) break
}

return report
