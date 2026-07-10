"""Characterization tests for the release/bump flow (MODERNIZATION_BRIEF.md §5).

Pins contract items:

- C1 — atomic multi-file version write (all-or-nothing rollback across targets)
- C2 — preflight gates a mutating bump before any write happens
- C6 — changelog `[Unreleased]` promotion at bump time
- C10 — bump math reachable through the CLI surface

Source anchors cited in the brief:

- ``src/repo_release_tools/version/targets.py:96-136`` (``replace_all_versions_atomic``)
- ``src/repo_release_tools/preflight.py:17-68`` (``run_preflight``)
- ``src/repo_release_tools/commands/bump.py`` (CLI orchestration, changelog promotion)
- ``src/repo_release_tools/version/semver.py:13-94`` (``Version.bump``)

These tests run the ``rrt`` CLI as a real subprocess against temp git repos and
assert on literal, observed output/file content — the legacy code is the
oracle. Where reality surprised the author relative to the brief's prose, a
``# NOTE(P1):`` comment records the discrepancy without "fixing" anything.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest
from harness import PYPROJECT_TEMPLATE, rrt

pytestmark = pytest.mark.e2e

# ---------------------------------------------------------------------------
# C1 — Atomic multi-file version write
# ---------------------------------------------------------------------------

_TWO_TARGET_PYPROJECT_NO_OP = """\
[tool.rrt]
changelog_file = "CHANGELOG.md"

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[[tool.rrt.version_targets]]
path = "version.py"
kind = "pattern"
pattern = '^VERSION = "([^"]+)"$'

[project]
name = "e2e-fixture"
version = "0.1.0"
requires-python = ">=3.12"
"""


def test_c1_atomic_write_rolls_back_all_targets_on_no_op_substitution(
    e2e_repo_factory: Callable[..., Path],
) -> None:
    """A second target that already holds the *new* version makes bump fail entirely.

    ``version.py`` is seeded with ``VERSION = "0.2.0"`` (the value the bump would
    produce). ``replace_version_in_file``/``replace_all_versions_atomic`` treats an
    unchanged version string as a no-op error rather than passing silently (C1).
    Because ``pyproject.toml`` is written first in target order, the atomic-write
    rollback must restore it to its pre-bump content once the second target raises.
    """
    repo = e2e_repo_factory(pyproject=_TWO_TARGET_PYPROJECT_NO_OP)
    (repo / "version.py").write_text('VERSION = "0.2.0"\n', encoding="utf-8")
    from harness import git

    git("add", "-A", cwd=repo)
    git("commit", "-m", "fix: seed version.py with the target version", cwd=repo)

    before_pyproject = (repo / "pyproject.toml").read_text(encoding="utf-8")
    before_version_py = (repo / "version.py").read_text(encoding="utf-8")

    result = rrt("bump", "minor", "--no-update", cwd=repo)

    assert result.returncode != 0, (
        f"expected bump to fail on no-op substitution\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    assert "had no effect" in result.stderr, (
        f"expected the no-op error message\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

    after_pyproject = (repo / "pyproject.toml").read_text(encoding="utf-8")
    after_version_py = (repo / "version.py").read_text(encoding="utf-8")

    assert after_pyproject == before_pyproject, (
        f"pyproject.toml must be rolled back to its original content after the atomic "
        f"write fails\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert 'version = "0.1.0"' in after_pyproject, (
        f"pyproject.toml must still read the pre-bump version 0.1.0\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert after_version_py == before_version_py, (
        f"version.py content must be unchanged\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


_TWO_TARGET_PYPROJECT_UNREADABLE = """\
[tool.rrt]
changelog_file = "CHANGELOG.md"

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[[tool.rrt.version_targets]]
path = "version.py"
kind = "pattern"
pattern = '^VERSION = "([^"]+)"$'

[project]
name = "e2e-fixture"
version = "0.1.0"
requires-python = ">=3.12"
"""


def test_c1_second_target_missing_pattern_is_caught_before_any_write(
    e2e_repo_factory: Callable[..., Path],
) -> None:
    """A second target whose configured pattern never matches fails before writing.

    ``version.py`` here does not contain a matching ``VERSION = "..."`` line at all.
    # NOTE(P1): the brief frames this as C1's atomic-rollback path, but the actual
    # failure point is earlier — ``check_version_targets_readable`` in preflight.py
    # rejects the whole bump (C2) before ``replace_all_versions_atomic`` ever runs,
    # so pyproject.toml is never touched in the first place (nothing to roll back).
    """
    repo = e2e_repo_factory(pyproject=_TWO_TARGET_PYPROJECT_UNREADABLE)
    (repo / "version.py").write_text('VERSION_NO_MATCH = "0.9.9"\n', encoding="utf-8")
    from harness import git

    git("add", "-A", cwd=repo)
    git("commit", "-m", "fix: seed non-matching version.py", cwd=repo)

    before_pyproject = (repo / "pyproject.toml").read_text(encoding="utf-8")

    result = rrt("bump", "minor", "--no-update", cwd=repo)

    assert result.returncode != 0, (
        f"expected bump to fail on unreadable target\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    assert "pre-flight checks failed" in result.stderr, (
        f"expected the preflight failure message\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "Could not match configured pattern" in result.stderr, (
        f"expected the pattern-match diagnostic\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

    after_pyproject = (repo / "pyproject.toml").read_text(encoding="utf-8")
    assert after_pyproject == before_pyproject, (
        f"pyproject.toml must be untouched since preflight rejects the bump before any "
        f"write\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# C2 — Preflight gates a mutating bump
# ---------------------------------------------------------------------------


def test_c2_dirty_working_tree_refuses_bump_before_any_write(e2e_repo: Path) -> None:
    """An uncommitted change makes a real bump fail before writing any files."""
    (e2e_repo / "untracked_dirty.txt").write_text("dirty\n", encoding="utf-8")
    from harness import git

    git("add", "untracked_dirty.txt", cwd=e2e_repo)

    before_pyproject = (e2e_repo / "pyproject.toml").read_text(encoding="utf-8")

    result = rrt("bump", "patch", "--no-update", cwd=e2e_repo)

    assert result.returncode != 0, (
        f"expected bump to refuse a dirty tree\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "Working tree has uncommitted changes" in result.stderr, (
        f"expected the dirty-tree diagnostic\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

    after_pyproject = (e2e_repo / "pyproject.toml").read_text(encoding="utf-8")
    assert after_pyproject == before_pyproject, (
        f"pyproject.toml must be untouched when preflight rejects a dirty tree\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_c2_dry_run_succeeds_despite_dirty_working_tree(e2e_repo: Path) -> None:
    """``--dry-run`` bypasses the working-tree-clean check (characterized, not assumed).

    ``run_preflight`` only calls ``check_working_tree_clean`` when ``dry_run`` is
    False (preflight.py:65), so a dirty tree does not block a dry-run preview.
    """
    (e2e_repo / "untracked_dirty.txt").write_text("dirty\n", encoding="utf-8")
    from harness import git

    git("add", "untracked_dirty.txt", cwd=e2e_repo)

    result = rrt("bump", "patch", "--dry-run", cwd=e2e_repo)

    assert result.returncode == 0, (
        f"expected --dry-run to succeed on a dirty tree\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    assert "0.1.1" in result.stdout, (
        f"expected the previewed new version in output\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    # No real write happened: pyproject.toml on disk still says 0.1.0.
    assert 'version = "0.1.0"' in (e2e_repo / "pyproject.toml").read_text(encoding="utf-8")


def test_c2_missing_version_group_config_refuses_before_working_tree_check(
    e2e_repo_factory: Callable[..., Path],
) -> None:
    """An empty ``[tool.rrt]`` (no version targets) is rejected before any write.

    # NOTE(P1): the brief's C2 anchor (``preflight.py:17-68``) documents
    # ``check_config_consistent`` raising "No version groups are configured in
    # [tool.rrt]." — but with zero ``[[tool.rrt.version_targets]]`` entries and no
    # ``version_groups``, config *loading* itself fails earlier in
    # ``config/core.py``, before ``run_preflight`` is ever reached, with a
    # different message: "Missing [[tool.rrt.version_targets]] configuration".
    # ``check_config_consistent``'s message is therefore reachable only via a
    # different malformed-config shape (e.g. an explicit empty ``version_groups``
    # list), not this one. Pinning the message actually observed here.
    """
    empty_pyproject = """\
[tool.rrt]
changelog_file = "CHANGELOG.md"

[project]
name = "e2e-fixture"
version = "0.1.0"
requires-python = ">=3.12"
"""
    repo = e2e_repo_factory(pyproject=empty_pyproject)

    result = rrt("bump", "patch", "--no-update", cwd=repo)

    assert result.returncode != 0, (
        f"expected bump to fail with no version groups configured\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "Missing [[tool.rrt.version_targets]]" in result.stderr, (
        f"expected the missing-version-targets diagnostic\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# C6 — Changelog [Unreleased] promotion at bump
# ---------------------------------------------------------------------------


def test_c6_bump_promotes_unreleased_and_creates_release_branch_and_commit(
    e2e_repo: Path,
) -> None:
    """A real (non-dry-run) bump promotes [Unreleased], commits, and switches branch.

    Mirrors tests/integration/test_runtime_hybrid.py:490-511 but goes deeper on
    changelog content before/after.
    """
    from harness import git

    before_changelog = (e2e_repo / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## [Unreleased]" in before_changelog
    assert "Seed feature entry" in before_changelog

    result = rrt("bump", "patch", "--no-update", "--no-verify", cwd=e2e_repo)
    assert result.returncode == 0, (
        f"expected a real bump to succeed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

    log = git("log", "--oneline", "-1", cwd=e2e_repo).stdout.strip()
    assert "chore: bump version to v0.1.1" in log, f"unexpected HEAD commit: {log!r}"

    branch = git("rev-parse", "--abbrev-ref", "HEAD", cwd=e2e_repo).stdout.strip()
    assert branch == "release/v0.1.1", f"expected release branch, got {branch!r}"

    pyproject_text = (e2e_repo / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "0.1.1"' in pyproject_text

    after_changelog = (e2e_repo / "CHANGELOG.md").read_text(encoding="utf-8")
    # The old [Unreleased] heading is replaced by a versioned heading with today's date.
    assert "## [0.1.1] -" in after_changelog, (
        f"expected a versioned heading in the changelog\n{after_changelog}"
    )
    # A fresh, empty [Unreleased] placeholder is reinserted above the versioned section.
    assert after_changelog.count("## [Unreleased]") == 1, (
        f"expected exactly one fresh [Unreleased] placeholder\n{after_changelog}"
    )
    unreleased_idx = after_changelog.index("## [Unreleased]")
    versioned_idx = after_changelog.index("## [0.1.1] -")
    assert unreleased_idx < versioned_idx, "the fresh [Unreleased] placeholder must sit above"
    # The promoted section keeps the original bullet content verbatim.
    assert "Seed feature entry" in after_changelog
    # The original 0.1.0 section is preserved further down, unmodified.
    assert "## [0.1.0] - 2026-01-01" in after_changelog


def test_c6_promote_mode_fails_closed_on_empty_unreleased_section(
    e2e_repo_factory: Callable[..., Path],
) -> None:
    """``--changelog-mode promote`` refuses (prints, does not error) when [Unreleased] is empty.

    The command still exits 0 in this branch (update_changelog.py:212-225 prints
    a warning and returns without raising) — pinned as-is.
    """
    empty_unreleased_changelog = """\
# Changelog

## [Unreleased]

## [0.1.0] - 2026-01-01

### Added

- Initial release
"""
    repo = e2e_repo_factory(pyproject=PYPROJECT_TEMPLATE)
    (repo / "CHANGELOG.md").write_text(empty_unreleased_changelog, encoding="utf-8")
    from harness import git

    git("add", "-A", cwd=repo)
    git("commit", "-m", "chore: empty out unreleased section", cwd=repo)

    result = rrt(
        "bump", "patch", "--no-update", "--changelog-mode", "promote", "--no-verify", cwd=repo
    )

    assert result.returncode == 0, (
        f"expected the command to still exit 0\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "nothing to promote" in result.stdout, (
        f"expected the nothing-to-promote diagnostic\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )

    after_changelog = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
    # No versioned heading was created since promotion was skipped.
    assert "## [0.1.1]" not in after_changelog, (
        f"promote mode must not create a versioned section when [Unreleased] is empty\n"
        f"{after_changelog}"
    )
    # The version files were still bumped even though the changelog step no-opped.
    pyproject_text = (repo / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "0.1.1"' in pyproject_text


def test_c6_no_changelog_flag_leaves_changelog_file_untouched(e2e_repo: Path) -> None:
    """``--no-changelog`` skips the changelog update step entirely."""
    before_changelog = (e2e_repo / "CHANGELOG.md").read_text(encoding="utf-8")

    result = rrt("bump", "patch", "--no-update", "--no-changelog", "--no-verify", cwd=e2e_repo)
    assert result.returncode == 0, (
        f"expected bump with --no-changelog to succeed\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )

    after_changelog = (e2e_repo / "CHANGELOG.md").read_text(encoding="utf-8")
    assert after_changelog == before_changelog, (
        f"CHANGELOG.md must be byte-identical when --no-changelog is passed\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# C10 — Bump math via the CLI surface
# ---------------------------------------------------------------------------


def test_c10_bump_minor_from_0_1_0_previews_0_2_0(e2e_repo: Path) -> None:
    """``rrt bump minor`` on 0.1.0 computes 0.2.0 (minor increments, patch resets)."""
    result = rrt("bump", "minor", "--dry-run", cwd=e2e_repo)
    assert result.returncode == 0, result.stderr
    assert "0.1.0" in result.stdout and "0.2.0" in result.stdout, (
        f"expected the 0.1.0 -> 0.2.0 preview\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_c10_bump_major_from_0_1_0_previews_1_0_0(e2e_repo: Path) -> None:
    """``rrt bump major`` resets minor and patch to zero."""
    result = rrt("bump", "major", "--dry-run", cwd=e2e_repo)
    assert result.returncode == 0, result.stderr
    assert "1.0.0" in result.stdout, (
        f"expected the 1.0.0 preview\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_c10_bump_alpha_starts_a_prerelease_channel_on_a_stable_version(e2e_repo: Path) -> None:
    """``rrt bump alpha`` on a stable 0.1.0 starts ``0.1.0-alpha.1`` (kind='alpha')."""
    result = rrt("bump", "alpha", "--dry-run", cwd=e2e_repo)
    assert result.returncode == 0, result.stderr
    assert "0.1.0-alpha.1" in result.stdout, (
        f"expected the alpha channel preview\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_c10_bump_pre_release_advances_the_active_channel_counter(
    e2e_repo_factory: Callable[..., Path],
) -> None:
    """``rrt bump pre-release`` on an existing ``-alpha.1`` version advances to ``-alpha.2``."""
    pre_release_pyproject = """\
[tool.rrt]
changelog_file = "CHANGELOG.md"

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[project]
name = "e2e-fixture"
version = "0.1.0-alpha.1"
requires-python = ">=3.12"
"""
    repo = e2e_repo_factory(pyproject=pre_release_pyproject)

    result = rrt("bump", "pre-release", "--dry-run", cwd=repo)
    assert result.returncode == 0, result.stderr
    assert "0.1.0-alpha.2" in result.stdout, (
        f"expected the advanced pre-release preview\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


def test_c10_bump_rc_switches_channel_and_resets_counter_from_alpha(
    e2e_repo_factory: Callable[..., Path],
) -> None:
    """``rrt bump rc`` while on an ``-alpha`` channel switches to ``-rc.1`` (counter resets)."""
    alpha_pyproject = """\
[tool.rrt]
changelog_file = "CHANGELOG.md"

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[project]
name = "e2e-fixture"
version = "0.1.0-alpha.3"
requires-python = ">=3.12"
"""
    repo = e2e_repo_factory(pyproject=alpha_pyproject)

    result = rrt("bump", "rc", "--dry-run", cwd=repo)
    assert result.returncode == 0, result.stderr
    assert "0.1.0-rc.1" in result.stdout, (
        f"expected the channel-switch preview\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_c10_bump_explicit_version_string_is_accepted_verbatim(e2e_repo: Path) -> None:
    """Passing an explicit version (not a bump kind) previews that literal version."""
    result = rrt("bump", "2.5.0", "--dry-run", cwd=e2e_repo)
    assert result.returncode == 0, result.stderr
    assert "2.5.0" in result.stdout, (
        f"expected the explicit version to be echoed back\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


def test_c10_leading_zero_version_in_pyproject_is_a_clear_error(
    e2e_repo_factory: Callable[..., Path],
) -> None:
    """A leading-zero component (``01.2.0``) fails semver parsing with a readable message."""
    leading_zero_pyproject = """\
[tool.rrt]
changelog_file = "CHANGELOG.md"

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[project]
name = "e2e-fixture"
version = "01.2.0"
requires-python = ">=3.12"
"""
    repo = e2e_repo_factory(pyproject=leading_zero_pyproject)

    result = rrt("bump", "patch", "--no-update", cwd=repo)

    assert result.returncode != 0, (
        f"expected bump to reject a leading-zero version\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    assert "Invalid semver" in result.stderr and "01.2.0" in result.stderr, (
        f"expected a clear invalid-semver diagnostic naming the bad value\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_c10_invalid_bump_kind_and_unparsable_version_is_a_clear_error(e2e_repo: Path) -> None:
    """A bump argument that is neither a known kind nor a parsable version fails clearly."""
    result = rrt("bump", "not-a-kind-or-version", "--dry-run", cwd=e2e_repo)

    assert result.returncode != 0, (
        f"expected an invalid bump value to be rejected\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    assert "Invalid bump value" in result.stderr, (
        f"expected the invalid-bump-value diagnostic\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
