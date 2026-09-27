"""Tests for the ``repo_release_tools.version`` package's lazy re-exports."""

from __future__ import annotations

import subprocess
import sys

import pytest

import repo_release_tools.version as version_pkg
from repo_release_tools.version import targets


def test_lazy_target_export_resolves_to_targets_module_and_is_cached() -> None:
    version_pkg.__dict__.pop("read_current_version", None)

    resolved = version_pkg.read_current_version

    assert resolved is targets.read_current_version
    assert version_pkg.__dict__["read_current_version"] is targets.read_current_version


def test_every_public_name_is_resolvable() -> None:
    for name in version_pkg.__all__:
        assert getattr(version_pkg, name) is not None


def test_unknown_attribute_raises_attribute_error() -> None:
    with pytest.raises(AttributeError, match="has no attribute 'does_not_exist'"):
        _ = version_pkg.does_not_exist


def test_importing_config_first_does_not_cycle_through_version_targets() -> None:
    """config.model imports semver constants; that must not re-enter config via targets."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import repo_release_tools.config as c; print(sorted(c.VALID_PRERELEASE_BASES))",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "['auto', 'major', 'minor', 'patch']"
