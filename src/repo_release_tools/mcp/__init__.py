"""FastMCP server for repo-release-tools — expose rrt as an MCP service.

## Overview

This subpackage wires repo-release-tools into the **Model Context Protocol (MCP)** so that
AI coding assistants (Claude Desktop, VS Code Copilot, Cursor, and any MCP-compatible host)
can call rrt's version management, changelog, health, drift, artifact, and git-workflow
capabilities as first-class tools.

The server is built on [FastMCP 3.x](https://github.com/jlowin/fastmcp) and ships as an
optional extra:

```bash
pip install "repo-release-tools[mcp]"
# or with uv:
uv add "repo-release-tools[mcp]"
```

## What's inside

| Module | Contents |
|---|---|
| `server.py` | FastMCP server factory (`create_server`), lifespan, and `main()` CLI entry point |
| `apps.py` | Interactive PrefabApp dashboards: health, version, doctor, tree, locks, and init form |
| `tools/` | Structured tool modules: config, lock, version, validation, changelog, git |
| `resources.py` | MCP resources: version, config, config schema, changelog, lock files |
| `prompts.py` | Reusable prompt templates: release workflow, version strategy, branch strategy, commit guide |
| `models.py` | Pydantic response models used by all tool modules |

## Architecture

The server is created by `create_server()`, which:

1. Instantiates a `FastMCP` instance with the package version and a `_lifespan` context manager
2. Calls `register_tools(mcp)`, `register_resources(mcp)`, `register_prompts(mcp)`, and
   `register_apps(mcp)` to populate the server
3. Attaches a `GenerativeUI` provider so AI assistants can render rich UI components

The **lifespan** context manager (`_lifespan`) runs once at server startup:
- Walks up the filesystem to locate the repo root (looks for `.rrt/` or `pyproject.toml`)
- Tries to load the `[tool.rrt]` configuration; sets `config=None` if unavailable
- Passes `{"root": <Path>, "config": <Config | None>}` as lifespan context to all tools

## Transport modes

The `rrt-mcp` CLI entry point supports two transports:

```bash
# stdio (default) — used by Claude Desktop and MCP hosts that speak stdio
rrt-mcp

# HTTP — useful for local debugging or network-accessible MCP services
rrt-mcp --transport http --port 8080
```

## Connecting to Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "rrt": {
      "command": "rrt-mcp",
      "args": [],
      "cwd": "/path/to/your/repo"
    }
  }
}
```

After restarting Claude Desktop the full rrt tool palette is available in chat.

## Tool categories

**Version management** — `rrt_version`, `rrt_bump` (always dry-run by default for safety)

**Git workflow** — `rrt_branch_new`, `rrt_validate_branch`, `rrt_validate_commit`

**Changelog** — `rrt_changelog`

**Lock inspection** — `rrt_health`, `rrt_drift`, `rrt_tree`, `rrt_artifacts`

**Config** — `rrt_config`, `rrt_doctor`

**Interactive dashboards** — `rrt_health_dashboard`, `rrt_version_overview`,
`rrt_doctor_dashboard`, `rrt_tree_dashboard`, `rrt_locks_overview`, `rrt_init`

## Resources

| URI | Content |
|---|---|
| `rrt://version` | Installed rrt package version |
| `rrt://config` | Current `[tool.rrt]` configuration as JSON |
| `rrt://schema/config` | Full JSON Schema for all rrt config options |
| `rrt://changelog` | Full `CHANGELOG.md` text |
| `rrt://locks/{name}` | Parsed lock file (`health`, `drift`, `tree`, `artifacts`) as JSON |

## Safety

All mutating tools (`rrt_bump`, `rrt_branch_new`) default to `dry_run=True` so an AI
assistant cannot inadvertently modify the repo without explicit user confirmation.
"""

from __future__ import annotations

try:
    from .server import create_server
except ModuleNotFoundError as exc:  # pragma: no cover
    if exc.name in ("fastmcp", "prefab_ui", "mcp"):
        raise ImportError(
            "FastMCP is required for the MCP server. "
            "Install it with: pip install repo-release-tools[mcp]"
        ) from exc
    raise

__all__ = ["create_server"]
