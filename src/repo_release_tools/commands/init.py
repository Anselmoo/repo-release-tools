"""Repository init command."""

from __future__ import annotations

import argparse
import sys

from pathlib import Path

from repo_release_tools import output
from repo_release_tools.config import (
    DEFAULT_INIT_CONFIG,
    find_explicit_config_file,
    recommend_init_config,
)


def cmd_init(args: argparse.Namespace) -> int:
    """Write a recommended local .rrt.toml file."""
    root = Path.cwd()
    target = root / DEFAULT_INIT_CONFIG
    explicit_config = find_explicit_config_file(root)

    if explicit_config is not None and explicit_config != target and not args.force:
        relative = explicit_config.relative_to(root)
        print(
            f"Explicit rrt configuration already exists in {relative}. "
            f"Refusing to add {DEFAULT_INIT_CONFIG}; use --force to overwrite it anyway.",
            file=sys.stderr,
        )
        return 1

    if target.exists() and not args.force:
        print(
            f"{DEFAULT_INIT_CONFIG} already exists. Use --force to overwrite it.",
            file=sys.stderr,
        )
        return 1

    config_text = recommend_init_config(root)

    print()
    print(
        output.panel(
            "[DRY RUN] Init config" if args.dry_run else "Init config",
            [("File", DEFAULT_INIT_CONFIG)],
        )
    )
    print()

    if args.dry_run:
        print(output.dry_run(f"Would write {DEFAULT_INIT_CONFIG}:"))
        print()
        print(config_text)
        print()
        print(output.dry_run_complete("no files were modified"))
        return 0

    target.write_text(config_text + "\n", encoding="utf-8")
    print(output.ok(f"Wrote {DEFAULT_INIT_CONFIG}"))
    if explicit_config is not None and explicit_config != target:
        relative = explicit_config.relative_to(root)
        print(
            output.warning(
                f"{relative} still takes precedence over {DEFAULT_INIT_CONFIG} during config discovery."
            )
        )
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the init command."""
    parser = subparsers.add_parser(
        "init",
        help="Generate a recommended .rrt.toml for the current repository.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing files.")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing .rrt.toml.")
    parser.set_defaults(handler=cmd_init)
