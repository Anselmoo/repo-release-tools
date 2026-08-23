"""Tests for the [tool.rrt.artifact_protection] config section."""

from __future__ import annotations

from pathlib import Path

import pytest

from repo_release_tools.config import (
    ArtifactProtection,
    ConsumedArtifact,
    load_config,
)
from repo_release_tools.config import artifact_protection as ap

_BASE_RRT_CONFIG = """\
[tool.rrt]

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[project]
name = "example"
version = "0.1.0"
"""

_SPEC_BLOCK = """
[tool.rrt.artifact_protection]
protected_refs = ["main"]

[[tool.rrt.artifact_protection.consumed]]
job = "build:report_html"
ref = "$CI_DEFAULT_BRANCH"
artifacts = ["artifacts/manifest.json", "artifacts/report.html"]
consumed_by = [".gitlab/65-docs.yml", ".gitlab/60-pages.yml"]
reason = "docs performance page and Pages report.html fall back to the last successful main build"
"""


def _write_cfg(tmp_path: Path, extra: str) -> None:
    (tmp_path / "pyproject.toml").write_text(_BASE_RRT_CONFIG + extra, encoding="utf-8")


# ---------------------------------------------------------------------------
# Happy path — the exact spec block parses into the model
# ---------------------------------------------------------------------------


def test_load_config_artifact_protection_full_spec_block(tmp_path: Path) -> None:
    """The exact spec TOML block parses into ArtifactProtection/ConsumedArtifact."""
    _write_cfg(tmp_path, _SPEC_BLOCK)
    cfg = load_config(tmp_path)

    assert isinstance(cfg.artifact_protection, ArtifactProtection)
    assert cfg.artifact_protection.protected_refs == ("main",)
    assert len(cfg.artifact_protection.consumed) == 1

    entry = cfg.artifact_protection.consumed[0]
    assert isinstance(entry, ConsumedArtifact)
    assert entry.job == "build:report_html"
    assert entry.ref == "$CI_DEFAULT_BRANCH"
    assert entry.artifacts == ("artifacts/manifest.json", "artifacts/report.html")
    assert entry.consumed_by == (".gitlab/65-docs.yml", ".gitlab/60-pages.yml")
    assert entry.reason == (
        "docs performance page and Pages report.html fall back to the last successful main build"
    )


def test_job_value_with_multiple_colons_is_preserved_exactly(tmp_path: Path) -> None:
    """A job name with multiple colons must never be split or transformed."""
    _write_cfg(
        tmp_path,
        """
[[tool.rrt.artifact_protection.consumed]]
job = "build:report_html:bundle"
ref = "main"
artifacts = ["artifacts/bundle.zip"]
consumed_by = [".gitlab/deploy.yml"]
reason = "bundle reused by deploy job"
""",
    )
    cfg = load_config(tmp_path)

    assert cfg.artifact_protection is not None
    assert cfg.artifact_protection.consumed[0].job == "build:report_html:bundle"


# ---------------------------------------------------------------------------
# Section absence
# ---------------------------------------------------------------------------


def test_load_config_artifact_protection_section_absent() -> None:
    """When no [tool.rrt.artifact_protection] key is present, config field is None."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        (p / "pyproject.toml").write_text(_BASE_RRT_CONFIG, encoding="utf-8")
        cfg = load_config(p)
        assert cfg.artifact_protection is None


def test_load_config_artifact_protection_empty_table_defaults(tmp_path: Path) -> None:
    """[tool.rrt.artifact_protection] with no fields uses all defaults."""
    _write_cfg(tmp_path, "\n[tool.rrt.artifact_protection]\n")
    cfg = load_config(tmp_path)

    assert isinstance(cfg.artifact_protection, ArtifactProtection)
    assert cfg.artifact_protection.protected_refs == ()
    assert cfg.artifact_protection.consumed == ()


# ---------------------------------------------------------------------------
# Non-table section
# ---------------------------------------------------------------------------


def test_load_artifact_protection_rejects_non_table() -> None:
    with pytest.raises(ValueError, match="tool.rrt.artifact_protection must be a table"):
        ap._load_artifact_protection("oops")


# ---------------------------------------------------------------------------
# consumed entry missing job
# ---------------------------------------------------------------------------


def test_consumed_entry_missing_job_names_the_offending_table() -> None:
    with pytest.raises(
        ValueError,
        match=r"tool\.rrt\.artifact_protection\.consumed\[0\]\.job is required",
    ):
        ap._load_artifact_protection(
            {
                "consumed": [
                    {
                        "ref": "main",
                        "artifacts": ["artifacts/report.html"],
                        "consumed_by": [".gitlab/60-pages.yml"],
                        "reason": "docs fallback",
                    },
                ],
            },
        )


def test_consumed_entry_missing_ref_names_the_offending_table() -> None:
    with pytest.raises(
        ValueError,
        match=r"tool\.rrt\.artifact_protection\.consumed\[0\]\.ref is required",
    ):
        ap._load_artifact_protection(
            {
                "consumed": [
                    {
                        "job": "build:report_html",
                        "artifacts": ["artifacts/report.html"],
                        "consumed_by": [".gitlab/60-pages.yml"],
                        "reason": "docs fallback",
                    },
                ],
            },
        )


def test_consumed_entry_missing_artifacts_raises() -> None:
    with pytest.raises(
        ValueError,
        match=r"tool\.rrt\.artifact_protection\.consumed\[0\]\.artifacts must not be empty",
    ):
        ap._load_artifact_protection(
            {
                "consumed": [
                    {
                        "job": "build:report_html",
                        "ref": "main",
                        "consumed_by": [".gitlab/60-pages.yml"],
                        "reason": "docs fallback",
                    },
                ],
            },
        )


def test_consumed_entry_missing_consumed_by_raises() -> None:
    with pytest.raises(
        ValueError,
        match=r"tool\.rrt\.artifact_protection\.consumed\[0\]\.consumed_by must not be empty",
    ):
        ap._load_artifact_protection(
            {
                "consumed": [
                    {
                        "job": "build:report_html",
                        "ref": "main",
                        "artifacts": ["artifacts/report.html"],
                        "reason": "docs fallback",
                    },
                ],
            },
        )


def test_consumed_entry_reason_optional_defaults_to_empty_string() -> None:
    result = ap._load_artifact_protection(
        {
            "consumed": [
                {
                    "job": "build:report_html",
                    "ref": "main",
                    "artifacts": ["artifacts/report.html"],
                    "consumed_by": [".gitlab/60-pages.yml"],
                },
            ],
        },
    )
    assert result is not None
    assert result.consumed[0].reason == ""


# ---------------------------------------------------------------------------
# consumed not a table / not a list
# ---------------------------------------------------------------------------


def test_consumed_must_be_array_of_tables() -> None:
    with pytest.raises(
        ValueError,
        match="tool.rrt.artifact_protection.consumed must be an array of tables",
    ):
        ap._load_artifact_protection({"consumed": "oops"})


def test_consumed_entry_must_be_a_table() -> None:
    with pytest.raises(
        ValueError,
        match=r"tool\.rrt\.artifact_protection\.consumed\[0\] must be a table",
    ):
        ap._load_artifact_protection({"consumed": ["oops"]})


def test_protected_refs_must_be_a_list_of_strings() -> None:
    with pytest.raises(
        ValueError,
        match="tool.rrt.artifact_protection.protected_refs must be a list of strings",
    ):
        ap._load_artifact_protection({"protected_refs": [1]})


def test_protected_refs_rejects_empty_strings() -> None:
    with pytest.raises(
        ValueError,
        match="tool.rrt.artifact_protection.protected_refs must not contain empty strings",
    ):
        ap._load_artifact_protection({"protected_refs": ["   "]})


# ---------------------------------------------------------------------------
# Local module helpers — direct unit tests for error paths, mirrors
# tests/folders/test_folders_config_extra.py's helper coverage style.
# ---------------------------------------------------------------------------


def test_required_job_helper_error_paths() -> None:
    with pytest.raises(ValueError, match="job is required"):
        ap._required_job(None, label="job")

    with pytest.raises(ValueError, match="job must be a non-empty string"):
        ap._required_job("   ", label="job")

    with pytest.raises(ValueError, match="job must be a non-empty string"):
        ap._required_job(1, label="job")

    # Never transformed: internal whitespace and colons are preserved exactly.
    assert ap._required_job("build: weird  spacing", label="job") == "build: weird  spacing"


def test_required_string_helper_error_paths() -> None:
    with pytest.raises(ValueError, match="ref is required"):
        ap._required_string(None, label="ref")

    with pytest.raises(ValueError, match="ref must be a non-empty string"):
        ap._required_string("   ", label="ref")

    with pytest.raises(ValueError, match="ref must be a non-empty string"):
        ap._required_string(1, label="ref")

    assert ap._required_string("  main  ", label="ref") == "main"


def test_optional_string_helper_error_paths() -> None:
    assert ap._optional_string(None, default="d", label="reason") == "d"
    assert ap._optional_string("  ", default="d", label="reason") == "d"
    assert ap._optional_string("  because  ", default="d", label="reason") == "because"

    with pytest.raises(ValueError, match="reason must be a string"):
        ap._optional_string(1, default="d", label="reason")


# ---------------------------------------------------------------------------
# Dataclass-level validate() guards (defense-in-depth, mirrors FolderPolicyConfig style)
# ---------------------------------------------------------------------------


def test_consumed_artifact_validate_guards() -> None:
    with pytest.raises(ValueError, match="job must be a non-empty string"):
        ConsumedArtifact(
            job=" ",
            ref="main",
            artifacts=("a",),
            consumed_by=("b",),
        ).validate()

    with pytest.raises(ValueError, match="ref must be a non-empty string"):
        ConsumedArtifact(
            job="build:x",
            ref=" ",
            artifacts=("a",),
            consumed_by=("b",),
        ).validate()

    with pytest.raises(ValueError, match="must declare at least one artifact"):
        ConsumedArtifact(
            job="build:x",
            ref="main",
            artifacts=(),
            consumed_by=("b",),
        ).validate()

    with pytest.raises(ValueError, match="must declare at least one consumed_by entry"):
        ConsumedArtifact(
            job="build:x",
            ref="main",
            artifacts=("a",),
            consumed_by=(),
        ).validate()

    ConsumedArtifact(
        job="build:x",
        ref="main",
        artifacts=("a",),
        consumed_by=("b",),
        reason="because",
    ).validate()


def test_artifact_protection_validate_delegates_to_consumed_entries() -> None:
    with pytest.raises(ValueError, match="must declare at least one artifact"):
        ArtifactProtection(
            consumed=(ConsumedArtifact(job="x", ref="main", artifacts=(), consumed_by=("b",)),),
        ).validate()

    ArtifactProtection(protected_refs=("main",)).validate()
