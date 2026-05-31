import pytest

from repo_release_tools.tools import platform as platform_mod


def test_format_registry_url_pypi_default():
    url = platform_mod.format_registry_url("pypi", package="requests")
    assert url == "https://pypi.org/project/requests/"


def test_format_registry_url_pypi_versioned():
    url = platform_mod.format_registry_url(
        "pypi", template_key="versioned", package="requests", version="2.28.1"
    )
    assert url == "https://pypi.org/project/requests/2.28.1/"


def test_format_registry_url_missing_required():
    with pytest.raises(ValueError):
        platform_mod.format_registry_url("pypi")


def test_validate_registry_unknown():
    with pytest.raises(ValueError):
        platform_mod.validate_registry_template("not-a-registry")
