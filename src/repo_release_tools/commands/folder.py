"""Folder supervision and scaffolding command family.

Overview

`rrt folder` validates, scaffolds, and infers folder structures for a
project. It supports three primary flows:

- `check` — validate an existing tree against configured folder policies or
    built-in templates and report violations.
- `scaffold` — create missing files and directories from named templates,
    optionally running in `--dry-run` mode to preview changes.
- `design` — capture an existing directory tree and emit a reusable
    template description (TOML) that can be applied elsewhere.

Usage examples:

    rrt folder check --template python-package
    rrt folder scaffold --template cargo-inspired --dry-run
    rrt folder design --name captured-template --root src

This module implements the command handlers exposed via the top-level
`rrt folder` command and is intentionally documented so contributors and
automation can rely on a clear, multi-line module-level docstring.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from repo_release_tools.config import (
    RrtConfig,
    is_missing_tool_rrt_error,
    load_or_autodetect_config,
)
from repo_release_tools.folders import (
    capture_template,
    check_folders,
    render_captured_template_toml,
    resolve_template_catalog,
    scaffold_folders,
)
from repo_release_tools.state import health_lock_path, upsert_health_lock_checks
from repo_release_tools.ui import DryRunPrinter, VerbosePrinter

FOLDER_EPILOG = (
    "  $ rrt folder check --template python-package\n"
    "  $ rrt folder scaffold --template cargo-inspired --dry-run\n"
    "  $ rrt folder design --name captured-template --root src"
)


def _load_folder_policy_config() -> RrtConfig | None:
    """Return loaded config when available, otherwise ``None`` for template-only flows."""
    try:
        return load_or_autodetect_config(Path.cwd())
    except FileNotFoundError:
        return None
    except ValueError as exc:
        if is_missing_tool_rrt_error(exc):
            return None
        raise


def cmd_folder_check(args: argparse.Namespace) -> int:
    """Run folder supervision checks."""
    verbose: int = getattr(args, "verbose", 0) or 0
    root = Path(args.root).resolve()
    config = _load_folder_policy_config()
    report = check_folders(
        root=root,
        policy=None if config is None else config.folders,
        template_names=tuple(args.template or ()),
        mode_override="warn" if args.report_only else None,
    )

    if getattr(args, "snapshot", False):
        check_entries = [
            {
                "name": f"folder.{target.rule_name}",
                "status": "ok" if target.ok else "error",
                "message": (
                    f"{target.rule_name}: {target.base_path} — "
                    f"{len(target.violations)} violation(s)"
                    if not target.ok
                    else f"{target.rule_name}: {target.base_path} — ok"
                ),
            }
            for target in report.targets
        ]
        upsert_health_lock_checks(health_lock_path(root), check_entries)
        p_snap = VerbosePrinter(verbose=verbose)
        p_snap.ok(f"Folder results merged into .rrt/health.lock.toml ({len(check_entries)} checks)")

    if getattr(args, "format", "text") == "json":
        sys.stdout.write(json.dumps(report.to_dict(), indent=2) + "\n")
        return 0 if report.ok or args.report_only else 1

    p = VerbosePrinter(verbose=verbose)
    p.blank_line()
    p.header("Folder check", Root=str(root))
    for target in report.targets:
        if target.ok:
            p.ok(f"{target.rule_name}: {target.base_path}")
            continue
        p.warn(f"{target.rule_name}: {target.base_path}")
        for violation in target.violations:
            if violation.severity == "warning":
                p.warn(f"{violation.path}: {violation.message}")
            else:
                p.line(f"{violation.path}: {violation.message}", ok=False, stream=sys.stderr)

    return 0 if report.ok or args.report_only else 1


def cmd_folder_scaffold(args: argparse.Namespace) -> int:
    """Scaffold folder structure from templates or config."""
    verbose: int = getattr(args, "verbose", 0) or 0
    root = Path(args.root).resolve()
    config = _load_folder_policy_config()
    report = scaffold_folders(
        root=root,
        policy=None if config is None else config.folders,
        template_names=tuple(args.template or ()),
        force=args.force,
        dry_run=args.dry_run,
    )

    if getattr(args, "format", "text") == "json":
        sys.stdout.write(json.dumps(report.to_dict(), indent=2) + "\n")
        return 0

    p = DryRunPrinter(args.dry_run, verbose=verbose)
    p.blank_line()
    p.header("Folder scaffold", Root=str(root))
    for action in report.actions:
        if p.dry_run:
            p.action(f"[dry-run] {action.kind} {action.path} {action.detail}".rstrip())
            continue
        p.action(f"{action.kind} {action.path} {action.detail}".rstrip())
    p.ok(f"Completed {len(report.actions)} scaffold actions.")
    return 0


def cmd_folder_design(args: argparse.Namespace) -> int:
    """Infer a folder template from an existing directory tree."""
    verbose: int = getattr(args, "verbose", 0) or 0
    root = Path(args.root).resolve()
    if not root.exists() or not root.is_dir():
        p = VerbosePrinter(verbose=verbose)
        p.line(f"Design root must be an existing directory: {root}", ok=False, stream=sys.stderr)
        return 1

    template = capture_template(name=args.name, root=root, loose=args.loose)
    snippet = render_captured_template_toml(template, selector=args.selector)
    sys.stdout.write(snippet)
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the folder command family."""
    parser = subparsers.add_parser(
        "folder",
        help="Check, scaffold, and design folder structures.",
        description=(
            "Supervise folder structures against config-defined rules or built-in templates, "
            "scaffold missing structure, and infer new templates from existing trees."
        ),
        epilog=FOLDER_EPILOG,
    )
    folder_sub = parser.add_subparsers(dest="folder_command", required=True)

    check_parser = folder_sub.add_parser(
        "check",
        help="Validate folder structure against templates or configured rules.",
    )
    check_parser.add_argument("--root", default=".", metavar="PATH", help="Root to validate.")
    check_parser.add_argument(
        "--template",
        action="append",
        default=[],
        help=(
            "Built-in or custom template name to apply at the root. "
            f"Available built-ins: {', '.join(sorted(resolve_template_catalog()))}."
        ),
    )
    check_parser.add_argument(
        "--report-only",
        action="store_true",
        default=False,
        help="Downgrade violations to warnings for this invocation.",
    )
    check_parser.add_argument(
        "--snapshot",
        action="store_true",
        default=False,
        help="Merge folder check results into .rrt/health.lock.toml after running.",
    )
    check_parser.set_defaults(handler=cmd_folder_check)

    scaffold_parser = folder_sub.add_parser(
        "scaffold",
        help="Create missing files and folders from templates or configured rules.",
    )
    scaffold_parser.add_argument("--root", default=".", metavar="PATH", help="Root to scaffold.")
    scaffold_parser.add_argument(
        "--template",
        action="append",
        default=[],
        help="Built-in or custom template name to apply at the root.",
    )
    scaffold_parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Overwrite existing scaffold-managed files.",
    )
    scaffold_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview scaffold actions without writing files.",
    )
    scaffold_parser.set_defaults(handler=cmd_folder_scaffold)

    design_parser = folder_sub.add_parser(
        "design",
        help="Infer a custom template from an existing directory.",
    )
    design_parser.add_argument("--root", default=".", metavar="PATH", help="Directory to inspect.")
    design_parser.add_argument(
        "--name",
        default="captured-template",
        metavar="NAME",
        help="Template name to emit.",
    )
    design_parser.add_argument(
        "--selector",
        default=".",
        metavar="GLOB",
        help="Selector to pair with the emitted rule snippet.",
    )
    design_parser.add_argument(
        "--loose",
        action="store_true",
        default=False,
        help="Emit a permissive loose template instead of an exact one.",
    )
    design_parser.set_defaults(handler=cmd_folder_design)
