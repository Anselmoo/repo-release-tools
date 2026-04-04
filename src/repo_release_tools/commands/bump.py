"""Version bump command."""

from __future__ import annotations

import argparse
import sys

from pathlib import Path

from repo_release_tools import git, output
from repo_release_tools.changelog import build_changelog_section
from repo_release_tools.config import (
    RrtConfig,
    format_autodetected_config_notice,
    format_missing_tool_rrt_guidance,
    is_missing_tool_rrt_error,
    iter_config_files,
    load_or_autodetect_config,
)
from repo_release_tools.version_targets import (
    read_group_current_version,
    read_group_version_strings,
    replace_version_in_file,
)
from repo_release_tools.versioning import Version

PREVIEW_LINES = 8


def _ensure_autodetected_versions_match(config: RrtConfig) -> str | None:
    """Return an error message when auto-detected targets disagree on the version."""
    if not config.autodetected:
        return None

    group = config.resolve_group()
    versions = read_group_version_strings(group)
    distinct_versions = {version for _, version in versions}
    if len(distinct_versions) <= 1:
        return None

    details = ", ".join(f"{target.path.name}={version}" for target, version in versions)
    return (
        "Auto-detected version files do not agree: "
        f"{details}. Make them consistent, or add [tool.rrt] to choose explicit targets/groups."
    )


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
) -> None:
    """Prepend a generated changelog section."""
    path = config.changelog_file
    if not path.exists():
        print(output.warning(f"{path} not found {output.GLYPHS.typography.mdash} skipping"))
        return

    section = build_changelog_section(
        version,
        git_log_since_latest_tag(config.root),
        include_maintenance=include_maintenance,
    )

    if dry_run:
        print(output.dry_run(f"Would prepend to {path}:"))
        for line in section.splitlines()[:PREVIEW_LINES]:
            print(output.status(">", line, indent=4))
        if len(section.splitlines()) > PREVIEW_LINES:
            print(output.status(">", str(output.GLYPHS.typography.ellipsis), indent=4))
        return

    existing = path.read_text(encoding="utf-8")
    path.write_text(section + "\n" + existing, encoding="utf-8")
    print(output.ok(f"{path} updated"))


def cmd_bump(args: argparse.Namespace) -> int:
    """Bump project version using [tool.rrt]."""
    root = Path.cwd()
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
        if mismatch := _ensure_autodetected_versions_match(config):
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
    base = args.base_branch or ("<current>" if args.dry_run else git.current_branch(root))

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

    if not args.dry_run:
        if not git.working_tree_clean(root):
            print(
                "Working tree has uncommitted changes. Commit or stash them first, or use --dry-run.",
                file=sys.stderr,
            )
            return 1
        if git.branch_exists(root, branch_name):
            print(
                f"Branch '{branch_name}' already exists. Delete it first or choose a different version.",
                file=sys.stderr,
            )
            return 1
        if git.current_branch(root) != base:
            git.run(["git", "checkout", base], root, dry_run=False, label="git checkout base")

    print(output.section("Updating version strings"))
    for target in group.version_targets:
        replace_version_in_file(target, str(new), dry_run=args.dry_run)

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
        )

    if group.lock_command and not args.no_update:
        print(f"\n{output.section('Refreshing lockfiles')}")
        git.run(group.lock_command, root, dry_run=args.dry_run, label="lock command")

    print(f"\n{output.section('Git')}")
    git.run(
        ["git", "checkout", "-b", branch_name], root, dry_run=args.dry_run, label="git checkout -b"
    )

    files_to_stage = [str(target.path.relative_to(root)) for target in group.version_targets]
    for path in group.generated_files:
        if path.exists():
            files_to_stage.append(str(path.relative_to(root)))
    if group.changelog_file.exists() and not args.no_changelog:
        files_to_stage.append(str(group.changelog_file.relative_to(root)))
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
    parser.add_argument("--no-commit", action="store_true", help="Skip the git commit step.")
    parser.add_argument("--no-changelog", action="store_true", help="Skip updating the changelog.")
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
