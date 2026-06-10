"""Tests for the [Unreleased] changelog helpers in changelog.py."""

from __future__ import annotations

import pytest

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


# ---------------------------------------------------------------------------
# detect_changelog_format
# ---------------------------------------------------------------------------

from repo_release_tools.changelog import (  # noqa: E402
    ChangelogFormat,
    detect_changelog_format,
)


def test_detect_changelog_format_md() -> None:
    assert detect_changelog_format("CHANGELOG.md") == ChangelogFormat.MARKDOWN


def test_detect_changelog_format_no_extension() -> None:
    assert detect_changelog_format("CHANGELOG") == ChangelogFormat.MARKDOWN


def test_detect_changelog_format_rst() -> None:
    assert detect_changelog_format("CHANGELOG.rst") == ChangelogFormat.RST


def test_detect_changelog_format_txt() -> None:
    assert detect_changelog_format("CHANGELOG.txt") == ChangelogFormat.RST


def test_detect_changelog_format_txt_case_insensitive() -> None:
    assert detect_changelog_format("CHANGELOG.TXT") == ChangelogFormat.RST


# ---------------------------------------------------------------------------
# RST changelog fixtures
# ---------------------------------------------------------------------------

_RST_EMPTY = """\
Changelog
=========

All notable changes to this project will be documented here.
"""

_RST_UNRELEASED_EMPTY = """\
Changelog
=========

Unreleased
----------

1.0.0 - 2025-01-01
-------------------

Added
~~~~~

- Initial release
"""

_RST_UNRELEASED_WITH_ENTRIES = """\
Changelog
=========

Unreleased
----------

Fixed
~~~~~

- fix connection timeout

1.0.0 - 2025-01-01
-------------------

Added
~~~~~

- Initial release
"""

_RST_NO_UNRELEASED = """\
Changelog
=========

1.0.0 - 2025-01-01
-------------------

Added
~~~~~

- Initial release
"""

# ---------------------------------------------------------------------------
# has_unreleased_section – RST
# ---------------------------------------------------------------------------


def test_has_unreleased_section_rst_detects_present() -> None:
    assert has_unreleased_section(_RST_UNRELEASED_EMPTY, ChangelogFormat.RST) is True


def test_has_unreleased_section_rst_with_entries() -> None:
    assert has_unreleased_section(_RST_UNRELEASED_WITH_ENTRIES, ChangelogFormat.RST) is True


def test_has_unreleased_section_rst_absent() -> None:
    assert has_unreleased_section(_RST_NO_UNRELEASED, ChangelogFormat.RST) is False


def test_has_unreleased_section_rst_empty_changelog() -> None:
    assert has_unreleased_section(_RST_EMPTY, ChangelogFormat.RST) is False


# ---------------------------------------------------------------------------
# get_unreleased_entries – RST
# ---------------------------------------------------------------------------


def test_get_unreleased_entries_rst_with_entries() -> None:
    entries = get_unreleased_entries(_RST_UNRELEASED_WITH_ENTRIES, ChangelogFormat.RST)
    assert entries == ["- fix connection timeout"]


def test_get_unreleased_entries_rst_empty_section() -> None:
    assert get_unreleased_entries(_RST_UNRELEASED_EMPTY, ChangelogFormat.RST) == []


def test_get_unreleased_entries_rst_no_section() -> None:
    assert get_unreleased_entries(_RST_NO_UNRELEASED, ChangelogFormat.RST) == []


# ---------------------------------------------------------------------------
# append_to_unreleased – RST
# ---------------------------------------------------------------------------


def test_append_to_unreleased_rst_creates_section_when_absent() -> None:
    result = append_to_unreleased(_RST_EMPTY, "feat: new widget", ChangelogFormat.RST)
    assert has_unreleased_section(result, ChangelogFormat.RST)
    assert "new widget" in result
    assert "Added" in result
    assert "~" in result  # RST subsection underline


def test_append_to_unreleased_rst_adds_to_existing_section() -> None:
    result = append_to_unreleased(_RST_UNRELEASED_EMPTY, "fix: null pointer", ChangelogFormat.RST)
    assert has_unreleased_section(result, ChangelogFormat.RST)
    assert "null pointer" in result
    assert "Fixed" in result


def test_append_to_unreleased_rst_inserts_under_existing_subsection() -> None:
    result = append_to_unreleased(
        _RST_UNRELEASED_WITH_ENTRIES,
        "fix: another bug",
        ChangelogFormat.RST,
    )
    entries = get_unreleased_entries(result, ChangelogFormat.RST)
    descriptions = [e.lstrip("- ") for e in entries]
    assert "fix connection timeout" in descriptions
    assert "another bug" in descriptions


def test_append_to_unreleased_rst_deduplication() -> None:
    content = append_to_unreleased(_RST_EMPTY, "feat: shiny thing", ChangelogFormat.RST)
    result = append_to_unreleased(content, "feat: shiny thing", ChangelogFormat.RST)
    assert result == content
    assert result.count("shiny thing") == 1


def test_append_to_unreleased_rst_preserves_title() -> None:
    result = append_to_unreleased(_RST_EMPTY, "feat: new widget", ChangelogFormat.RST)
    assert result.startswith("Changelog\n=========")


def test_append_to_unreleased_rst_no_brackets_in_heading() -> None:
    """RST unreleased heading must not use Markdown [Unreleased] notation."""
    result = append_to_unreleased(_RST_EMPTY, "feat: x", ChangelogFormat.RST)
    assert "## [" not in result
    assert "###" not in result


# ---------------------------------------------------------------------------
# build_changelog_section – RST
# ---------------------------------------------------------------------------

from repo_release_tools.changelog import build_changelog_section  # noqa: E402


def test_build_changelog_section_rst_heading_format() -> None:
    result = build_changelog_section(
        "1.1.0",
        ["feat: cool thing"],
        include_maintenance=False,
        fmt=ChangelogFormat.RST,
    )
    # No Markdown brackets around version
    assert "## [" not in result
    assert "### " not in result
    # RST underline present (dash for version heading, tilde for sub-section)
    assert "-" * 3 in result
    assert "~" * 3 in result
    assert "1.1.0" in result
    assert "Added" in result
    assert "cool thing" in result


def test_build_changelog_section_rst_no_notable_changes() -> None:
    result = build_changelog_section(
        "1.1.0",
        [],
        include_maintenance=False,
        fmt=ChangelogFormat.RST,
    )
    assert "1.1.0" in result
    assert "_No notable changes recorded._" in result


# ---------------------------------------------------------------------------
# promote_unreleased – RST
# ---------------------------------------------------------------------------


def test_promote_unreleased_rst_renames_header() -> None:
    result = promote_unreleased(_RST_UNRELEASED_WITH_ENTRIES, "1.1.0", ChangelogFormat.RST)
    assert has_unreleased_section(result, ChangelogFormat.RST)
    assert "1.1.0" in result
    assert "fix connection timeout" in result
    # New Unreleased placeholder above versioned section
    unreleased_pos = result.index("Unreleased\n")
    versioned_pos = result.index("1.1.0")
    assert unreleased_pos < versioned_pos


def test_promote_unreleased_rst_no_op_when_absent() -> None:
    result = promote_unreleased(_RST_NO_UNRELEASED, "1.1.0", ChangelogFormat.RST)
    assert result == _RST_NO_UNRELEASED


def test_promote_unreleased_rst_fresh_placeholder_is_empty() -> None:
    result = promote_unreleased(_RST_UNRELEASED_WITH_ENTRIES, "1.1.0", ChangelogFormat.RST)
    assert get_unreleased_entries(result, ChangelogFormat.RST) == []


# ---------------------------------------------------------------------------
# insert_generated_section – RST
# ---------------------------------------------------------------------------


def test_insert_generated_section_rst_after_empty_unreleased() -> None:
    section = build_changelog_section(
        "1.1.0",
        ["feat: new thing"],
        include_maintenance=False,
        fmt=ChangelogFormat.RST,
    )
    result = insert_generated_section(_RST_UNRELEASED_EMPTY, section, ChangelogFormat.RST)
    assert result.index("Unreleased") < result.index("1.1.0") < result.index("1.0.0")


def test_insert_generated_section_rst_adds_placeholder_when_absent() -> None:
    section = build_changelog_section(
        "1.1.0",
        ["feat: new thing"],
        include_maintenance=False,
        fmt=ChangelogFormat.RST,
    )
    result = insert_generated_section(_RST_NO_UNRELEASED, section, ChangelogFormat.RST)
    assert has_unreleased_section(result, ChangelogFormat.RST)
    assert result.index("Unreleased") < result.index("1.1.0") < result.index("1.0.0")


def test_insert_generated_section_rst_preserves_title() -> None:
    section = build_changelog_section(
        "0.2.0",
        [],
        include_maintenance=False,
        fmt=ChangelogFormat.RST,
    )
    result = insert_generated_section(_RST_EMPTY, section, ChangelogFormat.RST)
    assert result.startswith("Changelog\n=========")
    assert has_unreleased_section(result, ChangelogFormat.RST)


# ---------------------------------------------------------------------------
# append_to_unreleased – blank-line correctness (regression)
# ---------------------------------------------------------------------------

_VERSIONED_AFTER_TITLE = """\
# Changelog

## [1.0.0] - 2025-01-01

### Added
- initial release
"""

_UNRELEASED_WITH_FIXED_AND_VERSION = """\
# Changelog

## [Unreleased]

### Fixed
- fix connection timeout

## [1.0.0] - 2025-01-01

### Added
- initial release
"""

_UNRELEASED_EMPTY_WITH_VERSION = """\
# Changelog

## [Unreleased]

## [1.0.0] - 2025-01-01

### Added
- initial release
"""


def test_append_new_section_preserves_blank_line_before_versioned_section() -> None:
    """Adding a new subsection must keep exactly one blank line before ## [version]."""
    result = append_to_unreleased(_UNRELEASED_WITH_FIXED_AND_VERSION, "feat: add dark mode")
    # The blank line separator between the new bullet and the version header must exist.
    assert "- add dark mode\n\n## [1.0.0]" in result


def test_append_to_empty_unreleased_preserves_blank_line_before_versioned_section() -> None:
    """Filling an empty [Unreleased] must keep exactly one blank line before ## [version]."""
    result = append_to_unreleased(_UNRELEASED_EMPTY_WITH_VERSION, "feat: new feature")
    assert "- new feature\n\n## [1.0.0]" in result


def test_fresh_unreleased_section_no_double_blank_line_before_versioned_section() -> None:
    """Creating [Unreleased] from scratch must not produce two blank lines before ## [version]."""
    result = append_to_unreleased(_VERSIONED_AFTER_TITLE, "fix: correct null pointer")
    # Exactly one blank line between bullet and next version header.
    assert "- correct null pointer\n\n## [1.0.0]" in result
    assert "- correct null pointer\n\n\n## [1.0.0]" not in result


def test_append_multiple_sections_no_extra_blank_lines() -> None:
    """Three successive commits must not accumulate extra blank lines."""
    content = _VERSIONED_AFTER_TITLE
    content = append_to_unreleased(content, "feat: add widget")
    content = append_to_unreleased(content, "fix: fix typo")
    content = append_to_unreleased(content, "feat: add pagination")

    # No run of three or more consecutive newlines anywhere.
    assert "\n\n\n" not in content
    # Version header still present and preceded by exactly one blank line.
    assert "## [1.0.0]" in content
    # Both subsections present.
    assert "### Added" in content
    assert "### Fixed" in content


def test_parse_conventional_commit_skips_release_prefix() -> None:
    from repo_release_tools.changelog import parse_conventional_commit

    assert parse_conventional_commit("release: 1.2.3") is None


def test_build_changelog_section_skips_maintenance_when_disabled() -> None:
    from repo_release_tools.changelog import build_changelog_section

    rendered = build_changelog_section(
        "1.2.3",
        ["chore: tidy lockfile"],
        include_maintenance=False,
    )
    assert "### Maintenance" not in rendered


def test_build_changelog_section_skips_unmapped_type_via_section_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from repo_release_tools import changelog as changelog_module

    original = dict(changelog_module.SECTION_MAP)
    monkeypatch.setitem(changelog_module.SECTION_MAP, "feat", None)
    try:
        rendered = changelog_module.build_changelog_section(
            "1.2.3",
            ["feat: brand new feature"],
            include_maintenance=True,
        )
    finally:
        changelog_module.SECTION_MAP.clear()
        changelog_module.SECTION_MAP.update(original)

    assert "brand new feature" not in rendered


def test_append_to_unreleased_no_title_uses_separator_before_existing_content() -> None:
    content = "## [1.0.0] - 2025-01-01\n\n### Added\n- init\n"
    result = append_to_unreleased(content, "fix: patch edge case")
    assert result.startswith("## [Unreleased]")
    assert "patch edge case" in result


def test_append_to_unreleased_returns_unchanged_when_section_mapping_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from repo_release_tools import changelog as changelog_module

    original = dict(changelog_module.SECTION_MAP)
    monkeypatch.setitem(changelog_module.SECTION_MAP, "feat", None)
    try:
        content = "# Changelog\n"
        result = changelog_module.append_to_unreleased(content, "feat: x")
    finally:
        changelog_module.SECTION_MAP.clear()
        changelog_module.SECTION_MAP.update(original)

    assert result == content


def test_append_to_unreleased_rst_without_title_prepends_section() -> None:
    plain = "1.0.0 - 2025-01-01\n------------------\n"
    result = append_to_unreleased(plain, "fix: rst body", ChangelogFormat.RST)
    assert result.startswith("Unreleased\n")
    assert "rst body" in result


def test_insert_generated_section_without_title_or_unreleased_adds_header() -> None:
    content = "## [1.0.0] - 2025-01-01\n"
    section = "## [1.1.0] - 2025-06-01\n\n### Added\n- thing\n"
    result = insert_generated_section(content, section)
    assert result.startswith("## [Unreleased]\n")
    assert "## [1.1.0]" in result


def test_build_changelog_section_skips_non_conventional_subjects_in_loop() -> None:
    from repo_release_tools.changelog import build_changelog_section

    rendered = build_changelog_section(
        "1.2.3",
        ["not a commit", "fix: valid fix"],
        include_maintenance=True,
    )
    assert "valid fix" in rendered


def test_build_changelog_section_markdown_renders_subheaders() -> None:
    from repo_release_tools.changelog import build_changelog_section

    rendered = build_changelog_section(
        "1.2.3",
        ["fix: valid fix"],
        include_maintenance=True,
    )
    assert "### Fixed" in rendered


# ---------------------------------------------------------------------------
# _build_commit_re with extra commit types
# ---------------------------------------------------------------------------


def test_build_commit_re_with_extra_types_matches_custom() -> None:
    from repo_release_tools.changelog import _build_commit_re

    pattern = _build_commit_re(("hotfix", "spike"))
    m = pattern.match("hotfix: fix the thing")
    assert m is not None
    assert m.group("type").lower() == "hotfix"


def test_build_commit_re_with_extra_types_still_matches_base() -> None:
    from repo_release_tools.changelog import _build_commit_re

    pattern = _build_commit_re(("hotfix",))
    m = pattern.match("feat: new feature")
    assert m is not None


# ---------------------------------------------------------------------------
# get_unreleased_section_body — RST and MD no-match paths
# ---------------------------------------------------------------------------


def test_get_unreleased_section_body_rst_no_match_returns_empty() -> None:
    from repo_release_tools.changelog import ChangelogFormat, get_unreleased_section_body

    content = "1.0.0\n-----\n\n- Some entry\n"
    result = get_unreleased_section_body(content, fmt=ChangelogFormat.RST)
    assert result == ""


def test_get_unreleased_section_body_md_no_match_returns_empty() -> None:
    from repo_release_tools.changelog import ChangelogFormat, get_unreleased_section_body

    content = "## [1.0.0] - 2024-01-01\n\n- Some entry\n"
    result = get_unreleased_section_body(content, fmt=ChangelogFormat.MARKDOWN)
    assert result == ""


def test_get_unreleased_section_body_rst_with_entries() -> None:
    """Returns the body when an RST unreleased section exists with entries."""
    from repo_release_tools.changelog import ChangelogFormat, get_unreleased_section_body

    result = get_unreleased_section_body(_RST_UNRELEASED_WITH_ENTRIES, fmt=ChangelogFormat.RST)
    assert "fix connection timeout" in result


# ---------------------------------------------------------------------------
# list_versioned_sections / get_release_section_body
# ---------------------------------------------------------------------------


_RST_CHANGELOG_WITH_RELEASES = """\
Changelog
=========

Unreleased
----------

[1.7.1] - 2026-06-10
--------------------
Fixed
~~~~~
- correct workflow pipeline

[1.7.0] - 2026-06-09
--------------------
Added
~~~~~
- earlier feature
"""


def test_list_versioned_sections_rst_skips_unreleased() -> None:
    """RST: returns released labels in document order, excluding Unreleased."""
    from repo_release_tools.changelog import ChangelogFormat, list_versioned_sections

    labels = list_versioned_sections(_RST_CHANGELOG_WITH_RELEASES, ChangelogFormat.RST)
    assert labels == ["1.7.1", "1.7.0"]


def test_list_versioned_sections_md_returns_labels_in_order() -> None:
    """Markdown: returns released labels in document order."""
    from repo_release_tools.changelog import list_versioned_sections

    md = "## [Unreleased]\n\n## [2.0.0] - 2026-01-01\n\n## [1.9.0] - 2025-12-01\n"
    assert list_versioned_sections(md) == ["2.0.0", "1.9.0"]


def test_get_release_section_body_rst_returns_body() -> None:
    """RST: extracts the body of a versioned section."""
    from repo_release_tools.changelog import ChangelogFormat, get_release_section_body

    body = get_release_section_body(_RST_CHANGELOG_WITH_RELEASES, "1.7.0", ChangelogFormat.RST)
    assert body is not None
    assert "earlier feature" in body


def test_get_release_section_body_rst_missing_returns_none() -> None:
    """RST: unknown version returns None."""
    from repo_release_tools.changelog import ChangelogFormat, get_release_section_body

    assert (
        get_release_section_body(_RST_CHANGELOG_WITH_RELEASES, "99.0.0", ChangelogFormat.RST)
        is None
    )


def test_get_latest_released_version_returns_none_when_empty() -> None:
    """An empty changelog has no latest released version."""
    from repo_release_tools.changelog import get_latest_released_version

    assert get_latest_released_version("# Changelog\n\n## [Unreleased]\n") is None


# ---------------------------------------------------------------------------
# clear_unreleased_section
# ---------------------------------------------------------------------------


def test_clear_unreleased_section_md_wipes_bullets() -> None:
    """Bullets under `[Unreleased]` are removed; the `[VERSION]` section stays."""
    from repo_release_tools.changelog import clear_unreleased_section

    content = (
        "# Changelog\n\n"
        "## [Unreleased]\n"
        "- forgotten cleanup\n"
        "- another one\n\n"
        "## [1.9.0] - 2026-06-10\n### Added\n- shipped\n"
    )
    cleared = clear_unreleased_section(content)
    assert "forgotten cleanup" not in cleared
    assert "another one" not in cleared
    # [VERSION] survives untouched, including its body.
    assert "## [1.9.0]" in cleared
    assert "- shipped" in cleared
    # The placeholder header is preserved.
    assert "## [Unreleased]" in cleared


def test_clear_unreleased_section_md_no_unreleased_is_noop() -> None:
    """Missing `[Unreleased]` header → content returned unchanged."""
    from repo_release_tools.changelog import clear_unreleased_section

    content = "# Changelog\n\n## [1.9.0] - 2026-06-10\n- shipped\n"
    assert clear_unreleased_section(content) == content


def test_clear_unreleased_section_md_without_next_section() -> None:
    """`[Unreleased]` with bullets and no following section gets trimmed cleanly."""
    from repo_release_tools.changelog import clear_unreleased_section

    content = "# Changelog\n\n## [Unreleased]\n- stuff\n- more stuff\n"
    cleared = clear_unreleased_section(content)
    assert "## [Unreleased]" in cleared
    assert "stuff" not in cleared
    # No spurious trailing artefacts.
    assert cleared.endswith("\n")


def test_clear_unreleased_section_rst() -> None:
    """RST notation: dash-underlined header is preserved, body wiped."""
    from repo_release_tools.changelog import ChangelogFormat, clear_unreleased_section

    content = (
        "Changelog\n=========\n\n"
        "Unreleased\n----------\n"
        "- forgotten\n\n"
        "1.9.0 - 2026-06-10\n------------------\nAdded\n~~~~~\n- shipped\n"
    )
    cleared = clear_unreleased_section(content, ChangelogFormat.RST)
    assert "forgotten" not in cleared
    assert "1.9.0 - 2026-06-10" in cleared
    assert "- shipped" in cleared
    assert "Unreleased\n----------" in cleared


def test_clear_unreleased_section_rst_missing_unreleased_is_noop() -> None:
    """RST: missing Unreleased header → unchanged content."""
    from repo_release_tools.changelog import ChangelogFormat, clear_unreleased_section

    content = "Changelog\n=========\n\n1.0.0 - 2026-01-01\n------------------\n- shipped\n"
    assert clear_unreleased_section(content, ChangelogFormat.RST) == content


def test_clear_unreleased_section_rst_no_following_section() -> None:
    """RST: `[Unreleased]` with no follow-up section drops the body cleanly."""
    from repo_release_tools.changelog import ChangelogFormat, clear_unreleased_section

    content = "Changelog\n=========\n\nUnreleased\n----------\n- stale\n"
    cleared = clear_unreleased_section(content, ChangelogFormat.RST)
    assert "stale" not in cleared
    assert "Unreleased\n----------" in cleared
