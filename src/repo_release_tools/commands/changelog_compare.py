"""Compare two named changelog release sections.

`rrt changelog compare <from> <to>` parses both release sections and emits a
structured diff: entries unique to *from*, entries in common, and entries unique
to *to*.  Useful for release auditing and PR review.

## Examples

```bash
rrt changelog compare v1.2.0 v1.3.0
rrt changelog compare v1.2.0 v1.3.0 --format json
```
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from repo_release_tools.changelog import ChangelogFormat, detect_changelog_format
from repo_release_tools.config import RrtConfig, VersionGroup, load_or_autodetect_config
from repo_release_tools.ui import error, info, success, warning

_MD_RELEASE_HEADER_RE = re.compile(r"^## \[([^\]]+)\][^\n]*\n", re.MULTILINE)
_MD_SUBSECTION_RE = re.compile(r"^### (.+)$", re.MULTILINE)
_MD_BULLET_RE = re.compile(r"^[-*] .+$", re.MULTILINE)
_RST_RELEASE_HEADER_RE = re.compile(r"^(\S[^\n]*)\n-{3,}$\n?", re.MULTILINE)
_RST_SUBSECTION_RE = re.compile(r"^(\S[^\n]*)\n~{3,}$\n?", re.MULTILINE)
_RST_BULLET_RE = re.compile(r"^[-*] .+$", re.MULTILINE)


def _extract_section_text(content: str, version: str, fmt: ChangelogFormat) -> str | None:
    """Return the raw text under a release header, or None if not found."""
    if fmt == ChangelogFormat.RST:
        for m in _RST_RELEASE_HEADER_RE.finditer(content):
            if m.group(1).strip().lstrip("[").rstrip("]") == version.lstrip("v"):
                section_start = m.end()
                # next section boundary at the same heading level
                next_m = _RST_RELEASE_HEADER_RE.search(content, section_start)
                end = next_m.start() if next_m else len(content)
                return content[section_start:end].strip()
        return None

    for m in _MD_RELEASE_HEADER_RE.finditer(content):
        label = m[1].strip()
        if label.lower() == version.lower().lstrip("v") or label.lower() == version.lower():
            section_start = m.end()
            next_m = _MD_RELEASE_HEADER_RE.search(content, section_start)
            end = next_m.start() if next_m else len(content)
            return content[section_start:end].strip()
    return None


def _parse_subsections(text: str, fmt: ChangelogFormat) -> dict[str, list[str]]:
    """Parse subsections (### Added, etc.) into {section_name: [bullet, ...]}."""
    result: dict[str, list[str]] = {}
    subsection_re = _RST_SUBSECTION_RE if fmt == ChangelogFormat.RST else _MD_SUBSECTION_RE
    bullet_re = _RST_BULLET_RE if fmt == ChangelogFormat.RST else _MD_BULLET_RE

    boundaries = [(m.start(), m[1].strip()) for m in subsection_re.finditer(text)]
    if not boundaries:
        if bullets := [b.strip() for b in bullet_re.findall(text)]:
            result["General"] = bullets
        return result

    for i, (start, name) in enumerate(boundaries):
        end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text)
        chunk = text[start:end]
        if bullets := [b.strip() for b in bullet_re.findall(chunk)]:
            result[name] = bullets

    return result


def _compare_sections(
    from_sections: dict[str, list[str]],
    to_sections: dict[str, list[str]],
) -> dict[str, dict[str, list[str]]]:
    """Return {section: {only_from, common, only_to}} diff."""
    all_sections = sorted(set(from_sections) | set(to_sections))
    result: dict[str, dict[str, list[str]]] = {}
    for section in all_sections:
        from_set = set(from_sections.get(section, []))
        to_set = set(to_sections.get(section, []))
        result[section] = {
            "only_from": sorted(from_set - to_set),
            "common": sorted(from_set & to_set),
            "only_to": sorted(to_set - from_set),
        }
    return result


def _print_comparison(
    diff: dict[str, dict[str, list[str]]],
    from_ver: str,
    to_ver: str,
    *,
    stdout: object,
) -> None:
    """Print a human-readable colored comparison."""
    write = getattr(stdout, "write", None) or (lambda s: None)
    for section, parts in diff.items():
        any_entries = parts["only_from"] or parts["common"] or parts["only_to"]
        if not any_entries:
            continue
        write(f"\n### {section}\n")
        for entry in parts["only_from"]:
            write(f"  - (only in {from_ver}) {entry}\n")
        for entry in parts["common"]:
            write(f"  = (in both)         {entry}\n")
        for entry in parts["only_to"]:
            write(f"  + (only in {to_ver}) {entry}\n")


def cmd_changelog_compare(args: argparse.Namespace) -> int:
    """Compare two changelog release sections."""
    root = Path.cwd()
    try:
        config: RrtConfig = load_or_autodetect_config(root)
    except Exception as exc:
        sys.stderr.write(error(f"Could not load rrt config: {exc}") + "\n")
        return 1

    group_name: str | None = getattr(args, "group", None)
    try:
        group: VersionGroup = config.resolve_group(group_name)
    except Exception as exc:
        sys.stderr.write(error(str(exc)) + "\n")
        return 1

    changelog_path = group.changelog_file
    if not changelog_path.exists():
        sys.stderr.write(error(f"Changelog not found: {changelog_path}") + "\n")
        return 1

    content = changelog_path.read_text(encoding="utf-8")
    fmt = detect_changelog_format(changelog_path)

    from_ver: str = args.from_version
    to_ver: str = args.to_version

    from_text = _extract_section_text(content, from_ver, fmt)
    to_text = _extract_section_text(content, to_ver, fmt)

    if from_text is None or to_text is None:
        for v, text in ((from_ver, from_text), (to_ver, to_text)):
            if text is None:
                sys.stderr.write(error(f"Release {v!r} not found in {changelog_path}") + "\n")
        return 1

    from_sections = _parse_subsections(from_text, fmt)
    to_sections = _parse_subsections(to_text, fmt)

    diff = _compare_sections(from_sections, to_sections)

    output_format: str = getattr(args, "compare_format", "text")

    if output_format == "json":
        sys.stdout.write(
            json.dumps({"from": from_ver, "to": to_ver, "diff": diff}, indent=2) + "\n"
        )
        return 0

    sys.stdout.write(info(f"Comparing {from_ver} → {to_ver} in {changelog_path}") + "\n")
    _print_comparison(diff, from_ver, to_ver, stdout=sys.stdout)

    only_from_total = sum(len(p["only_from"]) for p in diff.values())
    only_to_total = sum(len(p["only_to"]) for p in diff.values())
    common_total = sum(len(p["common"]) for p in diff.values())
    sys.stdout.write(
        f"\n{success(f'{common_total} common, {only_from_total} only in {from_ver},')} "
        f"{warning(f'{only_to_total} only in {to_ver}')}\n"
    )
    return 0


def register_subcommand(changelog_subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Register `compare` under a changelog sub-parser."""
    p = changelog_subparsers.add_parser(
        "compare",
        help="Compare two release sections in the changelog.",
        description=(
            "Parse and diff two named release sections from the configured changelog file.\n\n"
            "Each entry is classified as only-in-FROM, common, or only-in-TO."
        ),
    )
    p.add_argument("from_version", metavar="<from>", help="Release label to compare from.")
    p.add_argument("to_version", metavar="<to>", help="Release label to compare to.")
    p.add_argument(
        "--format",
        dest="compare_format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text).",
    )
    p.add_argument("--group", metavar="NAME", default=None, help="Version group name.")
    p.set_defaults(handler=cmd_changelog_compare)
