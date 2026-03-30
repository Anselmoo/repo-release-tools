from repo_release_tools.versioning import Version


def test_parse_version() -> None:
    version = Version.parse("1.2.3")
    assert str(version) == "1.2.3"


def test_bump_patch() -> None:
    assert str(Version.parse("1.2.3").bump("patch")) == "1.2.4"


def test_bump_minor() -> None:
    assert str(Version.parse("1.2.3").bump("minor")) == "1.3.0"


def test_bump_major() -> None:
    assert str(Version.parse("1.2.3").bump("major")) == "2.0.0"
