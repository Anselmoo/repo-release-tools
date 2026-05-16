"""Generate a release body from the [Unreleased] changelog section.

## Overview

`rrt release notes` extracts the current ``[Unreleased]`` section from the
configured changelog and emits it as a formatted release body.  The output is
ready to paste into a GitHub Release, GitLab Release, or any markdown editor.

## Formats

* ``md`` (default) — the raw changelog body stripped of the ``[Unreleased]``
  header line.
* ``gh-release`` — GitHub-flavored release body with a ``## What's Changed``
  header, the changelog bullets, and an automatically generated
  ``## Contributors`` section built from ``git log`` author names since the
  most recent tag.

## Examples

```bash
rrt release notes
rrt release notes --format gh-release
rrt release notes --format md > RELEASE_BODY.md
```
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
