<!--
rrt-pr-meta
type: feat|fix|refactor|perf|docs|chore|ci|build|test|deps
scope:
breaking: false

CLAUDE: fill the three fields above first — every other section below depends on them.
  type     -> the Conventional Commit type of this change. If your commits disagree, use the
              highest-impact one: feat > fix > refactor/perf > docs > chore/ci/build/test/deps.
  scope    -> the `(scope)` from your commit subject(s), or leave blank if you used none.
  breaking -> true only if a commit subject has `!` after type/scope, or a commit body has a
              `BREAKING CHANGE:` footer. Verify, don't guess:
                git log --format='%B' "$(git merge-base HEAD origin/main)"...HEAD | grep -E '^\w+(\(.+\))?!:|BREAKING CHANGE:'
  `type` determines the required changelog section (see SECTION_MAP in
  src/repo_release_tools/changelog.py); `breaking` gates the "Breaking changes" section below.
-->

<!-- CLAUDE: run these once and reuse the output for every section below. Ground every claim in
     this actual output — don't reconstruct the diff from memory of what you intended to do.
       BASE=$(git merge-base HEAD origin/main)
       git log --format='%s' "$BASE"...HEAD
       git diff --stat "$BASE"...HEAD
-->

## Summary

<!-- CLAUDE: one sentence, derived from the `git diff --stat` output above. -->

## Why

<!-- CLAUDE: intent behind the change, alternatives considered and rejected, and any judgment
     call you made that wasn't explicitly specified — flag those so the reviewer knows what to
     double-check rather than silently absorbing the ambiguity. -->

## Traceability

- Related issue/task: <!-- CLAUDE: search the branch name and commit subjects for `#<number>`; N/A if none — don't invent one -->
- Modules touched: <!-- CLAUDE: paste the file list from `git diff --stat "$BASE"...HEAD` verbatim -->

## Breaking changes

<!-- CLAUDE: "None" if `breaking: false` above. Otherwise describe the break and the exact
     migration steps a downstream consumer must take. -->

## Self-verification

<!-- CLAUDE: run every command below yourself before checking its box — a box checked without
     having run the command is a fabricated claim.

     This repo has a two-tier coverage gate: the local Stop hook
     (.claude/hooks/coverage_non_regression.py) allows a small margin during iteration so it
     doesn't false-block on stale/partial state — that leniency is NOT proof of anything.
     `git push` (check_push_coverage.py) and CI always re-verify fresh at a hard 100%. Verify
     against that number, not against the Stop hook having stayed quiet. If possible, mention the fixed issue(s) via GitHub notation (e.g. Fixes #123). -->

- [ ] `uv run pytest -q -m "not runtime"` passes with no `Missing:` lines (`--cov-fail-under=100` in `pyproject.toml`)
- [ ] Changelog: per `SECTION_MAP`, `feat/fix/refactor/perf/docs` need a `[Unreleased]` bullet; `chore/ci/build/test/deps` are exempt — confirm with `git diff "$BASE"...HEAD -- CHANGELOG.md`, or N/A
- [ ] `rrt-hooks check-branch-name --branch "$(git branch --show-current)"` exits 0, and `rrt-hooks check-commit-subject --subject "<subject>"` exits 0 for each commit subject above
- [ ] Every mutating `rrt` command run for this change was previewed with `--dry-run` first — list them, or N/A
- [ ] `rrt docs map --check` exits 0 — or N/A if no `[tool.rrt.docs.map]`-managed directory was touched
- [ ] Fixes:

## Follow-ups (out of scope, not fixed here)

<!-- CLAUDE: noticed something else worth fixing while working? Don't fix it inline — that's
     scope creep. List it here as a one-line bullet instead; each is a candidate for a new
     "🤖 Agent Task" issue, not a reason to expand this PR. Empty is fine. -->

## Reviewer hand-off

<!-- CLAUDE: .github/workflows/claude-code-review.yml runs a FRESH Claude instance against this
     PR with none of this session's conversation — it sees only this description and the diff.
     Before finishing, re-read the sections above and confirm they contain everything that
     reviewer would need and could not infer from the diff alone.

     After merge, a maintainer can request follow-up work by mentioning `@claude` in a review
     comment or issue comment — that re-triggers .github/workflows/claude.yml. That session
     starts cold too: reference this PR number, don't assume it remembers this conversation. -->
