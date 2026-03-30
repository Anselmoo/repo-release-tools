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
