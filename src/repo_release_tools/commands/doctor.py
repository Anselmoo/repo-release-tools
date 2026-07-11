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
- `.husky/*` hook scripts when present
- `.github/workflows/*.yml` / `.yaml` when present

The checks are intentionally light-touch: they verify presence, readability,
and whether the file appears to reference repo-release-tools policy checks.
They do **not** replace the deeper feature validators.

## Output and severity

The command prints one grouped report for the core automation surfaces and an
overall status at the end.

- unreadable automation files are errors
- missing hook-manager surfaces are obsolete when another hook manager is active
- missing optional integration surfaces are warnings when no equivalent surface is active
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

- [Runtime EOL tracking](/repo-release-tools/commands/eol_check/)
- [rrt eol (CLI)](/repo-release-tools/commands/rrt-cli/)
- [rrt release check](/repo-release-tools/commands/rrt-cli/)
- [pre-commit / lefthook / husky](/repo-release-tools/commands/hooks/)
- [GitHub Action](/repo-release-tools/action/)
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from repo_release_tools.changelog import (
    RST_UNRELEASED_PLACEHOLDER,
    UNRELEASED_PLACEHOLDER,
    ChangelogFormat,
    detect_changelog_format,
    has_unreleased_section,
)
from repo_release_tools.commands._common import describe_config_load_error
from repo_release_tools.config import (
    find_repo_root,
    format_autodetected_config_notice,
    iter_config_files,
    load_or_autodetect_config,
)
from repo_release_tools.state import (
    build_health_lock,
    health_lock_is_current,
    health_lock_path,
    write_lock,
)
from repo_release_tools.ui import VerbosePrinter

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


def _check_husky(root: Path) -> tuple[str, bool, str]:
    """Inspect Husky hook scripts for repo-release-tools usage."""
    husky_dir = root / ".husky"
    if not husky_dir.exists():
        return ".husky not configured", True, "warning"

    try:
        hook_files = sorted(
            path
            for path in husky_dir.iterdir()
            if path.is_file() and not path.name.startswith((".", "_"))
        )
    except OSError as exc:
        return f".husky unreadable: {exc}", False, "error"

    if not hook_files:
        return ".husky contains no hook scripts", True, "warning"

    markers = ("rrt-hooks", "repo-release-tools")
    matching: list[str] = []
    for hook_file in hook_files:
        try:
            text = _read_text(hook_file)
        except OSError as exc:
            return f"{hook_file.relative_to(root)} unreadable: {exc}", False, "error"
        if any(marker in text for marker in markers):
            matching.append(hook_file.name)

    if matching:
        hooks = ", ".join(matching)
        return f".husky includes repo-release-tools hooks ({hooks})", True, "ok"

    return ".husky exists but no repo-release-tools hooks were detected", True, "warning"


def _obsolete_hook_check(message: str, active_names: list[str]) -> tuple[str, bool, str]:
    """Return an obsolete hook-manager result for a missing inactive surface."""
    active = ", ".join(active_names)
    return f"{message} (obsolete: {active} already configured)", True, "obsolete"


def _check_hook_integrations(root: Path) -> dict[str, tuple[str, bool, str]]:
    """Inspect hook-manager integrations and mark inactive alternatives obsolete."""
    checks: dict[str, tuple[str, bool, str]] = {
        "pre_commit": _check_text_integration(
            root,
            ".pre-commit-config.yaml",
            markers=("repo-release-tools", "rrt-"),
            success_message=".pre-commit-config.yaml includes repo-release-tools hooks",
            warning_message=(
                ".pre-commit-config.yaml exists but no repo-release-tools hooks were detected"
            ),
        ),
        "lefthook": _check_text_integration(
            root,
            "lefthook.yml",
            markers=("rrt-hooks", "repo-release-tools"),
            success_message="lefthook.yml includes repo-release-tools hooks",
            warning_message="lefthook.yml exists but no repo-release-tools hooks were detected",
        ),
        "husky": _check_husky(root),
    }
    active_names = [name for name, (_message, _ok, severity) in checks.items() if severity == "ok"]
    if not active_names:
        return checks

    return {
        name: (
            _obsolete_hook_check(message, active_names)
            if severity == "warning" and message.endswith(" not configured")
            else (message, ok, severity)
        )
        for name, (message, ok, severity) in checks.items()
    }


def _fix_missing_unreleased(root: Path, config: object, *, dry_run: bool) -> list[str]:
    """Add a missing [Unreleased] section to each group's changelog.

    Returns a list of human-readable messages describing what was (or would be) changed.
    """
    changes: list[str] = []
    from repo_release_tools.config import RrtConfig

    if not isinstance(config, RrtConfig):
        return changes

    for group in config.version_groups:
        changelog = group.changelog_file
        if not changelog.exists():
            continue
        content = changelog.read_text(encoding="utf-8")
        fmt = detect_changelog_format(changelog)
        if has_unreleased_section(content, fmt=fmt):
            continue

        if fmt == ChangelogFormat.RST:
            placeholder = RST_UNRELEASED_PLACEHOLDER
        else:
            placeholder = UNRELEASED_PLACEHOLDER

        rel = changelog.relative_to(root) if changelog.is_relative_to(root) else changelog
        if dry_run:
            changes.append(f"Would insert [Unreleased] section into {rel}")
        else:
            updated = f"{placeholder}\n{content}"
            changelog.write_text(updated, encoding="utf-8")
            changes.append(f"Inserted [Unreleased] section into {rel}")

    return changes


@dataclass(frozen=True)
class Options:
    """Typed view of ``argparse.Namespace`` for ``rrt doctor``.

    Built once via :meth:`from_args` at the top of :func:`cmd_doctor` so every
    flag has a single, typed read site instead of scattered
    ``getattr(args, ..., default)`` calls throughout the function body.
    """

    fix: bool
    fix_dry_run: bool
    snapshot: bool
    check: bool
    strict: bool
    verbose: int

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> Options:
        """Build an :class:`Options` from a parsed ``argparse.Namespace``."""
        # NOTE: every flag below is given a real default by doctor.py's own
        # register() (or, for --verbose, by cli.py's global parser), so a
        # Namespace produced by argparse always carries every attribute.
        # The getattr fallbacks here exist only because some unit tests in
        # tests/commands/test_doctor.py construct sparse argparse.Namespace
        # objects by hand instead of going through register(); this is the
        # single translation point that absorbs that, so the rest of
        # cmd_doctor can read opts.x unconditionally.
        return cls(
            fix=getattr(args, "fix", False),
            fix_dry_run=getattr(args, "fix_dry_run", False),
            snapshot=getattr(args, "snapshot", False),
            check=getattr(args, "check", False),
            strict=getattr(args, "strict", False),
            verbose=getattr(args, "verbose", 0) or 0,
        )


def cmd_doctor(args: argparse.Namespace) -> int:
    """Check the health of the rrt configuration."""
    opts = Options.from_args(args)
    root = find_repo_root(Path.cwd())
    verbose = opts.verbose

    try:
        config = load_or_autodetect_config(root)
    except FileNotFoundError as exc:
        err = describe_config_load_error(exc, root, no_config_file_checked=iter_config_files(root))
        VerbosePrinter(verbose=verbose).line(err.text, ok=False, stream=sys.stderr)
        return 1
    except (ValueError, RuntimeError) as exc:
        err = describe_config_load_error(exc, root)
        p = VerbosePrinter(verbose=verbose)
        if err.kind == "missing_tool_rrt":
            p.warn("No [tool.rrt] configuration found.", stream=sys.stderr)
            p.action(err.text, stream=sys.stderr)
        else:
            p.line(err.text, ok=False, stream=sys.stderr)
        return 1

    p = VerbosePrinter(verbose=verbose)
    if config.autodetected:
        p.warn(format_autodetected_config_notice(config), stream=sys.stderr)

    source = "(auto-detected)" if config.autodetected else str(config.config_file.relative_to(root))
    group_count = len(config.version_groups)
    plural = "group" if group_count == 1 else "groups"
    p.ok("rrt doctor")
    p.action(f"Config file: {source}")
    p.action(f"Version groups: {group_count} {plural}")
    p.verbose_line(f"doctor: {root}", level=1)
    p.verbose_line(f"  config: {source}", level=2)
    p.verbose_line(f"  groups: {group_count}", level=2)
    p.blank_line()

    hook_checks = _check_hook_integrations(root)
    named_checks: list[tuple[str, tuple[str, bool, str]]] = [
        ("pre_commit", hook_checks["pre_commit"]),
        ("lefthook", hook_checks["lefthook"]),
        ("husky", hook_checks["husky"]),
        ("workflows", _check_github_workflows(root)),
    ]

    # Structured results for snapshot/check
    check_results: list[dict[str, str]] = [
        {"name": name, "status": severity, "message": message}
        for name, (message, _ok, severity) in named_checks
    ]

    if opts.snapshot:
        lock_data = build_health_lock(check_results)
        write_lock(health_lock_path(root), lock_data)
        p.ok("Health snapshot written to .rrt/health.lock.toml")
        return 0

    if opts.check:
        current, regressions = health_lock_is_current(health_lock_path(root), check_results)
        if current:
            p.ok("No health regressions detected.")
            return 0
        for msg in regressions:
            p.warn(f"  {msg}")
        if opts.strict:
            p.line("Health regressions detected (--strict mode).", ok=False, stream=sys.stderr)
            p.line(
                "Run `rrt doctor --snapshot` to update the health snapshot.",
                ok=False,
                stream=sys.stderr,
            )
            return 1
        p.warn("Health regressions detected (advisory). Use --strict to block.")
        return 0

    all_ok = True
    p.section("Core automation checks")
    for _name, (message, ok, severity) in named_checks:
        p.verbose_line(f"  {_name}: {severity}", level=1)
        match severity:
            case "ok":
                p.line(f"  {message}", ok=True)
            case "obsolete":
                p.obsolete(f"  {message}")
            case "warning":
                p.warn(f"  {message}")
            case _:
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

    if opts.fix or opts.fix_dry_run:
        fixes = _fix_missing_unreleased(root, config, dry_run=opts.fix_dry_run)
        if fixes:
            p.blank_line()
            p.section("Auto-fix results")
            for msg in fixes:
                p.ok(f"  {msg}")
        else:
            p.blank_line()
            p.ok("Nothing to fix — all auto-fixable issues are already resolved.")

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
    parser.add_argument(
        "--fix",
        action="store_true",
        default=False,
        help="Auto-repair fixable issues (e.g. missing [Unreleased] changelog section).",
    )
    parser.add_argument(
        "--fix-dry-run",
        dest="fix_dry_run",
        action="store_true",
        default=False,
        help="Preview what --fix would change without writing files.",
    )
    snapshot_group = parser.add_mutually_exclusive_group()
    snapshot_group.add_argument(
        "--snapshot",
        action="store_true",
        default=False,
        help="Write current health check results to .rrt/health.lock.toml as a baseline.",
    )
    snapshot_group.add_argument(
        "--check",
        action="store_true",
        default=False,
        help="Compare current health against .rrt/health.lock.toml and report regressions.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="With --check: exit 1 on any regression (default: advisory, exit 0).",
    )
