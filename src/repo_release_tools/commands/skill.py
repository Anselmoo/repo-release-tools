"""Install bundled rrt user workflow skills.

## Overview

`rrt skill` manages installation of the packaged user-facing `rrt` skills into
tool-specific skill directories. The only implemented subcommand is `install`.

This repository bundles ten user workflow skills:
- `rrt-user-bootstrap`
- `rrt-user-versioning`
- `rrt-user-release-flow`
- `rrt-user-branch-strategy`
- `rrt-user-commit-quality`
- `rrt-user-changelog-automation`
- `rrt-user-docs-consistency`
- `rrt-user-config-safety`
- `rrt-user-ci-readiness`
- `rrt-user-migration-uvx-to-installed`

## Target surfaces

The install command can write to local or global skill roots for:

- Claude: `.claude/skills`
- Codex: `.codex/skills`
- Copilot: `.github/skills` (local), `~/.copilot/skills` (global)
- Gemini: `.gemini/skills`

Each target receives one directory per bundled skill, each containing a
`SKILL.md`.

## Behavior

- Accepts one or more `--target` values; duplicates are ignored after first use.
- Resolves local targets relative to the current working directory and global
  targets relative to the home directory.
- Refuses to overwrite an existing skill directory unless `--force` is provided.
- Supports `--dry-run` previews that show the resolved destination paths
  without writing files.

## Examples

- `rrt skill install --target copilot-local`
- `rrt skill install --target claude-local --target codex-local`
- `rrt skill install --target gemini-local`
- `rrt skill install --target copilot-global --force --dry-run`

## Caveats

- `rrt skill` requires a subcommand; use `rrt skill install ...`.
- Without `--target`, the command prints available destinations in dry-run
  mode and otherwise fails.
- Existing symlinks, files, or directories at the destination are replaced
  only when `--force` is used.
"""

from __future__ import annotations

import argparse
import contextlib
import shutil
import sys
from collections.abc import Iterable
from pathlib import Path

from repo_release_tools.integrations.skill_assets import BUNDLED_SKILLS
from repo_release_tools.ui import DryRunPrinter

TARGET_PATHS = {
    "claude-global": lambda cwd, home: home / ".claude" / "skills",
    "claude-local": lambda cwd, home: cwd / ".claude" / "skills",
    "codex-global": lambda cwd, home: home / ".codex" / "skills",
    "codex-local": lambda cwd, home: cwd / ".codex" / "skills",
    "copilot-global": lambda cwd, home: home / ".copilot" / "skills",
    "copilot-local": lambda cwd, home: cwd / ".github" / "skills",
    "gemini-global": lambda cwd, home: home / ".gemini" / "skills",
    "gemini-local": lambda cwd, home: cwd / ".gemini" / "skills",
}


SKILL_EXAMPLES = (
    "  $ rrt skill install --target copilot-local\n"
    "  $ rrt skill install --target claude-local --target codex-local\n"
    "  $ rrt skill install --target gemini-local"
)

SKILL_INSTALL_EXAMPLES = (
    "  $ rrt skill install --target copilot-local\n"
    "  $ rrt skill install --target claude-local --target codex-local\n"
    "  $ rrt skill install --target copilot-global --force --dry-run\n"
    "  $ rrt skill install --target gemini-global"
)

# Ordered source-owned topic docs for docs generation.
SOURCE_OWNED_TOPIC_DOCS: tuple[tuple[str, str], ...] = (("skill", __doc__ or ""),)


def _dedupe_targets(targets: Iterable[str]) -> list[str]:
    """Return targets in first-seen order without duplicates."""
    seen: set[str] = set()
    ordered: list[str] = []
    for target in targets:
        if target in seen:
            continue
        seen.add(target)
        ordered.append(target)
    return ordered


def _display_path(path: Path, *, cwd: Path, home: Path) -> str:
    """Render *path* relative to cwd or home when possible."""
    with contextlib.suppress(ValueError):
        return str(path.relative_to(cwd))
    with contextlib.suppress(ValueError):
        return f"~/{path.relative_to(home)}"
    return str(path)


def _emit_install_error(message: str) -> int:
    p = DryRunPrinter(False)
    p.line(message, ok=False, stream=sys.stderr)
    return 1


def _resolve_install_plan(targets: list[str], *, cwd: Path, home: Path) -> list[tuple[str, Path]]:
    """Resolve target names into base skill directories."""
    return [(target, TARGET_PATHS[target](cwd, home)) for target in _dedupe_targets(targets)]


def _show_available_install_targets(*, cwd: Path, home: Path) -> None:
    p = DryRunPrinter(True)
    p.blank_line()
    p.header("Skill install", Skills=str(len(BUNDLED_SKILLS)))
    p.section("Available targets")
    for target_name, resolver in sorted(TARGET_PATHS.items()):
        for skill in BUNDLED_SKILLS:
            location = _display_path(
                resolver(cwd, home) / skill.name / "SKILL.md",
                cwd=cwd,
                home=home,
            )
            p.would_install(skill.name, target_name, location)
    p.blank_line()
    p.footer("pass --target DEST to install (see targets above)")


def cmd_install(args: argparse.Namespace) -> int:
    """Install the bundled rrt user skills into one or more agent skill dirs."""
    verbose: int = getattr(args, "verbose", 0) or 0
    cwd = Path.cwd()
    home = Path.home()
    if not args.targets:
        if args.dry_run:
            _show_available_install_targets(cwd=cwd, home=home)
            return 0
        available = ", ".join(sorted(TARGET_PATHS))
        return _emit_install_error(
            f"No --target specified. Pass --target DEST (e.g. --target claude-local). Available: {available}.",
        )

    install_plan = _resolve_install_plan(args.targets, cwd=cwd, home=home)

    p = DryRunPrinter(args.dry_run, verbose=verbose)
    p.blank_line()
    p.header(
        "Skill install",
        Skills=str(len(BUNDLED_SKILLS)),
        Targets=str(len(install_plan)),
    )

    conflicts: list[tuple[str, str, Path]] = []
    for target_name, skills_dir in install_plan:
        for skill in BUNDLED_SKILLS:
            destination = skills_dir / skill.name
            if destination.exists() and not args.force:
                conflicts.append((target_name, skill.name, destination))

    if conflicts:
        for target_name, skill_name, destination in conflicts:
            location = _display_path(destination, cwd=cwd, home=home)
            return _emit_install_error(
                f"{target_name} already has {skill_name} at {location}. Use --force to overwrite it.",
            )

    if args.dry_run:
        for target_name, skills_dir in install_plan:
            for skill in BUNDLED_SKILLS:
                destination = skills_dir / skill.name / "SKILL.md"
                location = _display_path(destination, cwd=cwd, home=home)
                p.would_install(skill.name, target_name, location)
        p.blank_line()
        p.footer("no files were modified")
        return 0

    for target_name, skills_dir in install_plan:
        for skill in BUNDLED_SKILLS:
            destination_dir = skills_dir / skill.name
            destination_file = destination_dir / "SKILL.md"
            try:
                if destination_dir.is_symlink() or destination_dir.is_file():
                    destination_dir.unlink()
                elif destination_dir.exists():
                    shutil.rmtree(destination_dir)
                destination_dir.mkdir(parents=True, exist_ok=True)
                destination_file.write_text(skill.markdown.rstrip() + "\n", encoding="utf-8")
            except OSError as exc:
                location = _display_path(destination_file, cwd=cwd, home=home)
                return _emit_install_error(
                    f"Could not install {skill.name} to {target_name} ({location}): {exc}",
                )
            location = _display_path(destination_file, cwd=cwd, home=home)
            p.ok(f"Installed {skill.name} to {target_name}: {location}")
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the skill command group."""
    parser = subparsers.add_parser(
        "skill",
        help="Install bundled rrt user workflow skills.",
        description="Install the bundled rrt user workflow skills.",
        epilog=SKILL_EXAMPLES,
    )
    skill_sub = parser.add_subparsers(
        dest="skill_command",
        metavar="<skill_command>",
        parser_class=type(parser),
        required=True,
    )

    install_parser = skill_sub.add_parser(
        "install",
        help="Install bundled rrt user skills into agent skill directories.",
        description="Install the bundled rrt user skills into one or more local or global agent skill directories.",
        epilog=SKILL_INSTALL_EXAMPLES,
    )
    install_parser.add_argument(
        "--target",
        dest="targets",
        action="append",
        required=False,
        choices=sorted(TARGET_PATHS),
        metavar="DEST",
        help=(
            "Install target. Repeat to install into multiple locations: "
            "copilot-local, claude-local, codex-local, gemini-local, "
            "copilot-global, claude-global, codex-global, gemini-global."
        ),
    )
    install_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing files.",
    )
    install_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing installed skill directories.",
    )
    install_parser.set_defaults(handler=cmd_install)
