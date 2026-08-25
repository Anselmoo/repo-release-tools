"""Tests for PEP 440 validation and PEP 440 <-> SemVer conversion helpers."""

from __future__ import annotations

from repo_release_tools.version.pep440 import (
    has_local_segment,
    is_valid,
    pep440_dev_to_semver,
)

# ---------------------------------------------------------------------------
# is_valid
# ---------------------------------------------------------------------------


def test_is_valid_plain_release() -> None:
    assert is_valid("2.0.0") is True


def test_is_valid_alpha_prerelease() -> None:
    assert is_valid("2.0.0-alpha.1") is True


def test_is_valid_beta_prerelease() -> None:
    assert is_valid("2.0.0-beta.2") is True


def test_is_valid_rc_prerelease() -> None:
    assert is_valid("2.0.0-rc.3") is True


def test_is_valid_canonical_pre_release_spelling() -> None:
    assert is_valid("2.0.0b2") is True


def test_is_valid_dev_release() -> None:
    assert is_valid("0.2.0.dev12345601") is True


def test_is_valid_local_segment() -> None:
    assert is_valid("2.0.0+build.42") is True


def test_is_valid_rejects_garbage() -> None:
    assert is_valid("not-a-version") is False


def test_is_valid_rejects_empty_string() -> None:
    assert is_valid("") is False


# ---------------------------------------------------------------------------
# has_local_segment
# ---------------------------------------------------------------------------


def test_has_local_segment_true_for_build_metadata() -> None:
    assert has_local_segment("2.0.0+build.42") is True


def test_has_local_segment_false_for_plain_release() -> None:
    assert has_local_segment("2.0.0") is False


def test_has_local_segment_false_for_prerelease_without_local() -> None:
    assert has_local_segment("2.0.0-beta.2") is False


def test_has_local_segment_false_for_invalid_version() -> None:
    assert has_local_segment("not-a-version") is False


# ---------------------------------------------------------------------------
# pep440_dev_to_semver
# ---------------------------------------------------------------------------


def test_pep440_dev_to_semver_dev_release() -> None:
    assert pep440_dev_to_semver("0.2.0.dev12345601") == "0.2.0-dev.12345601"


def test_pep440_dev_to_semver_release_unchanged() -> None:
    assert pep440_dev_to_semver("1.2.3") == "1.2.3"


def test_pep440_dev_to_semver_large_run_id() -> None:
    assert pep440_dev_to_semver("0.2.0.dev9999999901") == "0.2.0-dev.9999999901"
