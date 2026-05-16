from __future__ import annotations

import pytest

from repo_release_tools.version.semver import Version


def test_parse_version() -> None:
    version = Version.parse("1.2.3")
    assert str(version) == "1.2.3"


def test_bump_patch() -> None:
    assert str(Version.parse("1.2.3").bump("patch")) == "1.2.4"


def test_bump_minor() -> None:
    assert str(Version.parse("1.2.3").bump("minor")) == "1.3.0"


def test_bump_major() -> None:
    assert str(Version.parse("1.2.3").bump("major")) == "2.0.0"


def test_parse_invalid_semver_raises() -> None:
    with pytest.raises(ValueError, match="Invalid semver"):
        Version.parse("not-a-version")


def test_bump_unknown_kind_raises() -> None:
    with pytest.raises(ValueError, match="Unknown bump kind"):
        Version.parse("1.2.3").bump("hotfix")


def test_parse_with_pre_release() -> None:
    v = Version.parse("1.2.3-alpha.1")
    assert v.pre == "alpha.1"
    assert str(v) == "1.2.3-alpha.1"


def test_parse_with_build_metadata() -> None:
    v = Version.parse("1.2.3+build.42")
    assert v.build == "build.42"
    assert str(v) == "1.2.3+build.42"


def test_parse_with_pre_and_build() -> None:
    v = Version.parse("1.0.0-rc.1+exp.sha.5114f85")
    assert v.pre == "rc.1"
    assert v.build == "exp.sha.5114f85"
    assert str(v) == "1.0.0-rc.1+exp.sha.5114f85"


def test_bump_pre_release_increments_numeric_suffix() -> None:
    v = Version.parse("1.2.3-alpha.1")
    result = v.bump("pre-release")
    assert str(result) == "1.2.3-alpha.2"


def test_bump_pre_release_appends_1_when_no_suffix() -> None:
    v = Version.parse("1.2.3-beta")
    result = v.bump("pre-release")
    assert str(result) == "1.2.3-beta.1"


def test_bump_pre_release_on_stable_raises() -> None:
    v = Version.parse("1.2.3")
    with pytest.raises(ValueError, match="Cannot bump pre-release"):
        v.bump("pre-release")


def test_set_channel_on_stable_starts_at_1() -> None:
    v = Version.parse("1.2.3")
    result = v.bump("alpha")
    assert str(result) == "1.2.3-alpha.1"


def test_set_channel_same_channel_increments() -> None:
    v = Version.parse("1.2.3-alpha.2")
    result = v.bump("alpha")
    assert str(result) == "1.2.3-alpha.3"


def test_set_channel_switch_resets_counter() -> None:
    v = Version.parse("1.2.3-alpha.3")
    result = v.bump("beta")
    assert str(result) == "1.2.3-beta.1"


def test_bump_rc_channel() -> None:
    v = Version.parse("1.2.3-rc.1")
    result = v.bump("rc")
    assert str(result) == "1.2.3-rc.2"


def test_stable_drops_pre_and_build() -> None:
    v = Version.parse("2.0.0-rc.3+build.7")
    assert str(v.stable()) == "2.0.0"


def test_is_pre_release_true() -> None:
    assert Version.parse("1.0.0-alpha.1").is_pre_release() is True


def test_is_pre_release_false() -> None:
    assert Version.parse("1.0.0").is_pre_release() is False
