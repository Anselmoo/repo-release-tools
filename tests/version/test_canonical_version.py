"""RRT-VER-1 §1 canonical version model: SemVer and PEP 440 spellings of one value."""

from __future__ import annotations

import itertools
import random
from typing import Any

import pytest
from packaging.version import Version as PackagingVersion

from repo_release_tools.version.semver import Version

# (PEP 440 spelling, SemVer spelling) for every entry of the issue's train, ascending.
_TRAIN: list[tuple[str, str]] = [
    ("0.1.0.dev1", "0.1.0-0.dev.1"),
    ("0.1.0a1.dev2", "0.1.0-alpha.0.dev.2"),
    ("0.1.0a1", "0.1.0-alpha.1"),
    ("0.1.0b1", "0.1.0-beta.1"),
    ("0.1.0rc1.dev4", "0.1.0-rc.0.dev.4"),
    ("0.1.0rc1", "0.1.0-rc.1"),
    ("0.1.0rc2.dev5", "0.1.0-rc.1.dev.5"),
    ("0.1.0rc2", "0.1.0-rc.2"),
    ("0.1.0rc10", "0.1.0-rc.10"),
    ("0.1.0", "0.1.0"),
    ("0.1.0.post1", "0.1.0-post.1"),
    ("0.1.1.dev3", "0.1.1-0.dev.3"),
    ("0.1.1", "0.1.1"),
]

_CANONICAL_FIELDS = ("release", "pre_channel", "pre_number", "post", "dev", "local")


def _fields(v: Version) -> tuple[object, ...]:
    return tuple(getattr(v, name) for name in _CANONICAL_FIELDS)


@pytest.mark.parametrize(
    ("pep440", "semver", "expected"),
    [
        ("0.1.0.dev1", "0.1.0-0.dev.1", ((0, 1, 0), None, None, None, 1, None)),
        ("0.1.0a1.dev2", "0.1.0-alpha.0.dev.2", ((0, 1, 0), "alpha", 1, None, 2, None)),
        ("0.1.0rc1", "0.1.0-rc.1", ((0, 1, 0), "rc", 1, None, None, None)),
        ("0.1.0.post1", "0.1.0-post.1", ((0, 1, 0), None, None, 1, None, None)),
    ],
)
def test_pep440_and_semver_spellings_parse_to_same_canonical_values(
    pep440: str, semver: str, expected: tuple[object, ...]
) -> None:
    from_pep440 = Version.parse(pep440)
    from_semver = Version.parse(semver)
    assert from_pep440 == from_semver
    assert _fields(from_pep440) == _fields(from_semver) == expected
    assert from_pep440.sort_key() == from_semver.sort_key()


def test_canonical_order_matches_packaging_version_for_issue_train() -> None:
    entries = [(raw, pep) for pep, sem in _TRAIN for raw in (pep, sem)]
    random.Random(259).shuffle(entries)

    by_rrt = sorted(entries, key=lambda e: Version.parse(e[0]).sort_key())
    by_packaging = sorted(entries, key=lambda e: PackagingVersion(e[1]))
    assert [PackagingVersion(pep) for _, pep in by_rrt] == [
        PackagingVersion(pep) for _, pep in by_packaging
    ]
    assert [pep for pep, _ in _TRAIN] == sorted({pep for _, pep in entries}, key=PackagingVersion)

    for (raw_a, pep_a), (raw_b, pep_b) in itertools.product(entries, repeat=2):
        a, b = Version.parse(raw_a), Version.parse(raw_b)
        pa, pb = PackagingVersion(pep_a), PackagingVersion(pep_b)
        assert (a < b) == (pa < pb), (raw_a, raw_b)
        assert (a == b) == (pa == pb), (raw_a, raw_b)
        assert (a <= b) == (pa <= pb), (raw_a, raw_b)


@pytest.mark.parametrize("raw", [raw for pair in _TRAIN for raw in pair])
def test_round_trip_str_and_to_pep440(raw: str) -> None:
    v = Version.parse(raw)
    assert Version.parse(str(v)) == v
    assert Version.parse(v.to_pep440()) == v
    assert PackagingVersion(v.to_pep440()) == PackagingVersion(Version.parse(raw).to_pep440())


def test_round_trip_renders_canonical_spellings() -> None:
    assert str(Version.parse("0.1.0.dev1")) == "0.1.0-0.dev.1"
    assert str(Version.parse("0.1.0a1.dev2")) == "0.1.0-alpha.0.dev.2"
    assert str(Version.parse("0.1.0rc1.dev5")) == "0.1.0-rc.0.dev.5"
    assert str(Version.parse("0.1.0-post.1")) == "0.1.0.post1"
    assert str(Version.parse("0.1.0.post1.dev2+abc")) == "0.1.0.post1.dev2+abc"
    assert Version.parse("0.1.0-0.dev.1").to_pep440() == "0.1.0.dev1"
    assert Version.parse("0.1.0-alpha.0.dev.2").to_pep440() == "0.1.0a1.dev2"
    assert Version.parse("0.1.0-beta.3").to_pep440() == "0.1.0b3"
    assert Version.parse("0.1.0-rc.1+build.7").to_pep440() == "0.1.0rc1+build.7"
    assert Version.parse("0.1.0a0").to_pep440() == "0.1.0a0"


@pytest.mark.parametrize(
    ("raw", "pre", "dev", "post", "final"),
    [
        ("0.1.0.dev1", True, True, False, False),
        ("0.1.0a1.dev2", True, True, False, False),
        ("0.1.0rc1", True, False, False, False),
        ("0.1.0", False, False, False, True),
        ("0.1.0.post1", False, False, True, False),
        ("0.1.0.post1.dev2", True, True, False, False),
        ("1.0.0-alpha", True, False, False, False),
    ],
)
def test_classification_dev_pre_post(
    raw: str, pre: bool, dev: bool, post: bool, final: bool
) -> None:
    v = Version.parse(raw)
    assert v.is_pre_release() is pre
    assert v.is_dev_release() is dev
    assert v.is_post_release() is post
    assert (v == v.stable()) is final
    assert v.stable() == Version(*v.release)


@pytest.mark.parametrize(
    ("raw", "pre"),
    [
        ("1.0.0-dev.1", "dev.1"),
        ("1.0.0-alpha", "alpha"),
        ("1.0.0-alpha.0", "alpha.0"),
        ("1.0.0-alpha.beta", "alpha.beta"),
        ("1.0.0-rc.00.dev.1", "rc.00.dev.1"),
        ("1.0.0-post.0", "post.0"),
    ],
)
def test_opaque_semver_labels_keep_semver_meaning(raw: str, pre: str) -> None:
    v = Version.parse(raw)
    assert v.pre == pre
    assert v.dev is None
    assert v.post is None
    assert v.pre_channel is None
    assert v.pre_number is None
    assert str(v) == raw
    assert v.sort_key()[3] == 0
    assert v < v.stable()


def test_opaque_labels_keep_semver_section_11_order() -> None:
    ordered = ["1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta", "1.0.0"]
    parsed = [Version.parse(raw) for raw in ordered]
    assert parsed == sorted(parsed)
    assert Version.parse("1.0.0-dev.1") > Version.parse("1.0.0-alpha.1")


def test_opaque_pre_label_cannot_render_as_pep440() -> None:
    with pytest.raises(ValueError, match=r"'dev\.1'.*PEP 440"):
        Version.parse("1.0.0-dev.1").to_pep440()


def test_uppercase_build_cannot_render_as_pep440() -> None:
    with pytest.raises(ValueError, match="local segment"):
        Version.parse("1.0.0+Build").to_pep440()


@pytest.mark.parametrize(
    ("raw", "match"),
    [
        ("1!1.0.0", r"Invalid semver: '1!1\.0\.0'.*epoch"),
        ("1.0", r"Invalid semver: '1\.0'.*three release components"),
        ("1.0.0.0", r"Invalid semver: '1\.0\.0\.0'.*three release components"),
        ("01.2.0", r"Invalid semver: '01\.2\.0'.*leading zero"),
        ("1.0.0a0.dev1", r"Invalid semver: '1\.0\.0a0\.dev1'.*dev.*opaque"),
        ("1.0.0rc1.post1", r"Invalid semver: '1\.0\.0rc1\.post1'.*post.*pre-release"),
        ("1.0.0.post0", r"Invalid semver: '1\.0\.0\.post0'.*post"),
        ("v1.0.0", r"Invalid semver: 'v1\.0\.0'.*'v' prefix"),
        ("not-a-version", r"Invalid semver: 'not-a-version' \(expected SemVer .* or PEP 440\)"),
    ],
)
def test_pep440_rejections(raw: str, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        Version.parse(raw)


def test_zero_epoch_is_accepted() -> None:
    assert Version.parse("0!1.0.0rc1") == Version.parse("1.0.0-rc.1")


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"dev": 1, "pre": "dev.1"}, "opaque"),
        ({"post": 1, "pre": "rc.1"}, "pre-release"),
        ({"post": 0}, "post"),
        ({"dev": -1}, "dev"),
        ({"pre": "0.dev.1", "dev": 2}, "not both"),
        ({"pre": "post.1", "post": 2}, "not both"),
        ({"pre": "rc.0.dev.1", "post": 2}, "not both"),
        ({"post": 1, "build": "ABC"}, "lowercase"),
    ],
)
def test_constructor_rejects_invalid_combinations(kwargs: dict[str, Any], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        Version(1, 0, 0, **kwargs)


def test_constructor_canonicalises_semver_dev_and_post_encodings() -> None:
    assert Version(0, 1, 0, pre="0.dev.1") == Version(0, 1, 0, dev=1)
    assert Version(0, 1, 0, pre="rc.1.dev.5") == Version(0, 1, 0, pre="rc.2", dev=5)
    assert Version(0, 1, 0, pre="post.3") == Version(0, 1, 0, post=3)
    assert Version(1, 2, 3, pre="rc.1") == Version.parse("1.2.3-rc.1")


def test_pep440_channel_spellings_normalise() -> None:
    assert Version.parse("1.0.0alpha2").pre == "alpha.2"
    assert Version.parse("1.0.0_b.2").pre == "beta.2"
    assert Version.parse("1.0.0-b.2").pre == "b.2"  # SemVer grammar wins
    assert Version.parse("1.0.0c3").pre == "rc.3"
    assert Version.parse("1.0.0pre3").pre == "rc.3"
    assert Version.parse("1.0.0preview3").pre == "rc.3"
    assert Version.parse("1.0.0RC3").pre == "rc.3"
    assert Version.parse("1.0.0a").pre == "alpha.0"
    assert Version.parse("1.0.0.dev").dev == 0
    assert Version.parse("1.0.0-3", spelling="pep440").post == 3
    assert Version.parse("1.0.0-3").pre == "3"  # SemVer grammar wins
    assert Version.parse("1.0.0.rev4").post == 4


def test_local_segment_maps_to_build_and_local_alias() -> None:
    v = Version.parse("1.0.0rc1+Ubuntu-1_x")
    assert v.build == "ubuntu.1.x"
    assert v.local == "ubuntu.1.x"
    assert v.to_pep440() == "1.0.0rc1+ubuntu.1.x"
    assert Version.parse("1.0.0+exp.sha.5114f85").local == "exp.sha.5114f85"
    assert Version.parse("1.0.0").local is None
    assert Version.parse("0.1.0.post1+abc").local == "abc"


def test_spelling_selects_one_grammar() -> None:
    assert Version.parse("1.0.0-dev.1", spelling="pep440") == Version(1, 0, 0, dev=1)
    assert Version.parse("1.0.0-dev.1", spelling="semver").pre == "dev.1"
    assert Version.parse("1.0.0-dev.1", spelling="any").pre == "dev.1"
    with pytest.raises(ValueError, match=r"Invalid semver: '1\.0\.0rc1' \(expected SemVer"):
        Version.parse("1.0.0rc1", spelling="semver")
    with pytest.raises(ValueError, match=r"Invalid semver: '1\.0\.0-x' \(expected PEP 440"):
        Version.parse("1.0.0-x", spelling="pep440")
    with pytest.raises(ValueError, match="spelling"):
        Version.parse("1.0.0", spelling="calver")


def test_semver_post_label_with_uppercase_build_falls_back_to_pep440() -> None:
    assert Version.parse("1.0.0-post.1+ABC") == Version(1, 0, 0, post=1, build="abc")
    with pytest.raises(ValueError, match=r"Invalid semver: '1\.0\.0-post\.1\+ABC'.*lowercase"):
        Version.parse("1.0.0-post.1+ABC", spelling="semver")


def test_sort_key_orders_post_and_post_dev_per_pep440() -> None:
    assert Version.parse("1.0.0").sort_key()[5] == (0, 1, 0)
    assert Version.parse("1.0.0.post2").sort_key()[5] == (2, 1, 0)
    assert Version.parse("1.0.0.post2.dev3").sort_key()[5] == (2, 0, 3)
    chain = ["1.0.0", "1.0.0.post1.dev0", "1.0.0.post1", "1.0.0.post2.dev1", "1.0.0.post2"]
    parsed = [Version.parse(raw) for raw in chain]
    assert parsed == sorted(reversed(parsed))
    assert [PackagingVersion(v.to_pep440()) for v in parsed] == sorted(
        PackagingVersion(raw) for raw in chain
    )


def test_bumps_keep_legacy_behaviour_on_dev_and_post_versions() -> None:
    assert Version.parse("0.1.0.dev1").bump("patch") == Version.parse("0.1.0")
    assert Version.parse("0.1.0.dev1").bump("pre-release") == Version.parse("0.1.0.dev2")
    assert Version.parse("0.1.0.dev1").bump("rc") == Version.parse("0.1.0rc1")
    assert Version.parse("1.2.3-beta.1.dev.42").bump("pre-release") == Version.parse(
        "1.2.3-beta.1.dev.43"
    )
    assert Version.parse("0.1.0.post1").bump("patch") == Version.parse("0.1.1")
    assert Version.parse("0.1.0.post1").bump("rc") == Version.parse("0.1.1rc1")
    with pytest.raises(ValueError, match="no pre-release"):
        Version.parse("0.1.0.post1").bump("release")
