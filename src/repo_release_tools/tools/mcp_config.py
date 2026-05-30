#!/usr/bin/env python3
"""Small utility to write/merge `.mcp.json` configuration files.

Usage examples:
  rrt-mcp-config --mode append --target local
  rrt-mcp-config --mode extend --path ~/.mcp.json
  python -m repo_release_tools.tools.mcp_config --mode overwrite --command rrt-mcp --args "--transport http --port 8000" --output .mcp.json
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_KEY = "rrt"


def deep_merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """Merge b into a and return a. For lists under 'args' perform unique concat."""
    for k, v in b.items():
        if k in a and isinstance(a[k], dict) and isinstance(v, dict):
            deep_merge(a[k], v)
        elif k in a and isinstance(a[k], list) and isinstance(v, list):
            # unique-preserve order
            existing = list(a[k])
            for item in v:
                if item not in existing:
                    existing.append(item)
            a[k] = existing
        else:
            a[k] = v
    return a


def load_json(path: Path) -> Dict[str, Any]:
    """Load JSON from *path* returning an empty dict if the file is missing.

    Raises SystemExit when the file exists but is not valid JSON.
    """
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raise SystemExit(f"Failed to read JSON from {path}")


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    """Write *payload* as pretty JSON to *path* (creating parent directories)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    # Use the UI printer for consistent CLI output
    from repo_release_tools.ui import DryRunPrinter

    DryRunPrinter(dry_run=False).ok(f"Wrote {path}")


def build_payload(command: str, args: List[str], key: str) -> Dict[str, Any]:
    """Return a minimal MCP payload dict for *key* that invokes *command* with *args*."""
    return {"mcpServers": {key: {"type": "stdio", "command": command, "args": args}}}


def resolve_target_path(target: str, custom: str | None) -> Path:
    """Resolve the target name to a filesystem path.

    Supported targets: local, user, claude-desktop, custom.
    """
    home = Path.home()
    if target == "local":
        return Path.cwd() / ".mcp.json"
    if target == "user":
        return home / ".mcp.json"
    if target == "claude-desktop":
        # macOS location preferred; fallback to user path
        mac = home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
        if mac.exists() or os.name != "nt":
            return mac
        # Windows fallback
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "Claude" / "claude_desktop_config.json"
        return home / ".mcp.json"
    if target == "custom":
        if not custom:
            raise SystemExit("--path is required for custom target")
        return Path(custom).expanduser()
    raise SystemExit(f"Unknown target: {target}")


def main(argv: List[str] | None = None) -> None:
    """Command-line entry point. Parse arguments and perform the requested action."""
    p = argparse.ArgumentParser(description="Generate or merge .mcp.json MCP server configs")
    p.add_argument(
        "--mode",
        choices=["append", "extend", "overwrite"],
        default="append",
        help="append: add only if key missing; extend: merge; overwrite: replace file",
    )
    p.add_argument(
        "--target",
        choices=["local", "user", "claude-desktop", "custom"],
        default="local",
        help="Where to write the file",
    )
    p.add_argument("--path", help="Custom path for target (required if --target custom)")
    p.add_argument("--command", default="rrt-mcp", help="Command to invoke for server entry")
    p.add_argument("--args", default="", help="Space-separated args for the command")
    p.add_argument("--key", default=DEFAULT_KEY, help="mcpServers key name to write/merge")
    p.add_argument(
        "--output", default=None, help="Optional explicit output path (overrides target)"
    )
    args = p.parse_args(argv)

    args_list = [a for a in args.args.split() if a]
    out_path = (
        Path(args.output).expanduser()
        if args.output
        else resolve_target_path(args.target, args.path)
    )

    payload = build_payload(args.command, args_list, args.key)

    if out_path.exists():
        existing = load_json(out_path)
    else:
        existing = {}

    printer = None
    try:
        from repo_release_tools.ui import DryRunPrinter

        printer = DryRunPrinter(dry_run=False)
    except Exception:
        printer = None

    if args.mode == "append":
        ms = existing.get("mcpServers", {})
        if args.key in ms:
            # Prefer the structured UI printer when available
            if printer:
                printer.warn(
                    f"Server key '{args.key}' already present in {out_path}; no changes made (append mode)"
                )
            else:
                try:
                    from repo_release_tools.ui import DryRunPrinter

                    DryRunPrinter(dry_run=False).warn(
                        f"Server key '{args.key}' already present in {out_path}; no changes made (append mode)"
                    )
                except Exception:
                    # No UI available, silently exit (no-op)
                    pass
            return
        # add payload
        existing.setdefault("mcpServers", {})
        existing["mcpServers"][args.key] = payload["mcpServers"][args.key]
        write_json(out_path, existing)
        return

    if args.mode == "extend":
        merged = existing.copy() if existing else {}
        merged.setdefault("mcpServers", {})
        merged_servers = merged["mcpServers"]
        new_servers = payload["mcpServers"]
        for k, v in new_servers.items():
            if k in merged_servers and isinstance(merged_servers[k], dict):
                deep_merge(merged_servers[k], v)
            else:
                merged_servers[k] = v
        write_json(out_path, merged)
        return

    if args.mode == "overwrite":
        write_json(out_path, payload)
        return


if __name__ == "__main__":
    main()
