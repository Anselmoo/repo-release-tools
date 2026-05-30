#!/usr/bin/env python3
"""Generate a .mcp.json configuration file for locally connecting MCP servers.

Usage examples:
  python3 scripts/generate_mcp_json.py --command rrt-mcp --output .mcp.json
  python3 scripts/generate_mcp_json.py --command uvx --args 'repo-release-tools rrt-mcp' --output .mcp.json
"""
import argparse
import json
import shlex
from pathlib import Path

def main():
    p = argparse.ArgumentParser(description="Generate .mcp.json for MCP servers")
    p.add_argument("--command", required=True, help="Command to run (e.g. rrt-mcp or uvx)")
    p.add_argument("--args", default="", help="Space-separated args for the command (e.g. 'repo-release-tools rrt-mcp')")
    p.add_argument("--transport", default="stdio", choices=["stdio", "http"], help="Transport type")
    p.add_argument("--name", default="rrt", help="MCP server name key")
    p.add_argument("--output", default=".mcp.json", help="Output file path")
    args = p.parse_args()

    args_list = shlex.split(args.args) if args.args else []

    payload = {
        "mcpServers": {
            args.name: {
                "type": args.transport,
                "command": args.command,
                "args": args_list,
            }
        }
    }

    out = Path(args.output)
    out.write_text(json.dumps(payload, indent=2))
    print(f"Wrote {out.resolve()}")

if __name__ == '__main__':
    main()
