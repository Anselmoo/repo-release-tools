"""Inspect the resolved rrt configuration for the current repository.

## Overview

This command shows the configuration that rrt will actually use after
repository discovery and any automatic config-file detection. It is the
fastest way to answer:

- Which config file did rrt pick?
- Which version groups were resolved?
- Which files and targets belong to each group?

Use this command when you want to verify release metadata before running a
bump, changelog update, or release workflow.

## What the command reports

The default view renders a tree-style summary with:

- the config file source, or an "auto-detected" notice when no explicit file
  was selected
- the number of version groups in the resolved configuration
- each version group name
- per-group details for:
  - `release_branch`
  - `changelog`
  - `lock_command`, when configured
  - `generated_files`, when configured
  - `version_targets`

Each version target is rendered using the same internal description that rrt
uses elsewhere, so the output is intended to be directly useful in generated
CLI documentation.

## Raw mode

`--raw` prints the underlying config file instead of the rendered tree. The
file is syntax-highlighted when possible and written directly to standard
output.

This is useful when you want to inspect the exact TOML/text content that rrt
loaded, rather than the resolved structure.

## Validate mode

`--validate` runs every config check and reports pass/fail for each validation
step.  Exits non-zero on any failure.

## Schema mode

`--schema` prints the bundled JSON Schema for `[tool.rrt]` to stdout.  Redirect
the output to a file and reference it from your TOML language server settings to
enable IDE completion and inline validation.

## Failure behavior

The command exits with a non-zero status when:

- no config file can be found
- the config file cannot be loaded
- the resolved config is invalid
- the raw file cannot be read in `--raw` mode

In these cases, the command writes the error or discovery guidance to stderr.

## Examples

```bash
rrt config
rrt config --raw
rrt config --validate
rrt config --schema > rrt-config.schema.json
```

## Caveats

- Paths in the tree are shown relative to the current repository root.
- The resolved output reflects discovery and auto-detection, not just the
  contents of one file.
"""

from __future__ import annotations

import argparse
import importlib.resources
import json
import sys
from pathlib import Path

from repo_release_tools import config as cfg
from repo_release_tools.ui import (
    GLYPHS,
    DryRunPrinter,
    highlight_terminal,
)

CONFIG_EPILOG = (
    "  $ rrt config\n  $ rrt config --raw\n  $ rrt config --validate\n  $ rrt config --schema"
)

RRT_CONFIG_SCHEMA = "rrt-config.schema.json"


def _render_group_details(group: cfg.VersionGroup, root: Path) -> list[str]:
    """Render the text lines for a version-group detail block."""
    g = GLYPHS
    details: list[str] = [
        f"  {g.bullet.dot} release_branch: {group.release_branch}",
        f"  {g.bullet.dot} changelog: {group.changelog_file.relative_to(root)}",
    ]
    if group.lock_command:
        details.append(f"  {g.bullet.dot} lock_command: {' '.join(group.lock_command)}")
    if group.generated_files:
        details.append(f"  {g.bullet.dot} generated_files:")
        details.extend(
            f"    {g.arrow.right} {generated_file.relative_to(root)}"
            for generated_file in group.generated_files
        )
    details.append(f"  {g.bullet.dot} version_targets:")
    details.extend(
        f"    {g.arrow.right} {cfg._describe_version_target(target, root=root)}"
        for target in group.version_targets
    )
    return details


def _load_schema() -> dict:
    """Load the bundled JSON Schema for [tool.rrt]."""
    try:
        schema_ref = importlib.resources.files("repo_release_tools").joinpath(
            f"_data/{RRT_CONFIG_SCHEMA}"
        )
        with importlib.resources.as_file(schema_ref) as schema_path:
            return json.loads(schema_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, TypeError):
        # Fall back to the repo-root schema when running from source
        here = Path(__file__).parent.parent.parent.parent
        schema_path = here / RRT_CONFIG_SCHEMA
        if schema_path.exists():
            return json.loads(schema_path.read_text(encoding="utf-8"))
        return {}


def _cmd_validate(root: Path) -> int:
    """Run all config validation checks and report results."""
    p = DryRunPrinter(False)
    p.blank_line()
    p.section("Config validation")
    errors: list[str] = []

    try:
        conf = cfg.load_or_autodetect_config(root)
    except FileNotFoundError:
        p.line("No config file found.", ok=False, stream=sys.stderr)
        p.line(
            cfg.format_missing_tool_rrt_guidance(root, cfg.iter_config_files(root)),
            ok=False,
            stream=sys.stderr,
        )
        return 1
    except (ValueError, cfg.MissingRrtConfigError) as exc:
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1

    source = "(auto-detected)" if conf.autodetected else str(conf.config_file.relative_to(root))
    p.ok(f"Config file loaded: {source}")

    if not conf.version_groups:
        errors.append("No version groups configured")
    else:
        p.ok(f"{len(conf.version_groups)} version group(s) found")

    for group in conf.version_groups:
        for target in group.version_targets:
            try:
                target.validate()
                p.ok(f"version_target {target.path.relative_to(root)}: valid")
            except ValueError as exc:
                errors.append(f"version_target {target.path}: {exc}")

        for pin in group.pin_targets + conf.global_pin_targets:
            try:
                pin.validate()
                p.ok(f"pin_target {pin.path.relative_to(root)}: valid")
            except ValueError as exc:
                errors.append(f"pin_target {pin.path}: {exc}")

    if conf.docs is not None:
        try:
            conf.docs.validate()
            p.ok("docs config: valid")
        except ValueError as exc:
            errors.append(f"docs config: {exc}")

    if conf.folders is not None:
        try:
            conf.folders.validate()
            p.ok("folders config: valid")
        except ValueError as exc:
            errors.append(f"folders config: {exc}")

    if errors:
        p.blank_line()
        p.line(f"{len(errors)} validation error(s):", ok=False)
        for err in errors:
            p.line(f"  {GLYPHS.bullet.dot} {err}", ok=False)
        return 1

    p.blank_line()
    p.ok("All validation checks passed.")
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    """Print the resolved rrt config as a tree."""
    root = cfg.find_repo_root(Path.cwd())

    if getattr(args, "schema", False):
        schema = _load_schema()
        if not schema:
            p = DryRunPrinter(False)
            p.line(
                "Schema not found. Run rrt from the project source directory.",
                ok=False,
                stream=sys.stderr,
            )
            return 1
        sys.stdout.write(json.dumps(schema, indent=2) + "\n")
        return 0

    if getattr(args, "validate", False):
        return _cmd_validate(root)

    try:
        conf = cfg.load_or_autodetect_config(root)
    except FileNotFoundError:
        checked = cfg.iter_config_files(root)
        p = DryRunPrinter(False)
        p.line(cfg.format_missing_tool_rrt_guidance(root, checked), ok=False, stream=sys.stderr)
        return 1
    except (ValueError, cfg.MissingRrtConfigError) as exc:
        p = DryRunPrinter(False)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1

    # --raw: syntax-highlighted view of the raw config file
    if getattr(args, "raw", False):
        config_path = conf.config_file
        try:
            raw_text = config_path.read_text(encoding="utf-8")
        except OSError as exc:
            p = DryRunPrinter(False)
            p.line(str(exc), ok=False, stream=sys.stderr)
            return 1
        lang = "toml" if config_path.suffix in {".toml"} else "text"
        # raw display: write highlighted text directly to stdout
        sys.stdout.write(highlight_terminal(raw_text, lang) + "\n")
        return 0

    source = "(auto-detected)" if conf.autodetected else str(conf.config_file.relative_to(root))
    group_count = len(conf.version_groups)
    plural = "group" if group_count == 1 else "groups"

    p = DryRunPrinter(False)
    p.line("rrt config", ok=True)
    p.meta("Config file", source)
    p.meta("Version groups", f"{group_count} {plural}")
    p.blank_line()

    p.section("Version groups")
    for group in conf.version_groups:
        p.ok(f"[{group.name}]")
        for detail_line in _render_group_details(group, root):
            p.line(detail_line)
        p.blank_line()
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the config command."""
    parser = subparsers.add_parser(
        "config",
        help="Show the resolved rrt configuration for this repository.",
        description=(
            "Inspect the resolved rrt configuration after discovery and auto-detection.\n\n"
            "Shows which config file rrt will use, the version groups it resolved, and the "
            "targets each group manages. Use --raw to print the underlying config file "
            "instead of the rendered tree view."
        ),
        epilog=CONFIG_EPILOG,
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        default=False,
        help="Show the raw config file with syntax highlighting instead of the tree view.",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        default=False,
        help="Validate the config and report pass/fail for each check.",
    )
    parser.add_argument(
        "--schema",
        action="store_true",
        default=False,
        help="Print the JSON Schema for [tool.rrt] to stdout.",
    )
    parser.set_defaults(handler=cmd_config)
