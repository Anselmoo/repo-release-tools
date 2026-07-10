"""Install bundled rrt user workflow surfaces into local/global tool roots.

## Overview

`rrt install` provides a unified, top-level entrypoint for the existing
specialized installer surfaces:

- `skill install`
- `agents install`
- `hooks install`

It is designed to simplify the initial setup and maintenance of the agentic
workflow tools by allowing users to install all (or a subset of) surfaces
into one or more target destinations in a single operation.

## Responsibilities

- coordinate the installation of multiple surface types (skills, agents, hooks)
- validate target compatibility across all requested surfaces
- provide a consistent dry-run experience for multi-surface installation
- manage local and global tool root discovery

## Target roots

Supported local/global roots include:

- **Claude**: `./.claude` (local) and `~/.claude` (global)
- **Codex**: `./.codex` (local) and `~/.codex` (global)
- **Copilot**: `./.github` (local) and `~/.copilot` (global)
- **Gemini**: `./.gemini` (local) and `~/.gemini` (global)

Each surface appends its own standardized subdirectory (e.g., `skills`,
`agents`, or `hooks`) using the internal per-surface logic.

## Behavior

- If `--surface` is omitted, all bundled surfaces are installed.
- Accepts multiple `--target` values to support parallel installation into
  different tools or both local and global roots.
- Respects `--force` to overwrite existing files across all selected surfaces.
- Supports `--dry-run` to preview the entire installation plan without modifying
  any files.
- Exits with an error if any requested target is unsupported by a selected
  surface.

## Examples

- `rrt install --target claude-local`
- `rrt install --surface skill --target copilot-local`
- `rrt install --surface agents --surface hooks --target codex-global --dry-run`
- `rrt install --target gemini-local --target gemini-global --force`

## Caveats

- Without `--target`, the command prints available destinations in dry-run
  mode and otherwise fails.
- The installation is additive by default; existing files are only replaced
  when `--force` is explicitly passed.
"""

from __future__ import annotations

import argparse
import sys
from argparse import Namespace
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from repo_release_tools.commands import agents_cmd, hooks_cmd, skill
from repo_release_tools.ui import DryRunPrinter, VerbosePrinter

INSTALL_EXAMPLES = (
    "  $ rrt install --target claude-local\n"
    "  $ rrt install --surface skill --target copilot-local\n"
    "  $ rrt install --surface agents --surface hooks --target codex-global --dry-run"
)

SOURCE_OWNED_TOPIC_DOCS: tuple[tuple[str, str], ...] = (("install", __doc__ or ""),)


def _emit_install_error(message: str) -> int:
    p = VerbosePrinter()
    p.line(message, ok=False, stream=sys.stderr)
    return 1


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _resolve_surfaces(surfaces: list[str] | None) -> list[str]:
    resolved = _dedupe(surfaces or ["all"])
    return ["skill", "agents", "hooks"] if "all" in resolved else resolved


def _surface_registry() -> dict[str, tuple[Mapping[str, object], Callable[[Namespace], int]]]:
    return {
        "skill": (skill.TARGET_PATHS, skill.cmd_install),
        "agents": (agents_cmd.AGENT_TARGET_PATHS, agents_cmd.cmd_install),
        "hooks": (hooks_cmd.HOOK_TARGET_PATHS, hooks_cmd.cmd_install),
    }


def _all_known_targets() -> list[str]:
    targets: set[str] = set()
    for target_map, _ in _surface_registry().values():
        targets.update(target_map)
    return sorted(targets)


def _show_available_targets() -> None:
    p = DryRunPrinter(True)
    p.blank_line()
    p.header("Install", Surfaces="3")
    p.section("Available targets by surface")
    for surface, (target_map, _) in _surface_registry().items():
        p.meta(surface, ", ".join(sorted(target_map)))
    p.blank_line()
    p.footer("pass --target DEST to install (see targets above)")


@dataclass(frozen=True)
class InstallOptions:
    """Typed view of ``argparse.Namespace`` for ``rrt install``.

    Built once via :meth:`from_args` at the top of :func:`cmd_install` so all
    flags it reads have typed read sites instead of ``getattr(args, ...,
    default)`` / ``args.x`` calls throughout the function body.
    """

    surfaces: list[str] | None
    targets: list[str] | None
    dry_run: bool
    force: bool
    verbose: int

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> InstallOptions:
        """Build an :class:`InstallOptions` from a parsed ``argparse.Namespace``.

        ``surfaces``, ``targets``, ``dry_run``, and ``force`` are given real
        defaults by install_cmd.py's own register(), and every test in
        tests/commands/test_install_cmd.py that exercises cmd_install
        constructs its Namespace with all four set explicitly, so they are
        read directly. ``verbose`` is set globally by cli.py's parser, but no
        test Namespace here ever sets it, so the getattr fallback here
        absorbs that gap.
        """
        return cls(
            surfaces=args.surfaces,
            targets=args.targets,
            dry_run=args.dry_run,
            force=args.force,
            verbose=getattr(args, "verbose", 0) or 0,
        )


def cmd_install(args: argparse.Namespace) -> int:
    """Install one or more bundled surfaces into one or more targets."""
    opts = InstallOptions.from_args(args)
    targets = _dedupe(opts.targets or [])
    if not targets:
        if opts.dry_run:
            _show_available_targets()
            return 0
        return _emit_install_error(
            "No --target specified. Pass --target DEST (e.g. --target claude-local).",
        )

    surfaces = _resolve_surfaces(opts.surfaces)
    registry = _surface_registry()
    for surface in surfaces:
        target_map, _ = registry[surface]
        if unsupported := [target for target in targets if target not in target_map]:
            available = ", ".join(sorted(target_map))
            joined = ", ".join(unsupported)
            return _emit_install_error(
                f"{surface} does not support target(s): {joined}. Available: {available}.",
            )

    p = DryRunPrinter(opts.dry_run, verbose=opts.verbose)
    p.blank_line()
    p.header("Install", Surfaces=str(len(surfaces)), Targets=str(len(targets)))

    for surface in surfaces:
        _, handler = registry[surface]
        p.section(f"Surface: {surface}")
        result = handler(Namespace(targets=targets, dry_run=opts.dry_run, force=opts.force))
        if result != 0:
            return result

    if opts.dry_run:
        p.blank_line()
        p.footer("no files were modified")
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the unified install command."""
    parser = subparsers.add_parser(
        "install",
        help="Install bundled rrt agent surfaces into local/global roots.",
        description=(
            "Install one or more bundled rrt agent surfaces (skill, agents, hooks) "
            "into one or more local/global targets."
        ),
        epilog=INSTALL_EXAMPLES,
    )
    parser.add_argument(
        "--surface",
        dest="surfaces",
        action="append",
        required=False,
        choices=["all", "skill", "agents", "hooks"],
        metavar="SURFACE",
        help=(
            "Surface to install. Repeat for multiple values. Defaults to all: skill, agents, hooks."
        ),
    )
    parser.add_argument(
        "--target",
        dest="targets",
        action="append",
        required=False,
        choices=_all_known_targets(),
        metavar="DEST",
        help=(
            "Install target. Repeat to install into multiple locations. "
            "Use --dry-run with no targets to inspect supported values."
        ),
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing files.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing installed files.")
    parser.set_defaults(handler=cmd_install)
