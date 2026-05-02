"""Validate the health of the resolved rrt configuration for the current repository.

## Overview

`rrt doctor` is a repository health check for release automation. It inspects
the active configuration and looks for the kinds of issues that usually cause
release jobs to fail late: missing files, broken patterns, unreadable version
targets, and optional runtime EOL policy problems.

## What it checks

For each resolved version group, the command checks:

- version target files exist
- version target values can be read
- pin target patterns compile as regular expressions
- pin target files contain at least one match
- the group changelog file exists

It also checks any global pin targets, deduplicating repeated path/pattern
pairs so the same target is not reported twice.

If `[tool.rrt.eol]` is configured, the command adds a runtime EOL section that
checks the configured languages against the repository's host runtime and
project minimum versions.

## Output and severity

The command prints a grouped report for each version group and an overall
status at the end.

- missing targets and missing changelog files are errors
- unreadable version content is reported as a warning
- pin patterns that compile but do not match are reported as a warning
- valid matches and readable targets are reported as OK

For EOL checks, the command uses the configured thresholds from `[tool.rrt.eol]`
and reports the host runtime and project minimum for each configured language.

## Config discovery behavior

If no config file can be found, the command prints repository guidance and
exits with an error.

If a config is auto-detected, the command emits a notice on stderr before the
main report so you can tell that rrt did not use an explicitly selected file.

## Examples

```bash
rrt doctor
```

## Caveats

- The command reports health for the resolved configuration, not just the
  visible file in the current directory.
- EOL checks are only shown when EOL policy is configured.
- A warning does not fail the command; only error-level findings do.

## Related docs

- [Runtime EOL tracking](eol.md)
- [rrt eol (CLI)](rrt-cli.md)
- [pre-commit / lefthook](hooks.md)
- [GitHub Action](action.md)
"""

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
from repo_release_tools.eol import (
    check_eol_status,
    detect_host_version,
    detect_project_minimum,
    get_eol_records,
)
from repo_release_tools.ui import DryRunPrinter
from repo_release_tools.version_targets import read_version_string

DOCTOR_EPILOG = "  $ rrt doctor"

# Docs live in the module docstring above — consistent with bump.py / ci_version.py.
SOURCE_OWNED_TOPIC_DOCS: tuple[tuple[str, str], ...] = (("doctor", __doc__ or ""),)


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
    else:
        p.line("One or more health checks failed.", ok=False)

    # EOL section — only shown when [tool.rrt.eol] is configured
    if config.eol is not None:
        eol_cfg = config.eol
        p.blank_line()
        p.section("Runtime EOL")
        eol_all_ok = True
        for language in eol_cfg.languages:
            records = get_eol_records(language, fetch_live=eol_cfg.fetch_live)

            # Build override map for this language
            from datetime import date as _date  # noqa: PLC0415

            def _override(ver: str) -> _date | None:
                from repo_release_tools.eol import _parse_cycle  # noqa: PLC0415

                cycle = _parse_cycle(ver)
                if cycle is None:
                    return None
                lang_lower = language.lower()
                for ov in eol_cfg.overrides:
                    if ov.language.lower() == lang_lower and ov.cycle == cycle:
                        try:
                            return _date.fromisoformat(ov.eol)
                        except ValueError:
                            return None
                return None

            for label, version in [
                ("Host runtime", detect_host_version(language)),
                ("Project minimum", detect_project_minimum(language, root)),
            ]:
                if version is None:
                    p.warn(f"  {language} {label}: not detected")
                    continue
                ov = _override(version)
                status, record = check_eol_status(
                    version,
                    records,
                    language=language,
                    warn_days=eol_cfg.warn_days,
                    error_days=eol_cfg.error_days,
                    allow_eol=eol_cfg.allow_eol,
                    override_eol=ov,
                )
                detail = ""
                if record is not None:
                    if record.is_eol:
                        detail = " (EOL)"
                    elif record.eol_date is not None:
                        detail = f" (EOL {record.eol_date})"
                msg = f"  {language} {label}: {version}{detail}"
                if status in ("ok", "info"):
                    p.line(msg, ok=True)
                elif status == "warn":
                    p.warn(msg)
                else:
                    p.line(msg, ok=False)
                    if not eol_cfg.allow_eol:
                        eol_all_ok = False
                        all_ok = False
        p.blank_line()
        if eol_all_ok:
            p.ok("All EOL checks passed.")
        else:
            p.line("One or more EOL checks failed.", ok=False)

    if all_ok:
        return 0
    return 1


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the doctor command."""
    parser = subparsers.add_parser(
        "doctor",
        help="Check the health of the rrt configuration (files, patterns, versions).",
        description=(
            "Validate the resolved rrt configuration for the current repository.\n\n"
            "Checks configured version targets, pin patterns, changelog files, and optional "
            "runtime EOL policy so you can catch broken release automation before a bump or "
            "release run."
        ),
        epilog=DOCTOR_EPILOG,
    )
    parser.set_defaults(handler=cmd_doctor)
