"""Install bundled rrt user agent definitions (.agent.md files).

## Overview

`rrt agents` manages installation of the packaged user-facing agent definitions
into tool-specific agent directories. The only implemented subcommand is `install`.

## Target surfaces

The install command can write to local or global agent roots for:

- Claude: `.claude/agents`
- Codex: `.codex/agents`
- Copilot: `.github/agents` (local), `~/.copilot/agents` (global)
- Gemini: `.gemini/agents`

Each target receives one flat `.agent.md` file per bundled user agent.

## Behavior

- Accepts one or more `--target` values; duplicates are ignored after first use.
- Resolves local targets relative to the current working directory and global
  targets relative to the home directory.
- Refuses to overwrite an existing file unless `--force` is provided.
- Supports `--dry-run` previews that show the resolved destination paths
  without writing files.

## Examples

- `rrt agents install --target claude-local`
- `rrt agents install --target claude-local --target codex-local`
- `rrt agents install --target claude-global --force`
- `rrt agents install --dry-run`

## Caveats

- `rrt agents` requires a subcommand; use `rrt agents install ...`.
- Without `--target`, the command prints available destinations in dry-run
  mode and otherwise fails.
- Existing files at the destination are replaced only when `--force` is used.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from collections.abc import Iterable
from pathlib import Path

from repo_release_tools.integrations.agent_assets import BUNDLED_AGENTS, BundledAgent
from repo_release_tools.ui import DryRunPrinter

AGENT_TARGET_PATHS = {
    "claude-global": lambda cwd, home: home / ".claude" / "agents",
    "claude-local": lambda cwd, home: cwd / ".claude" / "agents",
    "codex-global": lambda cwd, home: home / ".codex" / "agents",
    "codex-local": lambda cwd, home: cwd / ".codex" / "agents",
    "copilot-global": lambda cwd, home: home / ".copilot" / "agents",
    "copilot-local": lambda cwd, home: cwd / ".github" / "agents",
    "gemini-global": lambda cwd, home: home / ".gemini" / "agents",
    "gemini-local": lambda cwd, home: cwd / ".gemini" / "agents",
}

AGENTS_EXAMPLES = (
    "  $ rrt agents install --target claude-local\n"
    "  $ rrt agents install --target claude-local --target codex-local\n"
    "  $ rrt agents install --target copilot-local\n"
    "  $ rrt agents install --target claude-global --force"
)

AGENTS_INSTALL_EXAMPLES = (
    "  $ rrt agents install --target claude-local\n"
    "  $ rrt agents install --target claude-local --target codex-local\n"
    "  $ rrt agents install --target gemini-local\n"
    "  $ rrt agents install --target claude-global --force --dry-run\n"
    "  $ rrt agents install --target copilot-global"
)


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
    """Resolve target names into base agent directories."""
    return [(target, AGENT_TARGET_PATHS[target](cwd, home)) for target in _dedupe_targets(targets)]


def _show_available_install_targets(*, cwd: Path, home: Path) -> None:
    p = DryRunPrinter(True)
    p.blank_line()
    p.header("Agent install", Agents=str(len(BUNDLED_AGENTS)))
    p.section("Available targets")
    for target_name, resolver in sorted(AGENT_TARGET_PATHS.items()):
        for agent in BUNDLED_AGENTS:
            location = _display_path(
                resolver(cwd, home) / f"{agent.name}.agent.md",
                cwd=cwd,
                home=home,
            )
            p.would_install(agent.name, target_name, location)
    p.blank_line()
    p.footer("pass --target DEST to install (see targets above)")


def cmd_install(args: argparse.Namespace) -> int:
    """Install bundled user agents into one or more agent directories.

    Supports optional --agent/--agents to request installation of a single
    agent by name. When the requested agent declares a `family:` metadata key,
    the entire family is installed instead.
    """
    verbose: int = getattr(args, "verbose", 0) or 0
    cwd = Path.cwd()
    home = Path.home()
    if not args.targets:
        if args.dry_run:
            _show_available_install_targets(cwd=cwd, home=home)
            return 0
        available = ", ".join(sorted(AGENT_TARGET_PATHS))
        return _emit_install_error(
            f"No --target specified. Pass --target DEST (e.g. --target claude-local). Available: {available}.",
        )

    install_plan = _resolve_install_plan(args.targets, cwd=cwd, home=home)

    # Determine selected agents based on optional --agent flags.
    selected_agents = list(BUNDLED_AGENTS)
    if getattr(args, "agents", None):
        requested_names = args.agents
        # Build an ordered, deduplicated selection preserving the canonical order.
        requested_set: set[str] = set()
        interim: list[BundledAgent] = []
        for name in requested_names:
            match = next((a for a in BUNDLED_AGENTS if a.name == name), None)
            if match is None:
                return _emit_install_error(
                    f"Unknown agent: {name}. Available: {', '.join(a.name for a in BUNDLED_AGENTS)}"
                )
            if match.family:
                interim.extend([a for a in BUNDLED_AGENTS if a.family == match.family])
            else:
                interim.append(match)
        ordered: list[BundledAgent] = []
        for a in BUNDLED_AGENTS:
            if a in interim and a.name not in requested_set:
                ordered.append(a)
                requested_set.add(a.name)
        selected_agents = ordered

    p = DryRunPrinter(args.dry_run, verbose=verbose)
    p.blank_line()
    p.header(
        "Agent install",
        Agents=str(len(selected_agents)),
        Targets=str(len(install_plan)),
    )

    conflicts: list[tuple[str, str, Path]] = []
    for target_name, agents_dir in install_plan:
        for agent in selected_agents:
            destination = agents_dir / f"{agent.name}.agent.md"
            if destination.exists() and not args.force:
                conflicts.append((target_name, agent.name, destination))

    if conflicts:
        for target_name, agent_name, destination in conflicts:
            location = _display_path(destination, cwd=cwd, home=home)
            return _emit_install_error(
                f"{target_name} already has {agent_name} at {location}. Use --force to overwrite it.",
            )

    if args.dry_run:
        for target_name, agents_dir in install_plan:
            for agent in selected_agents:
                destination = agents_dir / f"{agent.name}.agent.md"
                location = _display_path(destination, cwd=cwd, home=home)
                p.would_install(agent.name, target_name, location)
        p.blank_line()
        p.footer("no files were modified")
        return 0

    for target_name, agents_dir in install_plan:
        agents_dir.mkdir(parents=True, exist_ok=True)
        for agent in selected_agents:
            destination = agents_dir / f"{agent.name}.agent.md"
            try:
                destination.write_text(agent.markdown.rstrip() + "\n", encoding="utf-8")
            except OSError as exc:
                location = _display_path(destination, cwd=cwd, home=home)
                return _emit_install_error(
                    f"Could not install {agent.name} to {target_name} ({location}): {exc}",
                )
            location = _display_path(destination, cwd=cwd, home=home)
            p.ok(f"Installed {agent.name} to {target_name}: {location}")
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the agents command group."""
    parser = subparsers.add_parser(
        "agents",
        help="Install bundled rrt user agents into agent directories.",
        description="Install bundled rrt user agents into one or more local or global agent directories.",
        epilog=AGENTS_EXAMPLES,
    )
    agents_sub = parser.add_subparsers(
        dest="agents_command",
        metavar="<agents_command>",
        parser_class=type(parser),
        required=True,
    )

    install_parser = agents_sub.add_parser(
        "install",
        help="Install bundled rrt user agents into agent directories.",
        description="Install bundled .agent.md user agents into one or more local or global agent directories.",
        epilog=AGENTS_INSTALL_EXAMPLES,
    )
    install_parser.add_argument(
        "--target",
        dest="targets",
        action="append",
        required=False,
        choices=sorted(AGENT_TARGET_PATHS),
        metavar="DEST",
        help=(
            "Install target. Repeat to install into multiple locations: "
            "claude-local, claude-global, codex-local, codex-global, "
            "copilot-local, copilot-global, gemini-local, gemini-global."
        ),
    )
    install_parser.add_argument(
        "--agent",
        dest="agents",
        action="append",
        required=False,
        metavar="AGENT",
        help=(
            "Install a specific agent by name. When the agent declares a `family:` metadata, "
            "the entire family will be installed. Repeat for multiple agents."
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
        help="Overwrite existing agent files.",
    )
    install_parser.set_defaults(handler=cmd_install)


def main() -> None:
    """Entry point for the rrt-agents standalone CLI."""
    parser = argparse.ArgumentParser(
        prog="rrt-agents",
        description="Install bundled rrt user agents into agent directories.",
        epilog=AGENTS_EXAMPLES,
    )
    sub = parser.add_subparsers(
        dest="agents_command",
        metavar="<command>",
        required=True,
    )
    install_parser = sub.add_parser(
        "install",
        help="Install bundled rrt user agents into agent directories.",
        description="Install bundled .agent.md user agents into one or more local or global agent directories.",
        epilog=AGENTS_INSTALL_EXAMPLES,
    )
    install_parser.add_argument(
        "--target",
        dest="targets",
        action="append",
        required=False,
        choices=sorted(AGENT_TARGET_PATHS),
        metavar="DEST",
        help=(
            "Install target. Repeat to install into multiple locations: "
            "claude-local, claude-global, codex-local, codex-global, "
            "copilot-local, copilot-global, gemini-local, gemini-global."
        ),
    )
    install_parser.add_argument(
        "--agent",
        dest="agents",
        action="append",
        required=False,
        metavar="AGENT",
        help=(
            "Install a specific agent by name. When the agent declares a `family:` metadata, "
            "the entire family will be installed. Repeat for multiple agents."
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
        help="Overwrite existing agent files.",
    )
    install_parser.set_defaults(handler=cmd_install)
    args = parser.parse_args()
    sys.exit(args.handler(args))
