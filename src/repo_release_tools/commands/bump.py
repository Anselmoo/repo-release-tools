"""Version bump command."""

from __future__ import annotations

import argparse
import sys

from pathlib import Path

from repo_release_tools import git, output
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
from repo_release_tools.version_targets import (
    check_autodetected_version_consistency,
    read_group_current_version,
    replace_pin_in_file,
    replace_version_in_file,
)
from repo_release_tools.versioning import Version

PREVIEW_LINES = 8


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
        print(output.warning(f"{path} not found {output.GLYPHS.typography.mdash} skipping"))
        return

    existing = path.read_text(encoding="utf-8")
    fmt = detect_changelog_format(path.name)
    has_entries = bool(get_unreleased_entries(existing, fmt))

    # ---- Decide mode -------------------------------------------------------
    if changelog_mode == "generate":
        do_promote = False
    elif changelog_mode == "promote":
        if not has_entries:
            if has_unreleased_section(existing, fmt):
                print(
                    output.warning(
                        f"[Unreleased] section in {path} is empty"
                        f" {output.GLYPHS.typography.mdash} nothing to promote."
                    )
                )
            else:
                print(
                    output.warning(
                        f"No [Unreleased] section found in {path}"
                        f" {output.GLYPHS.typography.mdash} nothing to promote."
                    )
                )
            return
        do_promote = True
    else:  # "auto"
        do_promote = has_entries

    # ---- Promote [Unreleased] → versioned section --------------------------
    if do_promote:
        section_text = promote_unreleased(existing, version, fmt)
        if dry_run:
            print(output.dry_run(f"Would promote [Unreleased] to [{version}] in {path}:"))
            for line in section_text.splitlines()[:PREVIEW_LINES]:
                print(output.status(">", line, indent=4))
            if len(section_text.splitlines()) > PREVIEW_LINES:
                print(output.status(">", str(output.GLYPHS.typography.ellipsis), indent=4))
            return
        path.write_text(section_text, encoding="utf-8")
        print(output.ok(f"{path} updated (promoted [Unreleased] to [{version}])"))
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
        print(output.dry_run(f"Would prepend to {path}:"))
        for line in section_text.splitlines()[:PREVIEW_LINES]:
            print(output.status(">", line, indent=4))
        if len(section_text.splitlines()) > PREVIEW_LINES:
            print(output.status(">", str(output.GLYPHS.typography.ellipsis), indent=4))
        return

    path.write_text(section_text, encoding="utf-8")
    print(output.ok(f"{path} updated"))


def cmd_bump(args: argparse.Namespace) -> int:
    """Bump project version using [tool.rrt]."""
    root = Path.cwd()
    force = getattr(args, "force", False)
    try:
        config = load_or_autodetect_config(root)
    except FileNotFoundError:
        print(output.warning("No supported rrt config file found."), file=sys.stderr)
        print(format_missing_tool_rrt_guidance(root, []), file=sys.stderr)
        return 1
    except ValueError as exc:
        if is_missing_tool_rrt_error(exc):
            print(output.warning("No [tool.rrt] configuration found."), file=sys.stderr)
            print(format_missing_tool_rrt_guidance(root, iter_config_files(root)), file=sys.stderr)
            return 1
        print(str(exc), file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if config.autodetected:
        print(output.warning(format_autodetected_config_notice(config)), file=sys.stderr)
        if mismatch := check_autodetected_version_consistency(config):
            print(mismatch, file=sys.stderr)
            return 1

    try:
        group = config.resolve_group(args.group)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    current = read_group_current_version(group)
    if args.bump in {"major", "minor", "patch"}:
        new = current.bump(args.bump)
    else:
        try:
            new = Version.parse(args.bump)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1

    branch_name = group.release_branch.format(version=new)
    current_branch = "<current>" if args.dry_run else git.current_branch(root)
    base = args.base_branch or current_branch

    title = "[DRY RUN] Version bump" if args.dry_run else "Version bump"
    print()
    print(
        output.panel(
            title,
            [
                ("Current", f"{current} {output.GLYPHS.arrow.right} {new}"),
                ("Branch", branch_name),
                ("Base", base),
            ],
        )
    )
    print()

    branch_exists = False
    if not args.dry_run:
        if not git.working_tree_clean(root):
            print(
                "Working tree has uncommitted changes. Commit or stash them first, or use --dry-run.",
                file=sys.stderr,
            )
            return 1
        branch_exists = git.branch_exists(root, branch_name)
        if branch_exists and not force:
            print(
                f"Branch '{branch_name}' already exists. Delete it first or choose a different version.",
                file=sys.stderr,
            )
            return 1
        if current_branch != base:
            git.run(["git", "checkout", base], root, dry_run=False, label="git checkout base")
        if branch_exists:
            print(
                output.warning(f"Branch '{branch_name}' already exists. Resetting it with --force.")
            )

    g = output.GLYPHS
    print(output.section("Updating version strings"))
    total_targets = len(group.version_targets)
    for i, target in enumerate(group.version_targets, 1):
        replace_version_in_file(target, str(new), dry_run=args.dry_run)
        if total_targets > 1:
            print(f"  {g.progress.render_bar(i / total_targets)}")

    all_pins = group.pin_targets + config.global_pin_targets
    if all_pins and not getattr(args, "no_pin_sync", False):
        print(f"\n{output.section('Updating doc pins')}")
        seen_pin_keys: set[tuple[object, str]] = set()
        unique_pins: list = []
        for pin in all_pins:
            key = (pin.path, pin.pattern)
            if key not in seen_pin_keys:
                seen_pin_keys.add(key)
                unique_pins.append(pin)
        total_pins = len(unique_pins)
        for i, pin in enumerate(unique_pins, 1):
            replace_pin_in_file(pin, str(new), dry_run=args.dry_run)
            if total_pins > 1:
                print(f"  {g.progress.render_bar(i / total_pins)}")

    if not args.no_changelog:
        print(f"\n{output.section('Updating changelog')}")
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
            changelog_mode=getattr(args, "changelog_mode", "auto"),
        )

    if group.lock_command and not args.no_update:
        print(f"\n{output.section('Refreshing lockfiles')}")
        with output.spinner_lines("Running lock command…"):
            git.run(group.lock_command, root, dry_run=args.dry_run, label="lock command")

    print(f"\n{output.section('Git')}")
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
        print()
        print(output.ok(f"Done. Branch '{branch_name}' created with commit: {commit_msg!r}"))
    else:
        print()
        print(output.ok(f"Done. Branch '{branch_name}' created and files staged."))

    if args.dry_run:
        print(output.status(output.GLYPHS.bullet.dot, f"Base branch: {base}"))
        print(output.dry_run_complete("no files were modified"))
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the bump command."""
    parser = subparsers.add_parser("bump", help="Bump project version using [tool.rrt] config.")
    parser.add_argument(
        "bump",
        metavar="BUMP",
        help="Bump kind: major | minor | patch, or an explicit semver like 1.2.3",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing changes.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reset the release branch if it already exists instead of failing.",
    )
    parser.add_argument("--no-commit", action="store_true", help="Skip the git commit step.")
    parser.add_argument("--no-changelog", action="store_true", help="Skip updating the changelog.")
    parser.add_argument(
        "--no-pin-sync",
        action="store_true",
        help="Skip updating doc/CI pin references (pin_targets).",
    )
    parser.add_argument(
        "--no-update",
        action="store_true",
        help="Skip the lockfile update step (do not run the lock command).",
    )
    parser.add_argument(
        "--include-maintenance",
        action="store_true",
        help="Include chore/ci/build/test entries in the changelog.",
    )
    parser.add_argument(
        "--changelog-mode",
        choices=["auto", "promote", "generate"],
        default="auto",
        metavar="MODE",
        help=(
            "How to update the changelog: "
            "'auto' (default) promotes [Unreleased] when it has entries, "
            "otherwise generates from the git log; "
            "'promote' requires a non-empty [Unreleased] section and renames it; "
            "'generate' always writes a new section from the git log "
            "(heading/hash notation)."
        ),
    )
    parser.add_argument(
        "--base-branch",
        default=None,
        metavar="BRANCH",
        help="Branch to create the release branch from (default: current branch).",
    )
    parser.add_argument(
        "--group",
        default=None,
        metavar="GROUP",
        help="Version group to bump when multiple release groups are configured.",
    )
    parser.set_defaults(handler=cmd_bump)
