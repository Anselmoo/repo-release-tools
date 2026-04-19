"""Tests for the [Unreleased] changelog helpers in changelog.py."""

from __future__ import annotations

from repo_release_tools.changelog import (
    append_to_unreleased,
    get_unreleased_entries,
    has_unreleased_section,
    insert_generated_section,
    promote_unreleased,
)

# ---------------------------------------------------------------------------
# Sample changelog fixtures
# ---------------------------------------------------------------------------

EMPTY_CHANGELOG = "# Changelog\n\nAll notable changes to this project will be documented here.\n"

UNRELEASED_EMPTY = """\
# Changelog

## [Unreleased]

## [1.0.0] - 2025-01-01

### Added
- Initial release
"""

UNRELEASED_WITH_ENTRIES = """\
# Changelog

## [Unreleased]

### Fixed
- fix connection timeout

## [1.0.0] - 2025-01-01

### Added
- Initial release
"""

UNRELEASED_MULTI_SECTION = """\
# Changelog

## [Unreleased]

### Added
- new widget

### Fixed
- connection timeout

## [1.0.0] - 2025-01-01
"""

NO_UNRELEASED = """\
# Changelog

## [1.0.0] - 2025-01-01

### Added
- Initial release
"""


# ---------------------------------------------------------------------------
# has_unreleased_section
# ---------------------------------------------------------------------------


def test_has_unreleased_section_detects_present() -> None:
    assert has_unreleased_section(UNRELEASED_EMPTY) is True


def test_has_unreleased_section_detects_with_entries() -> None:
    assert has_unreleased_section(UNRELEASED_WITH_ENTRIES) is True


def test_has_unreleased_section_absent_returns_false() -> None:
    assert has_unreleased_section(NO_UNRELEASED) is False


def test_has_unreleased_section_empty_string() -> None:
    assert has_unreleased_section("") is False


def test_has_unreleased_section_is_case_insensitive() -> None:
    assert has_unreleased_section("## [unreleased]\n") is True


# ---------------------------------------------------------------------------
# get_unreleased_entries
# ---------------------------------------------------------------------------


def test_get_unreleased_entries_returns_empty_when_no_section() -> None:
    assert get_unreleased_entries(NO_UNRELEASED) == []


def test_get_unreleased_entries_returns_empty_for_empty_section() -> None:
    assert get_unreleased_entries(UNRELEASED_EMPTY) == []


def test_get_unreleased_entries_returns_bullets() -> None:
    entries = get_unreleased_entries(UNRELEASED_WITH_ENTRIES)
    assert entries == ["- fix connection timeout"]


def test_get_unreleased_entries_returns_all_bullets_across_sub_sections() -> None:
    entries = get_unreleased_entries(UNRELEASED_MULTI_SECTION)
    assert "- new widget" in entries
    assert "- connection timeout" in entries
    assert len(entries) == 2


def test_get_unreleased_entries_does_not_bleed_into_versioned_section() -> None:
    entries = get_unreleased_entries(UNRELEASED_WITH_ENTRIES)
    # "Initial release" is under [1.0.0], must not appear
    assert all("Initial release" not in e for e in entries)


# ---------------------------------------------------------------------------
# append_to_unreleased
# ---------------------------------------------------------------------------


def test_append_to_unreleased_creates_section_when_absent() -> None:
    result = append_to_unreleased(NO_UNRELEASED, "fix: correct null pointer")
    assert has_unreleased_section(result)
    assert "correct null pointer" in result


def test_append_to_unreleased_places_section_before_existing_versions() -> None:
    result = append_to_unreleased(NO_UNRELEASED, "fix: correct null pointer")
    unreleased_pos = result.index("## [Unreleased]")
    versioned_pos = result.index("## [1.0.0]")
    assert unreleased_pos < versioned_pos


def test_append_to_unreleased_inserts_under_existing_sub_header() -> None:
    result = append_to_unreleased(UNRELEASED_WITH_ENTRIES, "fix: add retry on timeout")
    entries = get_unreleased_entries(result)
    assert "- fix connection timeout" in entries
    assert "- add retry on timeout" in entries


def test_append_to_unreleased_adds_new_sub_header_when_section_differs() -> None:
    result = append_to_unreleased(UNRELEASED_WITH_ENTRIES, "feat: add dark mode")
    assert "### Added" in result
    assert "add dark mode" in result
    assert "fix connection timeout" in result


def test_append_to_unreleased_adds_maintenance_commits() -> None:
    # chore maps to Maintenance — append_to_unreleased writes all conventional
    # commits; it is run_update_unreleased that gates on commit_subject_requires_changelog.
    result = append_to_unreleased(NO_UNRELEASED, "chore: update lockfile")
    assert has_unreleased_section(result)
    assert "### Maintenance" in result
    assert "update lockfile" in result


def test_append_to_unreleased_ignores_non_conventional_commits() -> None:
    result = append_to_unreleased(NO_UNRELEASED, "update stuff")
    assert result == NO_UNRELEASED


def test_append_to_unreleased_handles_scoped_commit() -> None:
    result = append_to_unreleased(EMPTY_CHANGELOG, "fix(auth): handle token expiry")
    assert "**auth**: handle token expiry" in result


def test_append_to_unreleased_handles_breaking_change() -> None:
    result = append_to_unreleased(EMPTY_CHANGELOG, "feat!: drop Python 3.11 support")
    assert "### Breaking Changes" in result
    assert "drop Python 3.11 support" in result


def test_append_to_unreleased_inserts_after_title_line() -> None:
    result = append_to_unreleased(EMPTY_CHANGELOG, "feat: brand new feature")
    lines = result.splitlines()
    # Title must remain first
    assert lines[0].startswith("# Changelog")
    # [Unreleased] must appear before the old body text
    title_idx = next(i for i, line in enumerate(lines) if line.startswith("# Changelog"))
    unreleased_idx = next(i for i, line in enumerate(lines) if "[Unreleased]" in line)
    assert title_idx < unreleased_idx


# ---------------------------------------------------------------------------
# promote_unreleased
# ---------------------------------------------------------------------------


def test_promote_unreleased_renames_header() -> None:
    result = promote_unreleased(UNRELEASED_WITH_ENTRIES, "1.1.0")
    assert "## [1.1.0]" in result
    assert "## [Unreleased]\n\n## [1.1.0]" in result


def test_promote_unreleased_adds_empty_placeholder_above() -> None:
    result = promote_unreleased(UNRELEASED_WITH_ENTRIES, "1.1.0")
    assert result.count("## [Unreleased]") == 1
    # The placeholder must appear before the versioned section
    placeholder_pos = result.index("## [Unreleased]")
    versioned_pos = result.index("## [1.1.0]")
    assert placeholder_pos < versioned_pos


def test_promote_unreleased_preserves_entry_content() -> None:
    result = promote_unreleased(UNRELEASED_WITH_ENTRIES, "1.1.0")
    assert "fix connection timeout" in result


def test_promote_unreleased_noop_when_no_section() -> None:
    result = promote_unreleased(NO_UNRELEASED, "1.1.0")
    assert result == NO_UNRELEASED


def test_promote_unreleased_includes_today_date() -> None:
    import datetime as dt

    result = promote_unreleased(UNRELEASED_WITH_ENTRIES, "2.0.0")
    today = dt.datetime.now(dt.UTC).date().isoformat()
    assert f"## [2.0.0] - {today}" in result


def test_promote_unreleased_does_not_duplicate_existing_versions() -> None:
    result = promote_unreleased(UNRELEASED_WITH_ENTRIES, "1.1.0")
    assert result.count("## [1.0.0]") == 1


def test_append_then_promote_round_trip() -> None:
    """Full round-trip: append a commit, then promote to a version."""
    content = EMPTY_CHANGELOG
    content = append_to_unreleased(content, "feat: add new endpoint")
    content = append_to_unreleased(content, "fix: handle edge case")
    assert get_unreleased_entries(content)  # non-empty before promote

    content = promote_unreleased(content, "0.2.0")
    assert "## [0.2.0]" in content
    # Fresh [Unreleased] placeholder must be empty after promotion
    assert get_unreleased_entries(content) == []


# ---------------------------------------------------------------------------
# append_to_unreleased – deduplication
# ---------------------------------------------------------------------------


def test_append_to_unreleased_no_duplicate_bullet() -> None:
    """Appending the same bullet a second time must leave the content unchanged."""
    content = append_to_unreleased(EMPTY_CHANGELOG, "feat: new shiny thing")
    result = append_to_unreleased(content, "feat: new shiny thing")
    assert result == content
    assert result.count("new shiny thing") == 1


def test_append_to_unreleased_allows_different_bullets_same_section() -> None:
    """Two distinct bullets under the same sub-header are both inserted."""
    content = append_to_unreleased(EMPTY_CHANGELOG, "feat: first feature")
    result = append_to_unreleased(content, "feat: second feature")
    assert "first feature" in result
    assert "second feature" in result


# ---------------------------------------------------------------------------
# insert_generated_section
# ---------------------------------------------------------------------------


def test_insert_generated_section_after_empty_unreleased() -> None:
    """Generated section must be inserted after an existing empty [Unreleased] header."""
    section = "## [1.1.0] - 2025-06-01\n\n### Added\n- new thing\n"
    result = insert_generated_section(UNRELEASED_EMPTY, section)
    unreleased_pos = result.index("## [Unreleased]")
    new_version_pos = result.index("## [1.1.0]")
    old_version_pos = result.index("## [1.0.0]")
    assert unreleased_pos < new_version_pos < old_version_pos


def test_insert_generated_section_adds_unreleased_placeholder_when_absent() -> None:
    """When no [Unreleased] section exists a fresh placeholder must be prepended."""
    section = "## [1.1.0] - 2025-06-01\n\n### Added\n- new thing\n"
    result = insert_generated_section(NO_UNRELEASED, section)
    assert has_unreleased_section(result)
    unreleased_pos = result.index("## [Unreleased]")
    new_version_pos = result.index("## [1.1.0]")
    old_version_pos = result.index("## [1.0.0]")
    assert unreleased_pos < new_version_pos < old_version_pos


def test_insert_generated_section_preserves_title_line() -> None:
    """The # Changelog title must remain at the top after insertion."""
    section = "## [0.2.0] - 2025-06-01\n\n### Added\n- something\n"
    result = insert_generated_section(EMPTY_CHANGELOG, section)
    assert result.startswith("# Changelog")
    assert has_unreleased_section(result)


def test_insert_generated_section_after_empty_unreleased_with_title() -> None:
    """Title line stays first when inserting after an empty [Unreleased]."""
    content = "# Changelog\n\n## [Unreleased]\n\n## [1.0.0] - 2025-01-01\n\n### Added\n- init\n"
    section = "## [1.1.0] - 2025-06-01\n\n### Fixed\n- a bug\n"
    result = insert_generated_section(content, section)
    assert result.startswith("# Changelog")
    assert result.index("## [Unreleased]") < result.index("## [1.1.0]")
    assert result.index("## [1.1.0]") < result.index("## [1.0.0]")
