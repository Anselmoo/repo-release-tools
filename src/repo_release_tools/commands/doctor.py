"""rrt doctor — health-check the rrt configuration for the current repository."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

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
from repo_release_tools.ui import DryRunPrinter
from repo_release_tools.version_targets import read_version_string


def _check_version_target(target: VersionTarget, root: Path) -> tuple[str, bool, str]:
    """Return the status message, whether it is okay, and its severity."""
    relative = str(target.path.relative_to(root))
    kind_hint = _describe_version_target(target, root=root).split("(", 1)
    suffix = f" ({kind_hint[1]}" if len(kind_hint) > 1 else ""

    if not target.path.exists():
        return f"{relative}{suffix} not found", False, "error"

    try:
        version = read_version_string(target)
        return f"{relative}{suffix} {version}", True, "ok"
    except (RuntimeError, ValueError):
        return f"{relative}{suffix} version unreadable", True, "warning"


def _check_pin_target(pin: PinTarget, root: Path) -> tuple[str, bool, str]:
    """Return the status message, whether it is okay, and its severity."""
    relative = str(pin.path.relative_to(root))

    if not pin.path.exists():
        return f"{relative} not found", False, "error"

    try:
        compiled = re.compile(pin.pattern)
    except re.error as exc:
        return f"{relative} bad pattern: {exc}", False, "error"

    text = pin.path.read_text(encoding="utf-8")
    if compiled.search(text) is None:
        return f"{relative} no match", True, "warning"

    return f"{relative} match", True, "ok"


def cmd_doctor(args: argparse.Namespace) -> int:  # noqa: ARG001
    """Check the health of the rrt configuration."""
    root = Path.cwd()

    try:
        config = load_or_autodetect_config(root)
    except FileNotFoundError:
        checked = iter_config_files(root)
        p = DryRunPrinter(False)
        p.line(format_missing_tool_rrt_guidance(root, checked), ok=False, stream=sys.stderr)
        return 1
    except ValueError as exc:
        if is_missing_tool_rrt_error(exc):
            p = DryRunPrinter(False)
            p.warn("No [tool.rrt] configuration found.", stream=sys.stderr)
            p.action(
                format_missing_tool_rrt_guidance(root, iter_config_files(root)), stream=sys.stderr
            )
            return 1
        p = DryRunPrinter(False)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1
    except RuntimeError as exc:
        p = DryRunPrinter(False)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1

    p = DryRunPrinter(False)
    if config.autodetected:
        p.warn(format_autodetected_config_notice(config), stream=sys.stderr)

    source = "(auto-detected)" if config.autodetected else str(config.config_file.relative_to(root))
    group_count = len(config.version_groups)
    plural = "group" if group_count == 1 else "groups"
    p.ok("rrt doctor")
    p.action(f"Config file: {source}")
    p.action(f"Version groups: {group_count} {plural}")
    p.blank_line()

    all_ok = True

    p.section("Health checks")

    for group in config.version_groups:
        group_ok = True
        statuses: list[tuple[str, str]] = []

        for target in group.version_targets:
            message, ok, severity = _check_version_target(target, root)
            statuses.append((message, severity))
            if not ok:
                group_ok = False

        all_pins = group.pin_targets + config.global_pin_targets
        if all_pins:
            seen: set[tuple[object, str]] = set()
            unique_pins = []
            for pin in all_pins:
                key = (pin.path, pin.pattern)
                if key not in seen:
                    seen.add(key)
                    unique_pins.append(pin)

            for pin in unique_pins:
                message, ok, severity = _check_pin_target(pin, root)
                statuses.append((message, severity))
                if not ok:
                    group_ok = False

        cl = group.changelog_file
        if cl.exists():
            statuses.append((f"{cl.relative_to(root)} exists", "ok"))
        else:
            statuses.append((f"{cl.relative_to(root)} not found", "error"))
            group_ok = False

        if group_ok:
            p.ok(f"[{group.name}]")
        else:
            p.line(f"[{group.name}]", ok=False)
        for msg, severity in statuses:
            if severity == "ok":
                p.line(f"  {msg}", ok=True)
            elif severity == "warning":
                p.warn(f"  {msg}")
            else:
                p.line(f"  {msg}", ok=False)
        p.blank_line()

        if not group_ok:
            all_ok = False

    if all_ok:
        p.ok("All health checks passed.")
        return 0
    else:
        p.line("One or more health checks failed.", ok=False)
        return 1


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the doctor command."""
    parser = subparsers.add_parser(
        "doctor",
        help="Check the health of the rrt configuration (files, patterns, versions).",
    )
    parser.set_defaults(handler=cmd_doctor)
