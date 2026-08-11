<!--
rrt-pr-meta
type: feat|fix|refactor|perf|docs|chore|ci|build|test|deps
scope:
breaking: false

AGENT: fill the three fields above first — every other section below depends on them.
  type     -> the Conventional Commit type of this change. If your commits disagree, use the
              highest-impact one: feat > fix > refactor/perf > docs > chore/ci/build/test/deps.
  scope    -> the `(scope)` from your commit subject(s), or leave blank if you used none.
  breaking -> true only if a commit subject has `!` after type/scope, or a commit body has a
              `BREAKING CHANGE:` footer. Verify, don't guess:
                git log --format='%B' "$(git merge-base HEAD origin/main)"...HEAD | grep -E '^\w+(\(.+\))?!:|BREAKING CHANGE:'
  This block is not decorative: `type` determines the required changelog section in the
  Self-verification checklist (see SECTION_MAP in src/repo_release_tools/changelog.py), and
  `breaking` gates the "Breaking changes" section below.
-->

<!-- AGENT: run these once and reuse the output for every section below. Ground every claim
     in this actual output — do not reconstruct the diff from memory of what you intended to do.
       BASE=$(git merge-base HEAD origin/main)
       git log --format='%s' "$BASE"...HEAD
       git diff --stat "$BASE"...HEAD
-->

## Summary

<!-- AGENT: one sentence describing the mechanical change, derived from the `git diff --stat`
     output above. State what changed, not why — that belongs in the next section. -->

## Why

<!-- AGENT: state the intent behind the change. If you considered and rejected an alternative
     approach while implementing, name it and say why. If you made any judgment call the user
     did not explicitly specify, flag it here explicitly so a human reviewer knows what to
     double-check — do not silently absorb ambiguity. -->

## Traceability

- Related issue/task: <!-- AGENT: search the branch name and commit subjects for `#<number>`; if none is found, write N/A — do not invent one -->
- Modules touched: <!-- AGENT: paste the file list from `git diff --stat "$BASE"...HEAD` verbatim -->

## Breaking changes

<!-- AGENT: if `breaking: false` in the metadata block above, write "None" and stop there.
     If `breaking: true`, describe the break and the exact migration steps a downstream
     consumer must take — this is user-facing, not a restatement of your diff. -->

## Self-verification

<!-- AGENT: run every command below yourself before checking its box. A box checked without
     having run the command is a fabricated claim, not a verification. Your sandbox is not
     guaranteed to run this repo's pre-commit/lefthook git hooks automatically — run these
     commands directly rather than assuming a hook would have caught a problem. -->

- [ ] `uv run pytest -q -m "not runtime"` passes with no `Missing:` lines in the coverage report (floor is 100%, enforced by `--cov-fail-under=100` in `pyproject.toml`)
- [ ] Changelog: per `SECTION_MAP` in `src/repo_release_tools/changelog.py`, `type` values `feat/fix/refactor/perf/docs` require a `[Unreleased]` bullet in `CHANGELOG.md`; `chore/ci/build/test/deps` map to Maintenance and are exempt. Confirm which applies to the `type` set above, then check with `git diff "$BASE"...HEAD -- CHANGELOG.md` — or write N/A
- [ ] `rrt-hooks check-branch-name --branch "$(git branch --show-current)"` exits 0, and `rrt-hooks check-commit-subject --subject "<subject>"` exits 0 for each commit subject from the `git log` output above
- [ ] Every mutating `rrt` command run for this change (`rrt bump`, `rrt branch new`, etc.) was previewed with `--dry-run` first — list the commands run, or write N/A
- [ ] `rrt docs map --check` exits 0 — or N/A if no `[tool.rrt.docs.map]`-managed directory was touched

## Follow-ups (out of scope, not fixed here)

<!-- AGENT: noticed something else worth fixing while working? Don't fix it inline — that's
     scope creep. List it here as a one-line bullet instead; each is a candidate for a new
     "🤖 Agent Task" issue, not a reason to expand this PR. Empty is fine. -->

## Reviewer hand-off

<!-- AGENT: this repo's .github/workflows/claude-code-review.yml runs against every PR
     regardless of author — a Claude instance with none of your session's context will review
     this PR from the description and diff alone. Before finishing, re-read the sections above
     and confirm they contain everything that reviewer would need and could not infer from the
     diff alone.

     A maintainer can request follow-up work by mentioning `@claude` in a review comment, which
     triggers .github/workflows/claude.yml independently of how this PR was opened — that's a
     separate agent picking this up cold, not you resuming. -->
