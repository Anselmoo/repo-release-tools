"""Tests for MCP Pydantic response models."""

from __future__ import annotations

import pytest

pytest.importorskip("fastmcp", reason="[mcp] extra not installed")

from repo_release_tools.mcp.models import (
    BranchResult,
    BranchValidationResult,
    BumpGroupResult,
    ChangelogResponse,
    CheckResult,
    CommitValidationResult,
    ConfigError,
    DoctorResponse,
    LockError,
    RawLockData,
    VersionGroupResult,
)

pytestmark = pytest.mark.mcp


class TestCheckResult:
    def test_defaults(self) -> None:
        r = CheckResult(message="ok", ok=True, severity="ok")
        assert r.message == "ok"
        assert r.ok is True
        assert r.severity == "ok"

    def test_failed(self) -> None:
        r = CheckResult(message="missing", ok=False, severity="error")
        assert not r.ok


class TestDoctorResponse:
    def test_all_ok(self) -> None:
        ok = CheckResult(message="ok", ok=True, severity="ok")
        dr = DoctorResponse(pre_commit=ok, lefthook=ok, husky=ok, workflows=ok)
        assert dr.pre_commit.ok


class TestVersionGroupResult:
    def test_no_error(self) -> None:
        r = VersionGroupResult(group="main", version="1.2.3")
        assert r.error is None

    def test_with_error(self) -> None:
        r = VersionGroupResult(group="main", version="", error="file not found")
        assert r.error == "file not found"


class TestBumpGroupResult:
    def test_defaults(self) -> None:
        r = BumpGroupResult(group="main")
        assert r.dry_run is True
        assert r.applied is False
        assert r.current is None

    def test_applied(self) -> None:
        r = BumpGroupResult(group="main", current="1.0.0", new="1.1.0", dry_run=False, applied=True)
        assert r.applied is True


class TestBranchValidationResult:
    def test_valid(self) -> None:
        r = BranchValidationResult(valid=True, branch="feat/foo")
        assert r.reason is None

    def test_invalid(self) -> None:
        r = BranchValidationResult(valid=False, branch="bad", reason="no type prefix")
        assert r.reason == "no type prefix"


class TestCommitValidationResult:
    def test_valid(self) -> None:
        r = CommitValidationResult(valid=True, subject="feat: add thing")
        assert r.reason is None

    def test_invalid(self) -> None:
        r = CommitValidationResult(valid=False, subject="bad", reason="no colon")
        assert r.reason == "no colon"


class TestChangelogResponse:
    def test_defaults(self) -> None:
        r = ChangelogResponse(path="CHANGELOG.md", section="unreleased")
        assert r.entries == []
        assert r.content is None

    def test_with_entries(self) -> None:
        r = ChangelogResponse(path="CHANGELOG.md", section="unreleased", entries=["Added: foo"])
        assert len(r.entries) == 1


class TestLockError:
    def test_no_hint(self) -> None:
        r = LockError(error="not found")
        assert r.hint == ""

    def test_with_hint(self) -> None:
        r = LockError(error="not found", hint="run rrt doctor")
        assert r.hint == "run rrt doctor"


class TestConfigError:
    def test_error(self) -> None:
        r = ConfigError(error="no config")
        assert r.error == "no config"


class TestBranchResult:
    def test_dry_run(self) -> None:
        r = BranchResult(
            branch="feat/foo", created=False, dry_run=True, suggested_commit_title="feat: foo"
        )
        assert r.error is None

    def test_error(self) -> None:
        r = BranchResult(
            branch="", created=False, dry_run=True, suggested_commit_title="", error="oops"
        )
        assert r.error == "oops"


class TestRawLockData:
    def test_to_flat(self) -> None:
        r = RawLockData(data={"a": 1, "b": 2})
        assert r.to_flat() == {"a": 1, "b": 2}
