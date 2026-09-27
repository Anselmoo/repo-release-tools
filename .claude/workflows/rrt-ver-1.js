export const meta = {
  name: 'rrt-ver-1',
  description: 'Implement one RRT-VER-1 roadmap tier (issue #259) test-first, review, verify, check',
  whenToUse:
    'Work through the RRT-VER-1 version/MCP/release roadmap from issue #259, one tier per run. ' +
    'args: {tier: "0"|"1"|"2"|"3"|"4"|"4b"|"5", commit?: boolean}',
  phases: [
    { title: 'Plan', detail: 'read the tier files, return steps, tests and risks' },
    { title: 'Implement', detail: 'regression tests first, then the fix, docs and parity' },
    { title: 'Review', detail: 'correctness, parity, docs, coverage lenses in parallel' },
    { title: 'Verify', detail: 'one skeptic per finding tries to refute it' },
    { title: 'Fix', detail: 'address the findings that survived' },
    { title: 'Checks', detail: 'pytest, pre-commit, docs publish --check, coverage floor' },
    { title: 'Commit', detail: 'one Conventional Commit, only when args.commit is true' },
  ],
}

const ISSUE = 'https://github.com/Anselmoo/repo-release-tools/issues/259'

// Decisions from the issue. Each one is a default that one config key can change,
// and each knob exists as [tool.rrt] config, CLI flag and MCP parameter (D-4).
const DECISIONS = [
  'D-1: a pre-release started from a final targets the next patch (1.0.0 -> 1.0.1-rc.1). ' +
    'Knob: prerelease_base = "patch" | "minor" | "major" | "auto" (per group); CLI --base; MCP base. ' +
    'Advancing inside a channel or switching channel never changes major.minor.patch.',
  'D-2: prerelease_changelog = "cumulative" (default) | "fold" | "separate". ' +
    'The git-log range for a final always starts at the previous final tag; dev never creates a section.',
  'D-3: version_policy = "independent" (default) | "lockstep"; per-group depends_on.',
  'D-4: parity. Every new knob is [tool.rrt] config, a CLI flag and an MCP tool parameter with the same default.',
  'D-5: pin_policy = "final-only" (default) | "all", per pin target overridable. ' +
    'Pins capture and compare the full version; pre-release and dev bumps leave final-only pins untouched.',
  'D-6: [tool.rrt.mcp] publish_prereleases = true (default). Pre-releases never move OCI latest; ' +
    'dev builds never publish. Confirm against the MCP Registry pre-release semantics before shipping.',
]

const TIERS = {
  0: {
    title: 'Independent bug fixes',
    closes: ['F1', 'F8', 'F9', 'F10', 'F14', 'F16', 'F24', 'F27'],
    scope: [
      'SemVer 2.0 section 11 comparator: numeric identifiers compare numerically (rc.2 < rc.10).',
      'Channel start on a final targets the next patch, with the prerelease_base toggle (D-1).',
      'One prefix-aware canonical latest-tag helper in workflow/git.py, used by bump, release notes and tag.',
      'action.yml detect-version step calls `rrt ci-version compute` instead of the bare group command.',
      'workspace bump: clean error for pre-release on a stable package; accept the release kind.',
      'Pins: capture and compare the full version (no "-rc.2-rc.1" residue); add pin_policy (D-5).',
      'cicd.yml: OCI latest only for final tags.',
    ],
    acceptance: [
      'A regression test per finding.',
      '`rrt bump rc` after 1.0.0 yields 1.0.1-rc.1, and 1.1.0-rc.1 with base=minor.',
      'The latest tag after v1.0.0 is v1.0.0, not v1.0.0-rc.2.',
      'rc -> rc -> release leaves pins at the last final (final-only) or at the new final with no residue (all).',
      'An rc tag does not push :latest.',
    ],
    files: [
      'src/repo_release_tools/version/semver.py',
      'src/repo_release_tools/version/targets.py',
      'src/repo_release_tools/workflow/git.py',
      'src/repo_release_tools/commands/bump.py',
      'src/repo_release_tools/commands/release_notes.py',
      'src/repo_release_tools/commands/release_cmd.py',
      'src/repo_release_tools/commands/tag.py',
      'src/repo_release_tools/commands/workspace.py',
      'src/repo_release_tools/config/model.py',
      'action.yml',
      '.github/workflows/cicd.yml',
    ],
  },
  1: {
    title: 'Canonical model',
    closes: ['F2', 'F11'],
    scope: [
      'Structured Version: release (major, minor, patch), pre (alpha|beta|rc, n), post, dev, local.',
      'Accept both SemVer and PEP 440 spellings as input; keep today\'s SemVer config strings valid.',
      'version_scheme per group ("semver" | "pep440" | "calver"), inferred from the primary target.',
      'read_group_current_version parses through the scheme, so CalVer such as 2026.05.15 reads back.',
      'Bump algebra as a table: every kind (major, minor, patch, alpha, beta, rc, pre-release, release, ' +
        'dev, post, calver, explicit) for every state (final, pre, dev, post).',
      'Invariant I5: every transition is strictly monotonic, otherwise refuse unless --force and name the target.',
    ],
    acceptance: [
      'A parametrised transition-table test covering every kind x state.',
      '2026.05.15 round-trips through read and bump.',
    ],
    files: [
      'src/repo_release_tools/version/semver.py',
      'src/repo_release_tools/version/pep440.py',
      'src/repo_release_tools/version/calver.py',
      'src/repo_release_tools/version/targets.py',
      'src/repo_release_tools/config/model.py',
      'src/repo_release_tools/commands/bump.py',
    ],
  },
  2: {
    title: 'Renderers',
    closes: ['F3', 'F4', 'F7', 'F12'],
    scope: [
      'format on VersionTarget and PinTarget: semver | pep440 | rubygems | go-tag | oci-tag | calver | custom.',
      'Defaults from kind: pep621/python_version -> pep440; cargo_toml/package_json/csproj/maven_pom -> semver; ' +
        'gemspec -> rubygems; mcp_server_json OCI entries -> oci-tag. ci_format becomes a deprecated alias.',
      'replace_all_versions_atomic renders each target from the canonical version.',
      'SemVer dev rendering uses the numeric-identifier trick (0.1.0-0.dev.1, <channel>.(N-1).dev.M).',
      'post is refused for SemVer targets unless post_policy = "patch".',
      'Conformance suite I1-I5 against the real comparators, as a CI matrix job.',
    ],
    acceptance: [
      'Matrix job green for packaging, node-semver, golang.org/x/mod/semver, the semver crate, RubyGems and NuGet.Versioning.',
      'Every rendering in the issue\'s renderer table round-trips (I1) and sorts identically (I2).',
    ],
    files: [
      'src/repo_release_tools/version/',
      'src/repo_release_tools/config/model.py',
      '.github/workflows/cicd.yml',
      'tests/version/',
    ],
  },
  3: {
    title: 'CLI surface',
    closes: ['F5', 'F13', 'F15'],
    scope: [
      '`rrt version [--group G] [--json]`: canonical, scheme, rendered per target, pins, ' +
        'is_prerelease/is_devrelease/is_postrelease, next per bump kind (or refusal reason).',
      '`rrt bump dev` and `rrt bump post` with the group-level post refusal.',
      'ci-version compute uses next-patch dev by default (0.1.0 -> 0.1.1.devN), switchable.',
      'version_policy / depends_on (D-3).',
      'One planner shared by `bump --group a,b`, `workspace bump` and `sync --bump`: resolve all, compute all, ' +
        'validate I4/I5, write atomically in one rollback domain, lock commands, one commit. workspace becomes a write command.',
    ],
    acceptance: [
      'A lockstep fixture with 3 groups bumps atomically.',
      'A rollback test: a failure in the last target leaves every file unchanged.',
    ],
    files: [
      'src/repo_release_tools/cli.py',
      'src/repo_release_tools/commands/bump.py',
      'src/repo_release_tools/commands/workspace.py',
      'src/repo_release_tools/commands/ci_version.py',
      'src/repo_release_tools/commands/_version_render.py',
    ],
  },
  4: {
    title: 'MCP workflow',
    closes: ['F20', 'F21', 'F22', 'F23'],
    scope: [
      'Shared pure cores returning Pydantic models; CLI renders via ui/, MCP returns the model.',
      'rrt_bump covers every kind and knob; rrt_bump_plan; rrt_ci_version; rrt_tag (create needs confirm); ' +
        'rrt_release_notes; rrt_release_repair; rrt_release_status; rrt_verify_dist.',
      'rrt_changelog(group=...), rrt://changelog/{group}, rrt://versions.',
      'rrt_version_overview gains rendered columns, pins, classification, bump preview and train position.',
      'Prompts updated; the server instructions\' CLI-only list is derived from the tool list in a test.',
      'A generic MCP <-> CLI parity test over every version and release command.',
    ],
    acceptance: [
      'The parity test covers every version/release command.',
      'The instructions\' CLI-only list is derived from the registered tools.',
    ],
    files: [
      'src/repo_release_tools/mcp/',
      'docs/src/content/docs/reference/internal-contracts.mdx',
      'tests/mcp/',
    ],
  },
  '4b': {
    title: 'MCP distribution (needs tier 2)',
    closes: ['F25', 'F26', 'F28', 'F29', 'F30', 'F31'],
    scope: [
      'Per-field server.json rendering: version -> semver, packages[pypi].version -> pep440, ' +
        'packages[npm].version -> semver, packages[oci].identifier tag -> oci-tag. A mismatched identifier is an error.',
      'Distribution block in `rrt version --json`: server.json fields, OCI tags (latest only for finals), .mcpb version, registry channel.',
      'mcpb_manifest target kind; verify-dist covers .mcpb and the OCI image version label.',
      'Registry / OCI latest / GitHub release routing by classification (D-6).',
      'Doctor and release-check distribution checks: server.json name vs Dockerfile label, every version field vs canonical, ' +
        'explicit-config cross-target agreement, mcp-publisher validate when available, zero-match pin targets reported.',
      'rrt init mcp-server preset; autodetect server.json.',
      '`rrt release plan --json` / rrt_release_plan (D.8) and the Action release-plan output.',
      'cicd.yml drops the jq server.json sync and uses the rrt renderer.',
    ],
    acceptance: [
      'server.json fields are rendered per format and never silently skipped.',
      'An rc tag gives a registry version and a GitHub prerelease without moving latest; a dev build publishes nothing.',
      'Drift between server.json, targets, .mcpb and the image label fails release check.',
      'release plan output is identical across CLI, MCP and Action.',
    ],
    files: [
      'src/repo_release_tools/version/targets.py',
      'src/repo_release_tools/commands/release_cmd.py',
      'src/repo_release_tools/commands/doctor.py',
      'src/repo_release_tools/commands/init.py',
      'src/repo_release_tools/config/core.py',
      'src/repo_release_tools/mcp/tools/release_tools.py',
      'server.json',
      'Dockerfile',
      'action.yml',
      '.github/workflows/cicd.yml',
    ],
  },
  5: {
    title: 'Release process',
    closes: ['F6', 'F17', 'F18', 'F19'],
    scope: [
      '`rrt release status`: the release train as a state machine per group.',
      'Canonical tag resolution everywhere, with a latest_final variant for changelog ranges.',
      'prerelease_changelog modes (D-2).',
      'Tag validation and tag_format; `rrt tag check --strict`.',
      '`rrt version verify-dist <dist-dir> --tag <tag>`.',
      'Action outputs: version, canonical-version, is-prerelease, is-devrelease, is-postrelease, publish-channel, ' +
        'release-notes-path, oci-tags, move-latest, mcp-registry-publish, mcpb-version, release-plan.',
      'Dogfood the reference workflow in this repository\'s cicd.yml.',
      'Hotfix and post releases follow the F4 rule (post_policy).',
    ],
    acceptance: [
      'An end-to-end fixture dev -> rc.1 -> rc.2 -> final -> post produces correct tags, changelog in all three modes, ' +
        'classification and publish channel.',
    ],
    files: [
      'src/repo_release_tools/changelog.py',
      'src/repo_release_tools/commands/release_cmd.py',
      'src/repo_release_tools/commands/tag.py',
      'src/repo_release_tools/workflow/git.py',
      'action.yml',
      '.github/workflows/cicd.yml',
    ],
  },
}

// Object keys put '4b' after '5'; list the roadmap order explicitly.
const TIER_ORDER = ['0', '1', '2', '3', '4', '4b', '5']

const tierKey = String(args?.tier ?? '')
const tier = TIERS[tierKey]
if (!tier) {
  throw new Error(
    `Unknown tier ${JSON.stringify(args?.tier)}. Valid tiers: ${TIER_ORDER.join(', ')}. ` +
      'Example: Workflow({name: "rrt-ver-1", args: {tier: "0"}})',
  )
}
const commit = args?.commit === true

const CONTEXT = [
  `You are implementing tier ${tierKey} ("${tier.title}") of the RRT-VER-1 roadmap in ${ISSUE}.`,
  'Fetch the issue body first (GitHub MCP issue_read, owner Anselmoo, repo repo-release-tools, issue 259) ' +
    'and read the findings this tier closes, with their evidence and reproduction.',
  `Findings closed: ${tier.closes.join(', ')}.`,
  `Scope:\n- ${tier.scope.join('\n- ')}`,
  `Acceptance:\n- ${tier.acceptance.join('\n- ')}`,
  `Key files:\n- ${tier.files.join('\n- ')}`,
  `Decisions (encode the default, expose the knob on config, CLI and MCP):\n- ${DECISIONS.join('\n- ')}`,
  'Stay inside this tier. Anything that belongs to a later tier is a note in your output, not code.',
].join('\n\n')

const PLAN_SCHEMA = {
  type: 'object',
  properties: {
    steps: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          finding: { type: 'string' },
          change: { type: 'string' },
          files: { type: 'array', items: { type: 'string' } },
          tests: { type: 'array', items: { type: 'string' } },
        },
        required: ['finding', 'change', 'files', 'tests'],
      },
    },
    reuse: { type: 'array', items: { type: 'string' } },
    risks: { type: 'array', items: { type: 'string' } },
    deferred: { type: 'array', items: { type: 'string' } },
  },
  required: ['steps', 'risks'],
}

const FINDINGS_SCHEMA = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          file: { type: 'string' },
          line: { type: 'integer' },
          severity: { type: 'string', enum: ['blocker', 'major', 'minor'] },
          summary: { type: 'string' },
          failure_scenario: { type: 'string' },
        },
        required: ['file', 'severity', 'summary', 'failure_scenario'],
      },
    },
  },
  required: ['findings'],
}

const VERDICT_SCHEMA = {
  type: 'object',
  properties: {
    refuted: { type: 'boolean' },
    reason: { type: 'string' },
  },
  required: ['refuted', 'reason'],
}

const CHECKS_SCHEMA = {
  type: 'object',
  properties: {
    passed: { type: 'boolean' },
    results: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          command: { type: 'string' },
          passed: { type: 'boolean' },
          summary: { type: 'string' },
        },
        required: ['command', 'passed', 'summary'],
      },
    },
  },
  required: ['passed', 'results'],
}

phase('Plan')
const plan = await agent(
  `${CONTEXT}\n\nRead the key files and the tests that cover them. Do not edit anything. ` +
    'Return one step per finding: the change, the files it touches, and the regression tests that fail today ' +
    'and pass after the change. List existing helpers to reuse, the risks, and anything deferred to a later tier.',
  { label: `plan:tier-${tierKey}`, phase: 'Plan', schema: PLAN_SCHEMA },
)
if (!plan) throw new Error('Plan phase returned nothing; aborting before any edit.')
log(`Tier ${tierKey}: ${plan.steps.length} planned steps, ${plan.risks.length} risks`)

phase('Implement')
const implementation = await agent(
  `${CONTEXT}\n\nPlan:\n${JSON.stringify(plan, null, 2)}\n\n` +
    'Implement the plan test-first:\n' +
    '1. Write the regression tests for each finding and run them to see them fail.\n' +
    '2. Make the change, then run the tests to see them pass.\n' +
    '3. Update the published module docstrings you touched (Overview, Examples, Caveats, Related docs; ' +
    'at most 22 words per sentence) and the version-release command docs.\n' +
    '4. New CLI output goes through repo_release_tools.ui (DryRunPrinter); every mutating path honours --dry-run.\n' +
    '5. Keep MCP and Action behaviour in parity with the CLI where this tier touches them (D-4).\n' +
    'No new runtime dependencies. Do not commit. Return a short summary of the diff and the tests added.',
  { label: `implement:tier-${tierKey}`, phase: 'Implement' },
)

const LENSES = [
  {
    key: 'correctness',
    prompt:
      'Correctness lens. Check every version comparison, rendering and transition against SemVer 2.0 ' +
      '(section 11 precedence) and PEP 440 (dev < a < b < rc < final < post). Look for off-by-one channel ' +
      'numbers, non-monotonic transitions, silent fall-through on unparseable input and broken rollback.',
  },
  {
    key: 'parity',
    prompt:
      'Parity lens. Compare the CLI, the MCP tools and action.yml for every behaviour this diff touches. ' +
      'Every new knob must exist as [tool.rrt] config, CLI flag and MCP parameter with the same default (D-4). ' +
      'Error shapes and dry-run defaults must match the Internal Contracts page.',
  },
  {
    key: 'docs',
    prompt:
      'Docs lens. Published docstrings under commands/, workflow/, integrations/ and eol/ must keep ' +
      'Overview, Examples, Caveats, Related docs, with Overview first and the last two in order, ' +
      'and at most 22 words per sentence. The version-release docs and the changelog behaviour must match the code.',
  },
  {
    key: 'coverage',
    prompt:
      'Coverage lens. Every new branch needs a test; the floor is 100%. Every finding this tier closes ' +
      'needs a regression test that fails without the fix. Flag tests that assert nothing meaningful.',
  },
]

phase('Review')
const reviewed = await pipeline(
  LENSES,
  (lens) =>
    agent(
      `${CONTEXT}\n\nImplementation summary:\n${implementation}\n\n${lens.prompt}\n\n` +
        'Review the working-tree diff (`git diff` plus untracked files). Report only concrete defects with a failure scenario.',
      { label: `review:${lens.key}`, phase: 'Review', schema: FINDINGS_SCHEMA },
    ),
  (review, lens) =>
    parallel(
      (review?.findings ?? []).map((finding) => () =>
        agent(
          `Try to refute this ${lens.key} review finding on the working-tree diff for tier ${tierKey} of ${ISSUE}. ` +
            'Read the code and, where possible, run a minimal reproduction. ' +
            'Set refuted=true if the failure scenario cannot happen or is already handled; default to refuted=true if uncertain.\n\n' +
            JSON.stringify(finding, null, 2),
          { label: `verify:${lens.key}:${finding.file}`, phase: 'Verify', schema: VERDICT_SCHEMA },
        ).then((verdict) => ({ ...finding, lens: lens.key, verdict })),
      ),
    ),
)
const confirmed = reviewed
  .filter(Boolean)
  .flat()
  .filter(Boolean)
  .filter((f) => f.verdict && !f.verdict.refuted)
log(`${confirmed.length} review findings survived verification`)

if (confirmed.length > 0) {
  phase('Fix')
  await agent(
    `${CONTEXT}\n\nFix each of these verified review findings in the working tree. ` +
      'Add or adjust a test for each. Do not commit.\n\n' +
      JSON.stringify(confirmed, null, 2),
    { label: `fix:tier-${tierKey}`, phase: 'Fix' },
  )
}

phase('Checks')
const checks = await agent(
  'Run these repository checks from the repo root and report each result. Fix nothing; only report.\n' +
    '1. uv run pytest -q -m "not runtime" --cov --cov-report=term-missing\n' +
    '2. uvx pre-commit run --all-files\n' +
    '3. uv run rrt docs publish --check\n' +
    'passed is true only if all three pass and total coverage is 100%.',
  { label: `checks:tier-${tierKey}`, phase: 'Checks', schema: CHECKS_SCHEMA },
)

let committed = false
if (commit && checks?.passed) {
  phase('Commit')
  const result = await agent(
    `Stage the tier ${tierKey} changes and create one Conventional Commit. ` +
      `Pick the type from the change (fix for tier 0, feat otherwise) and reference ${ISSUE} and ` +
      `the findings ${tier.closes.join(', ')} in the body. Do not push. Return the commit hash.`,
    { label: `commit:tier-${tierKey}`, phase: 'Commit' },
  )
  committed = Boolean(result)
} else if (commit) {
  log('Checks failed, so nothing was committed.')
}

return {
  tier: tierKey,
  title: tier.title,
  closes: tier.closes,
  plan,
  confirmedFindings: confirmed,
  checks,
  committed,
}
