"""Tests for the multi-provider version fetcher (providers.py).

All tests mock urllib.request.urlopen — no real network calls.
"""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from collections.abc import Callable
from types import TracebackType

import pytest

from repo_release_tools.sync import providers

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _Resp(io.BytesIO):
    """Minimal context-manager wrapper around BytesIO to mimic urlopen response."""

    def __enter__(self) -> _Resp:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        return None


def _make_urlopen(
    payload: object, *, assert_url: str | None = None, assert_ua: str | None = None
) -> Callable[[urllib.request.Request, int], _Resp]:
    """Return a fake urlopen that returns *payload* encoded as JSON.

    Optionally asserts that the URL contains *assert_url* and/or that the
    ``User-Agent`` header of the ``Request`` object equals *assert_ua*.
    """

    def fake_urlopen(req: urllib.request.Request, timeout: int = 10) -> _Resp:
        if assert_url is not None:
            assert assert_url in req.full_url
        if assert_ua is not None:
            assert req.get_header("User-agent") == assert_ua
        return _Resp(json.dumps(payload).encode())

    return fake_urlopen


def _make_urlopen_error(exc: Exception) -> Callable[[urllib.request.Request, int], None]:
    """Return a fake urlopen that always raises *exc*."""

    def fake_urlopen(req: urllib.request.Request, timeout: int = 10) -> None:
        raise exc

    return fake_urlopen


# ---------------------------------------------------------------------------
# npm
# ---------------------------------------------------------------------------


def test_fetch_versions_npm_success(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"versions": {"1.0.0": {}, "1.1.0": {}, "2.0.0-beta.1": {}}}
    monkeypatch.setattr(
        providers.urllib.request,
        "urlopen",
        _make_urlopen(payload, assert_url="registry.npmjs.org/lodash"),
    )
    out = providers.fetch_versions("lodash", "npm")
    assert set(out) == {"1.0.0", "1.1.0", "2.0.0-beta.1"}


def test_fetch_versions_npm_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        providers.urllib.request,
        "urlopen",
        _make_urlopen_error(urllib.error.URLError("offline")),
    )
    assert providers.fetch_versions("lodash", "npm") == []


def test_fetch_versions_npm_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Response that lacks the 'versions' key returns []."""
    monkeypatch.setattr(
        providers.urllib.request,
        "urlopen",
        _make_urlopen({"name": "lodash"}),
    )
    assert providers.fetch_versions("lodash", "npm") == []


def test_fetch_versions_npm_non_dict_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        providers.urllib.request,
        "urlopen",
        _make_urlopen(["not", "a", "dict"]),
    )
    assert providers.fetch_versions("lodash", "npm") == []


def test_fetch_versions_npm_scoped_package_encodes_slash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SEC-005: a scoped package's '/' separator is percent-encoded as %2F."""
    payload = {"versions": {"1.0.0": {}}}
    monkeypatch.setattr(
        providers.urllib.request,
        "urlopen",
        _make_urlopen(payload, assert_url="registry.npmjs.org/@types%2Fnode"),
    )
    out = providers.fetch_versions("@types/node", "npm")
    assert set(out) == {"1.0.0"}


def test_fetch_versions_npm_rejects_extra_path_segments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SEC-005: an adversarial package name cannot introduce extra URL path segments."""
    captured: dict[str, str] = {}

    def fake_urlopen(req: urllib.request.Request, timeout: int = 10) -> _Resp:
        captured["url"] = req.full_url
        return _Resp(json.dumps({"versions": {}}).encode())

    monkeypatch.setattr(providers.urllib.request, "urlopen", fake_urlopen)
    providers.fetch_versions("../../evil", "npm")
    assert "/../" not in captured["url"]
    assert captured["url"] == "https://registry.npmjs.org/..%2F..%2Fevil"


# ---------------------------------------------------------------------------
# nuget
# ---------------------------------------------------------------------------


def test_fetch_versions_nuget_success(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"versions": ["1.0.0", "1.1.0", "2.0.0"]}
    monkeypatch.setattr(
        providers.urllib.request,
        "urlopen",
        _make_urlopen(
            payload, assert_url="api.nuget.org/v3-flatcontainer/newtonsoft.json/index.json"
        ),
    )
    out = providers.fetch_versions("Newtonsoft.Json", "nuget")
    assert out == ["1.0.0", "1.1.0", "2.0.0"]


def test_fetch_versions_nuget_lowercases_package(monkeypatch: pytest.MonkeyPatch) -> None:
    """Package id must be lowercased in the URL."""
    captured: list[str] = []

    def fake_urlopen(req: urllib.request.Request, timeout: int = 10) -> _Resp:
        captured.append(req.full_url)
        return _Resp(json.dumps({"versions": []}).encode())

    monkeypatch.setattr(providers.urllib.request, "urlopen", fake_urlopen)
    providers.fetch_versions("MyPackage", "nuget")
    assert "mypackage" in captured[0]


def test_fetch_versions_nuget_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        providers.urllib.request,
        "urlopen",
        _make_urlopen_error(OSError("conn refused")),
    )
    assert providers.fetch_versions("Newtonsoft.Json", "nuget") == []


def test_fetch_versions_nuget_non_dict_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        providers.urllib.request,
        "urlopen",
        _make_urlopen(None),
    )
    assert providers.fetch_versions("Newtonsoft.Json", "nuget") == []


def test_fetch_versions_nuget_missing_versions_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        providers.urllib.request,
        "urlopen",
        _make_urlopen({"other": "data"}),
    )
    assert providers.fetch_versions("Newtonsoft.Json", "nuget") == []


def test_fetch_versions_nuget_rejects_extra_path_segments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SEC-005: an adversarial package name cannot introduce extra URL path segments."""
    captured: dict[str, str] = {}

    def fake_urlopen(req: urllib.request.Request, timeout: int = 10) -> _Resp:
        captured["url"] = req.full_url
        return _Resp(json.dumps({"versions": []}).encode())

    monkeypatch.setattr(providers.urllib.request, "urlopen", fake_urlopen)
    providers.fetch_versions("../../evil", "nuget")
    assert "/../" not in captured["url"]
    assert captured["url"] == ("https://api.nuget.org/v3-flatcontainer/..%2F..%2Fevil/index.json")


# ---------------------------------------------------------------------------
# crates
# ---------------------------------------------------------------------------


def test_fetch_versions_crates_success(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"versions": [{"num": "0.1.0"}, {"num": "0.2.0"}, {"num": "1.0.0"}]}
    monkeypatch.setattr(
        providers.urllib.request,
        "urlopen",
        _make_urlopen(payload, assert_url="crates.io/api/v1/crates/serde/versions"),
    )
    out = providers.fetch_versions("serde", "crates")
    assert set(out) == {"0.1.0", "0.2.0", "1.0.0"}


def test_fetch_versions_crates_sends_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    """crates.io fetcher must send the correct User-Agent header."""
    payload = {"versions": [{"num": "1.0.0"}]}
    monkeypatch.setattr(
        providers.urllib.request,
        "urlopen",
        _make_urlopen(payload, assert_ua=providers.USER_AGENT),
    )
    out = providers.fetch_versions("serde", "crates")
    assert out == ["1.0.0"]


def test_fetch_versions_crates_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        providers.urllib.request,
        "urlopen",
        _make_urlopen_error(urllib.error.URLError("403 Forbidden")),
    )
    assert providers.fetch_versions("serde", "crates") == []


def test_fetch_versions_crates_non_dict_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        providers.urllib.request,
        "urlopen",
        _make_urlopen("not a dict"),
    )
    assert providers.fetch_versions("serde", "crates") == []


def test_fetch_versions_crates_missing_versions_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        providers.urllib.request,
        "urlopen",
        _make_urlopen({"crate": {}}),
    )
    assert providers.fetch_versions("serde", "crates") == []


def test_fetch_versions_crates_rejects_extra_path_segments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SEC-005: an adversarial package name cannot introduce extra URL path segments."""
    captured: dict[str, str] = {}

    def fake_urlopen(req: urllib.request.Request, timeout: int = 10) -> _Resp:
        captured["url"] = req.full_url
        return _Resp(json.dumps({"versions": []}).encode())

    monkeypatch.setattr(providers.urllib.request, "urlopen", fake_urlopen)
    providers.fetch_versions("../../evil", "crates")
    assert "/../" not in captured["url"]
    assert captured["url"] == ("https://crates.io/api/v1/crates/..%2F..%2Fevil/versions")


# ---------------------------------------------------------------------------
# packagist
# ---------------------------------------------------------------------------


def test_fetch_versions_packagist_success(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "package": {
            "versions": {
                "v1.0.0": {},
                "v1.1.0": {},
                "dev-main": {},
            }
        }
    }
    monkeypatch.setattr(
        providers.urllib.request,
        "urlopen",
        _make_urlopen(payload, assert_url="packagist.org/packages/symfony/console.json"),
    )
    out = providers.fetch_versions("symfony/console", "packagist")
    assert set(out) == {"v1.0.0", "v1.1.0", "dev-main"}


def test_fetch_versions_packagist_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        providers.urllib.request,
        "urlopen",
        _make_urlopen_error(urllib.error.URLError("timeout")),
    )
    assert providers.fetch_versions("symfony/console", "packagist") == []


def test_fetch_versions_packagist_non_dict_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        providers.urllib.request,
        "urlopen",
        _make_urlopen(42),
    )
    assert providers.fetch_versions("symfony/console", "packagist") == []


def test_fetch_versions_packagist_missing_package_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        providers.urllib.request,
        "urlopen",
        _make_urlopen({"something": "else"}),
    )
    assert providers.fetch_versions("symfony/console", "packagist") == []


def test_fetch_versions_packagist_missing_versions_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        providers.urllib.request,
        "urlopen",
        _make_urlopen({"package": {"name": "symfony/console"}}),
    )
    assert providers.fetch_versions("symfony/console", "packagist") == []


def test_fetch_versions_packagist_percent_encodes_each_segment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SEC-005: each vendor/name segment is percent-encoded; the separator stays literal."""
    captured: dict[str, str] = {}

    def fake_urlopen(req: urllib.request.Request, timeout: int = 10) -> _Resp:
        captured["url"] = req.full_url
        return _Resp(json.dumps({"package": {"versions": {}}}).encode())

    monkeypatch.setattr(providers.urllib.request, "urlopen", fake_urlopen)
    providers.fetch_versions("vendor name/pkg?name", "packagist")
    assert captured["url"] == "https://packagist.org/packages/vendor%20name/pkg%3Fname.json"


def test_fetch_versions_packagist_percent_encodes_bare_package_without_slash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A malformed package with no vendor/name separator is still percent-encoded whole."""
    captured: dict[str, str] = {}

    def fake_urlopen(req: urllib.request.Request, timeout: int = 10) -> _Resp:
        captured["url"] = req.full_url
        return _Resp(json.dumps({"package": {"versions": {}}}).encode())

    monkeypatch.setattr(providers.urllib.request, "urlopen", fake_urlopen)
    providers.fetch_versions("bare package", "packagist")
    assert captured["url"] == "https://packagist.org/packages/bare%20package.json"


def test_fetch_versions_packagist_rejects_extra_path_segments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SEC-005: a bare ``..`` segment cannot survive as a literal dot-segment.

    ``.`` is an RFC3986 unreserved character, so ``urllib.parse.quote()``
    never encodes it - a vendor/name segment that is *exactly* ``..`` would
    otherwise pass through untouched and could be removed by dot-segment
    normalization (RFC 3986 5.2.4) in an intermediary, escaping the intended
    ``/packages/`` prefix.
    """
    captured: dict[str, str] = {}

    def fake_urlopen(req: urllib.request.Request, timeout: int = 10) -> _Resp:
        captured["url"] = req.full_url
        return _Resp(json.dumps({"package": {"versions": {}}}).encode())

    monkeypatch.setattr(providers.urllib.request, "urlopen", fake_urlopen)
    providers.fetch_versions("../../evil", "packagist")
    assert "/../" not in captured["url"]
    assert captured["url"] == "https://packagist.org/packages/%2E%2E/..%2Fevil.json"


# ---------------------------------------------------------------------------
# pypi (via delegation to fetch_pypi_versions)
# ---------------------------------------------------------------------------


def test_fetch_versions_pypi_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    """pypi provider delegates to fetch_pypi_versions."""
    called: list[tuple[str, int]] = []

    def fake_fetch(package: str, *, timeout: int = 10) -> list[str]:
        called.append((package, timeout))
        return ["1.0.0", "2.0.0"]

    monkeypatch.setattr(providers, "fetch_pypi_versions", fake_fetch)
    out = providers.fetch_versions("ruff", "pypi", timeout=5)
    assert out == ["1.0.0", "2.0.0"]
    assert called == [("ruff", 5)]


# ---------------------------------------------------------------------------
# Unknown provider
# ---------------------------------------------------------------------------


def test_fetch_versions_unknown_provider_returns_empty() -> None:
    assert providers.fetch_versions("anything", "maven") == []
    assert providers.fetch_versions("anything", "") == []
    assert providers.fetch_versions("anything", "PYPI") == []  # case-sensitive


# ---------------------------------------------------------------------------
# PROVIDERS constant
# ---------------------------------------------------------------------------


def test_providers_constant_contains_all_five() -> None:
    assert providers.PROVIDERS == frozenset({"pypi", "npm", "nuget", "crates", "packagist"})


def test_providers_constant_is_frozenset() -> None:
    assert isinstance(providers.PROVIDERS, frozenset)
