"""rrt config — visualise the resolved rrt configuration for the current repository."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from repo_release_tools import config as cfg, output


def _render_group_details(group: cfg.VersionGroup, root: Path) -> list[str]:
    """Render the text lines for a version-group detail block."""
    details: list[str] = [
        output.status(output.GLYPHS.bullet.dot, f"release_branch: {group.release_branch}"),
        output.status(
            output.GLYPHS.bullet.dot, f"changelog: {group.changelog_file.relative_to(root)}"
        ),
    ]
    if group.lock_command:
        details.append(
            output.status(
                output.GLYPHS.bullet.dot,
                f"lock_command: {' '.join(group.lock_command)}",
            )
        )
    if group.generated_files:
        details.append(output.status(output.GLYPHS.bullet.dot, "generated_files:"))
        for generated_file in group.generated_files:
            details.append(
                output.status(
                    output.GLYPHS.arrow.right,
                    str(generated_file.relative_to(root)),
                    indent=4,
                )
            )
    details.append(output.status(output.GLYPHS.bullet.dot, "version_targets:"))
    for target in group.version_targets:
        details.append(
            output.status(
                output.GLYPHS.arrow.right,
                cfg._describe_version_target(target, root=root),
                indent=4,
            )
        )
    return details


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

    source = "(auto-detected)" if conf.autodetected else str(conf.config_file.relative_to(root))
    group_count = len(conf.version_groups)
    plural = "group" if group_count == 1 else "groups"

    print(output.ok("rrt config"))
    print(output.info(f"Config file: {source}"))
    print(output.info(f"Version groups: {group_count} {plural}"))
    print()

    print(output.section("Version groups"))
    for group in conf.version_groups:
        print(output.ok(f"[{group.name}]"))
        for detail_line in _render_group_details(group, root):
            print(detail_line)
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
