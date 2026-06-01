"""Validate release-oriented rrt configuration targets for the current repository.

## Overview

`rrt release check` is the feature-specific health gate for release automation.
It focuses on the config targets that drive version bumps and changelog updates,
without mixing in broader repository automation checks.

## What it checks

For each resolved version group, the command checks:

- version target files exist
- version target values can be read
- pin target patterns compile as regular expressions
- pin target files contain at least one match
- the group changelog file exists

It also checks any global pin targets, deduplicating repeated path/pattern
pairs so the same target is not reported twice.

## Output and severity

The command prints one grouped report per version group and an overall status at
the end.

- missing targets and missing changelog files are errors
- unreadable version content is reported as a warning
- pin patterns that compile but do not match are reported as a warning
- valid matches and readable targets are reported as OK

## Config discovery behavior

If no config file can be found in the current directory or any ancestor, the
command prints repository guidance and exits with an error. The supported
config roots are `pyproject.toml`, `package.json`, `Cargo.toml`, `.rrt.toml`,
and `.config/rrt.toml`.

If a config is auto-detected, the command emits a notice on stderr before the
main report so you can tell that rrt did not use an explicitly selected file.

## Examples

```bash
rrt release check
```

The command can be run from a nested subdirectory inside the repository; rrt
walks upward until it finds the repo root and then checks the resolved config
from there.

Version targets may also point at Go, Rust, or .NET-style version files when
you need to keep multiple language surfaces aligned.

## Related docs

- [rrt doctor](doctor.md)
- [rrt eol (CLI)](rrt-cli.md)
- [pre-commit / lefthook](hooks.md)
- [GitHub Action](action.md)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from repo_release_tools.commands.release_notes import register_subcommand as _register_notes
from repo_release_tools.config import (
    PinTarget,
    VersionTarget,
    _describe_version_target,
    find_repo_root,
    format_autodetected_config_notice,
    format_missing_tool_rrt_guidance,
    is_missing_tool_rrt_error,
    iter_config_files,
    load_or_autodetect_config,
)
from repo_release_tools.ui import DryRunPrinter
from repo_release_tools.version.targets import read_version_string

RELEASE_CHECK_EPILOG = "  $ rrt release check"

SOURCE_OWNED_TOPIC_DOCS: tuple[tuple[str, str], ...] = (("release_check", __doc__ or ""),)


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


def cmd_release_check(args: argparse.Namespace) -> int:  # noqa: ARG001
    """Check release-oriented version, pin, and changelog targets."""
    verbose: int = getattr(args, "verbose", 0) or 0
    root = find_repo_root(Path.cwd())

    try:
        config = load_or_autodetect_config(root)
    except FileNotFoundError:
        checked = iter_config_files(root)
        p = DryRunPrinter(False, verbose=verbose)
        p.line(format_missing_tool_rrt_guidance(root, checked), ok=False, stream=sys.stderr)
        return 1
    except ValueError as exc:
        if is_missing_tool_rrt_error(exc):
            p = DryRunPrinter(False, verbose=verbose)
            p.warn("No [tool.rrt] configuration found.", stream=sys.stderr)
            p.action(
                format_missing_tool_rrt_guidance(root, iter_config_files(root)),
                stream=sys.stderr,
            )
            return 1
        p = DryRunPrinter(False, verbose=verbose)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1
    except RuntimeError as exc:
        p = DryRunPrinter(False, verbose=verbose)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1

    p = DryRunPrinter(False, verbose=verbose)
    if config.autodetected:
        p.warn(format_autodetected_config_notice(config), stream=sys.stderr)

    source = "(auto-detected)" if config.autodetected else str(config.config_file.relative_to(root))
    group_count = len(config.version_groups)
    plural = "group" if group_count == 1 else "groups"
    p.ok("rrt release check")
    p.action(f"Config file: {source}")
    p.action(f"Version groups: {group_count} {plural}")
    p.blank_line()

    all_ok = True
    p.section("Release checks")

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

        changelog = group.changelog_file
        if changelog.exists():
            statuses.append((f"{changelog.relative_to(root)} exists", "ok"))
        else:
            statuses.append((f"{changelog.relative_to(root)} not found", "error"))
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
        p.ok("All release checks passed.")
        return 0

    p.line("One or more release checks failed.", ok=False)
    return 1


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register release-oriented commands."""
    parser = subparsers.add_parser(
        "release",
        help="Release-oriented checks and workflows.",
        description=(
            "Release-specific workflows and checks.\n\n"
            "Use `rrt release check` to validate version targets, pin targets, and "
            "changelog files without mixing in broader repository automation checks."
        ),
    )
    release_subparsers = parser.add_subparsers(
        dest="release_command",
        metavar="<release_command>",
        required=True,
    )

    check_parser = release_subparsers.add_parser(
        "check",
        help="Validate version targets, pin targets, and changelog files.",
        description=(
            "Validate the release-oriented parts of the resolved rrt configuration for the "
            "current repository, starting from the nearest repo root above the current "
            "working directory."
        ),
        epilog=RELEASE_CHECK_EPILOG,
    )
    check_parser.set_defaults(handler=cmd_release_check)

    _register_notes(release_subparsers)
