"""Generate a release body from the [Unreleased] changelog section.

## Overview

`rrt release notes` provides a utility for extracting and formatting the current
work-in-progress changelog entries into a polished release body. It targets the
`[Unreleased]` section of the configured changelog file, making it easy to
generate content for GitHub Releases, GitLab Releases, or internal release
announcements.

By automating the extraction and contributor discovery, the command ensures
that release notes are accurate, consistent, and reflect the actual changes
captured in the project history.

## Responsibilities

- parse the `[Unreleased]` section from Markdown or RST changelog files
- extract and clean individual bullet points for use in the release body
- discover unique contributors from the Git history since the last release tag
- format the output using standard Markdown or GitHub-flavored styles
- support multi-group configurations to target specific package changelogs

## Output Formats

- **md** (default): Emits the raw, cleaned bullet points from the changelog.
  The `[Unreleased]` header is removed, and the content is presented as a
  simple Markdown list.
- **gh-release**: Emits a rich, GitHub-flavored release body. It includes a
  `## What's Changed` header followed by the changelog entries, and an
  automatically generated `## Contributors` section listing the names of
  everyone who committed since the most recent tag.

## Behavior

- **Detection**: Automatically identifies the changelog format based on the
  file extension.
- **Git Integration**: Uses `git tag` to find the most recent release and
  `git log` to identify contributors for the `gh-release` format.
- **Validation**: Refuses to emit notes if the `[Unreleased]` section is
  missing or empty.
- **Output**: Writes the formatted content directly to standard output,
  allowing for easy piping to files or other tools.

## Examples

- `rrt release notes`
- `rrt release notes --format gh-release`
- `rrt release notes --format md > RELEASE_BODY.md`
- `rrt release notes --group api --format gh-release`

## Caveats

- Relies on the presence of a standard `[Unreleased]` placeholder in the
  changelog.
- Contributor discovery requires a Git history and assumes that release tags
  follow a detectable versioning pattern.
- The command targets only the unreleased changes; for comparing previous
  releases, see `rrt changelog compare`.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from repo_release_tools.changelog import (
    detect_changelog_format,
    get_unreleased_section_body,
    has_unreleased_section,
)
from repo_release_tools.config import (
    format_missing_tool_rrt_guidance,
    is_missing_tool_rrt_error,
    iter_config_files,
    load_or_autodetect_config,
)
from repo_release_tools.ui import DryRunPrinter


def _git_contributors(root: Path) -> list[str]:
    """Return sorted, unique author names from commits since the latest tag."""
    try:
        tags_raw = subprocess.run(
            ["git", "tag", "--sort=-v:refname"],
            capture_output=True,
            text=True,
            check=True,
            cwd=root,
        ).stdout
        tags = [t.strip() for t in tags_raw.splitlines() if t.strip()]
        ref = f"{tags[0]}..HEAD" if tags else "HEAD"
        out = subprocess.run(
            ["git", "log", ref, "--format=%an"],
            capture_output=True,
            text=True,
            check=True,
            cwd=root,
        ).stdout
        names = [line.strip() for line in out.splitlines() if line.strip()]
        return sorted(set(names))
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []


def _format_gh_release(body: str, contributors: list[str]) -> str:
    """Format *body* as a GitHub Release body with an optional Contributors section."""
    lines = ["## What's Changed", ""]
    lines.extend(body.splitlines())
    if contributors:
        lines.extend(["", "## Contributors", ""])
        lines.extend(f"- {name}" for name in contributors)
    return "\n".join(lines) + "\n"


def cmd_release_notes(args: argparse.Namespace) -> int:
    """Emit the [Unreleased] changelog section as a formatted release body."""
    root = Path.cwd()
    output_format = getattr(args, "notes_format", "md")

    try:
        config = load_or_autodetect_config(root)
    except FileNotFoundError:
        checked = iter_config_files(root)
        p = DryRunPrinter(False)
        p.line(format_missing_tool_rrt_guidance(root, checked), ok=False, stream=sys.stderr)
        return 1
    except ValueError as exc:
        if is_missing_tool_rrt_error(exc):
            p = DryRunPrinter(False)
            p.line("No [tool.rrt] configuration found.", ok=False, stream=sys.stderr)
            p.line(
                format_missing_tool_rrt_guidance(root, iter_config_files(root)),
                ok=False,
                stream=sys.stderr,
            )
            return 1
        p = DryRunPrinter(False)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1
    except RuntimeError as exc:
        p = DryRunPrinter(False)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1

    try:
        group = config.resolve_group(getattr(args, "group", None))
    except ValueError as exc:
        p = DryRunPrinter(False)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1

    path = group.changelog_file
    if not path.exists():
        p = DryRunPrinter(False)
        p.line(f"Changelog not found: {path}", ok=False, stream=sys.stderr)
        return 1

    existing = path.read_text(encoding="utf-8")
    fmt = detect_changelog_format(path.name)

    if not has_unreleased_section(existing, fmt):
        p = DryRunPrinter(False)
        p.line("No [Unreleased] section found in the changelog.", ok=False, stream=sys.stderr)
        return 1

    body = get_unreleased_section_body(existing, fmt)
    if not body:
        p = DryRunPrinter(False)
        p.line("[Unreleased] section is empty — nothing to emit.", ok=False, stream=sys.stderr)
        return 1

    if output_format == "gh-release":
        contributors = _git_contributors(root)
        output = _format_gh_release(body, contributors)
    else:
        output = body + "\n"

    sys.stdout.write(output)
    return 0


_RELEASE_NOTES_EPILOG = (
    "  $ rrt release notes\n"
    "  $ rrt release notes --format gh-release\n"
    "  $ rrt release notes --format md > RELEASE_BODY.md"
)


def register_subcommand(
    release_subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Register the ``release notes`` subcommand on *release_subparsers*."""
    parser = release_subparsers.add_parser(
        "notes",
        help="Emit the [Unreleased] changelog section as a formatted release body.",
        description=(
            "Extract the current [Unreleased] section from the configured changelog "
            "and emit it as a formatted release body ready for GitHub, GitLab, or "
            "any markdown editor."
        ),
        epilog=_RELEASE_NOTES_EPILOG,
    )
    parser.add_argument(
        "--format",
        dest="notes_format",
        choices=["md", "gh-release"],
        default="md",
        metavar="FORMAT",
        help="Output format: md (default) or gh-release.",
    )
    parser.add_argument(
        "--group",
        default=None,
        metavar="GROUP",
        help="Version group to read from when multiple groups are configured.",
    )
    parser.set_defaults(handler=cmd_release_notes)
