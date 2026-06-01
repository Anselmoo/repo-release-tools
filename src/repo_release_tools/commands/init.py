"""Initialize repo-release-tools configuration for a repository.

## Overview

`rrt init` provides a streamlined onboarding experience for new repositories.
It generates a recommended starter configuration tailored to the project's
language and structure, allowing developers to quickly adopt standard release
and documentation workflows.

The command can either create a standalone `.rrt.toml` file—which is the
preferred method for most projects—or merge the configuration into existing
project manifests like `pyproject.toml`, `Cargo.toml`, or `package.json`.

## Responsibilities

- discover the repository root and identify the primary project language
- generate high-quality, documented starter configurations for multiple targets
- provide language-specific recommendations (e.g., Python, Node.js, Go, Rust)
- ensure safe initialization with dry-run and overwrite protections
- guide the user through the configuration discovery process

## Target Surfaces

- **.rrt.toml** (default): Creates a new, standalone configuration file with
  rich comments and recommended defaults for generic or multi-language projects.
- **pyproject.toml**: Appends a `[tool.rrt]` section to the Python project
  manifest.
- **Cargo.toml**: Appends a `[package.metadata.rrt]` section to the Rust
  crate manifest.
- **package.json**: Merges an `"rrt"` key into the Node.js project manifest.
- **go**: Generates a `.rrt.toml` file pre-configured with Go-oriented
  version targets and release patterns.

## Behavior

- **Safety**: Refuses to overwrite an existing configuration unless `--force`
  is explicitly provided.
- **Discovery**: Warns the user if an existing configuration is found in a
  different location (e.g., if `.rrt.toml` is created but `pyproject.toml`
  already has an `rrt` section).
- **Templates**: Uses internal recommendation engines to populate the starter
  config with sensible `version_targets`, `changelog_file`, and `release_branch`
  patterns.
- **Preview**: Supports `--dry-run` to show the exact content and target path
  before any changes are made.

## Examples

- `rrt init`
- `rrt init --dry-run`
- `rrt init --target pyproject`
- `rrt init --target node --force`
- `rrt init --target go`
- `rrt init --target cargo --dry-run`

## Caveats

- For `pyproject.toml` and `Cargo.toml`, the command only appends to existing
  files; it will not create the manifest if it is missing.
- Standalone `.rrt.toml` files take precedence over manifest-embedded
  configurations during standard tool discovery.
"""

from __future__ import annotations

import argparse
import json as _json
import sys
import tomllib
from pathlib import Path

from repo_release_tools.config import (
    DEFAULT_INIT_CONFIG,
    find_explicit_config_file,
    recommend_init_config,
    recommend_init_config_for_go,
    recommend_init_section_for_cargo,
    recommend_init_section_for_node,
    recommend_init_section_for_pyproject,
)
from repo_release_tools.ui import DryRunPrinter, highlight_terminal
from repo_release_tools.ui import cli_error as render_error

INIT_EPILOG = (
    "  $ rrt init --dry-run\n"
    "  $ rrt init --target pyproject\n"
    "  $ rrt init --target node --force\n"
    "  $ rrt init --target go"
)


def cmd_init(args: argparse.Namespace) -> int:
    """Write a recommended rrt configuration block."""
    _: int = getattr(args, "verbose", 0) or 0
    target_fmt = getattr(args, "target", "rrt-toml")
    match target_fmt:
        case "pyproject":
            return _init_manifest(args, manifest="pyproject.toml", section_label="[tool.rrt]")
        case "cargo":
            return _init_manifest(
                args, manifest="Cargo.toml", section_label="[package.metadata.rrt]"
            )
        case "node":
            return _init_package_json(args)
        case "go":
            return _init_rrt_toml(args, go=True)
    return _init_rrt_toml(args)


def _init_rrt_toml(args: argparse.Namespace, *, go: bool = False) -> int:
    """Write a recommended local .rrt.toml file."""
    root = Path.cwd()
    target = root / DEFAULT_INIT_CONFIG

    try:
        explicit_config = find_explicit_config_file(root)
    except (ValueError, RuntimeError) as exc:
        p = DryRunPrinter(False)
        p.line(f"Could not read existing configuration: {exc}", ok=False, stream=sys.stderr)
        return 1

    if (
        explicit_config is not None
        and explicit_config != target
        and not args.force
        and not args.dry_run
    ):
        relative = explicit_config.relative_to(root)
        p = DryRunPrinter(False)
        p.line(
            render_error(
                f"configuration already exists in {relative}",
                hint=f"Use --force to overwrite {DEFAULT_INIT_CONFIG}.",
                stream=sys.stderr,
            ),
            ok=False,
            stream=sys.stderr,
        )
        return 1

    if target.exists() and not args.force and not args.dry_run:
        p = DryRunPrinter(False)
        p.line(
            render_error(
                f"{DEFAULT_INIT_CONFIG} already exists",
                hint="Use --force to overwrite it.",
                stream=sys.stderr,
            ),
            ok=False,
            stream=sys.stderr,
        )
        return 1

    try:
        config_text = recommend_init_config_for_go(root) if go else recommend_init_config(root)
    except (ValueError, RuntimeError) as exc:
        p = DryRunPrinter(False)
        p.line(f"Could not generate init config: {exc}", ok=False, stream=sys.stderr)
        return 1

    p = DryRunPrinter(args.dry_run)
    p.blank_line()
    p.header("Init config", File=DEFAULT_INIT_CONFIG)

    if args.dry_run:
        p.would_write(DEFAULT_INIT_CONFIG)
        p.section("Preview")
        p.line(highlight_terminal(config_text, "toml"))
        p.footer("no files were modified")
        return 0

    target.write_text(config_text + "\n", encoding="utf-8")
    p.ok(f"Wrote {DEFAULT_INIT_CONFIG}")
    if explicit_config is not None and explicit_config != target:
        relative = explicit_config.relative_to(root)
        p.warn(
            f"{relative} still takes precedence over {DEFAULT_INIT_CONFIG} during config discovery.",
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
        p = DryRunPrinter(False)
        p.line(
            f"{manifest} does not exist in the current directory. "
            f"Create it first, or run `rrt init` (without --target) to write {DEFAULT_INIT_CONFIG}.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    existing_text = manifest_path.read_text(encoding="utf-8")

    try:
        already_present = _has_rrt_section(manifest, existing_text)
    except ValueError as exc:
        p = DryRunPrinter(False)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1
    if already_present and not args.dry_run:
        p = DryRunPrinter(False)
        p.line(
            f"{manifest} already contains rrt configuration. "
            "Edit the existing rrt section manually instead of appending a duplicate table.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    try:
        if manifest == "pyproject.toml":
            section_text = recommend_init_section_for_pyproject(root)
        else:
            section_text = recommend_init_section_for_cargo(root)
    except (ValueError, RuntimeError) as exc:
        p = DryRunPrinter(False)
        p.line(f"Could not generate init config: {exc}", ok=False, stream=sys.stderr)
        return 1

    p = DryRunPrinter(args.dry_run)
    p.blank_line()
    p.header("Init config", File=manifest, Section=section_label)

    if args.dry_run:
        p.would_write(manifest, f"append {section_label}")
        p.section("Preview")
        p.line(highlight_terminal(section_text, "toml"))
        p.footer("no files were modified")
        return 0

    separator = "\n" if existing_text.endswith("\n") else "\n\n"
    manifest_path.write_text(existing_text + separator + section_text + "\n", encoding="utf-8")
    p.ok(f"Appended {section_label} to {manifest}")
    return 0


def _init_package_json(args: argparse.Namespace) -> int:
    """Merge the rrt config block into an existing package.json."""
    root = Path.cwd()
    manifest_path = root / "package.json"

    if not manifest_path.exists():
        p = DryRunPrinter(False)
        p.line(
            "package.json does not exist in the current directory. "
            f"Create it first, or run `rrt init` (without --target) to write {DEFAULT_INIT_CONFIG}.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    try:
        data: dict = _json.loads(manifest_path.read_text(encoding="utf-8"))
    except _json.JSONDecodeError as exc:
        p = DryRunPrinter(False)
        p.line(f"Could not parse package.json: {exc}", ok=False, stream=sys.stderr)
        return 1

    if not isinstance(data, dict):
        p = DryRunPrinter(False)
        p.line("package.json must contain a top-level object.", ok=False, stream=sys.stderr)
        return 1

    if "rrt" in data and not args.force:
        p = DryRunPrinter(False)
        p.line(
            'package.json already contains an "rrt" key. Use --force to overwrite it.',
            ok=False,
            stream=sys.stderr,
        )
        return 1

    try:
        rrt_dict = recommend_init_section_for_node(root)
    except (ValueError, RuntimeError) as exc:
        p = DryRunPrinter(False)
        p.line(f"Could not generate init config: {exc}", ok=False, stream=sys.stderr)
        return 1

    preview = _json.dumps({"rrt": rrt_dict}, indent=2)

    p = DryRunPrinter(args.dry_run)
    p.blank_line()
    p.header("Init config", File="package.json", Key='"rrt"')

    if args.dry_run:
        p.would_write("package.json", 'add "rrt" key')
        p.section("Preview")
        p.line(highlight_terminal(preview, "json"))
        p.footer("no files were modified")
        return 0

    data["rrt"] = rrt_dict
    manifest_path.write_text(_json.dumps(data, indent=2) + "\n", encoding="utf-8")
    p.ok('Added "rrt" to package.json')
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
        description=(
            "Generate a starter rrt configuration for the current repository or manifest.\n\n"
            "By default this writes .rrt.toml. Use --target to append or merge equivalent "
            "configuration into pyproject.toml, Cargo.toml, package.json, or a Go-oriented "
            ".rrt.toml template."
        ),
        epilog=INIT_EPILOG,
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing files.")
    parser.add_argument(
        "--force",
        action="store_true",
        help='Overwrite an existing .rrt.toml or package.json "rrt" key when writing those targets.',
    )
    parser.add_argument(
        "--target",
        choices=["rrt-toml", "pyproject", "cargo", "node", "go"],
        default="rrt-toml",
        metavar="FORMAT",
        help=(
            "Where to write the rrt configuration. "
            "rrt-toml (default): write .rrt.toml; "
            "pyproject: append [tool.rrt] to pyproject.toml; "
            "cargo: append [package.metadata.rrt] to Cargo.toml; "
            'node: merge or replace the "rrt" key in package.json; '
            "go: write .rrt.toml with the recommended Go template."
        ),
    )
    parser.set_defaults(handler=cmd_init)
