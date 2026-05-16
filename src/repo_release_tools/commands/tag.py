"""Create and validate release tags for the current repository.

## Overview

``rrt tag`` provides two subcommands:

* ``rrt tag create`` — create an annotated git tag matching the current version
  read from the rrt configuration.
* ``rrt tag check`` — validate that existing tags follow the configured naming
  convention and that the most recent tag matches the current configured version.

## Tag format

By default tags are prefixed with ``v`` (e.g. ``v1.2.3``).  The prefix can be
changed with ``--prefix`` or removed entirely with ``--no-prefix``.

## Examples

```bash
rrt tag create
rrt tag create --push
rrt tag create --prefix "" --message "Release 1.2.3"
rrt tag check
rrt tag check --strict
```
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from repo_release_tools.config import (
    format_missing_tool_rrt_guidance,
    is_missing_tool_rrt_error,
    iter_config_files,
    load_or_autodetect_config,
)
from repo_release_tools.ui import DryRunPrinter
from repo_release_tools.version.targets import read_group_current_version


def _git(args: list[str], cwd: Path, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=check, cwd=cwd)


def _tag_name(version: str, prefix: str) -> str:
    return f"{prefix}{version}"


def _load_config_and_version(root: Path, group_name: str | None) -> tuple[object, str] | None:
    """Load config and return (config, version_str), printing errors on failure."""
    try:
        config = load_or_autodetect_config(root)
    except FileNotFoundError:
        p = DryRunPrinter(False)
        p.line(
            format_missing_tool_rrt_guidance(root, iter_config_files(root)),
            ok=False,
            stream=sys.stderr,
        )
        return None
    except ValueError as exc:
        if is_missing_tool_rrt_error(exc):
            p = DryRunPrinter(False)
            p.line("No [tool.rrt] configuration found.", ok=False, stream=sys.stderr)
            return None
        p = DryRunPrinter(False)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return None
    except RuntimeError as exc:
        p = DryRunPrinter(False)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return None

    try:
        group = config.resolve_group(group_name)
    except ValueError as exc:
        p = DryRunPrinter(False)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return None

    current = read_group_current_version(group)
    return config, str(current)


def _existing_tags(root: Path) -> list[str]:
    """Return all tags sorted by version."""
    try:
        result = _git(["git", "tag", "--sort=-v:refname"], root)
        return [t.strip() for t in result.stdout.splitlines() if t.strip()]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []


def cmd_tag_create(args: argparse.Namespace) -> int:
    """Create an annotated git tag matching the current configured version."""
    root = Path.cwd()
    dry_run: bool = getattr(args, "dry_run", False)
    push: bool = getattr(args, "push", False)
    prefix: str = getattr(args, "prefix", "v")
    message: str | None = getattr(args, "message", None)

    result = _load_config_and_version(root, getattr(args, "group", None))
    if result is None:
        return 1
    _config, version = result

    tag = _tag_name(version, prefix)
    msg = message or f"Release {tag}"

    p = DryRunPrinter(dry_run)
    p.blank_line()
    p.header("Tag create", Tag=tag, Message=msg)

    existing = _existing_tags(root)
    if tag in existing and not getattr(args, "force", False):
        p2 = DryRunPrinter(False)
        p2.line(
            f"Tag '{tag}' already exists. Use --force to overwrite.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    if dry_run:
        p.line(f"would run: git tag -a {tag} -m {msg!r}")
        p.line("no changes were made")
        return 0

    try:
        if tag in existing and getattr(args, "force", False):
            _git(["git", "tag", "-d", tag], root)
        _git(["git", "tag", "-a", tag, "-m", msg], root)
    except subprocess.CalledProcessError as exc:
        p2 = DryRunPrinter(False)
        p2.line(f"git tag failed: {exc.stderr.strip()}", ok=False, stream=sys.stderr)
        return 1

    p.ok(f"Created tag {tag!r}")

    if push:
        try:
            _git(["git", "push", "origin", tag], root)
            p.ok(f"Pushed {tag!r} to origin")
        except subprocess.CalledProcessError as exc:
            p2 = DryRunPrinter(False)
            p2.line(f"git push failed: {exc.stderr.strip()}", ok=False, stream=sys.stderr)
            return 1

    return 0


def cmd_tag_check(args: argparse.Namespace) -> int:
    """Validate existing tags match the configured naming convention."""
    root = Path.cwd()
    strict: bool = getattr(args, "strict", False)
    prefix: str = getattr(args, "prefix", "v")

    result = _load_config_and_version(root, getattr(args, "group", None))
    if result is None:
        return 1
    _config, version = result

    expected_tag = _tag_name(version, prefix)
    existing_tags = _existing_tags(root)

    p = DryRunPrinter(False)
    p.blank_line()
    p.header("Tag check", Expected=expected_tag, Total=str(len(existing_tags)))

    errors: list[str] = []

    for tag in existing_tags:
        if not tag.startswith(prefix):
            errors.append(f"Tag '{tag}' does not match prefix '{prefix}'")

    if expected_tag not in existing_tags:
        if strict:
            errors.append(f"Expected tag '{expected_tag}' not found")
        else:
            p.line(f"  Expected tag '{expected_tag}' not found (run `rrt tag create`)", ok=False)

    if errors:
        p.blank_line()
        for err in errors:
            p.line(f"  {err}", ok=False)
        return 1

    p.ok(f"Tag '{expected_tag}' is present and consistent.")
    return 0


_TAG_EPILOG = (
    "  $ rrt tag create\n"
    "  $ rrt tag create --push\n"
    "  $ rrt tag create --prefix '' --message 'Release 1.2.3'\n"
    "  $ rrt tag check\n"
    "  $ rrt tag check --strict"
)


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the tag command."""
    parser = subparsers.add_parser(
        "tag",
        help="Create and validate release tags.",
        description=(
            "Create annotated git tags from the current configured version, "
            "or check that existing tags follow the naming convention."
        ),
    )
    tag_sub = parser.add_subparsers(
        dest="tag_command",
        metavar="<tag_command>",
        required=True,
    )

    # --- create ---------------------------------------------------------------
    create_parser = tag_sub.add_parser(
        "create",
        help="Create an annotated git tag for the current version.",
        description="Create an annotated git tag matching the current configured version.",
        epilog=_TAG_EPILOG,
    )
    create_parser.add_argument(
        "--prefix",
        default="v",
        metavar="PREFIX",
        help="Tag prefix (default: 'v'). Pass empty string for no prefix.",
    )
    create_parser.add_argument(
        "--message",
        default=None,
        metavar="MSG",
        help="Annotation message. Defaults to 'Release <tag>'.",
    )
    create_parser.add_argument(
        "--push",
        action="store_true",
        help="Push the tag to origin after creating it.",
    )
    create_parser.add_argument(
        "--force",
        action="store_true",
        help="Delete and recreate the tag if it already exists.",
    )
    create_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would happen without making changes.",
    )
    create_parser.add_argument(
        "--group",
        default=None,
        metavar="GROUP",
        help="Version group to read when multiple groups are configured.",
    )
    create_parser.set_defaults(handler=cmd_tag_create)

    # --- check ----------------------------------------------------------------
    check_parser = tag_sub.add_parser(
        "check",
        help="Validate existing tags against the configured version.",
        description="Check that existing git tags follow the naming convention.",
        epilog=_TAG_EPILOG,
    )
    check_parser.add_argument(
        "--prefix",
        default="v",
        metavar="PREFIX",
        help="Expected tag prefix (default: 'v').",
    )
    check_parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if the expected tag for the current version is missing.",
    )
    check_parser.add_argument(
        "--group",
        default=None,
        metavar="GROUP",
        help="Version group to read when multiple groups are configured.",
    )
    check_parser.set_defaults(handler=cmd_tag_check)
