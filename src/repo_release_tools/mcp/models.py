"""Pydantic response models for the rrt MCP server tools."""

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


class RawLockData(BaseModel):
    """Passthrough wrapper for arbitrary lock file data."""

    data: dict[str, Any]

    def to_flat(self) -> dict[str, Any]:
        """Return the raw lock data as a flat dict."""
        return self.data
