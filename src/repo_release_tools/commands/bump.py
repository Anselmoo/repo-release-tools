"""Version bump command."""

from __future__ import annotations

import argparse
import contextlib
import sys
from pathlib import Path

from repo_release_tools import git
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
    format_autodetected_config_notice,
    format_missing_tool_rrt_guidance,
    is_missing_tool_rrt_error,
    iter_config_files,
    load_or_autodetect_config,
)
from repo_release_tools.ui import (
    GLYPHS,
    DryRunPrinter,
    ProgressLine,
    spinner_lines,
)
from repo_release_tools.version_targets import (
    check_autodetected_version_consistency,
    read_group_current_version,
    replace_pin_in_file,
    replace_version_in_file,
)
from repo_release_tools.versioning import Version

PREVIEW_LINES = 8


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
        p = DryRunPrinter(False)
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
            p = DryRunPrinter(False)
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
        p = DryRunPrinter(False)
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
    p = DryRunPrinter(False)
    p.ok(f"{path} updated")


def cmd_bump(args: argparse.Namespace) -> int:
    """Bump project version using [tool.rrt]."""
    root = Path.cwd()
    force = getattr(args, "force", False)
    try:
        config = load_or_autodetect_config(root)
    except FileNotFoundError:
        p = DryRunPrinter(False)
        p.line("No supported rrt config file found.", ok=False, stream=sys.stderr)
        p.line(format_missing_tool_rrt_guidance(root, []), ok=False, stream=sys.stderr)
        return 1
    except ValueError as exc:
        if is_missing_tool_rrt_error(exc):
            p = DryRunPrinter(False)
            p.line("No [tool.rrt] configuration found.", ok=False, stream=sys.stderr)
            p.line(
                format_missing_tool_rrt_guidance(root, iter_config_files(root)),
                ok=False,
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

    if config.autodetected:
        p = DryRunPrinter(False)
        p.line(format_autodetected_config_notice(config), ok=False, stream=sys.stderr)
        if mismatch := check_autodetected_version_consistency(config):
            p.line(mismatch, ok=False, stream=sys.stderr)
            return 1

    try:
        group = config.resolve_group(args.group)
    except ValueError as exc:
        p = DryRunPrinter(False)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1

    current = read_group_current_version(group)
    if args.bump in {"major", "minor", "patch"}:
        new = current.bump(args.bump)
    else:
        try:
            new = Version.parse(args.bump)
        except ValueError as exc:
            p = DryRunPrinter(False)
            p.line(str(exc), ok=False, stream=sys.stderr)
            return 1

    branch_name = group.release_branch.format(version=new)
    current_branch = "<current>" if args.dry_run else git.current_branch(root)
    base = args.base_branch or current_branch

    p = DryRunPrinter(args.dry_run)
    p.blank_line()
    p.header(
        "Version bump",
        Current=f"{current} {GLYPHS.arrow.right} {new}",
        Branch=branch_name,
        Base=base,
    )

    branch_exists = False
    if not args.dry_run:
        if not git.working_tree_clean(root):
            p = DryRunPrinter(False)
            p.line(
                "Working tree has uncommitted changes. Commit or stash them first, or use --dry-run.",
                ok=False,
                stream=sys.stderr,
            )
            return 1
        branch_exists = git.branch_exists(root, branch_name)
        if branch_exists and not force:
            p = DryRunPrinter(False)
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
            p = DryRunPrinter(False)
            p.line(msg)

    version_progress = ProgressLine(file=sys.stdout)
    p.section("Updating version strings")
    total_targets = len(group.version_targets)
    for i, target in enumerate(group.version_targets, 1):
        if total_targets > 1 and i > 1:
            version_progress.clear()
        replace_version_in_file(target, str(new), dry_run=args.dry_run)
        if total_targets > 1:
            version_progress.update_bar(i / total_targets)
    if total_targets > 1:
        version_progress.clear()

    all_pins = group.pin_targets + config.global_pin_targets
    if all_pins and not getattr(args, "no_pin_sync", False):
        pin_progress = ProgressLine(file=sys.stdout)
        p.section("Updating doc pins")
        seen_pin_keys: set[tuple[object, str]] = set()
        unique_pins: list = []
        for pin in all_pins:
            key = (pin.path, pin.pattern)
            if key not in seen_pin_keys:
                seen_pin_keys.add(key)
                unique_pins.append(pin)
        total_pins = len(unique_pins)
        for i, pin in enumerate(unique_pins, 1):
            if total_pins > 1 and i > 1:
                pin_progress.clear()
            replace_pin_in_file(pin, str(new), dry_run=args.dry_run)
            if total_pins > 1:
                pin_progress.update_bar(i / total_pins)
        if total_pins > 1:
            pin_progress.clear()

    if not args.no_changelog:
        p.section("Updating changelog")
        effective_changelog_mode = resolve_changelog_mode(
            config, getattr(args, "changelog_mode", None)
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

    p.section("Git")
    create_flag = "-B" if force else "-b"
    git.run(
        ["git", "checkout", create_flag, branch_name],
        root,
        dry_run=args.dry_run,
        label=f"git checkout {create_flag}",
    )

    files_to_stage = [str(target.path.relative_to(root)) for target in group.version_targets]
    for path in group.generated_files:
        if path.exists():
            files_to_stage.append(str(path.relative_to(root)))
    if group.changelog_file.exists() and not args.no_changelog:
        files_to_stage.append(str(group.changelog_file.relative_to(root)))
    if not getattr(args, "no_pin_sync", False):
        seen_pin_stage: set[tuple[object, str]] = set()
        for pin in all_pins:
            key = (pin.path, pin.pattern)
            if key in seen_pin_stage:
                continue
            seen_pin_stage.add(key)
            files_to_stage.append(str(pin.path.relative_to(root)))
    git.run(
        ["git", "add", *dict.fromkeys(files_to_stage)], root, dry_run=args.dry_run, label="git add"
    )

    if not args.no_commit:
        git.run(["git", "add", "-u"], root, dry_run=args.dry_run, label="git add -u")
        commit_msg = f"chore: bump version to v{new}"
        git.run(["git", "commit", "-m", commit_msg], root, dry_run=args.dry_run, label="git commit")
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
        help="major | minor | patch | <semver>  \u2014 bump kind or explicit version",
    )

    release_grp = parser.add_argument_group("Release control")
    release_grp.add_argument(
        "--dry-run", action="store_true", help="Preview changes without writing to disk."
    )
    release_grp.add_argument(
        "--force",
        action="store_true",
        help="Reset the release branch if it already exists.",
    )
    release_grp.add_argument("--no-commit", action="store_true", help="Skip the git commit step.")

    content_grp = parser.add_argument_group("Content")
    content_grp.add_argument(
        "--no-changelog", action="store_true", help="Do not update the changelog file."
    )
    content_grp.add_argument(
        "--no-pin-sync",
        action="store_true",
        help="Skip dependency pin synchronisation.",
    )
    content_grp.add_argument(
        "--no-update",
        action="store_true",
        help="Skip the lockfile update step.",
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
