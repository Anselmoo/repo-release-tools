"""Cross-cutting argparse helpers shared across `rrt` command families.

Unlike `_git_shared.py` (scoped to the `rrt git` families), this module holds
helpers with no family-specific logic -- currently just the `--dry-run` flag,
which every mutating subcommand across the CLI registers identically. It
holds no command handlers of its own and is not registered as a subcommand.
"""

from __future__ import annotations

import argparse


def add_dry_run_flag(
    parser: argparse.ArgumentParser | argparse._ArgumentGroup,
    verb: str = "writing files",
    *,
    help_text: str | None = None,
) -> None:
    """Register a shared `--dry-run` flag.

    Most subcommands preview by not doing *something* -- pass `verb` to
    describe that something (e.g. `verb="touching git"`). A handful of
    subcommands describe dry-run behavior that depends on another flag or
    otherwise doesn't fit "Preview without {verb}."; pass `help_text` to
    supply that wording verbatim instead.
    """
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=help_text or f"Preview without {verb}.",
    )
