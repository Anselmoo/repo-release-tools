"""Prompt templates for the rrt MCP server — reusable AI assistant guidance.

## Overview

This module registers **MCP prompt templates** on the FastMCP server.  Prompts differ from
tools in that they return plain text that the AI assistant uses as a starting point for
reasoning — they don't invoke any code or return structured data.  Instead, each prompt
expands a parameterised Markdown template that guides the assistant through a rrt workflow.

Prompts appear in the MCP host's prompt palette (e.g. the `/` menu in Claude Desktop) and
can be invoked by name with optional arguments.

## Available prompts

### `release_workflow`

**Trigger:** user wants a step-by-step release guide

**Parameters:**
- `version_level` (default `"minor"`) — semver bump level: `major`, `minor`, or `patch`
- `repo_name` (default `"this repo"`) — repository name for personalised output

**Output:** An eight-step numbered guide covering `rrt bump`, changelog review,
`rrt git commit`, health checks, branch creation, PR, and tagging.  References the
`rrt_health`, `rrt_drift`, and `rrt_version` MCP tools for in-chat inspection.

---

### `version_strategy`

**Trigger:** user wants help deciding which semver level to bump

**Parameters:**
- `change_summary` (default `""`) — free-form description of the changes since the last
  release

**Output:** A structured analysis prompt that the assistant fills in with a recommendation
(`major` / `minor` / `patch`), one-line rationale, and the exact `rrt bump` command to run.

Rules embedded in the prompt:
- `major` → breaking API or behaviour change (`BREAKING CHANGE` footer)
- `minor` → new feature, backward-compatible (`feat:` commits)
- `patch` → bug fix, docs, maintenance (`fix:`, `docs:`, `chore:`)

---

### `branch_strategy`

**Trigger:** user is about to create a branch and wants naming guidance

**Parameters:**
- `task_description` (default `""`) — what the branch is for
- `context_hint` (default `""`) — additional context (e.g. module name, ticket number)

**Output:** A structured template listing all conventional branch types (`feat`, `fix`,
`chore`, `docs`, `refactor`, `test`, `ci`, `perf`, `style`, `build`) with slug rules and
the exact `rrt branch new` command to create the branch.

---

### `commit_message_guide`

**Trigger:** user wants to write a Conventional Commit message

**Parameters:**
- `staged_summary` (default `""`) — description of staged changes (`git diff --cached`)
- `branch_name` (default `""`) — current branch name for additional context

**Output:** A Conventional Commits formatting guide with format, rules, type list, and
three worked examples.  The assistant drafts the subject line and an optional body/footer.

Format: `<type>[(<scope>)]: <description>` — max 72 chars, imperative mood, no period.

---

### `changelog_entry`

**Trigger:** user wants to add an entry to `CHANGELOG.md`

**Parameters:**
- `commit_summary` (default `""`) — one-line description of the change
- `section_hint` (default `""`) — target Keep-a-Changelog section name

**Output:** A drafter prompt listing all Keep-a-Changelog sections (`Added`, `Changed`,
`Deprecated`, `Removed`, `Fixed`, `Security`, `Maintenance`) with style rules and two
example bullets.  The assistant responds with the section name and full bullet text.

Note: `Maintenance` entries (chore/ci/build/test/deps) do NOT require a changelog entry
per the rrt convention — the prompt explains this explicitly.

---

### `config_setup`

**Trigger:** user wants to add `[tool.rrt]` to a project

**Parameters:**
- `project_type` (default `"python"`) — one of `"python"`, `"node"`, `"go"` (unknown values
  fall back to `"python"`)

**Output:** A five-step setup guide covering install, `rrt init`, a starter config snippet
tailored to the project type, key config options, and validation commands.

Config snippet variants:
- `python` → `pep621` version target pointing at `pyproject.toml`
- `node` → `package_json` target pointing at `package.json`
- `go` → `go_version` target pointing at `cmd/root.go`

---

### `release_readiness`

**Trigger:** user is about to cut a release and wants a pre-flight checklist

**Parameters:**
- `version` (default `""`) — pending version string (displayed as `v{version}`)
- `target_env` (default `"production"`) — deployment environment label

**Output:** A six-section Markdown checklist covering version, changelog, health & drift,
branch validation, CI, and the final `rrt bump` + commit + push sequence.  Each section
has specific MCP tool calls to make and a pass/fail/warn verdict format.

---

## Usage example

```python
from repo_release_tools.mcp.prompts import register_prompts
from fastmcp import FastMCP

mcp = FastMCP("my-server")
register_prompts(mcp)
# Prompts are now available as mcp.get_prompt("release_workflow") etc.
```
"""

from __future__ import annotations

from fastmcp import FastMCP

from repo_release_tools import __version__ as _PKG_VERSION


def register_prompts(mcp: FastMCP) -> None:
    """Register reusable prompt templates on *mcp*."""

    @mcp.prompt(
        title="Release Workflow Guide",
        tags={"release", "workflow"},
        version=_PKG_VERSION,
        meta={"domain": "rrt", "surface": "mcp"},
    )
    def release_workflow(version_level: str = "minor", repo_name: str = "this repo") -> str:
        """Step-by-step rrt release guide for the given semver bump level."""
        return (
            f"# Release workflow for {repo_name} ({version_level} bump)\n\n"
            "Follow these steps to cut a release with repo-release-tools:\n\n"
            f"1. **Preview the bump**: `rrt bump {version_level} --dry-run`\n"
            f"2. **Apply the bump**: `rrt bump {version_level}`\n"
            "3. **Review changelog**: Ensure `[Unreleased]` has accurate entries.\n"
            "4. **Commit**: `rrt git commit`\n"
            "5. **Check health**: `rrt doctor && rrt release check`\n"
            "6. **Create release branch**: follows `release/v{version}` pattern.\n"
            "7. **Push and open PR**: Push the release branch and open a pull request.\n"
            "8. **After merge**: Tag the commit and publish the GitHub release.\n\n"
            "Use `rrt_health`, `rrt_drift`, and `rrt_version` tools to inspect current state."
        )

    @mcp.prompt(
        title="Version Strategy Advisor",
        tags={"versioning", "strategy"},
        version=_PKG_VERSION,
        meta={"domain": "rrt", "surface": "mcp"},
    )
    def version_strategy(change_summary: str = "") -> str:
        """Recommend the correct semver bump level based on a summary of changes."""
        return (
            "# Version bump strategy\n\n"
            "Analyse the following change summary and recommend a semver bump level "
            "(major | minor | patch) with rationale:\n\n"
            f"**Change summary:**\n{change_summary or '(no summary provided — describe your changes)'}\n\n"
            "**Rules:**\n"
            "- `major`: breaking API or behaviour change (BREAKING CHANGE in commit footer)\n"
            "- `minor`: new feature, backward-compatible (`feat:` commits)\n"
            "- `patch`: bug fix, docs, or maintenance (`fix:`, `docs:`, `chore:`)\n\n"
            "Respond with: recommended level, one-line rationale, and the rrt command to run."
        )

    @mcp.prompt(
        title="Branch Strategy Guide",
        tags={"git", "branching", "workflow"},
        version=_PKG_VERSION,
        meta={"domain": "rrt", "surface": "mcp"},
    )
    def branch_strategy(task_description: str = "", context_hint: str = "") -> str:
        """Suggest a conventional branch type and slug for a task description."""
        task = task_description or "(no task described — describe what you are working on)"
        hint = f"\n**Additional context:** {context_hint}" if context_hint else ""
        return (
            "# Branch strategy\n\n"
            f"**Task:** {task}{hint}\n\n"
            "Pick the right branch type and build a slug using the rules below:\n\n"
            "**Branch types:**\n"
            "- `feat` — new feature or capability\n"
            "- `fix` — bug fix or regression correction\n"
            "- `chore` — housekeeping, dependency update, or tooling change\n"
            "- `docs` — documentation only\n"
            "- `refactor` — code restructuring with no behaviour change\n"
            "- `test` — test additions or corrections\n"
            "- `ci` — CI/CD pipeline changes\n"
            "- `perf` — performance improvement\n"
            "- `style` — formatting or linting (no logic change)\n"
            "- `build` — build system or packaging changes\n\n"
            "**Slug rules:** kebab-case, max 60 characters, lowercase, no punctuation except hyphens.\n\n"
            "**Format:** `<type>/<slug>` e.g. `feat/add-mcp-server`, `fix/config-loader-crash`\n\n"
            '**Command:** `rrt branch new <type> "<description>" [--scope <scope>]`\n\n'
            "Respond with: chosen type, slug, full branch name, and the exact rrt command to run."
        )

    @mcp.prompt(
        title="Commit Message Guide",
        tags={"git", "commit", "workflow"},
        version=_PKG_VERSION,
        meta={"domain": "rrt", "surface": "mcp"},
    )
    def commit_message_guide(staged_summary: str = "", branch_name: str = "") -> str:
        """Draft a Conventional Commits subject line from staged changes and branch context."""
        staged = staged_summary or "(no staged summary — describe what you changed)"
        branch = f"\n**Current branch:** `{branch_name}`" if branch_name else ""
        return (
            "# Conventional commit message\n\n"
            f"**Staged changes:** {staged}{branch}\n\n"
            "Write a commit subject following Conventional Commits:\n\n"
            "**Format:** `<type>[(<scope>)]: <description>`\n\n"
            "**Rules:**\n"
            "- Max 72 characters for the subject line\n"
            "- Imperative mood: 'add', 'fix', 'remove' — not 'added', 'fixes'\n"
            "- No period at the end\n"
            "- `scope` is optional; use it for sub-component clarity (e.g. `fix(cli): …`)\n"
            "- Breaking changes: append `!` after type/scope OR add `BREAKING CHANGE: …` footer\n\n"
            "**Types:** feat | fix | chore | docs | refactor | test | ci | perf | style | build\n\n"
            "**Examples:**\n"
            "- `feat(mcp): add rrt_branch_new tool with dry-run support`\n"
            "- `fix: resolve config loader crash on missing pyproject.toml`\n"
            "- `chore!: drop Python 3.11 support`\n\n"
            "**Command:** `rrt git commit` (auto-drafts from branch name)\n\n"
            "Respond with: the commit subject line and an optional body/footer if breaking."
        )

    @mcp.prompt(
        title="Changelog Entry Drafter",
        tags={"changelog", "workflow"},
        version=_PKG_VERSION,
        meta={"domain": "rrt", "surface": "mcp"},
    )
    def changelog_entry(commit_summary: str = "", section_hint: str = "") -> str:
        """Draft a Keep-a-Changelog bullet point from a commit or change summary."""
        summary = commit_summary or "(no summary — describe the change to document)"
        section = section_hint or "(auto-detect from change type)"
        return (
            "# Changelog entry drafter\n\n"
            f"**Change summary:** {summary}\n"
            f"**Target section:** {section}\n\n"
            "Write a Keep-a-Changelog bullet for the `[Unreleased]` block.\n\n"
            "**Sections and when to use them:**\n"
            "- `Added` — new features or capabilities\n"
            "- `Changed` — changes to existing behaviour\n"
            "- `Deprecated` — soon-to-be-removed features\n"
            "- `Removed` — features removed in this release\n"
            "- `Fixed` — bug fixes\n"
            "- `Security` — vulnerability fixes\n"
            "- `Maintenance` — chore, ci, build, test, deps (does NOT require a changelog entry)\n\n"
            "**Style rules:**\n"
            "- Imperative mood: 'Add', 'Fix', 'Remove'\n"
            "- One sentence, no trailing period\n"
            "- Reference tool/component in natural language: 'MCP server', 'CLI', 'config loader'\n\n"
            "**Example entries:**\n"
            "- `Added: MCP tool rrt_branch_new for creating conventional branches via AI assistants`\n"
            "- `Fixed: Config loader no longer crashes when pyproject.toml has no [tool.rrt] section`\n\n"
            "Respond with: the section name and the full bullet text."
        )

    @mcp.prompt(
        title="RRT Config Setup Guide",
        tags={"config", "setup", "workflow"},
        version=_PKG_VERSION,
        meta={"domain": "rrt", "surface": "mcp"},
    )
    def config_setup(project_type: str = "python") -> str:
        """Step-by-step guide for adding [tool.rrt] configuration to a project."""
        snippets: dict[str, str] = {
            "python": (
                "[tool.rrt]\n"
                'release_branch = "release/v{version}"\n'
                'changelog_file = "CHANGELOG.md"\n\n'
                "[[tool.rrt.version_targets]]\n"
                'path = "pyproject.toml"\n'
                'kind = "pep621"'
            ),
            "node": (
                '[tool.rrt]  # or "rrt" key in package.json\n'
                'release_branch = "release/v{version}"\n'
                'changelog_file = "CHANGELOG.md"\n\n'
                "[[tool.rrt.version_targets]]\n"
                'path = "package.json"\n'
                'kind = "package_json"'
            ),
            "go": (
                "[tool.rrt]  # in .rrt.toml\n"
                'release_branch = "release/v{version}"\n'
                'changelog_file = "CHANGELOG.md"\n\n'
                "[[tool.rrt.version_targets]]\n"
                'path = "cmd/root.go"\n'
                'kind = "go_version"'
            ),
        }
        snippet = snippets.get(project_type, snippets["python"])
        return (
            f"# rrt config setup ({project_type})\n\n"
            "Follow these steps to add `[tool.rrt]` to your project:\n\n"
            "**1. Install rrt:**\n"
            "```bash\nuv add --dev repo-release-tools\n# or: pip install repo-release-tools\n```\n\n"
            "**2. Run init (scaffolds config and CHANGELOG.md):**\n"
            "```bash\nrrt init\n```\n\n"
            "**3. Minimal starter config:**\n"
            f"```toml\n{snippet}\n```\n\n"
            "**Key config options:**\n"
            "- `release_branch` — branch name template; `{version}` is replaced on bump\n"
            "- `changelog_file` — path to your CHANGELOG.md\n"
            "- `version_targets` — files to update on `rrt bump`; kinds: `pep621`, `package_json`, `go_version`, `python_version`, or custom `pattern`\n"
            "- `pin_targets` — extra files kept in sync (e.g. CI action version pins)\n"
            "- `extra_branch_types` — add custom branch prefixes beyond the built-in set\n"
            "- `lock_command` — run after bump (e.g. `['uv', 'lock', '-U']`)\n\n"
            "**4. View the full JSON Schema for all options:**\n"
            "```bash\nrrt config --schema\n```\n"
            "Or read the `rrt://schema/config` MCP resource.\n\n"
            "**5. Validate your config:**\n"
            "```bash\nrrt config --validate\n```\n\n"
            "Respond with a tailored config snippet for the project structure you see."
        )

    @mcp.prompt(
        title="Release Readiness Checklist",
        tags={"release", "workflow", "validation"},
        version=_PKG_VERSION,
        meta={"domain": "rrt", "surface": "mcp"},
    )
    def release_readiness(version: str = "", target_env: str = "production") -> str:
        """Pre-release verification checklist: health, changelog, version, branch, and CI status."""
        ver_label = f"v{version}" if version else "<pending version>"
        return (
            f"# Release readiness — {ver_label} → {target_env}\n\n"
            "Work through each check before cutting the release.\n\n"
            "## 1. Version\n"
            "- [ ] Call `rrt_version` — confirm current version matches expectations\n"
            "- [ ] Call `rrt_bump <level> --dry-run` — verify the new version is correct\n\n"
            "## 2. Changelog\n"
            "- [ ] Call `rrt_changelog` (section=unreleased) — review pending entries\n"
            "- [ ] Ensure every user-visible change has a bullet under the right section\n"
            "- [ ] No empty `[Unreleased]` block (at least one non-Maintenance entry)\n\n"
            "## 3. Health & drift\n"
            "- [ ] Call `rrt_health` — all checks green (pre-commit, lefthook, workflows)\n"
            "- [ ] Call `rrt_drift` — no unexpected source changes since last snapshot\n"
            "- [ ] Call `rrt_artifacts` — artifact hashes match committed lock\n\n"
            "## 4. Branch\n"
            "- [ ] Call `rrt_validate_branch` with current branch name — must be valid\n"
            "- [ ] Confirm branch follows `release/v{version}` pattern (or project convention)\n\n"
            "## 5. CI\n"
            "- [ ] All CI jobs green on the release branch\n"
            "- [ ] No unresolved review comments on the PR\n\n"
            "## 6. Apply & ship\n"
            "- [ ] `rrt bump <level>` (without --dry-run) — apply version bump\n"
            "- [ ] `rrt git commit` — stage and commit the bump\n"
            "- [ ] Push release branch, merge PR, tag, publish GitHub release\n\n"
            "**Use `rrt_health_dashboard` and `rrt_doctor_dashboard` app tools for a visual overview.**\n\n"
            "Call each MCP tool above and report: pass ✓ / fail ✗ / warn ⚠ for each check."
        )
