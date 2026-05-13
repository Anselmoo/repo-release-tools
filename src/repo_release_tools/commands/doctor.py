"""Validate the core automation health of the resolved rrt configuration.

## Overview

`rrt doctor` is the basics-first repository health check. It focuses on the
shared automation wiring around the resolved configuration — local hooks, CI
workflows, and guidance to the feature-specific checks that own deeper policy
validation.

## What it checks

The command checks the automation surfaces that tell you whether repository
basics are wired correctly:

- `.pre-commit-config.yaml` when present
- `lefthook.yml` when present
- `.github/workflows/*.yml` / `.yaml` when present

The checks are intentionally light-touch: they verify presence, readability,
and whether the file appears to reference repo-release-tools policy checks.
They do **not** replace the deeper feature validators.

## Output and severity

The command prints one grouped report for the core automation surfaces and an
overall status at the end.

- unreadable automation files are errors
- missing optional integration surfaces are warnings
- surfaces that exist but do not appear to reference repo-release-tools are warnings
- readable, recognized surfaces are reported as OK

At the end, `rrt doctor` also points you to the feature-specific commands that
own deeper validation, such as `rrt release check`, `rrt docs check`, and
`rrt eol`.

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

- The command reports core automation health for the resolved configuration,
    not just the visible file in the current directory.
- Feature-specific checks belong to their own surfaces: `rrt release check`,
    `rrt docs check`, and `rrt eol`.
- A warning does not fail the command; only error-level findings do.

## Related docs

- [Runtime EOL tracking](eol.md)
- [rrt eol (CLI)](rrt-cli.md)
- [rrt release check](rrt-cli.md)
- [pre-commit / lefthook](hooks.md)
- [GitHub Action](action.md)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from repo_release_tools.config import (
    format_autodetected_config_notice,
    format_missing_tool_rrt_guidance,
    is_missing_tool_rrt_error,
    iter_config_files,
    load_or_autodetect_config,
)
from repo_release_tools.ui import DryRunPrinter

DOCTOR_EPILOG = "  $ rrt doctor\n  $ rrt release check\n  $ rrt docs check"

# Docs live in the module docstring above — consistent with bump.py / ci_version.py.
SOURCE_OWNED_TOPIC_DOCS: tuple[tuple[str, str], ...] = (("doctor", __doc__ or ""),)


def _read_text(path: Path) -> str:
    """Return text content for a repository automation file."""
    return path.read_text(encoding="utf-8")


def _check_text_integration(
    root: Path,
    relative_path: str,
    *,
    markers: tuple[str, ...],
    success_message: str,
    warning_message: str,
) -> tuple[str, bool, str]:
    """Check a text-based automation surface for repo-release-tools markers."""
    path = root / relative_path
    if not path.exists():
        return f"{relative_path} not configured", True, "warning"

    try:
        text = _read_text(path)
    except OSError as exc:
        return f"{relative_path} unreadable: {exc}", False, "error"

    if any(marker in text for marker in markers):
        return success_message, True, "ok"
    return warning_message, True, "warning"


def _check_github_workflows(root: Path) -> tuple[str, bool, str]:
    """Inspect workflow files for repo-release-tools policy usage."""
    workflows_dir = root / ".github" / "workflows"
    if not workflows_dir.exists():
        return ".github/workflows not configured", True, "warning"

    workflow_files = sorted({*workflows_dir.glob("*.yml"), *workflows_dir.glob("*.yaml")})
    if not workflow_files:
        return ".github/workflows contains no workflow files", True, "warning"

    markers = (
        "Anselmoo/repo-release-tools",
        "repo-release-tools",
        "rrt-hooks",
        "check-doctor",
        "check-release-health",
    )
    matching: list[str] = []
    for workflow_file in workflow_files:
        try:
            text = _read_text(workflow_file)
        except OSError as exc:
            return f"{workflow_file.relative_to(root)} unreadable: {exc}", False, "error"
        if any(marker in text for marker in markers):
            matching.append(workflow_file.name)

    if matching:
        files = ", ".join(matching)
        return (
            f".github/workflows includes repo-release-tools policy checks ({files})",
            True,
            "ok",
        )

    return (
        ".github/workflows has workflow files but no repo-release-tools policy step detected",
        True,
        "warning",
    )


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
                format_missing_tool_rrt_guidance(root, iter_config_files(root)),
                stream=sys.stderr,
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

    statuses = [
        _check_text_integration(
            root,
            ".pre-commit-config.yaml",
            markers=("repo-release-tools", "rrt-"),
            success_message=".pre-commit-config.yaml includes repo-release-tools hooks",
            warning_message=(
                ".pre-commit-config.yaml exists but no repo-release-tools hooks were detected"
            ),
        ),
        _check_text_integration(
            root,
            "lefthook.yml",
            markers=("rrt-hooks", "repo-release-tools"),
            success_message="lefthook.yml includes repo-release-tools hooks",
            warning_message="lefthook.yml exists but no repo-release-tools hooks were detected",
        ),
        _check_github_workflows(root),
    ]

    all_ok = True
    p.section("Core automation checks")
    for message, ok, severity in statuses:
        if severity == "ok":
            p.line(f"  {message}", ok=True)
        elif severity == "warning":
            p.warn(f"  {message}")
        else:
            p.line(f"  {message}", ok=False)
        if not ok:
            all_ok = False

    p.blank_line()
    if all_ok:
        p.ok("Core automation checks passed.")
    else:
        p.line("One or more core automation checks failed.", ok=False)

    p.blank_line()
    p.warn(
        "Compatibility note: release-target validation lives in 'rrt release check'. "
        "Use both checks for historical doctor coverage.",
    )
    p.blank_line()
    p.section("Feature-specific checks")
    p.action("Run 'rrt release check' for version targets, pin targets, and changelog files.")
    if config.docs is not None:
        p.action("Run 'rrt docs check' for source-owned docs lockfile and marker health.")
    if config.eol is not None:
        p.action("Run 'rrt eol' for runtime support and end-of-life policy checks.")

    return 0 if all_ok else 1


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the doctor command."""
    parser = subparsers.add_parser(
        "doctor",
        help="Check core automation wiring for the resolved rrt configuration.",
        description=(
            "Validate the core automation wiring for the current repository.\n\n"
            "Use `rrt doctor` for repository basics, then run feature-specific checks like "
            "`rrt release check`, `rrt docs check`, or `rrt eol` for deeper validation."
        ),
        epilog=DOCTOR_EPILOG,
    )
    parser.set_defaults(handler=cmd_doctor)
