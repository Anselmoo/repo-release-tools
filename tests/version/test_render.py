"""Tests for :mod:`repo_release_tools.version.render` (RRT-VER-1 tier 2)."""

from __future__ import annotations

import pytest
from packaging.version import Version as PackagingVersion

from repo_release_tools.version.calver import CalVersion
from repo_release_tools.version.render import (
    FORMATS,
    UnrepresentableVersionError,
    default_format_for_kind,
    parse_rendered,
    render,
)
from repo_release_tools.version.semver import Version

# ---------------------------------------------------------------------------
# The issue #259 table: canonical PEP 440 -> semver | rubygems | pep440.
# `None` means the format refuses that value.
# ---------------------------------------------------------------------------
TABLE: list[tuple[str, str | None, str, str]] = [
    ("0.1.0.dev1", "0.1.0-0.dev.1", "0.1.0.a.dev.1", "0.1.0.dev1"),
    ("0.1.0a1.dev2", "0.1.0-alpha.0.dev.2", "0.1.0.alpha.1.dev.2", "0.1.0a1.dev2"),
    ("0.1.0a1", "0.1.0-alpha.1", "0.1.0.alpha.1", "0.1.0a1"),
    ("0.1.0b1", "0.1.0-beta.1", "0.1.0.beta.1", "0.1.0b1"),
    ("0.1.0rc1.dev4", "0.1.0-rc.0.dev.4", "0.1.0.rc.1.dev.4", "0.1.0rc1.dev4"),
    ("0.1.0rc1", "0.1.0-rc.1", "0.1.0.rc.1", "0.1.0rc1"),
    ("0.1.0rc2.dev5", "0.1.0-rc.1.dev.5", "0.1.0.rc.2.dev.5", "0.1.0rc2.dev5"),
    ("0.1.0rc10", "0.1.0-rc.10", "0.1.0.rc.10", "0.1.0rc10"),
    ("0.1.0", "0.1.0", "0.1.0", "0.1.0"),
    ("0.1.0.post1", None, "0.1.0.1", "0.1.0.post1"),
    ("0.1.1.dev3", "0.1.1-0.dev.3", "0.1.1.a.dev.3", "0.1.1.dev3"),
]


def _version(raw: str) -> Version:
    return Version.parse(raw, spelling="pep440")


@pytest.mark.parametrize(("raw", "expected"), [(row[0], row[1]) for row in TABLE])
def test_render_semver_matches_table(raw: str, expected: str | None) -> None:
    v = _version(raw)
    if expected is None:
        with pytest.raises(UnrepresentableVersionError, match="semver"):
            render(v, "semver")
    else:
        assert render(v, "semver") == expected


@pytest.mark.parametrize(("raw", "expected"), [(row[0], row[2]) for row in TABLE])
def test_render_rubygems_matches_table(raw: str, expected: str) -> None:
    assert render(_version(raw), "rubygems") == expected


@pytest.mark.parametrize(("raw", "expected"), [(row[0], row[3]) for row in TABLE])
def test_render_pep440_matches_table(raw: str, expected: str) -> None:
    assert render(_version(raw), "pep440") == expected


@pytest.mark.parametrize(("raw", "expected"), [(row[0], row[1]) for row in TABLE])
def test_render_go_tag_matches_v_prefixed_semver(raw: str, expected: str | None) -> None:
    v = _version(raw)
    if expected is None:
        with pytest.raises(UnrepresentableVersionError, match="go-tag"):
            render(v, "go-tag")
    else:
        assert render(v, "go-tag") == f"v{expected}"


@pytest.mark.parametrize(("raw", "expected"), [(row[0], row[1]) for row in TABLE])
def test_render_oci_tag_matches_semver_with_dash(raw: str, expected: str | None) -> None:
    v = _version(raw)
    if expected is None:
        with pytest.raises(UnrepresentableVersionError, match="oci-tag"):
            render(v, "oci-tag")
    else:
        assert render(v, "oci-tag") == expected.replace("+", "-")


# ---------------------------------------------------------------------------
# I1 round trip: parse(render(v, fmt), fmt) == v for every representable value.
# ---------------------------------------------------------------------------

_ROUND_TRIP_FORMATS = ("semver", "pep440", "python", "rubygems", "go-tag", "oci-tag")


@pytest.mark.parametrize("raw", [row[0] for row in TABLE])
@pytest.mark.parametrize("fmt", _ROUND_TRIP_FORMATS)
def test_round_trip_i1(raw: str, fmt: str) -> None:
    v = _version(raw)
    try:
        text = render(v, fmt)
    except UnrepresentableVersionError:
        return  # not representable in this format; nothing to round-trip
    assert parse_rendered(text, fmt) == v


def test_round_trip_semver_pre_release_without_dev() -> None:
    v = Version.parse("1.2.3-beta.4")
    for fmt in _ROUND_TRIP_FORMATS:
        text = render(v, fmt)
        assert parse_rendered(text, fmt) == v


# ---------------------------------------------------------------------------
# Ordering: pep440 renderings of the train sort identically to packaging.version.
# ---------------------------------------------------------------------------


def test_pep440_ordering_matches_packaging_version() -> None:
    versions = [_version(row[0]) for row in TABLE]
    by_sort_key = sorted(versions, key=Version.sort_key)
    by_packaging = sorted(versions, key=lambda v: PackagingVersion(render(v, "pep440")))
    assert [render(v, "pep440") for v in by_sort_key] == [render(v, "pep440") for v in by_packaging]


# ---------------------------------------------------------------------------
# Refusals and errors
# ---------------------------------------------------------------------------


def test_render_unknown_format_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unknown version format"):
        render(_version("0.1.0"), "bogus")


def test_render_version_as_calver_refuses() -> None:
    with pytest.raises(UnrepresentableVersionError, match="calver"):
        render(_version("0.1.0"), "calver")


def test_render_pep440_refuses_build_segment() -> None:
    v = Version(1, 0, 0, build="build.5")
    with pytest.raises(UnrepresentableVersionError, match="pep440"):
        render(v, "pep440")


def test_render_pep440_refuses_opaque_label_via_underlying_error() -> None:
    v = Version(1, 0, 0, pre="dev.1")
    with pytest.raises(UnrepresentableVersionError, match="pep440"):
        render(v, "pep440")


def test_render_rubygems_refuses_build_segment() -> None:
    v = Version(1, 0, 0, build="build.5")
    with pytest.raises(UnrepresentableVersionError, match="rubygems"):
        render(v, "rubygems")


def test_render_rubygems_refuses_opaque_pre_release_label() -> None:
    v = Version(1, 0, 0, pre="dev.1")
    with pytest.raises(UnrepresentableVersionError, match="rubygems"):
        render(v, "rubygems")


def test_render_rubygems_post_with_dev() -> None:
    v = Version(1, 0, 1, post=1, dev=0)
    assert render(v, "rubygems") == "1.0.1.1.dev.0"


def test_parse_rendered_unknown_format_raises() -> None:
    with pytest.raises(ValueError, match="Unknown version format"):
        parse_rendered("1.0.0", "bogus")


def test_parse_rendered_calver_raises() -> None:
    with pytest.raises(ValueError, match="calver"):
        parse_rendered("1.0.0", "calver")


def test_parse_rendered_go_tag_requires_v_prefix() -> None:
    with pytest.raises(ValueError, match="'v' prefix"):
        parse_rendered("1.0.0", "go-tag")


def test_parse_rendered_rubygems_invalid_raises() -> None:
    with pytest.raises(ValueError, match="Invalid rubygems version"):
        parse_rendered("not-a-version", "rubygems")


# ---------------------------------------------------------------------------
# CalVersion rendering
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fmt", FORMATS)
def test_render_calver_every_format(fmt: str) -> None:
    cal = CalVersion(2026, 5, 15, scheme="YYYY.MM.DD")
    text = render(cal, fmt)
    if fmt == "go-tag":
        assert text == "v2026.05.15"
    else:
        assert text == "2026.05.15"


def test_render_calver_with_micro() -> None:
    cal = CalVersion(2026, 5, 15, micro=2, scheme="YYYY.MM.DD")
    assert render(cal, "semver") == "2026.05.15.2"
    assert render(cal, "go-tag") == "v2026.05.15.2"


# ---------------------------------------------------------------------------
# default_format_for_kind
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind",
    [
        "package_json",
        "mcp_server_json",
        "go_version",
        "cargo_toml",
        "maven_pom",
        "csproj",
        "pattern",
        None,
    ],
)
def test_default_format_for_kind_is_semver(kind: str | None) -> None:
    assert default_format_for_kind(kind) == "semver"


@pytest.mark.parametrize("kind", ["pep621", "python_version"])
def test_default_format_for_kind_python_kinds_are_python(kind: str) -> None:
    assert default_format_for_kind(kind) == "python"


def test_python_format_keeps_semver_spelling_for_final_and_channels() -> None:
    assert render(Version(1, 2, 0), "python") == "1.2.0"
    assert render(Version(1, 2, 0, pre="rc.1"), "python") == "1.2.0-rc.1"
    assert render(Version(1, 2, 0, build="build.5"), "python") == "1.2.0+build.5"


def test_python_format_uses_pep440_for_dev_and_post() -> None:
    assert render(Version(1, 2, 1, dev=0), "python") == "1.2.1.dev0"
    assert render(Version(1, 2, 0, pre="rc.2", dev=4), "python") == "1.2.0rc2.dev4"
    assert render(Version(1, 2, 0, post=1), "python") == "1.2.0.post1"


def test_default_format_for_kind_gemspec_is_rubygems() -> None:
    assert default_format_for_kind("gemspec") == "rubygems"
