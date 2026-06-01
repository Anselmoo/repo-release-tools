"""Create and validate release tags for the current repository.

## Overview

`rrt tag` centralizes the management of Git release tags, ensuring that the
repository's version history remains consistent with its configuration. It
automates the creation of annotated tags and provides validation tools to
verify that existing tags align with the project's versioning policy.

The command supports both manual release tagging and automated verification in
CI pipelines, helping to maintain a clean and reliable release record.

## Responsibilities

- create annotated Git tags matching the current configured version
- support custom tag prefixes and annotation messages
- validate that existing tags follow the expected naming convention
- verify that the expected tag for the current version is present
- optionally push newly created tags to the remote repository

## Tag Format

By default, tags are created with a `v` prefix (e.g., `v1.2.3`) as is standard
for many version control and release automation tools.

- The prefix can be customized using `--prefix <string>`.
- The prefix can be removed entirely using `--prefix ""`.
- Tag names are derived directly from the current version read from the
  active `[tool.rrt]` configuration group.

## Behavior

- **create**: Reads the current version from config, builds the tag name and
  message, and executes `git tag -a`. Refuses to overwrite existing tags
  unless `--force` is used.
- **check**: Scans all repository tags, identifies those that don't match the
  requested prefix, and verifies the presence of the tag corresponding to the
  current version.
- **push**: When `--push` is used with `create`, the command executes
  `git push origin <tag>` after a successful local tag creation.
- **dry-run**: Previews the `git` commands that would be executed without
  modifying the repository.

## Examples

- `rrt tag create`
- `rrt tag create --push --message "Production release v1.5.0"`
- `rrt tag create --prefix "" --force`
- `rrt tag check`
- `rrt tag check --strict --prefix "rel-"`

## Caveats

- Requires a valid Git repository and `repo-release-tools` configuration.
- Annotated tags are used to ensure that metadata (author, date, message) is
  correctly captured in the Git history.
- The `check --strict` mode is recommended for CI pipelines to ensure that a
  tag was correctly created before a release proceeds.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from repo_release_tools.config import (
    find_repo_root,
    format_missing_tool_rrt_guidance,
    is_missing_tool_rrt_error,
    iter_config_files,
    load_or_autodetect_config,
)
from repo_release_tools.ui import DryRunPrinter, VerbosePrinter
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
        p = VerbosePrinter()
        p.line(
            format_missing_tool_rrt_guidance(root, iter_config_files(root)),
            ok=False,
            stream=sys.stderr,
        )
        return None
    except ValueError as exc:
        if is_missing_tool_rrt_error(exc):
            p = VerbosePrinter()
            p.line("No [tool.rrt] configuration found.", ok=False, stream=sys.stderr)
            return None
        p = VerbosePrinter()
        p.line(str(exc), ok=False, stream=sys.stderr)
        return None
    except RuntimeError as exc:
        p = VerbosePrinter()
        p.line(str(exc), ok=False, stream=sys.stderr)
        return None

    try:
        group = config.resolve_group(group_name)
    except ValueError as exc:
        p = VerbosePrinter()
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
    verbose: int = getattr(args, "verbose", 0) or 0
    root = find_repo_root(Path.cwd())
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

    p = DryRunPrinter(dry_run, verbose=verbose)
    p.blank_line()
    p.header("Tag create", Tag=tag, Message=msg)

    existing = _existing_tags(root)
    if tag in existing and not getattr(args, "force", False):
        p2 = VerbosePrinter(verbose=verbose)
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
        p2 = VerbosePrinter(verbose=verbose)
        p2.line(f"git tag failed: {exc.stderr.strip()}", ok=False, stream=sys.stderr)
        return 1

    p.ok(f"Created tag {tag!r}")

    if push:
        try:
            _git(["git", "push", "origin", tag], root)
            p.ok(f"Pushed {tag!r} to origin")
        except subprocess.CalledProcessError as exc:
            p2 = VerbosePrinter(verbose=verbose)
            p2.line(f"git push failed: {exc.stderr.strip()}", ok=False, stream=sys.stderr)
            return 1

    return 0


def cmd_tag_check(args: argparse.Namespace) -> int:
    """Validate existing tags match the configured naming convention."""
    verbose: int = getattr(args, "verbose", 0) or 0
    root = find_repo_root(Path.cwd())
    strict: bool = getattr(args, "strict", False)
    prefix: str = getattr(args, "prefix", "v")

    result = _load_config_and_version(root, getattr(args, "group", None))
    if result is None:
        return 1
    _config, version = result

    expected_tag = _tag_name(version, prefix)
    existing_tags = _existing_tags(root)

    p = VerbosePrinter(verbose=verbose)
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
