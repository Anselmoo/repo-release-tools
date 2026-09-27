"""Bump a release version and prepare the associated release branch.

## Overview

This command reads the active ``[tool.rrt]`` configuration, computes a new
version, updates configured files, and creates the release branch named by the
selected version group.

The bump value may be one of:

* ``major``, ``minor``, or ``patch`` to increment the current version
* ``alpha``, ``beta``, or ``rc`` to start or advance a pre-release channel
* ``release`` to drop the pre-release suffix, or ``pre-release`` to advance it
* ``calver`` to move to today's calendar version
* an explicit version string such as ``2.1.0``

## Pre-release base

Starting ``alpha``, ``beta`` or ``rc`` from a final version targets the next
patch by default. So ``rrt bump rc`` turns ``1.0.0`` into ``1.0.1-rc.1``.

``--base LEVEL`` picks another core for one run. ``minor`` gives
``1.1.0-rc.1`` and ``major`` gives ``2.0.0-rc.1``. The flag overrides the
``prerelease_base`` key under ``[tool.rrt]`` or the version group.

``auto`` reads the Conventional Commits since the group's last final tag. A
breaking change means major, a ``feat`` means minor, anything else means patch.
Later pre-release tags never move that range. ``changelog_paths`` and
``extra_commit_types`` apply as they do for changelog generation.

The base is ignored once the version is already a pre-release. So ``1.0.1-rc.1``
bumps to ``1.0.1-rc.2``, whatever ``--base`` says.

## What the command updates

Depending on the selected version group, the command can update:

* version targets defined in ``[[tool.rrt.version_targets]]``
* dependency or documentation pins configured for the group
* the changelog file
* lockfiles, when the group defines a lock command

## Release workflow

1. Load the repository config from ``[tool.rrt]``.
2. Resolve the selected version group.
3. Compute the new version from the current group version or the explicit
   ``<bump>`` value.
4. Update version targets and optional pin targets.
5. Update the changelog unless ``--no-changelog`` is set.
6. Run the configured lock and generated-asset commands unless
   ``--no-update`` is set.
7. Create the release branch and stage or commit the resulting changes.

## Changelog behavior

The changelog update logic supports three modes:

* ``auto`` - promote ``[Unreleased]`` when it has entries, otherwise generate a
  new section from git history
* ``promote`` - require a non-empty ``[Unreleased]`` section and rename it to
  the new version heading
* ``generate`` - always generate a fresh section from the commit log

When an empty ``[Unreleased]`` placeholder exists, generated content is kept
below it so the placeholder stays at the top of the file.

## Safety notes

* The working tree must be clean unless ``--dry-run`` is used.
* Existing release branches are refused unless ``--force`` is set.
* ``--no-commit`` leaves the branch created with staged changes only.
* ``--dry-run`` previews the planned file edits and git actions without writing
  to disk.

## Examples

* ``rrt bump patch``
* ``rrt bump minor --dry-run``
* ``rrt bump 2.1.0 --no-changelog --no-commit``
* ``rrt bump major --base-branch develop``
* ``rrt bump rc --dry-run``
* ``rrt bump rc --base minor --dry-run``
* ``rrt bump beta --base auto``
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from repo_release_tools.changelog import (
    build_changelog_section,
    detect_changelog_format,
    get_unreleased_entries,
    has_unreleased_section,
    insert_generated_section,
    parse_conventional_commit,
    promote_unreleased,
)
from repo_release_tools.commands._cli_shared import add_dry_run_flag
from repo_release_tools.commands._common import (
    describe_config_load_error,
    find_duplicate_group_names,
    parse_group_names,
)
from repo_release_tools.commands._registry import CommandCategory, CommandGroup, register_command
from repo_release_tools.commands._version_render import render_version_write_events
from repo_release_tools.config import (
    DEFAULT_TAG_PREFIX,
    RrtConfig,
    VersionGroup,
    find_repo_root,
    format_autodetected_config_notice,
    iter_config_files,  # noqa: F401 -- re-exported for test monkeypatch compatibility
    load_or_autodetect_config,
)
from repo_release_tools.preflight import (
    PreflightError,
    check_config_consistent,
    check_version_targets_readable,
    run_preflight,
)
from repo_release_tools.ui import (
    GLYPHS,
    DryRunPrinter,
    VerbosePrinter,
    spinner_lines,
)
from repo_release_tools.version.calver import CALVER_SCHEMES, CalVersion
from repo_release_tools.version.semver import PRE_RELEASE_CHANNELS, PRERELEASE_BASES, Version
from repo_release_tools.version.targets import (
    check_autodetected_version_consistency,
    read_group_current_version,
    replace_all_versions_atomic,
    replace_pin_in_file,
)
from repo_release_tools.workflow import git

if TYPE_CHECKING:
    from collections.abc import Sequence

PREVIEW_LINES = 8

# Keyword bump kinds shared by ``rrt bump`` and ``rrt workspace bump``.
BUMP_KINDS = {"major", "minor", "patch", "release", "pre-release", "calver", *PRE_RELEASE_CHANNELS}

# Pre-commit's fixed status line for a hook that auto-regenerated files and
# thereby failed its own pass even though the fix is now correct on disk.
_HOOK_MODIFIED_FILES_MARKER = "files were modified by this hook"

# Upper bound on commit attempts in finalize_bump_git's auto-fix retry loop.
# More than one auto-fixing hook (ruff, tree/doctor/config-reference
# auto-update, ...) can cascade across successive commit attempts, so a
# single retry isn't always enough; this caps the loop rather than retrying
# forever.
_MAX_COMMIT_ATTEMPTS = 3


class BumpResolutionError(Exception):
    """Raised by :func:`resolve_bump_target` when the bump kind or version group is invalid.

    ``str(exc)`` is the exact text ``cmd_bump`` already prints to stderr; this
    only relocates the *computation*, not the *wording*, of these checks.
    """


@dataclass(frozen=True)
class BumpTarget:
    """A resolved version group and the version to bump it to."""

    group: VersionGroup
    current: Version | CalVersion
    new: Version | CalVersion | str


def resolve_bump_target(config: RrtConfig, opts: Options) -> BumpTarget:
    """Resolve the release group and compute the new version.

    No printing and no filesystem writes. This step happens entirely before
    ``cmd_bump`` prints its "Version bump" header, so extracting it cannot
    reorder any observable output (unlike preflight/branch-existence, which
    interleave with that header print and stay inline in ``cmd_bump`` for that
    reason).

    Starting ``alpha``, ``beta`` or ``rc`` from a FINAL version uses the
    pre-release base from :func:`resolve_prerelease_base`. That is the only
    case that reads git: a base of ``auto`` scans the Conventional Commits
    since the group's last FINAL tag. Every other kind stays git-free.
    """
    try:
        group = config.resolve_group(opts.group)
    except ValueError as exc:
        raise BumpResolutionError(str(exc)) from exc

    current = read_group_current_version(group)
    new: Version | CalVersion | str
    if opts.bump == "calver":
        calver_scheme = opts.calver_scheme
        try:
            current_calver = CalVersion.parse(str(current))
        except ValueError:
            current_calver = CalVersion.today(calver_scheme)
            new = str(current_calver)
        else:
            new = str(current_calver.bump())
    elif opts.bump in BUMP_KINDS:
        base = resolve_prerelease_base(config, group, opts.bump, current, opts.prerelease_base)
        try:
            if base is None:
                new = current.bump(opts.bump)  # type: ignore[assignment]
            else:
                new = current.bump(opts.bump, base=base)  # type: ignore[call-arg]
        except ValueError as exc:
            raise BumpResolutionError(str(exc)) from exc
    else:
        try:
            new = Version.parse(opts.bump)
        except ValueError:
            try:
                new = CalVersion.parse(opts.bump)
            except ValueError:
                raise BumpResolutionError(f"Invalid bump value: {opts.bump!r}") from None

    return BumpTarget(group=group, current=current, new=new)


def infer_prerelease_base(
    root: Path,
    tag_prefix: str = DEFAULT_TAG_PREFIX,
    paths: Sequence[str] = (),
    extra_types: Sequence[str] = (),
) -> str:
    """Return the core level implied by Conventional Commits since the last FINAL tag.

    This is how a pre-release base of ``auto`` resolves (decision D-1). The
    range starts at :func:`git.latest_final_tag` for *tag_prefix*, so commits
    before that release and later pre-release tags (``v1.0.1-rc.1``) never
    move it.  Without a final tag the range is all of ``HEAD``.

    Returns ``"major"`` when any commit is breaking (``type!:`` or a
    ``BREAKING CHANGE:`` / ``BREAKING-CHANGE:`` footer), else ``"minor"`` when
    any commit is a ``feat``, else ``"patch"``.  *paths* restricts the log to
    the group's ``changelog_paths``; *extra_types* are the project's
    ``extra_commit_types``.
    """
    latest = git.latest_final_tag(root, tag_prefix)
    ref = f"{latest}..HEAD" if latest else "HEAD"
    cmd = ["git", "log", ref, "--pretty=format:%B%x1e"]
    if paths:
        cmd += ["--", *paths]
    out = git.capture(cmd, root)

    level = "patch"
    for message in out.split("\x1e"):
        lines = message.strip().splitlines()
        if not lines:
            continue
        if any(line.startswith(("BREAKING CHANGE:", "BREAKING-CHANGE:")) for line in lines):
            return "major"
        parsed = parse_conventional_commit(lines[0], tuple(extra_types))
        if parsed is None:
            continue
        if parsed.breaking:
            return "major"
        if parsed.type == "feat":
            level = "minor"
    return level


def resolve_prerelease_base(
    config: RrtConfig,
    group: VersionGroup,
    kind: str,
    current: Version | CalVersion,
    override: str | None = None,
) -> str | None:
    """Return the concrete pre-release base for *kind*, or ``None`` when none applies.

    A base only matters when *kind* starts ``alpha``, ``beta`` or ``rc`` from a
    FINAL SemVer *current*; every other case returns ``None`` without touching
    git.  *override* (the CLI ``--base`` or MCP ``base``) wins over the group's
    ``prerelease_base``.  ``auto`` resolves through :func:`infer_prerelease_base`
    against *config*'s root, the rendered group ``tag_prefix``, the group's
    ``changelog_paths`` and the project's ``extra_commit_types``.
    """
    if (
        kind not in PRE_RELEASE_CHANNELS
        or not isinstance(current, Version)
        or current.is_pre_release()
    ):
        return None
    base = override or group.prerelease_base
    if base == "auto":
        tag_prefix = group.tag_prefix.replace("{group}", group.name)
        return infer_prerelease_base(
            config.root, tag_prefix, group.changelog_paths, config.extra_commit_types
        )
    return base


def apply_bump_files(
    group: VersionGroup,
    new: Version | CalVersion | str,
    config: RrtConfig,
    *,
    dry_run: bool = False,
) -> list[Path]:
    """Write the new version to every target/pin file for *group*.

    Thin, named wrapper over :func:`apply_version` -- kept as a distinct
    function so the ``resolve -> apply -> assets -> git-finalize`` stages of
    :func:`cmd_bump` each have a directly testable, directly named
    counterpart.
    """
    return apply_version(group, str(new), config, dry_run=dry_run)


def refresh_bump_lockfile(
    group: VersionGroup, root: Path, *, dry_run: bool, verbose: int = 0
) -> None:
    """Run *group*'s lock command, if configured.

    Callers guard this with ``group.lock_command and not opts.no_update``
    before calling (matches cmd_bump's original inline guard) -- this
    function does not check that itself. Prints its own progress, matching
    this file's established convention (see :func:`update_changelog`) of
    helper functions owning their own output rather than threading a printer
    in from the caller.
    """
    p = DryRunPrinter(dry_run, verbose=verbose)
    p.section("Refreshing lockfiles")
    spinner = (
        contextlib.nullcontext()
        if dry_run
        else spinner_lines(
            "Running lock command…",
            detail=f"$ {' '.join(group.lock_command)}",
            file=sys.stdout,
        )
    )
    with spinner:
        git.run(
            group.lock_command,
            root,
            dry_run=dry_run,
            label="lock command",
            suppress_announce=True,
        )


def refresh_bump_generated_assets(
    group: VersionGroup, root: Path, *, dry_run: bool, verbose: int = 0
) -> bool:
    """Run each of *group*'s generated-asset refresh commands.

    Callers guard this with ``group.generated_assets and not opts.no_update``
    before calling. Returns ``False`` when a *real* (non-dry-run) command
    failure or missing-output-file occurs -- callers should exit 1 in that
    case. In dry-run mode the same conditions only warn and continue,
    matching cmd_bump's original inline behavior exactly.
    """
    p = DryRunPrinter(dry_run, verbose=verbose)
    p.section("Refreshing generated assets")
    for asset in group.generated_assets:
        command_preview = " ".join(asset.command)
        spinner = (
            contextlib.nullcontext()
            if dry_run
            else spinner_lines(
                "Running generated asset command…",
                detail=f"$ {command_preview}",
                file=sys.stdout,
            )
        )
        try:
            with spinner:
                git.run(
                    asset.command,
                    root,
                    dry_run=dry_run,
                    label=f"generated asset command ({asset.path.relative_to(root)})",
                    suppress_announce=True,
                )
        except RuntimeError as exc:
            if dry_run:
                p.warn(
                    f"Generated asset command for {asset.path.relative_to(root)} failed in dry-run: {exc}",
                )
                continue
            p.line(str(exc), ok=False, stream=sys.stderr)
            return False

        if not asset.path.exists():
            message = (
                f"Generated asset {asset.path.relative_to(root)} not found after refresh command"
            )
            if dry_run:
                p.warn(message)
            else:
                p.line(message, ok=False, stream=sys.stderr)
                return False
    return True


def finalize_bump_git(
    group: VersionGroup,
    new: Version | CalVersion | str,
    changed_paths: list[Path],
    root: Path,
    *,
    branch_name: str,
    base: str,
    force: bool,
    opts: Options,
) -> None:
    """Checkout the release branch, stage changed files, and commit.

    Ordering is contract: checkout -> stage -> commit. Retries the commit,
    up to ``_MAX_COMMIT_ATTEMPTS`` times, whenever a pre-commit hook
    auto-regenerated files during the previous attempt -- more than one
    auto-fixing hook can trip across successive attempts, so a single retry
    isn't always enough.
    """
    p = DryRunPrinter(opts.dry_run, verbose=opts.verbose)
    p.section("Git")
    create_flag = "-B" if force else "-b"
    git.run(
        ["git", "checkout", create_flag, branch_name],
        root,
        dry_run=opts.dry_run,
        label=f"git checkout {create_flag}",
    )

    # changed_paths contains version-target paths followed by pin paths (already deduplicated).
    files_to_stage = [str(path.relative_to(root)) for path in changed_paths]
    for path in group.generated_files:
        if path.exists():
            files_to_stage.append(str(path.relative_to(root)))
    for asset in group.generated_assets:
        if asset.path.exists():
            files_to_stage.append(str(asset.path.relative_to(root)))
    if group.changelog_file.exists() and not opts.no_changelog:
        files_to_stage.append(str(group.changelog_file.relative_to(root)))
    git.run(
        ["git", "add", *dict.fromkeys(files_to_stage)],
        root,
        dry_run=opts.dry_run,
        label="git add",
    )

    if not opts.no_commit:
        git.run(["git", "add", "-u"], root, dry_run=opts.dry_run, label="git add -u")
        commit_msg = f"chore: bump version to v{new}"
        commit_cmd = ["git", "commit", "-m", commit_msg]
        if opts.no_verify:
            commit_cmd.append("--no-verify")
        prev_exc: RuntimeError | None = None
        for attempt in range(1, _MAX_COMMIT_ATTEMPTS + 1):
            try:
                git.run(commit_cmd, root, dry_run=opts.dry_run, label="git commit")
                break
            except RuntimeError as exc:
                has_marker = _HOOK_MODIFIED_FILES_MARKER in str(exc)
                if not has_marker or attempt == _MAX_COMMIT_ATTEMPTS:
                    if prev_exc is not None:
                        raise exc from prev_exc
                    raise
                # A pre-commit hook (e.g. rrt-cli-docs) may have auto-regenerated
                # files during this pass — pre-commit always fails that pass even
                # though the fix is now correct. Re-stage and retry.
                git.run(["git", "add", "-u"], root, dry_run=opts.dry_run, label="git add -u")
                prev_exc = exc
        done_msg = f"Done. Branch '{branch_name}' created with commit: {commit_msg!r}"
        p.footer(done_msg)
    else:
        done_msg = f"Done. Branch '{branch_name}' created and files staged."
        p.meta("Base branch", base)
        p.footer(done_msg)
    if opts.dry_run:
        # Provide an explicit dry-run completion line expected by some tests
        p.line("no files were modified")


def apply_version(
    group: VersionGroup,
    version: str,
    config: RrtConfig,
    *,
    dry_run: bool = False,
) -> list[Path]:
    """Apply *version* to a group's version targets and pin targets.

    This is the shared write-only core used by ``cmd_bump`` and the upcoming
    ``rrt sync --bump``.  It intentionally has no git, branch, or changelog
    side-effects — those remain the responsibility of the caller.

    Steps performed:

    1. Atomically rewrite every ``group.version_targets`` entry.
    2. Apply ``group.pin_targets + config.global_pin_targets``, deduplicating
       by ``(path, pattern)`` and honouring ``config.pin_target_missing``.

    Returns a deduplicated list of :class:`~pathlib.Path` objects for every
    file that was (or, in dry-run, would be) modified.  Callers use this list
    to stage the changes with ``git add``.
    """
    events = replace_all_versions_atomic(group.version_targets, version, dry_run=dry_run)
    render_version_write_events(events)
    changed: list[Path] = [target.path for target in group.version_targets]

    all_pins = group.pin_targets + config.global_pin_targets
    seen_pin_keys: set[tuple[object, str]] = set()
    for pin in all_pins:
        key = (pin.path, pin.pattern)
        if key in seen_pin_keys:
            continue
        seen_pin_keys.add(key)
        replace_pin_in_file(
            pin, version, dry_run=dry_run, pin_target_missing=config.pin_target_missing
        )
        changed.append(pin.path)

    return changed


def resolve_changelog_mode(group: VersionGroup, requested_mode: str | None) -> str:
    """Resolve the changelog update mode from CLI input and workflow defaults."""
    if requested_mode is not None:
        return requested_mode
    return "generate" if group.changelog_workflow == "squash" else "auto"


def git_log_since_latest_tag(
    root: Path,
    tag_prefix: str = DEFAULT_TAG_PREFIX,
    paths: Sequence[str] = (),
) -> list[str]:
    """Collect commit subjects since the latest tag carrying *tag_prefix*.

    Filtering by prefix is what keeps a group's range anchored to its own
    release history: a repository holding both ``v*`` and ``sdk-v*`` tags would
    otherwise start every group's range at whichever tag sorts first overall
    (issue #251).  The anchor comes from :func:`git.latest_tag`, which matches
    the prefix with ``startswith`` (like ``rrt tag check``), never a git glob.

    Tags are ranked by version precedence, not by name: a final release
    outranks its own pre-releases (``v1.0.0`` beats ``v1.0.0-rc.2``), and
    tags whose remainder is not a version (``vnext``) are ignored.  CalVer
    tags rank by date.  Without a matching tag the range is all of ``HEAD``.

    *paths* restricts the log to the group's own files when the group
    configures ``changelog_paths``.
    """
    latest = git.latest_tag(root, tag_prefix)
    ref = f"{latest}..HEAD" if latest else "HEAD"
    cmd = ["git", "log", ref, "--pretty=format:%s"]
    if paths:
        cmd += ["--", *paths]
    out = git.capture(cmd, root)
    return [line.strip() for line in out.splitlines() if line.strip()]


def update_changelog(
    config: RrtConfig,
    version: str,
    *,
    include_maintenance: bool,
    dry_run: bool,
    changelog_mode: str = "auto",
) -> None:
    """Update the changelog for a new version.

    Three modes are supported via *changelog_mode*:

    ``auto`` (default)
        Promotes the ``[Unreleased]`` section when it contains entries;
        otherwise generates a new section from the git log.
    ``promote``
        Requires a non-empty ``[Unreleased]`` section and renames it to the
        versioned heading.  Prints a warning and returns early when no entries
        are found.
    ``generate``
        Always generates a new section from the git log, ignoring any
        ``[Unreleased]`` section.

    Generated sections read the commit range from the resolved group's own
    latest tag (its configured ``tag_prefix``, with a ``{group}`` token rendered
    to the group name) and, when the group configures ``changelog_paths``, only
    from commits touching those paths.

    When the changelog contains an empty ``[Unreleased]`` placeholder (e.g.
    after a previous release), the generated section is inserted *after* that
    placeholder so it stays at the top.  When no ``[Unreleased]`` section is
    present at all, a fresh empty placeholder is prepended (health-mode).

    The changelog format (Markdown vs. RST/plain-text underline notation) is
    inferred automatically from the file extension.
    """
    path = config.changelog_file
    if not path.exists():
        p = VerbosePrinter()
        p.line(f"{path} not found {GLYPHS.typography.mdash} skipping", ok=False)
        return

    existing = path.read_text(encoding="utf-8")
    fmt = detect_changelog_format(path.name)
    has_entries = bool(get_unreleased_entries(existing, fmt))

    # ---- Decide mode -------------------------------------------------------
    if changelog_mode == "generate":
        do_promote = False
    elif changelog_mode == "promote":
        if not has_entries:
            p = VerbosePrinter()
            if has_unreleased_section(existing, fmt):
                p.line(
                    f"[Unreleased] section in {path} is empty {GLYPHS.typography.mdash} nothing to promote.",
                    ok=False,
                )
            else:
                p.line(
                    f"No [Unreleased] section found in {path} {GLYPHS.typography.mdash} nothing to promote.",
                    ok=False,
                )
            return
        do_promote = True
    else:  # "auto"
        do_promote = has_entries

    # ---- Promote [Unreleased] → versioned section --------------------------
    if do_promote:
        section_text = promote_unreleased(existing, version, fmt)
        if dry_run:
            p = DryRunPrinter(True)
            p.would_write(str(path), f"promote [Unreleased] → [{version}]")
            for line in section_text.splitlines()[:PREVIEW_LINES]:
                p.line(f"    > {line}")
            if len(section_text.splitlines()) > PREVIEW_LINES:
                p.list_item(f"> {GLYPHS.typography.ellipsis}")
            return
        path.write_text(section_text, encoding="utf-8")
        p = VerbosePrinter()
        p.ok(f"{path} updated (promoted [Unreleased] to [{version}])")
        return

    # ---- Generate section from git log (heading / hash notation) -----------
    group = config.resolve_group()
    tag_prefix = group.tag_prefix.replace("{group}", group.name)
    section = build_changelog_section(
        version,
        git_log_since_latest_tag(config.root, tag_prefix, group.changelog_paths),
        include_maintenance=include_maintenance,
        fmt=fmt,
    )
    # insert_generated_section handles both an empty [Unreleased] placeholder
    # (inserts after it) and a missing [Unreleased] section (health-mode prepend).
    section_text = insert_generated_section(existing, section, fmt)

    if dry_run:
        p = DryRunPrinter(True)
        p.would_write(str(path), "prepend generated entries")
        for line in section_text.splitlines()[:PREVIEW_LINES]:
            p.line(f"    > {line}")
        if len(section_text.splitlines()) > PREVIEW_LINES:
            p.list_item(f"> {GLYPHS.typography.ellipsis}")
        return

    path.write_text(section_text, encoding="utf-8")
    p = VerbosePrinter()
    p.ok(f"{path} updated")


@dataclass(frozen=True)
class Options:
    """Typed view of ``argparse.Namespace`` for ``rrt bump``.

    Built once via :meth:`from_args` at the top of :func:`cmd_bump` so every
    flag has a single, typed read site instead of scattered
    ``getattr(args, ..., default)`` calls throughout the function body.
    """

    bump: str
    group: str | None
    dry_run: bool
    force: bool
    no_commit: bool
    no_verify: bool
    no_changelog: bool
    no_pin_sync: bool
    no_update: bool
    include_maintenance: bool
    changelog_mode: str | None
    base_branch: str | None
    calver_scheme: str
    verbose: int
    prerelease_base: str | None = None

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> Options:
        """Build an :class:`Options` from a parsed ``argparse.Namespace``."""
        # NOTE: every flag below is given a real default by bump.py's own
        # register() (or, for --verbose, by cli.py's global parser), so a
        # Namespace produced by argparse always carries every attribute.
        # The getattr fallbacks here exist only because some unit tests in
        # tests/commands/test_bump.py construct sparse argparse.Namespace
        # objects by hand (e.g. Namespace(bump="minor", dry_run=False, ...))
        # instead of going through register(); this is the single
        # translation point that absorbs that, so the rest of cmd_bump can
        # read opts.x unconditionally.
        return cls(
            bump=getattr(args, "bump", ""),
            group=getattr(args, "group", None),
            dry_run=getattr(args, "dry_run", False),
            force=getattr(args, "force", False),
            no_commit=getattr(args, "no_commit", False),
            no_verify=getattr(args, "no_verify", False),
            no_changelog=getattr(args, "no_changelog", False),
            no_pin_sync=getattr(args, "no_pin_sync", False),
            no_update=getattr(args, "no_update", False),
            include_maintenance=getattr(args, "include_maintenance", False),
            changelog_mode=getattr(args, "changelog_mode", None),
            base_branch=getattr(args, "base_branch", None),
            calver_scheme=getattr(args, "calver_scheme", "YYYY.MM.DD"),
            verbose=getattr(args, "verbose", 0) or 0,
            prerelease_base=getattr(args, "prerelease_base", None),
        )


def _cmd_bump_batch(
    opts: Options,
    config: RrtConfig,
    root: Path,
    group_names: list[str],
) -> int:
    """Bump every group in *group_names* in one invocation (issue #191).

    Reuses every per-group helper ``cmd_bump`` already has --
    :func:`resolve_bump_target`, :func:`run_preflight`, :func:`apply_bump_files`,
    :func:`resolve_changelog_mode`, :func:`update_changelog`,
    :func:`refresh_bump_lockfile`, :func:`refresh_bump_generated_assets`, and
    :func:`finalize_bump_git` -- unchanged. Each group gets its own release
    branch and commit, identical to running ``rrt bump`` once per group by
    hand. Every group is resolved and validated before anything is written
    (fail-fast, no partial state); any failure -- in validation or during
    apply -- stops the whole batch immediately.
    """
    verbose = opts.verbose

    if opts.no_commit:
        VerbosePrinter(verbose=verbose).line(
            "--no-commit is not supported with a multi-group --group batch (each "
            "group's checkout would carry the previous group's uncommitted changes "
            "onto the next branch); commit each group or bump one at a time.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    # --- Phase 1: resolve and validate every group before writing anything -----
    validated: list[tuple[BumpTarget, str]] = []
    for name in group_names:
        sub_opts = dataclasses.replace(opts, group=name)
        try:
            target = resolve_bump_target(config, sub_opts)
        except BumpResolutionError as exc:
            VerbosePrinter(verbose=verbose).line(str(exc), ok=False, stream=sys.stderr)
            return 1

        branch_name = target.group.release_branch.format(version=target.new)
        if not opts.dry_run:
            try:
                check_config_consistent(config)
                check_version_targets_readable(target.group)
            except PreflightError as exc:
                VerbosePrinter(verbose=verbose).line(str(exc), ok=False, stream=sys.stderr)
                return 1
            if git.branch_exists(root, branch_name) and not opts.force:
                VerbosePrinter(verbose=verbose).line(
                    f"Branch '{branch_name}' already exists. Delete it first or "
                    "choose a different version.",
                    ok=False,
                    stream=sys.stderr,
                )
                return 1

        validated.append((target, branch_name))

    # --- Phase 2: apply every group ---------------------------------------------
    pr = DryRunPrinter(opts.dry_run, verbose=verbose)
    pr.blank_line()
    pr.header("Version bump", Groups=str(len(validated)), Bump=opts.bump)

    for target, branch_name in validated:
        group, current, new = target.group, target.current, target.new
        current_branch = "<current>" if opts.dry_run else git.current_branch(root)
        base = opts.base_branch or current_branch

        pr.section(f"{group.name}: {current} {GLYPHS.arrow.right} {new}")
        pr.meta("Branch", branch_name)
        pr.meta("Base", base)

        try:
            run_preflight(config, dry_run=opts.dry_run, group=group)
        except PreflightError as exc:
            VerbosePrinter(verbose=verbose).line(str(exc), ok=False, stream=sys.stderr)
            return 1

        if not opts.dry_run:
            branch_exists = git.branch_exists(root, branch_name)
            if current_branch != base:
                git.run(["git", "checkout", base], root, dry_run=False, label="git checkout base")
            if branch_exists:
                VerbosePrinter(verbose=verbose).line(
                    f"Branch '{branch_name}' already exists. Resetting it with --force."
                )

        pr.section("Updating version strings")

        all_pins = group.pin_targets + config.global_pin_targets
        no_pin_sync = opts.no_pin_sync
        if all_pins and not no_pin_sync:
            pr.section("Updating doc pins")

        apply_group = dataclasses.replace(group, pin_targets=[]) if no_pin_sync else group
        apply_config = dataclasses.replace(config, global_pin_targets=[]) if no_pin_sync else config
        changed_paths = apply_bump_files(apply_group, new, apply_config, dry_run=opts.dry_run)

        if not opts.no_changelog:
            effective_changelog_mode = resolve_changelog_mode(group, opts.changelog_mode)
            update_changelog(
                RrtConfig(
                    root=config.root,
                    config_file=config.config_file,
                    version_groups=[group],
                    default_group_name=group.name,
                ),
                str(new),
                include_maintenance=opts.include_maintenance,
                dry_run=opts.dry_run,
                changelog_mode=effective_changelog_mode,
            )

        if group.lock_command and not opts.no_update:
            refresh_bump_lockfile(group, root, dry_run=opts.dry_run, verbose=verbose)

        if group.generated_assets and not opts.no_update:
            if not refresh_bump_generated_assets(
                group, root, dry_run=opts.dry_run, verbose=verbose
            ):
                return 1

        finalize_bump_git(
            group,
            new,
            changed_paths,
            root,
            branch_name=branch_name,
            base=base,
            force=opts.force,
            opts=opts,
        )

    return 0


def cmd_bump(args: argparse.Namespace) -> int:
    """Bump project version using [tool.rrt]."""
    opts = Options.from_args(args)
    verbose: int = opts.verbose
    root = find_repo_root(Path.cwd())
    force = opts.force
    try:
        config = load_or_autodetect_config(root)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        err = describe_config_load_error(exc, root)
        p = VerbosePrinter(verbose=verbose)
        if err.kind == "no_config_file":
            p.line("No supported rrt config file found.", ok=False, stream=sys.stderr)
            p.line(err.text, ok=False, stream=sys.stderr)
        elif err.kind == "missing_tool_rrt":
            p.line("No [tool.rrt] configuration found.", ok=False, stream=sys.stderr)
            p.line(err.text, ok=False, stream=sys.stderr)
        else:
            p.line(err.text, ok=False, stream=sys.stderr)
        return 1

    if config.autodetected:
        p = VerbosePrinter(verbose=verbose)
        p.line(format_autodetected_config_notice(config), ok=False, stream=sys.stderr)
        if mismatch := check_autodetected_version_consistency(config):
            p.line(mismatch, ok=False, stream=sys.stderr)
            return 1

    if opts.group is not None and "," in opts.group:
        group_names = parse_group_names(opts.group)
        if not group_names:
            p = VerbosePrinter(verbose=verbose)
            p.line(f"--group has no valid group names: {opts.group!r}", ok=False, stream=sys.stderr)
            return 1
        if dupes := find_duplicate_group_names(group_names):
            p = VerbosePrinter(verbose=verbose)
            p.line(
                "Duplicate group name(s) in --group: "
                f"{', '.join(repr(d) for d in dupes)}. Each group may be listed only once.",
                ok=False,
                stream=sys.stderr,
            )
            return 1
        return _cmd_bump_batch(opts, config, root, group_names)

    try:
        target = resolve_bump_target(config, opts)
    except BumpResolutionError as exc:
        p = VerbosePrinter(verbose=verbose)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1
    group, current, new = target.group, target.current, target.new

    branch_name = group.release_branch.format(version=new)
    current_branch = "<current>" if opts.dry_run else git.current_branch(root)
    base = opts.base_branch or current_branch

    p = DryRunPrinter(opts.dry_run, verbose=verbose)
    p.blank_line()
    p.header(
        "Version bump",
        Current=f"{current} {GLYPHS.arrow.right} {new}",
        Branch=branch_name,
        Base=base,
    )

    branch_exists = False
    try:
        run_preflight(config, dry_run=opts.dry_run, group=group)
    except PreflightError as exc:
        p = VerbosePrinter(verbose=verbose)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1

    if not opts.dry_run:
        branch_exists = git.branch_exists(root, branch_name)
        if branch_exists and not force:
            p = VerbosePrinter(verbose=verbose)
            p.line(
                f"Branch '{branch_name}' already exists. Delete it first or choose a different version.",
                ok=False,
                stream=sys.stderr,
            )
            return 1
        if current_branch != base:
            git.run(["git", "checkout", base], root, dry_run=False, label="git checkout base")
        if branch_exists:
            msg = f"Branch '{branch_name}' already exists. Resetting it with --force."
            p = VerbosePrinter(verbose=verbose)
            p.line(msg)

    p.section("Updating version strings")

    all_pins = group.pin_targets + config.global_pin_targets
    no_pin_sync = opts.no_pin_sync
    if all_pins and not no_pin_sync:
        p.section("Updating doc pins")

    # Build a pin-free view when no_pin_sync is set so apply_version skips pins.
    apply_group = dataclasses.replace(group, pin_targets=[]) if no_pin_sync else group
    apply_config = dataclasses.replace(config, global_pin_targets=[]) if no_pin_sync else config
    changed_paths = apply_bump_files(apply_group, new, apply_config, dry_run=opts.dry_run)

    if not opts.no_changelog:
        p.section("Updating changelog")
        effective_changelog_mode = resolve_changelog_mode(
            group,
            opts.changelog_mode,
        )
        update_changelog(
            RrtConfig(
                root=config.root,
                config_file=config.config_file,
                version_groups=[group],
                default_group_name=group.name,
            ),
            str(new),
            include_maintenance=opts.include_maintenance,
            dry_run=opts.dry_run,
            changelog_mode=effective_changelog_mode,
        )

    if group.lock_command and not opts.no_update:
        refresh_bump_lockfile(group, root, dry_run=opts.dry_run, verbose=verbose)

    if group.generated_assets and not opts.no_update:
        if not refresh_bump_generated_assets(group, root, dry_run=opts.dry_run, verbose=verbose):
            return 1

    finalize_bump_git(
        group,
        new,
        changed_paths,
        root,
        branch_name=branch_name,
        base=base,
        force=force,
        opts=opts,
    )
    return 0


_BUMP_EXAMPLES = (
    "  $ rrt bump patch\n"
    "  $ rrt bump minor --dry-run\n"
    "  $ rrt bump 2.1.0 --no-changelog --no-commit\n"
    "  $ rrt bump major --base-branch develop\n"
    "  $ rrt bump release --dry-run\n"
    "  $ rrt bump rc --base minor --dry-run\n"
    "  $ rrt bump patch --group self-assess,cupertino,confab"
)


def add_prerelease_base_flag(parser: argparse._ActionsContainer) -> None:
    """Register ``--base`` (dest ``prerelease_base``) shared by ``bump`` and ``workspace bump``."""
    parser.add_argument(
        "--base",
        dest="prerelease_base",
        choices=list(PRERELEASE_BASES),
        default=None,
        metavar="LEVEL",
        help=(
            "Core level for starting alpha|beta|rc from a final version "
            "(patch | minor | major | auto). Overrides [tool.rrt] prerelease_base."
        ),
    )


@register_command(name="bump", category=CommandCategory.WRITE, group=CommandGroup.VERSION_RELEASE)
def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the bump command."""
    parser = subparsers.add_parser(
        "bump",
        help="Bump project version using [tool.rrt] config.",
        description="Bump project version using [tool.rrt] config.",
        epilog=_BUMP_EXAMPLES,
    )
    parser.add_argument(
        "bump",
        metavar="<bump>",
        help=(
            "major | minor | patch | release | alpha | beta | rc | pre-release | calver | "
            "<version>  \u2014 bump kind or explicit version"
        ),
    )
    parser.add_argument(
        "--calver-scheme",
        choices=list(CALVER_SCHEMES),
        default="YYYY.MM.DD",
        metavar="SCHEME",
        help="CalVer scheme to use when bump=calver (YYYY.MM | YYYY.MM.DD | YYYY.M.D).",
    )

    prerelease_grp = parser.add_argument_group("Pre-release")
    add_prerelease_base_flag(prerelease_grp)

    release_grp = parser.add_argument_group("Release control")
    add_dry_run_flag(release_grp, verb="writing to disk")
    release_grp.add_argument(
        "--force",
        action="store_true",
        help="Reset the release branch if it already exists.",
    )
    release_grp.add_argument("--no-commit", action="store_true", help="Skip the git commit step.")
    release_grp.add_argument(
        "--no-verify",
        action="store_true",
        help="Pass --no-verify to git commit (bypass pre-commit hooks).",
    )

    content_grp = parser.add_argument_group("Content")
    content_grp.add_argument(
        "--no-changelog",
        action="store_true",
        help="Do not update the changelog file.",
    )
    content_grp.add_argument(
        "--no-pin-sync",
        action="store_true",
        help="Skip dependency pin synchronisation.",
    )
    content_grp.add_argument(
        "--no-update",
        action="store_true",
        help="Skip lockfile and generated-asset refresh steps.",
    )
    content_grp.add_argument(
        "--include-maintenance",
        action="store_true",
        help="Include maintenance commits in changelog.",
    )
    content_grp.add_argument(
        "--changelog-mode",
        choices=["auto", "promote", "generate"],
        default=None,
        metavar="MODE",
        help="How to write changelog entries (auto | promote | generate).",
    )

    git_grp = parser.add_argument_group("Git")
    git_grp.add_argument(
        "--base-branch",
        default=None,
        metavar="BRANCH",
        help="Branch to base the release on.",
    )
    git_grp.add_argument(
        "--group",
        default=None,
        metavar="GROUP",
        help=(
            "Version group to bump when multiple groups are configured. "
            "Pass a comma-separated list (e.g. 'a,b,c') to bump several groups "
            "in one invocation, each with its own release branch and commit."
        ),
    )
    parser.set_defaults(handler=cmd_bump)


# ---------------------------------------------------------------------------
# Source-owned topic docs
# ---------------------------------------------------------------------------

_VERSION_TARGET_CONFIG_DOC = """
## Version target configuration reference

### `kind='pattern'` targets

When a version string lives outside a well-known format (`pep621`,
`cargo_toml`, `package_json`, etc.), use `kind='pattern'` with a
single-capture-group regex. The captured group is **exactly the version
string** — no prefix or suffix groups needed.

```toml
[[tool.rrt.version_targets]]
path = "src/myapp/__init__.py"
kind = "pattern"
pattern = '^VERSION = "([^"]+)"$'
```

Rules:

- `pattern` must compile as a valid Python regex.
- The regex must contain **exactly 1 capture group** whose match is the
  version string itself.
- `kind='pattern'` is mutually exclusive with `section`, `field`, and
  all other `kind` values.
- The pattern is applied with `re.MULTILINE`; use `^` / `$` anchors for
  line-level matching.

`kind='pattern'` differs from the **legacy bare-pattern** approach (no
`kind`), which requires 3 groups — `(prefix)(version)(suffix)`. The
`kind='pattern'` form is preferred for new targets because the regex is
shorter and group intent is unambiguous:

```toml
# Legacy 3-group pattern — still supported
[[tool.rrt.version_targets]]
path = "docs/conf.py"
pattern = '^(release = ")([^"]+)(")$'

# Preferred: kind='pattern' with 1 capture group
[[tool.rrt.version_targets]]
path = "docs/conf.py"
kind = "pattern"
pattern = '^release = "([^"]+)"$'
```

### `pin_target_missing`

Controls what happens when a `[[tool.rrt.pin_targets]]` entry pattern
finds no matches in the target file:

| Value | Behavior |
|---|---|
| `"error"` *(default)* | `rrt bump` fails if any pin target has zero matches |
| `"warn"` | `rrt bump` prints a warning and continues |

Set in `[tool.rrt]`:

```toml
[tool.rrt]
pin_target_missing = "warn"
```

Use `"warn"` during a migration where some pin files may not yet contain
the expected pattern, or when a pin target is intentionally optional.

`pin_target_missing` applies to `rrt bump` only; `rrt release check` always
reports missing pin target matches as warnings regardless of this setting.

### `version_groups` — per-component versioning

`version_groups` lets a single repository maintain multiple independently
released components, each with its own version, changelog, and release
branch.

```toml
[[tool.rrt.version_groups]]
name = "backend"
release_branch = "release/backend/v{version}"
changelog_file = "backend/CHANGELOG.md"

  [[tool.rrt.version_groups.version_targets]]
  path = "backend/pyproject.toml"
  kind = "pep621"

[[tool.rrt.version_groups]]
name = "sdk"
release_branch = "release/sdk/v{version}"
changelog_file = "sdk/CHANGELOG.md"
tag_prefix = "sdk-v"
changelog_paths = ["sdk/"]

  [[tool.rrt.version_groups.version_targets]]
  path = "sdk/package.json"
  kind = "package_json"
```

Each group supports: `release_branch`, `changelog_file`,
`changelog_workflow`, `tag_prefix`, `prerelease_base`, `changelog_paths`,
`lock_command`, `generated_files`, `version_targets`, and `pin_targets`.

`prerelease_base` (default `"patch"`) picks the core an `alpha`, `beta` or
`rc` bump targets from a final version. `patch` turns `1.0.0` into
`1.0.1-rc.1`; `minor` gives `1.1.0-rc.1` and `major` gives `2.0.0-rc.1`.
`auto` reads Conventional Commits since the last final tag. A breaking change
means major, a `feat` means minor, anything else means patch. Set it under
`[tool.rrt]` for every group; a group's own value wins over that default.
Moving inside a channel (`rc.1` to `rc.2`) never changes the core.

`tag_prefix` (default `"v"`) names the group's release tags. It is the
default for `rrt tag create --prefix` / `rrt tag check --prefix`, and it is
what anchors a generated changelog section to the group's *own* latest tag —
without it, a repository holding both `v*` and `sdk-v*` tags would start
every group's range at whichever tag sorts first overall. A `{group}` token
in the prefix renders to the group name, so `"{group}-v"` means `sdk-v` here.
The latest tag is chosen by version precedence: `v1.0.0` outranks
`v1.0.0-rc.2`, and non-version tags such as `vnext` are ignored.

`changelog_paths` optionally restricts generated entries to commits touching
the group's own files, so one group's section cannot pick up another's work.

Bump a specific group:

```bash
rrt bump minor --group backend
rrt bump patch --group sdk
```

Bump several groups in one invocation with a comma-separated list -- each
group gets its own release branch and commit, identical to running the
command once per group:

```bash
rrt bump patch --group backend,sdk
```

When a single group is configured, `--group` is optional. With multiple
groups, set `default_group_name` to select the default:

```toml
[tool.rrt]
default_group_name = "backend"
```

## Caveats

A `kind='pattern'` regex must have exactly one capture group. The legacy
bare-pattern form still works but needs three groups instead, and the two
styles cannot be mixed on the same target.

`pin_target_missing` only changes `rrt bump` behavior. `rrt release check`
always reports a missing pin match as a warning, regardless of this
setting.

`--base` is now a flag of its own that sets the pre-release base. It no longer
abbreviates `--base-branch`, so spell out `--base-branch` to pick the branch.
An `auto` base reads git history, so it needs the group's release tags locally.

With more than one `version_group` configured, `--group` becomes required
unless `default_group_name` names a default. Bumping several groups in one
invocation still creates one release branch and one commit per group.

## Related docs

- [Version release](/repo-release-tools/commands/version-release/)
- [rrt CLI](/repo-release-tools/commands/rrt-cli/)
- [Repo health](/repo-release-tools/commands/repo-health/)
"""

# The module docstring is the canonical doc; the reference block above extends
# it rather than replacing it, so editing __doc__ actually changes the page.
_BUMP_DOC = (__doc__ or "") + _VERSION_TARGET_CONFIG_DOC

SOURCE_OWNED_TOPIC_DOCS: tuple[tuple[str, str], ...] = (("bump", _BUMP_DOC),)
