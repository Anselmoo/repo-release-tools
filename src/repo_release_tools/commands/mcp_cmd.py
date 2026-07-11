"""`rrt mcp tool new <name>` — scaffold a starter MCP tool module.

Emits a new file under ``src/repo_release_tools/mcp/tools/<name>_tools.py``
mirroring the pattern already used by the other modules in that directory:
a ``register(mcp: FastMCP)`` function plus one ``@mcp.tool`` body with a
typed Pydantic response model. Tool authors fill in the ``# TODO`` block.

The scaffolder is intentionally minimal — it does not edit
``mcp/tools/__init__.py``; the printed reminder tells the user to add the
new ``register()`` call there. Keeping the edits separate makes the
generated file reviewable on its own.

## Examples

- ``rrt mcp tool new sample``
- ``rrt mcp tool new sample --title "Sample" --description "demo" --dry-run``
- ``rrt mcp tool new sample --into custom/path.py --force``
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from repo_release_tools.ui import DryRunPrinter

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


_TEMPLATE = '''\
"""MCP tool: {title}.

{description}
"""

from __future__ import annotations

from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel

from repo_release_tools import __version__ as _PKG_VERSION


class {model_name}(BaseModel):
    """Response model for the ``{tool_name}`` MCP tool."""

    ok: bool
    detail: str | None = None


def register(mcp: FastMCP) -> None:
    """Register the ``{tool_name}`` tool on *mcp*."""

    @mcp.tool(
        title={title!r},
        tags={{"{name}"}},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(readOnlyHint=True),
        meta={{"domain": "rrt", "surface": "mcp"}},
    )
    def {tool_name}(ctx: Context) -> {model_name}:
        """{description}"""
        # TODO: implement the {tool_name} tool body.
        del ctx
        return {model_name}(ok=True, detail="placeholder")
'''


@dataclass(frozen=True)
class ToolNewOptions:
    """Typed view of ``argparse.Namespace`` for ``rrt mcp tool new``.

    Built once via :meth:`from_args` at the top of :func:`cmd_mcp_tool_new`
    so all flags it reads have typed read sites instead of
    ``getattr(args, ..., default)`` calls throughout the function body.
    """

    name: str
    title: str | None
    description: str | None
    into: str | None
    dry_run: bool
    force: bool

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> ToolNewOptions:
        """Build a :class:`ToolNewOptions` from a parsed ``argparse.Namespace``.

        ``name`` is positional/required and ``title``, ``description``,
        ``into``, ``dry_run``, and ``force`` are all given real defaults by
        mcp_cmd.py's own register(). No cmd_* dispatch in
        `workflow/hooks.py` calls cmd_mcp_tool_new (this file has no
        hooks.py entry at all), and the only test file exercising this
        command, tests/commands/test_mcp_scaffold.py, goes through the
        local ``_args()`` helper which always sets all six fields
        explicitly (the two bare ``argparse.Namespace()`` calls in that
        file target the unrelated ``_default_help`` handlers, not
        cmd_mcp_tool_new). This command does not read ``verbose`` at all.
        So no getattr fallback is needed for any field.
        """
        return cls(
            name=args.name,
            title=args.title,
            description=args.description,
            into=args.into,
            dry_run=args.dry_run,
            force=args.force,
        )


def cmd_mcp_tool_new(args: argparse.Namespace) -> int:
    """Scaffold a new MCP tool module from a name + optional title/description."""
    opts = ToolNewOptions.from_args(args)
    p = DryRunPrinter(opts.dry_run)

    name = opts.name
    if not _NAME_RE.match(name):
        p.line(
            f"Invalid tool name: {name!r}. "
            "Use lowercase letters, digits, and underscores; must start with a letter.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    title = opts.title or _humanize(name)
    description = opts.description or f"MCP tool stub for {name}."

    into = opts.into
    if into:
        target = Path(into).resolve()
    else:
        target = Path.cwd() / "src" / "repo_release_tools" / "mcp" / "tools" / f"{name}_tools.py"

    if target.exists() and not opts.force:
        p.line(
            f"Refusing to overwrite existing file: {target}. Use --force to override.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    body = _TEMPLATE.format(
        title=title,
        description=description,
        tool_name=f"rrt_{name}",
        model_name=_studly_case(name) + "Response",
        name=name,
    )

    if p.dry_run:
        p.action(f"[dry-run] Would write {target}")
        sys.stdout.write(body)
        return 0

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    p.ok(f"Created {target}")
    p.meta(
        "Next step",
        f"Import and call register() from {name}_tools in "
        f"src/repo_release_tools/mcp/tools/__init__.py:register_tools().",
    )
    return 0


def _humanize(name: str) -> str:
    """Render a snake_case name as a Title-Cased title."""
    return " ".join(part.capitalize() for part in name.split("_"))


def _studly_case(name: str) -> str:
    """Render a snake_case name as StudlyCase (StudlyCase + 'Response' → model name)."""
    return "".join(part.capitalize() for part in name.split("_"))


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the `mcp` command group on the root parser."""
    parser = subparsers.add_parser(
        "mcp",
        help="MCP server scaffolding helpers.",
        description=(
            "Scaffolders and utilities for the rrt MCP server. Currently exposes "
            "`mcp tool new` to generate a starter MCP tool module."
        ),
    )
    mcp_subparsers = parser.add_subparsers(dest="mcp_command", metavar="<mcp_command>")

    tool_parser = mcp_subparsers.add_parser(
        "tool",
        help="Manage MCP tool scaffolds.",
        description="Operations on MCP tool modules under mcp/tools/.",
    )
    tool_subparsers = tool_parser.add_subparsers(dest="tool_command", metavar="<tool_command>")

    new_parser = tool_subparsers.add_parser(
        "new",
        help="Scaffold a new MCP tool module.",
        description=(
            "Emit a starter `mcp/tools/<name>_tools.py` with one @mcp.tool body, "
            "a Pydantic response model, and a register(mcp) function ready to "
            "wire into mcp/tools/__init__.py:register_tools()."
        ),
    )
    new_parser.add_argument("name", help="Snake_case tool name (e.g. project_metadata).")
    new_parser.add_argument(
        "--title",
        default=None,
        metavar="TITLE",
        help="Human-readable title (default: derived from name).",
    )
    new_parser.add_argument(
        "--description",
        default=None,
        metavar="TEXT",
        help="Short description used in the docstring and tool body.",
    )
    new_parser.add_argument(
        "--into",
        default=None,
        metavar="PATH",
        help=(
            "Target path for the new module "
            "(default: src/repo_release_tools/mcp/tools/<name>_tools.py)."
        ),
    )
    new_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print the scaffold to stdout instead of writing the file.",
    )
    new_parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Overwrite the target file if it already exists.",
    )
    new_parser.set_defaults(handler=cmd_mcp_tool_new)

    tool_parser.set_defaults(handler=_default_help(tool_parser))
    parser.set_defaults(handler=_default_help(parser))


def _default_help(
    parser: argparse.ArgumentParser,
) -> Callable[[argparse.Namespace], int]:
    """Print help and exit with 1 when no subcommand was given."""

    def _handler(_args: argparse.Namespace) -> int:
        parser.print_help()
        return 1

    return _handler
