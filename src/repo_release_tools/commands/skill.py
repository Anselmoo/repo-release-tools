"""Skill installation commands."""

from __future__ import annotations

import argparse
import shutil
import sys

from collections.abc import Iterable
from pathlib import Path

from repo_release_tools import output
from repo_release_tools.skill_assets import INSTALLED_CLI_SKILL


TARGET_PATHS = {
    "claude-global": lambda cwd, home: home / ".claude" / "skills",
    "claude-local": lambda cwd, home: cwd / ".claude" / "skills",
    "codex-global": lambda cwd, home: home / ".codex" / "skills",
    "codex-local": lambda cwd, home: cwd / ".codex" / "skills",
    "copilot-global": lambda cwd, home: home / ".copilot" / "skills",
    "copilot-local": lambda cwd, home: cwd / ".copilot" / "skills",
}


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
    try:
        return str(path.relative_to(cwd))
    except ValueError:
        pass
    try:
        return f"~/{path.relative_to(home)}"
    except ValueError:
        return str(path)


def _resolve_install_plan(targets: list[str], *, cwd: Path, home: Path) -> list[tuple[str, Path]]:
    """Resolve target names into base skill directories."""
    return [(target, TARGET_PATHS[target](cwd, home)) for target in _dedupe_targets(targets)]


def cmd_install(args: argparse.Namespace) -> int:
    """Install the bundled repo-release-tools skill into one or more agent skill dirs."""
    cwd = Path.cwd()
    home = Path.home()
    install_plan = _resolve_install_plan(args.targets, cwd=cwd, home=home)

    print()
    print(
        output.panel(
            "[DRY RUN] Skill install" if args.dry_run else "Skill install",
            [
                ("Skill", INSTALLED_CLI_SKILL.name),
                ("Targets", str(len(install_plan))),
            ],
        )
    )
    print()

    conflicts: list[tuple[str, Path]] = []
    for target_name, skills_dir in install_plan:
        destination = skills_dir / INSTALLED_CLI_SKILL.name
        if destination.exists() and not args.force:
            conflicts.append((target_name, destination))

    if conflicts:
        for target_name, destination in conflicts:
            location = _display_path(destination, cwd=cwd, home=home)
            print(
                f"{target_name} already has {INSTALLED_CLI_SKILL.name} at {location}. "
                "Use --force to overwrite it.",
                file=sys.stderr,
            )
        return 1

    if args.dry_run:
        for target_name, skills_dir in install_plan:
            destination = skills_dir / INSTALLED_CLI_SKILL.name / "SKILL.md"
            location = _display_path(destination, cwd=cwd, home=home)
            print(
                output.dry_run(
                    f"Would install {INSTALLED_CLI_SKILL.name} to {target_name}: {location}"
                )
            )
        print()
        print(output.dry_run_complete("no files were modified"))
        return 0

    for target_name, skills_dir in install_plan:
        destination_dir = skills_dir / INSTALLED_CLI_SKILL.name
        destination_file = destination_dir / "SKILL.md"
        try:
            if destination_dir.exists():
                shutil.rmtree(destination_dir)
            destination_dir.mkdir(parents=True, exist_ok=True)
            destination_file.write_text(
                INSTALLED_CLI_SKILL.markdown.rstrip() + "\n", encoding="utf-8"
            )
        except OSError as exc:
            location = _display_path(destination_file, cwd=cwd, home=home)
            print(
                output.warning(
                    f"Could not install {INSTALLED_CLI_SKILL.name} to {target_name} ({location}): {exc}"
                ),
                file=sys.stderr,
            )
            return 1
        location = _display_path(destination_file, cwd=cwd, home=home)
        print(output.ok(f"Installed {INSTALLED_CLI_SKILL.name} to {target_name}: {location}"))
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the skill command group."""
    parser = subparsers.add_parser(
        "skill",
        help="Install the bundled repo-release-tools agent skill.",
    )
    skill_sub = parser.add_subparsers(dest="skill_command", required=True)

    install_parser = skill_sub.add_parser(
        "install",
        help="Install the bundled repo-release-tools skill into agent skill directories.",
    )
    install_parser.add_argument(
        "--target",
        dest="targets",
        action="append",
        required=True,
        choices=sorted(TARGET_PATHS),
        metavar="DEST",
        help=(
            "Install target. Repeat to install into multiple locations: "
            "copilot-local, claude-local, codex-local, copilot-global, claude-global, codex-global."
        ),
    )
    install_parser.add_argument(
        "--dry-run", action="store_true", help="Preview without writing files."
    )
    install_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing installed repo-release-tools skill.",
    )
    install_parser.set_defaults(handler=cmd_install)
