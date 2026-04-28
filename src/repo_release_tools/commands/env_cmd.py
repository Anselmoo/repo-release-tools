"""Environment introspection command for rrt."""

from __future__ import annotations

import argparse
import json
import os
import sys

from repo_release_tools import output

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
        print(json.dumps(dict(values), indent=2))
        return 0

    print(output.panel("Environment", values, style="single", expand=True, title_mode="row"))
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
