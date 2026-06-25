"""Fetch release versions for an upstream package from PyPI (stdlib only)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

PYPI_JSON_URL = "https://pypi.org/pypi/{package}/json"


def fetch_pypi_versions(package: str, *, timeout: int = 10) -> list[str]:
    """Return all release version strings for *package* from PyPI.

    Mirrors the stdlib-HTTP pattern in ``eol/core.py``: returns an empty list
    on any network or decode error rather than raising.
    """
    url = PYPI_JSON_URL.format(package=package)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        return []
    releases = data.get("releases", {})
    return list(releases.keys())
