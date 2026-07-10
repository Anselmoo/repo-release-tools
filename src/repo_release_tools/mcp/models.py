"""Pydantic response models for the rrt MCP server tools.

## Overview

All rrt MCP tools return typed Pydantic models rather than raw dicts.  This guarantees
that every tool response is schema-valid and serialisable to JSON, which FastMCP converts
to a structured `TextContent` payload the AI assistant can parse reliably.

## Design principles

- **Immutable by default** — models are created once per tool call and not mutated
- **Optional error fields** — each model that can fail carries an `error: str | None` field;
  the assistant checks this before acting on the primary fields
- **Flat structure** — models are kept shallow (one level of nesting at most) so the AI can
  read the output without recursive traversal

## Model index

### `CheckResult`
Result of a single automation health check (pre-commit, lefthook, husky, or CI workflow).

Fields:
- `message` — human-readable outcome text
- `ok` — `True` when the check passed
- `severity` — one of `"ok"`, `"obsolete"`, `"warning"`, `"error"`

### `DoctorResponse`
Aggregated result of `rrt_doctor`, which checks whether a project's automation tooling
(pre-commit hooks, lefthook, husky, and GitHub Actions workflows) is correctly wired.

Fields — one `CheckResult` per toolchain component:
- `pre_commit`
- `lefthook`
- `husky`
- `workflows`

### `VersionGroupResult`
Reports the current version string for one version group as defined in `[tool.rrt]`.

Fields:
- `group` — the group name (defaults to `"default"` when there is only one group)
- `version` — current version string (e.g. `"1.4.2"`)
- `error` — set when the version file is missing or the pattern doesn't match

### `BumpGroupResult`
Preview or result of a version bump for one version group.  Always returned from
`rrt_bump`; `applied=False` and `new=None` when `dry_run=True`.

Fields:
- `group` — version group name
- `current` — version before bump (may be `None` on read error)
- `new` — version after bump (may be `None` when dry_run or on error)
- `dry_run` — whether the bump was simulated only
- `applied` — `True` when the file was actually written
- `error` — set when bumping failed (e.g. version file missing)

### `BranchValidationResult`
Result of `rrt_validate_branch` for a single branch name.

Fields:
- `valid` — `True` when the branch name satisfies the configured allow-list
- `branch` — the branch name that was validated
- `reason` — human-readable failure reason when `valid=False`

### `CommitValidationResult`
Result of `rrt_validate_commit` for a single commit subject line.

Fields:
- `valid` — `True` when the subject is a well-formed Conventional Commit
- `subject` — the subject that was validated
- `reason` — human-readable failure reason when `valid=False`

### `ChangelogResponse`
Content extracted from `CHANGELOG.md` by `rrt_changelog`.

Fields:
- `path` — absolute path of the changelog file
- `section` — the section that was read (e.g. `"Unreleased"`, `"1.4.0"`)
- `entries` — list of bullet-point strings within that section
- `content` — raw section text (set when `raw=True` is requested)

### `LockError`
Returned by lock-inspection tools when the requested lock file does not exist or
cannot be parsed.

Fields:
- `error` — error description
- `hint` — optional suggestion (e.g. `"Run rrt drift update to create the lock"`)

### `ConfigError`
Returned by config-reading tools when `[tool.rrt]` cannot be loaded.

Fields:
- `error` — error description

### `BranchResult`
Result of `rrt_branch_new` (create or preview a conventional branch).

Fields:
- `branch` — the full branch name that was created or would be created
- `created` — `True` when the branch was actually created in git
- `dry_run` — whether the operation was a preview only
- `suggested_commit_title` — a Conventional Commit title derived from the branch name,
  ready to paste into `rrt git commit`
- `error` — set when branch creation failed (e.g. branch already exists)

### `RawLockData`
Passthrough wrapper for arbitrary lock-style data when a structured tool model is not needed.

Fields:
- `data` — the parsed TOML dictionary

Methods:
- `to_flat()` — returns `self.data` directly; convenience method for tool handlers
  that flatten the response before serialisation
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CheckResult(BaseModel):
    """Result of a single automation health check."""

    message: str
    ok: bool
    severity: str


class DoctorResponse(BaseModel):
    """Aggregated doctor check results."""

    pre_commit: CheckResult
    lefthook: CheckResult
    husky: CheckResult
    workflows: CheckResult


class VersionGroupResult(BaseModel):
    """Current version for one version group."""

    group: str
    version: str
    error: str | None = None


class BumpGroupResult(BaseModel):
    """Bump preview or result for one version group."""

    group: str
    current: str | None = None
    new: str | None = None
    dry_run: bool = True
    applied: bool = False
    error: str | None = None


class BranchValidationResult(BaseModel):
    """Result of a branch name validation."""

    valid: bool
    branch: str
    reason: str | None = None


class CommitValidationResult(BaseModel):
    """Result of a commit subject validation."""

    valid: bool
    subject: str
    reason: str | None = None


class ChangelogResponse(BaseModel):
    """Changelog content response."""

    path: str
    section: str
    entries: list[str] = Field(default_factory=list)
    content: str | None = None


class LockError(BaseModel):
    """Returned when a lock file is missing."""

    error: str
    hint: str = ""


class ConfigError(BaseModel):
    """Returned when config cannot be loaded."""

    error: str


class BranchResult(BaseModel):
    """Result of a branch creation (or dry-run preview)."""

    branch: str
    created: bool
    dry_run: bool
    suggested_commit_title: str
    error: str | None = None


class PublishSnapshotResult(BaseModel):
    """Result of a publish-snapshot preview or force-push."""

    remote: str
    branch: str
    published: bool
    dry_run: bool
    error: str | None = None
    excluded_paths: tuple[str, ...] = ()


class RawLockData(BaseModel):
    """Passthrough wrapper for arbitrary lock file data."""

    data: dict[str, Any]

    def to_flat(self) -> dict[str, Any]:
        """Return the raw lock data as a flat dict."""
        return self.data
