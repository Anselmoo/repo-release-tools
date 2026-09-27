"""Integration tests for RRT-VER-1 tier 2: per-target rendering in ``version/targets.py``.

Covers writing a canonical :class:`Version`/:class:`CalVersion` (not just a
pre-stringified value) through ``replace_all_versions_atomic``,
``replace_version_in_file`` and ``replace_pin_in_file``, a mixed-format group
(pep621 + package_json + gemspec + a pin) each getting its own spelling,
``post_policy`` atomicity, and a single-format-repo byte-identical regression.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from repo_release_tools.config import PinTarget, VersionTarget
from repo_release_tools.version.calver import CalVersion
from repo_release_tools.version.semver import Version
from repo_release_tools.version.targets import (
    replace_all_versions_atomic,
    replace_pin_in_file,
    replace_version_in_file,
)


def _pep621(tmp_path: Path, version: str = "1.0.0", *, fmt: str | None = None) -> VersionTarget:
    path = tmp_path / "pyproject.toml"
    path.write_text(f'[project]\nname = "x"\nversion = "{version}"\n', encoding="utf-8")
    return VersionTarget(path=path, kind="pep621", format=fmt)


def _package_json(tmp_path: Path, version: str = "1.0.0") -> VersionTarget:
    path = tmp_path / "package.json"
    path.write_text(json.dumps({"name": "x", "version": version}) + "\n", encoding="utf-8")
    return VersionTarget(path=path, kind="package_json")


def _gemspec(tmp_path: Path, version: str = "1.0.0") -> VersionTarget:
    path = tmp_path / "x.gemspec"
    path.write_text(f's.version = "{version}"\n', encoding="utf-8")
    return VersionTarget(path=path, kind="gemspec")


# ---------------------------------------------------------------------------
# Passing a canonical Version/CalVersion object directly (not a string).
# ---------------------------------------------------------------------------


def test_replace_version_in_file_accepts_version_object(tmp_path: Path) -> None:
    target = _pep621(tmp_path, "1.0.0")
    event = replace_version_in_file(target, Version(1, 2, 0), dry_run=False)
    assert event.new_version == "1.2.0"
    assert 'version = "1.2.0"' in target.path.read_text(encoding="utf-8")


def test_replace_all_versions_atomic_accepts_version_object(tmp_path: Path) -> None:
    target = _pep621(tmp_path, "1.0.0")
    events = replace_all_versions_atomic([target], Version(1, 2, 0), dry_run=False)
    assert [e.new_version for e in events] == ["1.2.0"]


def test_replace_all_versions_atomic_accepts_calversion_object(tmp_path: Path) -> None:
    path = tmp_path / "VERSION"
    path.write_text("2026.01.01\n", encoding="utf-8")
    target = VersionTarget(path=path, kind="pattern", pattern=r"(^)(\d{4}\.\d{2}\.\d{2})($)")
    events = replace_all_versions_atomic(
        [target], CalVersion(2026, 5, 15, scheme="YYYY.MM.DD"), dry_run=False
    )
    assert events[0].new_version == "2026.05.15"


def test_replace_pin_in_file_accepts_version_object(tmp_path: Path) -> None:
    path = tmp_path / "README.md"
    path.write_text("pinned: v1.0.0\n", encoding="utf-8")
    pin = PinTarget(path=path, pattern=r"(pinned: v)(\d+\.\d+\.\d+)($)")
    replace_pin_in_file(pin, Version(2, 0, 0), dry_run=False)
    assert "pinned: v2.0.0" in path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Mixed-format group: each target gets its own spelling of one canonical version.
# ---------------------------------------------------------------------------


def test_mixed_format_group_each_target_gets_its_own_spelling_dev(tmp_path: Path) -> None:
    pep621 = _pep621(tmp_path)
    package_json = _package_json(tmp_path)
    gemspec = _gemspec(tmp_path)
    new_version = Version(1, 0, 1, dev=0)  # canonical 1.0.1.dev0

    events = replace_all_versions_atomic(
        [pep621, package_json, gemspec], new_version, dry_run=False
    )

    by_path = {e.path: e.new_version for e in events}
    assert by_path[pep621.path] == "1.0.1.dev0"  # python default: PEP 440 for dev
    assert by_path[package_json.path] == "1.0.1-0.dev.0"  # semver default
    assert by_path[gemspec.path] == "1.0.1.a.dev.0"  # rubygems default

    assert 'version = "1.0.1.dev0"' in pep621.path.read_text(encoding="utf-8")
    assert json.loads(package_json.path.read_text(encoding="utf-8"))["version"] == "1.0.1-0.dev.0"
    assert 's.version = "1.0.1.a.dev.0"' in gemspec.path.read_text(encoding="utf-8")


def test_mixed_format_group_each_target_gets_its_own_spelling_rc(tmp_path: Path) -> None:
    pep621 = _pep621(tmp_path, fmt="pep440")
    gemspec = _gemspec(tmp_path)
    new_version = Version(2, 0, 0, pre="rc.1")

    events = replace_all_versions_atomic([pep621, gemspec], new_version, dry_run=False)

    by_path = {e.path: e.new_version for e in events}
    assert by_path[pep621.path] == "2.0.0rc1"  # explicit pep440 format
    assert by_path[gemspec.path] == "2.0.0.rc.1"  # rubygems default


def test_mixed_format_group_with_pin_gets_its_own_spelling(tmp_path: Path) -> None:
    pep621 = _pep621(tmp_path)
    pin_path = tmp_path / "README.md"
    pin_path.write_text("Install: `pip install foo==1.0.0`\n", encoding="utf-8")
    pin = PinTarget(
        path=pin_path,
        pattern=r"(pip install foo==)(\d+\.\d+\.\d+)(`)",
        format="rubygems",
    )
    new_version = Version(1, 0, 0, pre="alpha.1")

    replace_all_versions_atomic([pep621], new_version, dry_run=False)
    replace_pin_in_file(pin, new_version, dry_run=False)

    assert 'version = "1.0.0-alpha.1"' in pep621.path.read_text(encoding="utf-8")
    # rubygems can't spell "1.0.0.alpha.1" with 3-numeric pattern group here since
    # the pin's captured group has no dots requirement -- it just gets the rubygems text.
    assert "pip install foo==1.0.0.alpha.1" in pin_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Atomicity: validate every target renderable before writing anything.
# ---------------------------------------------------------------------------


def test_replace_all_versions_atomic_refuses_all_when_one_target_cannot_render(
    tmp_path: Path,
) -> None:
    ok_target = _pep621(tmp_path, "1.0.0", fmt="pep440")  # pep440 renders post fine
    refusing_target = _package_json(tmp_path, "1.0.0")  # default "semver" refuses post
    post_version = Version(1, 0, 1, post=1)

    with pytest.raises(RuntimeError, match="post"):
        replace_all_versions_atomic([ok_target, refusing_target], post_version, dry_run=False)

    # Nothing was written -- not even the target that could have rendered it.
    assert 'version = "1.0.0"' in ok_target.path.read_text(encoding="utf-8")
    assert json.loads(refusing_target.path.read_text(encoding="utf-8"))["version"] == "1.0.0"


def test_replace_all_versions_atomic_dry_run_also_refuses_unrepresentable(tmp_path: Path) -> None:
    target = _pep621(tmp_path, "1.0.0", fmt="semver")
    with pytest.raises(RuntimeError, match="post"):
        replace_all_versions_atomic([target], Version(1, 0, 1, post=1), dry_run=True)


def test_replace_version_in_file_unrepresentable_raises_runtime_error(tmp_path: Path) -> None:
    target = _pep621(tmp_path, "1.0.0", fmt="semver")
    with pytest.raises(RuntimeError, match="post"):
        replace_version_in_file(target, Version(1, 0, 1, post=1), dry_run=False)


def test_replace_pin_in_file_unrepresentable_raises_runtime_error(tmp_path: Path) -> None:
    path = tmp_path / "README.md"
    path.write_text("pinned: v1.0.0\n", encoding="utf-8")
    pin = PinTarget(path=path, pattern=r"(pinned: v)(\d+\.\d+\.\d+)($)")  # default "semver"
    with pytest.raises(RuntimeError, match="post"):
        replace_pin_in_file(pin, Version(1, 0, 1, post=1), dry_run=False)


# ---------------------------------------------------------------------------
# Backward compatibility: an unparseable string is still written verbatim.
# ---------------------------------------------------------------------------


def test_opaque_string_still_written_verbatim_everywhere(tmp_path: Path) -> None:
    package_json = _package_json(tmp_path)
    gemspec = _gemspec(tmp_path)
    events = replace_all_versions_atomic([package_json, gemspec], "not-a-version", dry_run=False)
    assert [e.new_version for e in events] == ["not-a-version", "not-a-version"]


# ---------------------------------------------------------------------------
# Single-format-repo regression: output stays byte-identical to pre-tier-2.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    ["2.0.0", "2.0.0-alpha.3", "2.0.0-beta.2", "2.0.0-rc.10"],
)
def test_single_format_repo_pep621_byte_identical_regression(tmp_path: Path, raw: str) -> None:
    """A single-format pep621-only repo writes exactly the same string as before.

    Regression guard for RRT-VER-1 tier 2: ``format`` unset on a ``pep621``
    target must keep rendering the plain SemVer spelling it always wrote,
    including for a value passed as a pre-formatted string (the historical
    calling convention every existing caller still uses).
    """
    target = _pep621(tmp_path, "1.0.0")
    event = replace_version_in_file(target, raw, dry_run=False)
    assert event.new_version == raw
    assert f'version = "{raw}"' in target.path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("canonical", "written"),
    [
        (Version(2, 0, 0, dev=1), "2.0.0.dev1"),
        (Version(2, 0, 0, pre="rc.2", dev=3), "2.0.0rc2.dev3"),
        (Version(2, 0, 0, post=1), "2.0.0.post1"),
    ],
)
def test_pep621_default_writes_pep440_for_dev_and_post(
    tmp_path: Path, canonical: Version, written: str
) -> None:
    """Dev and post releases reach a pep621 target in PEP 440 spelling.

    The SemVer dev spelling ``2.0.0-0.dev.1`` normalises to ``2.0.0.post0.dev1``
    in PEP 440, which sorts after ``2.0.0`` on PyPI; the ``python`` default
    avoids that and still lets a pure-Python group take a post release.
    """
    from packaging.version import Version as Pep440

    target = _pep621(tmp_path, "1.0.0")
    event = replace_version_in_file(target, canonical, dry_run=False)
    assert event.new_version == written
    assert f'version = "{written}"' in target.path.read_text(encoding="utf-8")
    assert Pep440(written) == Pep440(canonical.to_pep440())
