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
import difflib
import importlib.resources
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from repo_release_tools import config as cfg
from repo_release_tools.config.reference import render_reference_toml
from repo_release_tools.ui import (
    GLYPHS,
    DryRunPrinter,
    VerbosePrinter,
    highlight_terminal,
)

CONFIG_EPILOG = (
    "  $ rrt config\n  $ rrt config --raw\n  $ rrt config --validate\n  $ rrt config --schema"
    "\n  $ rrt config --reference\n  $ rrt config --reference --check"
    "\n  $ rrt config --reference --dry-run"
)

RRT_CONFIG_SCHEMA = "rrt-config.schema.json"

CONFIG_REFERENCE_PATH = Path("docs/rrt-config-reference.toml")


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
    p = VerbosePrinter()
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


def _cmd_reference(*, check: bool, dry_run: bool) -> int:
    """Implement ``rrt config --reference [--check] [--dry-run]``."""
    schema = _load_schema()
    text = render_reference_toml(schema)
    ref_path = CONFIG_REFERENCE_PATH

    if check:
        p = VerbosePrinter()
        if not ref_path.exists():
            p.line(
                f"{ref_path} does not exist. Run 'rrt config --reference' to generate it.",
                ok=False,
                stream=sys.stderr,
            )
            return 1
        existing = ref_path.read_text(encoding="utf-8")
        if existing == text:
            p.ok(f"{ref_path} is up to date.")
            return 0
        # Emit a unified diff to stderr
        diff_lines = list(
            difflib.unified_diff(
                existing.splitlines(keepends=True),
                text.splitlines(keepends=True),
                fromfile=str(ref_path),
                tofile="<generated>",
            )
        )
        p.line(
            f"{ref_path} is out of date. Run 'rrt config --reference' to regenerate.",
            ok=False,
            stream=sys.stderr,
        )
        for line in diff_lines:
            sys.stderr.write(line)
        return 1

    if dry_run:
        p = DryRunPrinter(dry_run=True)
        p.header("Generate config reference")
        p.would_write(str(ref_path), "annotated .rrt.toml reference from schema")
        p.blank_line()
        p.footer("Done.")
        return 0

    # Write the reference file
    ref_path.parent.mkdir(parents=True, exist_ok=True)
    ref_path.write_text(text, encoding="utf-8")
    p = VerbosePrinter()
    p.ok(f"Written: {ref_path}")
    return 0


@dataclass(frozen=True)
class Options:
    """Typed view of ``argparse.Namespace`` for ``rrt config``.

    Built once via :meth:`from_args` at the top of :func:`cmd_config` so
    every flag has a single, typed read site instead of scattered
    ``getattr(args, ..., default)`` calls throughout the function body.
    """

    verbose: int
    schema: bool
    reference: bool
    check: bool
    dry_run: bool
    validate: bool
    raw: bool

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> Options:
        """Build an :class:`Options` from a parsed ``argparse.Namespace``.

        Every flag other than ``verbose`` is given a real default by
        config_cmd.py's own register(), and workflow/hooks.py's
        "config-validate" and "config-reference-check" dispatch cases
        (workflow/hooks.py:1379-1401) each build a fully populated
        ``argparse.Namespace`` with every one of these fields set
        explicitly, so a Namespace from either caller always carries them.
        The getattr fallbacks here exist only because some unit tests in
        tests/commands/test_config_cmd.py construct sparse
        ``argparse.Namespace`` objects by hand instead of going through
        register(). ``verbose`` is set globally by cli.py's parser (and
        explicitly by hooks.py's dispatch cases), but tests may omit it, so
        the fallback here absorbs that gap too.
        """
        return cls(
            verbose=getattr(args, "verbose", 0) or 0,
            schema=getattr(args, "schema", False),
            reference=getattr(args, "reference", False),
            check=getattr(args, "check", False),
            dry_run=getattr(args, "dry_run", False),
            validate=getattr(args, "validate", False),
            raw=getattr(args, "raw", False),
        )


def cmd_config(args: argparse.Namespace) -> int:
    """Print the resolved rrt config as a tree."""
    opts = Options.from_args(args)
    verbose: int = opts.verbose
    root = cfg.find_repo_root(Path.cwd())

    if opts.schema:
        schema = _load_schema()
        if not schema:
            p = VerbosePrinter(verbose=verbose)
            p.line(
                "Schema not found. Run rrt from the project source directory.",
                ok=False,
                stream=sys.stderr,
            )
            return 1
        sys.stdout.write(json.dumps(schema, indent=2) + "\n")
        return 0

    if opts.reference:
        return _cmd_reference(
            check=opts.check,
            dry_run=opts.dry_run,
        )

    if opts.validate:
        return _cmd_validate(root)

    try:
        conf = cfg.load_or_autodetect_config(root)
    except FileNotFoundError:
        checked = cfg.iter_config_files(root)
        p = VerbosePrinter(verbose=verbose)
        p.line(cfg.format_missing_tool_rrt_guidance(root, checked), ok=False, stream=sys.stderr)
        return 1
    except (ValueError, cfg.MissingRrtConfigError) as exc:
        p = VerbosePrinter(verbose=verbose)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1

    # --raw: syntax-highlighted view of the raw config file
    if opts.raw:
        config_path = conf.config_file
        try:
            raw_text = config_path.read_text(encoding="utf-8")
        except OSError as exc:
            p = VerbosePrinter(verbose=verbose)
            p.line(str(exc), ok=False, stream=sys.stderr)
            return 1
        lang = "toml" if config_path.suffix in {".toml"} else "text"
        # raw display: write highlighted text directly to stdout
        sys.stdout.write(highlight_terminal(raw_text, lang) + "\n")
        return 0

    source = "(auto-detected)" if conf.autodetected else str(conf.config_file.relative_to(root))
    group_count = len(conf.version_groups)
    plural = "group" if group_count == 1 else "groups"

    p = VerbosePrinter(verbose=verbose)
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
    parser.add_argument(
        "--reference",
        action="store_true",
        default=False,
        help="Generate the annotated .rrt.toml config reference.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        default=False,
        help="With --reference: verify docs/rrt-config-reference.toml is current; exit 1 on drift.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="With --reference: print without writing.",
    )
    parser.set_defaults(handler=cmd_config)
