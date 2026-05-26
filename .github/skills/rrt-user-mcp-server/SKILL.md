---
name: rrt-user-mcp-server
description: >-
  Teaches AI assistants (Claude Code, Claude Desktop, Cursor) how to install
  and connect the repo-release-tools MCP server so rrt tools (config, version,
  health, drift, tree, artifacts, changelog, validation) are available via MCP.
  Use when wiring up rrt[mcp] to an AI assistant for the first time. DO NOT USE
  for debugging rrt CLI commands or for users who only need the CLI.
---

# rrt-user-mcp-server

## User problem statement

I want to use rrt's capabilities (config inspection, version bumping, health
checks, changelog reading, branch/commit validation) directly inside my AI
assistant without leaving the editor.

## Quick start commands

```bash
# Install the MCP extra
uv add "repo-release-tools[mcp]"

# Verify the server starts
uv run rrt-mcp --help

# Add .mcp.json at the repo root (Claude Code auto-detects this)
cat .mcp.json
# Should contain:
# {
#   "mcpServers": {
#     "rrt": { "type": "stdio", "command": "uv", "args": ["run", "rrt-mcp"] }
#   }
# }
```

## When to use

- Connecting the rrt MCP server to Claude Code, Claude Desktop, or Cursor
- Choosing between local (per-repo) and global MCP wiring
- Using interactive dashboards (`rrt_health_dashboard`, `rrt_tree_dashboard`, `rrt_locks_overview`, etc.)
- Calling `rrt_bump`, `rrt_changelog`, or `rrt_validate_branch` from within
  an AI assistant conversation
- Initializing rrt config via the `rrt_init` form app

## Do not use for

- Debugging rrt CLI commands (use `rrt doctor` instead)
- Writing custom MCP servers based on rrt internals
- Publishing or packaging the rrt release itself

## Install surfaces

### Claude Code — local (per-repo, auto-detected)

Create `.mcp.json` at the repository root:

```json
{
  "mcpServers": {
    "rrt": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "rrt-mcp"]
    }
  }
}
```

Claude Code picks this up automatically on next start.

### Claude Code — global

```bash
claude mcp add rrt -- uv run --with "repo-release-tools[mcp]" rrt-mcp
```

Or manually add to `~/.claude/mcp.json`:

```json
{
  "mcpServers": {
    "rrt": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "repo-release-tools[mcp]", "rrt-mcp"]
    }
  }
}
```

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`
(macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "rrt": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "repo-release-tools[mcp]", "rrt-mcp"]
    }
  }
}
```

Restart Claude Desktop after editing.

### Published package (no local install)

```json
{
  "mcpServers": {
    "rrt": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "repo-release-tools[mcp]", "rrt-mcp"]
    }
  }
}
```

## Available tools

| Tool | Tags | Notes |
|---|---|---|
| `rrt_config` | config, inspection | Resolved rrt config as JSON |
| `rrt_doctor` | config, inspection | Pre-commit / lefthook / workflow checks |
| `rrt_health` | locks, inspection | `.rrt/health.lock.toml` |
| `rrt_drift` | locks, inspection | `.rrt/drift.lock.toml` |
| `rrt_tree` | locks, inspection | `.rrt/tree.lock.toml` |
| `rrt_artifacts` | locks, inspection | `.rrt/artifacts.lock.toml` |
| `rrt_version` | versioning | Current version per group |
| `rrt_bump` | versioning | Bump version (destructive when dry_run=False) |
| `rrt_validate_branch` | validation | Conventional branch naming |
| `rrt_validate_commit` | validation | Conventional commit subject |
| `rrt_changelog` | changelog | Unreleased entries or full content |
| `rrt_health_dashboard` | ui, dashboard | Metric row, health Ring, per-lock BarChart, check Cards, detail table (app tool) |
| `rrt_version_overview` | ui, dashboard, versioning | Version target map with Metric header (app tool) |
| `rrt_doctor_dashboard` | ui, dashboard, inspection | Pass-rate Ring, per-check Metrics, status Cards, detail table (app tool) |
| `rrt_tree_dashboard` | ui, dashboard, inspection | Metric summary, per-directory BarChart, clean file table (app tool) |
| `rrt_init` | ui, init, config | Init form — target, dry_run, force (app tool, submits to rrt_init_run) |
| `rrt_init_run` | init, config | Executes rrt init; dry_run=True by default (destructive) |
| `rrt_locks_overview` | ui, dashboard, locks | Status donut PieChart, Carousel of lock summaries, detail table (app tool) |

## Available resources

| URI | Description |
|---|---|
| `rrt://version` | Installed package version |
| `rrt://config` | Config as JSON |
| `rrt://changelog` | Full CHANGELOG.md |
| `rrt://locks/{name}` | Any lock file by name (drift/health/tree/artifacts) |

## Generative UI

The server registers FastMCP's `GenerativeUI` provider, adding
`generate_prefab_ui` and `search_prefab_components` tools. The LLM can write
custom Prefab code executed in a Pyodide sandbox — useful for custom
visualizations of `rrt://locks/{name}` data.

## Full reference

See `docs/mcp-server.md` in the repository (or `/mcp-server/` on the docs site)
for the complete tool, resource, and prompt reference.

## Expected outcome / success criteria

- `rrt_config` returns the project's resolved rrt config without error
- `rrt_health_dashboard` renders Metric cards, a health Ring, and a BarChart in Claude's UI
- `rrt_tree_dashboard` shows a BarChart of file counts per directory with no empty columns in the table
- `rrt_locks_overview` shows a donut PieChart and a Carousel cycling through lock summaries
- `rrt_bump patch --dry-run` previews a version change without writing files
- The user can complete a full release workflow from inside the AI assistant
