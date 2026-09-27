"""Tests for repo_release_tools.version.scheme (issue #259, T1.2)."""

from __future__ import annotations

import subprocess
import sys

import pytest

from repo_release_tools.version.scheme import (
    PEP440_TARGET_KINDS,
    VERSION_SCHEMES,
    infer_version_scheme,
)


def test_version_schemes_are_the_single_source_of_truth() -> None:
    assert VERSION_SCHEMES == ("semver", "pep440", "calver")
    assert PEP440_TARGET_KINDS == frozenset({"pep621", "python_version"})


@pytest.mark.parametrize(
    ("kind", "current", "expected"),
    [
        pytest.param("pep621", "2026.05.15", "calver", id="calver-wins-over-python-kind"),
        pytest.param("package_json", "2026.05", "calver", id="calver-yyyy-mm"),
        pytest.param(None, "2026.5.15.2", "calver", id="calver-micro"),
        pytest.param("pep621", "1.2.3rc1", "pep440", id="pep621"),
        pytest.param("python_version", "1.2.3", "pep440", id="python-version"),
        pytest.param("package_json", "1.2.3-rc.1", "semver", id="package-json"),
        pytest.param("cargo_toml", "1.2.3", "semver", id="cargo"),
        pytest.param(None, "1.2.3", "semver", id="section-field-target"),
    ],
)
def test_infer_version_scheme(kind: str | None, current: str, expected: str) -> None:
    assert infer_version_scheme(kind, current) == expected


def test_scheme_module_never_imports_the_config_layer() -> None:
    """The leaf stays acyclic: importing it must not pull in repo_release_tools.config."""
    code = (
        "import sys, repo_release_tools.version.scheme as s; "
        "assert 'repo_release_tools.config' not in sys.modules, 'config imported'"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
