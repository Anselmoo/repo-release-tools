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
from dataclasses import dataclass
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


def _load_folder_policy_config(root: Path) -> RrtConfig | None:
    """Return loaded config when available, otherwise ``None`` for template-only flows."""
    try:
        return load_or_autodetect_config(root)
    except FileNotFoundError:
        return None
    except ValueError as exc:
        if is_missing_tool_rrt_error(exc):
            return None
        raise


@dataclass(frozen=True)
class CheckOptions:
    """Typed view of ``argparse.Namespace`` for ``rrt folder check``.

    Built once via :meth:`from_args` at the top of :func:`cmd_folder_check`
    so every flag has a single, typed read site instead of scattered
    ``getattr(args, ..., default)`` calls throughout the function body.
    """

    verbose: int
    root: str
    template: tuple[str, ...]
    report_only: bool
    snapshot: bool
    format: str

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> CheckOptions:
        """Build a :class:`CheckOptions` from a parsed ``argparse.Namespace``.

        ``root``, ``template``, and ``report_only`` are given real
        defaults by folder.py's own register() and by
        workflow/hooks.py's "folder-check" subparser
        (workflow/hooks.py:1237-1260), so a Namespace from either caller
        always carries them and they are read directly. ``snapshot`` is
        only registered by folder.py's own register() -- hooks.py's
        "folder-check" subparser also defines its own ``--snapshot``
        (line 1256), so both callers carry it, but several unit tests in
        tests/commands/test_folder.py construct sparse
        ``argparse.Namespace`` objects that omit it, so the getattr
        fallback absorbs that gap. ``format`` is never set by
        folder.py's own register() (there is no ``--format`` flag on
        this subcommand); hooks.py's "folder-check" dispatch case sets
        ``parsed.format = "text"`` explicitly, so the fallback here
        covers direct callers/tests that never set it. ``verbose`` is
        set globally by cli.py's parser (and explicitly by hooks.py's
        dispatch case), but tests may omit it, so the fallback absorbs
        that too.
        """
        return cls(
            verbose=getattr(args, "verbose", 0) or 0,
            root=args.root,
            template=tuple(args.template or ()),
            report_only=args.report_only,
            snapshot=getattr(args, "snapshot", False),
            format=getattr(args, "format", "text"),
        )


def cmd_folder_check(args: argparse.Namespace) -> int:
    """Run folder supervision checks."""
    opts = CheckOptions.from_args(args)
    verbose = opts.verbose
    root = Path(opts.root).resolve()
    config = _load_folder_policy_config(root)
    report = check_folders(
        root=root,
        policy=None if config is None else config.folders,
        template_names=opts.template,
        mode_override="warn" if opts.report_only else None,
    )

    if opts.snapshot:
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

    if opts.format == "json":
        sys.stdout.write(json.dumps(report.to_dict(), indent=2) + "\n")
        return 0 if report.ok or opts.report_only else 1

    p = VerbosePrinter(verbose=verbose)
    p.blank_line()
    p.header("Folder check", Root=str(root))
    for target in report.targets:
        if target.ok:
            p.ok(f"{target.rule_name}: {target.base_path}")
            continue
        p.warn(f"{target.rule_name}: {target.base_path}")
        for violation in target.violations:
            match violation.severity:
                case "warning":
                    p.warn(f"{violation.path}: {violation.message}")
                case "obsolete":
                    p.obsolete(f"{violation.path}: {violation.message}")
                case _:
                    p.line(f"{violation.path}: {violation.message}", ok=False, stream=sys.stderr)

    return 0 if report.ok or opts.report_only else 1


@dataclass(frozen=True)
class ScaffoldOptions:
    """Typed view of ``argparse.Namespace`` for ``rrt folder scaffold``.

    Built once via :meth:`from_args` at the top of :func:`cmd_folder_scaffold`
    so every flag has a single, typed read site instead of scattered
    ``getattr(args, ..., default)`` calls throughout the function body.
    """

    verbose: int
    root: str
    template: tuple[str, ...]
    force: bool
    dry_run: bool
    format: str

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> ScaffoldOptions:
        """Build a :class:`ScaffoldOptions` from a parsed ``argparse.Namespace``.

        ``root``, ``template``, ``force``, and ``dry_run`` are all given
        real defaults by folder.py's own register(), the only caller of
        ``cmd_folder_scaffold`` (workflow/hooks.py has no
        "folder-scaffold" dispatch case), so a Namespace produced by
        argparse always carries them and they are read directly.
        ``format`` has no corresponding ``--format`` flag on this
        subcommand at all, so the getattr fallback is the only source of
        its default. ``verbose`` is set globally by cli.py's parser, but
        several unit tests in tests/commands/test_folder.py construct
        sparse ``argparse.Namespace`` objects that omit it, so the
        fallback absorbs that gap.
        """
        return cls(
            verbose=getattr(args, "verbose", 0) or 0,
            root=args.root,
            template=tuple(args.template or ()),
            force=args.force,
            dry_run=args.dry_run,
            format=getattr(args, "format", "text"),
        )


def cmd_folder_scaffold(args: argparse.Namespace) -> int:
    """Scaffold folder structure from templates or config."""
    opts = ScaffoldOptions.from_args(args)
    verbose = opts.verbose
    root = Path(opts.root).resolve()
    config = _load_folder_policy_config(root)
    report = scaffold_folders(
        root=root,
        policy=None if config is None else config.folders,
        template_names=opts.template,
        force=opts.force,
        dry_run=opts.dry_run,
    )

    if opts.format == "json":
        sys.stdout.write(json.dumps(report.to_dict(), indent=2) + "\n")
        return 0

    p = DryRunPrinter(opts.dry_run, verbose=verbose)
    p.blank_line()
    p.header("Folder scaffold", Root=str(root))
    for action in report.actions:
        if p.dry_run:
            p.action(f"[dry-run] {action.kind} {action.path} {action.detail}".rstrip())
            continue
        p.action(f"{action.kind} {action.path} {action.detail}".rstrip())
    p.ok(f"Completed {len(report.actions)} scaffold actions.")
    return 0


@dataclass(frozen=True)
class DesignOptions:
    """Typed view of ``argparse.Namespace`` for ``rrt folder design``.

    Built once via :meth:`from_args` at the top of :func:`cmd_folder_design`
    so every flag has a single, typed read site instead of scattered
    ``getattr(args, ..., default)`` calls throughout the function body.
    """

    verbose: int
    root: str
    name: str
    loose: bool
    selector: str

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> DesignOptions:
        """Build a :class:`DesignOptions` from a parsed ``argparse.Namespace``.

        ``root``, ``name``, ``loose``, and ``selector`` are all given real
        defaults by folder.py's own register(), the only caller of
        ``cmd_folder_design`` (workflow/hooks.py has no "folder-design"
        dispatch case), so a Namespace produced by argparse always
        carries them and they are read directly. ``verbose`` is set
        globally by cli.py's parser, but several unit tests in
        tests/commands/test_folder.py construct sparse
        ``argparse.Namespace`` objects that omit it, so the getattr
        fallback absorbs that gap.
        """
        return cls(
            verbose=getattr(args, "verbose", 0) or 0,
            root=args.root,
            name=args.name,
            loose=args.loose,
            selector=args.selector,
        )


def cmd_folder_design(args: argparse.Namespace) -> int:
    """Infer a folder template from an existing directory tree."""
    opts = DesignOptions.from_args(args)
    verbose = opts.verbose
    root = Path(opts.root).resolve()
    if not root.exists() or not root.is_dir():
        p = VerbosePrinter(verbose=verbose)
        p.line(f"Design root must be an existing directory: {root}", ok=False, stream=sys.stderr)
        return 1

    template = capture_template(name=opts.name, root=root, loose=opts.loose)
    snippet = render_captured_template_toml(template, selector=opts.selector)
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
