from __future__ import annotations

from repo_release_tools.version.semver import Version, newer_versions


def test_sort_key_orders_pre_release_before_stable() -> None:
    assert Version.parse("1.2.0-rc.1").sort_key() < Version.parse("1.2.0").sort_key()


def test_newer_versions_filters_and_sorts() -> None:
    cur = Version.parse("0.5.0")
    cands = [Version.parse(v) for v in ["0.4.9", "0.5.0", "0.6.0", "0.5.1"]]
    assert [str(v) for v in newer_versions(cur, cands)] == ["0.5.1", "0.6.0"]
