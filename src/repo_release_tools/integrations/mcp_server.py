"""MCP server documentation for repo-release-tools.

Lives under ``integrations/`` (not ``mcp/``) so that
``repo_release_tools.docs.publisher`` -- which must stay importable without
the optional ``[mcp]`` extra installed -- can register this topic doc
unconditionally. Importing any submodule of ``repo_release_tools.mcp``
executes ``mcp/__init__.py``, which eagerly imports ``fastmcp`` and raises
``ImportError`` when it is not installed; this module intentionally sits
outside that package to avoid forcing that dependency onto doc generation.
"""

from __future__ import annotations

MCP_SERVER_DOC = """# MCP Server

The `[mcp]` extra ships a [FastMCP 3.x](https://gofastmcp.com) server named
`repo-release-tools` that exposes version management, changelog, health /
drift / tree / artifact lock inspection, branch and commit validation, config
introspection, and interactive dashboards as MCP tools, resources, and Prefab
UI apps.

## When to use it

Use the MCP server whenever a task in an rrt-configured repository touches release
policy — version numbers, the changelog, branch or commit naming, `[tool.rrt]` config,
or `.rrt/*.lock.toml` state. If you were about to shell out to `rrt ...`, check here first.

Three concrete reasons to prefer it over the CLI:

- **Typed responses.** Most tools return Pydantic models serialised to JSON. `rrt_doctor`
  gives one `CheckResult` per component with `ok` and `severity`; the CLI gives
  ANSI-formatted prose you have to parse. The four lock readers and `rrt_config` return
  raw dicts instead, and `rrt_init_run` returns captured text — not every tool is typed.
- **No shell quoting.** `rrt_validate_commit(subject=...)` takes the subject as an
  argument. Backticks, quotes, `!`, `$`, and newlines in a commit message cannot be
  mangled on the way in.
- **Preview by default.** `rrt_bump`, `rrt_branch_new`, and `rrt_publish_snapshot` all
  default to `dry_run=True`; `rrt_publish_snapshot` also requires `confirm=True`. On the
  CLI, safety is a flag you must remember. Here it is the default and destruction is the
  opt-in. (`rrt_init_run` also defaults to `dry_run=True`, but it exists to serve the
  `rrt_init` form's submit button — an agent working from a shell gains nothing from it
  over running `rrt init` directly.)

### When to use the CLI instead

The MCP surface deliberately does not mirror every command. Use the CLI for:

- `rrt docs map` / `rrt docs map --check`
- `rrt docs generate`, `rrt docs publish`, `rrt docs inject`
- `rrt tree --check` and every `--snapshot` write (`rrt artifacts --snapshot`,
  `rrt tree --snapshot`); `rrt drift` has no `--snapshot` flag — use `rrt drift generate`
  / `rrt drift check`
- `rrt artifacts --check`
- `rrt toc`, `rrt changelog lint`, `rrt changelog compare`
- every `rrt-hooks` subcommand
- ordinary git, tests, and linters

A session that mixes both surfaces is the expected shape, not a workaround.

### Getting your agent to reach for it

The server's `instructions` tell a connected assistant when to prefer these tools, but
the most reliable lever is your own repository instruction file. See
[Get your AI agent to actually use rrt](https://github.com/Anselmoo/repo-release-tools#get-your-ai-agent-to-actually-use-rrt)
in the README for a copyable block for `CLAUDE.md` / `AGENTS.md` /
`.github/copilot-instructions.md`.

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
(macOS) or `%APPDATA%\\Claude\\claude_desktop_config.json` (Windows):

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

`--transport http` binds a real network listener — unlike `stdio`, anyone who
can reach `--host`:`--port` could invoke every `rrt_*` tool, including
destructive ones like `rrt_bump` and `rrt_publish_snapshot`. To prevent that,
HTTP transport **requires a bearer token**: pass `--auth-token` or set
`RRT_MCP_AUTH_TOKEN`. If neither is set, the server refuses to start rather
than opening an unauthenticated port. `--host` still defaults to `127.0.0.1`
(loopback-only) unless overridden.

```bash
# Token via flag
uv run rrt-mcp --transport http --port 8000 --auth-token "$(openssl rand -hex 32)"

# Token via env var
export RRT_MCP_AUTH_TOKEN="$(openssl rand -hex 32)"
uv run rrt-mcp --transport http --port 8000
```

Clients connect with the same token as a bearer credential, e.g. an
`Authorization: Bearer <token>` header or FastMCP's `Client(url, auth=token)`.

`stdio` transport (the default) is process-local and piped over stdin/stdout —
no token is required or checked.

---

## Tools

Tools are split by audience: **agent-facing** tools return typed JSON a program can
reason over directly; **human-facing UI** tools (below) render a Prefab UI widget meant
for a person to look at.

### Agent-facing tools — read-only

| Tool | Tags | Description |
|---|---|---|
| `rrt_config` | config, inspection | Resolved rrt config as JSON |
| `rrt_doctor` | config, inspection | Pre-commit / lefthook / husky / workflow / CI artifact-protection checks |
| `rrt_version` | versioning | Current version per configured group |
| `rrt_validate_branch` | validation | Conventional branch naming check |
| `rrt_validate_commit` | validation | Conventional commit subject check |
| `rrt_changelog` | changelog | Unreleased entries or full content |
| `rrt_eol` | eol, inspection | Host/project EOL status per language against policy |
| `rrt_release_check` | release, inspection | Version/pin/changelog target validation per group |
| `rrt_sync_check` | sync, inspection | Newer upstream package versions (not idempotent — network) |
| `rrt_folder_check` | folders, inspection | Folder structure policy violations |
| `rrt_docs_check` | docs, inspection | `.rrt/docs.lock.toml` drift status |

### Agent-facing tools — mutating (default dry_run=True)

| Tool | Tags | Description |
|---|---|---|
| `rrt_bump` | versioning | Semver bump — preview or apply |
| `rrt_branch_new` | git | Create conventionally-named branch |
| `rrt_init_run` | init, config | Run `rrt init` with selected target |
| `rrt_publish_snapshot` | git, publishing | Force-push a single-commit snapshot of tracked content to a secondary remote; `exclude` drops specific glob patterns from the snapshot |

### Agent-facing tools — lock-snapshot readers

These four are thin `read_lock()` wrappers around a small, readable TOML file at a fixed
path — if your client can read files directly, `Read .rrt/<name>.lock.toml` is
equivalent, and each reflects the *last* snapshot-writing operation (`--snapshot` for
health/tree/artifacts, `rrt drift generate` for drift), not current state — they do not
run the corresponding `--check`. `.rrt/health.lock.toml` specifically can also carry EOL
and folder results merged in by `rrt eol --snapshot` / `rrt folder --snapshot`, not only
`rrt doctor --snapshot`.

| Tool | Tags | Description |
|---|---|---|
| `rrt_health` | locks, inspection | `.rrt/health.lock.toml` contents |
| `rrt_drift` | locks, inspection | `.rrt/drift.lock.toml` contents |
| `rrt_tree` | locks, inspection | `.rrt/tree.lock.toml` contents |
| `rrt_artifacts` | locks, inspection | `.rrt/artifacts.lock.toml` contents |

---

## Human-facing UI

Interactive [Prefab UI](https://prefab.prefect.io) apps rendered in
MCP-capable clients (Claude Code, Claude Desktop). All are read-only. If you are a
headless agent that needs the underlying values to reason over, call the matching
agent-facing tool above instead of one of these.

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
chooses from data exposed by `rrt://locks/{name}` or other resources. These two tools
are registered by the third-party `GenerativeUI` provider, not by rrt itself, and sit
outside the agent-facing / human-facing split above.

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

## Prompt phrasings that work

Agents route on triggers, not on capabilities. These reliably route to the MCP tools
rather than to hand-editing or shelling out — name `rrt` explicitly, and name the
*moment* ("before you create it", "before you open the PR"):

```
"Check with rrt whether this branch name will pass the hooks before you create it."
→ calls rrt_validate_branch

"Use rrt to preview a minor bump — dry run — and show me every file it would touch."
→ calls rrt_bump with level="minor", dry_run=True

"Read the Unreleased changelog with rrt before adding an entry, so you don't duplicate one."
→ calls rrt_changelog

"Run rrt doctor and tell me which hook integrations are missing."
→ calls rrt_doctor

"Before you write that commit message, validate the subject with rrt."
→ calls rrt_validate_commit

"What version is this repo at according to rrt?"
→ calls rrt_version — not "what's the version", which invites reading a random file

"Run rrt release check before you open the PR."
→ calls rrt_release_check
```

See [Get your AI agent to actually use rrt](https://github.com/Anselmoo/repo-release-tools#get-your-ai-agent-to-actually-use-rrt)
in the README for a copyable instruction-file snippet that biases your own agent toward
these phrasings automatically.
"""

# Ordered source-owned topic docs for docs generation.
SOURCE_OWNED_TOPIC_DOCS: tuple[tuple[str, str], ...] = (("mcp-server", MCP_SERVER_DOC),)
