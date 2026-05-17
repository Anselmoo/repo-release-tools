"""Changelog management command group (compare, lint).

## Overview

`rrt changelog` provides a unified entrypoint for auditing and validating the
project's changelog file. It centralizes utilities for diffing release sections
and enforcing stylistic consistency across entries, ensuring that the
human-readable history remains accurate and professional.

This module acts as a dispatcher for specialized subcommands that handle the
parsing, comparison, and linting of changelog data.

## Responsibilities

- coordinate changelog-related subcommands
- provide a consistent interface for changelog auditing and quality control
- dispatch execution to specialized `compare` and `lint` handlers

## Subcommands

- **compare**: Performs a structured diff between two named release sections.
  It classifies entries as unique to the starting version, common to both, or
  unique to the target version. Useful for PR reviews and release auditing.
- **lint**: Validates the style and structure of changelog entries. It checks
  for sentence casing, trailing punctuation, line length limits, and duplicate
  entries.

## Behavior

- Automatically detects the changelog format (Markdown or RST) based on the
  file extension.
- Discovers the changelog file location from the active `[tool.rrt]`
  configuration.
- Supports both machine-readable (JSON) and human-friendly (colored terminal)
  outputs for auditing subcommands.

## Examples

- `rrt changelog compare v1.2.0 v1.3.0`
- `rrt changelog lint`
- `rrt changelog lint --release v1.5.0 --no-fail`
- `rrt changelog compare v1.0.0 v2.0.0 --format json`

## Related Docs

- [Changelog Comparison](changelog_compare.py)
- [Changelog Linting](changelog_lint.py)
- [rrt bump](bump.py)
"""

from __future__ import annotations

import argparse

from repo_release_tools.commands.changelog_compare import register_subcommand as _register_compare
from repo_release_tools.commands.changelog_lint import register_subcommand as _register_lint


def register(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Register the ``changelog`` command group."""
    parser = subparsers.add_parser(
        "changelog",
        help="Changelog management: compare releases and lint entries.",
        description=(
            "Commands for working with the project changelog.\n\n"
            "Subcommands:\n"
            "  compare  Diff two named release sections.\n"
            "  lint     Lint entries for style consistency.\n"
        ),
    )
    changelog_subparsers = parser.add_subparsers(
        dest="changelog_command",
        metavar="<changelog_command>",
        required=True,
    )
    _register_compare(changelog_subparsers)
    _register_lint(changelog_subparsers)
