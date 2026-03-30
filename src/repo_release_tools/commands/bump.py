"""Version bump command."""

from __future__ import annotations

import argparse
import re
import sys
import tomllib

from pathlib import Path

from repo_release_tools import git, output
from repo_release_tools.changelog import build_changelog_section
from repo_release_tools.config import RrtConfig, VersionTarget, load_config
from repo_release_tools.versioning import Version


PEP621_PATTERN = re.compile(r'(?ms)(^\[project\]\s.*?^version\s*=\s*")([^"]+)(")')
PREVIEW_LINES = 8


def replace_version_in_file(
    target: VersionTarget,
    new_version: str,
    *,
    dry_run: bool,
) -> None:
    """Update a single configured version target."""
    path = target.path
    text = path.read_text(encoding="utf-8")

    if target.kind == "pep621":
        updated = PEP621_PATTERN.sub(rf"\g<1>{new_version}\g<3>", text, count=1)
    elif target.pattern:
        pattern = re.compile(target.pattern, re.MULTILINE)
        updated = pattern.sub(rf"\g<1>{new_version}\g<3>", text, count=1)
    else:
        updated = replace_toml_field(
            text, new_version, section=target.section or "", field=target.field or ""
        )

    if text == updated:
        raise RuntimeError(f"{path} version replacement had no effect")

    if dry_run:
        print(output.dry_run(f'Would update {path}: version = "{new_version}"'))
        return

    path.write_text(updated, encoding="utf-8")
    print(output.ok(f'{path}  {output.GLYPHS.arrow.right}  version = "{new_version}"'))


def replace_toml_field(text: str, new_version: str, *, section: str, field: str) -> str:
    """Replace a TOML field inside a named section."""
    field_pattern = rf'(?ms)(^\[{re.escape(section)}\]\s*$.*?^{re.escape(field)}\s*=\s*")([^"]+)(")'
    pattern = re.compile(field_pattern)
    return pattern.sub(rf"\g<1>{new_version}\g<3>", text, count=1)


def read_current_version(config: RrtConfig) -> Version:
    """Read the current version from the first target."""
    primary = config.version_targets[0]
    text = primary.path.read_text(encoding="utf-8")

    if primary.kind == "pep621":
        match = PEP621_PATTERN.search(text)
        if match is None:
            raise RuntimeError(f"Could not find [project].version in {primary.path}")
        return Version.parse(match.group(2))

    if primary.pattern:
        match = re.compile(primary.pattern, re.MULTILINE).search(text)
        if match is None:
            raise RuntimeError(f"Could not match configured pattern in {primary.path}")
        return Version.parse(match.group(2))

    value = read_toml_field(primary.path, section=primary.section or "", field=primary.field or "")
    return Version.parse(value)


def read_toml_field(path: Path, *, section: str, field: str) -> str:
    """Read a field from a TOML file using a dotted section name."""
    with path.open("rb") as handle:
        data = tomllib.load(handle)

    current: object = data
    for part in section.split("."):
        if not isinstance(current, dict) or part not in current:
            raise RuntimeError(f"Missing section [{section}] in {path}")
        current = current[part]

    if not isinstance(current, dict) or field not in current:
        raise RuntimeError(f"Missing field {field!r} in section [{section}] of {path}")
    value = current[field]
    if not isinstance(value, str):
        raise RuntimeError(f"Field {field!r} in [{section}] of {path} is not a string")
    return value


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
        config = load_config(root)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    current = read_current_version(config)
    if args.bump in {"major", "minor", "patch"}:
        new = current.bump(args.bump)
    else:
        try:
            new = Version.parse(args.bump)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1

    branch_name = config.release_branch.format(version=new)
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
    for target in config.version_targets:
        replace_version_in_file(target, str(new), dry_run=args.dry_run)

    if not args.no_changelog:
        print(f"\n{output.section('Updating changelog')}")
        update_changelog(
            config,
            str(new),
            include_maintenance=args.include_maintenance,
            dry_run=args.dry_run,
        )

    if config.lock_command:
        print(f"\n{output.section('Refreshing lockfiles')}")
        git.run(config.lock_command, root, dry_run=args.dry_run, label="lock command")

    print(f"\n{output.section('Git')}")
    git.run(
        ["git", "checkout", "-b", branch_name], root, dry_run=args.dry_run, label="git checkout -b"
    )

    files_to_stage = [str(target.path.relative_to(root)) for target in config.version_targets]
    lockfile = root / "uv.lock"
    if lockfile.exists():
        files_to_stage.append(str(lockfile.relative_to(root)))
    if config.changelog_file.exists() and not args.no_changelog:
        files_to_stage.append(str(config.changelog_file.relative_to(root)))
    git.run(["git", "add", *files_to_stage], root, dry_run=args.dry_run, label="git add")

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
    parser.set_defaults(handler=cmd_bump)
