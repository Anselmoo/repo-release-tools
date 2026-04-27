"""rrt config — visualise the resolved rrt configuration for the current repository."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from repo_release_tools import config as cfg, output
from repo_release_tools.ui.glyphs import display_width, pad_right


def _render_group_detail_rows(
    details: list[tuple[str, str]],
) -> list[tuple[str, bool, list | None]]:
    """Render aligned key/value lines for a version-group tree node."""
    key_width = max(display_width(key) for key, _ in details)
    return [(f"{pad_right(key, key_width)}  {value}", False, None) for key, value in details]


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

    # --raw: syntax-highlighted view of the raw config file
    if getattr(args, "raw", False):
        config_path = conf.config_file
        try:
            raw_text = config_path.read_text(encoding="utf-8")
        except OSError as exc:
            print(output.error(str(exc)), file=sys.stderr)
            return 1
        lang = "toml" if config_path.suffix in {".toml"} else "text"
        print(output.highlight_terminal(raw_text, lang))
        return 0

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
            expand=True,
            title_mode="row",
        )
    )
    print()

    print("Version groups")
    print(output.rule())

    # Tree: one branch per version group
    tree_entries: list[tuple[str, bool, list | None]] = []
    for group in conf.version_groups:
        detail_rows = [
            ("release_branch", group.release_branch),
            ("changelog", str(group.changelog_file.relative_to(root))),
        ]

        if group.lock_command:
            detail_rows.append(("lock_command", " ".join(group.lock_command)))

        children = _render_group_detail_rows(detail_rows)

        # Version targets
        target_children: list[tuple[str, bool, list | None]] = [
            (cfg._describe_version_target(t, root=root), False, None) for t in group.version_targets
        ]
        children.append(("version_targets", True, target_children or None))

        # Generated files (only when present)
        if group.generated_files:
            gen_children: list[tuple[str, bool, list | None]] = [
                (str(f.relative_to(root)), False, None) for f in group.generated_files
            ]
            children.append(("generated_files", True, gen_children))

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
    parser.add_argument(
        "--raw",
        action="store_true",
        default=False,
        help="Show the raw config file with syntax highlighting instead of the tree view.",
    )
    parser.set_defaults(handler=cmd_config)
