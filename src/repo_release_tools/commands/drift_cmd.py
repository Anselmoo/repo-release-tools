"""Lock and check agent-surface drift for repo-release-tools.

`rrt drift` tracks source-owned agent-facing files (hooks, instructions,
skills, and agent definitions) and stores hash snapshots in a lockfile under
`.rrt/`. The `generate` subcommand writes or previews lockfile updates, while
`check` validates current repository state against the lock and reports drift
with actionable follow-up guidance.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from repo_release_tools.state import (
    build_lock,
    docs_lock_path,
    hash_content,
    lock_is_current,
    write_lock,
)
from repo_release_tools.ui import DryRunPrinter

DRIFT_LOCK_EXAMPLES = "  $ rrt drift generate --dry-run\n  $ rrt drift check"
DRIFT_LOCK_FILE = "drift.lock.toml"
DRIFT_SURFACE_PATTERNS = (
    ".claude/settings.json",
    ".claude/hooks/*.py",
    ".github/agents/*.agent.md",
    ".github/copilot-instructions.md",
    ".github/instructions/*.md",
    ".github/skills/*/SKILL.md",
)


def _collect_drift_sources(root: Path) -> list[dict[str, Any]]:
    seen: set[str] = set()
    surface_paths: list[Path] = []

    for pattern in DRIFT_SURFACE_PATTERNS:
        for path in root.glob(pattern):
            if not path.is_file():
                continue
            rel = str(path.relative_to(root))
            if rel in seen:
                continue
            seen.add(rel)
            surface_paths.append(path)

    surface_paths.sort(key=lambda path: str(path.relative_to(root)))
    return [
        {
            "source_file": str(path.relative_to(root)),
            "hash": hash_content(path.read_text(encoding="utf-8")),
            "symbols": [],
            "lang": "text",
        }
        for path in surface_paths
    ]


def _lock_path(root: Path, lock_file: str) -> Path:
    return docs_lock_path(root, lock_file)


def _add_drift_lock_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--root",
        default=".",
        metavar="PATH",
        help="Repository root to scan. Defaults to the current directory.",
    )
    parser.add_argument(
        "--lock-file",
        default=DRIFT_LOCK_FILE,
        metavar="PATH",
        help="Lock file path relative to .rrt/ (default: drift.lock.toml).",
    )


def cmd_generate(args: argparse.Namespace) -> int:
    """Write the drift lockfile for agent-facing surfaces."""
    root = Path(args.root)
    sources = _collect_drift_sources(root)
    lock_data = build_lock(sources)
    lock_path = _lock_path(root, args.lock_file)

    p = DryRunPrinter(args.dry_run)
    p.blank_line()
    p.header("Drift lock", Lock=str(lock_path), Surfaces=str(len(sources)))

    if args.dry_run:
        p.would_write(str(lock_path), "drift lockfile (dry-run, not written)")
        p.footer("no files were modified")
        return 0

    write_lock(lock_path, lock_data)
    p.ok(f"Wrote {lock_path}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Verify the drift lockfile is current."""
    root = Path(args.root)
    sources = _collect_drift_sources(root)
    lock_path = _lock_path(root, args.lock_file)

    p = DryRunPrinter(False)
    is_current, messages = lock_is_current(lock_path, sources)
    if is_current:
        p.ok("drift lockfile is current")
        return 0

    p.line("drift lockfile is stale:", ok=False, stream=sys.stderr)
    for message in messages:
        p.warn(message, stream=sys.stderr)
    p.line(
        "Run 'rrt drift generate --dry-run' to preview regeneration.",
        ok=False,
        stream=sys.stderr,
    )
    return 1


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the drift command group."""
    parser = subparsers.add_parser(
        "drift",
        help="Lock and check agent-surface drift.",
        description="Lock and check the repo's agent-facing surfaces, such as Claude hooks, agent prompts, and shared skill docs.",
        epilog=DRIFT_LOCK_EXAMPLES,
    )
    drift_sub = parser.add_subparsers(
        dest="drift_command",
        metavar="<drift_command>",
        parser_class=type(parser),
        required=True,
    )

    generate_parser = drift_sub.add_parser(
        "generate",
        help="Write the drift lockfile for agent surfaces.",
        description="Write a TOML lockfile that records hashes for the configured agent-facing surfaces.",
        epilog=DRIFT_LOCK_EXAMPLES,
    )
    _add_drift_lock_arguments(generate_parser)
    generate_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing files.",
    )
    generate_parser.set_defaults(handler=cmd_generate)

    check_parser = drift_sub.add_parser(
        "check",
        help="Check whether the drift lockfile is current.",
        description="Compare the current agent-facing surfaces against the stored drift lockfile.",
        epilog=DRIFT_LOCK_EXAMPLES,
    )
    _add_drift_lock_arguments(check_parser)
    check_parser.set_defaults(handler=cmd_check)
