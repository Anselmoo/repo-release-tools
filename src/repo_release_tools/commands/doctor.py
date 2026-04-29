"""rrt doctor — health-check the rrt configuration for the current repository."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from repo_release_tools.ui.color import success, info, warning, error as color_error
from repo_release_tools.ui.glyphs import GLYPHS
from repo_release_tools.ui.layout import rule, terminal_width
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
from repo_release_tools.version_targets import read_version_string


def _check_version_target(target: VersionTarget, root: Path, g) -> tuple[str, bool, str]:
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


def _check_pin_target(pin: PinTarget, root: Path, g) -> tuple[str, bool, str]:
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
    g = GLYPHS

    try:
        config = load_or_autodetect_config(root)
    except FileNotFoundError:
        checked = iter_config_files(root)
        print(format_missing_tool_rrt_guidance(root, checked), file=sys.stderr)
        return 1
    except ValueError as exc:
        if is_missing_tool_rrt_error(exc):
            print(
                f"{g.bullet.warning} {warning('No [tool.rrt] configuration found.')}",
                file=sys.stderr,
            )
            print(format_missing_tool_rrt_guidance(root, iter_config_files(root)), file=sys.stderr)
            return 1
        print(str(exc), file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if config.autodetected:
        print(
            f"{g.bullet.warning} {warning(format_autodetected_config_notice(config))}",
            file=sys.stderr,
        )

    source = "(auto-detected)" if config.autodetected else str(config.config_file.relative_to(root))
    group_count = len(config.version_groups)
    plural = "group" if group_count == 1 else "groups"
    print(f"{g.bullet.ok} {success('rrt doctor')}")
    print(f"{g.arrow.right} {info(f'Config file: {source}')}")
    print(f"{g.arrow.right} {info(f'Version groups: {group_count} {plural}')}")
    print()

    all_ok = True
    W = terminal_width()

    print(rule("Health checks", width=W))

    for group in config.version_groups:
        group_ok = True
        statuses: list[str] = []

        for target in group.version_targets:
            message, ok, severity = _check_version_target(target, root, g)
            symbol = (
                g.bullet.ok
                if severity == "ok"
                else g.bullet.warning
                if severity == "warning"
                else g.bullet.error
            )
            statuses.append(f"  {symbol} {message}")
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
                message, ok, severity = _check_pin_target(pin, root, g)
                symbol = (
                    g.bullet.ok
                    if severity == "ok"
                    else g.bullet.warning
                    if severity == "warning"
                    else g.bullet.error
                )
                statuses.append(f"  {symbol} {message}")
                if not ok:
                    group_ok = False
                if not ok:
                    group_ok = False

        cl = group.changelog_file
        if cl.exists():
            message = f"{cl.relative_to(root)} exists"
            symbol = g.bullet.ok
        else:
            message = f"{cl.relative_to(root)} not found"
            symbol = g.bullet.error
            group_ok = False
        statuses.append(f"  {symbol} {message}")

        if group_ok:
            header = f"{g.bullet.ok} {success(f'[{group.name}]')}"
        else:
            header = f"{g.bullet.error} {color_error(f'[{group.name}]')}"
        print(header)
        for line in statuses:
            print(line)
        print()

        if not group_ok:
            all_ok = False

    if all_ok:
        print(f"{g.bullet.ok} {success('All health checks passed.')}")
        return 0
    else:
        print(f"{g.bullet.error} {color_error('One or more health checks failed.')}")
        return 1


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the doctor command."""
    parser = subparsers.add_parser(
        "doctor",
        help="Check the health of the rrt configuration (files, patterns, versions).",
    )
    parser.set_defaults(handler=cmd_doctor)
