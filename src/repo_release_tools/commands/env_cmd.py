"""Inspect the process environment and runtime context used by rrt.

## Overview

This command is a compact diagnostics tool for answering "what environment am
I running in?" It does not read repository configuration. Instead, it reports
the interpreter and terminal-related values that can affect rrt output.

## What it reports

The standard text view prints:

- platform
- Python version
- Python executable path
- `TERM`
- `COLORTERM`
- whether `NO_COLOR` is enabled
- `RRT_COLOR`

The `NO_COLOR` field is normalized to a friendly enabled/disabled value rather
than echoing the raw environment variable.

## JSON mode

Use `--json` to emit the same fields as a JSON object. This is useful for
automation, debugging, and documentation tooling that prefers structured
output.

## Examples

```bash
rrt env
rrt env --json
```

## Caveats

- This command reports only a small set of environment values that are most
  relevant to rrt behavior.
- It is a snapshot of the current process, not a probe of the wider shell or
  login environment.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from repo_release_tools.ui import DryRunPrinter

ENV_EPILOG = "  $ rrt env\n  $ rrt env --json"


def cmd_env(args: argparse.Namespace) -> int:
    """Render environment details for the current process."""
    values = [
        ("Platform", sys.platform),
        ("Python", sys.version.split()[0]),
        ("Python executable", sys.executable),
        ("TERM", os.environ.get("TERM", "<unset>")),
        ("COLORTERM", os.environ.get("COLORTERM", "<unset>")),
        ("NO_COLOR", "enabled" if os.environ.get("NO_COLOR") else "disabled"),
        ("RRT_COLOR", os.environ.get("RRT_COLOR", "<unset>")),
    ]

    if args.json:
        sys.stdout.write(json.dumps(dict(values), indent=2) + "\n")
        return 0

    p = DryRunPrinter(dry_run=False)
    p.ok("Environment")
    for name, value in values:
        p.meta(name, str(value))
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the env command."""
    parser = subparsers.add_parser(
        "env",
        help="Inspect the environment and runtime context for rrt.",
        description="Show environment variables and interpreter details that affect rrt behavior.",
        epilog=ENV_EPILOG,
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output the environment as JSON.",
    )
    parser.set_defaults(handler=cmd_env)
