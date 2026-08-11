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
from dataclasses import dataclass
from pathlib import Path

from repo_release_tools.commands._common import (
    describe_config_load_error,
    find_duplicate_group_names,
    parse_group_names,
)
from repo_release_tools.commands._registry import CommandCategory, CommandGroup, register_command
from repo_release_tools.config import (
    VersionGroup,
    find_repo_root,
    iter_config_files,
    load_or_autodetect_config,
)
from repo_release_tools.ui import DryRunPrinter, VerbosePrinter
from repo_release_tools.version.targets import read_group_current_version


def _git(args: list[str], cwd: Path, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=check, cwd=cwd)


def _tag_name(version: str, prefix: str) -> str:
    return f"{prefix}{version}"


def _tag_name_for_group(version: str, prefix: str, group_name: str) -> str:
    """Render --prefix's {group} token (batch mode only), then build the tag name.

    Uses ``str.replace``, not ``str.format``: a plain ``.format(group=...)``
    would raise ``KeyError`` on any *other* stray ``{...}`` in a user's custom
    prefix (e.g. ``--prefix "release-{build}"``). ``.replace`` only ever
    touches the one documented token and is a no-op for any prefix without it.
    """
    return f"{prefix.replace('{group}', group_name)}{version}"


def _load_config_and_version(root: Path, group_name: str | None) -> tuple[object, str] | None:
    """Load config and return (config, version_str), printing errors on failure."""
    try:
        config = load_or_autodetect_config(root)
    except FileNotFoundError as exc:
        err = describe_config_load_error(exc, root, no_config_file_checked=iter_config_files(root))
        VerbosePrinter().line(err.text, ok=False, stream=sys.stderr)
        return None
    except (ValueError, RuntimeError) as exc:
        err = describe_config_load_error(exc, root)
        p = VerbosePrinter()
        if err.kind == "missing_tool_rrt":
            p.line("No [tool.rrt] configuration found.", ok=False, stream=sys.stderr)
        else:
            p.line(err.text, ok=False, stream=sys.stderr)
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


@dataclass(frozen=True)
class TagCreateOptions:
    """Typed view of ``argparse.Namespace`` for ``rrt tag create``.

    Built once via :meth:`from_args` at the top of :func:`cmd_tag_create` so
    every flag it reads has a typed read site instead of scattered
    ``getattr(args, ..., default)`` calls throughout the function body.
    """

    verbose: int
    dry_run: bool
    push: bool
    prefix: str
    message: str | None
    group: str | None
    force: bool

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> TagCreateOptions:
        """Build a :class:`TagCreateOptions` from a parsed ``argparse.Namespace``.

        Every field here is given a real default by tag.py's own
        ``register()`` (used by ``rrt tag create``); hooks.py never dispatches
        to ``cmd_tag_create`` (only ``cmd_tag_check`` has a "tag-check" case),
        so there is no hooks.py Namespace gap to absorb. The getattr fallbacks
        remain because several tests in tests/commands/test_tag.py construct
        sparse ``argparse.Namespace`` objects by hand (via ``_args_create``)
        that omit some of these attributes.
        """
        return cls(
            verbose=getattr(args, "verbose", 0) or 0,
            dry_run=getattr(args, "dry_run", False),
            push=getattr(args, "push", False),
            prefix=getattr(args, "prefix", "v"),
            message=getattr(args, "message", None),
            group=getattr(args, "group", None),
            force=getattr(args, "force", False),
        )


def _cmd_tag_create_batch(opts: TagCreateOptions, root: Path, group_names: list[str]) -> int:
    """Create tags for every group in *group_names* in one invocation (issue #191).

    Validates every group name and checks every tag for a pre-existing
    conflict before creating any tag (fail-fast, no partial state) --
    mirrors ``_cmd_bump_batch``'s two-phase design.
    """
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
            p.line("No [tool.rrt] configuration found.", ok=False, stream=sys.stderr)
        else:
            p.line(err.text, ok=False, stream=sys.stderr)
        return 1

    existing = _existing_tags(root)

    # --- Phase 1: resolve and validate every group before tagging anything -----
    validated: list[tuple[VersionGroup, str, str]] = []
    for name in group_names:
        try:
            group = config.resolve_group(name)
        except ValueError as exc:
            VerbosePrinter(verbose=verbose).line(str(exc), ok=False, stream=sys.stderr)
            return 1
        version = str(read_group_current_version(group))
        tag = _tag_name_for_group(version, opts.prefix, group.name)
        if tag in existing and not opts.force:
            VerbosePrinter(verbose=verbose).line(
                f"Tag '{tag}' already exists (group {group.name!r}). Use --force to overwrite.",
                ok=False,
                stream=sys.stderr,
            )
            return 1
        validated.append((group, version, tag))

    # --- Phase 2: create every tag -----------------------------------------------
    p = DryRunPrinter(opts.dry_run, verbose=verbose)
    p.blank_line()
    p.header("Tag create", Groups=str(len(validated)))

    for group, _version, tag in validated:
        msg = opts.message or f"Release {tag}"
        p.section(group.name)
        p.meta("Tag", tag)
        p.meta("Message", msg)

        if opts.dry_run:
            p.line(f"would run: git tag -a {tag} -m {msg!r}")
            continue

        try:
            if tag in existing and opts.force:
                _git(["git", "tag", "-d", tag], root)
            _git(["git", "tag", "-a", tag, "-m", msg], root)
        except subprocess.CalledProcessError as exc:
            VerbosePrinter(verbose=verbose).line(
                f"git tag failed: {exc.stderr.strip()}", ok=False, stream=sys.stderr
            )
            return 1
        p.ok(f"Created tag {tag!r}")

        if opts.push:
            try:
                _git(["git", "push", "origin", tag], root)
                p.ok(f"Pushed {tag!r} to origin")
            except subprocess.CalledProcessError as exc:
                VerbosePrinter(verbose=verbose).line(
                    f"git push failed: {exc.stderr.strip()}", ok=False, stream=sys.stderr
                )
                return 1

    if opts.dry_run:
        p.line("no changes were made")

    return 0


def cmd_tag_create(args: argparse.Namespace) -> int:
    """Create an annotated git tag matching the current configured version."""
    opts = TagCreateOptions.from_args(args)
    verbose = opts.verbose
    root = find_repo_root(Path.cwd())

    if opts.group is not None and "," in opts.group:
        group_names = parse_group_names(opts.group)
        if not group_names:
            VerbosePrinter(verbose=verbose).line(
                f"--group has no valid group names: {opts.group!r}", ok=False, stream=sys.stderr
            )
            return 1
        if dupes := find_duplicate_group_names(group_names):
            VerbosePrinter(verbose=verbose).line(
                "Duplicate group name(s) in --group: "
                f"{', '.join(repr(d) for d in dupes)}. Each group may be listed only once.",
                ok=False,
                stream=sys.stderr,
            )
            return 1
        if "{group}" not in opts.prefix:
            VerbosePrinter(verbose=verbose).line(
                "--prefix must include the '{group}' placeholder when --group lists "
                f"multiple groups (got --prefix {opts.prefix!r}). Example: --prefix '{{group}}-v'.",
                ok=False,
                stream=sys.stderr,
            )
            return 1
        return _cmd_tag_create_batch(opts, root, group_names)

    result = _load_config_and_version(root, opts.group)
    if result is None:
        return 1
    _config, version = result

    tag = _tag_name(version, opts.prefix)
    msg = opts.message or f"Release {tag}"

    p = DryRunPrinter(opts.dry_run, verbose=verbose)
    p.blank_line()
    p.header("Tag create", Tag=tag, Message=msg)

    existing = _existing_tags(root)
    if tag in existing and not opts.force:
        p2 = VerbosePrinter(verbose=verbose)
        p2.line(
            f"Tag '{tag}' already exists. Use --force to overwrite.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    if opts.dry_run:
        p.line(f"would run: git tag -a {tag} -m {msg!r}")
        p.line("no changes were made")
        return 0

    try:
        if tag in existing and opts.force:
            _git(["git", "tag", "-d", tag], root)
        _git(["git", "tag", "-a", tag, "-m", msg], root)
    except subprocess.CalledProcessError as exc:
        p2 = VerbosePrinter(verbose=verbose)
        p2.line(f"git tag failed: {exc.stderr.strip()}", ok=False, stream=sys.stderr)
        return 1

    p.ok(f"Created tag {tag!r}")

    if opts.push:
        try:
            _git(["git", "push", "origin", tag], root)
            p.ok(f"Pushed {tag!r} to origin")
        except subprocess.CalledProcessError as exc:
            p2 = VerbosePrinter(verbose=verbose)
            p2.line(f"git push failed: {exc.stderr.strip()}", ok=False, stream=sys.stderr)
            return 1

    return 0


@dataclass(frozen=True)
class TagCheckOptions:
    """Typed view of ``argparse.Namespace`` for ``rrt tag check``.

    Built once via :meth:`from_args` at the top of :func:`cmd_tag_check` so
    every flag it reads has a typed read site instead of scattered
    ``getattr(args, ..., default)`` calls throughout the function body.
    """

    verbose: int
    strict: bool
    prefix: str
    group: str | None

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> TagCheckOptions:
        """Build a :class:`TagCheckOptions` from a parsed ``argparse.Namespace``.

        workflow/hooks.py's "tag-check" case hand-builds
        ``argparse.Namespace(strict=False, prefix="v", group=None,
        verbose=verbose)`` — exactly these four fields, so no field is
        missing from that dispatch arm. The getattr fallbacks remain because
        several tests in tests/commands/test_tag.py construct sparse
        ``argparse.Namespace`` objects by hand (via ``_args_check``) that
        never set ``verbose``.
        """
        return cls(
            verbose=getattr(args, "verbose", 0) or 0,
            strict=getattr(args, "strict", False),
            prefix=getattr(args, "prefix", "v"),
            group=getattr(args, "group", None),
        )


def _cmd_tag_check_batch(opts: TagCheckOptions, root: Path, group_names: list[str]) -> int:
    """Check tags for every group in *group_names*, aggregating results (issue #191).

    Read-only, so unlike the bump/tag-create batches this evaluates every
    group even after one fails -- there is no "apply" step to protect, and a
    user wants to see every group's mismatches in one pass, not stop at the
    first. Each group is checked with the exact single-group logic
    ``cmd_tag_check`` already uses, just with ``{group}`` rendered to that
    group's name in the expected prefix.
    """
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
            p.line("No [tool.rrt] configuration found.", ok=False, stream=sys.stderr)
        else:
            p.line(err.text, ok=False, stream=sys.stderr)
        return 1

    resolved: list[tuple[VersionGroup, str]] = []
    for name in group_names:
        try:
            group = config.resolve_group(name)
        except ValueError as exc:
            VerbosePrinter(verbose=verbose).line(str(exc), ok=False, stream=sys.stderr)
            return 1
        resolved.append((group, str(read_group_current_version(group))))

    existing_tags = _existing_tags(root)
    p = VerbosePrinter(verbose=verbose)
    p.blank_line()
    p.header("Tag check", Groups=str(len(resolved)), Total=str(len(existing_tags)))

    any_errors = False
    for group, version in resolved:
        group_prefix = opts.prefix.replace("{group}", group.name)
        expected_tag = f"{group_prefix}{version}"
        p.section(group.name)

        errors: list[str] = []
        for tag in existing_tags:
            if not tag.startswith(group_prefix):
                errors.append(f"Tag '{tag}' does not match prefix '{group_prefix}'")

        if expected_tag not in existing_tags:
            if opts.strict:
                errors.append(f"Expected tag '{expected_tag}' not found (run `rrt tag create`)")
            else:
                p.line(
                    f"  Expected tag '{expected_tag}' not found (run `rrt tag create`)", ok=False
                )

        if errors:
            any_errors = True
            for err in errors:
                p.line(f"  {err}", ok=False)
        else:
            p.ok(f"Tag '{expected_tag}' is present and consistent.")

    return 1 if any_errors else 0


def cmd_tag_check(args: argparse.Namespace) -> int:
    """Validate existing tags match the configured naming convention."""
    opts = TagCheckOptions.from_args(args)
    verbose = opts.verbose
    root = find_repo_root(Path.cwd())

    if opts.group is not None and "," in opts.group:
        group_names = parse_group_names(opts.group)
        if not group_names:
            VerbosePrinter(verbose=verbose).line(
                f"--group has no valid group names: {opts.group!r}", ok=False, stream=sys.stderr
            )
            return 1
        if dupes := find_duplicate_group_names(group_names):
            VerbosePrinter(verbose=verbose).line(
                "Duplicate group name(s) in --group: "
                f"{', '.join(repr(d) for d in dupes)}. Each group may be listed only once.",
                ok=False,
                stream=sys.stderr,
            )
            return 1
        if "{group}" not in opts.prefix:
            VerbosePrinter(verbose=verbose).line(
                "--prefix must include the '{group}' placeholder when --group lists "
                f"multiple groups (got --prefix {opts.prefix!r}). Example: --prefix '{{group}}-v'.",
                ok=False,
                stream=sys.stderr,
            )
            return 1
        return _cmd_tag_check_batch(opts, root, group_names)

    result = _load_config_and_version(root, opts.group)
    if result is None:
        return 1
    _config, version = result

    expected_tag = _tag_name(version, opts.prefix)
    existing_tags = _existing_tags(root)

    p = VerbosePrinter(verbose=verbose)
    p.blank_line()
    p.header("Tag check", Expected=expected_tag, Total=str(len(existing_tags)))

    errors: list[str] = []

    for tag in existing_tags:
        if not tag.startswith(opts.prefix):
            errors.append(f"Tag '{tag}' does not match prefix '{opts.prefix}'")

    if expected_tag not in existing_tags:
        if opts.strict:
            errors.append(f"Expected tag '{expected_tag}' not found (run `rrt tag create`)")
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
    "  $ rrt tag create --group backend,sdk --prefix '{group}-v'\n"
    "  $ rrt tag check\n"
    "  $ rrt tag check --strict\n"
    "  $ rrt tag check --group backend,sdk --prefix '{group}-v'"
)


@register_command(name="tag", category=CommandCategory.READ, group=CommandGroup.VERSION_RELEASE)
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
        help=(
            "Tag prefix (default: 'v'). Pass empty string for no prefix. "
            "Include the '{group}' token to render each group's name when "
            "--group lists multiple groups (e.g. '{group}-v')."
        ),
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
        help=(
            "Version group to read when multiple groups are configured. "
            "Pass a comma-separated list (e.g. 'a,b,c') to tag several groups "
            "in one invocation; --prefix must then include the '{group}' token."
        ),
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
        help=(
            "Expected tag prefix (default: 'v'). Include the '{group}' token to "
            "render each group's name when --group lists multiple groups "
            "(e.g. '{group}-v')."
        ),
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
        help=(
            "Version group to read when multiple groups are configured. "
            "Pass a comma-separated list (e.g. 'a,b,c') to check several groups "
            "in one invocation; --prefix must then include the '{group}' token."
        ),
    )
    check_parser.set_defaults(handler=cmd_tag_check)
