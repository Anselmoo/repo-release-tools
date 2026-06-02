import pytest

from repo_release_tools.tools import platform as platform_mod
from repo_release_tools.tools.platform import RegistryTemplate, _load_icon_path_from_assets


class _FakePath:
    def __init__(self, text: str) -> None:
        self._text = text

    def read_text(self, encoding: str = "utf-8") -> str:
        return self._text


class _FakeFiles:
    def __init__(self, text: str) -> None:
        self._text = text

    def joinpath(self, _name: str) -> "_FakePath":
        return _FakePath(self._text)


def test_format_registry_url_pypi_default() -> None:
    url = platform_mod.format_registry_url("pypi", package="requests")
    assert url == "https://pypi.org/project/requests/"


def test_format_registry_url_pypi_versioned() -> None:
    url = platform_mod.format_registry_url(
        "pypi", template_key="versioned", package="requests", version="2.28.1"
    )
    assert url == "https://pypi.org/project/requests/2.28.1/"


def test_format_registry_url_missing_required() -> None:
    with pytest.raises(ValueError):
        platform_mod.format_registry_url("pypi")


def test_validate_registry_unknown() -> None:
    with pytest.raises(ValueError):
        platform_mod.validate_registry_template("not-a-registry")


def test_registry_template_get_returns_value_and_default() -> None:
    tmpl = RegistryTemplate(templates={"default": "https://example.com/{pkg}"}, required=("pkg",))
    assert tmpl.get("default") == "https://example.com/{pkg}"
    assert tmpl.get("missing") is None
    assert tmpl.get("missing", "fallback") == "fallback"


def test_validate_registry_template_bad_key_raises() -> None:
    platform_mod.REGISTRY_TEMPLATES["_test_reg"] = RegistryTemplate(
        templates={"other": "https://x.com/{p}"}, required=("p",)
    )
    try:
        with pytest.raises(ValueError, match="has no template"):
            platform_mod.validate_registry_template("_test_reg", template_key="missing_key")
    finally:
        del platform_mod.REGISTRY_TEMPLATES["_test_reg"]


def test_format_registry_url_unknown_registry_raises() -> None:
    with pytest.raises(ValueError, match="unknown registry"):
        platform_mod.format_registry_url("not-a-registry", package="foo")


def test_format_registry_url_unknown_template_key_falls_back_to_default() -> None:
    url = platform_mod.format_registry_url("pypi", template_key="nonexistent", package="requests")
    assert "requests" in url


def test_format_registry_url_non_string_template() -> None:
    tmpl = RegistryTemplate(
        templates={"default": "42"},  # type: ignore[arg-type]
        required=(),
    )
    platform_mod.REGISTRY_TEMPLATES["_int_tmpl"] = tmpl
    try:
        url = platform_mod.format_registry_url("_int_tmpl")
        assert url == "42"
    finally:
        del platform_mod.REGISTRY_TEMPLATES["_int_tmpl"]


def test_load_icon_path_returns_path_data_from_svg(monkeypatch: pytest.MonkeyPatch) -> None:
    svg = '<svg><path d="M 0 0 L 10 10"/></svg>'
    monkeypatch.setattr(platform_mod.resources, "files", lambda _pkg: _FakeFiles(svg))
    result = _load_icon_path_from_assets("testicon")
    assert result == "M 0 0 L 10 10"


def test_load_icon_path_fallback_returns_stripped_path_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # SVG with no <path d="..."> but content that looks like path data
    path_data = "M 10 20 L 30 40"
    monkeypatch.setattr(platform_mod.resources, "files", lambda _pkg: _FakeFiles(path_data))
    result = _load_icon_path_from_assets("testicon")
    assert result == path_data


def test_load_icon_path_returns_none_for_non_path_content(monkeypatch: pytest.MonkeyPatch) -> None:
    # SVG with no <path d="..."> and content that does NOT look like path data
    non_path = "<xml>complicated stuff &amp; more</xml>"
    monkeypatch.setattr(platform_mod.resources, "files", lambda _pkg: _FakeFiles(non_path))
    result = _load_icon_path_from_assets("testicon")
    assert result is None


def test_load_icon_path_returns_none_on_missing_asset(monkeypatch: pytest.MonkeyPatch) -> None:
    class _ErrorFiles:
        def joinpath(self, _name: str) -> None:  # type: ignore[return]
            raise FileNotFoundError("no icon")

    monkeypatch.setattr(platform_mod.resources, "files", lambda _pkg: _ErrorFiles())
    result = _load_icon_path_from_assets("missing")
    assert result is None
