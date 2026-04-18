"""rrt config — visualise the resolved rrt configuration for the current repository."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from repo_release_tools import config as cfg, output


def cmd_config(args: argparse.Namespace) -> int:
    """Print the resolved rrt config as a tree."""
    root = Path.cwd()

    try:
        conf = cfg.load_or_autodetect_config(root)
    except FileNotFoundError:
        checked = cfg.iter_config_files(root)
        print(cfg.format_missing_tool_rrt_guidance(root, checked), file=sys.stderr)
        return 1
    except (ValueError, cfg.MissingRrtConfigError) as exc:
        print(exc, file=sys.stderr)
        return 1

    # Header panel: config origin + number of groups
    source = "(auto-detected)" if conf.autodetected else str(conf.config_file.relative_to(root))
    group_count = len(conf.version_groups)
    plural = "group" if group_count == 1 else "groups"
    print(
        output.panel(
            "rrt config",
            [
                ("config file", source),
                ("version groups", f"{group_count} {plural}"),
            ],
        )
    )
    print()

    # Tree: one branch per version group
    tree_entries: list[tuple[str, bool, list | None]] = []
    for group in conf.version_groups:
        children: list[tuple[str, bool, list | None]] = [
            (f"release_branch  {group.release_branch}", False, None),
            (f"changelog       {group.changelog_file.relative_to(root)}", False, None),
        ]

        if group.lock_command:
            children.append((f"lock_command    {' '.join(group.lock_command)}", False, None))

        # Version targets
        target_children: list[tuple[str, bool, list | None]] = [
            (f"{t.path.relative_to(root)}  [{t.kind}]", False, None) for t in group.version_targets
        ]
        children.append(("version_targets/", True, target_children or None))

        # Generated files (only when present)
        if group.generated_files:
            gen_children: list[tuple[str, bool, list | None]] = [
                (str(f.relative_to(root)), False, None) for f in group.generated_files
            ]
            children.append(("generated_files/", True, gen_children))

        tree_entries.append((f"[{group.name}]", True, children))

    print(output.GLYPHS.tree.render(tree_entries))
    print()
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the config command."""
    parser = subparsers.add_parser(
        "config",
        help="Show the resolved rrt configuration for this repository.",
    )
    parser.set_defaults(handler=cmd_config)
