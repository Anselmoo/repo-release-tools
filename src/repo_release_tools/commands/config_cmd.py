"""rrt config — visualise the resolved rrt configuration for the current repository."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from repo_release_tools import config as cfg
from repo_release_tools.ui import (
    DryRunPrinter,
    GLYPHS,
    highlight_terminal,
)


def _render_group_details(group: cfg.VersionGroup, root: Path) -> list[str]:
    """Render the text lines for a version-group detail block."""
    g = GLYPHS
    details: list[str] = [
        f"  {g.bullet.dot} release_branch: {group.release_branch}",
        f"  {g.bullet.dot} changelog: {group.changelog_file.relative_to(root)}",
    ]
    if group.lock_command:
        details.append(f"  {g.bullet.dot} lock_command: {' '.join(group.lock_command)}")
    if group.generated_files:
        details.append(f"  {g.bullet.dot} generated_files:")
        for generated_file in group.generated_files:
            details.append(f"    {g.arrow.right} {generated_file.relative_to(root)}")
    details.append(f"  {g.bullet.dot} version_targets:")
    for target in group.version_targets:
        details.append(f"    {g.arrow.right} {cfg._describe_version_target(target, root=root)}")
    return details


def cmd_config(args: argparse.Namespace) -> int:
    """Print the resolved rrt config as a tree."""
    root = Path.cwd()

    try:
        conf = cfg.load_or_autodetect_config(root)
    except FileNotFoundError:
        checked = cfg.iter_config_files(root)
        p = DryRunPrinter(False)
        p.line(cfg.format_missing_tool_rrt_guidance(root, checked), ok=False, stream=sys.stderr)
        return 1
    except (ValueError, cfg.MissingRrtConfigError) as exc:
        p = DryRunPrinter(False)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1

    # --raw: syntax-highlighted view of the raw config file
    if getattr(args, "raw", False):
        config_path = conf.config_file
        try:
            raw_text = config_path.read_text(encoding="utf-8")
        except OSError as exc:
            p = DryRunPrinter(False)
            p.line(str(exc), ok=False, stream=sys.stderr)
            return 1
        lang = "toml" if config_path.suffix in {".toml"} else "text"
        # raw display: write highlighted text directly to stdout
        sys.stdout.write(highlight_terminal(raw_text, lang) + "\n")
        return 0

    source = "(auto-detected)" if conf.autodetected else str(conf.config_file.relative_to(root))
    group_count = len(conf.version_groups)
    plural = "group" if group_count == 1 else "groups"

    p = DryRunPrinter(False)
    p.line("rrt config", ok=True)
    p.meta("Config file", source)
    p.meta("Version groups", f"{group_count} {plural}")
    p.blank_line()

    p.section("Version groups")
    for group in conf.version_groups:
        p.ok(f"[{group.name}]")
        for detail_line in _render_group_details(group, root):
            p.line(detail_line)
        p.blank_line()
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the config command."""
    parser = subparsers.add_parser(
        "config",
        help="Show the resolved rrt configuration for this repository.",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        default=False,
        help="Show the raw config file with syntax highlighting instead of the tree view.",
    )
    parser.set_defaults(handler=cmd_config)
