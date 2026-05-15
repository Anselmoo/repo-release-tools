"""API protocol index for rrt — introspects the live argparse parser tree.

Walks the argparse parser built by ``cli.build_parser()`` and extracts a
structured index of every command, sub-command, and their arguments.  The
result can be rendered as Markdown, plain text, or JSON for tooling and
documentation.

## Design

- ``ApiEntry`` — dataclass representing a single command (leaf or group).
- ``build_api_index(parser)`` — recursively walks an ``ArgumentParser`` and
  returns a flat list of ``ApiEntry`` objects.
- ``load_hooks()`` — reads ``.pre-commit-hooks.yaml`` and returns a mapping of
  hook ``entry`` → ``id`` so that the index can cross-link CLI commands to
  their pre-commit hook counterparts.

## Usage

```python
from repo_release_tools.cli import build_parser
from repo_release_tools.docs.api_index import build_api_index, render_api_md

parser = build_parser()
entries = build_api_index(parser)
print(render_api_md(entries))
```
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ArgInfo:
    """Metadata for a single argument / option on a command."""

    flags: list[str]
    dest: str
    help: str
    default: Any
    required: bool
    metavar: str | None
    choices: list[str] | None


@dataclass
class ApiEntry:
    """Metadata for a single rrt command (possibly a sub-command)."""

    name: str
    description: str
    arguments: list[ArgInfo] = field(default_factory=list)
    hook_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialise to a plain dict suitable for JSON output."""
        return {
            "name": self.name,
            "description": self.description,
            "hook_id": self.hook_id,
            "arguments": [
                {
                    "flags": a.flags,
                    "dest": a.dest,
                    "help": a.help,
                    "default": a.default,
                    "required": a.required,
                    "metavar": a.metavar,
                    "choices": a.choices,
                }
                for a in self.arguments
            ],
        }


# ---------------------------------------------------------------------------
# Pre-commit hook cross-link table
# ---------------------------------------------------------------------------


def load_hooks(root: Path | None = None) -> dict[str, str]:
    """Return a mapping of rrt hook entry-point → hook id.

    Reads ``.pre-commit-hooks.yaml`` from *root* (or CWD when *root* is
    ``None``).  Returns an empty dict when the file is absent or cannot be
    parsed.

    The return value maps the ``entry`` field (e.g. ``"rrt-hooks pre-commit"``)
    to the hook ``id`` (e.g. ``"rrt-branch-name"``).
    """
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:  # pragma: no cover
        return {}

    search_root = root or Path(".")
    hook_file = search_root / ".pre-commit-hooks.yaml"
    if not hook_file.exists():
        return {}

    try:
        raw = yaml.safe_load(hook_file.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError):
        return {}

    if not isinstance(raw, list):
        return {}

    result: dict[str, str] = {}
    for item in raw:
        if isinstance(item, dict):
            entry = item.get("entry", "")
            hook_id = item.get("id", "")
            if entry and hook_id:
                result[str(entry)] = str(hook_id)
    return result


def _hook_id_for(name: str, hook_map: dict[str, str]) -> str | None:
    """Return the pre-commit hook id whose entry matches *name*."""
    for entry, hid in hook_map.items():
        parts = entry.split()
        if name in parts:
            return hid
    return None


# ---------------------------------------------------------------------------
# Parser walker
# ---------------------------------------------------------------------------


def _collect_args(parser: argparse.ArgumentParser) -> list[ArgInfo]:
    """Collect argument metadata from *parser*, skipping internal defaults."""
    args: list[ArgInfo] = []
    for action in parser._actions:
        if isinstance(action, (argparse._HelpAction, argparse._VersionAction)):
            continue
        if isinstance(action, argparse._SubParsersAction):
            continue
        metavar: str | None = None
        if isinstance(action.metavar, str):
            metavar = action.metavar
        elif isinstance(action.metavar, tuple):
            metavar = " ".join(action.metavar)

        choices: list[str] | None = None
        if action.choices is not None:
            choices = [str(c) for c in action.choices]

        required = bool(getattr(action, "required", False))
        # Positional actions are implicitly required unless nargs allows zero
        if not action.option_strings:
            nargs = action.nargs
            required = nargs not in ("?", "*")

        args.append(
            ArgInfo(
                flags=list(action.option_strings) or [action.dest],
                dest=action.dest,
                help=(action.help or "").replace("%(default)s", str(action.default)),
                default=action.default,
                required=required,
                metavar=metavar,
                choices=choices,
            )
        )
    return args


def build_api_index(
    parser: argparse.ArgumentParser,
    *,
    hook_map: dict[str, str] | None = None,
    _prefix: str = "",
) -> list[ApiEntry]:
    """Walk *parser* recursively and return a flat list of ``ApiEntry`` objects.

    Parameters
    ----------
    parser:
        The root (or sub) ``ArgumentParser`` to walk.
    hook_map:
        Optional mapping from hook entry → hook id, as returned by
        ``load_hooks()``.  When provided, each entry's ``hook_id`` field is
        populated when a matching hook is found.
    _prefix:
        Internal prefix for building the full command name (e.g. ``"rrt docs"``).
    """
    if hook_map is None:
        hook_map = {}

    entries: list[ApiEntry] = []

    prog = parser.prog or "rrt"
    description = (parser.description or "").strip()

    name = _prefix or prog
    args = _collect_args(parser)
    hook_id = _hook_id_for(prog.split()[-1], hook_map) if prog else None

    # Only emit a top-level entry when there is meaningful content
    if description or args:
        entries.append(
            ApiEntry(
                name=name,
                description=description,
                arguments=args,
                hook_id=hook_id,
            )
        )

    # Walk sub-parsers
    for action in parser._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue
        choices: dict[str, argparse.ArgumentParser] = action.choices or {}
        for sub_name, sub_parser in choices.items():
            full_name = f"{name} {sub_name}"
            sub_entries = build_api_index(
                sub_parser,
                hook_map=hook_map,
                _prefix=full_name,
            )
            entries.extend(sub_entries)

    return entries


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


def render_api_md(entries: list[ApiEntry]) -> str:
    """Render the API index as a Markdown document."""
    parts: list[str] = ["# rrt API Index\n"]
    for entry in entries:
        anchor = entry.name.lower().replace(" ", "-")
        hook_line = f"\n*Pre-commit hook: `{entry.hook_id}`*" if entry.hook_id else ""
        parts.append(f"\n## `{entry.name}` {{#{anchor}}}\n")
        if entry.description:
            parts.append(f"{entry.description}\n")
        if hook_line:
            parts.append(f"{hook_line}\n")
        if entry.arguments:
            parts.append("\n**Arguments:**\n")
            parts.append("| Flag | Dest | Default | Required | Help |\n")
            parts.append("|---|---|---|---|---|\n")
            for arg in entry.arguments:
                flags = ", ".join(f"`{f}`" for f in arg.flags)
                default = f"`{arg.default}`" if arg.default not in (None, argparse.SUPPRESS) else ""
                req = "✓" if arg.required else ""
                help_text = arg.help.replace("|", "\\|")
                parts.append(f"| {flags} | `{arg.dest}` | {default} | {req} | {help_text} |\n")
    return "".join(parts)


def render_api_txt(entries: list[ApiEntry]) -> str:
    """Render the API index as plain text."""
    parts: list[str] = []
    for entry in entries:
        parts.append(f"=== {entry.name} ===")
        if entry.description:
            parts.append(entry.description)
        if entry.hook_id:
            parts.append(f"Pre-commit hook: {entry.hook_id}")
        for arg in entry.arguments:
            flags = ", ".join(arg.flags)
            req = " [required]" if arg.required else ""
            parts.append(f"  {flags}{req}  {arg.help}")
        parts.append("")
    return "\n".join(parts)


def render_api_json(entries: list[ApiEntry]) -> str:
    """Render the API index as a JSON array."""
    return json.dumps([e.to_dict() for e in entries], indent=2)
