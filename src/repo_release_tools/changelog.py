"""Changelog rendering helpers."""

from __future__ import annotations

import datetime as dt
import re

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


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


# ---------------------------------------------------------------------------
# Changelog format
# ---------------------------------------------------------------------------


class ChangelogFormat(str, Enum):
    """Supported changelog file formats.

    * ``MARKDOWN`` — standard ``##``/``###`` heading notation (``.md``).
    * ``RST`` — reStructuredText underline notation (``.rst``, ``.txt``).
    """

    MARKDOWN = "markdown"
    RST = "rst"


def detect_changelog_format(path: Path | str) -> ChangelogFormat:
    """Infer the changelog format from the file extension.

    Returns ``ChangelogFormat.RST`` for ``.rst`` and ``.txt`` files because
    both formats use plain-text underline notation.  Returns
    ``ChangelogFormat.MARKDOWN`` for everything else (including ``.md`` and
    extension-less names such as ``CHANGELOG``).
    """
    suffix = Path(path).suffix.lower()
    if suffix in (".rst", ".txt"):
        return ChangelogFormat.RST
    return ChangelogFormat.MARKDOWN


# ---------------------------------------------------------------------------
# Markdown patterns and constants
# ---------------------------------------------------------------------------

# Matches the top-level "## [Unreleased]" header (case-insensitive).
_UNRELEASED_HEADER_RE = re.compile(r"^## \[Unreleased\]\s*$", re.IGNORECASE | re.MULTILINE)
# Matches any "## [version]" or "## [Unreleased]" header used as a section boundary.
_SECTION_HEADER_RE = re.compile(r"^## \[", re.MULTILINE)
# Matches a leading "# Changelog" or "# CHANGELOG" title line.
_CHANGELOG_TITLE_RE = re.compile(r"^# .+\n", re.MULTILINE)

UNRELEASED_PLACEHOLDER = "## [Unreleased]\n"

# ---------------------------------------------------------------------------
# RST patterns and constants
# ---------------------------------------------------------------------------

# Underline characters for each heading level in generated RST changelogs.
_RST_SECTION_CHAR = "-"      # version / Unreleased level  (## in Markdown)
_RST_SUBSECTION_CHAR = "~"   # sub-section level           (### in Markdown)

# "Unreleased" or "[Unreleased]" heading followed immediately by a dash underline.
# The optional trailing \n? is consumed so that m.end() lands after the underline line.
# Requires 3+ dashes anchored to end-of-line to avoid matching bullet points ("- text").
_RST_UNRELEASED_HEADER_RE = re.compile(
    r"^(?:\[Unreleased\]|Unreleased) *\n-{3,}$\n?",
    re.IGNORECASE | re.MULTILINE,
)
# Any section at the version/unreleased level: text line + dash underline (3+ dashes,
# end-of-line anchored so that bullet points starting with "- " don't match).
_RST_SECTION_BOUNDARY_RE = re.compile(r"^\S[^\n]*\n-{3,}$\n?", re.MULTILINE)
# Document title: text line + equals underline (3+ chars, end-of-line anchored).
_RST_TITLE_RE = re.compile(r"^.+\n={3,}$\n?", re.MULTILINE)

# "Unreleased\n----------\n"
RST_UNRELEASED_PLACEHOLDER = f"Unreleased\n{_RST_SECTION_CHAR * len('Unreleased')}\n"


def _rst_heading(text: str, underline_char: str) -> str:
    """Render *text* as an RST heading with the given *underline_char*."""
    return f"{text}\n{underline_char * max(len(text), 3)}\n"


# ---------------------------------------------------------------------------
# build_changelog_section
# ---------------------------------------------------------------------------


def build_changelog_section(
    version: str,
    commit_subjects: list[str],
    *,
    include_maintenance: bool,
    fmt: ChangelogFormat = ChangelogFormat.MARKDOWN,
) -> str:
    """Render a Keep-a-Changelog style section.

    The *fmt* parameter controls whether Markdown (``## [version]``,
    ``### Sub``) or RST underline (``version - date\\n---``, ``Sub\\n~~~``)
    notation is used.
    """
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
    if fmt == ChangelogFormat.RST:
        version_text = f"{version} - {today}"
        lines: list[str] = [version_text, _RST_SECTION_CHAR * max(len(version_text), 3), ""]
    else:
        lines = [f"## [{version}] - {today}", ""]

    rendered_any = False
    for section_name in SECTION_ORDER:
        entries = sections[section_name]
        if not entries:
            continue
        if section_name == "Maintenance" and not include_maintenance:
            continue
        if fmt == ChangelogFormat.RST:
            lines.append(section_name)
            lines.append(_RST_SUBSECTION_CHAR * max(len(section_name), 3))
        else:
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


def has_unreleased_section(
    content: str,
    fmt: ChangelogFormat = ChangelogFormat.MARKDOWN,
) -> bool:
    """Return True if *content* contains an ``[Unreleased]`` / ``Unreleased`` header."""
    if fmt == ChangelogFormat.RST:
        return bool(_RST_UNRELEASED_HEADER_RE.search(content))
    return bool(_UNRELEASED_HEADER_RE.search(content))


def get_unreleased_entries(
    content: str,
    fmt: ChangelogFormat = ChangelogFormat.MARKDOWN,
) -> list[str]:
    """Return bullet lines that exist under the ``[Unreleased]`` / ``Unreleased`` section.

    Returns an empty list when no ``[Unreleased]`` section is present or when
    the section contains no bullet items.

    The *fmt* parameter selects Markdown (default) or RST pattern matching.
    """
    if fmt == ChangelogFormat.RST:
        m = _RST_UNRELEASED_HEADER_RE.search(content)
        if not m:
            return []
        section_start = m.end()
        next_section = _RST_SECTION_BOUNDARY_RE.search(content, section_start)
    else:
        m = _UNRELEASED_HEADER_RE.search(content)
        if not m:
            return []
        section_start = m.end()
        next_section = _SECTION_HEADER_RE.search(content, section_start)

    section_body = content[section_start : next_section.start() if next_section else len(content)]
    return [line for line in section_body.splitlines() if line.strip().startswith("- ")]


def append_to_unreleased(
    content: str,
    commit_subject: str,
    fmt: ChangelogFormat = ChangelogFormat.MARKDOWN,
) -> str:
    """Insert a parsed bullet from *commit_subject* into the ``[Unreleased]`` section.

    If no ``[Unreleased]`` section exists, one is created at the top of the
    file (after a title line when present).

    Returns the updated content.  If the commit subject is not a conventional
    commit subject, or its parsed type is not mapped in ``SECTION_MAP``, the
    content is returned unchanged.  If the exact bullet is already present in
    the ``[Unreleased]`` section the content is also returned unchanged.

    The *fmt* parameter selects Markdown (default) or RST underline notation.
    """
    parsed = parse_conventional_commit(commit_subject)
    if parsed is None:
        return content

    section = "Breaking Changes" if parsed.breaking else SECTION_MAP.get(parsed.type)
    if section is None:
        return content

    scope_part = f"**{parsed.scope}**: " if parsed.scope else ""
    bullet = f"- {scope_part}{parsed.description}"

    if fmt == ChangelogFormat.RST:
        return _append_to_unreleased_rst(content, section, bullet)

    # --- Markdown ---
    if has_unreleased_section(content):
        m = _UNRELEASED_HEADER_RE.search(content)
        assert m is not None  # guaranteed by has_unreleased_section
        insert_pos = m.end()
        section_end_m = _SECTION_HEADER_RE.search(content, insert_pos)
        section_body_end = section_end_m.start() if section_end_m else len(content)
        section_body = content[insert_pos:section_body_end]

        # Skip if this exact bullet is already present in the section.
        if bullet in section_body.splitlines():
            return content

        sub_header = f"### {section}"
        if sub_header in section_body:
            sub_pos = section_body.index(sub_header) + len(sub_header)
            new_body = section_body[:sub_pos] + f"\n{bullet}" + section_body[sub_pos:]
        else:
            stripped = section_body.rstrip("\n")
            new_body = stripped + f"\n\n### {section}\n{bullet}\n"

        return content[:insert_pos] + new_body + content[section_body_end:]
    else:
        new_section = f"## [Unreleased]\n\n### {section}\n{bullet}\n\n"
        title_m = _CHANGELOG_TITLE_RE.match(content)
        if title_m:
            insert_pos = title_m.end()
            return content[:insert_pos] + "\n" + new_section + content[insert_pos:]
        return new_section + content


def _append_to_unreleased_rst(content: str, section: str, bullet: str) -> str:
    """RST-specific implementation for appending a bullet to the Unreleased section."""
    sub_header_re = re.compile(
        rf"^{re.escape(section)}\n{re.escape(_RST_SUBSECTION_CHAR)}{{3,}}$",
        re.MULTILINE,
    )

    if has_unreleased_section(content, ChangelogFormat.RST):
        m = _RST_UNRELEASED_HEADER_RE.search(content)
        assert m is not None  # guaranteed by has_unreleased_section
        insert_pos = m.end()
        next_section_m = _RST_SECTION_BOUNDARY_RE.search(content, insert_pos)
        section_body_end = next_section_m.start() if next_section_m else len(content)
        section_body = content[insert_pos:section_body_end]

        # Skip if this exact bullet is already present in the section.
        if bullet in section_body.splitlines():
            return content

        sub_match = sub_header_re.search(section_body)
        if sub_match:
            sub_pos = sub_match.end()
            new_body = section_body[:sub_pos] + f"\n{bullet}" + section_body[sub_pos:]
        else:
            stripped = section_body.rstrip("\n")
            new_body = (
                stripped + f"\n\n{_rst_heading(section, _RST_SUBSECTION_CHAR)}{bullet}\n"
            )

        return content[:insert_pos] + new_body + content[section_body_end:]
    else:
        new_section = (
            f"{RST_UNRELEASED_PLACEHOLDER}\n"
            f"{_rst_heading(section, _RST_SUBSECTION_CHAR)}"
            f"{bullet}\n\n"
        )
        title_m = _RST_TITLE_RE.match(content)
        if title_m:
            insert_pos = title_m.end()
            return content[:insert_pos] + "\n" + new_section + content[insert_pos:]
        return new_section + content


def insert_generated_section(
    content: str,
    section: str,
    fmt: ChangelogFormat = ChangelogFormat.MARKDOWN,
) -> str:
    """Insert a generated version *section* into *content*.

    When an (empty) ``[Unreleased]`` section already exists, the generated
    section is placed *after* that placeholder so the placeholder remains at
    the top (Keep-a-Changelog convention).  When no ``[Unreleased]`` section
    is present, a fresh empty placeholder is prepended as a *health-mode*
    guarantee and the generated section follows it.

    A title line, when present, is always kept at the very top.

    The *fmt* parameter selects Markdown (default) or RST underline notation.
    """
    if fmt == ChangelogFormat.RST:
        unreleased_header_re = _RST_UNRELEASED_HEADER_RE
        section_boundary_re = _RST_SECTION_BOUNDARY_RE
        unreleased_placeholder = RST_UNRELEASED_PLACEHOLDER
        title_re = _RST_TITLE_RE
    else:
        unreleased_header_re = _UNRELEASED_HEADER_RE
        section_boundary_re = _SECTION_HEADER_RE
        unreleased_placeholder = UNRELEASED_PLACEHOLDER
        title_re = _CHANGELOG_TITLE_RE

    if has_unreleased_section(content, fmt):
        m = unreleased_header_re.search(content)
        assert m is not None  # guaranteed by has_unreleased_section
        insert_pos = m.end()
        next_section_m = section_boundary_re.search(content, insert_pos)
        next_section_pos = next_section_m.start() if next_section_m else len(content)
        return content[:insert_pos] + "\n" + section + "\n" + content[next_section_pos:]
    else:
        new_content = unreleased_placeholder + "\n" + section + "\n"
        title_m = title_re.match(content)
        if title_m:
            insert_pos = title_m.end()
            return content[:insert_pos] + "\n" + new_content + content[insert_pos:]
        return new_content + content


def promote_unreleased(
    content: str,
    version: str,
    fmt: ChangelogFormat = ChangelogFormat.MARKDOWN,
) -> str:
    """Rename the ``[Unreleased]`` header to ``[version] - YYYY-MM-DD``.

    After promotion an empty ``[Unreleased]`` placeholder is inserted above
    the newly versioned section so contributors always have a place to add
    entries.

    Returns the updated content.  If no ``[Unreleased]`` section exists the
    content is returned unchanged.

    The *fmt* parameter selects Markdown (default) or RST underline notation.
    """
    if not has_unreleased_section(content, fmt):
        return content

    today = dt.datetime.now(dt.UTC).date().isoformat()

    if fmt == ChangelogFormat.RST:
        m = _RST_UNRELEASED_HEADER_RE.search(content)
        assert m is not None  # guaranteed by has_unreleased_section
        versioned_text = f"{version} - {today}"
        versioned_heading = (
            f"{versioned_text}\n{_RST_SECTION_CHAR * max(len(versioned_text), 3)}"
        )
        updated = content[: m.start()] + versioned_heading + content[m.end() :]
        updated = updated.replace(
            versioned_heading,
            f"{RST_UNRELEASED_PLACEHOLDER}\n{versioned_heading}",
            1,
        )
        return updated

    versioned_header = f"## [{version}] - {today}"
    updated = _UNRELEASED_HEADER_RE.sub(versioned_header, content, count=1)
    updated = updated.replace(versioned_header, f"{UNRELEASED_PLACEHOLDER}\n{versioned_header}", 1)
    return updated
