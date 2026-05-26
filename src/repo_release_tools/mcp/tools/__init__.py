"""Tool registration for the rrt MCP server — structured tool modules.

## Overview

This package houses all rrt **MCP tools** — the callable functions that AI assistants
invoke to inspect and mutate repo state.  Each module corresponds to one functional domain
and exposes a single `register(mcp)` function that attaches its tools to the FastMCP
instance.

`register_tools(mcp)` (the public entry-point in this `__init__`) calls all six module
registrations in dependency order.

## Tool modules

### `config_tools` → `rrt_config`, `rrt_doctor`

- **`rrt_config`** — Returns the current `[tool.rrt]` configuration as a JSON object.
  When no config is found the tool returns `{"error": "..."}` rather than raising.
- **`rrt_doctor`** — Checks whether the project's automation tooling is wired correctly:
  pre-commit hooks, lefthook, husky, and GitHub Actions workflow files.  Returns a
  `DoctorResponse` with a `CheckResult` per component.

### `lock_tools` → `rrt_health`, `rrt_drift`, `rrt_tree`, `rrt_artifacts`

- **`rrt_health`** — Reads `.rrt/health.lock.toml` and returns all health check entries
  (status, message, updated_at) as a list.
- **`rrt_drift`** — Reads `.rrt/drift.lock.toml` and returns source drift entries.
  Drift indicates that source files have changed since the last `rrt drift update`.
- **`rrt_tree`** — Reads `.rrt/tree.lock.toml` and returns the tree snapshot metadata
  (tree_hash, entry_count, updated_at).
- **`rrt_artifacts`** — Reads `.rrt/artifacts.lock.toml` and returns registered artifact
  file metadata (path, description, hash, updated_at).
### `version_tools` → `rrt_version`, `rrt_bump`

- **`rrt_version`** — Returns the current version for each configured version group.
  Safe to call at any time; never modifies files.
- **`rrt_bump`** — Preview or apply a semver bump across all version targets.  Defaults to
  `dry_run=True` for safety; set `dry_run=False` only after the user explicitly confirms.
  Accepts `level` = `"major"`, `"minor"`, `"patch"`, `"alpha"`, `"beta"`, or `"rc"`.

### `validation_tools` → `rrt_validate_branch`, `rrt_validate_commit`

- **`rrt_validate_branch`** — Validates a branch name against the project's configured
  allow-list (conventional branch types + optional `extra_branch_types`).  Returns a
  `BranchValidationResult` with `valid`, `branch`, and an optional `reason` on failure.
- **`rrt_validate_commit`** — Validates a commit subject line against the Conventional
  Commits spec as enforced by rrt's hook.  Returns a `CommitValidationResult`.

### `changelog_tools` → `rrt_changelog`

- **`rrt_changelog`** — Reads `CHANGELOG.md` and returns the entries for a given section
  (default: `"Unreleased"`). Returns a `ChangelogResponse`.

### `git_tools` → `rrt_branch_new`

- **`rrt_branch_new`** — Creates (or previews) a conventional branch from a type + slug.
  Uses rrt branch naming helpers and runs `git checkout -b` when `dry_run=False`.
  Always defaults to `dry_run=True`. Returns a `BranchResult` with the full branch name
  and a suggested commit title.

## Response conventions

All tools return Pydantic models (see `mcp.models`) serialised to JSON by FastMCP.
Tools that can fail return an `error` field rather than raising an exception, so the
AI assistant can report the failure gracefully without a tool error traceback.

All mutating tools (`rrt_bump`, `rrt_branch_new`) default to `dry_run=True`.

## Adding a new tool module

1. Create `src/repo_release_tools/mcp/tools/my_tools.py` with a `register(mcp)` function.
2. Import and call it in `register_tools()` here.
3. Add corresponding tests in `tests/mcp/test_tools.py`.
"""

from __future__ import annotations

from fastmcp import FastMCP

from .changelog_tools import register as register_changelog
from .config_tools import register as register_config
from .git_tools import register as register_git
from .lock_tools import register as register_locks
from .validation_tools import register as register_validation
from .version_tools import register as register_version


def register_tools(mcp: FastMCP) -> None:
    """Register all rrt tools on the given FastMCP instance."""
    register_config(mcp)
    register_locks(mcp)
    register_version(mcp)
    register_validation(mcp)
    register_changelog(mcp)
    register_git(mcp)
