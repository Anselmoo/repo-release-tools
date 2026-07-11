"""Characterization tests for the ``rrt-hooks`` policy surface and the GitHub Action.

Pins contract items from ``analysis/the/MODERNIZATION_BRIEF.md`` §5:

* **C7** — squash-merge changelog post-correction (``rrt-hooks changelog post-correct``):
  exact-duplicate and lexical opposite-verb bullet cancellation, restricted to the
  squash commit's own diff hunks.
* **C8** — branch-name policy (``rrt-hooks check-branch-name``): fixed names,
  ``release/v<semver>``, ``<type>/<kebab-slug>`` (<=60 chars), bot-branch slug exemption.
* **C9** — commit-type -> changelog-section mapping (``rrt-hooks update-unreleased`` /
  ``check-changelog``): feat->Added, fix->Fixed, chore->Maintenance (no changelog
  required), ``fix!:``->Breaking Changes, scope rendered bold.
* **D8** — the GitHub Action's changelog-status grep (``action.yml:134``) was anchored
  ``^\\[Unreleased\\]`` and therefore never matched a standard ``## [Unreleased]``
  heading. Fixed in Phase 6a to match ``^## \\[Unreleased\\]`` (mirroring
  ``changelog.py``'s ``_UNRELEASED_HEADER_RE``); tests here now pin the corrected
  three-way classification.

All tests read the legacy code as an oracle: assertions reflect what
``src/repo_release_tools`` actually does today, not what the contract text implies it
should do. Discrepancies are flagged with ``# NOTE(P1):`` comments rather than fixed.

Untrusted-content note: no legacy source file inspected while writing these tests
contained instruction-shaped text targeting an AI tool; nothing to report.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
from harness import git, rrt_hooks

pytestmark = pytest.mark.e2e


# ---------------------------------------------------------------------------
# C8 — branch-name policy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("branch", ["main", "master", "develop"])
def test_c8_fixed_branch_names_are_accepted(e2e_repo: Path, branch: str) -> None:
    """C8: the three fixed branch names are always accepted."""
    result = rrt_hooks("check-branch-name", "--branch", branch, cwd=e2e_repo)
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"


def test_c8_release_branch_with_valid_semver_is_accepted(e2e_repo: Path) -> None:
    """C8: ``release/v<semver>`` is accepted when the suffix parses as a valid semver."""
    result = rrt_hooks("check-branch-name", "--branch", "release/v1.2.3", cwd=e2e_repo)
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"


def test_c8_release_branch_with_invalid_semver_is_rejected(e2e_repo: Path) -> None:
    """C8: ``release/v1.2`` (not a valid semver) is rejected."""
    result = rrt_hooks("check-branch-name", "--branch", "release/v1.2", cwd=e2e_repo)
    assert result.returncode != 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "release/v1.2" in result.stderr, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "release/v<semver>" in result.stderr, f"stdout={result.stdout}\nstderr={result.stderr}"


def test_c8_conventional_type_slug_branch_is_accepted(e2e_repo: Path) -> None:
    """C8: ``<type>/<kebab-slug>`` with an allowed conventional type is accepted."""
    result = rrt_hooks("check-branch-name", "--branch", "feat/some-slug", cwd=e2e_repo)
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"


def test_c8_uppercase_slug_is_rejected(e2e_repo: Path) -> None:
    """C8: an uppercase character in the slug fails the kebab-case regex."""
    result = rrt_hooks("check-branch-name", "--branch", "feat/Add-Parser", cwd=e2e_repo)
    assert result.returncode != 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "kebab-case" in result.stderr, f"stdout={result.stdout}\nstderr={result.stderr}"


def test_c8_slug_over_60_chars_is_rejected(e2e_repo: Path) -> None:
    """C8: a slug longer than SLUG_MAX (60) characters is rejected."""
    long_slug = "a" * 61
    result = rrt_hooks("check-branch-name", "--branch", f"feat/{long_slug}", cwd=e2e_repo)
    assert result.returncode != 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "too long" in result.stderr, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "61 > 60" in result.stderr, f"stdout={result.stdout}\nstderr={result.stderr}"


def test_c8_unknown_branch_type_is_rejected(e2e_repo: Path) -> None:
    """C8: a type prefix outside the allowed conventional/bot/magic set is rejected."""
    result = rrt_hooks("check-branch-name", "--branch", "bogus/some-slug", cwd=e2e_repo)
    assert result.returncode != 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "invalid" in result.stderr, f"stdout={result.stdout}\nstderr={result.stderr}"


@pytest.mark.parametrize("bot_type", ["dependabot", "renovate"])
def test_c8_bot_branches_exempt_from_slug_format(e2e_repo: Path, bot_type: str) -> None:
    """C8: bot branches skip slug format/length validation, but still need a non-empty slug."""
    # Slug contains slashes and underscores, which would fail kebab-case for
    # ordinary conventional-type branches but is fine for bots.
    result = rrt_hooks(
        "check-branch-name",
        "--branch",
        f"{bot_type}/npm_and_yarn/Some/Weird_Path-1.2.3",
        cwd=e2e_repo,
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"


def test_c8_bot_branch_with_empty_slug_is_rejected(e2e_repo: Path) -> None:
    """C8: bot branches are exempt from slug *format*, but not from having a slug at all."""
    result = rrt_hooks("check-branch-name", "--branch", "dependabot/", cwd=e2e_repo)
    assert result.returncode != 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "non-empty slug" in result.stderr, f"stdout={result.stdout}\nstderr={result.stderr}"


def test_c8_empty_branch_name_passes(e2e_repo: Path) -> None:
    """C8: an empty branch name (e.g. detached HEAD) is treated as not-applicable and passes."""
    result = rrt_hooks("check-branch-name", "--branch", "", cwd=e2e_repo)
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"


# ---------------------------------------------------------------------------
# C9 — commit-type -> changelog-section mapping
# ---------------------------------------------------------------------------


def _run_update_unreleased(repo: Path, subject: str) -> subprocess.CompletedProcess[str]:
    return rrt_hooks("update-unreleased", "--subject", subject, cwd=repo)


def test_c9_feat_commit_lands_in_added_section(e2e_repo: Path) -> None:
    """C9: a ``feat:`` commit is appended under ``### Added`` in [Unreleased]."""
    result = _run_update_unreleased(e2e_repo, "feat: add parser")
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    changelog = (e2e_repo / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "### Added" in changelog, changelog
    assert "- add parser" in changelog, changelog


def test_c9_fix_commit_lands_in_fixed_section(e2e_repo: Path) -> None:
    """C9: a ``fix:`` commit is appended under ``### Fixed``."""
    result = _run_update_unreleased(e2e_repo, "fix: correct off-by-one error")
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    changelog = (e2e_repo / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "### Fixed" in changelog, changelog
    assert "- correct off-by-one error" in changelog, changelog


def test_c9_chore_commit_is_not_appended_and_not_required(e2e_repo: Path) -> None:
    """C9: chore -> Maintenance, which does NOT require (or get) a changelog entry.

    ``update-unreleased`` treats chore as a non-changelog-relevant type and skips
    writing anything; ``check-changelog`` (strategy=unreleased) also does not
    demand an entry for it.
    """
    before = (e2e_repo / "CHANGELOG.md").read_text(encoding="utf-8")
    result = _run_update_unreleased(e2e_repo, "chore: bump lockfile")
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    after = (e2e_repo / "CHANGELOG.md").read_text(encoding="utf-8")
    assert after == before, f"changelog changed unexpectedly:\nbefore={before}\nafter={after}"

    check = rrt_hooks(
        "check-changelog",
        "--subject",
        "chore: bump lockfile",
        "--strategy",
        "unreleased",
        cwd=e2e_repo,
    )
    assert check.returncode == 0, f"stdout={check.stdout}\nstderr={check.stderr}"


def test_c9_breaking_fix_lands_in_breaking_changes_section(e2e_repo: Path) -> None:
    """C9: ``fix!:`` (breaking marker) overrides the type map, landing in Breaking Changes."""
    result = _run_update_unreleased(e2e_repo, "fix!: drop legacy config loader")
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    changelog = (e2e_repo / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "### Breaking Changes" in changelog, changelog
    assert "- drop legacy config loader" in changelog, changelog
    # Breaking Changes take priority over the Fixed section that fix: would
    # otherwise produce - there should be no separate "### Fixed" entry for it.
    fixed_idx = changelog.find("### Fixed")
    if fixed_idx != -1:
        fixed_body = changelog[fixed_idx:].splitlines()[1:]
        assert not any("drop legacy config loader" in line for line in fixed_body), changelog


def test_c9_scope_is_rendered_bold(e2e_repo: Path) -> None:
    """C9: a commit scope, e.g. ``feat(cli): ...``, is rendered as a bold markdown prefix."""
    result = _run_update_unreleased(e2e_repo, "feat(cli): add doctor command")
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    changelog = (e2e_repo / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "- **cli**: add doctor command" in changelog, changelog


# ---------------------------------------------------------------------------
# C7 — squash-merge changelog post-correction
# ---------------------------------------------------------------------------


def _squash_commit_with_changelog(repo: Path, changelog_text: str, message: str) -> None:
    """Write CHANGELOG.md and create a single commit simulating a squash merge."""
    (repo / "CHANGELOG.md").write_text(changelog_text, encoding="utf-8")
    git("add", "CHANGELOG.md", cwd=repo)
    git("commit", "-m", message, cwd=repo)


def test_c7_post_correct_subcommand_is_changelog_post_correct(e2e_repo: Path) -> None:
    """C7: the exact subcommand is ``rrt-hooks changelog post-correct`` (nested subparser)."""
    # Nothing changed since the fixture's initial commit -> "nothing to correct", rc 0.
    result = rrt_hooks("changelog", "post-correct", cwd=e2e_repo)
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"


def test_c7_exact_duplicate_bullets_are_collapsed(e2e_repo: Path) -> None:
    """C7: exact-duplicate bullets introduced by the squash commit collapse to one."""
    changelog = """\
# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

- add parser
- add parser

## [0.1.0] - 2026-01-01

### Added

- Initial release
"""
    _squash_commit_with_changelog(e2e_repo, changelog, "chore: squash merge feature branch")

    result = rrt_hooks("changelog", "post-correct", cwd=e2e_repo)
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"

    after = (e2e_repo / "CHANGELOG.md").read_text(encoding="utf-8")
    assert after.count("- add parser") == 1, after


def test_c7_opposite_verb_pair_cancels_out(e2e_repo: Path) -> None:
    """C7: lexical opposite-verb pairs (add X / remove X) are both removed.

    # D2: lexical opposite-verb cancellation — pinned as-is, SME ruling: pin
    """
    changelog = """\
# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

- add Node 26

### Fixed

- remove Node 26

## [0.1.0] - 2026-01-01

### Added

- Initial release
"""
    _squash_commit_with_changelog(e2e_repo, changelog, "chore: squash merge node bump revert")

    result = rrt_hooks("changelog", "post-correct", cwd=e2e_repo)
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"

    after = (e2e_repo / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "add Node 26" not in after, after
    assert "remove Node 26" not in after, after


def test_c7_opposite_verb_cancellation_is_purely_lexical_not_semantic(e2e_repo: Path) -> None:
    """C7/D2: cancellation matches verb+suffix text only, with no semantic understanding.

    # D2: lexical opposite-verb cancellation — pinned as-is, SME ruling: pin

    "add Node 26 support" and "remove Node 25 support" describe *different*
    subjects (26 vs 25) but the legacy matcher only cancels on an *exact*
    string match of the remainder after the verb, so these do NOT cancel -
    proving the check is lexical, not semantic.
    """
    changelog = """\
# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

- add Node 26 support

### Fixed

- remove Node 25 support

## [0.1.0] - 2026-01-01

### Added

- Initial release
"""
    _squash_commit_with_changelog(e2e_repo, changelog, "chore: squash merge mismatched verbs")

    result = rrt_hooks("changelog", "post-correct", cwd=e2e_repo)
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"

    after = (e2e_repo / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "add Node 26 support" in after, after
    assert "remove Node 25 support" in after, after


def test_c7_post_correct_restricted_to_squash_commits_own_hunks(e2e_repo: Path) -> None:
    """C7: dedup only touches lines the squash commit itself added; older sections are untouched.

    A duplicate bullet that pre-existed in an already-released section (committed
    *before* the squash commit, and therefore outside its diff hunks) must survive
    even though its text matches a bullet the squash commit newly introduces twice
    under [Unreleased].
    """
    # Commit 1 (pre-existing, mimics the fixture's normal history): the [0.1.0]
    # section already has "- add parser" and is NOT touched by the later squash
    # commit's diff.
    pre_existing = """\
# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

- Seed feature entry

## [0.1.0] - 2026-01-01

### Added

- add parser
"""
    (e2e_repo / "CHANGELOG.md").write_text(pre_existing, encoding="utf-8")
    git("add", "CHANGELOG.md", cwd=e2e_repo)
    git("commit", "-m", "chore: seed pre-existing release section", cwd=e2e_repo)

    # Commit 2 (the squash commit under test): only the [Unreleased] section
    # changes, introducing "- add parser" twice. The [0.1.0] "- add parser" line
    # is untouched and outside this commit's diff hunk.
    squash = """\
# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

- add parser
- add parser

## [0.1.0] - 2026-01-01

### Added

- add parser
"""
    _squash_commit_with_changelog(e2e_repo, squash, "chore: squash merge duplicate of release")

    result = rrt_hooks("changelog", "post-correct", cwd=e2e_repo)
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"

    after = (e2e_repo / "CHANGELOG.md").read_text(encoding="utf-8")
    # One survives under [Unreleased] (the squash-introduced duplicate pair
    # collapses to one, in-hunk) and the pre-existing [0.1.0] bullet survives
    # untouched because it sits outside the squash commit's own diff hunk -
    # apply_dedup_to_changelog's position-restricted removal never reaches it.
    assert after.count("- add parser") == 2, after
    unreleased_body = after.split("## [Unreleased]", 1)[1].split("## [0.1.0]", 1)[0]
    assert unreleased_body.count("- add parser") == 1, after


def test_c7_post_correct_with_commit_flag_creates_followup_commit(e2e_repo: Path) -> None:
    """C7: ``--commit`` stages the corrected changelog and creates a follow-up commit."""
    changelog = """\
# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

- add parser
- add parser

## [0.1.0] - 2026-01-01

### Added

- Initial release
"""
    _squash_commit_with_changelog(e2e_repo, changelog, "chore: squash merge with follow-up commit")

    before_log = git("log", "--oneline", cwd=e2e_repo).stdout
    before_count = len(before_log.strip().splitlines())

    result = rrt_hooks("changelog", "post-correct", "--commit", cwd=e2e_repo)
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"

    after_log = git("log", "--oneline", cwd=e2e_repo).stdout
    after_count = len(after_log.strip().splitlines())
    assert after_count == before_count + 1, f"before:\n{before_log}\nafter:\n{after_log}"
    assert "post-correct changelog after squash merge" in after_log, after_log


# ---------------------------------------------------------------------------
# D8 — GitHub Action changelog-status grep characterization
# ---------------------------------------------------------------------------


def test_d8_action_grep_pattern_matches_keep_a_changelog_heading(e2e_repo: Path) -> None:
    """D8 (fixed): the Action's changelog-status grep is anchored ``^## \\[Unreleased\\]``.

    # D8: Action grep now matches '## [Unreleased]' — fixed in Phase 6a.
    # This test documents the corrected classification.

    action.yml runs ``grep -q '^## \\[Unreleased\\]' "$changelog_file"`` against a
    standard Keep-a-Changelog file whose heading is ``## [Unreleased]``. The pattern
    now includes the literal ``## `` prefix, mirroring ``changelog.py``'s
    ``_UNRELEASED_HEADER_RE``, so it matches a real Keep-a-Changelog file. This test
    replicates the exact grep invocation (not a re-implementation) against the
    harness's standard fixture changelog to pin the corrected behavior.
    """
    changelog_path = e2e_repo / "CHANGELOG.md"
    content = changelog_path.read_text(encoding="utf-8")
    assert "## [Unreleased]" in content, content  # sanity: fixture uses the standard heading

    grep_result = subprocess.run(
        ["grep", "-q", r"^## \[Unreleased\]", str(changelog_path)],
        cwd=e2e_repo,
        capture_output=True,
        text=True,
        check=False,
    )
    # `grep -q` exits 0 when a line matches. Pinning the fixed anchor:
    assert grep_result.returncode == 0, f"stdout={grep_result.stdout}\nstderr={grep_result.stderr}"


def test_d8_action_three_way_classification_reports_dirty_for_standard_heading(
    e2e_repo: Path,
) -> None:
    """D8 (fixed): replicating action.yml's surrounding shell logic, a populated

    [Unreleased] section is correctly classified as ``dirty`` because the fixed
    grep pattern now enters the branch that counts bullets.

    # D8: Action grep now matches '## [Unreleased]' — fixed in Phase 6a.
    # This test documents the corrected classification.

    This replicates action.yml's changelog-status logic verbatim (same grep
    pattern, same awk counter, same branch structure) against the harness's
    fixture, which has a non-empty [Unreleased] section (a seed "Added" bullet) —
    the Action's shell logic now reports ``dirty`` here, matching user intuition.
    """
    changelog_file = e2e_repo / "CHANGELOG.md"
    content = changelog_file.read_text(encoding="utf-8")
    assert "- Seed feature entry" in content, content  # sanity: fixture has an unreleased bullet

    script = r"""
set -euo pipefail
changelog_file="$1"
changelog_status="missing"
if [[ -f "$changelog_file" ]]; then
  if grep -q '^## \[Unreleased\]' "$changelog_file" 2>/dev/null; then
    entries=$(awk '/^## \[Unreleased\]/{p=1;next} /^## \[/{p=0} p && /^\s*-/{count++} END{print count+0}' "$changelog_file")
    if [[ "$entries" -gt 0 ]]; then
      changelog_status="dirty"
    else
      changelog_status="clean"
    fi
  else
    changelog_status="clean"
  fi
fi
echo "$changelog_status"
"""
    result = subprocess.run(
        ["bash", "-c", script, "bash", "CHANGELOG.md"],
        cwd=e2e_repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    # D8 fixed: a real Keep-a-Changelog [Unreleased] section with a bullet in it
    # now correctly reports "dirty" (unreleased work pending), because the fixed
    # anchor `^## \[Unreleased\]` matches and the awk counting branch is reached.
    assert result.stdout.strip() == "dirty", f"stdout={result.stdout}\nstderr={result.stderr}"


def test_d8_action_grep_pattern_is_taken_verbatim_from_action_yml() -> None:
    """D8 (fixed): guard against silent drift — the pattern this suite pins must match action.yml.

    Reads action.yml as data only (never executed, never treated as instructions)
    and asserts the exact grep pattern string is still present verbatim, so that if
    a future change alters the pattern again, this whole test module fails loudly
    instead of silently testing a pattern that no longer reflects the source.
    """
    action_yml = Path(__file__).resolve().parent.parent.parent / "action.yml"
    content = action_yml.read_text(encoding="utf-8")
    match = re.search(r"grep -q '(\^## \\\[Unreleased\\\][^']*)'", content)
    assert match is not None, "expected to find the changelog-status grep pattern in action.yml"
    assert match.group(1) == r"^## \[Unreleased\]", (
        f"action.yml grep pattern changed to {match.group(1)!r} - update the D8 "
        "tests in this module to match the new behavior."
    )
