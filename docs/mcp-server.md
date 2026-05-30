---
title: "MCP Server"
permalink: "/mcp-server/"
---
<!-- rrt:auto:start:page-header -->
<p><a href="https://github.com/Anselmoo/repo-release-tools"><picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/badges/github-reto-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="../assets/badges/github-reto-light.svg">
  <img alt="GitHub" src="../assets/badges/github-reto-dark.svg">
</picture></a></p>
<!-- rrt:auto:end:page-header -->


# MCP Server

The `[mcp]` extra ships a [FastMCP 3.x](https://gofastmcp.com) server named
`repo-release-tools` that exposes version management, changelog, health /
drift / tree / artifact lock inspection, branch and commit validation, config
introspection, and interactive dashboards as MCP tools, resources, and Prefab
UI apps.

## Install

```bash
# Add the [mcp] extra to your project
uv add "repo-release-tools[mcp]"

# Verify the entry point works
uv run rrt-mcp --help
```

## Connect

### Claude Code — local (per-repo)

Create or update `.mcp.json` at the repository root:

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

### HTTP transport

```bash
uv run rrt-mcp --transport http --port 8000
```

#### Typical MCP client configuration examples (.mcp.json)

Installed entry point (recommended, per-repo):

```json
{
  "mcpServers": {
    "rrt": {
      "type": "stdio",
      "command": "rrt-mcp",
      "args": []
    }
  }
}
```

From-source (developer convenience using uvx):

```json
{
  "mcpServers": {
    "rrt": {
      "type": "stdio",
      "command": "uvx",
      "args": ["repo-release-tools", "rrt-mcp"]
    }
  }
}
```

Claude Desktop / platform adapter example (uvx wrapper):

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

(Use the installed `rrt-mcp` entry point in production; `uvx` is convenient for iterating from a checkout.)

### GitHub Copilot

GitHub Copilot integrations vary by product and local tooling. The recommended approach is to install the bundled Copilot skill and run an MCP server that the Copilot client or adapter can reach:

```bash
rrt skill install --target copilot-local
# start a local MCP HTTP server that an adapter can proxy to
uv run rrt-mcp --transport http --port 8000
```

If using a hosted or product-specific Copilot client, consult the client documentation for how to point it at an MCP-compatible server or use a local adapter that bridges the client's extension API to MCP.

### Codex and Gemini (adapters)

Codex- and Gemini-based integrations typically require an adapter that understands the platform's client. For local testing and early development, install the codex-local skill and run the MCP HTTP transport:

```bash
rrt skill install --target codex-local
uv run rrt-mcp --transport http --port 8000
```

For production or hosted LLMs, use an MCP-aware gateway or adapter that forwards requests from your LLM client to the local MCP server. See docs/commands/skill.md for how to install and manage bundled skills.

For more details and advanced deployment options, consult the fastmcp project and the MCP client documentation for your chosen agent runtime.

### Helper: generate a .mcp.json from a template

A tiny helper script is included at `scripts/generate_mcp_json.py` to create a `.mcp.json` from a small template. Example usage (from the repository root):

```bash
python3 scripts/generate_mcp_json.py --command rrt-mcp --output .mcp.json
# or, to generate a uvx-based entry for development
python3 scripts/generate_mcp_json.py --command uvx --args 'repo-release-tools rrt-mcp' --output .mcp.json
```

A new CLI helper is also available once the package is installed: `rrt-mcp-config`.

Basic examples:

- Append mode (only adds server entry if missing):

```bash
# write .mcp.json in repo root only if key 'rrt' is absent
rrt-mcp-config --mode append --target local
```

- Extend mode (deep-merge into existing file):

```bash
# merge server entry, preserving existing args and merging lists
rrt-mcp-config --mode extend --target local --command rrt-mcp --args "--transport http --port 8000"
```

- Overwrite mode (replace file):

```bash
rrt-mcp-config --mode overwrite --target local --command rrt-mcp --args "--transport http --port 8000"
```

Where to write:
- local: `.mcp.json` in current repo
- user: `~/.mcp.json` (user-level)
- claude-desktop: platform path for Claude Desktop config (macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`)
- custom: pass `--path /some/path/.mcp.json`

This tool supports three modes:
- append: add server only if key missing
- extend: deep-merge existing file and add/merge server entry
- overwrite: replace target file with generated content

Use with care for global targets; prefer `--mode append` or `--mode extend` when updating user or desktop config files.


---

## Tools

### Read-only inspection tools

| Tool | Tags | Description |
|---|---|---|
| `rrt_config` | config, inspection | Resolved rrt config as JSON |
| `rrt_doctor` | config, inspection | Pre-commit / lefthook / husky / workflow checks |
| `rrt_health` | locks, inspection | `.rrt/health.lock.toml` contents |
| `rrt_drift` | locks, inspection | `.rrt/drift.lock.toml` contents |
| `rrt_tree` | locks, inspection | `.rrt/tree.lock.toml` contents |
| `rrt_artifacts` | locks, inspection | `.rrt/artifacts.lock.toml` contents |
| `rrt_version` | versioning | Current version per configured group |
| `rrt_validate_branch` | validation | Conventional branch naming check |
| `rrt_validate_commit` | validation | Conventional commit subject check |
| `rrt_changelog` | changelog | Unreleased entries or full content |

### Mutating tools (default dry_run=True)

| Tool | Tags | Description |
|---|---|---|
| `rrt_bump` | versioning | Semver bump — preview or apply |
| `rrt_branch_new` | git | Create conventionally-named branch |
| `rrt_init_run` | init, config | Run `rrt init` with selected target |

---

## App Dashboards

Interactive [Prefab UI](https://prefab.prefect.io) apps rendered in
MCP-capable clients (Claude Code, Claude Desktop). All are read-only.

| App tool | Description |
|---|---|
| `rrt_health_dashboard` | Health overview: Metric summary row, health Ring, per-lock status BarChart, check status Cards, full detail DataTable |
| `rrt_version_overview` | Version target map: all configured files, kinds, and current version values |
| `rrt_doctor_dashboard` | Doctor checks: pass-rate Ring, per-check Metric cards, status Cards, detail DataTable |
| `rrt_tree_dashboard` | File tree: Metric summary (total files, directories, snapshot), per-directory BarChart, clean DataTable |
| `rrt_init` | Init form: pick target format (`rrt-toml` / `pyproject` / `cargo` / `node` / `go`), dry_run, force — submits to `rrt_init_run` |
| `rrt_locks_overview` | All-locks overview: status donut PieChart, Carousel of per-lock summary cards, full detail DataTable |

### Generative UI

The server registers FastMCP's `GenerativeUI` provider, which adds
`generate_prefab_ui` and `search_prefab_components` tools. This lets the
LLM write custom [Prefab Python code](https://gofastmcp.com/apps/generative)
executed in a Pyodide sandbox — the LLM can build any visualization it
chooses from data exposed by `rrt://locks/{name}` or other resources.

---

## Resources

| URI | MIME | Description |
|---|---|---|
| `rrt://version` | `text/plain` | Installed package version string |
| `rrt://config` | `application/json` | Fully resolved rrt config |
| `rrt://schema/config` | `application/json` | JSON Schema for `[tool.rrt]` |
| `rrt://changelog` | `text/plain` | Full `CHANGELOG.md` content |
| `rrt://locks/{name}` | `application/json` | Lock file by name: `drift` / `health` / `tree` / `artifacts` |

---

## Prompt templates

Seven reusable prompts guide AI-assisted workflows:

| Prompt | Parameters | Description |
|---|---|---|
| `release_workflow` | `version_level`, `repo_name` | Step-by-step release guide |
| `version_strategy` | `change_summary` | Semver bump recommendation |
| `branch_strategy` | `task_description`, `context_hint` | Conventional branch selector |
| `commit_message_guide` | `staged_summary`, `branch_name` | Conventional Commits format |
| `changelog_entry` | `commit_summary`, `section_hint` | Keep-a-Changelog bullet |
| `config_setup` | `project_type` | Starter config per language |
| `release_readiness` | `version`, `target_env` | Pre-release checklist |

---

## Example session

```
# From inside Claude Code with rrt MCP connected:

"Show me the health dashboard"
→ calls rrt_health_dashboard — renders Metric cards, Ring, BarChart

"What version is the project at?"
→ calls rrt_version or rrt_version_overview

"Bump the patch version (dry run)"
→ calls rrt_bump with dry_run=True, shows preview

"Open the init form"
→ calls rrt_init — renders target/dry_run/force form

"Give me a custom chart of the lock file data"
→ LLM uses generate_prefab_ui + rrt://locks/{name} resources
```
