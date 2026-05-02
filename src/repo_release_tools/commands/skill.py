"""Install the bundled repo-release-tools agent skill.

## Overview

`rrt skill` manages installation of the packaged `repo-release-tools` skill
into tool-specific skill directories. The only implemented subcommand is
`install`.

## Target surfaces

The install command can write to local or global skill roots for:

- Claude: `.claude/skills`
- Codex: `.codex/skills`
- Copilot: `.copilot/skills`

Each target receives a directory named after the bundled skill, containing
`SKILL.md`.

## Behavior

- Accepts one or more `--target` values; duplicates are ignored after first use.
- Resolves local targets relative to the current working directory and global
  targets relative to the home directory.
- Refuses to overwrite an existing installation unless `--force` is provided.
- Supports `--dry-run` previews that show the resolved destination paths
  without writing files.

## Examples

- `rrt skill install --target copilot-local`
- `rrt skill install --target claude-local --target codex-local`
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
import shutil
import sys
from collections.abc import Iterable
from pathlib import Path

from repo_release_tools.skill_assets import INSTALLED_CLI_SKILL
from repo_release_tools.ui import DryRunPrinter

TARGET_PATHS = {
    "claude-global": lambda cwd, home: home / ".claude" / "skills",
    "claude-local": lambda cwd, home: cwd / ".claude" / "skills",
    "codex-global": lambda cwd, home: home / ".codex" / "skills",
    "codex-local": lambda cwd, home: cwd / ".codex" / "skills",
    "copilot-global": lambda cwd, home: home / ".copilot" / "skills",
    "copilot-local": lambda cwd, home: cwd / ".copilot" / "skills",
}


SKILL_EXAMPLES = (
    "  $ rrt skill install --target copilot-local\n"
    "  $ rrt skill install --target claude-local --target codex-local"
)

SKILL_INSTALL_EXAMPLES = (
    "  $ rrt skill install --target copilot-local\n"
    "  $ rrt skill install --target claude-local --target codex-local\n"
    "  $ rrt skill install --target copilot-global --force --dry-run"
)

SKILLS_DOC = """# Skills

This repository bundles two agent skills:

- `/.github/skills/repo-release-tools-uvx/SKILL.md` — zero-install guidance
- `/.github/skills/repo-release-tools/SKILL.md` — guidance for an installed `rrt`

If you need the exact CLI syntax for branch, Git, or skill commands, use the
[RRT CLI reference](rrt-cli.md) first.

## Which skill to use

### `repo-release-tools-uvx`

Use this when `repo-release-tools` is not installed and you want quick
`uvx`-based usage examples for branches, bumps, or one-off release automation.

### `repo-release-tools`

Use this when `rrt` is already available and you want help with:

- `rrt branch ...` naming and branch repair
- `rrt bump ...` release versioning
- `rrt git ...` workflow helpers
- `rrt doctor` / `rrt config`
- `rrt skill install ...`
- hook and CI workflow guidance that points back to the main docs

## Installing the bundled CLI skill

Install into one or more agent skill locations with:

```bash
rrt skill install --target copilot-local
rrt skill install --target claude-local --target codex-local
rrt skill install --target copilot-global --dry-run
rrt skill install --target codex-global --force
```

Supported targets:

| Target | Directory |
|---|---|
| `copilot-local` | `.copilot/skills` |
| `claude-local` | `.claude/skills` |
| `codex-local` | `.codex/skills` |
| `copilot-global` | `~/.copilot/skills` |
| `claude-global` | `~/.claude/skills` |
| `codex-global` | `~/.codex/skills` |

The installer refuses to overwrite an existing skill unless you pass `--force`.
Use `--dry-run` to preview the destination paths first.

## Related docs

- [RRT CLI](rrt-cli.md)
- [pre-commit / lefthook](pre-commit.md)
- [GitHub Action](github-action.md)
- [Git magic](git-magic.md)

## Skill eval fixtures

Keep the canonical skill eval prompts in `/evals/evals.json`.

Structured workspace artifacts under
`.github/skills/repo-release-tools-workspace/` may be committed as evidence of an
evaluation run. Do **not** commit ad-hoc execution transcripts
(`transcript.md`).
"""

# Ordered source-owned topic docs for docs generation.
SOURCE_OWNED_TOPIC_DOCS: tuple[tuple[str, str], ...] = (("skill", SKILLS_DOC),)


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
    if not args.targets:
        if args.dry_run:
            p = DryRunPrinter(True)
            p.blank_line()
            p.header("Skill install", Skill=INSTALLED_CLI_SKILL.name)
            p.section("Available targets")
            for target_name, resolver in sorted(TARGET_PATHS.items()):
                location = _display_path(
                    resolver(cwd, home) / INSTALLED_CLI_SKILL.name / "SKILL.md", cwd=cwd, home=home
                )
                p.would_install(INSTALLED_CLI_SKILL.name, target_name, location)
            p.blank_line()
            p.footer("pass --target DEST to install (see targets above)")
            return 0
        available = ", ".join(sorted(TARGET_PATHS))
        p = DryRunPrinter(False)
        p.line(
            f"No --target specified. Pass --target DEST (e.g. --target claude-local). Available: {available}.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    install_plan = _resolve_install_plan(args.targets, cwd=cwd, home=home)

    p = DryRunPrinter(args.dry_run)
    p.blank_line()
    p.header(
        "Skill install",
        Skill=INSTALLED_CLI_SKILL.name,
        Targets=str(len(install_plan)),
    )

    conflicts: list[tuple[str, Path]] = []
    for target_name, skills_dir in install_plan:
        destination = skills_dir / INSTALLED_CLI_SKILL.name
        if destination.exists() and not args.force:
            conflicts.append((target_name, destination))

    if conflicts:
        for target_name, destination in conflicts:
            location = _display_path(destination, cwd=cwd, home=home)
            p = DryRunPrinter(False)
            p.line(
                f"{target_name} already has {INSTALLED_CLI_SKILL.name} at {location}. Use --force to overwrite it.",
                ok=False,
                stream=sys.stderr,
            )
        return 1

    if args.dry_run:
        for target_name, skills_dir in install_plan:
            destination = skills_dir / INSTALLED_CLI_SKILL.name / "SKILL.md"
            location = _display_path(destination, cwd=cwd, home=home)
            p.would_install(INSTALLED_CLI_SKILL.name, target_name, location)
        p.blank_line()
        p.footer("no files were modified")
        return 0

    for target_name, skills_dir in install_plan:
        destination_dir = skills_dir / INSTALLED_CLI_SKILL.name
        destination_file = destination_dir / "SKILL.md"
        try:
            if destination_dir.is_symlink() or destination_dir.is_file():
                destination_dir.unlink()
            elif destination_dir.exists():
                shutil.rmtree(destination_dir)
            destination_dir.mkdir(parents=True, exist_ok=True)
            destination_file.write_text(
                INSTALLED_CLI_SKILL.markdown.rstrip() + "\n", encoding="utf-8"
            )
        except OSError as exc:
            location = _display_path(destination_file, cwd=cwd, home=home)
            p = DryRunPrinter(False)
            p.line(
                f"Could not install {INSTALLED_CLI_SKILL.name} to {target_name} ({location}): {exc}",
                ok=False,
                stream=sys.stderr,
            )
            return 1
        location = _display_path(destination_file, cwd=cwd, home=home)
        p.ok(f"Installed {INSTALLED_CLI_SKILL.name} to {target_name}: {location}")
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the skill command group."""
    parser = subparsers.add_parser(
        "skill",
        help="Install the bundled repo-release-tools agent skill.",
        description="Install the bundled repo-release-tools agent skill.",
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
        help="Install the bundled repo-release-tools skill into agent skill directories.",
        description="Install the bundled repo-release-tools skill into one or more local or global agent skill directories.",
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
