from __future__ import annotations

import pytest
from packaging.version import Version as PackagingVersion

from repo_release_tools.version.semver import (
    DEFAULT_PRERELEASE_BASE,
    PRERELEASE_BASES,
    Version,
    newer_versions,
)


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


# ---------------------------------------------------------------------------
# Decision D-1: starting a channel from a FINAL version targets the next patch
# ---------------------------------------------------------------------------


def test_prerelease_base_constants_are_the_single_source_of_truth() -> None:
    assert PRERELEASE_BASES == ("patch", "minor", "major", "auto")
    assert DEFAULT_PRERELEASE_BASE == "patch"


@pytest.mark.parametrize("channel", ["alpha", "beta", "rc"])
def test_channel_from_final_defaults_to_next_patch(channel: str) -> None:
    assert Version.parse("1.0.0").bump(channel) == Version.parse(f"1.0.1-{channel}.1")
    assert Version.parse("1.0.0").bump(channel, base="patch") == Version.parse(f"1.0.1-{channel}.1")


def test_channel_from_final_honours_base_minor_and_major() -> None:
    assert Version.parse("1.0.0").bump("rc", base="minor") == Version.parse("1.1.0-rc.1")
    assert Version.parse("1.0.0").bump("rc", base="major") == Version.parse("2.0.0-rc.1")
    assert Version.parse("1.2.3").bump("alpha", base="minor") == Version.parse("1.3.0-alpha.1")
    assert Version.parse("1.2.3").bump("beta", base="major") == Version.parse("2.0.0-beta.1")


def test_channel_advance_and_switch_keep_core_and_ignore_base() -> None:
    assert Version.parse("1.0.1-rc.1").bump("rc") == Version.parse("1.0.1-rc.2")
    assert Version.parse("1.0.1-rc.1").bump("rc", base="major") == Version.parse("1.0.1-rc.2")
    assert Version.parse("1.0.1-beta.2").bump("rc") == Version.parse("1.0.1-rc.1")
    assert Version.parse("1.0.1-beta.2").bump("rc", base="minor") == Version.parse("1.0.1-rc.1")


def test_switching_to_an_earlier_channel_raises_instead_of_going_backwards() -> None:
    with pytest.raises(ValueError, match=r"not newer"):
        Version.parse("1.0.1-rc.1").bump("alpha")


def test_switching_from_a_non_channel_label_that_sorts_later_raises() -> None:
    with pytest.raises(ValueError, match=r"1\.0\.0-dev\.1.*1\.0\.0-alpha\.1.*not newer"):
        Version.parse("1.0.0-dev.1").bump("alpha")


def test_invalid_prerelease_base_raises_naming_allowed_values() -> None:
    with pytest.raises(ValueError, match=r"'huge'.*patch.*minor.*major"):
        Version.parse("1.0.0").bump("rc", base="huge")


def test_auto_prerelease_base_must_be_resolved_before_version_bump() -> None:
    with pytest.raises(ValueError, match=r"'auto'.*commit history"):
        Version.parse("1.0.0").bump("rc", base="auto")


_PROPERTY_VERSIONS = [
    "0.0.0",
    "1.0.0",
    "1.2.3",
    "1.0.0-alpha",
    "1.0.0-alpha.1",
    "1.0.1-beta.2",
    "1.0.1-rc.1",
    "2.0.0-beta.2",
    "1.2.0-rc.1",
    "1.0.0-dev.1",
]
_PROPERTY_KINDS = ["major", "minor", "patch", "release", "pre-release", "alpha", "beta", "rc"]
_PROPERTY_BASES = ["patch", "minor", "major"]


@pytest.mark.parametrize("base", _PROPERTY_BASES)
@pytest.mark.parametrize("kind", _PROPERTY_KINDS)
@pytest.mark.parametrize("raw", _PROPERTY_VERSIONS)
def test_every_bump_result_is_strictly_greater_or_raises(raw: str, kind: str, base: str) -> None:
    current = Version.parse(raw)
    if (raw, kind) in _PROPERTY_REFUSED:
        # The only refusals are the "would not be newer" guards; nothing silently regresses.
        with pytest.raises(ValueError, match=_PROPERTY_REFUSED[(raw, kind)]):
            current.bump(kind, base=base)
        return
    result = current.bump(kind, base=base)
    assert result > current, f"{current} bump {kind} (base={base}) -> {result} is not newer"


_FINALS = ("0.0.0", "1.0.0", "1.2.3")
_NOT_NEWER = r"which is not newer"
_PROPERTY_REFUSED: dict[tuple[str, str], str] = {
    **{(raw, "release"): r"Cannot finalize a version that has no pre-release" for raw in _FINALS},
    **{(raw, "pre-release"): r"Cannot bump pre-release on a stable version" for raw in _FINALS},
    ("1.0.1-beta.2", "alpha"): _NOT_NEWER,
    ("2.0.0-beta.2", "alpha"): _NOT_NEWER,
    ("1.0.1-rc.1", "alpha"): _NOT_NEWER,
    ("1.0.1-rc.1", "beta"): _NOT_NEWER,
    ("1.2.0-rc.1", "alpha"): _NOT_NEWER,
    ("1.2.0-rc.1", "beta"): _NOT_NEWER,
    ("1.0.0-dev.1", "alpha"): _NOT_NEWER,
    ("1.0.0-dev.1", "beta"): _NOT_NEWER,
}


@pytest.mark.parametrize("base", _PROPERTY_BASES)
@pytest.mark.parametrize("channel", ["alpha", "beta", "rc"])
@pytest.mark.parametrize("raw", _FINALS)
def test_every_channel_start_from_final_is_strictly_greater(
    raw: str, channel: str, base: str
) -> None:
    """D-1: starting any channel from a FINAL version always succeeds and moves forward."""
    current = Version.parse(raw)
    result = current.bump(channel, base=base)
    assert result > current
    assert result.pre == f"{channel}.1"


# ---------------------------------------------------------------------------
# Bump algebra: kind x state table, dev/post kinds (issue #259, T1.3)
# ---------------------------------------------------------------------------
#
# Five representative states built on the same core (1.0.1) and channel (rc),
# crossed with every bump kind. Each cell is either the expected PEP 440
# result or a regex matching the ValueError it must raise. Every non-error
# cell is asserted strictly newer both by our own sort_key() and by
# packaging.version.Version ordering on to_pep440(), so the table is
# cross-checked against an independent implementation of version precedence.

_ALGEBRA_STATES: dict[str, Version] = {
    "final": Version(1, 0, 1),
    "pre": Version(1, 0, 1, pre="rc.1"),  # 1.0.1rc1
    "dev-of-final": Version(1, 0, 1, dev=3),  # 1.0.1.dev3
    "dev-of-pre": Version(1, 0, 1, pre="rc.1", dev=2),  # 1.0.1rc1.dev2
    "post": Version(1, 0, 1, post=1),  # 1.0.1.post1
}

_ALGEBRA_KINDS = (
    "major",
    "minor",
    "patch",
    "release",
    "pre-release",
    "alpha",
    "beta",
    "rc",
    "dev",
    "post",
)

_NO_PRE_RELEASE = r"Cannot bump pre-release on a stable version"
_NO_FINALIZE = r"Cannot finalize a version that has no pre-release"
_POST_ONLY_FOLLOWS_FINAL = r"only follows a final release"

# (state, kind) -> expected PEP 440 result, or a regex for the ValueError raised.
_ALGEBRA_TABLE: dict[tuple[str, str], str] = {
    # major/minor/patch: uniform per kind across every state (existing semver
    # semantics -- a pre/dev/post release finalizes in place at the boundary).
    ("final", "major"): "2.0.0",
    ("pre", "major"): "2.0.0",
    ("dev-of-final", "major"): "2.0.0",
    ("dev-of-pre", "major"): "2.0.0",
    ("post", "major"): "2.0.0",
    ("final", "minor"): "1.1.0",
    ("pre", "minor"): "1.1.0",
    ("dev-of-final", "minor"): "1.1.0",
    ("dev-of-pre", "minor"): "1.1.0",
    ("post", "minor"): "1.1.0",
    ("final", "patch"): "1.0.2",
    ("pre", "patch"): "1.0.1",
    ("dev-of-final", "patch"): "1.0.1",
    ("dev-of-pre", "patch"): "1.0.1",
    ("post", "patch"): "1.0.2",
    # release: finalizes a pre/dev release to its stable core; final/post have
    # no pre-release to finalize.
    ("final", "release"): _NO_FINALIZE,
    ("pre", "release"): "1.0.1",
    ("dev-of-final", "release"): "1.0.1",
    ("dev-of-pre", "release"): "1.0.1",
    ("post", "release"): _NO_FINALIZE,
    # pre-release: advances the current pre-release label; a dev-of-pre drops
    # dev instead of incrementing it (I3: dev only ever precedes its channel).
    ("final", "pre-release"): _NO_PRE_RELEASE,
    ("pre", "pre-release"): "1.0.1rc2",
    ("dev-of-final", "pre-release"): "1.0.1.dev4",
    ("dev-of-pre", "pre-release"): "1.0.1rc1",
    ("post", "pre-release"): _NO_PRE_RELEASE,
    # alpha/beta: starting a *different*, lower channel than "rc" on a state
    # already at or past rc (pre, dev-of-pre) would go backwards -- refused.
    ("final", "alpha"): "1.0.2a1",
    ("pre", "alpha"): r"not newer",
    ("dev-of-final", "alpha"): "1.0.1a1",
    ("dev-of-pre", "alpha"): r"not newer",
    ("post", "alpha"): "1.0.2a1",
    ("final", "beta"): "1.0.2b1",
    ("pre", "beta"): r"not newer",
    ("dev-of-final", "beta"): "1.0.1b1",
    ("dev-of-pre", "beta"): r"not newer",
    ("post", "beta"): "1.0.2b1",
    # rc: same channel as "pre"/"dev-of-pre", so it always advances forward.
    ("final", "rc"): "1.0.2rc1",
    ("pre", "rc"): "1.0.1rc2",
    ("dev-of-final", "rc"): "1.0.1rc1",
    ("dev-of-pre", "rc"): "1.0.1rc1",
    ("post", "rc"): "1.0.2rc1",
    # dev: start or advance a dev release (T1.3 rules, see Version.bump docstring).
    ("final", "dev"): "1.0.2.dev0",
    ("pre", "dev"): "1.0.1rc2.dev0",
    ("dev-of-final", "dev"): "1.0.1.dev4",
    ("dev-of-pre", "dev"): "1.0.1rc1.dev3",
    ("post", "dev"): "1.0.2.dev0",
    # post: only ever follows a final or another post release.
    ("final", "post"): "1.0.1.post1",
    ("pre", "post"): _POST_ONLY_FOLLOWS_FINAL,
    ("dev-of-final", "post"): _POST_ONLY_FOLLOWS_FINAL,
    ("dev-of-pre", "post"): _POST_ONLY_FOLLOWS_FINAL,
    ("post", "post"): "1.0.1.post2",
}


def test_bump_algebra_table_covers_every_state_and_kind() -> None:
    """Every (state, kind) pair used by the table below is accounted for."""
    expected = {(s, k) for s in _ALGEBRA_STATES for k in _ALGEBRA_KINDS}
    assert set(_ALGEBRA_TABLE) == expected


@pytest.mark.parametrize("kind", _ALGEBRA_KINDS)
@pytest.mark.parametrize("state", list(_ALGEBRA_STATES))
def test_bump_algebra_kind_by_state_table(state: str, kind: str) -> None:
    """Full kind x state table for major/minor/patch/release/pre-release/alpha/

    beta/rc/dev/post (issue #259 T1.3). Each cell either raises or produces a
    result that is strictly newer than the current version, both by our own
    sort_key() and by packaging.version.Version ordering on to_pep440() --
    cross-checking the invariant (I5) against an independent implementation.
    """
    current = _ALGEBRA_STATES[state]
    expected = _ALGEBRA_TABLE[(state, kind)]
    if not expected[0].isdigit():
        with pytest.raises(ValueError, match=expected):
            current.bump(kind)
        return

    result = current.bump(kind)

    assert result.to_pep440() == expected
    assert result > current, f"{current} bump {kind} -> {result} is not newer (sort_key)"
    assert PackagingVersion(result.to_pep440()) > PackagingVersion(current.to_pep440()), (
        f"{current} bump {kind} -> {result} is not newer per packaging.version"
    )
