# Business Rules — repo-release-tools (`src/repo_release_tools`)

*Generated 2026-07-10 by `/modernize-extract-rules` (4 extraction rounds, per-rule citation verification by independent referee agents) and rendered by `render_business_rules.py`. 338 rules confirmed, 6 rejected by referees.*

## Methodology & caveats

- Three lens-scoped extractor agents per round (calculations / validations / lifecycle), loop-until-dry; **extraction stopped at the 4-round cap before running dry** — round 4 still surfaced 66 new rules, so a tail of lower-value rules likely remains uncatalogued.
- Every rule below was confirmed by a referee agent that re-read the cited source location. 6 rules failed refereeing and are listed at the end.
- **P0 adjudication caveat:** the workflow's independent P0 judging panel hit a usage limit and did not complete. The Behavior Contract section below was adjudicated in the coordinating session by a stated criterion (see there) and **requires SME confirmation before any phase ships against it.** The panel verdicts that did complete consistently re-tiered pure version arithmetic away from P0 (no money, no regulation) — that reasoning is applied here.
- One **prompt-injection attempt** was detected in tool output during verification (a fabricated 'MCP Server Instructions' block not present in any repo file). The verifying agent disregarded it; no rule cites it. Recorded here because rule text mined from untrusted code is data, not instructions.

## Behavior Contract (P0 candidates)

**Criterion:** for a release tool, 'moves money / regulatory / data integrity' translates to: *guards the integrity of the user's repository (files, git history, published artifacts) or gates a destructive, irreversible operation.* These rules must be pinned by characterization tests and proven equivalent before any modernization phase ships. 58 rules qualify:

### P0-01 — Action publish-snapshot composite kept isolated from main policy-check Action by trigger risk profile

**Category:** Policy · **Priority:** P1 · **Confidence:** Medium
**Source:** `/Users/hahn/LocalDocuments/GitHub_Forks/repo-release-tools/action.yml (main policy-check composite action, no force-push input) and /Users/hahn/LocalDocuments/GitHub_Forks/repo-release-tools/actions/publish-snapshot/action.yml (separate composite action definition containing the force-push step)`

The force-push snapshot-publishing capability is deliberately packaged as a separate GitHub Action (not a flag on the main read-only policy-check Action) so that destructive force-push behavior can only be triggered from workflows that explicitly opt into it (push-to-main/schedule/workflow_dispatch), never accidentally from a PR-triggered policy check run.

- **Given** a consuming repository's PR workflow uses only the main `Anselmoo/repo-release-tools@vX` action for branch/commit/changelog checks
- **When** any PR is opened
- **Then** no force-push can occur from that workflow, because publish-snapshot lives at a distinct action path (`.../actions/publish-snapshot@vX`) that must be referenced explicitly and separately
- **Parameters:** n/a
- **Edge case:** confirm input on the publish-snapshot action defaults to 'false', meaning even when explicitly wired in, it still only dry-runs unless a workflow author sets confirm: 'true' (action.py:172,180)
- ❓ **SME question:** Citation was corrected by referee (The cited lines src/repo_release_tools/integrations/action.py:138-150 are a Python triple-quoted string (GITHUB_ACTION_PUBLISH_SNAPSHOT_DOC) that is rendered into markdown documentation (see SOURCE_OWNED_TOPIC_DOCS mapping at action.py:196-199, and docs/src/content/docs/publish-snapshot-action.mdx). It is prose explaining the design rationale ("It is deliberately not part of the ma…

### P0-02 — Maintenance-type changelog entries are gated by include_maintenance when generating a release section

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/changelog.py:169-219`

When rrt generates a new changelog section from git history (rather than promoting an existing [Unreleased] section), commits of chore/ci/build/test/deps type are only included in the rendered output if the caller explicitly opts in via include_maintenance=True.

- **Given** Given commit subjects containing 3 'chore:' commits and 2 'feat:' commits, and include_maintenance=False
- **When** When build_changelog_section renders the section
- **Then** Then the Maintenance subsection is omitted entirely from the output even though matching entries were parsed; only the Added subsection (from feat commits) appears
- **Parameters:** SECTION_ORDER = [Breaking Changes, Added, Fixed, Changed, Documentation, Maintenance]
- **Edge case:** If no sections end up with entries at all (e.g. all commits were maintenance-only and include_maintenance=False), the output falls back to '_No notable changes recorded._'

### P0-03 — New branch creation carries uncommitted working-tree changes onto the new branch

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/branch.py:177-234`

`rrt branch new` refuses to create a branch that already exists, then creates and checks out the new branch via `git checkout -b`; any uncommitted staged/unstaged changes on the source branch automatically move with the checkout (native git behavior), and the command reports how many files, staged vs. unstaged, moved along.

- **Given** the working tree has 2 staged and 1 unstaged file when creating feat/new-thing
- **When** `rrt branch new feat "new thing"` runs (not dry-run)
- **Then** git checkout -b feat/new-thing succeeds and the 3 changed files are now attributed to the new branch; the command reports 'Files changed: 3, Staged: 2, Unstaged: 1' and lists up to STATUS_MAX changed files, truncating the rest with a '…and N more' summary

### P0-04 — Branch/tag creation guard: refuse to overwrite existing name

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/branch.py:191-197,346-352,409-415`

rrt branch new, rename, and rescue all refuse to create/rename to a branch name that already exists (except bump's explicit --force override), requiring the user to delete the branch first or choose a different name/description.

- **Given** Branch 'feat/add-parser' already exists
- **When** rrt branch new feat 'add parser' runs (non-dry-run)
- **Then** Command exits 1 with "Branch 'feat/add-parser' already exists. Delete it first or choose a different description."

### P0-05 — Changelog update mode resolution

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/bump.py:152-156,168-269`

How the changelog is written during a bump depends on the workflow: 'auto' promotes existing [Unreleased] entries if present, otherwise generates a section from git log since the last tag; 'promote' requires existing entries or aborts with a message; 'generate' always builds fresh from git log, ignoring [Unreleased].

- **Given** changelog_mode='promote' and the [Unreleased] section is empty
- **When** update_changelog(..., changelog_mode='promote') runs
- **Then** no file is written; a message is printed: '[Unreleased] section in <path> is empty — nothing to promote.' and the function returns without failing the whole bump
- **Parameters:** changelog_mode default resolution: 'generate' if config.changelog_workflow == 'squash' else 'auto' (bump.py:152-156)
- **Edge case:** missing changelog file entirely -> skip with 'not found — skipping', not a hard failure
- **Edge case:** generate mode always uses commits since the most recent git tag (git_log_since_latest_tag), or full HEAD history if no tags exist

### P0-06 — Changelog write mode selection at bump time (auto/promote/generate)

**Category:** Policy · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/bump.py:152-268`

At release time, 'auto' mode promotes a non-empty [Unreleased] section to the new version heading, or generates a fresh section from git log if [Unreleased] is empty; 'promote' requires a non-empty [Unreleased] section and fails otherwise; 'generate' always builds from git history, ignoring [Unreleased].

- **Given** changelog_mode='promote' and the [Unreleased] section has no bullet entries
- **When** update_changelog runs during rrt bump
- **Then** The function prints a warning ('nothing to promote') and returns without modifying the changelog file
- **Parameters:** resolve_changelog_mode default: 'generate' if changelog_workflow=='squash' else 'auto' (src/repo_release_tools/commands/bump.py:152-156)
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### P0-07 — Changelog mode selection at bump time

**Category:** Policy · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/bump.py:152-269`

The changelog update mode defaults to 'generate' when the workflow is 'squash' and 'auto' otherwise (unless explicitly overridden). In 'auto' mode, an [Unreleased] section with entries is promoted to the new version heading; an empty or missing section instead triggers generation of a new section from git log since the latest tag. In 'promote' mode, an empty [Unreleased] section aborts the update with a warning rather than promoting nothing.

- **Given** changelog_workflow='incremental' (default) and the changelog's [Unreleased] section has zero bullet entries
- **When** `rrt bump patch` runs with the default changelog_mode='auto'
- **Then** do_promote resolves to False (has_entries=False), so a new changelog section is generated fresh from `git log <last-tag>..HEAD` instead of promoting the empty placeholder
- **Parameters:** resolve_changelog_mode: 'generate' if changelog_workflow=='squash' else 'auto' (bump.py:152-156)
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### P0-08 — Bump command version resolution and branch creation gate

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/bump.py:271-543`

`rrt bump` computes the next version, builds the release branch name from it, and refuses to proceed if that branch already exists unless --force is passed (which resets the branch); the working tree must also be clean before any non-dry-run mutation, and preflight failures abort before any files change.

- **Given** the release branch 'release/v1.4.0' already exists and --force is not passed
- **When** `rrt bump minor` computes new version 1.4.0
- **Then** the command prints "Branch 'release/v1.4.0' already exists. Delete it first or choose a different version." and exits 1 without touching any files
- **Parameters:** none
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### P0-09 — Drift lockfile tracked agent-surface glob patterns

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/drift_cmd.py:77-110`

Only files matching a fixed set of glob patterns are tracked by `rrt drift` for agent-surface integrity: Claude settings/hooks, Copilot instructions, GitHub skill docs, and GitHub agent definitions; each matched file's content is hashed and recorded once (deduplicated by relative path) in the lockfile.

- **Given** Repo has `.claude/settings.json`, `.claude/hooks/pre_commit.py`, and an unrelated `scripts/deploy.py`
- **When** `rrt drift generate` runs
- **Then** Only the two `.claude/*` files are hashed and written to drift.lock.toml; `scripts/deploy.py` is never tracked because it matches none of the DRIFT_SURFACE_PATTERNS
- **Parameters:** DRIFT_SURFACE_PATTERNS = {.claude/settings.json, .claude/hooks/*.py, .github/agents/*.agent.md, .github/copilot-instructions.md, .github/instructions/*.md, .github/skills/*/SKILL.md}

### P0-10 — rrt git move auto-stash/checkout/restore lifecycle

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/git_sync.py:162-209`

Switching branches with `rrt git move` on a dirty working tree stashes local changes first, then checks out the target (creating it with -b if --create was given), then restores the stash; if the checkout itself fails on a dirty tree, the auto-stash is deliberately left on the stash stack instead of being auto-restored, and the error propagates.

- **Given** working tree has uncommitted changes and the target branch checkout fails (e.g., conflicting paths)
- **When** `rrt git move <target>` runs
- **Then** the stash push already occurred, the checkout raises a RuntimeError, a message notes the auto-stash remains on the stash stack, and the exception propagates instead of returning a code
- **Parameters:** n/a
- **Edge case:** On a clean tree, no stash push/pop happens at all — checkout runs directly (git_sync.py:181-205).

### P0-11 — rebootstrap requires explicit destructive confirmation and blocks conflicting flags

**Category:** Policy · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/git_sync.py:235-266`

rrt git rebootstrap (which destroys and reinitializes git history) requires --yes-i-know-this-destroys-history; it refuses to combine --hard-init with --empty-first; and it refuses to run when the repository has configured remotes unless --allow-remote is passed.

- **Given** --yes-i-know-this-destroys-history is omitted
- **When** cmd_rebootstrap runs
- **Then** Command exits 1 with 'Refusing to destroy repository history without --yes-i-know-this-destroys-history.'
- **Edge case:** --hard-init and --empty-first together also exit 1
- **Edge case:** Existing remotes without --allow-remote also exit 1
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### P0-12 — rrt git rebootstrap refuses repositories with configured remotes unless --allow-remote

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/git_sync.py:258-266`

Beyond the destructive-confirmation flag, rebootstrap has a second independent safety gate: if the repository has any configured git remotes, the command refuses to proceed unless --allow-remote is also passed, to avoid accidentally destroying history that a remote depends on.

- **Given** a repo has an 'origin' remote configured and --yes-i-know-this-destroys-history is passed but --allow-remote is not
- **When** rrt git rebootstrap runs
- **Then** the command exits 1 with 'Refusing to rebootstrap a repository with configured remotes. Use --allow-remote if that is intentional.' and no git state is touched
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### P0-13 — rrt git rebootstrap: default commit message depends on --hard-init vs snapshot mode

**Category:** Policy · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/git_sync.py:268-274`

If no explicit --message is given, rebootstrap uses 'chore: bootstrap repository' for an empty hard-init and 'chore: initial commit' when snapshotting current files.

- **Given** rrt git rebootstrap --yes-i-know-this-destroys-history --hard-init (no --message)
- **When** the new history is created
- **Then** the commit message used is 'chore: bootstrap repository'

### P0-14 — publish-snapshot refuses same-remote-as-origin force-push

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/git_sync.py:424-434`

rrt git publish-snapshot refuses to run if the target remote resolves to the same URL as the configured primary remote (default 'origin'), preventing an accidental force-push/history-rewrite of the main remote.

- **Given** --remote points to a URL identical to the primary remote's URL
- **When** cmd_publish_snapshot checks git.primary_remote_conflict
- **Then** Command exits 1 with 'Refusing to publish: <conflict reason>' and no push occurs
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### P0-15 — publish-snapshot blocked during in-progress git operation

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/git_sync.py:436-444`

Snapshot publishing (and rrt git sync) refuse to run while another git operation (e.g. rebase, merge) is already in progress in the working tree.

- **Given** A rebase is in progress (git.in_progress_operation returns 'rebase')
- **When** cmd_publish_snapshot or cmd_sync runs
- **Then** Command exits 1 with 'Cannot ... while a rebase is in progress. Resolve or abort it first.'

### P0-16 — publish-snapshot requires explicit destructive confirmation flag

**Category:** Policy · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/git_sync.py:446-457,679-683`

Force-pushing a snapshot to a remote only actually executes when --yes-i-know-this-overwrites-remote-history is passed; otherwise the command runs in preview/dry-run mode regardless of --dry-run.

- **Given** --yes-i-know-this-overwrites-remote-history is omitted
- **When** cmd_publish_snapshot runs
- **Then** dry_run is forced to True; a warning is printed ('Refusing to push without ...') and only a preview is shown — no git push occurs
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### P0-17 — Publish-snapshot CLI requires an explicit destructive-confirmation flag or it silently downgrades to dry-run

**Category:** Policy · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/git_sync.py:446-503`

The `rrt git publish-snapshot` command, which force-pushes a single orphan commit overwriting a remote branch's history, only performs the destructive push when --yes-i-know-this-overwrites-remote-history is passed. Otherwise (even without --dry-run) it behaves as a dry-run preview.

- **Given** Given a user runs `rrt git publish-snapshot --remote backup --branch main` without the confirmation flag
- **When** When cmd_publish_snapshot evaluates `confirmed = bool(args.yes_i_know_this_overwrites_remote_history)`
- **Then** Then dry_run is forced True (`dry_run = args.dry_run or not confirmed`) and a warning is printed instead of pushing
- **Parameters:** n/a
- **Edge case:** Even in confirmed mode, cleanup (restoring the original branch, deleting the temp branch) always runs in a finally block and failures there are only warned, not fatal
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### P0-18 — rrt git sync preconditions and auto-stash lifecycle

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/git_sync.py:70-159;src/repo_release_tools/workflow/git.py:255-264`

Before syncing the current branch, the command requires a configured upstream branch, requires no in-progress rebase/merge operation, and requires no unresolved merge conflicts in the working tree; if the tree is dirty it auto-stashes before fetch+pull and auto-pops after a successful pull, defaulting to rebase strategy (--merge switches to a merge pull); if the pull fails on a dirty tree, the stash is deliberately left in place rather than auto-restored.

- **Given** the current branch has no upstream branch configured
- **When** `rrt git sync` runs
- **Then** the command exits 1 immediately with a message to set an upstream first, without fetching or stashing anything
- **Parameters:** default pull strategy: rebase (git pull --rebase); --merge switches to plain git pull
- **Edge case:** An in-progress rebase or merge (detected via .git/rebase-merge, .git/rebase-apply, or .git/MERGE_HEAD) blocks sync entirely (git_sync.py:97-105).
- **Edge case:** Unresolved merge conflicts in `git status` output block sync entirely, showing up to a capped number of conflicting files (git_sync.py:106-114).

### P0-19 — Hooks install: duplicate --target values are deduplicated by first occurrence

**Category:** Validation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/hooks_cmd.py:137-146,173-176`

If the same install target is passed more than once, it is only processed once, in the order it first appeared.

- **Given** --target claude-local --target codex-local --target claude-local
- **When** the install plan is resolved
- **Then** claude-local is installed once (at its first position) and codex-local once; no duplicate work or double-counted file totals occur

### P0-20 — Hook registration merge: grouped-hooks dedup by exact command string per matcher

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/hooks_cmd.py:387-433`

When merging newly generated hook entries into an existing grouped hook-manager config (e.g. Claude Code settings.json style), a hook group is matched by its 'matcher' value, and within a matching group, individual hook commands are only added if no existing hook in that group already has the identical 'command' string.

- **Given** an existing hook group for matcher 'pre-commit' already contains a hook with command 'rrt-hooks pre-commit'
- **When** the same managed hook is regenerated and merged again
- **Then** no duplicate entry is appended; the existing group is left with one 'rrt-hooks pre-commit' entry

### P0-21 — Hook registration merge deduplicates by matcher+command (Claude/Codex/Gemini style)

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/hooks_cmd.py:387-433`

When installing hooks into a Claude/Codex/Gemini-style settings.json/hooks.json, existing hook groups are matched by their 'matcher' string; new commands are appended into the matching group only if that exact command string is not already present, and unmatched groups are appended as new entries. No existing entries are removed or overwritten.

- **Given** settings.json already has a PreCommit group with matcher '*' and one hook command
- **When** `rrt hooks install --target claude-local` runs again with the same hook script
- **Then** the registration file is re-written but the duplicate command is not added a second time (idempotent merge); a genuinely new command for the same matcher is appended to the existing group's hooks array

### P0-22 — Hooks install: managed hook-registration JSON is merged additively, deduped by command signature

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/hooks_cmd.py:387-470`

When writing the surface-native hook registration file (settings.json, hooks.json, etc.), rrt merges new hook entries into existing groups rather than overwriting the file; an entry already present (matched by command, or by matcher+bash+command for Copilot) is not duplicated.

- **Given** an existing .claude/settings.json already registering rrt_user_commit_policy.py under PreToolUse with matcher 'Bash'
- **When** rrt hooks install --target claude-local runs again
- **Then** the existing PreToolUse/Bash group is reused and the duplicate command entry is skipped rather than appended a second time

### P0-23 — Hook registration merge: Copilot-style dedup by (matcher, bash, command) signature

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/hooks_cmd.py:436-470`

For the Copilot hook-manager surface, merging uses a different dedup key than the grouped-hooks surface: the 3-tuple of (matcher, bash, command) must be identical for an entry to be treated as a duplicate; the merged file's schema 'version' field is forced to 1.

- **Given** an existing Copilot hooks.json with one entry for event 'pre-commit' with matcher='*', bash='sh', command='rrt-hooks pre-commit'
- **When** a new entry with the same matcher/bash/command is merged
- **Then** it is skipped as a duplicate; a different bash interpreter for the same matcher/command would NOT be treated as a duplicate and would be appended
- **Edge case:** merged['version'] is always overwritten to 1, discarding any pre-existing version value in the file

### P0-24 — Hook registration merge deduplicates by (matcher, bash, command) tuple (Copilot style)

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/hooks_cmd.py:436-470`

For Copilot-style hook registration (a different JSON shape than Claude/Codex/Gemini), entries are deduplicated using the full (matcher, bash, command) signature rather than just the command string, and the registration file's 'version' field is forced to 1 on every write.

- **Given** hooks.json for copilot-local already contains one PreToolUse entry
- **When** `rrt hooks install --target copilot-local` is run again
- **Then** the merged file has 'version': 1 and no duplicate entry is added when the (matcher, bash, command) triple exactly matches an existing entry; entries with any differing field are appended

### P0-25 — Release check global pin-target deduplication

**Category:** Validation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/release_cmd.py:227-241`

When checking pin targets, group-level and global pin targets are combined and de-duplicated by the (path, pattern) pair before checking, so an identical pin target configured both globally and per-group is only checked and reported once.

- **Given** A global pin target on docs/conf.py with pattern 'version = .*' also duplicated in the group's own pin_targets list
- **When** `rrt release check` runs
- **Then** Only one status line is emitted for that (path, pattern) pair, not two
- **Parameters:** n/a

### P0-26 — gh-release format contributor discovery since last tag

**Category:** Calculation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/release_notes.py:85-117`

For the gh-release output format, contributors are the sorted, de-duplicated set of commit-author names from `git log` between the most recent tag (by version sort) and HEAD; if no tags exist, the full history up to HEAD is used. A '## Contributors' section is appended only if at least one contributor is found.

- **Given** Tags v1.0.0, v1.1.0 exist; 3 commits since v1.1.0 by 'Alice' and 'Bob' (Alice authored 2)
- **When** `rrt release notes --format gh-release` runs
- **Then** Contributors section lists 'Alice' and 'Bob' once each, alphabetically sorted, derived from commits in range v1.1.0..HEAD
- **Parameters:** n/a

### P0-27 — gh-release format appends a deduplicated Contributors list since the last tag

**Category:** Calculation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/release_notes.py:85-117`

When formatting release notes for GitHub, contributor names are the unique set of git commit author names since the most recent tag (or all history if no tags exist), sorted alphabetically, appended under a '## Contributors' heading.

- **Given** 3 commits since the last tag with authors Alice, Bob, Alice
- **When** rrt release notes --format gh-release runs
- **Then** the Contributors section lists exactly 'Alice' and 'Bob' (deduplicated, sorted)

### P0-28 — Release repair recreate-mode safety gates

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/release_repair.py:158-263`

Recreate mode (`rrt release repair --from BASE`) refuses to run if the working tree is dirty, if there is no [VERSION] changelog section to restore (unless --changelog-from is given), if the base ref doesn't exist, or if the current branch is ahead of its origin remote counterpart (unless --force-allow-pushed is set, since the rewrite requires a destructive force-push). A backup ref is created before the destructive git reset --hard unless --no-backup is passed.

- **Given** branch 'release/v2.0.0' has 3 commits not yet pushed to 'origin/release/v2.0.0'
- **When** `rrt release repair --from main --yes` runs without --force-allow-pushed
- **Then** the command refuses with 'Repair refused: release/v2.0.0 is ahead of origin/release/v2.0.0. Re-run with --force-allow-pushed...' and exits 1 before any git reset happens
- **Parameters:** none
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### P0-29 — Tag creation refuses to overwrite existing tag without --force

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/tag.py:132-166`

Creating an annotated tag for the current configured version fails if that tag name already exists, unless --force is passed, in which case the existing tag is deleted first and recreated.

- **Given** tag 'v1.4.0' already exists in the repository and --force is not passed
- **When** `rrt tag create` computes the expected tag name 'v1.4.0'
- **Then** the command prints "Tag 'v1.4.0' already exists. Use --force to overwrite." and exits 1 without running git tag
- **Parameters:** default tag prefix = 'v'
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### P0-30 — Tag create refuses overwrite and force-recreates via delete-then-create

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/tag.py:153-176`

Creating a tag that already exists fails unless --force is given; with --force the existing tag is deleted locally then an annotated tag is created fresh at the current commit (not simply moved).

- **Given** tag 'v1.2.3' already exists pointing at an old commit
- **When** `rrt tag create --force` runs at a new HEAD
- **Then** the old 'v1.2.3' tag is deleted (`git tag -d`) and a new annotated 'v1.2.3' tag is created at the current HEAD (`git tag -a`)
- **Parameters:** n/a
- **Edge case:** Without --force, an existing tag causes exit 1 with a guidance message (tag.py:154-161).

### P0-31 — Tag check: prefix mismatch always errors; missing expected tag only under --strict

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/tag.py:191-229`

`rrt tag check` treats any existing tag that doesn't start with the configured prefix as an unconditional error (regardless of --strict), while a missing expected tag for the current version is only an error under --strict — otherwise it is printed as a non-blocking notice and the command can still succeed.

- **Given** Existing tags include 'rel-1.0.0' (wrong prefix) while the configured prefix is 'v', and the expected tag 'v1.2.3' is absent, run without --strict
- **When** `rrt tag check --prefix v` runs
- **Then** The command fails (exit 1) solely due to the prefix-mismatch error on 'rel-1.0.0'; the missing 'v1.2.3' tag is only printed as an informational line, not counted as a failure in non-strict mode
- **Parameters:** default prefix 'v'

### P0-32 — Tag check flags tags that don't match the configured prefix

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/tag.py:212-214`

rrt tag check inspects every existing tag in the repository and flags any tag whose name does not start with the expected prefix (default 'v').

- **Given** repository tags include v1.0.0, v1.1.0, and legacy-1.0
- **When** rrt tag check runs with the default prefix 'v'
- **Then** 'legacy-1.0' is reported as an error: "Tag 'legacy-1.0' does not match prefix 'v'"

### P0-33 — Tag prefix mismatch is always an error regardless of --strict

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/tag.py:212-226`

During `rrt tag check`, any existing git tag that doesn't start with the expected prefix is always reported as an error and fails the command, even without --strict; --strict only additionally controls whether a missing expected-version tag is an error.

- **Given** existing tags include 'v1.2.3' (matches prefix 'v') and 'rel-2.0.0' (does not match prefix 'v'), and the expected tag 'v1.2.3' for the current version is present
- **When** `rrt tag check` runs without --strict
- **Then** the command still exits 1 because of the prefix mismatch on 'rel-2.0.0', even though the current version's expected tag is present and --strict is off
- **Parameters:** default prefix: 'v'

### P0-34 — Tag check: missing expected tag is a warning unless --strict

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/tag.py:216-226`

If the tag for the current configured version doesn't exist yet, rrt tag check reports it as a non-fatal informational line by default; with --strict it becomes a hard failure (exit 1), which is intended for CI gates.

- **Given** current version is 2.0.0 and no v2.0.0 tag exists yet
- **When** rrt tag check runs without --strict
- **Then** the command prints the missing-tag notice but still exits 0 (unless other errors like prefix mismatches exist); with --strict it exits 1

### P0-35 — Workspace bump changelog promotion precondition

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/workspace.py:97-123`

During a workspace-wide bump, a package's changelog is only promoted from [Unreleased] to the new version if the changelog file exists, has an [Unreleased] section, and that section has at least one bullet.

- **Given** a package's CHANGELOG.md exists but its [Unreleased] section is empty (no bullets)
- **When** rrt workspace bump patch --packages <pkg> runs (and --no-changelog is not set)
- **Then** the changelog file is left untouched even though the version target files are updated to the new version

### P0-36 — Workspace bump changelog promotion requires a non-empty [Unreleased] section

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/workspace.py:97-123`

During a workspace bump, a package's changelog is only promoted from [Unreleased] to the new version if the changelog file exists, has an [Unreleased] section, and that section has at least one entry; otherwise the changelog is left untouched.

- **Given** a package changelog with an empty [Unreleased] section (no bullets)
- **When** rrt workspace bump runs without --no-changelog
- **Then** the changelog file is not modified for that package

### P0-37 — publish_targets require non-empty remote and branch

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/config/model.py:355-370;src/repo_release_tools/config/core.py:1166-1187`

Each named publish-snapshot destination must declare a non-empty remote name, branch, and commit message; missing or empty values fail config loading.

- **Given** publish_targets.docs = {branch = "main"} with no remote
- **When** the config loads
- **Then** loading fails: "publish_targets.docs must have a non-empty 'remote'"

### P0-38 — Doc extraction dedup: first-registered entry name wins per file

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/docs/extractor.py:692-734`

Within a single source file, doc entries are extracted in a fixed priority order — SOURCE_OWNED_TOPIC_DOCS (Python only) first, then explicit '# sym:' markers, then implicit language-native docstrings/comments — and once a given entry name has been captured, later extraction passes for the same name in that file are silently skipped rather than overwriting it.

- **Given** a Python file has both an explicit '# sym: config' marker above a string assignment AND a function named config() with a docstring
- **When** extract_docs runs with extraction_mode='both'
- **Then** only the explicit-marker content for 'config' is kept; the implicit docstring for the same name is discarded because the name was already seen

### P0-39 — MCP publish-snapshot: dry_run=False alone is the destructive confirmation (no separate flag)

**Category:** Policy · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/mcp/tools/publish_tools.py:27-142`

On the MCP tool surface, rrt_publish_snapshot force-pushes to a secondary remote as soon as it is called with dry_run=False; unlike the CLI's `git publish-snapshot`, there is no separate `--yes-i-know-this-overwrites-remote-history`-equivalent flag — dry_run=False alone authorizes the destructive push.

- **Given** an MCP client calls rrt_publish_snapshot(remote='mirror', branch='main', dry_run=False)
- **When** the tool executes
- **Then** it force-pushes an orphan single-commit snapshot to mirror:main immediately, without any additional confirmation parameter
- ⚠️ **Suspected defect:** This is a materially weaker confirmation policy than the CLI's dedicated destructive-confirmation flag for the same operation (git_sync.py:446-457) — worth flagging for parity review since both surfaces perform the same force-push.
- ❓ **SME question:** Should the MCP surface require a distinct explicit confirmation argument (mirroring --yes-i-know-this-overwrites-remote-history) rather than treating dry_run=False as sufficient authorization for a force-push?

### P0-40 — MCP publish-snapshot collapses the CLI's explicit destructive-confirmation flag into dry_run alone

**Category:** Policy · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/mcp/tools/publish_tools.py:27-35`

The MCP surface for publish-snapshot treats dry_run=False as sufficient authorization to force-push, with no separate confirmation input — whereas the CLI (rrt git publish-snapshot) requires a distinct --yes-i-know-this-overwrites-remote-history flag in addition to not passing --dry-run before it will force-push.

- **Given** an MCP client calls rrt_publish_snapshot(remote='public', branch='main', dry_run=False)
- **When** the tool executes
- **Then** it proceeds directly to git checkout --orphan / git push --force without any second confirmation input, unlike commands/git_sync.py:446-457 which additionally requires --yes-i-know-this-overwrites-remote-history
- ⚠️ **Suspected defect:** This is a policy divergence between product surfaces: the CLI requires two independent signals (not-dry-run AND explicit confirmation flag) before a destructive force-push runs, but the MCP tool requires only one (dry_run=False). An MCP client could trigger an irreversible remote-history overwrite with a single boolean it might set carelessly, where the CLI would have required a second, harder-to-mistype flag.
- ❓ **SME question:** Is it intentional that the MCP publish-snapshot tool only requires dry_run=False (no second confirmation parameter) to force-push, while the CLI requires an explicit --yes-i-know-this-overwrites-remote-history flag in addition to not using --dry-run? Should the MCP tool add an equivalent explicit-confirmation parameter?

### P0-41 — MCP version-bump tool applies per-target without atomic rollback

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/mcp/tools/version_tools.py:82-92`

The MCP server's bump tool (used by AI agents/automation) writes each version target file one at a time in a loop, unlike the CLI's all-or-nothing atomic bump; if a later target in the same group fails, earlier targets in that group remain updated with no rollback.

- **Given** a version group with 3 targets, dry_run=False
- **When** rrt_bump is invoked via MCP and the 2nd target's replace_version_in_file call raises
- **Then** the 1st target's file is left permanently updated to the new version while the 2nd and 3rd are not, producing an inconsistent group state that the CLI's replace_all_versions_atomic would have prevented
- **Parameters:** n/a
- **Edge case:** dry_run=True (the tool default) never reaches the write loop, so the divergence only manifests when an agent explicitly passes dry_run=False
- ⚠️ **Suspected defect:** This is a behavioral divergence from the CLI bump command (commands/bump.py:134 uses replace_all_versions_atomic) that is not documented anywhere in the MCP tool docstring. Confirmed by comparing mcp/tools/version_tools.py:86-92 (per-target replace_version_in_file loop) against commands/bump.py:103,134 (group-level replace_all_versions_atomic call).
- ❓ **SME question:** Should the MCP rrt_bump tool be changed to call replace_all_versions_atomic (matching CLI behavior) instead of writing targets one at a time, to avoid leaving a version group partially bumped on failure?

### P0-42 — Preflight: working tree must be clean before mutating bump

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/preflight.py:17-22,46-68`

Before writing any version changes, the working tree must have no uncommitted changes, unless the operation is a dry run.

- **Given** an uncommitted, dirty working tree and dry_run=False
- **When** run_preflight(config, dry_run=False, group=group) is called
- **Then** PreflightError is raised: 'Working tree has uncommitted changes. Commit or stash them first, or use --dry-run.'
- **Edge case:** dry_run=True skips the clean-tree check entirely
- **Edge case:** version targets that don't exist or can't be parsed also fail preflight (targets.py check)
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory (The Given/When/Then is faithful to the code: check_working_tree_clean (preflight.py:17-22) calls git.working_tree_clean(root) (workflow/git.py:156-165, which runs `git status --porcelain` and checks for empty output) and raises PreflightError with the exact quoted message when the tree is dirty. run_preflight (preflight.py:46-68) only invokes this check whe…

### P0-43 — Pre-flight checks gate mutating commands (bump)

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/preflight.py:17-68`

Before rrt bump performs any file writes, it must confirm the working tree is clean (skipped only in dry-run), at least one version group is configured, and every configured version target file exists and is readable in its expected format.

- **Given** Working tree has uncommitted changes and --dry-run is not set
- **When** run_preflight is called
- **Then** PreflightError is raised: 'Working tree has uncommitted changes. Commit or stash them first, or use --dry-run.' and the bump aborts with exit code 1
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### P0-44 — Preflight gate order for mutating commands

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/preflight.py:46-68`

Before any mutating command (like `rrt bump`) writes files, it checks in order: (1) at least one version group is configured, (2) every version target file is readable/parseable, (3) the working tree is clean — but the working-tree-clean check is skipped entirely in --dry-run mode. The first failing check aborts the whole command via PreflightError.

- **Given** one version_targets file has been deleted from disk and --dry-run is not passed
- **When** `rrt bump patch` calls run_preflight
- **Then** check_version_targets_readable raises PreflightError('Version target pre-flight checks failed:\n...') before check_working_tree_clean ever runs, aborting before any writes
- **Parameters:** none
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### P0-45 — Version target replacement raises on no-op substitution

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/version/targets.py:69-94,96-136`

If a computed 'new version' is identical to the currently-read version for a target file, the write is treated as an error rather than silently skipped, both for single-target and atomic multi-target replacement.

- **Given** a pep621 target already at version 1.11.2
- **When** replace_version_in_file is called with new_version="1.11.2"
- **Then** a RuntimeError "... version replacement had no effect" is raised and no bytes are written
- **Edge case:** Atomic multi-target replace_all_versions_atomic performs this same-version check in Phase 1 (before any file is written), so a single stale target aborts the whole batch

### P0-46 — Atomic multi-file version write with rollback

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/version/targets.py:96-136`

When bumping the version across every configured file target, rrt first checks that every file can be safely rewritten in memory (each target's current version must differ from the new version); only after every target passes does it write any file. If a write fails partway through, every file already written is restored to its original content.

- **Given** Given three version targets, and the second one's write raises an OSError
- **When** When replace_all_versions_atomic runs in non-dry-run mode
- **Then** Then the exception propagates, and any target file already written in this call is rewritten back to its original content before the error surfaces
- **Parameters:** n/a
- **Edge case:** If current_version == new_version for any target, the whole operation raises RuntimeError before any file is touched
- **Edge case:** Rollback write failures are swallowed (OSError caught) rather than raised, to avoid masking the original error
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### P0-47 — Atomic version replacement rollback on partial write failure

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/version/targets.py:96-136`

When updating multiple version-bearing files in one bump, all substitutions are computed in memory first; if writing any file fails partway through, every already-written file is rolled back to its original content before the error propagates.

- **Given** 3 version targets where the 3rd file write raises OSError (e.g. permission denied)
- **When** replace_all_versions_atomic runs with dry_run=False
- **Then** targets 1 and 2, already written with the new version, are rewritten back to their original content, and the exception is re-raised
- **Edge case:** Rollback write failures are swallowed (OSError caught and ignored) rather than raised, so a rollback can itself silently fail leaving partial state
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### P0-48 — Atomic multi-target version write with rollback

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/version/targets.py:96-136`

When bumping the version across multiple configured files, all files are read and their new content computed in memory first; only if every target computes successfully are any files actually written, and if a write fails partway through, previously-written files in that same batch are restored to their original content.

- **Given** three version targets (pyproject.toml, package.json, VERSION file) configured in one version group
- **When** rrt bump writes a new version and the third file's write raises an OSError after the first two succeeded
- **Then** the first two files are rewritten back to their pre-bump content so the working tree ends in its original state, and the exception propagates
- **Parameters:** n/a — behavioral guarantee, no magic numbers
- **Edge case:** If the rollback write itself fails (OSError), the exception is swallowed silently (targets.py:132-135) leaving that file in the new (unrolled-back) state — a partial-rollback risk
- **Edge case:** Any target whose current version already equals the new version raises 'version replacement had no effect' before any file is written (targets.py:118-120)
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### P0-49 — Version target atomic multi-file write with rollback

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/version/targets.py:96-141`

When updating version strings across multiple configured files, all substitutions are computed in memory first; if any target would produce no textual change (current==new) the whole operation aborts before any file is written; if a write fails partway through, already-written files are rolled back to their original content.

- **Given** Two version targets, one of which already contains the new version string
- **When** replace_all_versions_atomic is called
- **Then** RuntimeError('... version replacement had no effect') is raised and no files on disk are modified
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### P0-50 — In-progress merge/rebase detection

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/workflow/git.py:255-264`

The repository is considered to have an in-progress git operation if the .git directory contains rebase-merge/rebase-apply (rebase) or MERGE_HEAD (merge); this state gates several destructive commands elsewhere (e.g. publish-snapshot, already catalogued) from proceeding.

- **Given** a repository mid-rebase with .git/rebase-merge present
- **When** any caller checks in_progress_operation(cwd)
- **Then** the function returns the string 'rebase' (or 'merge' if MERGE_HEAD exists instead), else None when neither marker is present

### P0-51 — Publish-snapshot refuses to push to a remote that resolves to the same URL as the primary remote

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/workflow/git.py:306-342;src/repo_release_tools/commands/git_sync.py:429-434`

Before force-pushing a snapshot, rrt compares the target remote's URL against the repository's configured primary remote (default 'origin') after normalizing both (stripping scheme, trailing .git, case-folding host, collapsing path traversal, handling SCP-style git@host:path syntax). If they resolve to the same repository, the push is refused to prevent accidentally overwriting the main history.

- **Given** Given primary remote 'origin' points to git@github.com:acme/repo.git and the user targets --remote 'https://github.com/acme/repo' as the snapshot destination
- **When** When primary_remote_conflict compares normalized URLs
- **Then** Then both normalize to 'github.com/acme/repo' and the command exits 1 with 'Refusing to publish: --remote ... resolves to the same URL as origin'
- **Parameters:** primary_remote defaults to 'origin' (src/repo_release_tools/config/core.py:103-119)
- **Edge case:** normalize_remote_url is used only for this equality guard, never for the actual push command, which always uses the raw configured/flag value
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### P0-52 — Squash-merge changelog bullet dedup/cancellation

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/workflow/hooks.py:281-374,377-455`

After a squash merge, duplicate changelog bullets (same text, case-insensitive) are collapsed to one, and pairs of bullets whose descriptions are opposite actions on the same subject (e.g. 'add Node 26' and 'remove Node 26') are both deleted entirely, only within matching scope prefixes.

- **Given** added bullets ['- add Node 26 support', '- CI: remove Node 26 support']
- **When** dedup_changelog_entries(added_lines) runs
- **Then** neither bullet is removed, because their scope prefixes differ (None vs 'ci') even though the verbs are opposite and subjects match
- **Parameters:** _OPPOSITE_VERB_PAIRS: add/remove, adds/removes, enable/disable, enables/disables, include/exclude, includes/excludes, upgrade/downgrade, upgrades/downgrades, revert/apply, reverts/applies (hooks.py:281-292)
- **Edge case:** exact case-insensitive duplicates are always collapsed regardless of scope
- **Edge case:** consecutive blank lines left by removal are collapsed to one blank line

### P0-53 — Unreleased bullet dedup on squash merge cancels opposite-verb pairs

**Category:** Policy · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/workflow/hooks.py:281-374,377-455`

When post-correcting a squashed changelog, exact duplicate bullets (case-insensitive) are collapsed to one, and pairs of bullets whose descriptions are opposite-verb reversals of the same subject (e.g. 'add Node 26' and 'remove Node 26') are both deleted entirely — but only if they share the same scope prefix.

- **Given** added lines ['- add Node 26 to test matrix', '- remove Node 26 to test matrix'], neither with a scope prefix
- **When** dedup_changelog_entries runs during rrt-hooks post-correct
- **Then** both bullets are removed from the changelog entirely because they are recognized as an opposite-verb cancelling pair
- **Parameters:** _OPPOSITE_VERB_PAIRS: add/remove, adds/removes, enable/disable, enables/disables, include/exclude, includes/excludes, upgrade/downgrade, upgrades/downgrades, revert/apply, reverts/applies (hooks.py:281-292)
- ⚠️ **Suspected defect:** Cancelling logic is purely lexical (verb+suffix match) and does not consider commit authorship, timing, or intent — two genuinely independent commits that happen to phrase opposite verbs on the same subject would be silently dropped from the changelog.
- ❓ **SME question:** Is it acceptable for the post-correct hook to silently delete both changelog bullets whenever two entries have opposite verbs and identical remaining text, without any human review step, given this can permanently drop legitimate release notes?

### P0-54 — Post-squash changelog dedup: exact-duplicate and semantic-opposite bullet cancellation

**Category:** Calculation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/workflow/hooks.py:281-374,377-455`

After a squash merge, rrt cleans up the changelog entries the squash commit introduced: exact duplicate bullets (case-insensitive) collapse to the first occurrence, and pairs of bullets that are semantic opposites of each other (e.g. 'add Node 26' and 'remove Node 26', or 'CI: enable X' and 'CI: disable X') are both removed entirely, since together they represent a no-op. Bullets with different scope prefixes (e.g. 'CI:' vs 'Deps:') never cancel each other even if the verb+subject text matches.

- **Given** Given the squash commit added the bullets ['- add Node 26 support', '- CI: enable caching', '- remove Node 26 support', '- add Node 26 support']
- **When** When dedup_changelog_entries processes these four lines
- **Then** Then the exact duplicate 'add Node 26 support' collapses to one occurrence, and that occurrence cancels against 'remove Node 26 support' (opposite verb pair 'add '/'remove '), leaving only '- CI: enable caching'
- **Parameters:** _OPPOSITE_VERB_PAIRS = [(add,remove),(adds,removes),(enable,disable),(enables,disables),(include,exclude),(includes,excludes),(upgrade,downgrade),(upgrades,downgrades),(revert,apply),(reverts,applies)]
- **Edge case:** Removal is restricted to the exact line positions the squash commit introduced (via diff hunk header parsing), so identical lines in older, already-released changelog sections are never touched
- **Edge case:** Consecutive blank lines left behind by removals are collapsed to a single blank line

### P0-55 — Squash post-correction: dedupe and cancel opposite changelog bullets

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/workflow/hooks.py:281-455`

After a squash merge, exact-duplicate changelog bullets are collapsed to one, and pairs of bullets with the same scope whose verbs are opposites (e.g. 'add X' / 'remove X', 'enable X' / 'disable X') are both removed, since they cancel out.

- **Given** Added lines '- add Node 26' and '- remove Node 26' with no scope prefix
- **When** dedup_changelog_entries runs
- **Then** Both bullets are removed from the changelog (net-zero effective change)
- **Parameters:** Opposite verb pairs: add/remove, adds/removes, enable/disable, enables/disables, include/exclude, includes/excludes, upgrade/downgrade, upgrades/downgrades, revert/apply, reverts/applies (src/repo_release_tools/workflow/hooks.py:281-292)
- **Edge case:** Entries with different scope prefixes (e.g. 'CI: ...' vs 'Deps: ...') never cancel even if verb+subject match

### P0-56 — Squash-merge changelog dedup: exact duplicates and semantic-opposite cancellation

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/workflow/hooks.py:281-455`

After a squash merge, the post-correction step cleans up the changelog's newly-added bullet lines by removing exact case-insensitive duplicates (keeping the first) and by removing pairs of bullets that are semantic opposites of each other (e.g. 'add Node 26' followed later by 'remove Node 26'), so contradictory intermediate-commit noise doesn't survive into the release changelog.

- **Given** added lines ['- add Node 26 support', '- fix typo', '- remove Node 26 support']
- **When** dedup_changelog_entries() runs
- **Then** both the 'add Node 26 support' and 'remove Node 26 support' bullets are removed as a cancelling pair, leaving only '- fix typo'
- **Parameters:** opposite verb pairs: add/remove, adds/removes, enable/disable, enables/disables, include/exclude, includes/excludes, upgrade/downgrade, upgrades/downgrades, revert/apply, reverts/applies (hooks.py:281-292)
- **Edge case:** Entries with different scope prefixes (e.g. 'CI: add X' vs 'Deps: remove X') are never treated as a cancelling pair even if the verb+subject text matches (hooks.py:355-361)
- **Edge case:** Cancellation lookup is O(n) via a (scope, verb, suffix) dict keyed on the first-seen bullet of a pair, not O(n²) pairwise comparison (hooks.py:412-436)
- **Edge case:** Consecutive blank lines produced by removal are collapsed to one (hooks.py:445-455)

### P0-57 — Post-correction changelog rewrite restricted to the squash commit's own diff hunk positions

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/workflow/hooks.py:308-346,458-509`

When rewriting the changelog after dedup, only lines that were actually added at their current line positions by the specific squash commit being corrected are eligible for removal, so identical bullet text sitting in older, already-released changelog sections is never accidentally deleted.

- **Given** the squash commit added a bullet '- add caching' at line 8, but an older release section elsewhere in the file also happens to contain the literal text '- add caching' at line 240
- **When** apply_dedup_to_changelog() removes a duplicate '- add caching' bullet
- **Then** only the line at position 8 (within the recorded added_line_positions) is eligible for removal; the identical text at line 240 is left untouched because it falls outside the hunk's added-line positions
- **Parameters:** n/a
- **Edge case:** If added_line_positions is None, the removal budget applies to the whole file instead of being position-restricted (hooks.py:489)

### P0-58 — Working-tree dirty-check hook classification

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/workflow/hooks.py:578-602`

The dirty-tree pre-commit/CI gate fails distinctly for 'not a git repository' versus 'git repository with uncommitted changes', surfacing the specific changed entries in the failure message for the latter case.

- **Given** a working directory with 2 modified tracked files and no untracked files
- **When** run_dirty_tree_check() runs
- **Then** exit code 1 with message 'Working tree has uncommitted changes.' listing the 2 changed entries from git status --porcelain output
- **Parameters:** n/a
- **Edge case:** If cwd is not inside a git work tree at all, the check fails with a different message ('... is not inside a Git work tree') before even checking dirtiness (hooks.py:582-586)

## Suspected defects (verified citations, behavior questioned)

These are places where the *implemented* behavior is confirmed but the referee flagged it as probably not the *intended* behavior — issue-#140-class candidates. Each needs an SME ruling: fix (new behavior) or pin (characterize as-is):

1. **Version ordering / stable-after-prerelease sort** — `src/repo_release_tools/version/semver.py:104-110`
   Pre-release label comparison at semver.py:110 is a plain string comparison, so 'alpha.10' sorts before 'alpha.9' lexically, which is not standard semver precedence.

2. **Unreleased bullet dedup on squash merge cancels opposite-verb pairs** *(also in Behavior Contract)* — `src/repo_release_tools/workflow/hooks.py:281-374,377-455`
   Cancelling logic is purely lexical (verb+suffix match) and does not consider commit authorship, timing, or intent — two genuinely independent commits that happen to phrase opposite verbs on the same subject would be silently dropped from the changelog.

3. **rrt init idempotency and precedence guard across manifest formats** — `src/repo_release_tools/commands/init.py:110-152,182-320`
   The pyproject/Cargo manifest-append path (`_init_manifest`) has no --force override for an already-present rrt section, unlike the .rrt.toml and package.json paths which both honor --force for the equivalent 'already exists' case — this asymmetry may be intentional (avoiding a duplicate TOML table) or may be a gap.

4. **MCP publish-snapshot: dry_run=False alone is the destructive confirmation (no separate flag)** *(also in Behavior Contract)* — `src/repo_release_tools/mcp/tools/publish_tools.py:27-142`
   This is a materially weaker confirmation policy than the CLI's dedicated destructive-confirmation flag for the same operation (git_sync.py:446-457) — worth flagging for parity review since both surfaces perform the same force-push.

5. **All upstream provider fetchers fail silently to an empty version list** — `src/repo_release_tools/sync/providers.py:27-122;src/repo_release_tools/sync/pypi.py:12-25`
   Silently collapsing 'fetch failed' and 'no newer versions exist' into the same outcome could mask real network/API problems as false negatives during automated sync runs.

6. **MCP publish-snapshot collapses the CLI's explicit destructive-confirmation flag into dry_run alone** *(also in Behavior Contract)* — `src/repo_release_tools/mcp/tools/publish_tools.py:27-35`
   This is a policy divergence between product surfaces: the CLI requires two independent signals (not-dry-run AND explicit confirmation flag) before a destructive force-push runs, but the MCP tool requires only one (dry_run=False). An MCP client could trigger an irreversible remote-history overwrite with a single boolean it might set carelessly, where the CLI would have required a second, harder-to-mistype flag.

7. **CalVer scheme inference heuristic from parsed component widths** — `src/repo_release_tools/version/calver.py:52-74`
   The heuristic `day < 10` at calver.py:68 treats any single-digit day as 'padded' even when the source string had no leading zero, potentially misclassifying YYYY.M.D versions as YYYY.MM.DD.

8. **GitHub Action changelog status three-way classification** — `action.yml:82-90,121-140`
   The grep pattern is anchored ^\[Unreleased\] with no '##' prefix, but the repository's own CHANGELOG.md (and the standard Keep-a-Changelog format this tool otherwise enforces) uses '## [Unreleased]'. Verified: `grep -n '^\[Unreleased\]' CHANGELOG.md` returns no match against the real file, so for any standard-format changelog this step always falls through to changelog_status='clean' regardless of actual [Unreleased…

9. **MCP version-bump tool applies per-target without atomic rollback** *(also in Behavior Contract)* — `src/repo_release_tools/mcp/tools/version_tools.py:82-92`
   This is a behavioral divergence from the CLI bump command (commands/bump.py:134 uses replace_all_versions_atomic) that is not documented anywhere in the MCP tool docstring. Confirmed by comparing mcp/tools/version_tools.py:86-92 (per-target replace_version_in_file loop) against commands/bump.py:103,134 (group-level replace_all_versions_atomic call).


## Calculation rules (42)

### CAL-001 — Conventional commit type to changelog section mapping

**Category:** Calculation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/changelog.py:31-43`

Each conventional-commit type is mapped to a fixed changelog section: feat->Added, fix->Fixed, refactor/perf/style->Changed, docs->Documentation, and chore/ci/build/test/deps all collapse into Maintenance.

- **Given** a commit subject 'perf(cli): speed up bump'
- **When** build_changelog_section or append_to_unreleased parses it
- **Then** the bullet is filed under the '### Changed' subsection
- **Parameters:** SECTION_MAP dict (changelog.py:31-43)
- **Edge case:** a commit type not present in SECTION_MAP (none currently, since base_types are all mapped) is silently dropped from the changelog
- **Edge case:** breaking changes (subject has '!' after type/scope) always go to 'Breaking Changes' regardless of type
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory (Read src/repo_release_tools/changelog.py:31-43 directly; the SECTION_MAP dict is exactly as described (feat->Added, fix->Fixed, refactor/perf/style->Changed, docs->Documentation, chore/ci/build/test/deps->Maintenance), so the rule card is faithful to the code. No injection-shaped text found in these lines. However this is not a valid P0 under the compliance…

### CAL-002 — Latest released version is the topmost non-Unreleased section label

**Category:** Calculation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/changelog.py:334-406`

The 'latest released version' used by --latest-released in release notes is simply the first versioned section label encountered in document order (excluding [Unreleased]), not a semantic-version comparison across all sections.

- **Given** a changelog with sections in order: [Unreleased], [2.0.0], [1.9.0], [1.8.5]
- **When** rrt release notes --latest-released runs
- **Then** it emits the body of the [2.0.0] section because it is the first non-Unreleased heading, regardless of whether the sections are numerically sorted
- ❓ **SME question:** Is it guaranteed changelog sections are always maintained in strict descending version order (so 'topmost' == 'highest'), or could a manually-edited changelog have out-of-order sections and cause --latest-released to pick the wrong one?

### CAL-003 — Branch slug truncation on generation

**Category:** Calculation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/branch.py:128-133`

When rrt generates a new branch name from a type/scope/description, the slug is lower-cased, non-alphanumeric runs collapsed to single hyphens, then hard-truncated to 60 characters with any trailing hyphen trimmed.

- **Given** description exceeding 60 characters after slugification, e.g. 65 hyphen-joined characters
- **When** BranchName(...).slug() is called
- **Then** the slug is cut at exactly the 60th character, then any trailing '-' introduced by the cut is stripped
- **Parameters:** SLUG_MAX = 60
- **Edge case:** truncation can produce a slug shorter than 60 if the 60th character happened to be a hyphen

### CAL-004 — Version bump kind dispatch including CalVer fallback

**Category:** Calculation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/bump.py:315-339`

The bump argument is interpreted in this order: a recognized bump kind (major/minor/patch/pre-release/calver/pre-release-channel) triggers a structured bump of the current version; otherwise the argument is parsed first as an explicit semver string, and if that fails, as a CalVer string; if both parses fail the command errors out. When bump='calver' and the current version is not itself a valid CalVer string, it is treated as a fresh start using today's date under the requested scheme rather than erroring.

- **Given** current version is '2.3.1' (a semver, not CalVer) and the user runs `rrt bump calver --calver-scheme YYYY.MM.DD`
- **When** CalVersion.parse('2.3.1') raises ValueError
- **Then** the tool falls back to CalVersion.today('YYYY.MM.DD') as the new version, discarding the semver history rather than erroring
- **Parameters:** CALVER_SCHEMES; default scheme 'YYYY.MM.DD' (bump.py:317-318)
- ❓ **SME question:** Is silently discarding the prior semver history and resetting to today's CalVer date the intended behavior for a project's first calver bump, or should this require an explicit confirmation/flag?

### CAL-005 — rrt bump calver: non-calver current version triggers a fresh start instead of an error

**Category:** Calculation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/bump.py:317-327`

If a project is bumped with 'calver' but its currently recorded version isn't a valid calendar version (e.g. it's still semver), rrt treats this as a first-time conversion and starts today's calver version fresh rather than failing.

- **Given** Given the current recorded version is '1.11.2' (semver) and the user runs `rrt bump calver`
- **When** When CalVersion.parse('1.11.2') raises ValueError
- **Then** Then the new version becomes CalVersion.today(scheme) (e.g. 2026.07.10), not an error
- **Parameters:** default calver_scheme = YYYY.MM.DD
- **Edge case:** Only the 'calver' bump kind has this fallback; explicit CalVersion.parse(args.bump) elsewhere still raises on invalid input

### CAL-006 — Changelog compare classifies bullets as only-from / common / only-to per subsection

**Category:** Calculation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/changelog_compare.py:105-141`

For each subsection heading (e.g. Added, Fixed) present in either release, bullets are classified via set difference/intersection: present only in the 'from' version, present in both, or present only in the 'to' version. Bullets outside any subsection heading are grouped under 'General'.

- **Given** v1.0.0 'Fixed' section has bullets {A, B} and v2.0.0 'Fixed' section has bullets {B, C}
- **When** rrt changelog compare v1.0.0 v2.0.0 runs
- **Then** the Fixed diff reports only_from=[A], common=[B], only_to=[C]

### CAL-007 — Changelog compare set-based diff classification

**Category:** Calculation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/changelog_compare.py:126-141`

For each subsection (Added, Fixed, etc.) shared between two releases, entries are classified as only-in-from (set difference), common (set intersection), or only-in-to (set difference), based on exact string match after bullet extraction — not fuzzy or line-order matching.

- **Given** Release A's 'Added' section has bullets {'Support dark mode', 'Add CLI flag'} and Release B's 'Added' section has {'Add CLI flag', 'Add JSON export'}
- **When** `rrt changelog compare A B` runs
- **Then** only_from=['Support dark mode'], common=['Add CLI flag'], only_to=['Add JSON export']
- **Parameters:** n/a

### CAL-008 — CI version to_semver conversion formula

**Category:** Calculation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/ci_version.py:117-124`

Converting a PEP 440 dev-release string to Cargo-compatible SemVer replaces the trailing '.devNNN' with '-dev.NNN'; release versions without a .dev suffix pass through unchanged.

- **Given** version="0.2.0.dev12345601"
- **When** to_semver() is called (e.g. by ci-version apply for a semver_pre target)
- **Then** the result is "0.2.0-dev.12345601"

### CAL-009 — CI version: tag builds use the tag name (v-prefix stripped) verbatim

**Category:** Calculation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/ci_version.py:127-140`

When the CI build is triggered by a tag matching refs/tags/v*, the published version is the tag name with its leading 'v' removed, preferring the explicit ref-name over parsing the ref path; if the resulting string is empty it falls back to the configured base version.

- **Given** GITHUB_REF=refs/tags/v1.2.3, GITHUB_REF_NAME=v1.2.3, base version 1.0.0-dev
- **When** rrt ci-version compute runs on that tag build
- **Then** the published version is "1.2.3" (not the base)
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### CAL-010 — CI version: all other refs pass the base version through unchanged

**Category:** Calculation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/ci_version.py:127-152`

For any ref that is neither a v-prefixed tag nor refs/heads/main (e.g. a feature branch or PR build), the computed CI version is exactly the base version with no suffix applied.

- **Given** GITHUB_REF=refs/heads/feat/new-thing, base version 1.0.0
- **When** rrt ci-version compute runs
- **Then** the output is exactly "1.0.0"

### CAL-011 — CI version: main-branch builds produce a PEP 440 dev release with run id and zero-padded attempt

**Category:** Calculation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/ci_version.py:142-150`

On refs/heads/main builds, the published version is the base version suffixed with '.dev{GITHUB_RUN_ID}{GITHUB_RUN_ATTEMPT zero-padded to 2 digits}', so it's deterministic and monotonically distinguishable per CI run/attempt.

- **Given** base=0.2.0, GITHUB_RUN_ID=12345, GITHUB_RUN_ATTEMPT=1
- **When** rrt ci-version compute runs on a refs/heads/main build
- **Then** the published version is "0.2.0.dev1234501" (attempt zero-padded to 2 digits)
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### CAL-012 — gh-release format contributor discovery since last tag

**Category:** Calculation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/release_notes.py:85-117`

For the gh-release output format, contributors are the sorted, de-duplicated set of commit-author names from `git log` between the most recent tag (by version sort) and HEAD; if no tags exist, the full history up to HEAD is used. A '## Contributors' section is appended only if at least one contributor is found.

- **Given** Tags v1.0.0, v1.1.0 exist; 3 commits since v1.1.0 by 'Alice' and 'Bob' (Alice authored 2)
- **When** `rrt release notes --format gh-release` runs
- **Then** Contributors section lists 'Alice' and 'Bob' once each, alphabetically sorted, derived from commits in range v1.1.0..HEAD
- **Parameters:** n/a

### CAL-013 — gh-release format appends a deduplicated Contributors list since the last tag

**Category:** Calculation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/release_notes.py:85-117`

When formatting release notes for GitHub, contributor names are the unique set of git commit author names since the most recent tag (or all history if no tags exist), sorted alphabetically, appended under a '## Contributors' heading.

- **Given** 3 commits since the last tag with authors Alice, Bob, Alice
- **When** rrt release notes --format gh-release runs
- **Then** the Contributors section lists exactly 'Alice' and 'Bob' (deduplicated, sorted)

### CAL-014 — Workspace bump version resolution supports semver keywords, explicit versions, or CalVer

**Category:** Calculation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/workspace.py:72-94`

The bump argument to 'rrt workspace bump' can be a semver bump keyword, the literal 'calver' (bumps CalVer or falls back to today's date on parse failure), an explicit semver string, or an explicit CalVer string; anything else is rejected.

- **Given** rrt workspace bump calver --packages api where api's current version is not a valid CalVer string
- **When** the bump kind resolves
- **Then** the new version falls back to CalVersion.today() rather than failing the command

### CAL-015 — Workspace bump: unified new-version computation supports major/minor/patch/pre-release/calver/explicit version/channel names

**Category:** Calculation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/workspace.py:72-94`

Each package in a workspace bump gets its version recomputed the same way rrt bump computes a single version, falling back to CalVer.today() if parsing the current version as CalVer fails, or to explicit version parsing (semver first, then calver) if the bump word isn't a known keyword.

- **Given** a package with bump kind 'calver' whose current version string is not valid CalVer
- **When** _compute_new_version('calver', current) runs
- **Then** the function silently falls back to CalVersion.today() rather than raising an error

### CAL-016 — PEP 621 author rendering falls back name-only or email-only

**Category:** Calculation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/config/project_meta.py:191-213`

Each PEP 621 author entry is rendered as 'Name <email>' when both fields are present, 'Name' when only a name is present, or the bare email when only an email is present; entries with neither are dropped.

- **Given** project.authors = [{"name": "Jane Doe"}, {"email": "a@b.com"}, {"name": "J", "email": "j@x.com"}]
- **When** load_project_metadata parses pyproject.toml
- **Then** authors renders as ["Jane Doe", "a@b.com", "J <j@x.com>"]

### CAL-017 — Host/project minimum-version extraction per ecosystem

**Category:** Calculation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/eol/detect.py:20-146`

The installed host language version is read differently per ecosystem (Python via sys.version_info; Node/Go/Rust via shelling out to `--version` and regex-extracting the numeric version), and the project's declared minimum version is read from the ecosystem's manifest field (Python: pyproject.toml requires-python; Go: go.mod 'go' directive; Node: package.json engines.node; Rust: Cargo.toml rust-version), each parsed with a `\d+\.\d+(\.\d+)?` regex.

- **Given** A pyproject.toml with `requires-python = ">=3.11,<4"`
- **When** `detect_project_minimum('python', root)` runs
- **Then** Returns '3.11' (first regex match for \d+\.\d+(\.\d+)?), ignoring the upper bound and comparison operators
- **Parameters:** version regex \d+\.\d+(?:\.\d+)?; per-language commands: node --version, go version, rustc --version; timeout 10s
- **Edge case:** Any subprocess timeout or non-zero exit returns None silently
- **Edge case:** Unrecognized languages return None

### CAL-018 — SHA-256 content hashing for drift/artifact locks

**Category:** Calculation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/state.py:50-52,344-374`

All lockfile drift detection (docs, artifacts) is based on SHA-256 digests of file/content bytes, prefixed with 'sha256:'; for combined multi-file input hashes, each file's relative path and content are hashed together with null-byte separators to avoid path/content boundary collisions.

- **Given** two files ['a','b'] with contents 'X','' vs one file ['ab'] with content 'X' (concatenation collision scenario)
- **When** _compute_inputs_hash computes the combined hash
- **Then** the two scenarios produce different hashes because each file's relative path is hashed as a boundary marker before its content (state.py:367-373), preventing the 'ab'/'a'+'b' collision
- **Parameters:** hash algorithm: SHA-256, prefix 'sha256:'
- **Edge case:** no matching files for any glob returns None, and callers omit the key entirely rather than storing an empty hash

### CAL-019 — crates.io version fetch extracts the 'num' field per release object

**Category:** Calculation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/sync/providers.py:68-83`

For the crates.io provider, the list of available versions is built by reading the 'num' field out of each object in the API's 'versions' array; malformed entries are silently dropped rather than raising.

- **Given** crates.io returns versions: [{"num": "1.2.0"}, {"bad": true}, {"num": "1.3.0"}]
- **When** _fetch_crates_versions parses the response
- **Then** the result is ['1.2.0', '1.3.0']; the malformed entry with no 'num' key is skipped, not treated as an error

### CAL-020 — Unknown template_key falls back to the registry's 'default' template, or its first defined template

**Category:** Calculation · **Priority:** P2 · **Confidence:** Medium
**Source:** `src/repo_release_tools/tools/platform.py:251-264`

When formatting a registry URL with a template_key not defined for that registry, the code falls back to the 'default' template if one exists, otherwise to the first template defined for that registry (e.g. Maven, which has no 'default', falls back to its only 'versioned' template).

- **Given** format_registry_url('maven', template_key='default', groupId='g', artifactId='a', version='1.0')
- **When** 'default' is not among maven's declared templates ({'versioned': ...})
- **Then** the 'versioned' template is used instead of raising
- ❓ **SME question:** Is silently falling back to a different template (rather than erroring) intended when the caller explicitly requested 'default' and it doesn't exist for that registry?

### CAL-021 — Git hosting platform detection: exact/suffix host match, then self-hosted subdomain/path heuristics, else generic

**Category:** Calculation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/tools/platform.py:639-679`

To decide which git hosting platform a repository URL belongs to (for badges and source links), rrt first checks the hostname against a fixed list of known hosts (github.com, gitlab.com, bitbucket.org, dev.azure.com, visualstudio.com, codeberg.org, gitea.io) — matching either exactly or as a subdomain. If no match, it falls back to heuristics: a hostname starting with 'gitlab.' or a URL path containing '/gitlab/' is classified as GitLab; the same pattern for 'gitea.' / '/gitea/' classifies as Gitea. Anything else is 'generic'.

- **Given** Given repo_url = 'https://git.mycompany.com/gitlab/team/project'
- **When** When detect_platform(repo_url) is called
- **Then** Then the result is 'gitlab' via the path-segment heuristic, even though the host isn't gitlab.com
- **Parameters:** _PLATFORM_HOST_PATTERNS = {github.com->github, gitlab.com->gitlab, bitbucket.org->bitbucket, dev.azure.com->azure, visualstudio.com->azure, codeberg.org->codeberg, gitea.io->gitea}
- **Edge case:** Empty repo_url returns 'generic' immediately
- **Edge case:** A URL that fails to parse (ValueError) also returns 'generic'

### CAL-022 — GitHub-flavored heading anchor slug algorithm

**Category:** Calculation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/tools/toc.py:68-86`

A TOC anchor for a Markdown heading is generated by lowercasing the title, replacing spaces with hyphens, stripping any character that isn't a lowercase letter/digit/hyphen, and appending -1, -2, etc. for repeated anchors within the same document.

- **Given** Headings 'My Module!' followed by another 'My Module!' later in the same document
- **When** `render_toc` builds the table of contents
- **Then** First anchor is `my-module`, second occurrence becomes `my-module-1`
- **Parameters:** n/a

### CAL-023 — TOC rendering level filter and indentation

**Category:** Calculation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/tools/toc.py:89-122`

Only headings within [min_level, max_level] are rendered; the first included heading defines the base indent level (indent 0), and each deeper heading is indented by 2 spaces per level below the base.

- **Given** Headings [(2,'Intro'), (3,'Details'), (2,'Usage')] with min_level=2, max_level=6
- **When** `render_toc` runs
- **Then** 'Intro' and 'Usage' render at indent 0, 'Details' renders at indent 2 (1 level deeper than base level 2)
- **Parameters:** min_level default 1, max_level default 6, indent unit 2 spaces per level

### CAL-024 — CalVer scheme inference heuristic on parse

**Category:** Calculation · **Priority:** P2 · **Confidence:** Medium
**Source:** `src/repo_release_tools/version/calver.py:52-74`

When reading a calendar version string back, the padding scheme (padded vs unpadded month/day) is guessed from the literal digit widths in the string rather than being stored explicitly.

- **Given** string '2026.5.15'
- **When** CalVersion.parse('2026.5.15') is called
- **Then** scheme is inferred as YYYY.M.D since month has 1 digit
- **Edge case:** ambiguous case '2026.05.5' (month padded, day 1-digit <10) is heuristically classified as YYYY.MM.DD per the comment at calver.py:68-70 — could misclassify some inputs
- ❓ **SME question:** Is the day<10 heuristic at calver.py:68 (treating unpadded single-digit days as still YYYY.MM.DD when month is zero-padded) intentional, or should any unpadded day always classify as YYYY.M.D?

### CAL-025 — CalVer scheme selection and today's-date bump

**Category:** Calculation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/version/calver.py:76-98`

Bumping a calendar version always resets to today's UTC date; if a version for today's date was already used, a hidden micro counter increments instead of leaving the version unchanged.

- **Given** current CalVersion 2026.07.10 (scheme YYYY.MM.DD), invoked again same UTC day
- **When** bump() is called a second time on the same date
- **Then** the result is 2026.07.10.1 (micro counter starts at 1); a third call same day yields 2026.07.10.2
- **Parameters:** CALVER_SCHEMES = ('YYYY.MM', 'YYYY.MM.DD', 'YYYY.M.D') — calver.py:27
- **Edge case:** scheme 'YYYY.MM' ignores day entirely when comparing 'same_date'
- **Edge case:** if the UTC date has rolled over, micro resets to None (not carried over)
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory (The cited code (src/repo_release_tools/version/calver.py:76-98) implements CalVersion.bump(): it takes today's UTC date, and if it matches the stored year/month/(day, unless scheme is YYYY.MM) it increments a micro counter (new_micro = (self.micro or 0) + 1), otherwise micro is None. The rule card's Given/When/Then (2026.07.10 -> 2026.07.10.1 -> 2026.07.10.…

### CAL-026 — CalVer bump collision handling via micro counter

**Category:** Calculation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/version/calver.py:76-98`

When bumping a calendar version, if today's date matches the stored version's date, a micro counter is appended/incremented instead of producing a duplicate date-only version.

- **Given** Current CalVersion is 2026.07.10 (scheme YYYY.MM.DD) and today is also 2026-07-10
- **When** CalVersion.bump() is called
- **Then** The result is 2026.07.10.1 (micro=1); a second bump on the same day yields 2026.07.10.2
- **Edge case:** scheme='YYYY.MM' ignores day entirely when comparing 'same_date'

### CAL-027 — CalVer bump always uses today's date; same-day re-bump increments a micro counter

**Category:** Calculation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/version/calver.py:76-98`

When bumping a calendar-versioned release, the new version is always today's date; if a version for today already exists, an incrementing micro number (.1, .2, ...) is appended so the version stays unique.

- **Given** Given the current version is 2026.07.10 (scheme YYYY.MM.DD) and today's UTC date is still 2026-07-10
- **When** When CalVersion.bump() is called
- **Then** Then the new version is 2026.07.10.1; a subsequent same-day bump produces 2026.07.10.2
- **Parameters:** CALVER_SCHEMES = (YYYY.MM, YYYY.MM.DD, YYYY.M.D)
- **Edge case:** Bumping on a new calendar day resets micro to None (omitted from the string)
- **Edge case:** Scheme YYYY.MM has no day component so same-date comparison ignores day

### CAL-028 — CalVer bump increments micro counter only when today matches the existing date

**Category:** Calculation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/version/calver.py:76-98`

When bumping a calendar version, the new version always uses today's date; if today's date is the same as the version being bumped, a micro counter is appended/incremented instead of producing a duplicate version string.

- **Given** the current CalVersion is 2026.07.10 (scheme YYYY.MM.DD) and today's UTC date is 2026-07-10
- **When** CalVersion.bump() is called
- **Then** the result is 2026.07.10.1 (micro=1); if bump() is called again the same day the result is 2026.07.10.2
- **Edge case:** Bumping on a different day resets micro to None, e.g. 2026.07.11 with no micro suffix
- **Edge case:** YYYY.MM scheme ignores day when comparing 'same_date'

### CAL-029 — CalVer bump collision counter

**Category:** Calculation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/version/calver.py:76-98`

When bumping a CalVer version to today's date, if today's date exactly matches the version being bumped from, a micro (build) counter is appended/incremented instead of producing a duplicate date-only version.

- **Given** A CalVersion of 2026.07.10 (scheme YYYY.MM.DD) bumped again on the same UTC calendar day
- **When** CalVersion.bump() is called
- **Then** the result is 2026.07.10.1 (micro=1); a further bump the same day yields 2026.07.10.2
- **Parameters:** Schemes: YYYY.MM, YYYY.MM.DD, YYYY.M.D (calver.py:27); date source: UTC now (calver.py:82)
- **Edge case:** YYYY.MM scheme ignores day when comparing 'same_date' (calver.py:89)
- **Edge case:** Micro starts at 1 on first same-day collision, not 0 (calver.py:91)

### CAL-030 — Version ordering / stable-after-prerelease sort

**Category:** Calculation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/version/semver.py:104-110`

For sorting/comparison purposes, a stable release always sorts after any pre-release of the same major.minor.patch, so 1.2.0-rc.1 is considered older than 1.2.0.

- **Given** candidates [1.2.0-rc.1, 1.2.0]
- **When** sorted by sort_key()
- **Then** 1.2.0-rc.1 orders before 1.2.0
- **Parameters:** sort_key 4th element: 0 for pre-release, 1 for stable
- **Edge case:** pre-release labels among themselves order lexically (string comparison), not semver-precedence-aware (e.g. 'rc.9' > 'rc.10' lexically) — potential defect
- ⚠️ **Suspected defect:** Pre-release label comparison at semver.py:110 is a plain string comparison, so 'alpha.10' sorts before 'alpha.9' lexically, which is not standard semver precedence.
- ❓ **SME question:** Should pre-release identifiers be compared numerically per SemVer 2.0 precedence rules (dot-separated identifiers compared numerically when both are numeric) rather than as plain strings?

### CAL-031 — Upstream/candidate version freshness ordering treats stable releases as newer than same-core pre-releases

**Category:** Calculation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/version/semver.py:104-110,122-126`

When comparing versions for sorting or 'is this newer' checks, a stable release always ranks after any pre-release of the same major.minor.patch (e.g. 1.2.0-rc.1 is considered older than 1.2.0).

- **Given** Given candidates [1.2.0-rc.1, 1.2.0, 1.1.9] and current version 1.1.9
- **When** When newer_versions(current, candidates) is computed
- **Then** Then the result, ascending, is [1.2.0-rc.1, 1.2.0] — both are 'newer' and the pre-release sorts before the stable release of the same core
- **Parameters:** n/a
- **Edge case:** Two pre-releases of the same core order lexically by their pre-release label text

### CAL-032 — Upstream mirror discovery: only strictly-newer versions surfaced

**Category:** Calculation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/version/semver.py:122-126`

When checking an upstream package registry for new releases, only versions strictly greater than the current project version (by sort key) are reported; equal or older versions are dropped, and the result is sorted ascending.

- **Given** the current project version is 1.4.0 and the upstream registry returns [1.3.9, 1.4.0, 1.4.1, 1.5.0, 1.4.1-rc.1]
- **When** rrt sync (or sync --bump) computes the list of 'fresh' versions
- **Then** only 1.4.1 and 1.5.0 are returned, in that ascending order (1.4.1-rc.1 sorts before 1.4.1 per semver pre-release ordering and is excluded if not > current)

### CAL-033 — Sync mirror ordering: apply strictly-newer upstream versions ascending

**Category:** Calculation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/version/semver.py:122-126;src/repo_release_tools/commands/sync_cmd.py:110-134,172-198`

When mirroring an upstream package, rrt fetches all published versions, filters to those with a sort_key strictly greater than the current project version, sorts them ascending, and applies each in that order via bump so intermediate versions are represented one at a time rather than jumping straight to the newest.

- **Given** Current version 1.2.0; upstream registry reports [1.1.0, 1.2.0, 1.3.0, 1.4.0]
- **When** `rrt sync --bump --commit` runs
- **Then** 1.3.0 is applied and committed first, then 1.4.0 is applied and committed second — never applied out of order or skipped
- **Parameters:** n/a

### CAL-034 — Upstream mirror sync: strictly-newer versions only, applied in ascending order

**Category:** Calculation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/version/semver.py:122-126;src/repo_release_tools/commands/sync_cmd.py:110-134,172-200`

`rrt sync` compares the current project version against every version returned by the configured upstream package registry, keeps only versions strictly greater than the current one (non-semver / PEP 440 pre-release tags from the registry are silently skipped), sorts them ascending, and — in --bump mode — applies, optionally commits, and optionally tags each one in that ascending order so the project version history replays upstream's release order.

- **Given** current project version is 1.2.0 and the upstream registry lists 1.1.9, 1.3.0, 1.2.5, and a non-parseable pre-release tag 'nightly'
- **When** `rrt sync --bump --commit --tag` runs live (not dry-run)
- **Then** 'nightly' and 1.1.9 are ignored; the tool applies, commits, and tags 1.2.5 first, then 1.3.0 second — never applying 1.3.0 before 1.2.5
- **Parameters:** default tag prefix in mirror mode: 'v'; default commit message template: group.upstream_commit_message ('Mirror: {version}')
- **Edge case:** If tagging fails partway through the ascending loop (`cmd_tag_create` returns nonzero), the loop stops immediately and that exit code is returned — later, even-newer versions are not applied in that run (sync_cmd.py:196-198).
- **Edge case:** With no newer versions found in live mode, the command is a no-op returning exit 0 (sync_cmd.py:173-174).

### CAL-035 — Semantic version bump increments

**Category:** Calculation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/version/semver.py:47-68`

Bumping major, minor, or patch increments that component by 1 and resets everything to its right to zero, discarding any pre-release/build metadata.

- **Given** current version 2.3.5-rc.1
- **When** bump(kind='minor') is called
- **Then** the result is 2.4.0 (patch reset to 0, pre-release cleared)
- **Parameters:** N/A (pure integer increment)
- **Edge case:** major bump resets minor and patch to 0
- **Edge case:** any pre-release/build suffix is dropped on major/minor/patch bumps
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory (The Given/When/Then is faithful to src/repo_release_tools/version/semver.py:47-68 — bump('minor') on major=2,minor=3,patch=5,pre='rc.1' does hit the `case "minor": return Version(self.major, self.minor + 1, 0)` branch (line 59-60), which constructs a new Version with no pre/build args, so they default to None — confirming '2.4.0' with pre-release cleared. H…

### CAL-036 — Semver bump increments and pre-release resets

**Category:** Calculation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/version/semver.py:47-94`

Bumping major/minor/patch increments that segment and resets lower segments and any pre-release/build metadata; bumping a named channel (alpha/beta/rc) starts or advances that channel's counter.

- **Given** Current version is 1.4.2
- **When** bump(kind='minor') is called
- **Then** The result is 1.5.0 (patch reset to 0, pre-release and build cleared)
- **Edge case:** bump('pre-release') on a version with no pre-release label raises ValueError
- **Edge case:** Switching channel (alpha -> beta) resets the pre-release counter to .1 rather than continuing the previous channel's count

### CAL-037 — Semver bump kinds and pre-release channel switching

**Category:** Calculation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/version/semver.py:47-94`

Bumping major/minor/patch clears any pre-release/build metadata; bumping a named channel (alpha/beta/rc) either starts a new pre-release at .1, advances the counter on the same channel, or resets to .1 when switching channels.

- **Given** version 1.2.0-alpha.3
- **When** bump('beta') is called
- **Then** the result is 1.2.0-beta.1 (channel switch resets counter, does not carry over alpha's count)
- **Edge case:** bump('pre-release') on a stable version (no existing pre-release label) raises ValueError
- **Edge case:** bump('alpha') on a stable version starts at alpha.1 on the current patch, not the next patch

### CAL-038 — Pre-release numeric suffix increment

**Category:** Calculation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/version/semver.py:70-82`

Bumping 'pre-release' on a version that already has a pre-release label increments the trailing numeric segment of that label by 1; if there is no trailing number, '.1' is appended.

- **Given** version 1.4.0-beta.3
- **When** bump(kind='pre-release') is called
- **Then** the result is 1.4.0-beta.4
- **Edge case:** bump('pre-release') on a stable version (pre is None) raises ValueError requiring alpha/beta/rc instead
- **Edge case:** label without numeric suffix (e.g. '-beta') becomes '-beta.1'

### CAL-039 — Pre-release channel start/advance/switch

**Category:** Calculation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/version/semver.py:84-94`

Bumping to a named channel (alpha/beta/rc) starts that channel at .1 on a stable version, advances the counter if already on that same channel, or resets to .1 when switching to a different channel.

- **Given** version 1.4.0-alpha.2
- **When** bump(kind='beta') is called
- **Then** the result is 1.4.0-beta.1 (channel switch resets counter, base version unchanged)
- **Parameters:** PRE_RELEASE_CHANNELS = ('alpha', 'beta', 'rc') — src/repo_release_tools/version/semver.py:20
- **Edge case:** same channel: 1.4.0-alpha.2 + bump('alpha') -> 1.4.0-alpha.3 (delegates to pre-release increment)
- **Edge case:** stable version + bump('rc') -> 1.4.0-rc.1 (channel start on current patch, does not increment patch)

### CAL-040 — Semver pre-release channel switch resets the counter; same-channel bump increments it

**Category:** Calculation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/version/semver.py:84-94`

Advancing a pre-release channel (alpha/beta/rc) on a version that already has a pre-release label keeps counting up if it's the same channel, but switching to a different channel resets the count to 1.

- **Given** Given version 1.2.3-alpha.2
- **When** When bump('beta') is called
- **Then** Then the result is 1.2.3-beta.1 (reset); calling bump('beta') again on 1.2.3-beta.1 yields 1.2.3-beta.2 (incremented)
- **Parameters:** PRE_RELEASE_CHANNELS = (alpha, beta, rc)
- **Edge case:** Starting from a stable version (no pre) with a channel bump sets pre to '<channel>.1'
- **Edge case:** Channel comparison is case-insensitive via .lower()

### CAL-041 — Legacy double-escaped regex pattern compatibility for version/pin patterns

**Category:** Calculation · **Priority:** P2 · **Confidence:** Medium
**Source:** `src/repo_release_tools/version/targets.py:328-341`

When a configured version or pin regex pattern doesn't match, rrt automatically retries with a de-escaped variant (turning '\\\\' into '\\') to stay compatible with older config files that double-escaped backslashes in TOML.

- **Given** Given a pattern string containing '\\\\d+' from a legacy config
- **When** When the primary pattern fails to match and a de-escaped variant differs from the original
- **Then** Then both the original and the de-escaped compiled pattern are tried in order until one matches
- **Parameters:** n/a
- **Edge case:** Deduplicates identical variants so the same pattern isn't compiled twice
- ❓ **SME question:** Is this legacy double-escape fallback still needed, or can it be removed now that all configs have been migrated to single-escaped patterns?

### CAL-042 — Post-squash changelog dedup: exact-duplicate and semantic-opposite bullet cancellation

**Category:** Calculation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/workflow/hooks.py:281-374,377-455`

After a squash merge, rrt cleans up the changelog entries the squash commit introduced: exact duplicate bullets (case-insensitive) collapse to the first occurrence, and pairs of bullets that are semantic opposites of each other (e.g. 'add Node 26' and 'remove Node 26', or 'CI: enable X' and 'CI: disable X') are both removed entirely, since together they represent a no-op. Bullets with different scope prefixes (e.g. 'CI:' vs 'Deps:') never cancel each other even if the verb+subject text matches.

- **Given** Given the squash commit added the bullets ['- add Node 26 support', '- CI: enable caching', '- remove Node 26 support', '- add Node 26 support']
- **When** When dedup_changelog_entries processes these four lines
- **Then** Then the exact duplicate 'add Node 26 support' collapses to one occurrence, and that occurrence cancels against 'remove Node 26 support' (opposite verb pair 'add '/'remove '), leaving only '- CI: enable caching'
- **Parameters:** _OPPOSITE_VERB_PAIRS = [(add,remove),(adds,removes),(enable,disable),(enables,disables),(include,exclude),(includes,excludes),(upgrade,downgrade),(upgrades,downgrades),(revert,apply),(reverts,applies)]
- **Edge case:** Removal is restricted to the exact line positions the squash commit introduced (via diff hunk header parsing), so identical lines in older, already-released changelog sections are never touched
- **Edge case:** Consecutive blank lines left behind by removals are collapsed to a single blank line


## Validation rules (155)

### VAL-001 — Tag-triggered CI workflows bypass branch-name validation

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `action.yml:149-168`

The composite Action's branch-name-validation step is unconditionally skipped when the workflow's ref type is a tag (as opposed to a branch), since tag refs don't have a meaningful branch-naming convention to check.

- **Given** a workflow triggered by a tag push (github.ref_type == 'tag')
- **When** the 'Validate branch name' step runs with check-branch-name: 'true'
- **Then** the step prints 'Skipping branch-name validation for tag refs.' and exits 0 without invoking rrt-hooks check-branch-name at all
- **Parameters:** ref_type resolution precedence: INPUT_BRANCH_REF_TYPE override > GITHUB_REF_TYPE > empty (action.yml:161)
- **Edge case:** An explicit branch-ref-type input can override the detected GITHUB_REF_TYPE, letting callers force tag-skip behavior even on non-tag refs

### VAL-002 — Conventional commit subject parsing and merge/release exclusion

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/changelog.py:12-29,65-84`

A commit subject must start with one of a fixed set of types, optionally scoped in parentheses, optionally marked breaking with '!', followed by a colon and description; subjects starting with 'Merge ' or 'release:' are never parsed as conventional commits (so they never populate the changelog).

- **Given** commit subject 'release: v2.1.0'
- **When** parse_conventional_commit('release: v2.1.0') is called
- **Then** returns None (excluded before regex matching) because the subject lower-cases to start with 'release:'
- **Parameters:** base_types = feat|fix|docs|style|refactor|perf|test|build|ci|chore|deps (changelog.py:14)
- **Edge case:** matching is case-insensitive (re.IGNORECASE) so 'FEAT: x' parses as type='feat'
- **Edge case:** extra_types can extend the accepted type set per project config
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory (The rule text accurately describes the cited code: changelog.py:12-29 builds a case-insensitive regex requiring subjects to start with one of the base types (feat|fix|docs|style|refactor|perf|test|build|ci|chore|deps), optionally scoped in parens and marked breaking with '!', followed by ':' and a description; changelog.py:73 (`subject.startswith('Merge ') …

### VAL-003 — Release section / version lookup is case- and 'v'-prefix-insensitive

**Category:** Validation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/changelog.py:329-331,363-397`

When looking up a specific changelog release section (by rrt release notes --version, or internal lookups), the version label match ignores letter case and a leading 'v', so '1.2.3', 'V1.2.3', and 'v1.2.3' all match a '## [1.2.3]' heading.

- **Given** the changelog contains a heading '## [V1.2.3]'
- **When** get_release_section_body(content, "1.2.3") is called
- **Then** the section body is found and returned even though the requested label lacks the 'V' prefix and differs in case

### VAL-004 — Appending to [Unreleased] is a no-op when the exact bullet already exists in that section

**Category:** Validation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/changelog.py:409-451,499-509`

When a commit-msg hook appends a new bullet to the [Unreleased] section, if that exact bullet text is already present under the [Unreleased] section, the changelog file is left unchanged (idempotent behavior prevents duplicate bullets from repeated hook runs, e.g. on amended commits).

- **Given** Given [Unreleased] already contains '- **cli**: add hook installer' and the same commit is processed again
- **When** When append_to_unreleased checks `if bullet in section_body.splitlines()`
- **Then** Then the content is returned unchanged
- **Parameters:** n/a
- **Edge case:** This exact-match check applies per format (Markdown vs RST) using the same logic

### VAL-005 — Changelog append: commit types not mapped in SECTION_MAP are silently ignored

**Category:** Validation · **Priority:** P2 · **Confidence:** Medium
**Source:** `src/repo_release_tools/changelog.py:426-432`

If a commit's conventional type has no entry in the section map (and it's not marked breaking), append_to_unreleased leaves the changelog untouched rather than guessing a section.

- **Given** a commit type not present in SECTION_MAP (e.g. an unrecognized custom type without an extra_section_map entry)
- **When** append_to_unreleased() runs for that commit
- **Then** the changelog content is returned unchanged
- ❓ **SME question:** Is silently dropping unmapped-type commits from the changelog the intended behavior, or should unmapped types raise a warning so authors know their commit was not recorded?

### VAL-006 — Changelog append is idempotent for the exact same bullet

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/changelog.py:434-451`

When auto-appending a conventional-commit-derived bullet to the [Unreleased] section, if that exact bullet text is already present in the target subsection, the changelog content is returned unchanged rather than adding a duplicate line.

- **Given** the Unreleased > Fixed subsection already contains "- Fix login crash" and a new commit "fix: login crash" would render the identical bullet "- Fix login crash"
- **When** append_to_unreleased() runs for that commit
- **Then** the changelog content is returned byte-for-byte unchanged (no duplicate bullet inserted)

### VAL-007 — Merge and release commits are excluded from conventional-commit changelog generation

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/changelog.py:65-84`

When parsing commit subjects to build changelog entries, commits whose subject starts with 'Merge ' or (case-insensitively) 'release:' are never treated as conventional commits and are silently excluded from generated changelog sections.

- **Given** Given commit subjects ['Merge branch feature into main', 'release: v1.11.2', 'feat: add parser']
- **When** When build_changelog_section processes the git log
- **Then** Then only 'feat: add parser' produces a changelog bullet; the merge and release commits are skipped entirely
- **Parameters:** n/a
- **Edge case:** The 'release:' check is case-insensitive ('Release:', 'RELEASE:' also excluded)

### VAL-008 — Artifacts --dry-run only valid with --regenerate

**Category:** Validation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/artifacts_cmd.py:104-110`

The --dry-run flag has no effect and is rejected as an error (exit 1) unless combined with --regenerate; it cannot be used with --check, --snapshot, or --list.

- **Given** `rrt artifacts --check --dry-run`
- **When** The command runs
- **Then** It exits 1 with the message '--dry-run requires --regenerate; it has no effect with --check, --snapshot, or --list', without performing the check
- **Parameters:** n/a

### VAL-009 — Artifacts: --dry-run only has effect combined with --regenerate

**Category:** Validation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/artifacts_cmd.py:104-110`

The --dry-run flag on rrt artifacts is rejected as an error unless --regenerate is also passed, because dry-run has no meaning for --check/--snapshot/--list.

- **Given** a user runs rrt artifacts --check --dry-run
- **When** the command validates its flags
- **Then** it errors "--dry-run requires --regenerate; it has no effect with --check, --snapshot, or --list" and exits 1

### VAL-010 — Commit/branch description must be non-empty after joining words

**Category:** Validation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/branch.py:152-156`

Free-form description words passed to branch/commit commands are joined with single spaces and stripped; if the result is empty, the argument is rejected.

- **Given** rrt git commit "   " (only whitespace)
- **When** join_description parses the description arg
- **Then** argparse raises 'description must not be empty'

### VAL-011 — Branch/tag creation guard: refuse to overwrite existing name

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/branch.py:191-197,346-352,409-415`

rrt branch new, rename, and rescue all refuse to create/rename to a branch name that already exists (except bump's explicit --force override), requiring the user to delete the branch first or choose a different name/description.

- **Given** Branch 'feat/add-parser' already exists
- **When** rrt branch new feat 'add parser' runs (non-dry-run)
- **Then** Command exits 1 with "Branch 'feat/add-parser' already exists. Delete it first or choose a different description."

### VAL-012 — Branch rename requires a valid rebuildable or preservable slug

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/branch.py:252-332`

`rrt branch rename` requires at least one of --type/--scope/--no-scope/new description words; --no-scope specifically requires new description words too (since there's no other way to rebuild a slug without its embedded scope). When only type/scope change without new description words, the existing slug is preserved or scope-prefixed, but the recomputed slug must still satisfy the same length (<=60 chars) and kebab-case rules as branch creation, else the rename is rejected. A rename that computes to the same name as the current branch is treated as a no-op error.

- **Given** current branch is fix/handle-empty-config and the user runs `rrt branch rename --scope core`
- **When** no new description words are given
- **Then** the new branch name is fix/core-handle-empty-config (scope-prefixed, slug preserved); if the resulting slug exceeds 60 characters or fails kebab-case validation, the rename is refused with an error asking for new description words instead
- **Parameters:** SLUG_MAX = 60 characters (branch.py:108)

### VAL-013 — rrt branch rename requires at least one actual change

**Category:** Validation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/branch.py:261-277,326-332`

A branch rename must specify at least one of --type, --scope, --no-scope, or new description words; --no-scope additionally requires description words (since the slug must be rebuilt without the scope); and the computed new name must differ from the current name.

- **Given** rrt branch rename is invoked with no flags
- **When** cmd_rename runs
- **Then** Exit 1: 'Nothing to rename. Specify --type, --scope, --no-scope, or new description words.'

### VAL-014 — rrt branch rescue requires commits ahead of the reset target

**Category:** Validation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/branch.py:392-399`

Rescuing commits into a new branch requires at least one commit ahead of the origin/<branch> (or --since <sha>) reference; otherwise the operation is refused.

- **Given** No commits exist ahead of origin/main and --dry-run is not set
- **When** cmd_rescue runs
- **Then** Exit 1: "No commits found ahead of 'origin/main'. Nothing to rescue. Use --since <sha> to override."

### VAL-015 — Release branch existence guard on bump

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/bump.py:354-377`

rrt bump refuses to create a release branch that already exists unless --force is passed, in which case the existing branch is reset (checkout -B).

- **Given** Branch 'release/v2.0.0' already exists and --force is not passed
- **When** cmd_bump computes branch_name='release/v2.0.0' and checks existence
- **Then** Command exits 1 with "Branch 'release/v2.0.0' already exists. Delete it first or choose a different version."
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### VAL-016 — Release branch existence guard

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/bump.py:362-371`

A bump is refused if the target release branch already exists, unless --force is passed, to prevent silently overwriting an in-progress release branch.

- **Given** branch 'release/v2.1.0' already exists and --force is not set
- **When** rrt bump minor computes new version 2.1.0
- **Then** the command exits with code 1 and the message 'Branch ... already exists. Delete it first or choose a different version.'
- **Edge case:** dry-run mode skips this check entirely (branch_exists only checked when not args.dry_run)
- **Edge case:** --force resets (checks out -B) the existing branch instead of failing
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory (The cited code (src/repo_release_tools/commands/bump.py:362-371) does exactly what the rule card describes: if not a dry-run, it checks git.branch_exists(root, branch_name) and, if the branch exists and --force was not passed, prints "Branch '...' already exists. Delete it first or choose a different version." to stderr and returns exit code 1. So the Given…

### VAL-017 — Changelog compare requires both version labels to exist

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/changelog_compare.py:193-200`

Comparing two changelog release sections fails if either requested version label cannot be found in the changelog.

- **Given** rrt changelog compare v1.0.0 v9.9.9 where v9.9.9 was never released
- **When** the command runs
- **Then** it prints "Release '9.9.9' not found in <path>" to stderr and exits 1 without partial output

### VAL-018 — Changelog lint: sentence-case rule

**Category:** Validation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/changelog_lint.py:120-130,245-256`

Each changelog bullet must start with an uppercase letter (default enabled, configurable via [tool.rrt.changelog_lint].sentence_case).

- **Given** an Unreleased bullet "fix the login bug"
- **When** rrt changelog lint runs with default config
- **Then** a sentence-case violation is reported: "Entry must start with an uppercase letter"

### VAL-019 — Changelog lint: no-trailing-period rule

**Category:** Validation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/changelog_lint.py:131-138`

Changelog bullets must not end with a period.

- **Given** an Unreleased bullet "Fix the login bug."
- **When** rrt changelog lint runs with default config
- **Then** a no-trailing-period violation is reported

### VAL-020 — Changelog lint: max-length rule (default 120 chars)

**Category:** Validation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/changelog_lint.py:139-148,245-256`

Changelog bullets longer than a configurable character limit (default 120, 0 disables the rule) are flagged.

- **Given** a bullet with 135 characters and max_length left at the default
- **When** rrt changelog lint runs
- **Then** a max-length violation is reported: "Entry exceeds 120 characters (135 chars): ..."
- **Parameters:** max_length default = 120 (src/repo_release_tools/commands/changelog_lint.py:99)

### VAL-021 — Changelog lint: no-duplicates rule (case/whitespace-insensitive)

**Category:** Validation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/changelog_lint.py:158-170`

Two changelog bullets in the same section that are identical after case-folding and trimming are flagged as duplicates; only the second (and later) occurrence is reported.

- **Given** bullets "Fix login bug" and "fix login bug " in the same section
- **When** rrt changelog lint runs with no_duplicates enabled (default)
- **Then** the second bullet is reported as a duplicate of the first

### VAL-022 — Changelog lint rule suite and pass/fail behavior

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/changelog_lint.py:93-172,218-242`

Every bullet in the target changelog section is checked against four independently-toggleable style rules: it must start with an uppercase letter, must not end with a period, must not exceed a configurable character limit (default 120, 0 disables the check), and must not duplicate another entry in the same section (case-insensitive, whitespace-trimmed comparison). Violations fail the command with exit 1 unless --no-fail is passed.

- **Given** an [Unreleased] section with bullets 'fix bug.' (lowercase start + trailing period) and two entries 'Add widget' / 'add widget ' (case/whitespace-insensitive duplicate)
- **When** `rrt changelog lint` runs with default config
- **Then** 3 violations are reported (sentence-case, no-trailing-period, no-duplicates) and the command exits 1; with --no-fail it prints the same violations but exits 0
- **Parameters:** sentence_case=true, no_trailing_period=true, max_length=120 (0=disabled), no_duplicates=true, all configurable under [tool.rrt.changelog_lint]
- **Edge case:** If the [Unreleased] section has zero entries, the command exits 0 with a success message instead of running any rules (changelog_lint.py:213-216).
- **Edge case:** Linting a named --release section that doesn't exist in the changelog exits 1 (changelog_lint.py:206-211).

### VAL-023 — CI version: invalid run-attempt value fails fast

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/ci_version.py:142-150`

If GITHUB_RUN_ATTEMPT (or --run-attempt) is not an integer, computing the main-branch dev version fails with a clear error rather than producing a malformed version string.

- **Given** GITHUB_RUN_ATTEMPT="abc" on a refs/heads/main build
- **When** rrt ci-version compute (or sync) runs
- **Then** it raises "Invalid GitHub run attempt value 'abc'; GITHUB_RUN_ATTEMPT/--run-attempt must be an integer." and exits 1

### VAL-024 — CI version apply requires at least one ci_format-configured target

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/ci_version.py:278-287`

rrt ci-version apply refuses to run if the selected version group has no version targets with a ci_format ('pep440' or 'semver_pre') set, since there would be nothing to update.

- **Given** a version group whose targets all leave ci_format unset
- **When** rrt ci-version apply 1.2.3.dev4 runs
- **Then** the command errors "No version targets with ci_format configured..." and exits 1

### VAL-025 — CI version apply: semver_pre conversion only supports plain '.devN' suffixes

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/ci_version.py:296-310`

When applying a version to a target with ci_format='semver_pre' (e.g. Cargo.toml), the PEP 440 '.devN' suffix is converted to SemVer '-dev.N'; if the input version contains '.dev' but the conversion made no change (i.e. it didn't match the expected '.dev<digits>' pattern), the apply fails fast rather than writing an invalid SemVer string.

- **Given** version="1.2.3.devABC" applied to a semver_pre target
- **When** rrt ci-version apply 1.2.3.devABC runs
- **Then** the command errors "Cannot convert '1.2.3.devABC' to a Cargo-compatible SemVer prerelease. Only versions ending in '.dev<digits>' are supported..." and exits 1 without writing the file

### VAL-026 — Config validate: aggregates all check failures rather than stopping at first

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/config_cmd.py:151-218`

rrt config --validate runs every version_target, pin_target, docs config, and folders config validation check and reports every failure found, exiting non-zero if any check failed, rather than stopping at the first error.

- **Given** a config with one invalid version_target and one invalid pin_target
- **When** rrt config --validate runs
- **Then** both errors are printed together in a numbered list and the command exits 1

### VAL-027 — Config reference --check compares generated reference text byte-for-byte and emits a unified diff on drift

**Category:** Validation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/config_cmd.py:221-256`

rrt config --reference --check fails if docs/rrt-config-reference.toml does not exist, or if its content does not exactly match the freshly generated reference text, printing a unified diff to stderr.

- **Given** docs/rrt-config-reference.toml exists but is stale relative to the current schema
- **When** rrt config --reference --check runs
- **Then** the command exits 1 and prints a unified diff showing what changed

### VAL-028 — docs check compares live extraction against lockfile for staleness

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/docs_cmd.py:230-256`

`rrt docs check` re-extracts documentation from source and compares the resulting per-file symbol hashes against the recorded lockfile; any mismatch (added/removed/changed doc block) is reported as stale and the command exits non-zero, telling the user to regenerate.

- **Given** a source file's docstring changed since the last `rrt docs generate --format toml`
- **When** `rrt docs check` runs
- **Then** lock_is_current() returns False with messages describing the drift, the command prints them to stderr and exits 1

### VAL-029 — Generated docs consistency check blocks publish before any file is written

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/docs_cmd.py:280-296`

'rrt docs publish' renders every generated CLI-reference doc target and validates each rendering (frontmatter/H1 consistency) before writing any of them; if any target fails validation, the command reports all consistency issues and exits 1 without writing any file, even the ones that would have been valid.

- **Given** two of five generated command-group pages render successfully but one is missing its required top-level H1
- **When** rrt docs publish runs (not --dry-run)
- **Then** the command exits 1 listing the one bad page, and none of the five pages are written to disk

### VAL-030 — docs publish aborts on frontmatter/H1 consistency issues before writing anything

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/docs_cmd.py:280-296`

Before writing or checking any generated doc target, `rrt docs publish` renders every target and validates that command-group reference pages under docs/*/commands/*.mdx have YAML frontmatter and a top-level H1; if any target fails, the whole publish operation is aborted with no output written, even in non-dry-run mode.

- **Given** one generated command-group page is misconfigured and renders without frontmatter
- **When** `rrt docs publish` runs (not dry-run)
- **Then** consistency issues are printed to stderr and the command returns exit code 1 without writing any of the other, valid target files

### VAL-031 — Docs-map directory targeting: source-bearing, non-ignored, glob-filtered

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/docs_map.py:65-103`

`rrt docs map` only generates a purpose doc for a directory if it directly contains at least one recognized source file, is not an ignored/dot directory, and (when include/exclude globs are configured) passes the exclude-then-include glob filter.

- **Given** A configured root with subdirectory `src/pkg/util` containing only a `.json` file, and `src/pkg/core` containing a `.py` file
- **When** `rrt docs map` walks the tree with no include/exclude patterns
- **Then** `src/pkg/core` is selected as a target directory (has a `.py` file); `src/pkg/util` is skipped because it has no file with extension in {.py,.ts,.tsx,.js,.jsx,.mjs,.cjs,.go,.rs,.sh}
- **Parameters:** _SOURCE_EXTENSIONS = {.py,.ts,.tsx,.js,.jsx,.mjs,.cjs,.go,.rs,.sh}; exclude patterns checked before include patterns

### VAL-032 — docs map lock: three-way drift classification (missing-entry, stale, orphan-entry)

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/docs_map_lock.py:91-127`

Comparing the desired per-directory content hashes against the committed lockfile classifies each discrepancy as: a directory expected but absent from the lock ('missing-entry'), a directory present in both but with a different hash ('stale'), or a directory recorded in the lock but no longer a target ('orphan-entry').

- **Given** the lock has entries for src/a (hash X) and src/b (hash Y), but current desired hashes are src/a=X (unchanged), src/b=Z (changed), and src/c is a new target with no lock entry
- **When** rrt docs map --check runs (drift detection)
- **Then** it reports src/b as 'stale' and src/c as 'missing-entry'; if src/a were removed from the current targets, its lock entry would report as 'orphan-entry'

### VAL-033 — Docstring-suggest threshold triggers on missing docstring, single-line docstring, or short docstring

**Category:** Validation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/docs_suggest.py:188-195`

A module docstring is flagged as needing a scaffold if it is absent, contains no newline (i.e. it's a single line), or its stripped length is below the configured minimum (default 150 characters).

- **Given** a module docstring of exactly 149 characters on one line
- **When** scan() evaluates the file with the default min_chars=150
- **Then** needs_help is True and a finding with reason 'docstring is too short or too flat' is recorded

### VAL-034 — Docstring scaffold trigger threshold

**Category:** Validation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/docs_suggest.py:40-41,167-196`

A Python command module 'needs help' (gets flagged for a docstring scaffold) if it has no module docstring, or its docstring has no newline (i.e. is a single flat line), or its stripped docstring is shorter than a minimum character count (default 150). Files named __init__.py/__main__.py, or containing the literal marker 'rrt:docs-exempt', are always exempt.

- **Given** A module with docstring `"""Does the thing."""` (18 chars, single line, no newline)
- **When** `rrt docs suggest` scans the file
- **Then** The file is flagged with reason 'docstring is too short or too flat' because it lacks a newline and is under 150 chars
- **Parameters:** DEFAULT_MIN_CHARS = 150 (overridable via config or --min-chars); EXEMPT_FILES = {__init__.py, __main__.py}; exempt marker 'rrt:docs-exempt'

### VAL-035 — rrt env check ignores an unset variable (treats it as an empty PATH)

**Category:** Validation · **Priority:** P2 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/env_cmd.py:106-110`

If PATH or PYTHONPATH is entirely unset in the process environment, rrt env check treats it as an empty string (zero entries) rather than raising an error, so the check simply reports no duplicates for that variable.

- **Given** PYTHONPATH is not set in the environment
- **When** rrt env check runs
- **Then** no PYTHONPATH duplicates are reported (empty list), and only PATH is evaluated for duplicates
- ❓ **SME question:** Is silently treating an unset PYTHONPATH as 'no problem' the desired behavior, or should the check flag environments where PYTHONPATH is unexpectedly absent (for stricter CI environments that require it)?

### VAL-036 — env check: PATH/PYTHONPATH duplicate detection

**Category:** Validation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/env_cmd.py:81-126`

`rrt env check` splits PATH and PYTHONPATH on the OS path separator, normalizes each entry with os.path.normpath, drops empty entries, and reports (exit code 1) any entry value that appears more than once in either variable.

- **Given** PATH = '/usr/bin:/usr/local/bin:/usr/bin/'
- **When** `rrt env check` runs
- **Then** '/usr/bin' (normalized, trailing slash stripped) is reported as a duplicate; exit code is 1
- **Parameters:** path separator = os.pathsep

### VAL-037 — env check: flags duplicate PATH/PYTHONPATH entries after normalization

**Category:** Validation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/env_cmd.py:81-126`

rrt env check inspects the process's PATH and PYTHONPATH variables, normalizes each entry (e.g. resolving './' and trailing slashes via os.path.normpath), and reports any entry that appears more than once; it exits 1 if any duplicates are found in either variable, 0 otherwise.

- **Given** PATH=/usr/bin:/usr/local/bin:/usr/bin
- **When** rrt env check runs
- **Then** it reports '/usr/bin' as a PATH duplicate and exits with code 1

### VAL-038 — rrt env check duplicate PATH/PYTHONPATH detection

**Category:** Validation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/env_cmd.py:81-126`

`rrt env check` normalizes every PATH and PYTHONPATH entry and flags any entry that appears more than once (after path normalization) as a duplicate; the command fails (exit 1) if any duplicates exist in either variable, otherwise it exits 0.

- **Given** PATH contains '/usr/bin' twice (once as '/usr/bin' and once as '/usr/bin/')
- **When** `rrt env check` runs
- **Then** both normalize to the same entry and are reported as one duplicate; the command exits 1
- **Parameters:** normalization: os.path.normpath, split on os.pathsep, empty entries ignored

### VAL-039 — squash-local preconditions: clean tree, resolvable base ref, and at least one commit ahead

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/git_commit.py:131-179`

'rrt git squash-local' (outside --dry-run) refuses to run on a dirty working tree, requires a usable base ref (either --base-ref or the current branch's configured upstream), requires that base ref to have a valid merge-base with HEAD, and requires at least one commit ahead of that base ref to squash.

- **Given** the current branch has no configured upstream and --base-ref is not supplied
- **When** rrt git squash-local "message" runs
- **Then** the command exits 1 with 'No upstream branch is configured and no --base-ref was provided.' without touching git state
- **Edge case:** 0 commits ahead of the resolved base ref -> exit 1 'Nothing to squash.'
- **Edge case:** merge-base cannot be determined -> exit 1 distinct error

### VAL-040 — squash-local requires a clean working tree, a resolvable base ref, at least one commit ahead, and a valid merge-base

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/git_commit.py:131-179`

rrt git squash-local refuses to run (non-dry-run) if there are uncommitted changes; fails if neither --base-ref nor an upstream branch can be resolved; fails if there are zero commits ahead of the base ref; and fails if a git merge-base cannot be found between HEAD and the base ref. Any of these guard failures aborts before the destructive git reset --soft is executed.

- **Given** a repo with a dirty working tree and no --dry-run
- **When** rrt git squash-local "message" runs
- **Then** the command exits 1 with 'Working tree has uncommitted changes. Commit or stash them first.' and no git reset/commit is attempted
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### VAL-041 — rrt git doctor: fixed health-check gate list determines pass/fail

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/git_inspect.py:149-273`

'rrt git doctor' evaluates a fixed set of workflow health checks — branch naming, upstream configured, working tree clean, no merge/rebase in progress, no unresolved conflicts, latest commit subject conventional, changelog state valid, and (only when an upstream exists) no required sync — and exits 0 only if every check passes; each failing check is reported and counted.

- **Given** the working tree is clean, upstream is configured, no conflicts, commit subject is conventional, changelog is up to date, but the branch is 3 commits behind its upstream
- **When** rrt git doctor runs
- **Then** the 'does not need sync' check fails, the command reports 1 issue found, and exits 1
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### VAL-042 — Git doctor: changelog-required commits must have touched the configured changelog file

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/git_inspect.py:186-197`

If the most recent commit's subject implies a changelog update was required (per commit-type policy), rrt git doctor checks whether the changelog file path was actually part of that commit's changed files; if not, it flags a problem naming the branch and the expected changelog file.

- **Given** HEAD commit subject is "feat: add sync command" (a type that requires a changelog entry) but the diff for HEAD does not touch CHANGELOG.md
- **When** rrt git doctor runs
- **Then** it reports: "Branch '<name>' suggests changelog work, but CHANGELOG.md is not part of HEAD." as a failing check

### VAL-043 — rrt git doctor: changelog check only triggers for changelog-requiring commit types

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/git_inspect.py:186-197`

Doctor only checks whether the changelog file was touched by HEAD when the latest commit's type requires a changelog entry (per commit_subject_requires_changelog); commits of exempt types skip this check entirely.

- **Given** the latest commit is 'chore: bump deps' (a Maintenance-type, changelog-exempt commit)
- **When** rrt git doctor runs
- **Then** the changelog check is reported as passing without inspecting which files HEAD touched

### VAL-044 — rrt git sync-status: ahead-only is not a failure; behind or diverged or no-base-ref are

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/git_inspect.py:309-391`

'rrt git sync-status' aggregates four checks (no in-progress merge/rebase, no conflicts, a resolvable base ref, and the ahead/behind relation) into a pass/fail count; being purely ahead of the base ref counts as OK, but having no base ref, being behind, or being both ahead and behind (diverged) each count as a failure, and the command exits 1 if any failure is present.

- **Given** the branch is 2 commits ahead and 0 behind its upstream, working tree clean, no conflicts
- **When** rrt git sync-status runs
- **Then** all four checks report OK and the command exits 0 with 'Sync analysis passed.'
- **Edge case:** --base-ref pointing at a non-existent ref fails fast before running any check: exit 1 'Base ref ... does not exist.'

### VAL-045 — Sync-status requires an existing base ref when explicitly provided

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/git_inspect.py:319-323`

If --base-ref is explicitly passed to rrt git sync-status, the command verifies that ref actually exists in the repository before computing ahead/behind counts; a nonexistent ref fails immediately.

- **Given** rrt git sync-status --base-ref origin/does-not-exist
- **When** the command runs
- **Then** it prints "Base ref 'origin/does-not-exist' does not exist." and exits 1

### VAL-046 — Git doctor / sync-status: divergence needs manual resolution, one-directional lag needs sync

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/git_inspect.py:53-73`

Comparing the current branch to its upstream/base ref: if both ahead>0 and behind>0 the branches have diverged and a rebase or merge is required; if only behind>0 the branch merely needs to sync (pull/rebase); if only ahead>0 or neither, no action is needed.

- **Given** current branch is 2 commits ahead and 3 commits behind its upstream
- **When** rrt git doctor or rrt git sync-status evaluates the relation
- **Then** it reports "Branch '<name>' has diverged from <upstream> (ahead 2, behind 3). Rebase or merge is needed." as a check failure

### VAL-047 — rrt git rebootstrap refuses repositories with configured remotes unless --allow-remote

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/git_sync.py:258-266`

Beyond the destructive-confirmation flag, rebootstrap has a second independent safety gate: if the repository has any configured git remotes, the command refuses to proceed unless --allow-remote is also passed, to avoid accidentally destroying history that a remote depends on.

- **Given** a repo has an 'origin' remote configured and --yes-i-know-this-destroys-history is passed but --allow-remote is not
- **When** rrt git rebootstrap runs
- **Then** the command exits 1 with 'Refusing to rebootstrap a repository with configured remotes. Use --allow-remote if that is intentional.' and no git state is touched
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### VAL-048 — publish-snapshot refuses same-remote-as-origin force-push

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/git_sync.py:424-434`

rrt git publish-snapshot refuses to run if the target remote resolves to the same URL as the configured primary remote (default 'origin'), preventing an accidental force-push/history-rewrite of the main remote.

- **Given** --remote points to a URL identical to the primary remote's URL
- **When** cmd_publish_snapshot checks git.primary_remote_conflict
- **Then** Command exits 1 with 'Refusing to publish: <conflict reason>' and no push occurs
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### VAL-049 — publish-snapshot blocked during in-progress git operation

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/git_sync.py:436-444`

Snapshot publishing (and rrt git sync) refuse to run while another git operation (e.g. rebase, merge) is already in progress in the working tree.

- **Given** A rebase is in progress (git.in_progress_operation returns 'rebase')
- **When** cmd_publish_snapshot or cmd_sync runs
- **Then** Command exits 1 with 'Cannot ... while a rebase is in progress. Resolve or abort it first.'

### VAL-050 — Hooks install: duplicate --target values are deduplicated by first occurrence

**Category:** Validation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/hooks_cmd.py:137-146,173-176`

If the same install target is passed more than once, it is only processed once, in the order it first appeared.

- **Given** --target claude-local --target codex-local --target claude-local
- **When** the install plan is resolved
- **Then** claude-local is installed once (at its first position) and codex-local once; no duplicate work or double-counted file totals occur

### VAL-051 — Hooks install: existing hook file blocks the entire install unless --force

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/hooks_cmd.py:537-549`

If installing hooks to any requested target would overwrite an existing hook script file, the whole install command fails immediately (reporting only the first conflict found) unless --force is passed; no target's hook files are written.

- **Given** rrt hooks install --target claude-local --target codex-local where claude-local already has rrt_user_commit_policy.py on disk
- **When** cmd_install runs without --force
- **Then** the command exits 1 reporting the claude-local conflict, and no scripts are written to either claude-local or codex-local

### VAL-052 — Hook install refuses to overwrite existing hook script files without --force

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/hooks_cmd.py:537-549`

Before writing any hook script file, the command checks every planned destination across every requested target; if any file already exists and --force was not passed, the entire install is aborted (no files written for any target), reporting the first conflict found.

- **Given** claude-local already has pre_commit_check.py installed
- **When** `rrt hooks install --target claude-local --target codex-local` runs without --force
- **Then** the command exits 1 citing the claude-local conflict before writing any files to codex-local, even though codex-local had no conflicts

### VAL-053 — rrt init idempotency and precedence guard across manifest formats

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/init.py:110-152,182-320`

Initializing rrt configuration refuses to silently duplicate or clobber existing configuration: writing .rrt.toml fails if another explicit config file is already discovered elsewhere in the repo (unless --force), and fails if .rrt.toml itself already exists (unless --force); appending [tool.rrt] to pyproject.toml/Cargo.toml fails if an rrt table is already present anywhere in the recognized locations (workspace or package metadata for Cargo) regardless of --force; adding an 'rrt' key to package.json fails if the key already exists unless --force.

- **Given** pyproject.toml already has a [tool.rrt] table
- **When** `rrt init --target pyproject` runs (with or without --force)
- **Then** the command exits 1 with guidance to edit the existing section manually — --force does not override this particular check for the manifest-append flow (init.py:210-218)
- **Parameters:** n/a
- **Edge case:** Writing a fresh .rrt.toml while another explicit config file exists elsewhere still succeeds with --force, but a warning is printed that the other file still takes precedence during config discovery (init.py:174-178).
- ⚠️ **Suspected defect:** The pyproject/Cargo manifest-append path (`_init_manifest`) has no --force override for an already-present rrt section, unlike the .rrt.toml and package.json paths which both honor --force for the equivalent 'already exists' case — this asymmetry may be intentional (avoiding a duplicate TOML table) or may be a gap.
- ❓ **SME question:** Should `rrt init --target pyproject --force` be allowed to replace an existing [tool.rrt] table (like package.json's --force path does), or is manual editing intentionally required to avoid corrupting hand-tuned TOML?

### VAL-054 — rrt install cross-validates every requested target against every selected surface before installing anything

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/install_cmd.py:140-149`

Before performing any installation, rrt install checks that all requested --target values are supported by every selected --surface (skill, agents, hooks); if any surface doesn't support a requested target, the whole command fails up front with no partial installation.

- **Given** --surface skill --surface agents --target claude-local --target unsupported-target (agents doesn't support 'unsupported-target')
- **When** rrt install runs
- **Then** it errors "agents does not support target(s): unsupported-target. Available: ..." and exits 1 without installing the skill surface either

### VAL-055 — rrt install cross-surface target compatibility gate

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/install_cmd.py:140-149`

Before installing anything, every requested --target must be supported by every selected surface (skill/agents/hooks); if any surface doesn't recognize a target, the whole multi-surface install is aborted with no partial writes.

- **Given** --target gemini-local --surface skill --surface hooks, where 'hooks' has no gemini-local entry
- **When** `rrt install` validates targets against each surface's target map
- **Then** the command exits 1 with an error naming the unsupported target(s) and the surface, before any files are written for skill or hooks

### VAL-056 — Project info --key output requires a recognized field name

**Category:** Validation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/project_cmd.py:31,50-58`

The 'rrt project info --key' flag only accepts one of a fixed set of metadata field names (name, version, description, authors, license, urls, source); any other key is rejected with the list of valid keys and a non-zero exit.

- **Given** --key invalidfield
- **When** cmd_project_info runs
- **Then** the command prints 'Unknown --key 'invalidfield'. Valid keys: name, version, description, authors, license, urls, source.' to stderr and returns exit code 1

### VAL-057 — Release-check severity classification for version/pin/changelog targets

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/release_cmd.py:138-170,214-274`

When validating release targets, a missing version-target file or missing changelog file is a hard error, unreadable version content is a warning, and a pin-target regex that compiles but matches nothing is a warning; only hard errors fail the overall `rrt release check` run.

- **Given** a version group with a version target file that is unreadable and a pin target whose pattern compiles but has zero matches, and the changelog file exists
- **When** `rrt release check` runs
- **Then** the group is reported with warnings for the unreadable version and the no-match pin target, but the command still exits 0 for that group (only a missing file, missing changelog, or bad regex makes the group fail with exit 1)
- **Parameters:** Severities: not-found version/pin/changelog=error; unreadable version=warning; pin regex compiles but no match=warning; bad regex=error
- **Edge case:** Duplicate pin targets (same path+pattern) across group and global pin targets are de-duplicated before checking, so they are reported/checked only once (release_cmd.py:227-241).

### VAL-058 — Release check severity classification per target type

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/release_cmd.py:138-171,214-267`

`rrt release check` classifies findings with fixed severities: a missing version-target file or missing changelog file is always an error; an existing version-target file whose value can't be read is a warning (not blocking); a missing pin-target file or invalid pin regex is an error; a pin pattern that compiles but finds no match in its file is a warning. Any error anywhere in a group marks the whole group (and overall run) as failed; warnings alone do not.

- **Given** Group has one pin target whose regex compiles but matches nothing in the target file, and all other targets pass
- **When** `rrt release check` runs
- **Then** The group is still reported as OK overall (warnings don't fail a group) with a warning line '<path> no match'; exit code 0
- **Parameters:** n/a

### VAL-059 — Release check global pin-target deduplication

**Category:** Validation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/release_cmd.py:227-241`

When checking pin targets, group-level and global pin targets are combined and de-duplicated by the (path, pattern) pair before checking, so an identical pin target configured both globally and per-group is only checked and reported once.

- **Given** A global pin target on docs/conf.py with pattern 'version = .*' also duplicated in the group's own pin_targets list
- **When** `rrt release check` runs
- **Then** Only one status line is emitted for that (path, pattern) pair, not two
- **Parameters:** n/a

### VAL-060 — Release notes: refuse empty section, mutually exclusive version selectors

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/release_notes.py:120-227`

`rrt release notes` refuses to emit output (exit 1) if the target changelog section is missing or empty, and rejects combining --version with --latest-released as mutually exclusive; version matching for --version is case-insensitive and tolerant of a leading 'v'.

- **Given** `--version` and `--latest-released` both passed
- **When** `rrt release notes --version 1.2.3 --latest-released` runs
- **Then** Command exits 1 with '--version and --latest-released are mutually exclusive.' before touching the changelog
- **Parameters:** n/a

### VAL-061 — Release notes: --version and --latest-released are mutually exclusive

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/release_notes.py:135-142`

A user cannot ask for release notes for both an explicit version and 'the latest released version' at the same time.

- **Given** a user runs rrt release notes --version 1.2.3 --latest-released
- **When** the command parses its arguments
- **Then** it errors with "--version and --latest-released are mutually exclusive." and exits 1

### VAL-062 — Release notes require a non-empty target changelog section

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/release_notes.py:187-226`

Release notes generation refuses to emit output when the requested changelog section (Unreleased, a specific version, or the latest released) doesn't exist or has no content.

- **Given** the changelog has no [Unreleased] section, or the [1.2.3] section exists but is empty
- **When** rrt release notes (or --version 1.2.3) is run
- **Then** the command prints an explicit not-found/empty error to stderr and exits 1 instead of emitting a blank release body

### VAL-063 — Release repair recreate-mode safety gates

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/release_repair.py:158-263`

Recreate mode (`rrt release repair --from BASE`) refuses to run if the working tree is dirty, if there is no [VERSION] changelog section to restore (unless --changelog-from is given), if the base ref doesn't exist, or if the current branch is ahead of its origin remote counterpart (unless --force-allow-pushed is set, since the rewrite requires a destructive force-push). A backup ref is created before the destructive git reset --hard unless --no-backup is passed.

- **Given** branch 'release/v2.0.0' has 3 commits not yet pushed to 'origin/release/v2.0.0'
- **When** `rrt release repair --from main --yes` runs without --force-allow-pushed
- **Then** the command refuses with 'Repair refused: release/v2.0.0 is ahead of origin/release/v2.0.0. Re-run with --force-allow-pushed...' and exits 1 before any git reset happens
- **Parameters:** none
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### VAL-064 — Verify-mode repair refuses to blank a missing changelog section without a body source

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/release_repair.py:316-327,465-476`

If drift detection finds the changelog is missing its [VERSION] section, the repair command refuses to auto-fix unless a version_body can be resolved (from the current branch's changelog or an explicit --changelog-from file), preventing accidental replacement of real release notes with an empty section.

- **Given** the current branch's CHANGELOG.md has no [2.0.0] section, and --changelog-from is not provided
- **When** `rrt release repair --yes` attempts to apply fixes
- **Then** the command refuses with 'Repair refused: CHANGELOG.md has no [2.0.0] section on this branch. Re-run with --changelog-from PATH.' and exits 1 without writing any file
- **Parameters:** none
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### VAL-065 — Release repair requires unambiguous version group and at least one version target

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/release_repair.py:662-690`

If a repo has multiple configured version groups, `rrt release repair` refuses to run unless --group explicitly names one; and even a resolved group is refused for repair if it has zero configured version targets, since there would be nothing to repair.

- **Given** a config with two version groups (backend, frontend) and no --group flag
- **When** `rrt release repair` is run
- **Then** the command exits 1 with 'Repair refused: multiple version groups configured. Pass --group NAME.' before touching any files; a resolved group with an empty version_targets list is likewise refused with 'Repair refused: no version targets configured for the resolved group.'
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### VAL-066 — Release repair drift classification (four kinds)

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/release_repair.py:86-98,360-424`

Drift on a release branch is classified into exactly four kinds: 'version_target' (a version string file doesn't match the declared version, or is missing/unreadable), 'pin_target' (a doc pin whose matched value differs from the declared version — but only if the pattern matches at all), 'changelog_missing_section' (no [VERSION] section exists although a changelog file exists), and 'changelog_unreleased_dirty' (the [Unreleased] section still has bullet entries after a release).

- **Given** CHANGELOG.md exists, has a populated [Unreleased] section with 2 bullets, and also has a [2.0.0] section matching the declared version
- **When** `rrt release repair` (verify mode) runs _collect_drifts
- **Then** one Drift record is produced: kind='changelog_unreleased_dirty', expected='[Unreleased] empty', actual='<has entries>'
- **Parameters:** none
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### VAL-067 — Sync requires configured upstream package

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/sync_cmd.py:106-108`

rrt sync refuses to run unless the active version group has an [tool.rrt.upstream] package configured.

- **Given** a version group with no upstream_package set
- **When** a user runs rrt sync
- **Then** the command prints 'No [tool.rrt.upstream] package configured.' and exits with code 1

### VAL-068 — Upstream version strings that fail to parse are silently skipped

**Category:** Validation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/sync_cmd.py:113-118`

When fetching upstream registry versions, any version string that isn't valid semver/PEP440 is dropped from consideration rather than causing an error.

- **Given** upstream registry returns ['1.2.3', 'nightly-build', '2.0.0a1']
- **When** rrt sync parses fetched version strings
- **Then** '1.2.3' and any other successfully-parsed strings are kept; unparsable entries like 'nightly-build' are excluded without failing the command

### VAL-069 — Sync commit-message template restricted to {version} placeholder

**Category:** Validation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/sync_cmd.py:42-55`

The mirror commit-message template only supports the {version} format placeholder; any other named placeholder, positional placeholder, or unbalanced brace in the template raises a ValueError before any commit is attempted.

- **Given** Template `"Mirror: {ver}"` (misspelled placeholder)
- **When** `rrt sync --bump --commit --commit-message 'Mirror: {ver}'` runs
- **Then** A ValueError is raised: 'Invalid upstream commit_message template ... only the {version} placeholder is supported', and no commit is made
- **Parameters:** supported placeholder: {version} only; default template 'Mirror: {version}'

### VAL-070 — Mirror commit-message template only supports {version} placeholder

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/sync_cmd.py:42-55`

The commit message template used when mirroring an upstream release must contain only the {version} placeholder; any other named/positional placeholder or malformed brace raises a validation error.

- **Given** upstream_commit_message = "Mirror: {version} by {author}"
- **When** rrt sync --bump --commit renders the commit message for version 2.0.0
- **Then** a ValueError is raised: "Invalid upstream commit_message template ... only the {version} placeholder is supported"

### VAL-071 — Tag creation refuses to overwrite existing tag without --force

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/tag.py:132-166`

Creating an annotated tag for the current configured version fails if that tag name already exists, unless --force is passed, in which case the existing tag is deleted first and recreated.

- **Given** tag 'v1.4.0' already exists in the repository and --force is not passed
- **When** `rrt tag create` computes the expected tag name 'v1.4.0'
- **Then** the command prints "Tag 'v1.4.0' already exists. Use --force to overwrite." and exits 1 without running git tag
- **Parameters:** default tag prefix = 'v'
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### VAL-072 — Tag check strict mode gates missing-tag as failure

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/tag.py:191-229`

`rrt tag check` always flags tags that don't match the configured prefix as errors. A missing tag for the currently configured version is only a hard failure (exit 1) when --strict is passed; otherwise it's printed as informational and the command can still exit 0.

- **Given** the current declared version is '1.5.0' and no 'v1.5.0' tag exists yet
- **When** `rrt tag check` runs without --strict
- **Then** the missing tag is printed but does not add to the errors list, so the command can still exit 0 (assuming no prefix-mismatch errors); with --strict it is added to errors and the command exits 1
- **Parameters:** default prefix = 'v'

### VAL-073 — Tag check: prefix mismatch always errors; missing expected tag only under --strict

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/tag.py:191-229`

`rrt tag check` treats any existing tag that doesn't start with the configured prefix as an unconditional error (regardless of --strict), while a missing expected tag for the current version is only an error under --strict — otherwise it is printed as a non-blocking notice and the command can still succeed.

- **Given** Existing tags include 'rel-1.0.0' (wrong prefix) while the configured prefix is 'v', and the expected tag 'v1.2.3' is absent, run without --strict
- **When** `rrt tag check --prefix v` runs
- **Then** The command fails (exit 1) solely due to the prefix-mismatch error on 'rel-1.0.0'; the missing 'v1.2.3' tag is only printed as an informational line, not counted as a failure in non-strict mode
- **Parameters:** default prefix 'v'

### VAL-074 — Tag check flags tags that don't match the configured prefix

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/tag.py:212-214`

rrt tag check inspects every existing tag in the repository and flags any tag whose name does not start with the expected prefix (default 'v').

- **Given** repository tags include v1.0.0, v1.1.0, and legacy-1.0
- **When** rrt tag check runs with the default prefix 'v'
- **Then** 'legacy-1.0' is reported as an error: "Tag 'legacy-1.0' does not match prefix 'v'"

### VAL-075 — Tag prefix mismatch is always an error regardless of --strict

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/tag.py:212-226`

During `rrt tag check`, any existing git tag that doesn't start with the expected prefix is always reported as an error and fails the command, even without --strict; --strict only additionally controls whether a missing expected-version tag is an error.

- **Given** existing tags include 'v1.2.3' (matches prefix 'v') and 'rel-2.0.0' (does not match prefix 'v'), and the expected tag 'v1.2.3' for the current version is present
- **When** `rrt tag check` runs without --strict
- **Then** the command still exits 1 because of the prefix mismatch on 'rel-2.0.0', even though the current version's expected tag is present and --strict is off
- **Parameters:** default prefix: 'v'

### VAL-076 — rrt toc --inject and --anchor must be supplied together

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/toc.py:65-79`

The TOC command requires --inject and --anchor to be used as a pair; supplying only one is rejected.

- **Given** rrt toc README.md --inject README.md (no --anchor)
- **When** the command validates arguments
- **Then** it exits 1 with '--inject and --anchor must be used together.' before reading any file

### VAL-077 — rrt toc requires --inject and --anchor to be used together, and fails when there are no headings in range

**Category:** Validation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/toc.py:65-92,100-110`

rrt toc rejects invocations that pass exactly one of --inject/--anchor (they must both be present or both absent); it also fails if the parsed headings within [--min-level, --max-level] produce an empty table of contents, and fails injection if the target file lacks the matching anchor comment pair.

- **Given** rrt toc README.md --inject README.md  (no --anchor)
- **When** cmd_toc runs
- **Then** the command exits 1 with '--inject and --anchor must be used together.' before reading any file

### VAL-078 — rrt toc requires at least one heading in the requested level range

**Category:** Validation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/toc.py:86-92`

If the source Markdown file has no headings within --min-level..--max-level, the command fails instead of writing an empty TOC.

- **Given** a Markdown file with only H1s and --min-level 2 --max-level 3
- **When** rrt toc runs
- **Then** it exits 1 with 'No headings found in the requested level range.'

### VAL-079 — Phantom empty directory detection exempts .gitkeep-only directories

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/tree.py:521-574`

When scanning the project tree, a directory that has absolutely no visible children is flagged as 'phantom' (git cannot track truly empty directories, so it causes structure drift between checkouts). A directory whose only child is a .gitkeep placeholder file is treated as intentionally preserved and is not flagged.

- **Given** Given a directory 'data/' with zero children, and a directory 'logs/' containing only '.gitkeep'
- **When** When _warn_for_empty_directories scans the tree
- **Then** Then 'data/' is reported as a phantom empty directory (with a warning suggesting a .gitkeep placeholder); 'logs/' is silently skipped
- **Parameters:** n/a
- **Edge case:** When --show-hidden was off, the scan re-checks the filesystem directly (via root param) to still recognize .gitkeep and avoid false positives from hidden-file filtering
- **Edge case:** A directory that filesystem-check shows has other (hidden) children is not flagged even if the tree model shows it as empty

### VAL-080 — Workspace bump: all packages validated before any file is written

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/workspace.py:144-186`

When bumping versions across multiple monorepo packages in one command, every package directory and config must exist and load successfully, and the bump kind must resolve to a valid version for every package, before any file on disk is touched.

- **Given** rrt workspace bump minor --packages api,sdk,docs where 'docs' has no [tool.rrt] config
- **When** the command validates package 1 (api) and package 2 (sdk) successfully but fails to load config for 'docs'
- **Then** the command exits 1 immediately and no version target or changelog file in api or sdk is modified, even though they passed validation
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### VAL-081 — pin_targets path must resolve inside the repository root

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/config/core.py:1059-1095`

Every pin_targets path (whether a literal path or a glob) must resolve — after following symlinks — to a location inside the repository root; absolute paths are rejected outright and any glob match or relative-path resolution that escapes the root (e.g. via '..' or a symlink) fails config loading.

- **Given** pin_targets = [{path = "../../etc/passwd", pattern = "(a)(b)(c)"}]
- **When** the config loads
- **Then** loading fails because the resolved candidate path is outside the repository root: "pin_targets path '../../etc/passwd' resolves to ... which is outside repository root ..."
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### VAL-082 — pin_targets glob pattern must match at least one file

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/config/core.py:1066-1071`

If a pin_targets path uses glob wildcards, it must match at least one existing file at config-load time or the configuration is rejected.

- **Given** pin_targets = [{path = "docs/*.nonexistent", pattern = "(a)(b)(c)"}]
- **When** the config loads
- **Then** loading fails: "pin_targets path glob 'docs/*.nonexistent' matched no files under <root>"

### VAL-083 — extra_branch_types cannot reuse a built-in branch/commit type name

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/config/core.py:659-676;src/repo_release_tools/config/model.py:85-114`

Custom branch types configured via tool.rrt.extra_branch_types must be lowercase kebab/underscore identifiers and must not collide with any built-in conventional-commit type, AI-agent magic type, or dependency-bot type.

- **Given** tool.rrt.extra_branch_types = ["feat"]
- **When** the config is loaded
- **Then** loading fails with "tool.rrt.extra_branch_types entry 'feat' overlaps with a built-in branch type and must not be listed here"
- **Parameters:** Reserved set: feat, fix, chore, docs, refactor, test, ci, perf, style, build, claude, codex, copilot, dependabot, renovate (src/repo_release_tools/config/model.py:87-108)

### VAL-084 — Docs formats list must be non-empty

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/config/docs_config.py:207-222`

If tool.rrt.docs.formats is explicitly provided, it must contain at least one supported output format (md, txt, rich, clipboard, json, toml); an empty list is rejected even though omitting the key entirely defaults to ['md'].

- **Given** tool.rrt.docs.formats = []
- **When** config is loaded
- **Then** a ValueError is raised: 'tool.rrt.docs.formats must not be empty; at least one format is required'

### VAL-085 — EOL override entry required fields

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/config/docs_config.py:74-88`

Each manual EOL override in config must specify a non-empty language, cycle, and an EOL date string; incomplete overrides are rejected at config-load time rather than silently ignored.

- **Given** a [[tool.rrt.eol.overrides]] entry missing the 'eol' key
- **When** the config is loaded
- **Then** a ValueError is raised: 'tool.rrt.eol.overrides[].eol must be a non-empty YYYY-MM-DD string', preventing the config from loading at all

### VAL-086 — Version target replacement mode must be exactly one of kind/pattern/section+field

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/config/model.py:210-259`

Every configured version target must specify exactly one replacement mechanism — a known 'kind', a regex 'pattern', or a 'section'+'field' pair — never zero and never more than one; section and field must always be supplied together.

- **Given** a version target config with both kind='pep621' and pattern='...' set
- **When** the config loads and target.validate() runs
- **Then** loading fails with "Version target replacement selectors are mutually exclusive: use exactly one of kind, pattern, or section+field"
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### VAL-087 — kind='pattern' regex must have exactly 1 capture group (target-level)

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/config/model.py:216-229`

When a version target uses a custom regex pattern instead of a known file kind, that regex must contain exactly one capture group representing the version string, and cannot be combined with section/field.

- **Given** kind='pattern', pattern='(v1.2.3)' with 0 capture groups
- **When** the target validates
- **Then** loading fails: "kind='pattern' pattern must have exactly 1 capture group (the version string); got 0"
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### VAL-088 — pin_targets pattern must have exactly 3 capture groups (prefix, version, suffix)

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/config/model.py:274-301`

A pin_targets regex (used to update version pins in docs/CI files during rrt bump) must define exactly three capture groups: a constant prefix, the bare version, and a constant suffix — enabling in-place substitution without disturbing surrounding text.

- **Given** a pin_targets entry with pattern="(v)(\\d+\\.\\d+\\.\\d+)" (2 groups)
- **When** the pin target validates
- **Then** loading fails: "pin_targets pattern must have exactly 3 capture groups (prefix, version, suffix)"
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### VAL-089 — generated_assets / artifact_targets paths must be relative and must not escape the repo root

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/config/model.py:304-353`

Both generated_assets.path and artifact_targets.path (and artifact_targets.inputs entries) must be relative paths with no '..' path segments, preventing configuration from writing or globbing outside the repository.

- **Given** artifact_targets = [{path = "/etc/cron.d/x"}] or {path = "../outside/*.svg"}
- **When** the target validates
- **Then** loading fails with "artifact_targets.path must be a relative glob pattern" or "... must not escape the repo root (no '..' components)" respectively
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### VAL-090 — publish_targets require non-empty remote and branch

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/config/model.py:355-370;src/repo_release_tools/config/core.py:1166-1187`

Each named publish-snapshot destination must declare a non-empty remote name, branch, and commit message; missing or empty values fail config loading.

- **Given** publish_targets.docs = {branch = "main"} with no remote
- **When** the config loads
- **Then** loading fails: "publish_targets.docs must have a non-empty 'remote'"

### VAL-091 — shared_blocks require non-empty anchor_id, valid position, non-negative blank-line counts, and at least one target glob

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/config/model.py:453-474`

Each docs shared_blocks entry must have a non-empty anchor id, content defined, position of either 'prepend' or 'append', non-negative before/after blank-line counts, and at least one target glob pattern to inject into.

- **Given** a shared_blocks entry with position='middle' or targets=[]
- **When** DocsConfig validates
- **Then** loading fails with a position or missing-targets ValueError naming the offending anchor_id

### VAL-092 — docs.map.on_conflict, prompts, and tree_max_depth are validated enumerations/ranges

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/config/model.py:495-513`

[tool.rrt.docs.map] settings are constrained: on_conflict must be one of merge/skip/error, prompts entries must be from the known set (self-check, auto-update), tree_max_depth must be >= 0, and lock_file must be non-empty.

- **Given** docs.map.on_conflict = 'overwrite' (not a valid value)
- **When** MapConfig validates
- **Then** loading fails: "docs.map.on_conflict must be one of error, merge, skip, got 'overwrite'"

### VAL-093 — docs badge_style and badge_variant are validated enumerations

**Category:** Validation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/config/model.py:554-565`

The docs badge_style must be one of svg/shields/text and badge_variant must be one of the known color/dark/light/reto variants.

- **Given** docs.badge_style = 'png'
- **When** DocsConfig validates
- **Then** loading fails: "docs badge_style must be one of shields, svg, text, got 'png'"

### VAL-094 — Version group resolution / default-group ambiguity

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/config/model.py:734-753`

Resolving the active version group looks up an explicit name first; if none is given, it falls back to the configured default_group_name; if that's unset and exactly one group exists, that single group is used automatically; if multiple groups exist and no default is configured, resolution fails and the caller must pass --group explicitly.

- **Given** Config defines two version groups 'frontend' and 'backend' with no default_group set
- **When** A command calls `resolve_group(None)`
- **Then** A ValueError is raised: 'Multiple version groups configured. Select one explicitly with --group (available: frontend, backend).'
- **Parameters:** n/a

### VAL-095 — extra_branch_types identifier validation and reserved-name collision

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/config/model.py:85-114;src/repo_release_tools/config/core.py:651-676,988-1010`

Custom branch types configured via extra_branch_types must be non-empty, normalized to lowercase, match the pattern of a lowercase letter followed by lowercase letters/digits/hyphens/underscores, and must not collide with any built-in conventional-commit type, AI-agent magic type, or dependency-bot type.

- **Given** Config sets `extra_branch_types = ["Hotfix", "feat"]`
- **When** The config is loaded
- **Then** 'Hotfix' normalizes to 'hotfix' and is accepted as a new branch type, but 'feat' raises ValueError because it overlaps with a built-in conventional-commit type
- **Parameters:** _RESERVED_BRANCH_TYPES = {feat, fix, chore, docs, refactor, test, ci, perf, style, build, claude, codex, copilot, dependabot, renovate}; identifier regex [a-z][a-z0-9_-]*

### VAL-096 — Custom source_url_template must only reference supported placeholders

**Category:** Validation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/docs/formats/_shared.py:38-46`

If a custom source_url_template references a placeholder name not in the supported set (repo_url, ref, path, source_file, line, name, lang), rendering the source link raises a descriptive error listing the supported placeholders rather than silently producing a broken URL.

- **Given** source_url_template = '{repo_url}/{branch}/{path}' (uses an unsupported 'branch' placeholder)
- **When** a doc entry's source URL is rendered
- **Then** a ValueError is raised naming the invalid template and listing the 7 supported placeholders

### VAL-097 — Generated command-group MDX pages must carry YAML frontmatter and a top-level H1

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/docs/publisher.py:798-835`

Every generated .mdx page located directly under docs/src/content/docs/commands/ (and not itself an anchor-block fragment) must start with '---\n...frontmatter...\n---\n' and have a top-level '# ' heading as the first line of body content; rrt docs publish refuses to write output that fails either check.

- **Given** a command-group doc target whose rendered content is missing the closing '---' of its frontmatter block
- **When** validate_generated_page runs as part of rrt docs publish
- **Then** the issue 'malformed YAML frontmatter' is reported and the publish command exits 1 without writing any files

### VAL-098 — Unknown/unmatched version cycle EOL fallback

**Category:** Validation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/eol/core.py:255-270`

If a version string cannot be parsed into a major[.minor] cycle, or no EOL data exists for the language at all, the status is reported as 'unknown' or 'info' rather than blocking the pipeline with an error.

- **Given** language has zero bundled/live records (e.g. an unsupported/misspelled language slug)
- **When** check_eol_status(version, records=[], language=...) runs
- **Then** returns ('info', None) rather than erroring, so unresolvable EOL data never itself fails a CI gate
- **Edge case:** cycle extraction fails entirely (no digits in version string) -> ('unknown', None) immediately, before any record lookup

### VAL-099 — Folder policy exact-mode unexpected-entry detection

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/folders/core.py:260-304,371-391`

When a folder rule is in 'exact' mode, every immediate child of the target directory must be one of the required/allowed files or dirs (by top-level path segment) or match one of the configured allow_patterns (fnmatch glob); anything else is reported as an 'unexpected-entry' violation with severity determined by the rule's mode (warning for 'warn' mode, error otherwise).

- **Given** An exact-mode rule allowing only {README.md, src/} and an unconfigured `scratch.txt` file sitting in the target directory
- **When** `rrt folder check` runs
- **Then** A violation `unexpected-entry` is reported for `scratch.txt` with severity 'error' (assuming rule.mode != 'warn')
- **Parameters:** severity mapping: mode=='warn' -> 'warning', else 'error'

### VAL-100 — Folder policy: exact-mode directories reject unexpected top-level entries

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/folders/core.py:288-303,371-386`

When a folder rule is marked 'exact', every immediate child of the matched directory must be one of the required/allowed files, required/allowed dirs, scaffold entries, or match an allow_patterns glob — anything else is reported as an 'unexpected-entry' violation.

- **Given** a rule requiring only files a.txt and b.txt with exact=true, and the directory also contains c.txt
- **When** rrt folders check runs against that directory
- **Then** a violation is reported: "Unexpected entry 'c.txt' under exact rule '<name>'" with severity derived from the rule's mode

### VAL-101 — Folder policy violation severity by rule mode

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/folders/core.py:389-391;src/repo_release_tools/commands/folder.py:67-118`

Every folder-structure violation (missing required dir/file, unexpected entry under an exact rule, or a selector matching nothing) is tagged 'warning' when the rule's mode is 'warn' and 'error' otherwise (default mode 'strict'); `rrt folder check --report-only` forces every rule to warn mode and always exits 0 regardless of violations found.

- **Given** a required file `LICENSE` is missing under a rule with mode 'strict' (the default)
- **When** `rrt folder check` runs
- **Then** the violation is severity 'error' and the command exits 1 (any violation count > 0 fails unless --report-only was passed, in which case it always exits 0)
- **Parameters:** default policy mode: 'strict'; alternate mode: 'warn'
- **Edge case:** A selector glob that matches zero directories is itself reported as a 'selector-no-match' violation, not silently skipped (folders/core.py:70-87).

### VAL-102 — Branch naming policy

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/hooks.py (compat) -> src/repo_release_tools/workflow/hooks.py:56-105; src/repo_release_tools/commands/branch.py:95-149`

Branch names must be either a reserved name (main/master/develop), a release branch 'release/v<valid semver>', or '<type>/<kebab-case-slug>' where type is one of the conventional commit types, the AI-helper types (claude/codex/copilot), bot types (dependabot/renovate), or a project-configured extra type; slugs for non-bot/non-extra types must be lowercase letters/digits/hyphens only and at most 60 characters.

- **Given** branch name 'feat/Add_New-Parser!!'
- **When** validate_branch_name('feat/Add_New-Parser!!') is called
- **Then** returns an error: "Branch slug 'Add_New-Parser!!' must be normalized kebab-case using only lowercase letters, digits, and hyphens."
- **Parameters:** SLUG_MAX = 60 (branch.py:108); BRANCH_SLUG_RE = ^[a-z0-9]+(?:-[a-z0-9]+)*$ (branch.py:110); CONVENTIONAL_TYPES = feat, fix, chore, docs, refactor, test, ci, perf, style, build
- **Edge case:** release/v<x> branches are validated purely via Version.parse succeeding, not via the kebab-case slug rule
- **Edge case:** bot and extra_branch_types branches (e.g. dependabot/*) skip slug format/length checks entirely, only requiring a non-empty slug
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory (The Given/When/Then is faithful to the code: workflow/hooks.py:56-105 (re-exported unchanged via the compat shim src/repo_release_tools/hooks.py, which just does `globals()[_name] = getattr(_workflow_hooks, _name)`) implements exactly the described precedence — reserved names (ALLOWED_BRANCH_NAMES = main/master/develop, workflow/hooks.py:65-66), release/v<s…

### VAL-103 — MCP branch-new tool refuses to create a branch that already exists

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/mcp/tools/git_tools.py:53-64`

The rrt_branch_new MCP tool, when run with dry_run=False, checks whether the target branch name already exists locally before running git checkout -b, and returns a structured error instead of attempting (and failing) the checkout.

- **Given** a branch named 'feat/add-x' already exists and dry_run=False
- **When** rrt_branch_new(commit_type='feat', description='add x', dry_run=False) is invoked
- **Then** the tool returns created=False with error "Branch 'feat/add-x' already exists. Delete it first or choose a different description." without running git checkout

### VAL-104 — MCP version-bump tool restricted to a fixed set of level keywords

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/mcp/tools/version_tools.py:43-59`

The rrt_bump MCP tool only accepts level values major, minor, patch, alpha, beta, or rc; any other value is rejected before any config or version state is touched, and dry_run defaults to True so the destructive path requires an explicit opt-out.

- **Given** level="pre-release" (a valid Version.bump kind but not exposed via MCP)
- **When** rrt_bump is invoked
- **Then** returns {"error": "level must be one of: major, minor, patch, alpha, beta, rc"} without reading any config
- **Edge case:** dry_run=True (the default) still reads and reports the current/new version per group but performs no writes

### VAL-105 — MCP rrt_bump tool only supports semver channels, not CalVer or explicit version strings

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/mcp/tools/version_tools.py:43-77`

The MCP-exposed version-bump tool accepts only major/minor/patch/alpha/beta/rc as the bump level; unlike the `rrt bump` CLI command, it has no path to bump a CalVer scheme or set an explicit version string.

- **Given** Given an MCP client calls rrt_bump(level='calver')
- **When** When the tool validates `level not in valid_levels`
- **Then** Then it returns {'error': 'level must be one of: major, minor, patch, alpha, beta, rc'} without attempting any bump
- **Parameters:** valid_levels = (major, minor, patch, alpha, beta, rc)
- **Edge case:** dry_run defaults to True; only an explicit dry_run=False writes files

### VAL-106 — Preflight: working tree must be clean before mutating bump

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/preflight.py:17-22,46-68`

Before writing any version changes, the working tree must have no uncommitted changes, unless the operation is a dry run.

- **Given** an uncommitted, dirty working tree and dry_run=False
- **When** run_preflight(config, dry_run=False, group=group) is called
- **Then** PreflightError is raised: 'Working tree has uncommitted changes. Commit or stash them first, or use --dry-run.'
- **Edge case:** dry_run=True skips the clean-tree check entirely
- **Edge case:** version targets that don't exist or can't be parsed also fail preflight (targets.py check)
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory (The Given/When/Then is faithful to the code: check_working_tree_clean (preflight.py:17-22) calls git.working_tree_clean(root) (workflow/git.py:156-165, which runs `git status --porcelain` and checks for empty output) and raises PreflightError with the exact quoted message when the tree is dirty. run_preflight (preflight.py:46-68) only invokes this check whe…

### VAL-107 — Pre-flight checks gate mutating commands (bump)

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/preflight.py:17-68`

Before rrt bump performs any file writes, it must confirm the working tree is clean (skipped only in dry-run), at least one version group is configured, and every configured version target file exists and is readable in its expected format.

- **Given** Working tree has uncommitted changes and --dry-run is not set
- **When** run_preflight is called
- **Then** PreflightError is raised: 'Working tree has uncommitted changes. Commit or stash them first, or use --dry-run.' and the bump aborts with exit code 1
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### VAL-108 — Config consistency guard requires at least one version group

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/preflight.py:40-43`

A repository configuration must define at least one version group before any bump/mutating operation can proceed.

- **Given** config.version_groups is empty
- **When** check_config_consistent is called
- **Then** PreflightError('No version groups are configured in [tool.rrt].') is raised
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### VAL-109 — Preflight gate order for mutating commands

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/preflight.py:46-68`

Before any mutating command (like `rrt bump`) writes files, it checks in order: (1) at least one version group is configured, (2) every version target file is readable/parseable, (3) the working tree is clean — but the working-tree-clean check is skipped entirely in --dry-run mode. The first failing check aborts the whole command via PreflightError.

- **Given** one version_targets file has been deleted from disk and --dry-run is not passed
- **When** `rrt bump patch` calls run_preflight
- **Then** check_version_targets_readable raises PreflightError('Version target pre-flight checks failed:\n...') before check_working_tree_clean ever runs, aborting before any writes
- **Parameters:** none
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### VAL-110 — Health-lock regression-only comparison

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/state.py:189-220`

The health snapshot lock only flags a failure when a check's severity has gotten worse than what was previously recorded (ok/obsolete -> warning/error, or a brand-new check appearing); an improvement from warning back to ok is silently accepted without needing to update the lock.

- **Given** locked status for check 'docs-map' is 'warning', new run reports 'ok'
- **When** health_lock_is_current(lock_path, checks) is evaluated
- **Then** is_current is True (no regression) even though the lock file itself now technically disagrees with the new status
- **Parameters:** _SEVERITY = {ok: 0, obsolete: 0, warning: 1, error: 2} (state.py:203)
- **Edge case:** a brand-new check not previously in the lock is always reported as a regression, even if its status is 'ok'

### VAL-111 — Health/tree/docs/artifacts lock regression classification only flags severity increases

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/state.py:189-220`

When comparing a fresh health check run against the previously snapshotted results, only new failures or checks that got worse (e.g. ok to warning, or warning to error) are reported as regressions; checks that improved are accepted silently.

- **Given** Given a locked check 'folder.python-package' at status 'warning' and a new run reporting status 'ok'
- **When** When health_lock_is_current compares the two
- **Then** Then no regression is reported for that check (improvement is silent)
- **Parameters:** Severity ranking: ok=0, obsolete=0, warning=1, error=2
- **Edge case:** A brand-new check name not present in the old lock is always reported as a regression, regardless of its status
- **Edge case:** 'obsolete' is treated as equally low severity to 'ok'

### VAL-112 — Health-lock regression detection: only severity increases are flagged

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/state.py:189-220`

Comparing new health check results against the snapshot only reports a problem when a check's severity got worse (ok/obsolete → warning/error, or warning → error); improvements are silently accepted, and a brand-new check not previously in the snapshot is always flagged.

- **Given** a check named 'artifacts' was previously 'warning' and is now 'ok'
- **When** health_lock_is_current compares the new results to the lockfile
- **Then** no regression is reported because ok (severity 0) is not worse than warning (severity 1)
- **Edge case:** Severity order is fixed: ok=0, obsolete=0 (tied with ok), warning=1, error=2
- **Edge case:** A check present in the new run but absent from the old lock is always reported as a regression, even if its new status is 'ok'

### VAL-113 — Health-lock check status regression severity ranking

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/state.py:189-220`

Health snapshot comparisons only flag a problem when a check's status gets worse than what was previously recorded (ok/obsolete -> warning -> error); improvements are silently accepted without any diff reported, and any brand-new check name not seen in the prior snapshot is always reported.

- **Given** a health lock recording check 'docs-map' at status 'warning'
- **When** health_lock_is_current() runs and the current run reports 'docs-map' as 'ok'
- **Then** no regression is reported (improvement is silent); if instead the current run reports 'error', a regression message 'Health regression for docs-map: warning → error' is produced
- **Parameters:** severity ranks: ok=0, obsolete=0, warning=1, error=2 (state.py:203)
- **Edge case:** 'obsolete' is treated as equally benign as 'ok' (both rank 0)
- **Edge case:** A check present in the new run but absent from the old lock is always a regression regardless of its status (state.py:210-211)

### VAL-114 — Tree snapshot drift detection uses hash equality, not entry count

**Category:** Validation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/state.py:248-341`

The working-tree structure is considered drifted purely when its combined tree_hash differs from the locked snapshot's hash, even if the entry count is unchanged (e.g. a rename).

- **Given** the locked snapshot has entry_count=42, tree_hash='sha256:aaa...' and the current tree has entry_count=42, tree_hash='sha256:bbb...'
- **When** `rrt tree --check` runs tree_lock_is_current
- **Then** drift is reported with delta '+0' and a suggestion to run `rrt tree --snapshot`, because equal counts with different hashes still count as drift
- **Parameters:** none

### VAL-115 — Tree-lock drift diagnostic includes signed entry-count delta and remediation hint

**Category:** Validation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/state.py:248-341`

When the current repository tree hash differs from the snapshot, the drift message reports the entry-count delta as a signed number and, when the entry counts are equal despite the hash differing (implying content/order changed without item count changing), appends a suggestion to re-run the snapshot command.

- **Given** locked snapshot entry_count=42, current entry_count=42, but tree_hash differs
- **When** tree_lock_is_current compares them
- **Then** the drift message includes 'entry count: was 42 → now 42 (Δ 0)' plus a suggestion line 'run rrt tree --snapshot to refresh', since equal counts with differing hash implies a same-size but reshuffled/renamed tree
- **Edge case:** If the lockfile has no snapshot section at all, drift is reported as 'Tree snapshot not found in lockfile' without further diagnostics

### VAL-116 — Tree lockfile drift diagnostic with signed delta and remediation hint

**Category:** Validation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/state.py:248-341`

When the repository's tree snapshot hash no longer matches the recorded lockfile, the tool reports both the entry-count delta and, specifically when counts match but hashes still differ (implying files were renamed/moved/reordered rather than added or removed), suggests re-running the snapshot command.

- **Given** a locked tree_hash differs from the current tree_hash, with entry_count unchanged (was 42, now 42)
- **When** tree_lock_is_current() runs
- **Then** the drift message includes 'entry count: was 42 → now 42 (Δ 0)' plus a 'suggestion: run rrt tree --snapshot to refresh' line, because equal counts but differing hashes indicate structural change without count change
- **Parameters:** n/a
- **Edge case:** Missing tree_hash key in the lock entirely short-circuits to a generic 'Tree snapshot not found' message without the detailed diagnostic (state.py:263-265)
- **Edge case:** Non-integer counts fall back to '?' delta rather than raising (state.py:284-302)

### VAL-117 — Artifact input-staleness detection is independent of output-hash checks

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/state.py:377-420,423-480`

For artifact targets that declare 'inputs' (source files feeding a generated output), rrt separately tracks a combined hash of those input files; if the inputs change since the last snapshot, that's reported as drift even if the generated output file's own hash still matches the lock (i.e. the output is now stale relative to its sources).

- **Given** Given an artifact target with inputs=['src/**/*.py'] whose combined input hash was sha256:abc at snapshot time, and a source file has since changed
- **When** When artifacts_lock_is_current recomputes the combined input hash
- **Then** Then drift is reported as 'Input files changed since last snapshot ... run rrt artifacts --regenerate or --snapshot', independent of whether the output artifact file itself has changed
- **Parameters:** n/a
- **Edge case:** If inputs are configured but no inputs_hash was ever stored in the lock, that's reported as a distinct drift needing --snapshot to initialize
- **Edge case:** Input hashing includes each file's relative path as a boundary marker so that different file splits with identical concatenated bytes don't collide

### VAL-118 — Artifacts lock: input-file staleness detection distinct from output hash drift

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/state.py:377-480`

Artifact targets with a configured 'inputs' glob are tracked by a combined hash of all matching input files, separate from the hash of the output artifact itself. Drift is reported if inputs changed since the last snapshot (even if the output file's own hash hasn't been checked yet), if the output artifact isn't yet in the lock, if its content hash differs, or if a locked file no longer exists on disk.

- **Given** target path 'dist/bundle.js' configured with inputs=['src/**/*.ts'], and a source .ts file changed since the last snapshot
- **When** artifacts_lock_is_current runs
- **Then** a drift message 'Input files changed since last snapshot (target: dist/bundle.js) — run rrt artifacts --regenerate or --snapshot' is emitted, independent of whether dist/bundle.js's own hash changed
- **Edge case:** If inputs are configured but the lock has never recorded an inputs_hash for that target, a distinct 'no input hashes in lock' message is emitted instructing an initializing snapshot
- **Edge case:** Input hash combines each matched file's repo-relative path plus content, separated by null bytes, so identical concatenated content from differently-split files does not collide

### VAL-119 — Artifact input-staleness drift vs missing-hash drift distinction

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/state.py:423-461`

For artifact targets that declare source 'inputs' globs, drift detection distinguishes between never having recorded an inputs hash (needs an initial snapshot) versus having a recorded hash that no longer matches the current inputs (needs regeneration).

- **Given** an artifact target with inputs configured, and the lock's [targets] table has no inputs_hash entry for that target's path
- **When** artifacts_lock_is_current() runs
- **Then** the message is 'Input tracking configured but no input hashes in lock ... run rrt artifacts --snapshot to initialize', distinct from the message shown when a stored inputs_hash exists but no longer matches ('Input files changed ... run rrt artifacts --regenerate or --snapshot')
- **Parameters:** n/a
- **Edge case:** A target glob that produces zero matching files still records an empty/skipped inputs entry (no hash returned, state.py:363-364 in _compute_inputs_hash) and callers must omit the key rather than storing None

### VAL-120 — Artifact staleness detection via input hash

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/state.py:423-480`

An artifact target configured with 'inputs' globs is considered stale not only when its own output hash changed, but also when the combined hash of its declared input files has changed since the lock was last written, or when input tracking was newly configured but the lock has no baseline yet.

- **Given** a target with inputs=['src/**/*.py'] whose source hash in the lock is stale relative to current source
- **When** artifacts_lock_is_current(lock_path, artifact_targets, repo_root) runs
- **Then** drift message: 'Input files changed since last snapshot (target: <pattern>) — run rrt artifacts --regenerate or --snapshot'
- **Edge case:** a file present in the lock but no longer matched by any glob and missing from disk -> 'Artifact in lock but file missing'

### VAL-121 — Artifact lock drift detection

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/state.py:423-480`

An artifact is considered drifted if its file content hash differs from the locked hash, if it is newly matched but absent from the lock, if it was locked but the file no longer exists, or if any of its declared input files changed hash since the lock's inputs_hash was recorded.

- **Given** a locked artifact target's inputs_hash was computed from files A and B, and file A is subsequently edited
- **When** `rrt artifacts --check` (via artifacts_lock_is_current) runs
- **Then** the check reports 'Input files changed since last snapshot (target: <pattern>) — run rrt artifacts --regenerate or --snapshot'
- **Parameters:** none

### VAL-122 — Anchor injection: missing start/end anchor is a hard failure, not silent skip

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/tools/inject.py:280-305`

When content should be injected into an anchor block but the target file lacks the required anchor comment pair (or is missing entirely), the operation fails loudly rather than appending or creating anchors automatically.

- **Given** an .mdx doc target configured with anchor_id='cli-reference' whose output file exists but has no {/* rrt:auto:start:cli-reference */} marker
- **When** apply_generated_docs runs with that anchor_id
- **Then** it returns exit 1 with a message naming the missing MDX-style anchor tokens; the file is not modified

### VAL-123 — Anchor ID format restriction

**Category:** Validation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/tools/inject.py:54,202-203`

Anchor IDs used for injected content blocks must start with a letter or digit and contain only letters, digits, dots, underscores, or hyphens.

- **Given** anchor_id = '#bad id!'
- **When** replace_anchored_block is called
- **Then** it raises ValueError('Invalid anchor id: ...') before searching the file

### VAL-124 — Registry URL formatting requires all declared required placeholders

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/tools/platform.py:172-276`

Each package-registry (pypi, npm, maven, nuget, cargo, rubygems, packagist, docker) has a declared set of required template placeholders; formatting a registry URL fails if any required value is missing or empty, and an unknown registry or template key is also rejected.

- **Given** format_registry_url('maven', groupId='org.example', artifactId='lib') is called without version
- **When** the maven template (which requires groupId, artifactId, version) is rendered
- **Then** a ValueError is raised: 'missing required values for registry maven: version'

### VAL-125 — Registry URL templates require declared required-fields to be present and non-empty

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/tools/platform.py:237-276`

Formatting a package-registry URL (e.g. for pypi, npm, maven, packagist, docker) fails if any of that registry's required placeholder values (e.g. 'package' for pypi; 'groupId','artifactId','version' for maven) is missing or an empty string.

- **Given** format_registry_url('maven', groupId='org.example', artifactId='lib')  # version omitted
- **When** format_registry_url runs
- **Then** a ValueError is raised: 'missing required values for registry maven: version'

### VAL-126 — TOC heading extraction ignores fenced code blocks

**Category:** Validation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/tools/toc.py:31-65`

Lines beginning with # inside fenced code blocks (delimited by matching ``` or ~~~ markers) are never treated as Markdown headings, and setext-style (underline) headings are not recognized at all.

- **Given** A code block containing `#!/bin/bash` between triple-backtick fences
- **When** Headings are parsed from the document
- **Then** The shebang line is not included in the extracted heading list
- **Parameters:** n/a

### VAL-127 — CalVer round-trip padding heuristic

**Category:** Validation · **Priority:** P2 · **Confidence:** Medium
**Source:** `src/repo_release_tools/version/calver.py:52-74`

When parsing a CalVer string without an explicit scheme, the scheme is inferred: no day segment means YYYY.MM; if both month and day segments are two digits (or day<10) it is treated as YYYY.MM.DD; otherwise YYYY.M.D.

- **Given** Input string '2026.5.3'
- **When** CalVersion.parse('2026.5.3') is called
- **Then** scheme is inferred as 'YYYY.M.D' (month is not zero-padded)
- **Edge case:** Ambiguous cases like '2026.05.3' (day<10, unpadded) are heuristically classified as YYYY.MM.DD per the day<10 branch
- ❓ **SME question:** Is the day<10-implies-padded heuristic intentional, or could it misclassify legitimate unpadded single-digit-day CalVer strings (e.g. distinguishing '2026.05.3' from '2026.5.03')?

### VAL-128 — CalVer scheme inference heuristic from parsed component widths

**Category:** Validation · **Priority:** P2 · **Confidence:** Medium
**Source:** `src/repo_release_tools/version/calver.py:52-74`

When parsing a calendar version string, the scheme (YYYY.MM, YYYY.MM.DD, or YYYY.M.D) is inferred from whether the month/day components are zero-padded, not stored explicitly.

- **Given** the version string "2026.05.15"
- **When** CalVersion.parse is called
- **Then** scheme is inferred as YYYY.MM.DD because both month and day are 2-digit zero-padded
- **Edge case:** "2026.5.15" is ambiguous with day<10 heuristic and is classified YYYY.MM.DD per the heuristic at line 68 (day<10 counts as padded), which may misclassify unpadded single-digit-day versions
- ⚠️ **Suspected defect:** The heuristic `day < 10` at calver.py:68 treats any single-digit day as 'padded' even when the source string had no leading zero, potentially misclassifying YYYY.M.D versions as YYYY.MM.DD.
- ❓ **SME question:** Should scheme inference for ambiguous single-digit day/month combinations (e.g. '2026.5.5') default to YYYY.MM.DD or YYYY.M.D, and does this affect canonical re-serialization correctness?

### VAL-129 — Semver string format validation

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/version/semver.py:13-17,34-45`

A version string must match MAJOR.MINOR.PATCH with optional -prerelease and +build metadata, where each numeric component has no leading zero (except the value 0 itself), or parsing fails.

- **Given** input string '01.2.3'
- **When** Version.parse('01.2.3') is called
- **Then** raises ValueError('Invalid semver: ...') because '01' has a disallowed leading zero
- **Parameters:** regex at semver.py:13-17
- **Edge case:** valid pre-release identifiers: alphanumeric segments separated by dots (alpha, alpha.1, rc.10)
- **Edge case:** build metadata after '+' is accepted but never participates in bump logic
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory (The Given/When/Then is faithful to the code: src/repo_release_tools/version/semver.py:13-17 defines _SEMVER_RE requiring major/minor/patch to match `0|[1-9]\d*` (no leading zeros except bare 0), and Version.parse (lines 34-45) raises ValueError(f"Invalid semver: {raw!r}") when the compiled regex fails to match — so parsing '01.2.3' does raise as described. …

### VAL-130 — Semver 'pre-release' bump requires an existing pre-release label

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/version/semver.py:70-82`

You cannot ask to bump 'the pre-release number' unless the version already carries a pre-release tag like -alpha or -rc; otherwise the operation is rejected.

- **Given** Given a stable version 1.2.3 with no pre-release label
- **When** When Version.bump('pre-release') is called
- **Then** Then a ValueError is raised instructing to use 'alpha', 'beta', or 'rc' to start a channel instead
- **Parameters:** n/a
- **Edge case:** If the pre-release label has a numeric suffix (e.g. rc.3) it increments to rc.4; otherwise it appends '.1' (e.g. 'rc' -> 'rc.1')

### VAL-131 — Auto-detected version target consistency check

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/version/targets.py:158-176;src/repo_release_tools/commands/bump.py:301-306`

When rrt config is auto-detected (no explicit [tool.rrt] present), if multiple auto-discovered version-target files report different version strings, the bump command fails rather than picking one, since it can't determine the source of truth.

- **Given** Auto-detected pyproject.toml reports version 1.2.0 and package.json reports 1.1.0
- **When** check_autodetected_version_consistency is evaluated during cmd_bump
- **Then** Command exits 1 with 'Auto-detected version files do not agree: pyproject.toml=1.2.0, package.json=1.1.0. Make them consistent, or add rrt config to choose explicit targets/groups.'

### VAL-132 — Pattern-based version replacement legacy double-escape compatibility

**Category:** Validation · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/version/targets.py:328-341`

When a configured regex pattern for a version target fails against the literal pattern string, the tool automatically retries with backslashes de-doubled, to tolerate old configs that stored regex patterns with double-escaped backslashes (e.g. from earlier TOML-encoding conventions).

- **Given** a stored pattern containing '\\\\d+' (double-escaped) from a legacy config
- **When** search_pattern() or replace_pattern_version() is called
- **Then** if the literal pattern doesn't match, a de-escaped variant ('\\d+') is tried automatically before giving up
- **Parameters:** n/a
- **Edge case:** Both variants are deduplicated before compiling so identical patterns aren't compiled twice (targets.py:335-340)

### VAL-133 — Pin target missing-match policy at bump time

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/version/targets.py:357-382 (branching logic and default), with call-site wiring at src/repo_release_tools/commands/bump.py:139-146`

When a configured pin_target's regex finds zero matches in its target file, `rrt bump` fails the whole bump by default ('error' policy); setting pin_target_missing='warn' downgrades this to a printed warning that allows the bump to continue. `rrt release check` always treats a missing pin match as a warning regardless of this setting.

- **Given** pin_target_missing is left at its default value (unset)
- **When** `rrt bump patch` finds a pin_targets pattern with zero matches in its target file
- **Then** the bump command fails; only setting `pin_target_missing = "warn"` in [tool.rrt] allows the bump to continue with a warning printed instead
- **Parameters:** pin_target_missing default = "error"; alternative = "warn" (bump.py:690-711)
- ❓ **SME question:** Citation was corrected by referee (The cited span src/repo_release_tools/commands/bump.py:690-711 is not executable code — it sits inside the module-level docstring of bump.py (the docstring runs from line 1 to well past line 749, covering the CLI's `## Overview`, `## Changelog behavior`, and config-reference sections). Lines 690-711 specifically are a markdown subsection titled '### `pin_target_missing`' that descr…

### VAL-134 — Pin reference already-at-target-version is a silent no-op

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/version/targets.py:357-400`

When updating a doc/CI pin reference, if the currently pinned version already equals the new version, nothing is written and the tool reports the file is already up to date instead of erroring (unlike the primary version target, which errors on no-op).

- **Given** a pin_target pattern that currently captures version "1.11.2"
- **When** replace_pin_in_file is called with new_version="1.11.2"
- **Then** the function prints "{path}  already at 1.11.2" and returns without writing or erroring
- **Edge case:** This is asymmetric with replace_version_in_file, which raises RuntimeError on no-op for the same scenario

### VAL-135 — Pin-target missing-match policy at write time (warn vs error)

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/version/targets.py:357-401`

When updating a documentation/CI pin reference to a new version, if the configured pattern fails to match the file, the tool either raises a hard error (default) or prints a warning and skips the file, controlled by the pin_target_missing setting.

- **Given** pin_target_missing='warn' and a pin target file whose regex pattern no longer matches
- **When** replace_pin_in_file() runs
- **Then** a warning is printed and the file is left unchanged, with no exception raised; with pin_target_missing left at default 'error', the same situation raises RuntimeError instructing the user to set warn mode
- **Parameters:** pin_target_missing default: "error" (targets.py:362); values: "warn" | "error"
- **Edge case:** If the pattern matches but the captured current version already equals new_version, the write is skipped as a no-op with an informational line, not treated as an error (targets.py:384-388)

### VAL-136 — Version target replacement raises on no-op substitution

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/version/targets.py:69-94,96-136`

If a computed 'new version' is identical to the currently-read version for a target file, the write is treated as an error rather than silently skipped, both for single-target and atomic multi-target replacement.

- **Given** a pep621 target already at version 1.11.2
- **When** replace_version_in_file is called with new_version="1.11.2"
- **Then** a RuntimeError "... version replacement had no effect" is raised and no bytes are written
- **Edge case:** Atomic multi-target replace_all_versions_atomic performs this same-version check in Phase 1 (before any file is written), so a single stale target aborts the whole batch

### VAL-137 — Version target 'no-effect' guard

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/version/targets.py:78-83,118-122`

If the version already stored in a file exactly equals the version being bumped to, rrt refuses to proceed and raises an error rather than silently doing nothing.

- **Given** Given a pyproject.toml already at version 1.11.2 and the user runs `rrt bump 1.11.2`
- **When** When replace_version_in_file / replace_all_versions_atomic checks current_version == new_version
- **Then** Then a RuntimeError '<path> version replacement had no effect' is raised
- **Parameters:** n/a

### VAL-138 — In-progress merge/rebase detection

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/workflow/git.py:255-264`

The repository is considered to have an in-progress git operation if the .git directory contains rebase-merge/rebase-apply (rebase) or MERGE_HEAD (merge); this state gates several destructive commands elsewhere (e.g. publish-snapshot, already catalogued) from proceeding.

- **Given** a repository mid-rebase with .git/rebase-merge present
- **When** any caller checks in_progress_operation(cwd)
- **Then** the function returns the string 'rebase' (or 'merge' if MERGE_HEAD exists instead), else None when neither marker is present

### VAL-139 — Publish-snapshot refuses to push to a remote that resolves to the same URL as the primary remote

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/workflow/git.py:306-342;src/repo_release_tools/commands/git_sync.py:429-434`

Before force-pushing a snapshot, rrt compares the target remote's URL against the repository's configured primary remote (default 'origin') after normalizing both (stripping scheme, trailing .git, case-folding host, collapsing path traversal, handling SCP-style git@host:path syntax). If they resolve to the same repository, the push is refused to prevent accidentally overwriting the main history.

- **Given** Given primary remote 'origin' points to git@github.com:acme/repo.git and the user targets --remote 'https://github.com/acme/repo' as the snapshot destination
- **When** When primary_remote_conflict compares normalized URLs
- **Then** Then both normalize to 'github.com/acme/repo' and the command exits 1 with 'Refusing to publish: --remote ... resolves to the same URL as origin'
- **Parameters:** primary_remote defaults to 'origin' (src/repo_release_tools/config/core.py:103-119)
- **Edge case:** normalize_remote_url is used only for this equality guard, never for the actual push command, which always uses the raw configured/flag value
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### VAL-140 — Commit subject validation policy

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/workflow/hooks.py:117-141`

A commit subject must be non-empty and follow Conventional Commits format, except 'Merge ...' commits (always allowed) and 'fixup!'/'squash!' prefixed commits, which are validated against the rewritten subject after the prefix.

- **Given** commit subject 'fixup! feat: add parser'
- **When** validate_commit_subject('fixup! feat: add parser') is called
- **Then** returns None (valid) because the text after 'fixup! ' ('feat: add parser') parses as a conventional commit
- **Parameters:** allowed_types include CONVENTIONAL_TYPES plus 'deps' plus any project extra_types
- **Edge case:** empty subject -> 'Commit message is empty.'
- **Edge case:** a fixup!/squash! prefix whose rewritten body does NOT parse falls through to normal validation of the full original string, which will then fail
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory (This is a commit-message format linter enforced in a git hook / CI gate, not a compliance, financial, or data-integrity control. Reading src/repo_release_tools/workflow/hooks.py:117-141: validate_commit_subject() rejects empty subjects, always allows subjects starting with 'Merge ', special-cases 'fixup! '/'squash! ' prefixes by re-parsing the rewritten tex…

### VAL-141 — Commit subject validation accepts fixup!/squash! wrapped subjects

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/workflow/hooks.py:117-141`

A commit subject is valid if it is 'Merge '-prefixed, or a conventional-commit-formatted subject; subjects prefixed with 'fixup! ' or 'squash! ' are validated against the conventional-commit pattern of the text after the prefix.

- **Given** commit subject 'fixup! feat(cli): add parser'
- **When** validate_commit_subject runs
- **Then** the prefix is stripped and 'feat(cli): add parser' is parsed as a valid conventional commit, so the fixup subject passes validation
- **Parameters:** allowed_types = CONVENTIONAL_TYPES + 'deps' + extra_types

### VAL-142 — Commit subject validation: conventional commits, merge commits, and fixup!/squash! prefixes

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/workflow/hooks.py:117-141`

A commit subject is valid if it's empty-checked-first (empty always fails), starts with 'Merge ' (always allowed), starts with 'fixup! ' or 'squash! ' followed by a valid conventional-commit subject, or is itself a valid conventional-commit subject. Anything else is rejected with a list of allowed types.

- **Given** Given commit subject 'fixup! feat(cli): add hook installer'
- **When** When validate_commit_subject strips the 'fixup! ' prefix and re-parses the remainder
- **Then** Then the commit is accepted because 'feat(cli): add hook installer' parses as a valid conventional commit
- **Parameters:** allowed_types = CONVENTIONAL_TYPES + ('deps',) + extra_types
- **Edge case:** An empty subject fails with 'Commit message is empty.' before any other check
- **Edge case:** A 'fixup!'/'squash!' prefixed subject whose remainder still doesn't parse falls through to the standard conventional-commit check on the full original subject (which will also fail)
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### VAL-143 — Commit subject validation: Merge and fixup/squash prefixes bypass Conventional Commits

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/workflow/hooks.py:117-141`

Commit subjects starting with 'Merge ' are always accepted. Subjects starting with 'fixup! ' or 'squash! ' are accepted if the remainder after the prefix parses as a valid conventional commit.

- **Given** commit subject "fixup! feat(cli): add hook installer"
- **When** validate_commit_subject is called
- **Then** validation passes because the text after 'fixup! ' parses as a conventional commit
- **Edge case:** An empty subject always fails with 'Commit message is empty.'
- **Edge case:** 'squash! ' with a non-conventional remainder still falls through to require the full raw subject to parse

### VAL-144 — Conventional commit subject validation

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/workflow/hooks.py:117-141;src/repo_release_tools/changelog.py:12-29,65-84`

A commit subject must match Conventional Commits syntax (type(scope)!: description) using one of the allowed types, unless it is a Merge commit or fixup!/squash! commit whose rewritten form parses as conventional.

- **Given** Commit subject 'feat(cli): add hook installer'
- **When** validate_commit_subject is called
- **Then** Validation passes; a subject like 'added stuff' (no type prefix) fails with a message listing allowed types
- **Parameters:** Base types: feat|fix|docs|style|refactor|perf|test|build|ci|chore|deps (src/repo_release_tools/changelog.py:14)
- **Edge case:** 'Merge ...' subjects are always allowed
- **Edge case:** 'fixup! ...'/'squash! ...' subjects are allowed if the remainder parses as conventional
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### VAL-145 — Changelog update requirement by commit type

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/workflow/hooks.py:155-193`

A commit requires a changelog entry if it is a breaking change, or if its type maps to a changelog section other than 'Maintenance'. Maintenance-type commits (chore/ci/build/test/deps) never require a changelog update.

- **Given** commit subject 'ci: add Node 26 to test matrix'
- **When** commit_subject_requires_changelog is evaluated during pre-commit-changelog or check-changelog
- **Then** the function returns False because 'ci' maps to the 'Maintenance' section, so no changelog entry is required
- **Parameters:** SECTION_MAP (changelog.py:31-43)
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### VAL-146 — Changelog enforcement requirement is driven by commit type's changelog section, with breaking changes always required

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/workflow/hooks.py:155-193`

A commit is considered to 'require' a changelog update if it's marked breaking (always required, regardless of type), or if its conventional-commit type maps to a changelog section other than 'Maintenance' (chore/ci/build/test/deps commits do not require a changelog entry).

- **Given** Given commit subject 'chore: bump dependency versions'
- **When** When commit_subject_requires_changelog parses type='chore' (maps to Maintenance)
- **Then** Then the function returns False — no changelog update is required for this commit
- **Parameters:** SECTION_MAP (src/repo_release_tools/changelog.py:31-43)
- **Edge case:** A breaking chore commit ('chore!: ...') still requires a changelog entry despite chore normally mapping to Maintenance
- **Edge case:** branch_requires_changelog derives the same rule from the branch's <type> prefix rather than a parsed commit subject
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### VAL-147 — Branch changelog-requirement inference chains through commit-type-to-section mapping

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/workflow/hooks.py:155-193`

Whether a branch or commit needs a changelog update is derived transitively from its conventional-commit type: breaking-change commits always require one; other types require one only if their mapped changelog section is not 'Maintenance' (chore/ci/build/test/deps-mapped types are exempt).

- **Given** a branch named 'chore/upgrade-deps'
- **When** branch_requires_changelog() is evaluated
- **Then** returns False because 'chore' maps to the 'Maintenance' section, which is explicitly excluded from the changelog-required set
- **Parameters:** SECTION_MAP merged with any extra_section_map from config (hooks.py:164); Maintenance section name is the exemption sentinel (hooks.py:166)
- **Edge case:** breaking=True always forces True even if the type would otherwise map to Maintenance (hooks.py:162-163)
- **Edge case:** Branch types that fail normalize_commit_type validation (e.g. unknown/bot types) are treated as not requiring changelog rather than raising (hooks.py:181-184)

### VAL-148 — Branch naming policy: fixed allow-list, type/slug structure, release branches, and passthrough types

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/workflow/hooks.py:50-105`

A branch name passes validation if it is exactly 'main', 'master', or 'develop'; or matches 'release/v<semver>'; or has the form '<type>/<kebab-case-slug>' where type is a known conventional-commit type, an AI-helper type (claude/codex/copilot), a bot type (dependabot/renovate), or a configured extra_branch_types entry. Bot and extra_branch_types slugs skip kebab-case/length validation (they're externally generated and may include slashes/underscores); all other types require a non-empty, lowercase kebab-case slug of at most 60 characters.

- **Given** Given a branch named 'dependabot/npm_and_yarn/lodash-4.17.21'
- **When** When validate_branch_name checks the type_part 'dependabot' against BOT_BRANCH_TYPES
- **Then** Then the branch is accepted without kebab-case or length checks on the remaining slug
- **Parameters:** SLUG_MAX = 60 (src/repo_release_tools/commands/branch.py:108); ALLOWED_BRANCH_NAMES=(main, master, develop); MAGIC_BRANCH_TYPES=(claude, codex, copilot); BOT_BRANCH_TYPES=(dependabot, renovate)
- **Edge case:** A release branch with an unparseable semver suffix (e.g. release/vfoo) is explicitly rejected with a targeted message
- **Edge case:** A branch with no '/' at all is rejected as not matching <type>/<slug>
- **Edge case:** An empty branch_name string passes validation (returns None) — used when a branch can't be determined yet
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### VAL-149 — Branch name policy: allowed types, special names, and release branches

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/workflow/hooks.py:56-105`

A branch name must be one of the always-allowed names (main/master/develop), a release/v<semver> branch, or <type>/<kebab-slug> where type is a conventional type, AI-helper type (claude/codex/copilot), bot type (dependabot/renovate), or a configured extra type.

- **Given** Branch name 'release/v2.0.0'
- **When** validate_branch_name is called
- **Then** Validation passes (version parses as valid semver); a name like 'release/vX' fails with 'must use release/v<semver>'
- **Edge case:** Branch without '/' (and not a special name) is rejected
- **Edge case:** Bot/passthrough types (dependabot/renovate/extra_branch_types) skip slug format+length checks entirely
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### VAL-150 — Branch name validation state machine

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/workflow/hooks.py:56-105`

A branch name is valid if it is one of the reserved names (main/master/develop), matches 'release/v<semver>', or follows '<type>/<kebab-slug>' where type is a conventional type, an AI-helper type, a bot type, or a configured extra type; bot/extra-type branches skip slug format checks but must still have a non-empty slug, while conventional-type branches must satisfy a kebab-case regex and a max length.

- **Given** branch name 'dependabot/npm_and_yarn/lodash-4.17.21' (contains underscores/slashes not allowed in kebab-case)
- **When** validate_branch_name is called
- **Then** validation passes because 'dependabot' is a BOT_BRANCH_TYPES prefix, which skips the BRANCH_SLUG_RE and SLUG_MAX checks entirely
- **Parameters:** ALLOWED_BRANCH_NAMES=(main, master, develop); MAGIC_BRANCH_TYPES=(claude, codex, copilot); BOT_BRANCH_TYPES=(dependabot, renovate); SLUG_MAX=60; BRANCH_SLUG_RE=^[a-z0-9]+(?:-[a-z0-9]+)*$ (branch.py:108-110, hooks.py:50-105)
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### VAL-151 — Branch name validation: release/v<semver> exempt from type/slug rules

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/workflow/hooks.py:56-105`

A branch named release/v<version> is valid as long as the version part parses as semver; it bypasses the normal <type>/<kebab-slug> checks entirely. Bot branches (dependabot/renovate) and configured extra_branch_types skip slug format/length checks and only require a non-empty slug.

- **Given** branch name "release/v2.0.0-rc.1"
- **When** validate_branch_name is called
- **Then** validation passes (returns None) because "2.0.0-rc.1" parses via Version.parse, regardless of any kebab-case rules
- **Edge case:** "release/vNOTASEMVER" fails with a specific 'must use release/v<semver>' message
- **Edge case:** main/master/develop are always valid regardless of slash content
- **Edge case:** bot/extra-type branches allow slashes and underscores in the slug since they skip BRANCH_SLUG_RE

### VAL-152 — Working-tree dirty-check hook classification

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/workflow/hooks.py:578-602`

The dirty-tree pre-commit/CI gate fails distinctly for 'not a git repository' versus 'git repository with uncommitted changes', surfacing the specific changed entries in the failure message for the latter case.

- **Given** a working directory with 2 modified tracked files and no untracked files
- **When** run_dirty_tree_check() runs
- **Then** exit code 1 with message 'Working tree has uncommitted changes.' listing the 2 changed entries from git status --porcelain output
- **Parameters:** n/a
- **Edge case:** If cwd is not inside a git work tree at all, the check fails with a different message ('... is not inside a Git work tree') before even checking dirtiness (hooks.py:582-586)

### VAL-153 — Release branch name must embed a valid semver

**Category:** Validation · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/workflow/hooks.py:68-74`

Any branch starting with 'release/v' must have the remainder of its name parse as a valid semantic version, otherwise it fails validation.

- **Given** branch name 'release/vabc'
- **When** validate_branch_name checks a release/v-prefixed branch
- **Then** Version.parse raises ValueError and the function returns "Release branch 'release/vabc' must use release/v<semver>."
- **Parameters:** none
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### VAL-154 — Bot branches are exempt from changelog enforcement

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/workflow/hooks.py:814-819`

Commits made on branches whose type prefix is 'dependabot' or 'renovate' are always exempt from the changelog-update check, regardless of the configured strategy.

- **Given** branch 'dependabot/npm/lodash-4.17.21' and commit subject 'chore(deps): bump lodash to 4.17.21'
- **When** run_changelog_check evaluates the branch
- **Then** the check returns 0 immediately ('skipped (bot branch: ...)') without checking whether the changelog file changed
- **Parameters:** BOT_BRANCH_TYPES = (dependabot, renovate) (hooks.py:52)

### VAL-155 — Branch slug length and kebab-case format limits

**Category:** Validation · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/workflow/hooks.py:96-103;src/repo_release_tools/commands/branch.py:108-110`

For non-bot branch types, the slug portion after '/' must be lowercase kebab-case (letters, digits, hyphens only) and at most 60 characters.

- **Given** Branch slug of 61 characters, e.g. 'feat/a-very-long-description-that-exceeds-the-sixty-character-limit'
- **When** validate_branch_name is called
- **Then** Rejected with 'Branch slug ... is too long (61 > 60)'
- **Parameters:** SLUG_MAX = 60 (src/repo_release_tools/commands/branch.py:108)


## Policy rules (103)

### POL-001 — Action publish-snapshot composite kept isolated from main policy-check Action by trigger risk profile

**Category:** Policy · **Priority:** P1 · **Confidence:** Medium
**Source:** `/Users/hahn/LocalDocuments/GitHub_Forks/repo-release-tools/action.yml (main policy-check composite action, no force-push input) and /Users/hahn/LocalDocuments/GitHub_Forks/repo-release-tools/actions/publish-snapshot/action.yml (separate composite action definition containing the force-push step)`

The force-push snapshot-publishing capability is deliberately packaged as a separate GitHub Action (not a flag on the main read-only policy-check Action) so that destructive force-push behavior can only be triggered from workflows that explicitly opt into it (push-to-main/schedule/workflow_dispatch), never accidentally from a PR-triggered policy check run.

- **Given** a consuming repository's PR workflow uses only the main `Anselmoo/repo-release-tools@vX` action for branch/commit/changelog checks
- **When** any PR is opened
- **Then** no force-push can occur from that workflow, because publish-snapshot lives at a distinct action path (`.../actions/publish-snapshot@vX`) that must be referenced explicitly and separately
- **Parameters:** n/a
- **Edge case:** confirm input on the publish-snapshot action defaults to 'false', meaning even when explicitly wired in, it still only dry-runs unless a workflow author sets confirm: 'true' (action.py:172,180)
- ❓ **SME question:** Citation was corrected by referee (The cited lines src/repo_release_tools/integrations/action.py:138-150 are a Python triple-quoted string (GITHUB_ACTION_PUBLISH_SNAPSHOT_DOC) that is rendered into markdown documentation (see SOURCE_OWNED_TOPIC_DOCS mapping at action.py:196-199, and docs/src/content/docs/publish-snapshot-action.mdx). It is prose explaining the design rationale ("It is deliberately not part of the ma…

### POL-002 — GitHub Action changelog status three-way classification

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `action.yml:82-90,121-140`

The Action's health-summary output classifies changelog status as 'missing' (no file), 'clean' (file exists but no [Unreleased] bullets), or 'dirty' (file exists with at least one non-empty bullet under [Unreleased]).

- **Given** A CHANGELOG.md at the path configured by changelog-file, checked out by the composite Action
- **When** the 'Detect project version and changelog status' step runs
- **Then** changelog_status is 'missing' if the file does not exist; otherwise 'dirty' if a top-of-line '[Unreleased]' header is found and it has 1+ lines starting with '-', else 'clean'
- **Parameters:** grep anchor pattern: ^\[Unreleased\] (action.yml:130); bullet counter regex: ^\s*- (action.yml:132)
- **Edge case:** Changelog file missing entirely -> 'missing'
- **Edge case:** [Unreleased] header present but zero bullet lines -> 'clean'
- **Edge case:** Non-markdown (RST) changelog format is not accounted for by this grep-based check at all
- ⚠️ **Suspected defect:** The grep pattern is anchored ^\[Unreleased\] with no '##' prefix, but the repository's own CHANGELOG.md (and the standard Keep-a-Changelog format this tool otherwise enforces) uses '## [Unreleased]'. Verified: `grep -n '^\[Unreleased\]' CHANGELOG.md` returns no match against the real file, so for any standard-format changelog this step always falls through to changelog_status='clean' regardless of actual [Unreleased…

### POL-003 — Maintenance-type changelog entries are gated by include_maintenance when generating a release section

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/changelog.py:169-219`

When rrt generates a new changelog section from git history (rather than promoting an existing [Unreleased] section), commits of chore/ci/build/test/deps type are only included in the rendered output if the caller explicitly opts in via include_maintenance=True.

- **Given** Given commit subjects containing 3 'chore:' commits and 2 'feat:' commits, and include_maintenance=False
- **When** When build_changelog_section renders the section
- **Then** Then the Maintenance subsection is omitted entirely from the output even though matching entries were parsed; only the Added subsection (from feat commits) appears
- **Parameters:** SECTION_ORDER = [Breaking Changes, Added, Fixed, Changed, Documentation, Maintenance]
- **Edge case:** If no sections end up with entries at all (e.g. all commits were maintenance-only and include_maintenance=False), the output falls back to '_No notable changes recorded._'

### POL-004 — Breaking-change commits always route to Breaking Changes section

**Category:** Policy · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/changelog.py:184-192,426-432`

A conventional commit with the '!' breaking marker (e.g. 'feat!: drop legacy API') is always placed in the 'Breaking Changes' section regardless of its declared type, overriding the normal SECTION_MAP routing.

- **Given** a commit subject 'feat(api)!: remove deprecated endpoint'
- **When** the changelog section is built or a commit is appended to [Unreleased]
- **Then** the bullet '- **api**: remove deprecated endpoint' is placed under '### Breaking Changes', not '### Added'
- **Parameters:** none
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### POL-005 — Maintenance commits excluded from generated changelog by default

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/changelog.py:202-215; src/repo_release_tools/commands/bump.py:612-616`

Commits classified as Maintenance (chore, ci, build, test, deps) are omitted from the generated changelog section unless the operator explicitly opts in with --include-maintenance.

- **Given** git log since last tag contains only 'chore: bump deps' and 'ci: add matrix job'
- **When** build_changelog_section(..., include_maintenance=False) runs
- **Then** the generated section has no entries and renders '_No notable changes recorded._'
- **Parameters:** include_maintenance flag, default False
- **Edge case:** --include-maintenance renders the Maintenance subsection with those bullets

### POL-006 — Commit type maps to changelog section; Maintenance types are exempt

**Category:** Policy · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/changelog.py:31-43;src/repo_release_tools/workflow/hooks.py:155-193`

Each conventional commit type maps to a changelog section (feat->Added, fix->Fixed, refactor/perf/style->Changed, docs->Documentation); chore/ci/build/test/deps map to Maintenance and do NOT require a changelog entry unless the commit is marked breaking.

- **Given** Commit subject 'chore: bump ci runner image'
- **When** commit_subject_requires_changelog is evaluated
- **Then** Returns False (Maintenance-mapped types are exempt) unless the commit has a breaking '!' marker, in which case it always requires a changelog entry
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### POL-007 — Changelog commit-type to section mapping

**Category:** Policy · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/changelog.py:31-52`

Each conventional commit type is routed to a specific changelog section; chore/ci/build/test/deps commits land in 'Maintenance' and are excluded unless explicitly requested, while feat/fix/refactor/perf/style/docs map to Added/Fixed/Changed/Changed/Changed/Documentation respectively.

- **Given** a commit subject 'fix(cli): correct exit code' and a commit subject 'chore: bump deps'
- **When** `rrt bump` generates a new changelog section via build_changelog_section
- **Then** the fix commit appears under '### Fixed' while the chore commit is only included under '### Maintenance' if include_maintenance=True is passed
- **Parameters:** SECTION_MAP (changelog.py:31-43); SECTION_ORDER (changelog.py:45-52)
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### POL-008 — Changelog append: breaking commits always target the Breaking Changes subsection regardless of type

**Category:** Policy · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/changelog.py:426-432`

When appending an auto-generated bullet, if the parsed commit is marked breaking (e.g. 'feat!:' or has a BREAKING CHANGE footer), the bullet always goes into the 'Breaking Changes' subsection, overriding whatever section its commit type would normally map to.

- **Given** a commit "fix!: remove legacy config loader" (type=fix, breaking=true)
- **When** append_to_unreleased() renders the bullet
- **Then** the bullet is inserted under '### Breaking Changes', not under the 'Fixed' section that a non-breaking 'fix' commit would normally use
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### POL-009 — rrt tree --fix-empty-dirs: auto-resolve action takes precedence over --yes, which takes precedence over interactive prompt

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/_tree_fix.py:46-52,149-160,163-185`

When resolving phantom (untracked, empty) directories found by rrt tree, an invalid --auto-resolve value aborts the whole operation before any directory is touched; a valid --auto-resolve value (gitkeep/delete/hard/git-rm) is applied to every phantom directory without prompting and overrides --yes; --yes alone (without --auto-resolve) always adds .gitkeep without prompting; absent both flags, the user is prompted per-directory with a default of 'k' (gitkeep) if they just press enter.

- **Given** rrt tree --fix-empty-dirs --auto-resolve bogus
- **When** fix_empty_dirs runs
- **Then** the command reports 'Unknown --auto-resolve choice: 'bogus'.' and returns exit code 1 without evaluating any phantom directory

### POL-010 — Empty-directory fix: auto_resolve takes precedence over assume_yes; unset defaults to interactive prompt with 'gitkeep' as the blank-reply default

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/_tree_fix.py:46-52,149-186`

'rrt tree --fix-empty-dirs' resolves each phantom directory's action in this priority order: an explicit --auto-resolve choice (gitkeep/delete/hard/git-rm) always wins; otherwise --yes/assume_yes auto-picks 'gitkeep' for every directory without prompting; otherwise the user is prompted interactively, and a blank/non-interactive reply defaults to 'gitkeep' (add a .gitkeep placeholder), never to delete.

- **Given** both --yes and --auto-resolve delete are passed together
- **When** fix_empty_dirs resolves the action for each phantom directory
- **Then** every directory is deleted (auto_resolve wins over assume_yes)
- **Edge case:** an invalid --auto-resolve value (not in gitkeep/delete/hard/git-rm) fails the whole command before processing any directory
- **Edge case:** in non-interactive/CI stdin, ui.prompt.ask() returns the 'k' default, so unattended runs default to gitkeep, not skip or delete (src/repo_release_tools/ui/prompt.py:44-65)

### POL-011 — Generated Actions workflow pins the rrt Action to the running package version

**Category:** Policy · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/action_cmd.py:69-89`

The scaffolded GitHub Actions workflow always references Anselmoo/repo-release-tools@v<current-installed-rrt-version>, not a floating tag, so CI stays pinned to the toolchain version that generated it.

- **Given** rrt version 1.11.2 is installed
- **When** rrt action init writes the workflow file
- **Then** the generated YAML uses 'uses: Anselmoo/repo-release-tools@v1.11.2'

### POL-012 — GitHub Actions workflow init overwrite guard

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/action_cmd.py:92-122`

'rrt action init' refuses to overwrite an existing .github/workflows/rrt.yml unless --force is passed; --dry-run is always allowed regardless of whether the file exists.

- **Given** .github/workflows/rrt.yml already exists and neither --force nor --dry-run is passed
- **When** rrt action init runs
- **Then** the command exits 1 with 'rrt.yml already exists. Use --force to overwrite it.' and the file is not touched

### POL-013 — Agent/skill install: family expansion and overwrite guard

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/agents_cmd.py:130-220;src/repo_release_tools/commands/skill.py:147-182`

Requesting a single named agent that belongs to a 'family' installs every agent in that family, not just the one requested; installation is refused (exit non-zero, no writes) if any target destination already has a file for the requested agent/skill unless --force is passed, in which case the file is overwritten.

- **Given** BUNDLED_AGENTS includes agent 'reviewer' with family='code-quality' alongside sibling agent 'linter-agent' in the same family; user runs `--agent reviewer` without --force, and 'linter-agent.agent.md' already exists at the target
- **When** `rrt agents install --agent reviewer --target claude-local` runs
- **Then** Both 'reviewer' and 'linter-agent' are selected for install (family expansion), but the whole operation errors out because 'linter-agent.agent.md' already exists and --force was not given
- **Parameters:** n/a

### POL-014 — Artifacts check advisory-vs-strict exit policy

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/artifacts_cmd.py:137-156`

`rrt artifacts --check` reports hash drift as warnings and exits 0 by default (advisory); only with --strict does the same drift cause the messages to be treated as errors and the command to exit 1, making it suitable as a hard CI gate.

- **Given** Two artifact files have drifted from their locked hashes
- **When** `rrt artifacts --check` runs without --strict
- **Then** Both drift messages print as warnings, and the command exits 0 with an advisory note to run --snapshot
- **Parameters:** n/a

### POL-015 — Artifacts --check is advisory by default, hard-fails only with --strict

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/artifacts_cmd.py:137-156`

When tracked-artifact hashes don't match the committed lock, the check reports drift as warnings and exits 0 by default; only --strict turns any mismatch into a hard failure (exit 1), intended for CI gates.

- **Given** one artifact's hash no longer matches the lock file
- **When** rrt artifacts --check runs without --strict
- **Then** the mismatch is printed as an advisory warning and the command exits 0; with --strict it exits 1

### POL-016 — Artifact drift check is advisory unless --strict

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/artifacts_cmd.py:137-156`

Running `rrt artifacts --check` reports any hash mismatches from the committed artifact lock, but by default it still exits success (0); only `--check --strict` turns drift into a failing (exit 1) CI gate.

- **Given** an artifact target's current SHA-256 hash no longer matches the value recorded in .rrt/artifacts.lock.toml
- **When** `rrt artifacts --check` is run without --strict
- **Then** the mismatch is printed as an advisory warning and the command exits 0; running the same check with --strict exits 1
- **Parameters:** advisory flag: --strict (default False)
- **Edge case:** --dry-run only has effect when combined with --regenerate; using it with --check/--snapshot/--list is rejected with exit 1 (artifacts_cmd.py:104-110).

### POL-017 — Artifacts --regenerate only runs targets with a configured command

**Category:** Policy · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/artifacts_cmd.py:162-199`

During --regenerate, only artifact_targets entries that declare a 'command' are executed; targets without a command are silently skipped. If zero targets have commands, nothing runs and the lock is not rewritten.

- **Given** 3 configured artifact_targets, only 1 has a 'command'
- **When** rrt artifacts --regenerate runs
- **Then** only that 1 target's command executes, then the lock is re-snapshotted for all targets; the other 2 are untouched but still included in the new snapshot's hash set
- ❓ **SME question:** When --regenerate finds zero targets with a command, should the run still succeed (exit 0) with a no-op message, or should it be treated as a misconfiguration error?

### POL-018 — Changelog update mode resolution

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/bump.py:152-156,168-269`

How the changelog is written during a bump depends on the workflow: 'auto' promotes existing [Unreleased] entries if present, otherwise generates a section from git log since the last tag; 'promote' requires existing entries or aborts with a message; 'generate' always builds fresh from git log, ignoring [Unreleased].

- **Given** changelog_mode='promote' and the [Unreleased] section is empty
- **When** update_changelog(..., changelog_mode='promote') runs
- **Then** no file is written; a message is printed: '[Unreleased] section in <path> is empty — nothing to promote.' and the function returns without failing the whole bump
- **Parameters:** changelog_mode default resolution: 'generate' if config.changelog_workflow == 'squash' else 'auto' (bump.py:152-156)
- **Edge case:** missing changelog file entirely -> skip with 'not found — skipping', not a hard failure
- **Edge case:** generate mode always uses commits since the most recent git tag (git_log_since_latest_tag), or full HEAD history if no tags exist

### POL-019 — Changelog write mode selection at bump time (auto/promote/generate)

**Category:** Policy · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/bump.py:152-268`

At release time, 'auto' mode promotes a non-empty [Unreleased] section to the new version heading, or generates a fresh section from git log if [Unreleased] is empty; 'promote' requires a non-empty [Unreleased] section and fails otherwise; 'generate' always builds from git history, ignoring [Unreleased].

- **Given** changelog_mode='promote' and the [Unreleased] section has no bullet entries
- **When** update_changelog runs during rrt bump
- **Then** The function prints a warning ('nothing to promote') and returns without modifying the changelog file
- **Parameters:** resolve_changelog_mode default: 'generate' if changelog_workflow=='squash' else 'auto' (src/repo_release_tools/commands/bump.py:152-156)
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### POL-020 — Changelog mode selection at bump time

**Category:** Policy · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/bump.py:152-269`

The changelog update mode defaults to 'generate' when the workflow is 'squash' and 'auto' otherwise (unless explicitly overridden). In 'auto' mode, an [Unreleased] section with entries is promoted to the new version heading; an empty or missing section instead triggers generation of a new section from git log since the latest tag. In 'promote' mode, an empty [Unreleased] section aborts the update with a warning rather than promoting nothing.

- **Given** changelog_workflow='incremental' (default) and the changelog's [Unreleased] section has zero bullet entries
- **When** `rrt bump patch` runs with the default changelog_mode='auto'
- **Then** do_promote resolves to False (has_entries=False), so a new changelog section is generated fresh from `git log <last-tag>..HEAD` instead of promoting the empty placeholder
- **Parameters:** resolve_changelog_mode: 'generate' if changelog_workflow=='squash' else 'auto' (bump.py:152-156)
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### POL-021 — Changelog lint exit-code policy

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/changelog_lint.py:222-242`

The lint command exits 1 when any violation is found, unless the caller passed --no-fail, in which case violations are printed but the command exits 0 (useful for advisory CI runs).

- **Given** 5 lint violations found and --no-fail is passed
- **When** `rrt changelog lint --no-fail` runs
- **Then** All 5 violations are printed to stderr and the process exits with code 0
- **Parameters:** --no-fail flag; default exit code 1 on any violation

### POL-022 — Changelog lint exit code and --no-fail override

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/changelog_lint.py:222-242`

The lint command exits non-zero when any violation is found unless --no-fail is passed, in which case violations are only reported (advisory) and the command exits 0.

- **Given** 3 lint violations found
- **When** rrt changelog lint runs without --no-fail
- **Then** the command exits 1 and prints "3 changelog lint violation(s). Fix entries or use --no-fail."; with --no-fail it exits 0 with the same violations printed as warnings

### POL-023 — Badge assets URL rewritten from physical docs/public path to site-relative base URL only for SVG badge style

**Category:** Policy · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/docs_cmd.py:343-372`

When embedding platform badges in generated docs, the physical docs/public/... prefix used on disk is stripped and replaced with the site's configured base_url only if badge_style is 'svg'; other badge styles (e.g. shields.io URLs) use badge_assets_dir unmodified.

- **Given** docs.badge_style = 'svg', docs.badge_assets_dir = 'docs/public/assets/badges', docs.base_url = '/repo-release-tools'
- **When** _badge_assets_dir_for_target computes the embedded badge path
- **Then** the rendered badge image path is '/repo-release-tools/assets/badges', not the raw 'docs/public/assets/badges' filesystem path

### POL-024 — docs map file merge: 'error' mode refuses to inject into a foreign file lacking the anchor

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/docs_map.py:190-233`

When applying a generated purpose-doc block to an existing README that does not already contain the rrt anchor markers, on_conflict='error' refuses to modify the file (raises), on_conflict='skip' leaves it untouched, and on_conflict='merge' inserts the anchored block by appending it.

- **Given** a README.md exists with hand-written content and no rrt:auto anchor, and on_conflict='error'
- **When** rrt docs map runs
- **Then** a ValueError is raised: "<path> exists without the 'rrt-docs-map' anchor; set on_conflict='merge' to inject it, or remove the file." and no file is modified

### POL-025 — Docs-map on_conflict resolution modes

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/docs_map.py:190-260`

When applying a generated purpose-doc block to an existing README, the tool skips the file entirely under 'skip' mode, raises an error under 'error' mode if the file lacks the anchor markers, and otherwise merges/injects the anchor and replaces only the content between anchors, leaving surrounding prose untouched.

- **Given** An existing README.md without the `rrt-docs-map` anchor and `on_conflict='error'`
- **When** `rrt docs map` runs against that directory
- **Then** A ValueError is raised instructing the user to use `on_conflict='merge'` or remove the file; no write occurs
- **Parameters:** on_conflict modes: skip | error | merge (default write behavior otherwise appends anchor stub)

### POL-026 — docs map target directories must directly contain a recognized source file

**Category:** Policy · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/docs_map.py:65-103`

A directory under the configured docs.map.root is only eligible to receive a generated purpose doc if it directly contains at least one file with a recognized source extension (after applying ignore-dir, include, and exclude glob filters); directories containing only subdirectories or non-source files are skipped.

- **Given** src/foo/ contains only a subdirectory src/foo/bar/ with .py files, and src/foo/ itself has no source files directly in it
- **When** rrt docs map runs with root='src'
- **Then** src/foo/bar/ receives a generated README.md but src/foo/ does not (unless it separately has source files)
- ❓ **SME question:** Confirm the exact set of '_SOURCE_EXTENSIONS' recognized — should directories with only config/docs files (no code) ever be excluded from doc-map generation?

### POL-027 — Docstring-suggest scaffold applies only to a top-level string literal or is inserted after shebang/coding-comment lines

**Category:** Policy · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/docs_suggest.py:135-165`

When applying a docstring scaffold with --apply, if the module already starts with a string-literal expression it is replaced in place; otherwise the scaffold is inserted after a leading shebang line and after any '# ... coding ...' comment lines.

- **Given** a Python file with a shebang line but no existing module docstring
- **When** rrt docs suggest --apply runs on that file
- **Then** the scaffold is inserted as the second line (after the shebang), not at line 1

### POL-028 — Docstring-suggestion threshold: module docstrings under 150 chars or single-line are flagged

**Category:** Policy · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/docs_suggest.py:40-41,167-196`

rrt docs suggest flags a Python module as needing a richer docstring if it has no docstring at all, its docstring has no newline (i.e. is a single flat line), or its docstring is shorter than a configurable minimum character count (default 150). Files named __init__.py/__main__.py, or containing the literal marker 'rrt:docs-exempt', are always skipped.

- **Given** a module with docstring "Does the thing." (16 chars, single line)
- **When** rrt docs suggest scans it with default settings
- **Then** it is flagged with reason "docstring is too short or too flat"
- **Parameters:** DEFAULT_MIN_CHARS = 150 (src/repo_release_tools/commands/docs_suggest.py:40); EXEMPT_FILES = {__init__.py, __main__.py} (line 41)

### POL-029 — Docstring-suggest exemption via inline marker or filename

**Category:** Policy · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/docs_suggest.py:41,79-84`

A Python module is skipped by the docstring-suggestion scanner if its filename is __init__.py or __main__.py, or if the literal text 'rrt:docs-exempt' appears anywhere in the file.

- **Given** a module containing the comment '# rrt:docs-exempt' with only a one-line docstring
- **When** rrt docs suggest scans the file
- **Then** the file is skipped and no finding is reported for it, regardless of docstring length

### POL-030 — Health snapshot check exit code depends on --strict

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/doctor.py:355-371`

When comparing current health checks to the saved snapshot, regressions are only build-breaking (exit 1) if --strict is passed; otherwise they are printed as warnings and the command still exits 0.

- **Given** `rrt doctor --check` detects one or more health regressions
- **When** the command is run without --strict
- **Then** the command prints the regressions and exits 0 (advisory only); with --strict it exits 1
- **Parameters:** none (boolean flag)

### POL-031 — Doctor health-regression check severity gate

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/doctor.py:355-371`

`rrt doctor --check` compares current core-automation check results against the committed health lock; regressions are only advisory (exit 0 with a warning) unless --strict is passed, in which case any regression fails the command (exit 1).

- **Given** the lefthook integration check regresses from 'ok' to 'warning' compared to the committed health.lock.toml
- **When** `rrt doctor --check` runs without --strict
- **Then** the regression is printed as a warning but the command exits 0; with --strict it exits 1 and instructs the user to run `rrt doctor --snapshot`
- **Parameters:** n/a

### POL-032 — Drift lockfile tracked agent-surface glob patterns

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/drift_cmd.py:77-110`

Only files matching a fixed set of glob patterns are tracked by `rrt drift` for agent-surface integrity: Claude settings/hooks, Copilot instructions, GitHub skill docs, and GitHub agent definitions; each matched file's content is hashed and recorded once (deduplicated by relative path) in the lockfile.

- **Given** Repo has `.claude/settings.json`, `.claude/hooks/pre_commit.py`, and an unrelated `scripts/deploy.py`
- **When** `rrt drift generate` runs
- **Then** Only the two `.claude/*` files are hashed and written to drift.lock.toml; `scripts/deploy.py` is never tracked because it matches none of the DRIFT_SURFACE_PATTERNS
- **Parameters:** DRIFT_SURFACE_PATTERNS = {.claude/settings.json, .claude/hooks/*.py, .github/agents/*.agent.md, .github/copilot-instructions.md, .github/instructions/*.md, .github/skills/*/SKILL.md}

### POL-033 — Drift lock: track only a fixed set of agent-surface glob patterns, de-duplicated

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/drift_cmd.py:77-110`

The agent-surface drift lock only tracks files matching six hardcoded glob patterns (Claude settings/hooks, Copilot instructions, GitHub skills, agent definitions); if the same relative path is matched by more than one pattern it is only hashed once.

- **Given** a repo with .claude/settings.json, .claude/hooks/pre-commit.py, and .github/copilot-instructions.md
- **When** rrt drift generate runs
- **Then** the lock records exactly those 3 files (sorted by relative path), each hashed once, and any other agent-related file (e.g. a custom prompt outside these globs) is ignored
- **Parameters:** DRIFT_SURFACE_PATTERNS: .claude/settings.json, .claude/hooks/*.py, .github/agents/*.agent.md, .github/copilot-instructions.md, .github/instructions/*.md, .github/skills/*/SKILL.md (src/repo_release_tools/commands/drift_cmd.py:77-84)

### POL-034 — EOL check exit code depends on allow_eol override

**Category:** Policy · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/eol_check.py:319-390`

`rrt eol` fails (exit 1) if any host runtime or project minimum status resolves to 'error'. If allow_eol=True (via CLI flag or config), an otherwise-failing result is downgraded to a warning and the command exits 0 instead.

- **Given** the host Python runtime is past its EOL date (status='error') and allow_eol is not set
- **When** `rrt eol` runs
- **Then** the command prints 'One or more EOL checks failed.' and exits 1; if allow_eol=True, it instead prints 'EOL issues found but allow_eol=true — treating as warning only.' and exits 0
- **Parameters:** allow_eol default=False
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### POL-035 — Commit type inference from current branch name

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/git_commit.py:58-90`

'rrt git commit' without --type infers the conventional commit type from the current branch name's <type>/ prefix, but only when the branch is not a magic/special name, not a release/vX.Y.Z branch, not a bot-owned branch type, and the prefix is one of the recognized conventional commit types; otherwise the caller must pass --type explicitly.

- **Given** current branch is 'fix/handle-empty-config'
- **When** rrt git commit "handle empty config" runs without --type
- **Then** the commit subject is rendered as 'fix: handle empty config'
- **Edge case:** branch 'release/v1.2.3' never infers a type (must use --type)
- **Edge case:** branch with no '/' (e.g. 'main') never infers a type
- **Edge case:** bot/magic branch type prefixes (e.g. dependabot/renovate) never infer a type

### POL-036 — rebootstrap requires explicit destructive confirmation and blocks conflicting flags

**Category:** Policy · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/git_sync.py:235-266`

rrt git rebootstrap (which destroys and reinitializes git history) requires --yes-i-know-this-destroys-history; it refuses to combine --hard-init with --empty-first; and it refuses to run when the repository has configured remotes unless --allow-remote is passed.

- **Given** --yes-i-know-this-destroys-history is omitted
- **When** cmd_rebootstrap runs
- **Then** Command exits 1 with 'Refusing to destroy repository history without --yes-i-know-this-destroys-history.'
- **Edge case:** --hard-init and --empty-first together also exit 1
- **Edge case:** Existing remotes without --allow-remote also exit 1
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### POL-037 — rrt git rebootstrap: default commit message depends on --hard-init vs snapshot mode

**Category:** Policy · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/git_sync.py:268-274`

If no explicit --message is given, rebootstrap uses 'chore: bootstrap repository' for an empty hard-init and 'chore: initial commit' when snapshotting current files.

- **Given** rrt git rebootstrap --yes-i-know-this-destroys-history --hard-init (no --message)
- **When** the new history is created
- **Then** the commit message used is 'chore: bootstrap repository'

### POL-038 — publish-snapshot requires explicit destructive confirmation flag

**Category:** Policy · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/git_sync.py:446-457,679-683`

Force-pushing a snapshot to a remote only actually executes when --yes-i-know-this-overwrites-remote-history is passed; otherwise the command runs in preview/dry-run mode regardless of --dry-run.

- **Given** --yes-i-know-this-overwrites-remote-history is omitted
- **When** cmd_publish_snapshot runs
- **Then** dry_run is forced to True; a warning is printed ('Refusing to push without ...') and only a preview is shown — no git push occurs
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### POL-039 — Publish-snapshot CLI requires an explicit destructive-confirmation flag or it silently downgrades to dry-run

**Category:** Policy · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/git_sync.py:446-503`

The `rrt git publish-snapshot` command, which force-pushes a single orphan commit overwriting a remote branch's history, only performs the destructive push when --yes-i-know-this-overwrites-remote-history is passed. Otherwise (even without --dry-run) it behaves as a dry-run preview.

- **Given** Given a user runs `rrt git publish-snapshot --remote backup --branch main` without the confirmation flag
- **When** When cmd_publish_snapshot evaluates `confirmed = bool(args.yes_i_know_this_overwrites_remote_history)`
- **Then** Then dry_run is forced True (`dry_run = args.dry_run or not confirmed`) and a warning is printed instead of pushing
- **Parameters:** n/a
- **Edge case:** Even in confirmed mode, cleanup (restoring the original branch, deleting the temp branch) always runs in a finally block and failures there are only warned, not fatal
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### POL-040 — Hook install dispatch by target surface

**Category:** Policy · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/hooks_cmd.py:179-180,473-480`

Which JSON merge strategy is used for hook registration is decided purely by the surface prefix of the target name (text before the first '-'): 'copilot' targets use the Copilot merge strategy; every other surface (claude, codex, gemini) uses the grouped-hooks merge strategy.

- **Given** target = 'copilot-global'
- **When** _merge_managed_registration is called
- **Then** _merge_copilot_hooks is used; for target = 'claude-global', 'codex-local', or 'gemini-local', _merge_grouped_hooks is used instead

### POL-041 — Hook registration merge: grouped-hooks dedup by exact command string per matcher

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/hooks_cmd.py:387-433`

When merging newly generated hook entries into an existing grouped hook-manager config (e.g. Claude Code settings.json style), a hook group is matched by its 'matcher' value, and within a matching group, individual hook commands are only added if no existing hook in that group already has the identical 'command' string.

- **Given** an existing hook group for matcher 'pre-commit' already contains a hook with command 'rrt-hooks pre-commit'
- **When** the same managed hook is regenerated and merged again
- **Then** no duplicate entry is appended; the existing group is left with one 'rrt-hooks pre-commit' entry

### POL-042 — Hook registration merge: Copilot-style dedup by (matcher, bash, command) signature

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/hooks_cmd.py:436-470`

For the Copilot hook-manager surface, merging uses a different dedup key than the grouped-hooks surface: the 3-tuple of (matcher, bash, command) must be identical for an entry to be treated as a duplicate; the merged file's schema 'version' field is forced to 1.

- **Given** an existing Copilot hooks.json with one entry for event 'pre-commit' with matcher='*', bash='sh', command='rrt-hooks pre-commit'
- **When** a new entry with the same matcher/bash/command is merged
- **Then** it is skipped as a duplicate; a different bash interpreter for the same matcher/command would NOT be treated as a duplicate and would be appended
- **Edge case:** merged['version'] is always overwritten to 1, discarding any pre-existing version value in the file

### POL-043 — rrt install: --dry-run with no --target lists available targets instead of failing

**Category:** Policy · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/install_cmd.py:132-138`

Running rrt install with no --target specified normally fails with a usage error, except when --dry-run is also passed, in which case it instead prints the available targets per surface and exits 0.

- **Given** rrt install --dry-run with no --target
- **When** the command runs
- **Then** it prints a table of available targets by surface and exits 0, rather than the "No --target specified" error

### POL-044 — rrt install surface expansion via 'all'

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/install_cmd.py:97-99`

The unified `rrt install` command treats an omitted or explicit '--surface all' as shorthand for installing every bundled surface (skill, agents, hooks) rather than just a default subset.

- **Given** the user runs `rrt install --target claude-local` with no --surface flag
- **When** surfaces are resolved for the install plan
- **Then** all three surfaces (skill, agents, hooks) are installed to claude-local; the same happens if --surface all is passed explicitly, and duplicates across multiple --surface flags are removed while preserving first-seen order

### POL-045 — Pin target rewrite skip on non-matching pattern (repair mode)

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/release_repair.py:558-579`

During repair, a pin target file that exists but whose regex pattern does not match anywhere in the file is silently skipped rather than raising an error, deliberately differing from `rrt bump`'s default 'error' policy for missing pin matches, so an unrelated non-matching pin file never blocks a repair.

- **Given** a configured pin target pattern that no longer matches docs/README.md content
- **When** _rewrite_matching_pins runs during `rrt release repair --yes`
- **Then** that pin file is left untouched and does not appear in the drift list nor raise a RuntimeError, unlike `rrt bump` under pin_target_missing='error'
- **Parameters:** repair always treats no-match as non-drift, bypassing config.pin_target_missing

### POL-046 — Release repair backup ref naming

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/release_repair.py:605-616`

Before any destructive recreate operation, a backup ref is written pointing at the current HEAD, named using the current branch (slashes replaced with dashes) and a UTC timestamp, so history can be recovered even if the repair goes wrong.

- **Given** current branch is release/v1.2.0 and the time is 2026-07-10T12:00:00Z
- **When** _make_backup_ref runs during recreate mode
- **Then** a ref refs/heads/repair/backup/release-v1.2.0-20260710T120000 is created pointing at HEAD before any rewrite happens

### POL-047 — Release repair commit subject depends on hotfix flag and mode

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/release_repair.py:619-625`

The commit message used for a repair commit follows a priority order: if --hotfix is passed, the subject is always 'chore(release): repair vX.Y.Z' regardless of mode; otherwise, recreate mode uses 'chore: bump version to vX.Y.Z' (matching a normal bump commit) while verify-and-fix mode uses 'chore(release): repair vX.Y.Z'.

- **Given** mode='recreate', hotfix=False, version='2.1.0'
- **When** _commit_message is called
- **Then** the resulting commit subject is 'chore: bump version to v2.1.0'; the same call with hotfix=True instead produces 'chore(release): repair v2.1.0' regardless of mode

### POL-048 — Tag check: missing expected tag is a warning unless --strict

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/tag.py:216-226`

If the tag for the current configured version doesn't exist yet, rrt tag check reports it as a non-fatal informational line by default; with --strict it becomes a hard failure (exit 1), which is intended for CI gates.

- **Given** current version is 2.0.0 and no v2.0.0 tag exists yet
- **When** rrt tag check runs without --strict
- **Then** the command prints the missing-tag notice but still exits 0 (unless other errors like prefix mismatches exist); with --strict it exits 1

### POL-049 — Tree structure drift check is advisory by default, hard-fails only with --strict

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/tree.py:755-771,900-909`

Running `rrt tree --check` reports structural drift against the saved snapshot but exits successfully (0) unless --strict is passed, in which case drift causes a failing exit code (1). Separately, `--strict-empty-dirs` independently fails the command whenever any phantom empty directory exists, regardless of --check/--strict.

- **Given** Given the tree lockfile records 42 entries but the working tree now has 45
- **When** When `rrt tree --check` runs without --strict
- **Then** Then drift is printed as a warning and the command exits 0; with --strict it exits 1
- **Parameters:** n/a
- **Edge case:** --strict-empty-dirs is evaluated before --check/--snapshot and can fail the command even when --check was not requested

### POL-050 — --compressed implies --manifest for tree manifest generation

**Category:** Policy · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/tree.py:914-919`

Requesting a compressed tree manifest automatically also turns on manifest generation, so the user doesn't need to pass both flags.

- **Given** Given `rrt tree --compressed` without --manifest
- **When** When cmd_tree processes the flags
- **Then** Then do_manifest is forced True and .rrt/tree.manifest.json.gz is written
- **Parameters:** n/a

### POL-051 — Lock-command/lockfile ecosystem auto-detection priority

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/config/core.py:761-798`

When no explicit lock_command/generated_files is configured, rrt infers the package manager for JS/TS projects by checking for lockfiles in priority order pnpm > yarn > npm, infers Poetry lock for python-poetry targets, infers Cargo lock when Cargo.toml/*.rs targets exist, and infers `go mod tidy` when go.mod/*.go targets exist.

- **Given** A repo with both `pnpm-lock.yaml` and `package-lock.json` present, and a package_json version target
- **When** rrt auto-detects the lock command
- **Then** It selects `["pnpm", "install"]` with generated file `pnpm-lock.yaml`, ignoring the npm lockfile, per the pnpm > yarn > npm priority order
- **Parameters:** priority order: pnpm > yarn > npm for JS/TS; poetry lock for python-poetry; cargo update --workspace for rust; go mod tidy for go

### POL-052 — Docs shared_blocks template field is deprecated

**Category:** Policy · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/config/docs_config.py:332-361`

A shared_blocks entry may still reference an external 'template' file for backward compatibility, but doing so emits a DeprecationWarning steering users to migrate to inline 'content'; the template file's content is only used as a fallback when 'content' is not also given.

- **Given** a shared_blocks[0] entry sets template='./partial.md' and no content
- **When** the docs config is loaded
- **Then** a DeprecationWarning is emitted and the block's content becomes the text read from './partial.md'; if the template file cannot be read, loading fails with a ValueError

### POL-053 — EOL policy configuration defaults

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/config/docs_config.py:37-97`

When [tool.rrt.eol] is not fully specified, EOL tracking defaults to checking only Python, warns starting 180 days before end-of-life, treats a language as errored only once actually past EOL (error_days=0), never fetches live endoflife.date data unless enabled, and does not allow EOL runtimes to pass health checks unless explicitly allowed.

- **Given** a repo with no [tool.rrt.eol] table, or one that omits warn_days/error_days/fetch_live/allow_eol
- **When** `rrt eol` or the health snapshot evaluates a language's EOL status
- **Then** languages defaults to ['python'], warn_days defaults to 180, error_days defaults to 0, fetch_live defaults to false (uses bundled data only), and allow_eol defaults to false (EOL runtimes fail the check)
- **Parameters:** warn_days=180, error_days=0, fetch_live=False, allow_eol=False, languages=['python']

### POL-054 — Folder policy mode default

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/config/folders_config.py:17-37`

When [tool.rrt.folders] is configured but no top-level 'mode' is set, the folder policy defaults to 'strict' rather than a more permissive mode, meaning unexpected entries are flagged by default once folder policy is enabled at all.

- **Given** [tool.rrt.folders] table present with only 'rules' and no 'mode' key
- **When** config is loaded
- **Then** FolderPolicyConfig.mode resolves to 'strict'
- **Parameters:** default mode = 'strict'

### POL-055 — Project manifest metadata precedence: pyproject.toml > Cargo.toml > package.json, PEP 621 over Poetry

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/config/project_meta.py:52-114`

'rrt project info' reads project metadata from the first manifest found in a fixed search order (pyproject.toml, then Cargo.toml, then package.json); within pyproject.toml, PEP 621 [project] metadata is preferred and legacy [tool.poetry] is only used as a fallback when [project] is absent.

- **Given** a repo has both pyproject.toml (with [tool.poetry] but no [project] table) and Cargo.toml
- **When** rrt project info runs
- **Then** metadata comes from pyproject.toml's [tool.poetry] block (Cargo.toml is never consulted, since pyproject.toml is found first and produces non-empty metadata via the poetry fallback)

### POL-056 — Project metadata manifest and field precedence

**Category:** Policy · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/config/project_meta.py:52-156`

Project metadata (name, version, description, authors, license, urls) is read from the first manifest found in fixed search order pyproject.toml (PEP 621 [project] first, [tool.poetry] as fallback), then Cargo.toml, then package.json; only the first matching manifest's data is used, never merged across files.

- **Given** A repo with both a pyproject.toml containing only [tool.poetry] (no [project] table) and a package.json
- **When** `load_project_metadata` runs
- **Then** Metadata comes from the [tool.poetry] block of pyproject.toml; package.json is never consulted because pyproject.toml was found first
- **Parameters:** manifest search order: pyproject.toml (PEP621 > poetry) > Cargo.toml > package.json

### POL-057 — Doc extraction dedup: first-registered entry name wins per file

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/docs/extractor.py:692-734`

Within a single source file, doc entries are extracted in a fixed priority order — SOURCE_OWNED_TOPIC_DOCS (Python only) first, then explicit '# sym:' markers, then implicit language-native docstrings/comments — and once a given entry name has been captured, later extraction passes for the same name in that file are silently skipped rather than overwriting it.

- **Given** a Python file has both an explicit '# sym: config' marker above a string assignment AND a function named config() with a docstring
- **When** extract_docs runs with extraction_mode='both'
- **Then** only the explicit-marker content for 'config' is kept; the implicit docstring for the same name is discarded because the name was already seen

### POL-058 — EOL override date resolution

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/eol/core.py:195-211,275-283`

A project can override the bundled/live EOL date for a specific language+cycle via config; when present, the override date is used instead of the standard record's EOL date, evaluated with the same warn_days/error_days thresholds.

- **Given** override configured for language='python', cycle='3.9', eol='2026-06-01', evaluated on today=2026-07-10
- **When** check_eol_status('3.9.18', ..., overrides=[override]) runs
- **Then** days_until = (2026-06-01 - 2026-07-10).days = -40, which is < error_days(0), so status is 'error' (or 'warn' if allow_eol=True)
- **Parameters:** [[tool.rrt.eol.overrides]] language, cycle, eol (ISO date string)
- **Edge case:** an override with an unparsable ISO date silently returns None from resolve_override_eol and falls through to standard record-based logic

### POL-059 — Rust rolling-release lag-based EOL model

**Category:** Policy · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/eol/core.py:222-228,285-292; src/repo_release_tools/eol/data.py:3-4`

Rust has no fixed EOL dates; instead, a detected Rust version is compared to the latest stable release by position — 2 or more releases behind triggers a warning, 4 or more releases behind triggers an error. These thresholds are fixed in code, not configurable per project.

- **Given** the latest stable Rust release is at index 0 in records, and the detected cycle is 4 positions behind
- **When** check_eol_status(version, records, language='rust') runs with slug=='rust'
- **Then** lag == 4 >= RUST_ERROR_LAG, so status is 'error' (or 'warn' if allow_eol=True)
- **Parameters:** RUST_WARN_LAG = 2; RUST_ERROR_LAG = 4 (eol/data.py:3-4)
- **Edge case:** lag==2 or 3 -> 'warn'; lag<2 -> 'ok'
- **Edge case:** warn_days/error_days config values are ignored entirely for Rust (lag-based, not date-based) per the module docstring at eol/core.py:32-42
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### POL-060 — Rust rolling-release lag-based status (non-configurable thresholds)

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/eol/core.py:222-229,286-292`

Rust has no EOL dates; instead, its status is based on how many stable releases behind the latest the detected version is ('lag'). A lag of 4 or more is 'error' (or 'warn' if allow_eol=True); a lag of 2 or 3 is 'warn'; a lag of 0-1 is 'ok'. These lag thresholds are hardcoded and not configurable via [tool.rrt.eol].

- **Given** the detected Rust version is 4 stable releases behind the latest, and allow_eol=False
- **When** check_eol_status evaluates the Rust cycle
- **Then** the status is 'error' because lag (4) >= RUST_ERROR_LAG (4)
- **Parameters:** RUST_WARN_LAG=2, RUST_ERROR_LAG=4 (src/repo_release_tools/eol/data.py:3-4) — explicitly documented as non-configurable in eol/core.py:41-42

### POL-061 — Rust rolling-release lag-based EOL thresholds

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/eol/core.py:222-229,286-292;src/repo_release_tools/eol/data.py:3-4`

Rust has no EOL dates (rolling release); instead, status is based on how many stable releases behind the detected version is from the latest: 2+ releases behind is a warning, 4+ releases behind is an error (or warning if allow_eol is set). This threshold is hardcoded and not configurable via [tool.rrt.eol].

- **Given** Detected Rust version is 3 releases behind the latest stable
- **When** check_eol_status is called for language='rust'
- **Then** Status is 'warn' (lag=3, which is >= RUST_WARN_LAG=2 but < RUST_ERROR_LAG=4)
- **Parameters:** RUST_WARN_LAG = 2, RUST_ERROR_LAG = 4 (src/repo_release_tools/eol/data.py:3-4)

### POL-062 — EOL status classification (date-based languages)

**Category:** Policy · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/eol/core.py:231-303`

For date-based EOL languages (Python, Go, Node.js), a version's status is 'ok' if it has no known EOL date, 'error' if it is already past its EOL date or has fewer days remaining than error_days, 'warn' if it has fewer days remaining than warn_days but more than error_days, and 'ok' otherwise. When allow_eol=True, what would be 'error' downgrades to 'warn' instead.

- **Given** warn_days=180, error_days=0, and a Python cycle's eol_date is 45 days in the future
- **When** check_eol_status evaluates the detected version
- **Then** the status is 'warn' because days_until_eol (45) is <= warn_days (180) but > error_days (0)
- **Parameters:** warn_days default=180; error_days default=0; allow_eol default=False (eol/core.py:236-238)
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### POL-063 — EOL override date takes precedence over bundled/live data

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/eol/core.py:275-283`

If a configured EolOverride exists for the language+cycle, its date is used to compute days-until-EOL instead of the record's real eol_date from bundled or live data, using the same warn/error threshold logic.

- **Given** a configured override sets python 3.9's EOL to '2026-06-01', overriding the bundled data's real EOL date
- **When** check_eol_status evaluates a detected '3.9.x' version
- **Then** days_until is computed as (2026-06-01 - today).days, ignoring the bundled record's actual eol_date entirely
- **Parameters:** none

### POL-064 — EOL status thresholds (date-based languages)

**Category:** Policy · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/eol/core.py:294-303`

For date-based EOL languages (Python, Go, Node), a detected version is 'error' once its EOL date has passed or is within error_days, 'warn' once it is within warn_days of EOL, and 'ok' otherwise; allow_eol downgrades a hard error to a warning instead of failing.

- **Given** a Python cycle with 45 days remaining until its EOL date, default thresholds (warn_days=180, error_days=0), allow_eol=False
- **When** check_eol_status(version, records, language='python') is evaluated
- **Then** returns status 'warn' (45 <= 180 but > 0)
- **Parameters:** warn_days default = 180; error_days default = 0; allow_eol default = False (config/model.py:418-421)
- **Edge case:** record.eol_date is None (language never EOLs, e.g. eol=false in API) -> always 'ok'
- **Edge case:** already past EOL with allow_eol=True downgrades 'error' to 'warn' instead of failing a CI gate
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### POL-065 — Folder template merge: exact flag inherited only from strict templates

**Category:** Policy · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/folders/core.py:159-181`

A rule's effective 'exact' enforcement is taken directly from an explicit rule.exact override when present; otherwise it is enabled only if at least one merged template both declares exact=True and has strictness=='strict' (templates with strictness=='loose' never force exact mode even if they declare exact=True).

- **Given** A rule referencing two templates: one with exact=True/strictness='loose' and one with exact=False/strictness='strict'
- **When** The rule is resolved with no explicit rule.exact override
- **Then** effective_exact is False, because no merged template has both exact=True AND strictness=='strict'
- **Parameters:** n/a

### POL-066 — Folder scaffold skip-vs-overwrite policy

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/folders/core.py:332-366`

When scaffolding files, an existing file at the target path is left untouched (action recorded as 'skip', detail 'exists') unless --force is passed, in which case it is overwritten and recorded as 'overwritten'; a genuinely new file is recorded as 'created'.

- **Given** scaffold target `README.md` already exists and force=False
- **When** `rrt folder scaffold` runs
- **Then** Action recorded is kind='skip', detail='exists'; the file's content is never touched
- **Parameters:** n/a

### POL-067 — Folder scaffold: existing files are skipped unless --force

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/folders/core.py:336-347`

When scaffolding required/template files into a directory, any file that already exists is left untouched (recorded as 'skip') unless --force is passed, which overwrites it.

- **Given** scaffold defines README.md and it already exists with custom content
- **When** rrt folders scaffold runs without --force
- **Then** README.md is left unchanged and the action log records kind='skip', detail='exists'

### POL-068 — Folder scaffold: executable flag sets execute bits on write (best-effort)

**Category:** Policy · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/folders/core.py:348-359`

A scaffold file flagged 'executable' has its owner/group/other execute bits set after being written; any OS-level failure to chmod is silently ignored rather than failing the scaffold operation.

- **Given** a scaffold_files entry with executable=true for scripts/setup.sh
- **When** rrt folders scaffold creates scripts/setup.sh
- **Then** the file is written and then chmod'd +x for user/group/other; if chmod fails (e.g. read-only filesystem) the scaffold still reports success

### POL-069 — Folder violation severity follows rule mode

**Category:** Policy · **Priority:** P2 · **Confidence:** Medium
**Source:** `src/repo_release_tools/folders/core.py:389-391`

A folder rule's mode determines whether its violations are treated as warnings or errors: 'warn' mode produces warning-severity violations, every other mode (e.g. 'strict') produces error-severity violations.

- **Given** a rule with mode='warn' missing a required directory
- **When** rrt folders check evaluates it
- **Then** the violation's severity is 'warning' rather than 'error', so it does not fail a strict CI gate that only counts errors
- ❓ **SME question:** Confirm that 'off' mode rules are excluded entirely upstream (not evaluated) rather than producing warning-severity violations here — the severity function only distinguishes warn vs everything else.

### POL-070 — Folder designer capture: exact/strictness derived from --loose flag

**Category:** Policy · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/folders/designer.py:11-29`

When capturing a folder template from an existing directory structure ('rrt folder capture'), the resulting template's strictness is 'loose' if --loose was passed, otherwise 'strict', and the 'exact' flag (which rejects unexpected top-level entries) is always the logical negation of --loose.

- **Given** rrt folder capture --name mytpl (no --loose) run against a directory with 3 files and 1 subdirectory
- **When** capture_template builds the FolderTemplate
- **Then** the template is strictness='strict', exact=True, with required_files/required_dirs populated from every top-level entry found, sorted case-insensitively by name

### POL-071 — Folder template capture classifies structure as strict/exact unless --loose is given

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/folders/designer.py:11-29`

When capturing a folder template from an existing directory's immediate children (rrt folder designer / capture), every top-level file and directory found becomes a 'required' entry, and the template is marked strict+exact by default; passing --loose instead marks it loose and non-exact so unexpected files won't later be flagged as violations.

- **Given** a project root containing README.md, src/, and tests/ with capture_template(loose=False)
- **When** the template is captured
- **Then** required_files=('README.md',) required_dirs=('src','tests') strictness='strict' exact=True — meaning any later top-level entry not in this list will be reported as a folder-policy violation

### POL-072 — MCP publish-snapshot: dry_run=False alone is the destructive confirmation (no separate flag)

**Category:** Policy · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/mcp/tools/publish_tools.py:27-142`

On the MCP tool surface, rrt_publish_snapshot force-pushes to a secondary remote as soon as it is called with dry_run=False; unlike the CLI's `git publish-snapshot`, there is no separate `--yes-i-know-this-overwrites-remote-history`-equivalent flag — dry_run=False alone authorizes the destructive push.

- **Given** an MCP client calls rrt_publish_snapshot(remote='mirror', branch='main', dry_run=False)
- **When** the tool executes
- **Then** it force-pushes an orphan single-commit snapshot to mirror:main immediately, without any additional confirmation parameter
- ⚠️ **Suspected defect:** This is a materially weaker confirmation policy than the CLI's dedicated destructive-confirmation flag for the same operation (git_sync.py:446-457) — worth flagging for parity review since both surfaces perform the same force-push.
- ❓ **SME question:** Should the MCP surface require a distinct explicit confirmation argument (mirroring --yes-i-know-this-overwrites-remote-history) rather than treating dry_run=False as sufficient authorization for a force-push?

### POL-073 — MCP publish-snapshot collapses the CLI's explicit destructive-confirmation flag into dry_run alone

**Category:** Policy · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/mcp/tools/publish_tools.py:27-35`

The MCP surface for publish-snapshot treats dry_run=False as sufficient authorization to force-push, with no separate confirmation input — whereas the CLI (rrt git publish-snapshot) requires a distinct --yes-i-know-this-overwrites-remote-history flag in addition to not passing --dry-run before it will force-push.

- **Given** an MCP client calls rrt_publish_snapshot(remote='public', branch='main', dry_run=False)
- **When** the tool executes
- **Then** it proceeds directly to git checkout --orphan / git push --force without any second confirmation input, unlike commands/git_sync.py:446-457 which additionally requires --yes-i-know-this-overwrites-remote-history
- ⚠️ **Suspected defect:** This is a policy divergence between product surfaces: the CLI requires two independent signals (not-dry-run AND explicit confirmation flag) before a destructive force-push runs, but the MCP tool requires only one (dry_run=False). An MCP client could trigger an irreversible remote-history overwrite with a single boolean it might set carelessly, where the CLI would have required a second, harder-to-mistype flag.
- ❓ **SME question:** Is it intentional that the MCP publish-snapshot tool only requires dry_run=False (no second confirmation parameter) to force-push, while the CLI requires an explicit --yes-i-know-this-overwrites-remote-history flag in addition to not using --dry-run? Should the MCP tool add an equivalent explicit-confirmation parameter?

### POL-074 — Upstream provider dispatch and unsupported-provider fallback

**Category:** Policy · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/sync/providers.py:20,106-122`

Only five upstream registries are supported for version syncing (pypi, npm, nuget, crates, packagist); an unrecognized provider value silently returns an empty version list rather than raising, so sync reports zero newer versions instead of failing.

- **Given** group.upstream_provider = 'homebrew' (unsupported)
- **When** `rrt sync` fetches versions
- **Then** fetch_versions returns [] silently; the command reports no newer versions found instead of erroring
- **Parameters:** PROVIDERS = {pypi, npm, nuget, crates, packagist}

### POL-075 — All upstream provider fetchers fail silently to an empty version list

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/sync/providers.py:27-122;src/repo_release_tools/sync/pypi.py:12-25`

Every upstream registry fetcher (pypi, npm, nuget, crates, packagist) treats network errors, timeouts, JSON decode errors, and unexpected response shapes the same way: return an empty list rather than raising. Combined with the sync rule that 'no newer versions' is a no-op success, this means a network outage during 'rrt sync' silently reports nothing to sync rather than failing loudly.

- **Given** the PyPI API is unreachable (DNS failure) when rrt sync runs for a pypi-tracked upstream
- **When** fetch_versions('mypackage', provider='pypi') is called
- **Then** it returns [] and the sync command proceeds as if there genuinely were no newer upstream versions, reporting success rather than a network error
- ⚠️ **Suspected defect:** Silently collapsing 'fetch failed' and 'no newer versions exist' into the same outcome could mask real network/API problems as false negatives during automated sync runs.
- ❓ **SME question:** Should rrt sync distinguish a fetch failure (network/API error) from a genuine 'already up to date' result, e.g. via a distinct exit code or warning, rather than treating both as silent success?

### POL-076 — NuGet package ID lookup is case-normalized to lowercase

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/sync/providers.py:56-65`

When fetching available versions from NuGet for an upstream package sync, the package identifier is always lowercased before building the API URL, matching NuGet's case-insensitive, lowercase-canonical package ID convention.

- **Given** an upstream package configured as 'Newtonsoft.Json'
- **When** rrt sync fetches versions with provider='nuget'
- **Then** the request goes to https://api.nuget.org/v3-flatcontainer/newtonsoft.json/index.json

### POL-077 — crates.io fetch requires custom User-Agent header

**Category:** Policy · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/sync/providers.py:68-83`

Fetching version data from crates.io requires sending a custom User-Agent header identifying the tool; other registries (npm, NuGet, Packagist, PyPI) are queried without this requirement.

- **Given** provider = 'crates', package = 'serde'
- **When** `fetch_versions` is called
- **Then** The HTTP request to crates.io includes header User-Agent: 'repo-release-tools (+https://github.com/Anselmoo/repo-release-tools)'
- **Parameters:** USER_AGENT = 'repo-release-tools (+https://github.com/Anselmoo/repo-release-tools)'

### POL-078 — PyPI upstream fetch fails silently to an empty version list

**Category:** Policy · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/sync/pypi.py:12-25`

When checking PyPI for upstream releases of a mirrored package, any network error, timeout, or malformed JSON response is treated as 'no versions found' rather than raising, matching the same policy used by the other upstream providers.

- **Given** PyPI is unreachable or returns invalid JSON for a configured upstream package
- **When** fetch_pypi_versions is called
- **Then** an empty list is returned, so the sync command reports zero newer versions rather than erroring
- **Edge case:** A 10-second default timeout is hardcoded (timeout: int = 10)

### POL-079 — JSON indentation is inferred from the existing package.json before rewriting the version

**Category:** Policy · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/version/targets.py:276-291,344-354`

When rrt updates the version field inside package.json, it preserves the file's original indentation style (spaces vs tabs, and how many spaces) instead of imposing a fixed format.

- **Given** Given a package.json indented with tabs
- **When** When replace_package_json_version rewrites the version field
- **Then** Then the rewritten file is re-serialized using tab indentation to match the original
- **Parameters:** n/a
- **Edge case:** A file with no indentation detected (single-line JSON) returns indent=None, producing compact json.dumps output

### POL-080 — Legacy double-escaped regex pattern compatibility fallback

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/version/targets.py:328-341`

Configured version/pin regex patterns are tried as-written first; if a pattern contains a doubled backslash, a de-escaped variant is also compiled and tried, to keep old TOML configs (that used double escaping) working.

- **Given** a pin_targets pattern configured as "v\\\\d+\\\\.\\\\d+" (double-escaped legacy form)
- **When** search_pattern or replace_pattern_version is invoked
- **Then** both the original pattern and its single-escaped variant are attempted in order, and the first one that matches/substitutes is used
- **Edge case:** Duplicate compiled variants (when de-escaping produces the same string) are de-duplicated via a seen-set

### POL-081 — Pin target missing-match policy

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/version/targets.py:357-401`

When a documentation/CI pin pattern fails to match its target file, the default behavior is to fail the bump; setting pin_target_missing='warn' downgrades this to a warning that skips the file instead.

- **Given** a pin_targets entry whose regex pattern no longer matches its file, pin_target_missing left at default
- **When** replace_pin_in_file(target, new_version, dry_run=False) is called
- **Then** raises RuntimeError('Pin pattern did not match in <path>. Set pin_target_missing = "warn" ...')
- **Parameters:** pin_target_missing default = 'error' (config.py); alternate value = 'warn'
- **Edge case:** if the pin file's current value already equals the new version, the file is left untouched and reported as 'already at <version>' (no-op, not an error)
- **Edge case:** 'rrt release check' always treats missing pin matches as warnings regardless of this setting, per bump.py:710-711 doc comment

### POL-082 — rrt-hooks tree-check runs in forced strict/check mode regardless of caller flags

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/workflow/hooks.py:1322-1340`

The 'tree-check' hook subcommand always invokes the tree validator with check=True and strict=True hardcoded, so CI/hook usage of tree-check cannot be run in a lenient or non-failing mode — it is designed to always hard-fail on drift.

- **Given** any invocation of `python -m repo_release_tools.workflow.hooks tree-check`
- **When** the subcommand dispatches to cmd_tree
- **Then** the tree comparison always runs with strict=True and check=True baked into the constructed argparse.Namespace, ignoring any environment-level lenient preference
- **Parameters:** hardcoded: check=True, strict=True, fix_empty_dirs=False, snapshot=False (hooks.py:1322-1339)
- **Edge case:** dirs_only, show_hidden, max_depth, inject/anchor are all hardcoded off/None — the hook path only ever runs the plain strict drift check, none of the interactive/formatting features (hooks.py:1323-1339)

### POL-083 — Commit type determines changelog-enforcement requirement

**Category:** Policy · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/workflow/hooks.py:155-193`

A commit only requires a changelog update if its mapped section is not Maintenance, or if it is marked as a breaking change (in which case a changelog update is always required regardless of type).

- **Given** commit subject 'chore!: drop Python 3.11 support'
- **When** commit_type_requires_changelog('chore', breaking=True) is evaluated
- **Then** returns True even though 'chore' alone maps to Maintenance, because breaking=True forces the requirement
- **Parameters:** N/A (derives from SECTION_MAP plus a breaking override)
- **Edge case:** a commit type with no SECTION_MAP entry is treated as not requiring changelog (section is None)
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory (The Given/When/Then is faithful to the code: commit_type_requires_changelog (src/repo_release_tools/workflow/hooks.py:155-166) returns True unconditionally when breaking=True (line 162-163), and otherwise looks up SECTION_MAP (defined in src/repo_release_tools/changelog.py:31-43, merged with any extra_section_map) to require a changelog entry unless the map…

### POL-084 — Changelog requirement gating: breaking commits and non-Maintenance section types require changelog

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/workflow/hooks.py:155-193`

A commit type requires a changelog entry if it is marked breaking, or if its mapped changelog section is anything other than Maintenance. Branch-level and subject-level changelog requirement checks both delegate to this same rule.

- **Given** commit type 'chore' with breaking=False
- **When** commit_type_requires_changelog is evaluated
- **Then** returns False because 'chore' maps to the Maintenance section
- **Edge case:** Any commit type with breaking=True always requires a changelog entry even if its base type would normally map to Maintenance
- **Edge case:** extra_section_map overrides can reclassify a type into/out of Maintenance

### POL-085 — Branch-type determines changelog-enforcement requirement

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/workflow/hooks.py:169-186`

Whether a branch is expected to carry a changelog update is derived purely from its <type>/ prefix using the same type->section mapping as commits; protected branch names (main/master/develop) and release/v* branches never require it.

- **Given** branch name 'feat/add-parser'
- **When** branch_requires_changelog('feat/add-parser') is evaluated
- **Then** returns True (feat maps to 'Added', not Maintenance)
- **Parameters:** ALLOWED_BRANCH_NAMES = (main, master, develop) — hooks.py:50
- **Edge case:** branch 'chore/bump-deps' returns False (Maintenance)
- **Edge case:** a branch type unrecognized by normalize_commit_type returns False rather than raising

### POL-086 — branch_requires_changelog gates changelog staging by branch type

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/workflow/hooks.py:169-186`

Only branches whose type maps to a changelog-relevant section (not main/master/develop, not release/v*, not Maintenance-mapped types) are required to stage a changelog update at pre-commit time.

- **Given** Current branch 'docs/update-readme'
- **When** run_pre_commit_changelog runs on the incremental workflow
- **Then** A changelog update must be staged (docs maps to 'Documentation', which is changelog-relevant)

### POL-087 — Changelog meta-commit suppression for auto-update hook

**Category:** Policy · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/workflow/hooks.py:196-220`

When the automated 'update-unreleased' hook is about to add a bullet for a commit, it skips commits whose description is itself about maintaining the changelog (e.g. 'update changelog', 'changelog entries'), to avoid a recursive/nonsensical bullet, while still allowing genuine feature commits that merely mention 'changelog' in their name.

- **Given** commit subject 'fix: update changelog to reflect CI changes'
- **When** is_changelog_meta_commit(subject) is evaluated
- **Then** returns True, so run_update_unreleased skips adding a bullet for this commit
- **Parameters:** _CHANGELOG_META_RE regex (hooks.py:196-202): verbs update|bump|revise|amend|correct|trim + 'changelog', or 'changelog entries/updates/corrections/formatting'
- **Edge case:** 'feat: add changelog parser' does NOT match (verb 'add' not in the meta-verb list for 'changelog', and it's not one of the meta-noun phrases) so it is still recorded normally

### POL-088 — Changelog-meta commit suppression for auto-unreleased updates

**Category:** Policy · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/workflow/hooks.py:196-220,749-754`

Commits whose description is itself about updating/correcting the changelog (e.g. 'update changelog entries') are not auto-appended to [Unreleased] again, to avoid a recursive self-referential bullet.

- **Given** Commit subject 'fix: update changelog to reflect CI changes'
- **When** run_update_unreleased runs
- **Then** No bullet is appended (is_changelog_meta_commit returns True), even though 'fix' is normally changelog-relevant

### POL-089 — Changelog-meta-commit suppression prevents recursive '[Unreleased]' bullets

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/workflow/hooks.py:196-220,749-754`

When auto-appending a bullet to the [Unreleased] section based on the commit subject, rrt skips commits whose description is itself about maintaining the changelog (e.g. 'update changelog', 'changelog entries', 'trim changelog formatting') so a correction commit doesn't add a self-referential bullet like '- update changelog entries'. Genuine features whose name happens to contain 'changelog' (e.g. 'add changelog parser') are not suppressed because the regex only matches specific maintenance verb+noun phrasings.

- **Given** Given commit subject 'fix: update changelog to reflect CI changes'
- **When** When run_update_unreleased checks is_changelog_meta_commit(subject)
- **Then** Then the changelog is not modified and the hook exits 0 without adding a bullet
- **Parameters:** _CHANGELOG_META_RE matches verbs {update, bump, revise, amend, correct, trim} + 'changelog', or 'changelog' + nouns {entries, updates, corrections, formatting}
- **Edge case:** A subject like 'feat: add changelog parser' is NOT suppressed, since 'add' is not in the meta-verb list paired with 'changelog' in this pattern position

### POL-090 — Changelog-meta-commit suppression to avoid recursive changelog bullets

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/workflow/hooks.py:196-220,749-754`

Auto-writing a changelog bullet for a new commit is skipped when the commit's own description is itself about maintaining the changelog (e.g. 'update changelog entries'), using a narrow regex of maintenance verb+noun phrases, so genuine features whose names merely contain the word 'changelog' aren't suppressed.

- **Given** commit subject "fix: update changelog to reflect CI changes"
- **When** run_update_unreleased processes the commit
- **Then** no bullet is appended to [Unreleased] because the description matches the changelog-meta regex, and the skip is logged verbosely
- **Edge case:** "feat: add changelog parser" is NOT suppressed — 'changelog parser' does not match any of the maintenance verb/noun patterns

### POL-091 — Changelog meta-commit suppression to prevent recursive [Unreleased] bullets

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/workflow/hooks.py:196-220,752-754`

The auto-changelog-writer hook skips appending a bullet for commits whose own description is about maintaining the changelog itself (e.g. 'fix: update changelog to reflect CI changes'), so the tool doesn't recursively add '- update changelog' style noise entries, while still capturing genuine feature commits that merely mention 'changelog' in their subject (e.g. 'feat: add changelog parser').

- **Given** commit subject 'fix: update changelog entries for v1.2.0'
- **When** run_update_unreleased() processes this commit
- **Then** no bullet is appended to [Unreleased] because the description matches the meta-commit regex (verb + 'changelog', or 'changelog' + entries/updates/corrections/formatting)
- **Parameters:** regex: \b(?:update|bump|revise|amend|correct|trim)\s+changelog\b | \bchangelog\s+(?:entries?|updates?|corrections?|formatting?)\b, case-insensitive (hooks.py:196-202)
- **Edge case:** 'feat: add changelog parser' is NOT suppressed because 'add' is not in the maintenance-verb list and the noun pattern requires entries/updates/corrections/formatting immediately after 'changelog', not 'parser' (hooks.py:214-216 docstring example)

### POL-092 — Changelog enforcement strategy resolution (auto/incremental/per-commit/unreleased/release-only)

**Category:** Policy · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/workflow/hooks.py:255-274,777-870`

The 'auto' changelog check strategy is derived from the repo's configured changelog_workflow: 'incremental' workflow maps to requiring the changelog file to appear in the commit's changed-file list ('per-commit'), while 'squash' workflow maps to skipping the check entirely ('release-only'). Bot-authored branches (dependabot/*, renovate/*) always skip the check regardless of strategy.

- **Given** changelog_workflow='squash', a 'feat: add x' commit with no changelog file staged
- **When** run_changelog_check(..., strategy='auto', branch='feat/add-x') runs
- **Then** effective_strategy resolves to 'release-only' and the check returns 0 (pass) without inspecting changed files
- **Parameters:** DEFAULT_CHANGELOG_WORKFLOW (config default); BOT_BRANCH_TYPES = (dependabot, renovate) — hooks.py:52
- **Edge case:** 'unreleased' strategy instead requires a non-empty [Unreleased] section rather than the file being in the diff
- **Edge case:** config load failure (non-missing-config RuntimeError) fails the check with the error message rather than defaulting silently
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory (The cited code is accurately described: _resolve_changelog_strategy (hooks.py:255-274) maps changelog_workflow 'squash' -> 'release-only' (skip check) and 'incremental' (or explicit 'incremental' input) -> 'per-commit', with 'auto' deferring to the configured workflow via _detect_changelog_workflow. run_changelog_check (hooks.py:777-870) applies this resolu…

### POL-093 — Changelog enforcement strategy resolution (per-commit vs unreleased vs release-only)

**Category:** Policy · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/workflow/hooks.py:267-274,777-870`

Whether a commit must include a changelog update, and how that is checked, depends on the configured changelog_workflow: 'incremental' workflow requires the changelog file to be part of the commit's changed files (or a non-empty [Unreleased] section, depending on --strategy); 'squash' workflow skips the check entirely except at release time. Bot branches (dependabot/renovate) always skip the check.

- **Given** changelog_workflow = 'squash' and a commit 'feat: add parser' on branch 'feat/parser'
- **When** run_changelog_check / run_pre_commit_changelog runs
- **Then** The check is skipped ('release-only' strategy) — no changelog file update is required for that commit
- **Edge case:** strategy='unreleased' requires a non-empty [Unreleased] section rather than a staged file diff
- **Edge case:** Bot branch prefixes (dependabot, renovate) bypass the check regardless of strategy
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### POL-094 — Changelog enforcement strategy resolution (auto → per-commit or release-only)

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/workflow/hooks.py:267-274,777-870`

The changelog check supports four strategies. 'auto' derives per-commit vs release-only from the repo's configured changelog_workflow (squash→release-only, else per-commit). 'incremental' is an alias for per-commit. 'unreleased' requires a non-empty [Unreleased] section rather than a specific file diff. 'release-only' always passes. Bot branches (renovate/*, dependabot/*) always skip the check regardless of strategy.

- **Given** changelog_workflow="squash" and strategy="auto"
- **When** run_changelog_check evaluates a changelog-relevant commit
- **Then** effective_strategy resolves to release-only and the check is skipped entirely
- **Edge case:** strategy='unreleased' passes only if the [Unreleased] section is both present and non-empty, not merely present
- **Edge case:** A commit on branch 'dependabot/npm_and_yarn/foo' always skips the check even under per-commit strategy

### POL-095 — Changelog enforcement strategy resolution and effective-strategy precedence

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/workflow/hooks.py:267-274,777-870`

The changelog-update pre-commit/CI check supports four enforcement strategies (auto, per-commit, unreleased, release-only); 'auto' is resolved from the repo's changelog_workflow config (squash -> release-only, anything else -> per-commit), and bot branches (renovate/*, dependabot/*) always skip the check regardless of the resolved strategy.

- **Given** changelog_workflow='squash' in [tool.rrt], strategy argument left at 'auto'
- **When** run_changelog_check() evaluates a changelog-relevant commit
- **Then** the effective strategy resolves to 'release-only' and the check is skipped entirely for that commit, with no changelog file requirement enforced pre-release
- **Parameters:** strategy choices: auto, incremental (alias for per-commit), per-commit, unreleased, release-only (hooks.py:791-807); bot branch prefixes: dependabot, renovate (hooks.py:52,817)
- **Edge case:** Bot-branch skip happens before strategy resolution and applies unconditionally, even under 'unreleased' or 'per-commit' strategy (hooks.py:814-819)
- **Edge case:** Under 'unreleased' strategy, only a non-empty [Unreleased] section anywhere in the file satisfies the check — it does not need to correspond to the current commit's changes (hooks.py:834-849)

### POL-096 — Changelog enforcement strategy resolution

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/workflow/hooks.py:267-274,788-870`

When the changelog enforcement strategy is 'auto', it resolves based on the configured changelog_workflow: an 'incremental' workflow requires the changelog file to appear in every changelog-relevant commit's changed files ('per-commit'); a 'squash' workflow skips per-commit enforcement entirely ('release-only') because the changelog is only written at release/bump time.

- **Given** changelog_workflow is configured as 'squash' and a commit 'feat: add new exporter' is being validated
- **When** run_changelog_check resolves strategy='auto'
- **Then** the effective strategy becomes 'release-only' and the check is skipped, returning 0, even though the changelog file was not touched
- **Parameters:** DEFAULT_CHANGELOG_WORKFLOW

### POL-097 — Changelog enforcement strategy resolution and bot-branch exemption

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/workflow/hooks.py:267-274,789-849`

The changelog-check hook supports four enforcement strategies: 'auto' (derives per-commit for incremental workflow, release-only for squash workflow), 'incremental' (alias for per-commit), 'unreleased' (requires a non-empty [Unreleased] section rather than checking specific changed files), and 'release-only' (skips the check entirely). Additionally, any commit on a branch whose type prefix is 'renovate' or 'dependabot' skips the changelog check regardless of strategy.

- **Given** Given changelog_workflow='squash' in config and strategy='auto' is passed
- **When** When run_changelog_check resolves the effective strategy
- **Then** Then effective_strategy becomes 'release-only' and the check is skipped for every commit
- **Parameters:** BOT_BRANCH_TYPES = (dependabot, renovate)
- **Edge case:** The bot-branch skip happens before strategy resolution, so it applies even under 'unreleased' or 'per-commit' strategies
- **Edge case:** 'per-commit' strategy checks the changelog file is literally part of the commit's changed-file set; 'unreleased' strategy instead checks for non-empty bullet content

### POL-098 — Squash-merge changelog bullet dedup/cancellation

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/workflow/hooks.py:281-374,377-455`

After a squash merge, duplicate changelog bullets (same text, case-insensitive) are collapsed to one, and pairs of bullets whose descriptions are opposite actions on the same subject (e.g. 'add Node 26' and 'remove Node 26') are both deleted entirely, only within matching scope prefixes.

- **Given** added bullets ['- add Node 26 support', '- CI: remove Node 26 support']
- **When** dedup_changelog_entries(added_lines) runs
- **Then** neither bullet is removed, because their scope prefixes differ (None vs 'ci') even though the verbs are opposite and subjects match
- **Parameters:** _OPPOSITE_VERB_PAIRS: add/remove, adds/removes, enable/disable, enables/disables, include/exclude, includes/excludes, upgrade/downgrade, upgrades/downgrades, revert/apply, reverts/applies (hooks.py:281-292)
- **Edge case:** exact case-insensitive duplicates are always collapsed regardless of scope
- **Edge case:** consecutive blank lines left by removal are collapsed to one blank line

### POL-099 — Unreleased bullet dedup on squash merge cancels opposite-verb pairs

**Category:** Policy · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/workflow/hooks.py:281-374,377-455`

When post-correcting a squashed changelog, exact duplicate bullets (case-insensitive) are collapsed to one, and pairs of bullets whose descriptions are opposite-verb reversals of the same subject (e.g. 'add Node 26' and 'remove Node 26') are both deleted entirely — but only if they share the same scope prefix.

- **Given** added lines ['- add Node 26 to test matrix', '- remove Node 26 to test matrix'], neither with a scope prefix
- **When** dedup_changelog_entries runs during rrt-hooks post-correct
- **Then** both bullets are removed from the changelog entirely because they are recognized as an opposite-verb cancelling pair
- **Parameters:** _OPPOSITE_VERB_PAIRS: add/remove, adds/removes, enable/disable, enables/disables, include/exclude, includes/excludes, upgrade/downgrade, upgrades/downgrades, revert/apply, reverts/applies (hooks.py:281-292)
- ⚠️ **Suspected defect:** Cancelling logic is purely lexical (verb+suffix match) and does not consider commit authorship, timing, or intent — two genuinely independent commits that happen to phrase opposite verbs on the same subject would be silently dropped from the changelog.
- ❓ **SME question:** Is it acceptable for the post-correct hook to silently delete both changelog bullets whenever two entries have opposite verbs and identical remaining text, without any human review step, given this can permanently drop legitimate release notes?

### POL-100 — Squash post-correction: dedupe and cancel opposite changelog bullets

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/workflow/hooks.py:281-455`

After a squash merge, exact-duplicate changelog bullets are collapsed to one, and pairs of bullets with the same scope whose verbs are opposites (e.g. 'add X' / 'remove X', 'enable X' / 'disable X') are both removed, since they cancel out.

- **Given** Added lines '- add Node 26' and '- remove Node 26' with no scope prefix
- **When** dedup_changelog_entries runs
- **Then** Both bullets are removed from the changelog (net-zero effective change)
- **Parameters:** Opposite verb pairs: add/remove, adds/removes, enable/disable, enables/disables, include/exclude, includes/excludes, upgrade/downgrade, upgrades/downgrades, revert/apply, reverts/applies (src/repo_release_tools/workflow/hooks.py:281-292)
- **Edge case:** Entries with different scope prefixes (e.g. 'CI: ...' vs 'Deps: ...') never cancel even if verb+subject match

### POL-101 — Squash-merge changelog dedup: exact duplicates and semantic-opposite cancellation

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/workflow/hooks.py:281-455`

After a squash merge, the post-correction step cleans up the changelog's newly-added bullet lines by removing exact case-insensitive duplicates (keeping the first) and by removing pairs of bullets that are semantic opposites of each other (e.g. 'add Node 26' followed later by 'remove Node 26'), so contradictory intermediate-commit noise doesn't survive into the release changelog.

- **Given** added lines ['- add Node 26 support', '- fix typo', '- remove Node 26 support']
- **When** dedup_changelog_entries() runs
- **Then** both the 'add Node 26 support' and 'remove Node 26 support' bullets are removed as a cancelling pair, leaving only '- fix typo'
- **Parameters:** opposite verb pairs: add/remove, adds/removes, enable/disable, enables/disables, include/exclude, includes/excludes, upgrade/downgrade, upgrades/downgrades, revert/apply, reverts/applies (hooks.py:281-292)
- **Edge case:** Entries with different scope prefixes (e.g. 'CI: add X' vs 'Deps: remove X') are never treated as a cancelling pair even if the verb+subject text matches (hooks.py:355-361)
- **Edge case:** Cancellation lookup is O(n) via a (scope, verb, suffix) dict keyed on the first-seen bullet of a pair, not O(n²) pairwise comparison (hooks.py:412-436)
- **Edge case:** Consecutive blank lines produced by removal are collapsed to one (hooks.py:445-455)

### POL-102 — Squash post-correction: duplicate and semantically-cancelling changelog bullet removal

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/workflow/hooks.py:281-455,873-956`

After a squash merge, exact duplicate changelog bullets (case-insensitive) are collapsed to the first occurrence, and pairs of bullets whose descriptions are opposite-verb pairs (e.g. 'add X'/'remove X', 'enable Y'/'disable Y') for the same scope prefix are both removed as cancelling out. Removal is restricted to the lines the squash commit actually added, via 1-based line positions parsed from the diff hunk headers, so identical lines in older release sections are never touched.

- **Given** the squash commit's changelog diff added "- CI: add Node 26" and later "- CI: remove Node 26"
- **When** dedup_changelog_entries is applied and then written back via apply_dedup_to_changelog
- **Then** both bullets are removed from the changelog as a cancelling pair, and any resulting double-blank-line is collapsed to one
- **Edge case:** "CI: add Node 26" vs "Deps: remove Node 26" do NOT cancel because their scope prefixes differ
- **Edge case:** 10 opposite-verb pairs are hardcoded: add/remove, adds/removes, enable/disable, enables/disables, include/exclude, includes/excludes, upgrade/downgrade, upgrades/downgrades, revert/apply, reverts/applies

### POL-103 — Post-correction changelog rewrite restricted to the squash commit's own diff hunk positions

**Category:** Policy · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/workflow/hooks.py:308-346,458-509`

When rewriting the changelog after dedup, only lines that were actually added at their current line positions by the specific squash commit being corrected are eligible for removal, so identical bullet text sitting in older, already-released changelog sections is never accidentally deleted.

- **Given** the squash commit added a bullet '- add caching' at line 8, but an older release section elsewhere in the file also happens to contain the literal text '- add caching' at line 240
- **When** apply_dedup_to_changelog() removes a duplicate '- add caching' bullet
- **Then** only the line at position 8 (within the recorded added_line_positions) is eligible for removal; the identical text at line 240 is left untouched because it falls outside the hunk's added-line positions
- **Parameters:** n/a
- **Edge case:** If added_line_positions is None, the removal budget applies to the whole file instead of being position-restricted (hooks.py:489)


## Lifecycle rules (38)

### LIF-001 — rrt artifacts --regenerate then re-snapshot lifecycle

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/artifacts_cmd.py:162-199`

Regenerating artifacts runs each configured target's build command (skipping targets with no command) and, only on a real run (not dry-run), rewrites the lock file with fresh hashes; if zero targets have a command configured, nothing is rewritten.

- **Given** 3 configured artifact_targets, 2 of which have a `command` set and 1 without
- **When** `rrt artifacts --regenerate` runs (not dry-run)
- **Then** the 2 commands execute in order, then the lock file is rewritten to reflect all currently matched files' hashes; if a regenerate command fails the whole operation aborts with exit 1 before the snapshot is rewritten
- **Parameters:** n/a
- **Edge case:** Dry-run mode prints what would run/update but performs no writes and no lock update (artifacts_cmd.py:189-198).

### LIF-002 — New branch creation carries uncommitted working-tree changes onto the new branch

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/branch.py:177-234`

`rrt branch new` refuses to create a branch that already exists, then creates and checks out the new branch via `git checkout -b`; any uncommitted staged/unstaged changes on the source branch automatically move with the checkout (native git behavior), and the command reports how many files, staged vs. unstaged, moved along.

- **Given** the working tree has 2 staged and 1 unstaged file when creating feat/new-thing
- **When** `rrt branch new feat "new thing"` runs (not dry-run)
- **Then** git checkout -b feat/new-thing succeeds and the 3 changed files are now attributed to the new branch; the command reports 'Files changed: 3, Staged: 2, Unstaged: 1' and lists up to STATUS_MAX changed files, truncating the rest with a '…and N more' summary

### LIF-003 — Bump command version resolution and branch creation gate

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/bump.py:271-543`

`rrt bump` computes the next version, builds the release branch name from it, and refuses to proceed if that branch already exists unless --force is passed (which resets the branch); the working tree must also be clean before any non-dry-run mutation, and preflight failures abort before any files change.

- **Given** the release branch 'release/v1.4.0' already exists and --force is not passed
- **When** `rrt bump minor` computes new version 1.4.0
- **Then** the command prints "Branch 'release/v1.4.0' already exists. Delete it first or choose a different version." and exits 1 without touching any files
- **Parameters:** none
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### LIF-004 — Bump kind resolution and CalVer fallback

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/bump.py:315-339`

The bump command accepts a keyword (major/minor/patch/pre-release/alpha/beta/rc/calver) or an explicit version string; if 'calver' is requested but the current version isn't a valid CalVer, it starts fresh from today's date rather than failing.

- **Given** current version is a semver '1.2.3' and bump value is 'calver'
- **When** cmd_bump parses args.bump == 'calver'
- **Then** CalVersion.parse('1.2.3') fails, so the new version becomes today's CalVersion (e.g. 2026.07.10) — a full scheme switch with no error raised
- **Parameters:** _BUMP_KINDS = {major, minor, patch, pre-release, calver, alpha, beta, rc}
- **Edge case:** explicit version string that is neither valid semver nor valid calver -> command exits 1 with 'Invalid bump value'
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory (The Given/When/Then is faithful to the code: at src/repo_release_tools/commands/bump.py:317-327, when args.bump == "calver", the code tries CalVersion.parse(str(current)) (line 320); if that raises ValueError (e.g. current is a semver like '1.2.3'), it silently falls back to CalVersion.today(calver_scheme) (lines 321-324) with no error/warning raised, produ…

### LIF-005 — Bump retries commit once after pre-commit hook auto-fix

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/bump.py:520-535`

If the git commit created by rrt bump fails (e.g. a pre-commit hook auto-regenerated files), the tool re-stages all unstaged changes and retries the commit exactly once before giving up.

- **Given** A pre-commit hook regenerates a docs file during 'git commit -m "chore: bump version to vX"'
- **When** The first commit attempt fails with RuntimeError
- **Then** Files are re-staged with 'git add -u' and the same commit command is retried once; if it fails again the exception propagates

### LIF-006 — Pre-commit hook auto-fix retry after failed commit

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/bump.py:520-535`

If the initial `git commit` for a version bump fails (typically because a pre-commit hook auto-regenerated files, e.g. docs), the bump command re-stages all changes with `git add -u` and retries the commit exactly once before giving up.

- **Given** a pre-commit hook (e.g. rrt-cli-docs) rewrites a generated doc file during the first commit attempt, causing pre-commit to reject the commit
- **When** the first `git commit -m 'chore: bump version to v1.5.0'` raises RuntimeError
- **Then** the tool runs `git add -u` again and retries the identical commit command exactly once; a second failure is not retried further and propagates
- **Parameters:** retry limit = 1

### LIF-007 — docs generate dry-run TOML lockfile validation without write

**Category:** Lifecycle · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/docs_cmd.py:199-205`

When `rrt docs generate` targets the toml lockfile format with --dry-run, the tool still builds and structurally validates the lock content in memory (catching malformed doc entries) but never writes the lock file to disk.

- **Given** extracted doc entries exist and --format toml --dry-run is passed
- **When** _cmd_generate runs
- **Then** build_lock(sources) is called for validation only; the function returns success and prints 'would write' without touching the lockfile at .rrt/docs.lock.toml (or configured lock_file)

### LIF-008 — Docs-map lockfile drift classification

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/docs_map_lock.py:91-129`

Comparing the desired per-directory content hash against the recorded lockfile classifies each directory as missing-entry (in desired but not locked), stale (hash differs), or orphan-entry (locked but no longer a desired target); drift items are reported sorted by kind then directory.

- **Given** Lockfile has an entry for `src/old_module` (now deleted) and is missing an entry for newly-added `src/new_module`
- **When** `rrt docs map --check` runs
- **Then** Drift report includes one `missing-entry` for `src/new_module` and one `orphan-entry` for `src/old_module`
- **Parameters:** hash format sha256:<hex>

### LIF-009 — docs map three-way drift classification (missing / stale / orphan)

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/docs_map_lock.py:91-129`

For each per-directory generated documentation block, drift is classified into exactly one of three kinds: a directory expected to be tracked but absent from the lockfile is 'missing-entry', a directory present in both but with a different content hash is 'stale', and a lockfile entry for a directory no longer being generated is an 'orphan-entry'.

- **Given** the lockfile has entries for dirs A (matching hash), B (different hash than desired), and C (not currently a target directory); target directory D has no lockfile entry
- **When** `rrt docs map --check` runs drift detection
- **Then** the report lists D as missing-entry, B as stale, and C as orphan-entry; A produces no drift item; items are sorted by (kind, directory)
- **Parameters:** hash algorithm: sha256 (docs_map_lock.py:33-36)

### LIF-010 — Hook-manager surface becomes 'obsolete' once another manager is active

**Category:** Lifecycle · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/doctor.py:209-247`

If one hook manager (pre-commit, lefthook, or husky) is actively wired with repo-release-tools hooks, the absence of the other hook managers is reported as 'obsolete' rather than 'warning', since only one manager is expected to be active.

- **Given** lefthook.yml exists and references repo-release-tools hooks (status=ok), and .pre-commit-config.yaml does not exist
- **When** `rrt doctor` runs _check_hook_integrations
- **Then** the missing pre-commit surface is reported as status='obsolete' with message '... not configured (obsolete: lefthook already configured)' instead of a plain warning
- **Parameters:** none

### LIF-011 — Doctor --fix auto-inserts a missing [Unreleased] changelog section

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/doctor.py:250-283,408-417`

When `rrt doctor --fix` (or --fix-dry-run) runs, for every version group whose changelog file exists but has no [Unreleased] section, the tool prepends the format-appropriate Unreleased placeholder to the very top of the changelog file; groups whose changelog file doesn't exist are skipped entirely.

- **Given** CHANGELOG.md exists and has release sections but no [Unreleased] heading
- **When** `rrt doctor --fix` runs
- **Then** the Markdown Unreleased placeholder is prepended before the existing content and written back to disk; `--fix-dry-run` reports the same action without writing
- **Parameters:** Markdown placeholder vs RST placeholder chosen by detected changelog format
- **Edge case:** If the changelog file itself is missing, no fix is attempted for that group (doctor.py:262-264).

### LIF-012 — Doctor check severities map to exit code only via 'ok' flag

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/doctor.py:373-393,419`

Each automation surface check (pre-commit, lefthook, husky, GitHub workflows) resolves to one of four states — ok, obsolete, warning, error — but only 'error' (ok=False) flips the overall command result to failure; warning and obsolete are always non-blocking.

- **Given** the '.pre-commit-config.yaml' file exists but cannot be read due to an OSError
- **When** `rrt doctor` runs its core automation checks
- **Then** that check is classified severity='error', ok=False, causing all_ok=False and the command exits 1; a 'warning' or 'obsolete' classification never flips all_ok
- **Parameters:** none

### LIF-013 — EOL host/project checks feed into health snapshot with 3-way severity collapse

**Category:** Lifecycle · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/eol_check.py:269-312`

When merged into the shared health lock, the 5-value EolStatus (ok/info/warn/error/unknown) is collapsed to 3 health-lock severities: ok/info -> 'ok', warn/unknown -> 'warning', error -> 'error'.

- **Given** a language's host runtime status is 'unknown' (version not detected in bundled records)
- **When** the check_entries list is built for `rrt eol --snapshot`
- **Then** the corresponding health.lock.toml entry gets status='warning', not 'error' and not a distinct 'unknown' value
- **Parameters:** none

### LIF-014 — Squash-local preconditions and commit assembly

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/git_commit.py:131-205`

Squashing local commits into one conventional commit requires a clean working tree (unless dry-run), a resolvable base ref (explicit --base-ref or configured upstream), at least one commit ahead of that base, and a determinable merge-base; only then does it reset --soft to the merge-base and commit once.

- **Given** 3 commits exist ahead of origin/main with a clean working tree
- **When** the developer runs `rrt git squash-local --base-ref origin/main "ship parser"`
- **Then** the tool runs `git reset --soft <merge-base>` then `git commit -m "<type>: ship parser"`, collapsing the 3 commits into 1; if the tree is dirty, no upstream/base-ref is set, no commits are ahead, or no merge-base is found, the command exits 1 without modifying history

### LIF-015 — Commit type inference from branch name for rrt git commit

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/git_commit.py:58-71`

When drafting a conventional commit without an explicit --type, rrt infers the commit type from the current branch's type prefix (e.g. 'feat/add-x' infers 'feat'), but only if the branch name is not a magic/allowed branch name (main, develop, etc.), not a release/v* branch, not a bot-branch type (dependabot, renovate), and the prefix is itself one of the recognized conventional commit types; otherwise inference fails and --type is required.

- **Given** current branch is 'dependabot/npm_and_yarn/lodash-4.17.21' and no --type is passed
- **When** rrt git commit "bump lodash" runs
- **Then** infer_commit_type returns None because the prefix is a bot branch type, so the command fails with 'Could not infer a conventional commit type from the current branch. Use --type explicitly.'

### LIF-016 — Git sync-status divergence classification

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/git_inspect.py:53-73`

A branch's relationship to its sync base is classified as: 'no upstream' if there's no base ref; 'up to date' if ahead=0 and behind=0; 'ahead locally' if ahead>0 and behind=0; 'behind base' if ahead=0 and behind>0; otherwise 'diverged' (ahead>0 and behind>0), which requires the user to rebase or merge.

- **Given** Branch is 3 commits ahead and 2 commits behind its upstream
- **When** `rrt git doctor` or `rrt git sync-status` computes the relation
- **Then** Relation is classified as 'diverged', and sync_problem reports "Branch ... has diverged from ... (ahead 3, behind 2). Rebase or merge is needed."
- **Parameters:** n/a

### LIF-017 — rrt git move auto-stash/checkout/restore lifecycle

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/git_sync.py:162-209`

Switching branches with `rrt git move` on a dirty working tree stashes local changes first, then checks out the target (creating it with -b if --create was given), then restores the stash; if the checkout itself fails on a dirty tree, the auto-stash is deliberately left on the stash stack instead of being auto-restored, and the error propagates.

- **Given** working tree has uncommitted changes and the target branch checkout fails (e.g., conflicting paths)
- **When** `rrt git move <target>` runs
- **Then** the stash push already occurred, the checkout raises a RuntimeError, a message notes the auto-stash remains on the stash stack, and the exception propagates instead of returning a code
- **Parameters:** n/a
- **Edge case:** On a clean tree, no stash push/pop happens at all — checkout runs directly (git_sync.py:181-205).

### LIF-018 — rrt git sync preconditions and auto-stash lifecycle

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/git_sync.py:70-159;src/repo_release_tools/workflow/git.py:255-264`

Before syncing the current branch, the command requires a configured upstream branch, requires no in-progress rebase/merge operation, and requires no unresolved merge conflicts in the working tree; if the tree is dirty it auto-stashes before fetch+pull and auto-pops after a successful pull, defaulting to rebase strategy (--merge switches to a merge pull); if the pull fails on a dirty tree, the stash is deliberately left in place rather than auto-restored.

- **Given** the current branch has no upstream branch configured
- **When** `rrt git sync` runs
- **Then** the command exits 1 immediately with a message to set an upstream first, without fetching or stashing anything
- **Parameters:** default pull strategy: rebase (git pull --rebase); --merge switches to plain git pull
- **Edge case:** An in-progress rebase or merge (detected via .git/rebase-merge, .git/rebase-apply, or .git/MERGE_HEAD) blocks sync entirely (git_sync.py:97-105).
- **Edge case:** Unresolved merge conflicts in `git status` output block sync entirely, showing up to a capped number of conflicting files (git_sync.py:106-114).

### LIF-019 — Hook registration merge deduplicates by matcher+command (Claude/Codex/Gemini style)

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/hooks_cmd.py:387-433`

When installing hooks into a Claude/Codex/Gemini-style settings.json/hooks.json, existing hook groups are matched by their 'matcher' string; new commands are appended into the matching group only if that exact command string is not already present, and unmatched groups are appended as new entries. No existing entries are removed or overwritten.

- **Given** settings.json already has a PreCommit group with matcher '*' and one hook command
- **When** `rrt hooks install --target claude-local` runs again with the same hook script
- **Then** the registration file is re-written but the duplicate command is not added a second time (idempotent merge); a genuinely new command for the same matcher is appended to the existing group's hooks array

### LIF-020 — Hooks install: managed hook-registration JSON is merged additively, deduped by command signature

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/hooks_cmd.py:387-470`

When writing the surface-native hook registration file (settings.json, hooks.json, etc.), rrt merges new hook entries into existing groups rather than overwriting the file; an entry already present (matched by command, or by matcher+bash+command for Copilot) is not duplicated.

- **Given** an existing .claude/settings.json already registering rrt_user_commit_policy.py under PreToolUse with matcher 'Bash'
- **When** rrt hooks install --target claude-local runs again
- **Then** the existing PreToolUse/Bash group is reused and the duplicate command entry is skipped rather than appended a second time

### LIF-021 — Hook registration merge deduplicates by (matcher, bash, command) tuple (Copilot style)

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/hooks_cmd.py:436-470`

For Copilot-style hook registration (a different JSON shape than Claude/Codex/Gemini), entries are deduplicated using the full (matcher, bash, command) signature rather than just the command string, and the registration file's 'version' field is forced to 1 on every write.

- **Given** hooks.json for copilot-local already contains one PreToolUse entry
- **When** `rrt hooks install --target copilot-local` is run again
- **Then** the merged file has 'version': 1 and no duplicate entry is added when the (matcher, bash, command) triple exactly matches an existing entry; entries with any differing field are appended

### LIF-022 — Release repair mode dispatch by --from-ref presence

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/release_repair.py:101-150`

`rrt release repair` has two mutually exclusive modes selected by a single flag: passing --from-ref triggers full history 'recreate' mode (rewriting the release commit from a base ref); omitting it runs 'verify-and-fix' mode (checks and patches the current release state in place). Both modes first require a clean working tree.

- **Given** the working tree is clean and --from-ref origin/main is supplied
- **When** `rrt release repair --from-ref origin/main` is run
- **Then** the command dispatches to _recreate(); if --from-ref is omitted, it dispatches to _verify_and_fix() instead; if the working tree is dirty, both modes are refused before any mode-specific logic runs
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### LIF-023 — Sync --bump applies mirrored versions in ascending order with optional commit/tag

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/sync_cmd.py:172-198`

In live mirror mode, each newer upstream version is applied to version targets one at a time in ascending order; if --commit is set a commit is made after each version is applied, and if --tag is set an annotated tag is created after the commit (so the tag lands on the correct commit).

- **Given** fresh = [1.4.1, 1.5.0] and both --commit and --tag are passed
- **When** rrt sync --bump --commit --tag runs live (not dry-run)
- **Then** version targets are updated to 1.4.1, committed, tagged v1.4.1, then updated to 1.5.0, committed, tagged v1.5.0 — in that order; if a tag step fails the command returns that step's non-zero exit code immediately
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### LIF-024 — Sync with no newer versions is a no-op success

**Category:** Lifecycle · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/sync_cmd.py:173-174`

If there are no upstream versions newer than the current one, --bump mode exits successfully without doing anything.

- **Given** fresh = [] (no newer versions)
- **When** rrt sync --bump runs live
- **Then** the command returns exit code 0 and makes no changes

### LIF-025 — Tag create refuses overwrite and force-recreates via delete-then-create

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/tag.py:153-176`

Creating a tag that already exists fails unless --force is given; with --force the existing tag is deleted locally then an annotated tag is created fresh at the current commit (not simply moved).

- **Given** tag 'v1.2.3' already exists pointing at an old commit
- **When** `rrt tag create --force` runs at a new HEAD
- **Then** the old 'v1.2.3' tag is deleted (`git tag -d`) and a new annotated 'v1.2.3' tag is created at the current HEAD (`git tag -a`)
- **Parameters:** n/a
- **Edge case:** Without --force, an existing tag causes exit 1 with a guidance message (tag.py:154-161).

### LIF-026 — Workspace bump: two-phase all-or-nothing config load

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/commands/workspace.py:144-212`

When bumping the version across multiple packages at once, every package's config must load and its new version must resolve successfully before any file in any package is written.

- **Given** rrt workspace bump minor --packages api,sdk,docs and the 'docs' package has no [tool.rrt] config
- **When** the command runs (Phase 1 loads all three package configs and resolves versions before Phase 2 writes anything)
- **Then** the command exits 1 reporting the missing config for 'docs', and no version target or changelog file is modified in 'api' or 'sdk' either
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### LIF-027 — Workspace bump changelog promotion precondition

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/workspace.py:97-123`

During a workspace-wide bump, a package's changelog is only promoted from [Unreleased] to the new version if the changelog file exists, has an [Unreleased] section, and that section has at least one bullet.

- **Given** a package's CHANGELOG.md exists but its [Unreleased] section is empty (no bullets)
- **When** rrt workspace bump patch --packages <pkg> runs (and --no-changelog is not set)
- **Then** the changelog file is left untouched even though the version target files are updated to the new version

### LIF-028 — Workspace bump changelog promotion requires a non-empty [Unreleased] section

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/commands/workspace.py:97-123`

During a workspace bump, a package's changelog is only promoted from [Unreleased] to the new version if the changelog file exists, has an [Unreleased] section, and that section has at least one entry; otherwise the changelog is left untouched.

- **Given** a package changelog with an empty [Unreleased] section (no bullets)
- **When** rrt workspace bump runs without --no-changelog
- **Then** the changelog file is not modified for that package

### LIF-029 — Folder scaffold file overwrite policy

**Category:** Lifecycle · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/folders/core.py:332-368`

When scaffolding folder templates, an existing file is left untouched (action recorded as 'skip') unless --force is given, in which case it is overwritten and recorded as 'overwritten' rather than 'created'; newly-written executable scaffold files have their executable bits set best-effort after writing.

- **Given** a template scaffold file `Makefile` already exists in the target directory
- **When** `rrt folder scaffold` runs without --force
- **Then** the file is left unchanged and reported as skipped ('exists'); with --force it is overwritten and reported as 'overwritten'
- **Parameters:** n/a
- **Edge case:** Setting the execute bit is best-effort and silently ignores OS-level chmod failures (folders/core.py:355-359).

### LIF-030 — MCP version-bump tool applies per-target without atomic rollback

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/mcp/tools/version_tools.py:82-92`

The MCP server's bump tool (used by AI agents/automation) writes each version target file one at a time in a loop, unlike the CLI's all-or-nothing atomic bump; if a later target in the same group fails, earlier targets in that group remain updated with no rollback.

- **Given** a version group with 3 targets, dry_run=False
- **When** rrt_bump is invoked via MCP and the 2nd target's replace_version_in_file call raises
- **Then** the 1st target's file is left permanently updated to the new version while the 2nd and 3rd are not, producing an inconsistent group state that the CLI's replace_all_versions_atomic would have prevented
- **Parameters:** n/a
- **Edge case:** dry_run=True (the tool default) never reaches the write loop, so the divergence only manifests when an agent explicitly passes dry_run=False
- ⚠️ **Suspected defect:** This is a behavioral divergence from the CLI bump command (commands/bump.py:134 uses replace_all_versions_atomic) that is not documented anywhere in the MCP tool docstring. Confirmed by comparing mcp/tools/version_tools.py:86-92 (per-target replace_version_in_file loop) against commands/bump.py:103,134 (group-level replace_all_versions_atomic call).
- ❓ **SME question:** Should the MCP rrt_bump tool be changed to call replace_all_versions_atomic (matching CLI behavior) instead of writing targets one at a time, to avoid leaving a version group partially bumped on failure?

### LIF-031 — Health lock regression severity ordering

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/state.py:189-220`

A health check's status can only move through ok/obsolete (0) -> warning (1) -> error (2); `rrt doctor --check` only flags it as a regression when severity increases versus the last snapshot, and silently accepts any decrease.

- **Given** the last health snapshot recorded check 'pre_commit' as status 'warning'
- **When** a new `rrt doctor --check` run finds 'pre_commit' now has status 'error'
- **Then** the check reports a regression message 'Health regression for pre_commit: warning -> error'; if the new status were 'ok' (an improvement) no regression is reported
- **Parameters:** _SEVERITY map: ok=0, obsolete=0, warning=1, error=2 (state.py:203)

### LIF-032 — Anchor-based doc injection: stale-vs-write-vs-noop exit code policy

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/tools/inject.py:244-325`

When applying generated content to a target file (whole-file or inside an anchor block), the tool compares desired content to what's on disk: identical content is a no-op (exit 0), --check-only mode with different content fails (exit 1) telling the user which command to re-run, and an actual write either succeeds (exit 0) or, if fail_on_change is requested, succeeds but still returns exit 1 so CI hooks stop and prompt re-staging.

- **Given** a generated docs page differs from what's on disk and the command is invoked with check=True, write=False
- **When** apply_generated_docs runs
- **Then** the file is left unmodified and the command returns exit code 1 with 'is stale. Run: rrt docs publish'
- **Edge case:** anchor_id set but the target file does not exist: hard failure (exit 1), never auto-creates the file
- **Edge case:** anchor markers present but end marker missing: raises ValueError distinct from the missing-anchor case

### LIF-033 — Atomic multi-file version write with rollback

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/version/targets.py:96-136`

When bumping the version across every configured file target, rrt first checks that every file can be safely rewritten in memory (each target's current version must differ from the new version); only after every target passes does it write any file. If a write fails partway through, every file already written is restored to its original content.

- **Given** Given three version targets, and the second one's write raises an OSError
- **When** When replace_all_versions_atomic runs in non-dry-run mode
- **Then** Then the exception propagates, and any target file already written in this call is rewritten back to its original content before the error surfaces
- **Parameters:** n/a
- **Edge case:** If current_version == new_version for any target, the whole operation raises RuntimeError before any file is touched
- **Edge case:** Rollback write failures are swallowed (OSError caught) rather than raised, to avoid masking the original error
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### LIF-034 — Atomic version replacement rollback on partial write failure

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/version/targets.py:96-136`

When updating multiple version-bearing files in one bump, all substitutions are computed in memory first; if writing any file fails partway through, every already-written file is rolled back to its original content before the error propagates.

- **Given** 3 version targets where the 3rd file write raises OSError (e.g. permission denied)
- **When** replace_all_versions_atomic runs with dry_run=False
- **Then** targets 1 and 2, already written with the new version, are rewritten back to their original content, and the exception is re-raised
- **Edge case:** Rollback write failures are swallowed (OSError caught and ignored) rather than raised, so a rollback can itself silently fail leaving partial state
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### LIF-035 — Atomic multi-target version write with rollback

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/version/targets.py:96-136`

When bumping the version across multiple configured files, all files are read and their new content computed in memory first; only if every target computes successfully are any files actually written, and if a write fails partway through, previously-written files in that same batch are restored to their original content.

- **Given** three version targets (pyproject.toml, package.json, VERSION file) configured in one version group
- **When** rrt bump writes a new version and the third file's write raises an OSError after the first two succeeded
- **Then** the first two files are rewritten back to their pre-bump content so the working tree ends in its original state, and the exception propagates
- **Parameters:** n/a — behavioral guarantee, no magic numbers
- **Edge case:** If the rollback write itself fails (OSError), the exception is swallowed silently (targets.py:132-135) leaving that file in the new (unrolled-back) state — a partial-rollback risk
- **Edge case:** Any target whose current version already equals the new version raises 'version replacement had no effect' before any file is written (targets.py:118-120)
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### LIF-036 — Version target atomic multi-file write with rollback

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** Medium
**Source:** `src/repo_release_tools/version/targets.py:96-141`

When updating version strings across multiple configured files, all substitutions are computed in memory first; if any target would produce no textual change (current==new) the whole operation aborts before any file is written; if a write fails partway through, already-written files are rolled back to their original content.

- **Given** Two version targets, one of which already contains the new version string
- **When** replace_all_versions_atomic is called
- **Then** RuntimeError('... version replacement had no effect') is raised and no files on disk are modified
- ❓ **SME question:** P0 panel split on whether this moves money / is regulatory () — confirm criticality.

### LIF-037 — Git status porcelain line classification

**Category:** Lifecycle · **Priority:** P2 · **Confidence:** High
**Source:** `src/repo_release_tools/workflow/git.py:374-393`

Each line of `git status --short` output is classified into exactly one of six change categories: untracked, conflict, renamed, added, removed, or modified, using a fixed precedence order (untracked check first, then conflict markers, then rename/copy, then add, then delete, else modified).

- **Given** a porcelain status line 'UU file.txt' (both sides modified/conflicted)
- **When** the tool renders the changed-files list for `rrt branch new` or `rrt git status`
- **Then** the line is classified as 'conflict', not 'modified', because the 'U' check and the {'AA','DD'} set are evaluated before the rename/add/delete checks

### LIF-038 — Update-unreleased hook idempotent no-op detection and staging side effect

**Category:** Lifecycle · **Priority:** P1 · **Confidence:** High
**Source:** `src/repo_release_tools/workflow/hooks.py:723-774`

When a commit qualifies for an automatic [Unreleased] bullet, the hook only writes and re-stages the changelog file if the computed content actually differs from the original; if the bullet is already present (idempotent re-run), no file write or git add occurs.

- **Given** a commit-msg hook re-run where the [Unreleased] section already contains the exact bullet for the current commit subject
- **When** run_update_unreleased() runs a second time for the same subject
- **Then** append_to_unreleased() produces identical content to the original, so the function reports 'no change (already up to date)' and skips both the file write and 'git add' step
- **Parameters:** n/a
- **Edge case:** Squash-workflow repos skip this hook entirely before even checking idempotency (hooks.py:743-745)
- **Edge case:** A missing changelog file is a hard failure, not a silent skip (hooks.py:757-761)


## Rejected by referees (do not treat as behavior)

- **Version replacement no-op detection (atomic multi-file guard)** — `src/repo_release_tools/version/targets.py:96-136`
- **kind='pattern' version-target regex must have exactly one capture group** — `src/repo_release_tools/commands/bump.py:662-668`
- **Changelog lint style rules** — `src/repo_release_tools/commands/changelog_lint.py:93-172,245-256`
- **Changelog compare version-label matching** — `src/repo_release_tools/commands/changelog_compare.py:83-102`
- **Doc source-URL default template is per-platform, falling back to source_url_template override** — `src/repo_release_tools/docs/formats/_shared.py:21-49`
- **Documentation extraction priority: SOURCE_OWNED_TOPIC_DOCS always wins, then explicit markers, then implicit docstrings, first name wins** — `src/repo_release_tools/docs/extractor.py:700-734`
