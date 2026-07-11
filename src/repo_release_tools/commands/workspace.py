"""Coordinate version bumps across multiple packages in a monorepo.

## Overview

`rrt workspace bump` applies the same version bump to every listed package in
one pass.  It reads each package's own ``[tool.rrt]`` configuration, verifies
that all packages are loadable, then updates version targets and changelogs in
a single coordinated sweep.

## When to use this

Use ``rrt workspace bump`` when your repository contains multiple
independently-versioned packages (e.g. a Python backend, a TypeScript SDK, and
a Go CLI tool) that are always released together at the same version.

## What it does

1. Resolve each package path from ``--packages``.
2. Load each package's rrt config and read its current version.
3. Compute the new version using the same bump logic as ``rrt bump``.
4. For each package: update version targets and, unless ``--no-changelog``,
   the changelog.
5. Report every file write to stdout (or preview them with ``--dry-run``).

## Safety notes

* All package configs must exist and be valid before any file is written.
* ``--dry-run`` previews all planned writes without touching any file.

## Examples

```bash
rrt workspace bump minor --packages api,sdk,docs
rrt workspace bump 2.0.0 --packages ./packages/api,./packages/sdk
rrt workspace bump patch --dry-run --packages api,sdk
```
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from repo_release_tools.changelog import (
    detect_changelog_format,
    get_unreleased_entries,
    has_unreleased_section,
    promote_unreleased,
)
from repo_release_tools.commands._common import describe_config_load_error
from repo_release_tools.commands._version_render import render_version_write_events
from repo_release_tools.config import (
    RrtConfig,
    iter_config_files,
    load_or_autodetect_config,
)
from repo_release_tools.ui import GLYPHS, DryRunPrinter, VerbosePrinter
from repo_release_tools.version.calver import CalVersion
from repo_release_tools.version.semver import PRE_RELEASE_CHANNELS, Version
from repo_release_tools.version.targets import (
    read_group_current_version,
    replace_all_versions_atomic,
)


def _resolve_packages(packages_arg: str, cwd: Path) -> list[Path]:
    """Expand a comma-separated package list into absolute paths."""
    return [(cwd / pkg.strip()).resolve() for pkg in packages_arg.split(",") if pkg.strip()]


def _compute_new_version(
    bump_kind: str,
    current: Version,
) -> Version | CalVersion | None:
    """Return the new version for *bump_kind*, or None on parse failure."""
    _BUMP_KINDS = {"major", "minor", "patch", "pre-release", "calver", *PRE_RELEASE_CHANNELS}

    if bump_kind == "calver":
        try:
            return CalVersion.parse(str(current)).bump()
        except ValueError:
            return CalVersion.today()

    if bump_kind in _BUMP_KINDS:
        return current.bump(bump_kind)

    try:
        return Version.parse(bump_kind)
    except ValueError:
        try:
            return CalVersion.parse(bump_kind)
        except ValueError:
            return None


def _update_changelog_for_package(
    config: RrtConfig,
    group: object,
    new: str,
    *,
    dry_run: bool,
) -> None:
    """Promote [Unreleased] to *new* in the package changelog when entries exist."""
    path = config.changelog_file  # type: ignore[attr-defined]
    if not path.exists():
        return

    existing = path.read_text(encoding="utf-8")
    fmt = detect_changelog_format(path.name)

    if not has_unreleased_section(existing, fmt):
        return
    if not get_unreleased_entries(existing, fmt):
        return

    updated = promote_unreleased(existing, new, fmt)
    p = DryRunPrinter(dry_run)
    if dry_run:
        p.would_write(str(path), f"promote [Unreleased] → [{new}]")
    else:
        path.write_text(updated, encoding="utf-8")
        p.ok(f"{path} updated (promoted [Unreleased] to [{new}])")


@dataclass(frozen=True)
class WorkspaceBumpOptions:
    """Typed view of ``argparse.Namespace`` for ``rrt workspace bump``.

    Built once via :meth:`from_args` at the top of :func:`cmd_workspace_bump`
    so all flags it reads have typed read sites instead of
    ``getattr(args, ..., default)`` calls throughout the function body.
    """

    bump: str
    packages: str
    dry_run: bool
    no_changelog: bool
    verbose: int

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> WorkspaceBumpOptions:
        """Build a :class:`WorkspaceBumpOptions` from a parsed ``argparse.Namespace``.

        ``bump``, ``packages``, ``dry_run``, and ``no_changelog`` are all
        positional/required or given real defaults by workspace.py's own
        register(), and every test in tests/commands/test_workspace.py that
        exercises cmd_workspace_bump goes through the local ``_args()``
        helper which always sets all four, so they are read directly.
        ``verbose`` is set globally by cli.py's parser, but ``_args()``
        never sets it, so the getattr fallback here absorbs that gap.
        """
        return cls(
            bump=args.bump,
            packages=args.packages or "",
            dry_run=args.dry_run,
            no_changelog=args.no_changelog,
            verbose=getattr(args, "verbose", 0) or 0,
        )


def cmd_workspace_bump(args: argparse.Namespace) -> int:
    """Apply a unified version bump to all listed packages."""
    opts = WorkspaceBumpOptions.from_args(args)
    verbose = opts.verbose
    cwd = Path.cwd()
    dry_run = opts.dry_run
    packages_str = opts.packages
    bump_kind = opts.bump
    no_changelog = opts.no_changelog

    if not packages_str:
        p = VerbosePrinter(verbose=verbose)
        p.line(
            "--packages is required (comma-separated list of package paths).",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    pkg_paths = _resolve_packages(packages_str, cwd)

    # --- Phase 1: load all configs; fail early before touching any file -------
    loaded: list[tuple[Path, RrtConfig, object]] = []
    for pkg_path in pkg_paths:
        if not pkg_path.is_dir():
            p = VerbosePrinter(verbose=verbose)
            p.line(f"Package directory not found: {pkg_path}", ok=False, stream=sys.stderr)
            return 1

        try:
            config = load_or_autodetect_config(pkg_path)
        except FileNotFoundError as exc:
            err = describe_config_load_error(
                exc, pkg_path, no_config_file_checked=iter_config_files(pkg_path)
            )
            p = VerbosePrinter(verbose=verbose)
            p.line(f"No rrt config found in {pkg_path}.", ok=False, stream=sys.stderr)
            p.line(err.text, ok=False, stream=sys.stderr)
            return 1
        except (ValueError, RuntimeError) as exc:
            err = describe_config_load_error(exc, pkg_path)
            p = VerbosePrinter(verbose=verbose)
            if err.kind == "missing_tool_rrt":
                p.line(f"No [tool.rrt] config in {pkg_path}.", ok=False, stream=sys.stderr)
            else:
                p.line(err.text, ok=False, stream=sys.stderr)
            return 1

        group = config.resolve_group(None)
        current = read_group_current_version(group)
        new = _compute_new_version(bump_kind, current)
        if new is None:
            p = VerbosePrinter(verbose=verbose)
            p.line(f"Invalid bump value: {bump_kind!r}", ok=False, stream=sys.stderr)
            return 1

        loaded.append((pkg_path, config, new))

    # --- Phase 2: apply all updates ------------------------------------------
    pr = DryRunPrinter(dry_run, verbose=verbose)
    pr.blank_line()
    pr.header("Workspace bump", Packages=str(len(loaded)), Bump=bump_kind)

    for pkg_path, config, new in loaded:
        group = config.resolve_group(None)
        current = read_group_current_version(group)
        pr.section(f"{pkg_path.name}: {current} {GLYPHS.arrow.right} {new}")

        events = replace_all_versions_atomic(group.version_targets, str(new), dry_run=dry_run)
        render_version_write_events(events)

        if not no_changelog:
            group_config = RrtConfig(
                root=config.root,
                config_file=config.config_file,
                version_groups=[group],
                default_group_name=group.name,
            )
            _update_changelog_for_package(group_config, group, str(new), dry_run=dry_run)

    if dry_run:
        pr.line("no files were modified")

    return 0


_WORKSPACE_EPILOG = (
    "  $ rrt workspace bump minor --packages api,sdk,docs\n"
    "  $ rrt workspace bump 2.0.0 --packages ./packages/api,./packages/sdk\n"
    "  $ rrt workspace bump patch --dry-run --packages api,sdk"
)


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the workspace command."""
    parser = subparsers.add_parser(
        "workspace",
        help="Coordinate version bumps across multiple packages in a monorepo.",
        description=(
            "Apply a unified version bump to every listed package.\n\n"
            "Each package must have its own [tool.rrt] configuration. All configs "
            "are validated before any file is written."
        ),
    )
    ws_sub = parser.add_subparsers(
        dest="workspace_command",
        metavar="<workspace_command>",
        required=True,
    )

    bump_parser = ws_sub.add_parser(
        "bump",
        help="Bump versions across all listed packages.",
        description="Apply the same version bump to every package listed in --packages.",
        epilog=_WORKSPACE_EPILOG,
    )
    bump_parser.add_argument(
        "bump",
        metavar="<bump>",
        help="major | minor | patch | pre-release | calver | <version>",
    )
    bump_parser.add_argument(
        "--packages",
        required=True,
        metavar="PATHS",
        help="Comma-separated list of package directories to bump.",
    )
    bump_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing to disk.",
    )
    bump_parser.add_argument(
        "--no-changelog",
        action="store_true",
        help="Skip changelog updates.",
    )
    bump_parser.set_defaults(handler=cmd_workspace_bump)
