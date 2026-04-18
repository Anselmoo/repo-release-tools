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
    recommend_init_section_for_cargo,
    recommend_init_section_for_pyproject,
)

# Text guards used to detect whether rrt config is already present in an
# existing manifest file before appending to it.
_PYPROJECT_RRT_GUARD = "[tool.rrt]"
_CARGO_RRT_GUARD_PACKAGE = "package.metadata.rrt"
_CARGO_RRT_GUARD_WORKSPACE = "workspace.metadata.rrt"


def cmd_init(args: argparse.Namespace) -> int:
    """Write a recommended rrt configuration block."""
    target_fmt = getattr(args, "target", "rrt-toml")
    if target_fmt == "pyproject":
        return _init_manifest(args, manifest="pyproject.toml", section_label="[tool.rrt]")
    if target_fmt == "cargo":
        return _init_manifest(args, manifest="Cargo.toml", section_label="[package.metadata.rrt]")
    return _init_rrt_toml(args)


def _init_rrt_toml(args: argparse.Namespace) -> int:
    """Write a recommended local .rrt.toml file."""
    root = Path.cwd()
    target = root / DEFAULT_INIT_CONFIG

    try:
        explicit_config = find_explicit_config_file(root)
    except (ValueError, RuntimeError) as exc:
        print(output.warning(f"Could not read existing configuration: {exc}"), file=sys.stderr)
        return 1

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

    try:
        config_text = recommend_init_config(root)
    except (ValueError, RuntimeError) as exc:
        print(output.warning(f"Could not generate init config: {exc}"), file=sys.stderr)
        return 1

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


def _init_manifest(
    args: argparse.Namespace,
    *,
    manifest: str,
    section_label: str,
) -> int:
    """Append an rrt configuration section to an existing manifest file."""
    root = Path.cwd()
    manifest_path = root / manifest

    if not manifest_path.exists():
        print(
            f"{manifest} does not exist in the current directory. "
            f"Create it first, or run `rrt init` (without --target) to write {DEFAULT_INIT_CONFIG}.",
            file=sys.stderr,
        )
        return 1

    existing_text = manifest_path.read_text(encoding="utf-8")

    already_present = _has_rrt_section(manifest, existing_text)
    if already_present and not args.force:
        print(
            f"{manifest} already contains rrt configuration. "
            "Use --force to append another block anyway.",
            file=sys.stderr,
        )
        return 1

    try:
        if manifest == "pyproject.toml":
            section_text = recommend_init_section_for_pyproject(root)
        else:
            section_text = recommend_init_section_for_cargo(root)
    except (ValueError, RuntimeError) as exc:
        print(output.warning(f"Could not generate init config: {exc}"), file=sys.stderr)
        return 1

    print()
    print(
        output.panel(
            "[DRY RUN] Init config" if args.dry_run else "Init config",
            [("File", manifest), ("Section", section_label)],
        )
    )
    print()

    if args.dry_run:
        print(output.dry_run(f"Would append to {manifest}:"))
        print()
        print(section_text)
        print()
        print(output.dry_run_complete("no files were modified"))
        return 0

    separator = "\n" if existing_text.endswith("\n") else "\n\n"
    manifest_path.write_text(existing_text + separator + section_text + "\n", encoding="utf-8")
    print(output.ok(f"Appended {section_label} to {manifest}"))
    return 0


def _has_rrt_section(manifest: str, text: str) -> bool:
    """Return True if *text* already contains an rrt configuration section."""
    if manifest == "Cargo.toml":
        return _CARGO_RRT_GUARD_PACKAGE in text or _CARGO_RRT_GUARD_WORKSPACE in text
    return _PYPROJECT_RRT_GUARD in text


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the init command."""
    parser = subparsers.add_parser(
        "init",
        help="Generate a recommended rrt configuration for the current repository.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing files.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing .rrt.toml, or append even if rrt config already exists.",
    )
    parser.add_argument(
        "--target",
        choices=["rrt-toml", "pyproject", "cargo"],
        default="rrt-toml",
        metavar="FORMAT",
        help=(
            "Where to write the rrt configuration. "
            "rrt-toml (default): create .rrt.toml; "
            "pyproject: append [tool.rrt] to pyproject.toml; "
            "cargo: append [package.metadata.rrt] to Cargo.toml."
        ),
    )
    parser.set_defaults(handler=cmd_init)
