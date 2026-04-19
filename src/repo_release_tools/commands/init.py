"""Repository init command."""

from __future__ import annotations

import argparse
import json as _json
import sys
import tomllib

from pathlib import Path

from repo_release_tools import output
from repo_release_tools.config import (
    DEFAULT_INIT_CONFIG,
    find_explicit_config_file,
    recommend_init_config,
    recommend_init_config_for_go,
    recommend_init_section_for_cargo,
    recommend_init_section_for_node,
    recommend_init_section_for_pyproject,
)


def cmd_init(args: argparse.Namespace) -> int:
    """Write a recommended rrt configuration block."""
    target_fmt = getattr(args, "target", "rrt-toml")
    if target_fmt == "pyproject":
        return _init_manifest(args, manifest="pyproject.toml", section_label="[tool.rrt]")
    if target_fmt == "cargo":
        return _init_manifest(args, manifest="Cargo.toml", section_label="[package.metadata.rrt]")
    if target_fmt == "node":
        return _init_package_json(args)
    if target_fmt == "go":
        return _init_rrt_toml(args, go=True)
    return _init_rrt_toml(args)


def _init_rrt_toml(args: argparse.Namespace, *, go: bool = False) -> int:
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
        config_text = recommend_init_config_for_go(root) if go else recommend_init_config(root)
    except (ValueError, RuntimeError) as exc:
        print(output.warning(f"Could not generate init config: {exc}"), file=sys.stderr)
        return 1

    g = output.GLYPHS
    print()
    print(
        output.panel(
            "[DRY RUN] Init config" if args.dry_run else "Init config",
            [(f"{g.git.commit} File", DEFAULT_INIT_CONFIG)],
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

    try:
        already_present = _has_rrt_section(manifest, existing_text)
    except ValueError as exc:
        print(output.warning(str(exc)), file=sys.stderr)
        return 1
    if already_present:
        print(
            f"{manifest} already contains rrt configuration. "
            "Edit the existing rrt section manually instead of appending a duplicate table.",
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

    g = output.GLYPHS
    print()
    print(
        output.panel(
            "[DRY RUN] Init config" if args.dry_run else "Init config",
            [(f"{g.git.commit} File", manifest), ("Section", section_label)],
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


def _init_package_json(args: argparse.Namespace) -> int:
    """Merge the rrt config block into an existing package.json."""
    root = Path.cwd()
    manifest_path = root / "package.json"

    if not manifest_path.exists():
        print(
            "package.json does not exist in the current directory. "
            f"Create it first, or run `rrt init` (without --target) to write {DEFAULT_INIT_CONFIG}.",
            file=sys.stderr,
        )
        return 1

    try:
        data: dict = _json.loads(manifest_path.read_text(encoding="utf-8"))
    except _json.JSONDecodeError as exc:
        print(output.warning(f"Could not parse package.json: {exc}"), file=sys.stderr)
        return 1

    if not isinstance(data, dict):
        print(output.warning("package.json must contain a top-level object."), file=sys.stderr)
        return 1

    if "rrt" in data and not args.force:
        print(
            'package.json already contains an "rrt" key. Use --force to overwrite it.',
            file=sys.stderr,
        )
        return 1

    try:
        rrt_dict = recommend_init_section_for_node(root)
    except (ValueError, RuntimeError) as exc:
        print(output.warning(f"Could not generate init config: {exc}"), file=sys.stderr)
        return 1

    preview = _json.dumps({"rrt": rrt_dict}, indent=2)

    g = output.GLYPHS
    print()
    print(
        output.panel(
            "[DRY RUN] Init config" if args.dry_run else "Init config",
            [(f"{g.git.commit} File", "package.json"), ("Key", '"rrt"')],
        )
    )
    print()

    if args.dry_run:
        print(output.dry_run('Would add "rrt" key to package.json:'))
        print()
        print(preview)
        print()
        print(output.dry_run_complete("no files were modified"))
        return 0

    data["rrt"] = rrt_dict
    manifest_path.write_text(_json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(output.ok('Added "rrt" to package.json'))
    return 0


def _has_rrt_section(manifest: str, text: str) -> bool:
    """Return True if *text* already contains an rrt configuration section."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Could not parse {manifest}: {exc}") from exc
    if manifest == "Cargo.toml":
        package_rrt = data.get("package", {}).get("metadata", {}).get("rrt")
        workspace_rrt = data.get("workspace", {}).get("metadata", {}).get("rrt")
        return isinstance(package_rrt, dict) or isinstance(workspace_rrt, dict)
    tool_rrt = data.get("tool", {}).get("rrt")
    return isinstance(tool_rrt, dict)


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
        help="Overwrite an existing .rrt.toml or package.json rrt key.",
    )
    parser.add_argument(
        "--target",
        choices=["rrt-toml", "pyproject", "cargo", "node", "go"],
        default="rrt-toml",
        metavar="FORMAT",
        help=(
            "Where to write the rrt configuration. "
            "rrt-toml (default): create .rrt.toml; "
            "pyproject: append [tool.rrt] to pyproject.toml; "
            "cargo: append [package.metadata.rrt] to Cargo.toml; "
            'node: merge "rrt" key into package.json; '
            "go: create .rrt.toml with the recommended Go config, "
            "falling back to auto-detected targets when available."
        ),
    )
    parser.set_defaults(handler=cmd_init)
