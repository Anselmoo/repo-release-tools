"""`rrt project info` — surface project metadata from the project manifest.

Reads ``pyproject.toml`` / ``Cargo.toml`` / ``package.json`` and emits
``name``, ``description``, ``version``, ``authors``, ``license``, and
``urls`` as text (default) or JSON. Useful for generating README headers,
populating release-body templates, or scripting CI tasks that need a
single field via ``--key``.

## Examples

- ``rrt project info``
- ``rrt project info --format json``
- ``rrt project info --key description``
- ``rrt project info --format json --output project-info.json``
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from repo_release_tools.config.project_meta import (
    ProjectMetadata,
    load_project_metadata,
)
from repo_release_tools.ui import VerbosePrinter

_VALID_KEYS = ("name", "version", "description", "authors", "license", "urls", "source")


@dataclass(frozen=True)
class InfoOptions:
    """Typed view of ``argparse.Namespace`` for ``rrt project info``.

    Built once via :meth:`from_args` at the top of :func:`cmd_project_info` so
    all flags it reads have typed read sites instead of ``getattr(args, ...,
    default)`` calls throughout the function body.
    """

    root: Path
    project_format: str
    key: str | None
    output: str | None
    verbose: int

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> InfoOptions:
        """Build an :class:`InfoOptions` from a parsed ``argparse.Namespace``.

        ``root``, ``project_format``, ``key``, and ``output`` are given real
        defaults by project_cmd.py's own register(), and every test in
        tests/commands/test_project_cmd.py that exercises cmd_project_info
        goes through the local ``_args()`` helper which always sets all four,
        so they are read directly. ``verbose`` is set globally by cli.py's
        parser, but ``_args()`` never sets it, so the getattr fallback here
        absorbs that gap.
        """
        return cls(
            root=Path(args.root).resolve(),
            project_format=args.project_format,
            key=args.key,
            output=args.output,
            verbose=getattr(args, "verbose", 0) or 0,
        )


def cmd_project_info(args: argparse.Namespace) -> int:
    """Emit project metadata read from the manifest."""
    opts = InfoOptions.from_args(args)
    verbose = opts.verbose
    root = opts.root
    fmt = opts.project_format
    key = opts.key
    output_path = opts.output

    if not root.is_dir():
        VerbosePrinter(verbose=verbose).line(
            f"Root path is not a directory: {root}", ok=False, stream=sys.stderr
        )
        return 1

    metadata = load_project_metadata(root)

    if key is not None:
        if key not in _VALID_KEYS:
            VerbosePrinter(verbose=verbose).line(
                f"Unknown --key {key!r}. Valid keys: {', '.join(_VALID_KEYS)}.",
                ok=False,
                stream=sys.stderr,
            )
            return 1
        rendered = _render_single_key(metadata, key, fmt=fmt)
    elif fmt == "json":
        rendered = json.dumps(metadata.to_dict(), indent=2, ensure_ascii=False) + "\n"
    else:
        rendered = _render_text(metadata)

    if output_path:
        Path(output_path).write_text(rendered, encoding="utf-8")
        VerbosePrinter(verbose=verbose).verbose_line(f"project info → {output_path}", level=1)
    else:
        sys.stdout.write(rendered)
    return 0


def _render_single_key(metadata: ProjectMetadata, key: str, *, fmt: str) -> str:
    value = metadata.to_dict()[key]
    if fmt == "json":
        return json.dumps(value, ensure_ascii=False) + "\n"
    if value is None:
        return "\n"
    if isinstance(value, list):
        return "".join(f"{item}\n" for item in value)
    if isinstance(value, dict):
        return "".join(f"{label}: {url}\n" for label, url in value.items())
    return f"{value}\n"


def _render_text(metadata: ProjectMetadata) -> str:
    data = metadata.to_dict()
    lines: list[str] = []
    for label, attr in (
        ("Name", "name"),
        ("Version", "version"),
        ("Description", "description"),
        ("License", "license"),
        ("Source", "source"),
    ):
        value = data[attr]
        if value:
            lines.append(f"{label}: {value}")

    authors = data["authors"]
    if isinstance(authors, list) and authors:
        lines.append("Authors:")
        lines.extend(f"  - {item}" for item in authors)

    urls = data["urls"]
    if isinstance(urls, dict) and urls:
        lines.append("URLs:")
        lines.extend(f"  - {label}: {url}" for label, url in urls.items())

    return "\n".join(lines) + ("\n" if lines else "")


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the `project` command group on the root parser."""
    parser = subparsers.add_parser(
        "project",
        help="Project metadata utilities (read from pyproject/Cargo/package.json).",
        description=(
            "Read project metadata (name, description, version, authors, license, "
            "urls) from the appropriate manifest in the current repository."
        ),
    )
    project_subparsers = parser.add_subparsers(
        dest="project_command",
        metavar="<project_command>",
    )

    info_parser = project_subparsers.add_parser(
        "info",
        help="Print project metadata as text (default) or JSON.",
        description=(
            "Resolve the project manifest (pyproject.toml, Cargo.toml, or "
            "package.json) and emit name, version, description, authors, "
            "license, and URLs."
        ),
    )
    info_parser.add_argument(
        "--root",
        default=".",
        metavar="PATH",
        help="Project root to read (default: current directory).",
    )
    info_parser.add_argument(
        "--format",
        dest="project_format",
        choices=["text", "json"],
        default="text",
        metavar="FORMAT",
        help="Output format: text (default) or json.",
    )
    info_parser.add_argument(
        "--key",
        default=None,
        metavar="KEY",
        help=(
            "Emit only one field. Valid keys: "
            "name, version, description, authors, license, urls, source."
        ),
    )
    info_parser.add_argument(
        "--output",
        default=None,
        metavar="PATH",
        help="Write the output to PATH instead of stdout.",
    )
    info_parser.set_defaults(handler=cmd_project_info)

    parser.set_defaults(handler=_default_help(parser))


def _default_help(
    parser: argparse.ArgumentParser,
) -> Callable[[argparse.Namespace], int]:
    """Print help and exit with code 1 when no subcommand is provided."""

    def _handler(_args: argparse.Namespace) -> int:
        parser.print_help()
        return 1

    return _handler
