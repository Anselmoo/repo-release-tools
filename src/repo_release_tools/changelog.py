"""Changelog rendering helpers."""

from __future__ import annotations

import datetime as dt
import re

from dataclasses import dataclass


CONVENTIONAL_COMMIT_RE = re.compile(
    r"^(?P<type>feat|fix|docs|style|refactor|perf|test|build|ci|chore|deps)"
    r"(?:\((?P<scope>[^)]+)\))?"
    r"(?P<breaking>!)?"
    r"\s*:\s*(?P<desc>.+)$",
    re.IGNORECASE,
)

SECTION_MAP = {
    "feat": "Added",
    "fix": "Fixed",
    "refactor": "Changed",
    "perf": "Changed",
    "style": "Changed",
    "docs": "Documentation",
    "chore": "Maintenance",
    "ci": "Maintenance",
    "build": "Maintenance",
    "test": "Maintenance",
    "deps": "Maintenance",
}

SECTION_ORDER = [
    "Breaking Changes",
    "Added",
    "Fixed",
    "Changed",
    "Documentation",
    "Maintenance",
]


@dataclass(frozen=True)
class ParsedCommit:
    """Parsed conventional commit."""

    type: str
    description: str
    scope: str | None = None
    breaking: bool = False


def parse_conventional_commit(subject: str) -> ParsedCommit | None:
    """Parse a commit subject."""
    if subject.startswith("Merge ") or subject.lower().startswith("release:"):
        return None
    match = CONVENTIONAL_COMMIT_RE.match(subject)
    if match is None:
        return None
    return ParsedCommit(
        type=match.group("type").lower(),
        scope=match.group("scope"),
        description=match.group("desc").strip(),
        breaking=bool(match.group("breaking")),
    )


def build_changelog_section(
    version: str,
    commit_subjects: list[str],
    *,
    include_maintenance: bool,
) -> str:
    """Render a Keep-a-Changelog style section."""
    sections: dict[str, list[str]] = {section: [] for section in SECTION_ORDER}

    for subject in commit_subjects:
        parsed = parse_conventional_commit(subject)
        if parsed is None:
            continue
        section = "Breaking Changes" if parsed.breaking else SECTION_MAP.get(parsed.type)
        if section is None:
            continue
        scope_part = f"**{parsed.scope}**: " if parsed.scope else ""
        sections[section].append(f"- {scope_part}{parsed.description}")

    today = dt.datetime.now(dt.UTC).date().isoformat()
    lines = [f"## [{version}] - {today}", ""]
    rendered_any = False
    for section_name in SECTION_ORDER:
        entries = sections[section_name]
        if not entries:
            continue
        if section_name == "Maintenance" and not include_maintenance:
            continue
        lines.append(f"### {section_name}")
        lines.extend(entries)
        lines.append("")
        rendered_any = True

    if not rendered_any:
        lines.extend(["_No notable changes recorded._", ""])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# [Unreleased] section helpers
# ---------------------------------------------------------------------------

# Matches the top-level "## [Unreleased]" header (case-insensitive).
_UNRELEASED_HEADER_RE = re.compile(r"^## \[Unreleased\]\s*$", re.IGNORECASE | re.MULTILINE)
# Matches any "## [version]" or "## [Unreleased]" header used as a section boundary.
_SECTION_HEADER_RE = re.compile(r"^## \[", re.MULTILINE)
# Matches a leading "# Changelog" or "# CHANGELOG" title line.
_CHANGELOG_TITLE_RE = re.compile(r"^# .+\n", re.MULTILINE)

UNRELEASED_PLACEHOLDER = "## [Unreleased]\n"


def has_unreleased_section(content: str) -> bool:
    """Return True if *content* contains an ``## [Unreleased]`` header."""
    return bool(_UNRELEASED_HEADER_RE.search(content))


def get_unreleased_entries(content: str) -> list[str]:
    """Return bullet lines that exist under the ``## [Unreleased]`` section.

    Returns an empty list when no ``[Unreleased]`` section is present or when
    the section contains no bullet items.
    """
    m = _UNRELEASED_HEADER_RE.search(content)
    if not m:
        return []

    section_start = m.end()
    # Find the start of the next ``## [...]`` header (next versioned section).
    next_section = _SECTION_HEADER_RE.search(content, section_start)
    section_body = content[section_start : next_section.start() if next_section else len(content)]

    return [line for line in section_body.splitlines() if line.strip().startswith("- ")]


def append_to_unreleased(content: str, commit_subject: str) -> str:
    """Insert a parsed bullet from *commit_subject* into the ``[Unreleased]`` section.

    If no ``[Unreleased]`` section exists, one is created at the top of the
    file (after a ``# Changelog`` title line when present).

    Returns the updated content.  If the commit subject is not a conventional
    commit subject, or its parsed type is not mapped in ``SECTION_MAP``, the
    content is returned unchanged.  If the exact bullet is already present in
    the ``[Unreleased]`` section the content is also returned unchanged.
    """
    parsed = parse_conventional_commit(commit_subject)
    if parsed is None:
        return content

    section = "Breaking Changes" if parsed.breaking else SECTION_MAP.get(parsed.type)
    if section is None:
        return content

    scope_part = f"**{parsed.scope}**: " if parsed.scope else ""
    bullet = f"- {scope_part}{parsed.description}"

    if has_unreleased_section(content):
        m = _UNRELEASED_HEADER_RE.search(content)
        assert m is not None  # guaranteed by has_unreleased_section
        insert_pos = m.end()
        # Skip past any existing sub-headers / bullets to find the right place.
        # We insert under the matching sub-header if present, or append it.
        section_end_m = _SECTION_HEADER_RE.search(content, insert_pos)
        section_body_end = section_end_m.start() if section_end_m else len(content)
        section_body = content[insert_pos:section_body_end]

        # Skip if this exact bullet is already present in the section.
        if bullet in section_body.splitlines():
            return content

        sub_header = f"### {section}"
        if sub_header in section_body:
            # Insert bullet right after the matching sub-header line.
            sub_pos = section_body.index(sub_header) + len(sub_header)
            new_body = section_body[:sub_pos] + f"\n{bullet}" + section_body[sub_pos:]
        else:
            # Append a new sub-header + bullet at the end of the unreleased body.
            stripped = section_body.rstrip("\n")
            new_body = stripped + f"\n\n### {section}\n{bullet}\n"

        return content[:insert_pos] + new_body + content[section_body_end:]
    else:
        # Create a new [Unreleased] section at the top of the file.
        new_section = f"## [Unreleased]\n\n### {section}\n{bullet}\n\n"
        title_m = _CHANGELOG_TITLE_RE.match(content)
        if title_m:
            insert_pos = title_m.end()
            return content[:insert_pos] + "\n" + new_section + content[insert_pos:]
        return new_section + content


def insert_generated_section(content: str, section: str) -> str:
    """Insert a generated version *section* into *content*.

    When an (empty) ``[Unreleased]`` section already exists, the generated
    section is placed *after* that placeholder so the placeholder remains at
    the top (Keep-a-Changelog convention).  When no ``[Unreleased]`` section
    is present, a fresh empty placeholder is prepended as a *health-mode*
    guarantee and the generated section follows it.

    A ``# Changelog`` (or similar) title line, when present, is always kept
    at the very top.
    """
    if has_unreleased_section(content):
        m = _UNRELEASED_HEADER_RE.search(content)
        assert m is not None  # guaranteed by has_unreleased_section
        insert_pos = m.end()
        next_section_m = _SECTION_HEADER_RE.search(content, insert_pos)
        next_section_pos = next_section_m.start() if next_section_m else len(content)
        return content[:insert_pos] + "\n" + section + "\n" + content[next_section_pos:]
    else:
        new_content = UNRELEASED_PLACEHOLDER + "\n" + section + "\n"
        title_m = _CHANGELOG_TITLE_RE.match(content)
        if title_m:
            insert_pos = title_m.end()
            return content[:insert_pos] + "\n" + new_content + content[insert_pos:]
        return new_content + content


def promote_unreleased(content: str, version: str) -> str:
    """Rename the ``## [Unreleased]`` header to ``## [version] - YYYY-MM-DD``.

    After promotion an empty ``## [Unreleased]`` placeholder is inserted above
    the newly versioned section so contributors always have a place to add
    entries.

    Returns the updated content.  If no ``[Unreleased]`` section exists the
    content is returned unchanged.
    """
    if not has_unreleased_section(content):
        return content

    today = dt.datetime.now(dt.UTC).date().isoformat()
    versioned_header = f"## [{version}] - {today}"
    updated = _UNRELEASED_HEADER_RE.sub(versioned_header, content, count=1)
    # Re-insert an empty placeholder above the new versioned section.
    updated = updated.replace(versioned_header, f"{UNRELEASED_PLACEHOLDER}\n{versioned_header}", 1)
    return updated
