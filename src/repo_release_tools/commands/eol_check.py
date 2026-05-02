"""Check detected runtimes and project minimum versions against end-of-life policy.

## Overview

`rrt eol` helps you answer two questions for one or more languages:

- Is the current host runtime still supported?
- Is the repository's declared minimum version still supported?

It is designed for release pipelines and maintenance workflows where runtime
support windows matter.

## What the command checks

For each requested language, the command checks:

- the host runtime detected on the current machine
- the project minimum version detected from the repository

Each version is compared against EOL records and classified as:

- supported
- expiring soon
- end-of-life
- unknown

When the runtime cannot be detected, the command prints `not detected` instead
of failing that check.

## Data sources

By default, rrt uses bundled EOL data. With `--fetch-live`, it refreshes the
records from endoflife.date for the current run.

Language selection comes from the resolved configuration when available. If no
EOL config is present, the command defaults to Python.

## Policy behavior

The effective thresholds come from `[tool.rrt.eol]` when configured, with CLI
flags applied on top for the current invocation.

Important policy switches:

- `--warn-days` sets the warning window
- `--error-days` sets the failure window
- `--allow-eol` downgrades EOL failures to warnings
- `--language` limits the check to one language

## Output

The command prints a small summary first, then one section per language with
host runtime and project minimum results. If all checks pass it ends with a
success line; otherwise it prints a failure line and returns a non-zero exit
code.

## Examples

```bash
rrt eol
rrt eol --language node --fetch-live
rrt eol --warn-days 90 --error-days 30
```

## Caveats

- Supported languages are limited to the values exposed by rrt's EOL helpers.
- Configured EOL overrides apply per language and version cycle.
- `--allow-eol` changes exit-code behavior, not the underlying status labels.
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from repo_release_tools.config import EolConfig, EolOverride, load_or_autodetect_config
from repo_release_tools.eol import (
    SUPPORTED_LANGUAGES,
    EolRecord,
    EolStatus,
    check_eol_status,
    detect_host_version,
    detect_project_minimum,
    get_eol_records,
    resolve_override_eol,
)
from repo_release_tools.ui import DryRunPrinter

EOL_EPILOG = (
    "  $ rrt eol\n"
    "  $ rrt eol --language node --fetch-live\n"
    "  $ rrt eol --warn-days 90 --error-days 30"
)


def _override_for(
    language: str,
    version: str,
    overrides: tuple[EolOverride, ...],
) -> date | None:
    """Return a configured EOL date override for (language, cycle), or None."""
    return resolve_override_eol(language, version, overrides)


def _int_override(value: int | None, fallback: int) -> int:
    """Return the explicit CLI value when provided, otherwise the fallback."""
    return fallback if value is None else value


def _status_label(status: EolStatus) -> str:
    """Return a short human label for an EolStatus."""
    return {
        "ok": "supported",
        "info": "supported",
        "warn": "expiring soon",
        "error": "end-of-life",
        "unknown": "unknown",
    }.get(status, status)


def _emit_check(
    p: DryRunPrinter,
    label: str,
    version: str | None,
    status: EolStatus,
    record: EolRecord | None,
) -> None:
    """Emit a single EOL check line using the DryRunPrinter."""
    if version is None:
        p.warn(f"  {label}: not detected")
        return

    detail = ""
    if record is not None:
        if record.is_eol:
            detail = " (EOL)"
        elif record.eol_date is not None:
            detail = f" (EOL {record.eol_date})"
        elif record.days_until_eol is not None:
            detail = f" (EOL in {record.days_until_eol}d)"

    msg = f"  {label}: {version} — {_status_label(status)}{detail}"
    if status in ("ok", "info"):
        p.line(msg, ok=True)
    elif status in ("warn", "unknown"):
        p.warn(msg)
    else:
        p.line(msg, ok=False)


def run_eol_checks(
    languages: tuple[str, ...],
    root: Path,
    *,
    warn_days: int,
    error_days: int,
    fetch_live: bool,
    allow_eol: bool,
    overrides: tuple[EolOverride, ...],
    p: DryRunPrinter,
    today: date | None = None,
) -> bool:
    """Run EOL checks for all requested languages.

    Returns True when all checks pass (exit code 0), False when any error.
    """
    all_ok = True

    for language in languages:
        p.section(f"EOL check: {language}")
        records = get_eol_records(language, fetch_live=fetch_live, today=today)

        # Host runtime
        host_ver = detect_host_version(language)
        if host_ver is not None:
            override = _override_for(language, host_ver, overrides)
            host_status, host_record = check_eol_status(
                host_ver,
                records,
                language=language,
                warn_days=warn_days,
                error_days=error_days,
                allow_eol=allow_eol,
                override_eol=override,
                today=today,
            )
        else:
            host_status, host_record = "unknown", None
        _emit_check(p, "Host runtime", host_ver, host_status, host_record)
        if host_status == "error":
            all_ok = False

        # Project minimum
        proj_ver = detect_project_minimum(language, root)
        if proj_ver is not None:
            override = _override_for(language, proj_ver, overrides)
            proj_status, proj_record = check_eol_status(
                proj_ver,
                records,
                language=language,
                warn_days=warn_days,
                error_days=error_days,
                allow_eol=allow_eol,
                override_eol=override,
                today=today,
            )
        else:
            proj_status, proj_record = "unknown", None
        _emit_check(p, "Project minimum", proj_ver, proj_status, proj_record)
        if proj_status == "error":
            all_ok = False

        p.blank_line()

    return all_ok


def cmd_eol(args: argparse.Namespace) -> int:
    """Check host runtimes and project minimums against EOL dates."""
    root = Path.cwd()
    p = DryRunPrinter(False)

    # Determine effective config: CLI flags override config-file values
    eol_cfg: EolConfig | None = None
    try:
        rrt_config = load_or_autodetect_config(root)
        eol_cfg = rrt_config.eol
    except (FileNotFoundError, ValueError, RuntimeError):
        pass  # No rrt config found — fall through to CLI defaults

    if eol_cfg is not None:
        # Merge: CLI flags take priority over config-file values
        warn_days = _int_override(getattr(args, "warn_days", None), eol_cfg.warn_days)
        error_days = _int_override(getattr(args, "error_days", None), eol_cfg.error_days)
        fetch_live: bool = getattr(args, "fetch_live", False) or eol_cfg.fetch_live
        allow_eol: bool = getattr(args, "allow_eol", False) or eol_cfg.allow_eol
        overrides = eol_cfg.overrides
        lang_arg: str | None = getattr(args, "language", None)
        languages: tuple[str, ...] = (lang_arg,) if lang_arg else eol_cfg.languages
    else:
        warn_days = _int_override(getattr(args, "warn_days", None), 180)
        error_days = _int_override(getattr(args, "error_days", None), 0)
        fetch_live = getattr(args, "fetch_live", False)
        allow_eol = getattr(args, "allow_eol", False)
        overrides = ()
        lang_arg = getattr(args, "language", None)
        languages = (lang_arg,) if lang_arg else ("python",)

    p.ok("rrt eol")
    p.action(f"Languages: {', '.join(languages)}")
    p.action(f"Warn threshold: {warn_days}d  Error threshold: {error_days}d")
    if fetch_live:
        p.action("Fetching live data from endoflife.date …")
    p.blank_line()

    all_ok = run_eol_checks(
        languages=languages,
        root=root,
        warn_days=warn_days,
        error_days=error_days,
        fetch_live=fetch_live,
        allow_eol=allow_eol,
        overrides=overrides,
        p=p,
    )

    if all_ok:
        p.ok("All EOL checks passed.")
        return 0

    if allow_eol:
        p.warn("EOL issues found but allow_eol=true — treating as warning only.")
        return 0

    p.line("One or more EOL checks failed.", ok=False)
    return 1


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the eol command."""
    parser = subparsers.add_parser(
        "eol",
        help="Check host runtimes and project minimums against EOL dates.",
        description=(
            "Check detected host runtimes and project minimum versions against end-of-life "
            "dates.\n\n"
            "Uses bundled EOL data by default and can refresh from endoflife.date on demand. "
            "When [tool.rrt.eol] is configured, CLI flags override the configured thresholds "
            "for this invocation."
        ),
        epilog=EOL_EPILOG,
    )
    parser.add_argument(
        "--language",
        metavar="LANG",
        default=None,
        help=(
            "Check one language only "
            f"({', '.join(sorted(SUPPORTED_LANGUAGES))}). Default: from config or python."
        ),
    )
    parser.add_argument(
        "--fetch-live",
        action="store_true",
        default=False,
        dest="fetch_live",
        help="Fetch fresh EOL data from endoflife.date instead of using bundled snapshot.",
    )
    parser.add_argument(
        "--warn-days",
        type=int,
        default=None,
        dest="warn_days",
        metavar="N",
        help="Warn when EOL is within N days (default: 180 or from config).",
    )
    parser.add_argument(
        "--error-days",
        type=int,
        default=None,
        dest="error_days",
        metavar="N",
        help="Error when EOL is within N days (default: 0 or from config = only on actual EOL).",
    )
    parser.add_argument(
        "--allow-eol",
        action="store_true",
        default=False,
        dest="allow_eol",
        help="Downgrade errors to warnings (useful during migration grace periods).",
    )
    parser.set_defaults(handler=cmd_eol)
