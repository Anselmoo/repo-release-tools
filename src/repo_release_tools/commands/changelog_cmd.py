"""Changelog management subcommands (compare, lint).

This module wires the top-level ``rrt changelog`` command group and dispatches
to its available subcommands.
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
