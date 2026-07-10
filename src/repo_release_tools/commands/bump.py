"""Bump a release version and prepare the associated release branch.

## Overview

This command reads the active ``[tool.rrt]`` configuration, computes a new
version, updates configured files, and creates the release branch named by the
selected version group.

The bump value may be one of:

* ``major``, ``minor``, or ``patch`` to increment the current version
* an explicit version string such as ``2.1.0``

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
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import sys
from pathlib import Path

from repo_release_tools.changelog import (
    build_changelog_section,
    detect_changelog_format,
    get_unreleased_entries,
    has_unreleased_section,
    insert_generated_section,
    promote_unreleased,
)
from repo_release_tools.config import (
    RrtConfig,
    VersionGroup,
    find_repo_root,
    format_autodetected_config_notice,
    format_missing_tool_rrt_guidance,
    is_missing_tool_rrt_error,
    iter_config_files,
    load_or_autodetect_config,
)
from repo_release_tools.preflight import PreflightError, run_preflight
from repo_release_tools.ui import (
    GLYPHS,
    DryRunPrinter,
    ProgressLine,
    VerbosePrinter,
    spinner_lines,
)
from repo_release_tools.version.calver import CALVER_SCHEMES, CalVersion
from repo_release_tools.version.semver import PRE_RELEASE_CHANNELS, Version
from repo_release_tools.version.targets import (
    check_autodetected_version_consistency,
    read_group_current_version,
    replace_all_versions_atomic,
    replace_pin_in_file,
)
from repo_release_tools.workflow import git

PREVIEW_LINES = 8


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
    replace_all_versions_atomic(group.version_targets, version, dry_run=dry_run)
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


def resolve_changelog_mode(config: RrtConfig, requested_mode: str | None) -> str:
    """Resolve the changelog update mode from CLI input and workflow defaults."""
    if requested_mode is not None:
        return requested_mode
    return "generate" if config.changelog_workflow == "squash" else "auto"


def git_log_since_latest_tag(root: Path) -> list[str]:
    """Collect commit subjects since the latest tag."""
    tags_raw = git.capture(["git", "tag", "--sort=-v:refname"], root)
    tags = [tag.strip() for tag in tags_raw.splitlines() if tag.strip()]
    ref = f"{tags[0]}..HEAD" if tags else "HEAD"
    out = git.capture(["git", "log", ref, "--pretty=format:%s"], root)
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
    section = build_changelog_section(
        version,
        git_log_since_latest_tag(config.root),
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


def cmd_bump(args: argparse.Namespace) -> int:
    """Bump project version using [tool.rrt]."""
    verbose: int = getattr(args, "verbose", 0) or 0
    root = find_repo_root(Path.cwd())
    force = getattr(args, "force", False)
    try:
        config = load_or_autodetect_config(root)
    except FileNotFoundError:
        p = VerbosePrinter(verbose=verbose)
        p.line("No supported rrt config file found.", ok=False, stream=sys.stderr)
        p.line(format_missing_tool_rrt_guidance(root, []), ok=False, stream=sys.stderr)
        return 1
    except ValueError as exc:
        if is_missing_tool_rrt_error(exc):
            p = VerbosePrinter(verbose=verbose)
            p.line("No [tool.rrt] configuration found.", ok=False, stream=sys.stderr)
            p.line(
                format_missing_tool_rrt_guidance(root, iter_config_files(root)),
                ok=False,
                stream=sys.stderr,
            )
            return 1
        p = VerbosePrinter(verbose=verbose)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1
    except RuntimeError as exc:
        p = VerbosePrinter(verbose=verbose)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1

    if config.autodetected:
        p = VerbosePrinter(verbose=verbose)
        p.line(format_autodetected_config_notice(config), ok=False, stream=sys.stderr)
        if mismatch := check_autodetected_version_consistency(config):
            p.line(mismatch, ok=False, stream=sys.stderr)
            return 1

    try:
        group = config.resolve_group(args.group)
    except ValueError as exc:
        p = VerbosePrinter(verbose=verbose)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1

    current = read_group_current_version(group)
    _BUMP_KINDS = {"major", "minor", "patch", "pre-release", "calver", *PRE_RELEASE_CHANNELS}
    if args.bump == "calver":
        calver_scheme = getattr(args, "calver_scheme", "YYYY.MM.DD")
        try:
            current_calver = CalVersion.parse(str(current))
        except ValueError:
            current_calver = CalVersion.today(calver_scheme)
            # treat any non-calver current as a fresh start
            new_str = str(current_calver)
        else:
            new_str = str(current_calver.bump())
        new = new_str  # type: ignore[assignment]
    elif args.bump in _BUMP_KINDS:
        new = current.bump(args.bump)  # type: ignore[assignment]
    else:
        try:
            new = Version.parse(args.bump)  # type: ignore[assignment]
        except ValueError:
            try:
                new = CalVersion.parse(args.bump)  # type: ignore[assignment]
            except ValueError:
                p = VerbosePrinter(verbose=verbose)
                p.line(f"Invalid bump value: {args.bump!r}", ok=False, stream=sys.stderr)
                return 1

    branch_name = group.release_branch.format(version=new)
    current_branch = "<current>" if args.dry_run else git.current_branch(root)
    base = args.base_branch or current_branch

    p = DryRunPrinter(args.dry_run, verbose=verbose)
    p.blank_line()
    p.header(
        "Version bump",
        Current=f"{current} {GLYPHS.arrow.right} {new}",
        Branch=branch_name,
        Base=base,
    )

    branch_exists = False
    try:
        run_preflight(config, dry_run=args.dry_run, group=group)
    except PreflightError as exc:
        p = VerbosePrinter(verbose=verbose)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1

    if not args.dry_run:
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

    version_progress = ProgressLine(file=sys.stdout)
    p.section("Updating version strings")
    total_targets = len(group.version_targets)
    for i, _target in enumerate(group.version_targets, 1):
        if total_targets > 1 and i > 1:
            version_progress.clear()
        if total_targets > 1:
            version_progress.update_bar(i / total_targets)
    if total_targets > 1:
        version_progress.clear()

    all_pins = group.pin_targets + config.global_pin_targets
    no_pin_sync = getattr(args, "no_pin_sync", False)
    if all_pins and not no_pin_sync:
        pin_progress = ProgressLine(file=sys.stdout)
        p.section("Updating doc pins")
        seen_pin_count: set[tuple[object, str]] = set()
        unique_pin_count = 0
        for pin in all_pins:
            key = (pin.path, pin.pattern)
            if key not in seen_pin_count:
                seen_pin_count.add(key)
                unique_pin_count += 1
        total_pins = unique_pin_count
        for i in range(1, total_pins + 1):
            if total_pins > 1 and i > 1:
                pin_progress.clear()
            if total_pins > 1:
                pin_progress.update_bar(i / total_pins)
        if total_pins > 1:
            pin_progress.clear()

    # Build a pin-free view when no_pin_sync is set so apply_version skips pins.
    apply_group = dataclasses.replace(group, pin_targets=[]) if no_pin_sync else group
    apply_config = dataclasses.replace(config, global_pin_targets=[]) if no_pin_sync else config
    changed_paths = apply_version(apply_group, str(new), apply_config, dry_run=args.dry_run)

    if not args.no_changelog:
        p.section("Updating changelog")
        effective_changelog_mode = resolve_changelog_mode(
            config,
            getattr(args, "changelog_mode", None),
        )
        update_changelog(
            RrtConfig(
                root=config.root,
                config_file=config.config_file,
                version_groups=[group],
                default_group_name=group.name,
            ),
            str(new),
            include_maintenance=args.include_maintenance,
            dry_run=args.dry_run,
            changelog_mode=effective_changelog_mode,
        )

    if group.lock_command and not args.no_update:
        p.section("Refreshing lockfiles")
        spinner = (
            contextlib.nullcontext()
            if args.dry_run
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
                dry_run=args.dry_run,
                label="lock command",
                suppress_announce=True,
            )

    if group.generated_assets and not args.no_update:
        p.section("Refreshing generated assets")
        for asset in group.generated_assets:
            command_preview = " ".join(asset.command)
            spinner = (
                contextlib.nullcontext()
                if args.dry_run
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
                        dry_run=args.dry_run,
                        label=f"generated asset command ({asset.path.relative_to(root)})",
                        suppress_announce=True,
                    )
            except RuntimeError as exc:
                if args.dry_run:
                    p.warn(
                        f"Generated asset command for {asset.path.relative_to(root)} failed in dry-run: {exc}",
                    )
                    continue
                p.line(str(exc), ok=False, stream=sys.stderr)
                return 1

            if not asset.path.exists():
                message = f"Generated asset {asset.path.relative_to(root)} not found after refresh command"
                if args.dry_run:
                    p.warn(message)
                else:
                    p.line(message, ok=False, stream=sys.stderr)
                    return 1

    p.section("Git")
    create_flag = "-B" if force else "-b"
    git.run(
        ["git", "checkout", create_flag, branch_name],
        root,
        dry_run=args.dry_run,
        label=f"git checkout {create_flag}",
    )

    # changed_paths contains version-target paths followed by pin paths (already deduplicated).
    files_to_stage = [str(p.relative_to(root)) for p in changed_paths]
    for path in group.generated_files:
        if path.exists():
            files_to_stage.append(str(path.relative_to(root)))
    for asset in group.generated_assets:
        if asset.path.exists():
            files_to_stage.append(str(asset.path.relative_to(root)))
    if group.changelog_file.exists() and not args.no_changelog:
        files_to_stage.append(str(group.changelog_file.relative_to(root)))
    git.run(
        ["git", "add", *dict.fromkeys(files_to_stage)],
        root,
        dry_run=args.dry_run,
        label="git add",
    )

    if not args.no_commit:
        git.run(["git", "add", "-u"], root, dry_run=args.dry_run, label="git add -u")
        commit_msg = f"chore: bump version to v{new}"
        commit_cmd = ["git", "commit", "-m", commit_msg]
        if getattr(args, "no_verify", False):
            commit_cmd.append("--no-verify")
        try:
            git.run(commit_cmd, root, dry_run=args.dry_run, label="git commit")
        except RuntimeError:
            # A pre-commit hook (e.g. rrt-cli-docs) may have auto-regenerated
            # files during this pass — pre-commit always fails that pass even
            # though the fix is now correct. Re-stage and retry once.
            git.run(["git", "add", "-u"], root, dry_run=args.dry_run, label="git add -u")
            git.run(commit_cmd, root, dry_run=args.dry_run, label="git commit")
        done_msg = f"Done. Branch '{branch_name}' created with commit: {commit_msg!r}"
        p.footer(done_msg)
    else:
        done_msg = f"Done. Branch '{branch_name}' created and files staged."
        p.meta("Base branch", base)
        p.footer(done_msg)
    if args.dry_run:
        # Provide an explicit dry-run completion line expected by some tests
        p.line("no files were modified")
    return 0


_BUMP_EXAMPLES = (
    "  $ rrt bump patch\n"
    "  $ rrt bump minor --dry-run\n"
    "  $ rrt bump 2.1.0 --no-changelog --no-commit\n"
    "  $ rrt bump major --base-branch develop"
)


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
            "major | minor | patch | alpha | beta | rc | pre-release | calver | <version>  "
            "\u2014 bump kind or explicit version"
        ),
    )
    parser.add_argument(
        "--calver-scheme",
        choices=list(CALVER_SCHEMES),
        default="YYYY.MM.DD",
        metavar="SCHEME",
        help="CalVer scheme to use when bump=calver (YYYY.MM | YYYY.MM.DD | YYYY.M.D).",
    )

    release_grp = parser.add_argument_group("Release control")
    release_grp.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing to disk.",
    )
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
        help="Version group to bump when multiple groups are configured.",
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

  [[tool.rrt.version_groups.version_targets]]
  path = "sdk/package.json"
  kind = "package_json"
```

Each group supports: `release_branch`, `changelog_file`,
`changelog_workflow`, `lock_command`, `generated_files`,
`version_targets`, and `pin_targets`.

Bump a specific group:

```bash
rrt bump minor --group backend
rrt bump patch --group sdk
```

When a single group is configured, `--group` is optional. With multiple
groups, set `default_group_name` to select the default:

```toml
[tool.rrt]
default_group_name = "backend"
```
"""

SOURCE_OWNED_TOPIC_DOCS: tuple[tuple[str, str], ...] = (("bump", _VERSION_TARGET_CONFIG_DOC),)
