"""CLI entrypoint for rrt."""

from __future__ import annotations

import argparse
import sys

from repo_release_tools.commands import branch, bump, ci_version, git_cmd, glyphs_cmd, init


def build_parser() -> argparse.ArgumentParser:
    """Build the root parser."""
    parser = argparse.ArgumentParser(
        prog="rrt",
        description="repo-release-tools: branch, commit, and version helpers for Git repositories.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    branch.register(subparsers)
    bump.register(subparsers)
    ci_version.register(subparsers)
    git_cmd.register(subparsers)
    glyphs_cmd.register(subparsers)
    init.register(subparsers)
    return parser


def main() -> None:
    """Program entrypoint."""
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(args.handler(args))


if __name__ == "__main__":
    sys.exit(main())
