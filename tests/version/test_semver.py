from __future__ import annotations

import pytest

from repo_release_tools.version.semver import Version, newer_versions


def test_sort_key_orders_pre_release_before_stable() -> None:
    assert Version.parse("1.2.0-rc.1").sort_key() < Version.parse("1.2.0").sort_key()


def test_newer_versions_filters_and_sorts() -> None:
    cur = Version.parse("0.5.0")
    cands = [Version.parse(v) for v in ["0.4.9", "0.5.0", "0.6.0", "0.5.1"]]
    assert [str(v) for v in newer_versions(cur, cands)] == ["0.5.1", "0.6.0"]


# ---------------------------------------------------------------------------
# SemVer 2.0 section 11 precedence (T0.1)
# ---------------------------------------------------------------------------

_SPEC_CHAIN = [
    "1.0.0-alpha",
    "1.0.0-alpha.1",
    "1.0.0-alpha.beta",
    "1.0.0-beta",
    "1.0.0-beta.2",
    "1.0.0-beta.11",
    "1.0.0-rc.1",
    "1.0.0",
]


def test_sort_key_orders_numeric_pre_release_identifiers_numerically() -> None:
    versions = [Version.parse(v) for v in ["1.0.0-rc.1", "1.0.0-rc.10", "1.0.0-rc.2"]]
    assert [str(v) for v in sorted(versions, key=Version.sort_key)] == [
        "1.0.0-rc.1",
        "1.0.0-rc.2",
        "1.0.0-rc.10",
    ]


def test_semver_spec_section_11_precedence_chain_holds_pairwise() -> None:
    chain = [Version.parse(v) for v in _SPEC_CHAIN]
    for i, lower in enumerate(chain):
        for higher in chain[i + 1 :]:
            assert lower.sort_key() < higher.sort_key(), f"{lower} !< {higher} (sort_key)"
            assert lower < higher, f"{lower} !< {higher}"
            assert lower <= higher, f"{lower} !<= {higher}"
            assert higher > lower, f"{higher} !> {lower}"
            assert higher >= lower, f"{higher} !>= {lower}"
            assert not higher < lower
            assert not lower > higher
    assert sorted(reversed(chain)) == chain


def test_newer_versions_treats_rc10_as_newer_than_rc2() -> None:
    current = Version.parse("1.0.0-rc.2")
    candidates = [Version.parse("1.0.0-rc.10"), Version.parse("1.0.0-rc.1")]
    assert [str(v) for v in newer_versions(current, candidates)] == ["1.0.0-rc.10"]


def test_build_metadata_is_ignored_for_precedence() -> None:
    a = Version.parse("1.0.0+a")
    b = Version.parse("1.0.0+b")
    assert a.sort_key() == b.sort_key()
    assert a <= b and b <= a
    assert a >= b and b >= a
    assert not a < b and not b < a
    assert not a > b and not b > a
    # Equality stays structural: build metadata still distinguishes the objects.
    assert a != b


def test_numeric_identifier_sorts_before_alphanumeric() -> None:
    assert Version.parse("1.0.0-1") < Version.parse("1.0.0-alpha")
    assert Version.parse("1.0.0-alpha.9") < Version.parse("1.0.0-alpha.x")


def test_pre_release_identifiers_compare_ascii_lexically() -> None:
    # ASCII sort order: uppercase letters sort before lowercase ones.
    assert Version.parse("1.0.0-RC.1") < Version.parse("1.0.0-rc.1")


def test_shorter_identifier_list_sorts_first_when_prefix_equal() -> None:
    assert Version.parse("1.0.0-rc") < Version.parse("1.0.0-rc.1")
    assert Version.parse("1.0.0-rc.1") < Version.parse("1.0.0-rc.1.1")


def test_core_version_dominates_pre_release_identifiers() -> None:
    assert Version.parse("1.0.0-zzz") < Version.parse("1.0.1-alpha")
    assert Version.parse("1.9.0") < Version.parse("1.10.0-rc.1")


def test_rich_comparisons_return_not_implemented_for_non_version() -> None:
    v = Version.parse("1.0.0")
    assert v.__lt__("1.0.0") is NotImplemented  # type: ignore[operator]
    assert v.__le__("1.0.0") is NotImplemented  # type: ignore[operator]
    assert v.__gt__("1.0.0") is NotImplemented  # type: ignore[operator]
    assert v.__ge__("1.0.0") is NotImplemented  # type: ignore[operator]
    with pytest.raises(TypeError):
        _ = v < "1.0.0"  # type: ignore[operator]
