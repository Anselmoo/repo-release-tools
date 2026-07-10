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
from dataclasses import dataclass

from repo_release_tools.ui import VerbosePrinter

ENV_EPILOG = "  $ rrt env\n  $ rrt env --json"


@dataclass(frozen=True)
class EnvOptions:
    """Typed view of ``argparse.Namespace`` for ``rrt env``.

    Built once via :meth:`from_args` at the top of :func:`cmd_env` so both
    flags it reads have typed read sites instead of ``getattr(args, ...,
    default)`` / ``args.x`` calls throughout the function body.
    """

    json: bool
    verbose: int

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> EnvOptions:
        """Build an :class:`EnvOptions` from a parsed ``argparse.Namespace``.

        ``json`` is given a real default by env_cmd.py's own register(), so a
        Namespace produced by argparse always carries it and is read
        directly. ``verbose`` is set globally by cli.py's parser, but every
        test in tests/commands/test_env_cmd.py that exercises cmd_env calls
        it with ``argparse.Namespace(json=...)`` that never sets ``verbose``,
        so the getattr fallback here absorbs that gap.
        """
        return cls(json=args.json, verbose=getattr(args, "verbose", 0) or 0)


def cmd_env(args: argparse.Namespace) -> int:
    """Render environment details for the current process."""
    opts = EnvOptions.from_args(args)
    verbose = opts.verbose
    values = [
        ("Platform", sys.platform),
        ("Python", sys.version.split()[0]),
        ("Python executable", sys.executable),
        ("TERM", os.environ.get("TERM", "<unset>")),
        ("COLORTERM", os.environ.get("COLORTERM", "<unset>")),
        ("NO_COLOR", "enabled" if os.environ.get("NO_COLOR") else "disabled"),
        ("RRT_COLOR", os.environ.get("RRT_COLOR", "<unset>")),
    ]

    if opts.json:
        sys.stdout.write(json.dumps(dict(values), indent=2) + "\n")
        return 0

    p = VerbosePrinter(verbose=verbose)
    p.ok("Environment")
    for name, value in values:
        p.meta(name, str(value))
    return 0


def _find_duplicates(path_value: str) -> list[str]:
    """Return a list of duplicate path entries in a PATH-like string.

    Normalizes entries with os.path.normpath and ignores empty entries.
    """
    entries = [os.path.normpath(p) for p in path_value.split(os.pathsep) if p]
    seen: set[str] = set()
    dups: list[str] = []
    for e in entries:
        if e in seen and e not in dups:
            dups.append(e)
        seen.add(e)
    return dups


@dataclass(frozen=True)
class EnvCheckOptions:
    """Typed view of ``argparse.Namespace`` for ``rrt env check``.

    Built once via :meth:`from_args` at the top of :func:`cmd_env_check` so
    the single flag it reads has a typed read site instead of a bare
    ``getattr(args, ..., default)`` call.
    """

    verbose: int

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> EnvCheckOptions:
        """Build an :class:`EnvCheckOptions` from a parsed ``argparse.Namespace``.

        ``verbose`` is set globally by cli.py's parser, so a Namespace
        produced by argparse always carries it. The getattr fallback exists
        only because every test in tests/commands/test_env_cmd.py that
        exercises cmd_env_check calls it with
        ``argparse.Namespace(json=False)`` that never sets ``verbose``.
        """
        return cls(verbose=getattr(args, "verbose", 0) or 0)


def cmd_env_check(args: argparse.Namespace) -> int:
    """Run a small set of environment sanity checks.

    Currently checks for duplicate entries in PATH and PYTHONPATH. Returns
    exit code 0 when no issues are found and 1 when any duplicate is detected.
    """
    opts = EnvCheckOptions.from_args(args)
    verbose = opts.verbose

    p = VerbosePrinter(verbose=verbose)

    path = os.environ.get("PATH", "")
    pythonpath = os.environ.get("PYTHONPATH", "")

    path_dups = _find_duplicates(path)
    pypath_dups = _find_duplicates(pythonpath)

    if not path_dups and not pypath_dups:
        p.ok("Environment check: no duplicate PATH/PYTHONPATH entries detected.")
        return 0

    p.warn("Environment check found duplicate entries:")
    if path_dups:
        p.warn("  PATH duplicates:")
        for d in path_dups:
            p.warn(f"    {d}")
    if pypath_dups:
        p.warn("  PYTHONPATH duplicates:")
        for d in pypath_dups:
            p.warn(f"    {d}")

    return 1


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
    # Provide a `rrt env check` sub-action for automated sanity checks.
    sub = parser.add_subparsers(dest="env_action")
    chk = sub.add_parser(
        "check",
        help="Run environment sanity checks (duplicates in PATH/PYTHONPATH).",
        description="Run a small set of environment sanity checks and exit non-zero on failure.",
    )
    chk.add_argument(
        "--json",
        action="store_true",
        help="(Ignored) kept for interface parity with `rrt env`.",
    )
    chk.set_defaults(handler=cmd_env_check)

    parser.set_defaults(handler=cmd_env)
