"""rrt doctor — health-check the rrt configuration for the current repository."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from repo_release_tools import output
from repo_release_tools.config import (
    PinTarget,
    VersionTarget,
    _describe_version_target,
    format_autodetected_config_notice,
    format_missing_tool_rrt_guidance,
    is_missing_tool_rrt_error,
    iter_config_files,
    load_or_autodetect_config,
)
from repo_release_tools.ui import bold
from repo_release_tools.ui.layout import render_table
from repo_release_tools.version_targets import read_version_string


def _check_version_target(target: VersionTarget, root: Path, g) -> tuple[str, bool]:
    """Return a (label, is_ok) pair for a version target health check."""
    relative = str(target.path.relative_to(root))
    kind_hint = _describe_version_target(target, root=root).split("(", 1)
    suffix = f" ({kind_hint[1]}" if len(kind_hint) > 1 else ""

    if not target.path.exists():
        return f"{relative}{suffix}  {g.bullet.error} not found", False

    try:
        version = read_version_string(target)
        return f"{relative}{suffix}  {g.git.clean} {version}", True
    except (RuntimeError, ValueError):
        return f"{relative}{suffix}  {g.bullet.warning} version unreadable", True


def _check_pin_target(pin: PinTarget, root: Path, g) -> tuple[str, bool]:
    """Return a (label, is_ok) pair for a pin target health check."""
    relative = str(pin.path.relative_to(root))

    if not pin.path.exists():
        return f"{relative}  {g.bullet.error} not found", False

    try:
        compiled = re.compile(pin.pattern)
    except re.error as exc:
        return f"{relative}  {g.bullet.error} bad pattern: {exc}", False

    text = pin.path.read_text(encoding="utf-8")
    if compiled.search(text) is None:
        return f"{relative}  {g.bullet.warning} no match", True

    return f"{relative}  {g.git.clean} match", True


def cmd_doctor(args: argparse.Namespace) -> int:  # noqa: ARG001
    """Check the health of the rrt configuration."""
    root = Path.cwd()
    g = output.GLYPHS

    try:
        config = load_or_autodetect_config(root)
    except FileNotFoundError:
        checked = iter_config_files(root)
        print(format_missing_tool_rrt_guidance(root, checked), file=sys.stderr)
        return 1
    except ValueError as exc:
        if is_missing_tool_rrt_error(exc):
            print(output.warning("No [tool.rrt] configuration found."), file=sys.stderr)
            print(format_missing_tool_rrt_guidance(root, iter_config_files(root)), file=sys.stderr)
            return 1
        print(str(exc), file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if config.autodetected:
        print(output.warning(format_autodetected_config_notice(config)), file=sys.stderr)

    source = "(auto-detected)" if config.autodetected else str(config.config_file.relative_to(root))
    group_count = len(config.version_groups)
    plural = "group" if group_count == 1 else "groups"
    print(bold("rrt doctor"))
    print(render_table([("config file", source), ("version groups", f"{group_count} {plural}")]))
    print()

    all_ok = True

    tree_entries: list[tuple[str, bool, list | None]] = []

    for group in config.version_groups:
        group_children: list[tuple[str, bool, list | None]] = []
        group_ok = True

        # Version targets
        vtarget_children: list[tuple[str, bool, list | None]] = []
        for target in group.version_targets:
            label, is_ok = _check_version_target(target, root, g)
            vtarget_children.append((label, False, None))
            if not is_ok:
                group_ok = False

        group_children.append(("version_targets", True, vtarget_children or None))

        # Pin targets (group-level + global, deduplicated)
        all_pins = group.pin_targets + config.global_pin_targets
        if all_pins:
            seen: set[tuple[object, str]] = set()
            unique_pins = []
            for pin in all_pins:
                key = (pin.path, pin.pattern)
                if key not in seen:
                    seen.add(key)
                    unique_pins.append(pin)

            pin_children: list[tuple[str, bool, list | None]] = []
            for pin in unique_pins:
                label, is_ok = _check_pin_target(pin, root, g)
                pin_children.append((label, False, None))
                if not is_ok:
                    group_ok = False

            group_children.append(("pin_targets", True, pin_children))

        # Changelog file
        cl = group.changelog_file
        if cl.exists():
            cl_label = f"{cl.relative_to(root)}  {g.git.clean} exists"
        else:
            cl_label = f"{cl.relative_to(root)}  {g.bullet.warning} not found"
            group_ok = False

        group_children.append((cl_label, False, None))

        group_marker = str(g.git.clean) if group_ok else str(g.bullet.error)
        group_name = f"{group_marker} [{group.name}]"
        tree_entries.append((group_name, True, group_children))

        if not group_ok:
            all_ok = False

    print(output.rule("Health checks"))
    print(g.tree.render(tree_entries))
    print()

    if all_ok:
        print(output.ok("All health checks passed."))
        return 0
    else:
        print(output.error("One or more health checks failed."))
        return 1


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the doctor command."""
    parser = subparsers.add_parser(
        "doctor",
        help="Check the health of the rrt configuration (files, patterns, versions).",
    )
    parser.set_defaults(handler=cmd_doctor)
