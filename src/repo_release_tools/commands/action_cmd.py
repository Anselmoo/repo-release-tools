"""Scaffold GitHub Actions workflows for repo-release-tools.

## Overview

`rrt action` manages the bootstrapping of GitHub Actions workflows to automate
repository policy checks. It centralizes the creation of standard CI
configurations, ensuring that `repo-release-tools` is correctly integrated into
the project's development lifecycle.

The primary subcommand is `init`, which writes a pre-configured workflow file
that performs branch naming, commit subject, and changelog verification on
every push and pull request.

## Responsibilities

- generate starter GitHub Actions workflows using the current `rrt` version
- automate the integration of `repo-release-tools` into the project's CI
- provide safe file operations with dry-run and force-overwrite protections
- emit high-signal, formatted feedback during the scaffolding process

## Workflow Content

The generated workflow (`.github/workflows/rrt.yml`) includes:

- **Triggers**: Runs on `push` to the main branch and on all `pull_request` events.
- **Environment**: Executes on the latest Ubuntu runner.
- **Steps**:
    - Full history checkout (`fetch-depth: 0`) to support git-based checks.
    - Execution of `Anselmoo/repo-release-tools` with standard policy flags
      (branch name, commit subject, and changelog checks).

## Behavior

- Writes to `.github/workflows/rrt.yml` relative to the current working directory.
- Refuses to overwrite an existing workflow unless `--force` is provided.
- Supports `--dry-run` to preview the generated YAML in the terminal without
  writing to disk.
- Uses syntax highlighting when displaying the workflow preview in dry-run mode.

## Examples

- `rrt action init`
- `rrt action init --dry-run`
- `rrt action init --force`

## Caveats

- Requires a Git repository with a `.github/workflows` directory structure
  (automatically created if missing).
- The generated version pin matches the version of `rrt` currently in use.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from repo_release_tools import __version__
from repo_release_tools.ui import DryRunPrinter, VerbosePrinter, highlight_terminal

WORKFLOW_PATH = Path(".github/workflows/rrt.yml")

ACTION_INIT_EXAMPLES = (
    "  $ rrt action init\n  $ rrt action init --dry-run\n  $ rrt action init --force"
)


def _workflow_text() -> str:
    return f"""name: repo-release-tools

on:
  push:
    branches: [main]
  pull_request:

jobs:
  rrt:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
        with:
          fetch-depth: 0
      - uses: Anselmoo/repo-release-tools@v{__version__}
        with:
          check-branch-name: \"true\"
          check-commit-subject: \"true\"
          check-changelog: \"true\"
"""


@dataclass(frozen=True)
class InitOptions:
    """Typed view of ``argparse.Namespace`` for ``rrt action init``.

    Built once via :meth:`from_args` at the top of :func:`cmd_init` so all
    flags it reads have typed read sites instead of ``getattr(args, ...,
    default)`` / ``args.x`` calls throughout the function body.
    """

    dry_run: bool
    force: bool
    verbose: int

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> InitOptions:
        """Build an :class:`InitOptions` from a parsed ``argparse.Namespace``.

        ``dry_run`` and ``force`` are given real defaults by action_cmd.py's
        own register(), so a Namespace produced by argparse always carries
        both and they are read directly. ``verbose`` is set globally by
        cli.py's parser, but every test in tests/commands/test_action_cmd.py
        that exercises cmd_init calls it with
        ``Namespace(dry_run=..., force=...)`` that never sets ``verbose``,
        so the getattr fallback here absorbs that gap.
        """
        return cls(
            dry_run=args.dry_run,
            force=args.force,
            verbose=getattr(args, "verbose", 0) or 0,
        )


def cmd_init(args: argparse.Namespace) -> int:
    """Write a starter GitHub Actions workflow using repo-release-tools."""
    opts = InitOptions.from_args(args)
    verbose = opts.verbose
    root = Path.cwd()
    workflow_path = root / WORKFLOW_PATH
    workflow_text = _workflow_text()

    if workflow_path.exists() and not opts.force and not opts.dry_run:
        p = VerbosePrinter(verbose=verbose)
        p.line(
            f"{WORKFLOW_PATH} already exists. Use --force to overwrite it.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    p = DryRunPrinter(opts.dry_run, verbose=verbose)
    p.blank_line()
    p.header("Action init", File=str(WORKFLOW_PATH))

    if opts.dry_run:
        p.would_write(str(WORKFLOW_PATH))
        p.section("Preview")
        p.line(highlight_terminal(workflow_text, "yaml"))
        p.footer("no files were modified")
        return 0

    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.write_text(workflow_text, encoding="utf-8")
    p.ok(f"Wrote {WORKFLOW_PATH}")
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the action command group."""
    parser = subparsers.add_parser(
        "action",
        help="Scaffold a GitHub Actions workflow for repo-release-tools.",
        description="Scaffold a starter GitHub Actions workflow that runs repo-release-tools checks.",
        epilog=ACTION_INIT_EXAMPLES,
    )
    action_sub = parser.add_subparsers(
        dest="action_command",
        metavar="<action_command>",
        parser_class=type(parser),
        required=True,
    )

    init_parser = action_sub.add_parser(
        "init",
        help="Write a starter workflow that uses repo-release-tools.",
        description="Write a starter .github/workflows/rrt.yml workflow for repo-release-tools CI.",
        epilog=ACTION_INIT_EXAMPLES,
    )
    init_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing files.",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing workflow file.",
    )
    init_parser.set_defaults(handler=cmd_init)
