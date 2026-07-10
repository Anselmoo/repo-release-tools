"""Multi-provider version fetcher — stdlib only (urllib + json).

Supported providers: pypi, npm, nuget, crates, packagist.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from repo_release_tools.sync.pypi import fetch_pypi_versions

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

USER_AGENT = "repo-release-tools (+https://github.com/Anselmoo/repo-release-tools)"

PROVIDERS: frozenset[str] = frozenset({"pypi", "npm", "nuget", "crates", "packagist"})

# ---------------------------------------------------------------------------
# Shared HTTP helper
# ---------------------------------------------------------------------------


def _fetch_json(
    url: str, *, timeout: int = 10, headers: dict[str, str] | None = None
) -> object | None:
    """GET *url* and return parsed JSON, or None on any network/decode error."""
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        return None


# ---------------------------------------------------------------------------
# Per-provider fetchers
# ---------------------------------------------------------------------------


def _quote_npm_package(package: str) -> str:
    """Percent-encode an npm package identifier, handling ``@scope/name`` form.

    The npm registry expects a scoped package's ``/`` separator to be
    percent-encoded as ``%2F`` (``@scope%2Fname``) — an unencoded ``/`` would
    otherwise be a second path segment. Quote with ``safe="@"`` so the scope
    marker stays literal, then encode the separating slash. Any *other*
    slash in the input (not the single scope separator) is left encoded by
    ``quote`` too, so it cannot introduce extra path segments (CWE-20).
    """
    quoted = urllib.parse.quote(package, safe="@")
    return quoted.replace("/", "%2F")


def _fetch_npm_versions(package: str, *, timeout: int = 10) -> list[str]:
    """Return all versions of *package* from the npm registry."""
    url = f"https://registry.npmjs.org/{_quote_npm_package(package)}"
    data = _fetch_json(url, timeout=timeout)
    if not isinstance(data, dict):
        return []
    versions = data.get("versions")
    if not isinstance(versions, dict):
        return []
    return [str(k) for k in versions]


def _fetch_nuget_versions(package: str, *, timeout: int = 10) -> list[str]:
    """Return all versions of *package* from NuGet (package id is lowercased)."""
    url = (
        "https://api.nuget.org/v3-flatcontainer/"
        f"{urllib.parse.quote(package.lower(), safe='')}/index.json"
    )
    data = _fetch_json(url, timeout=timeout)
    if not isinstance(data, dict):
        return []
    versions = data.get("versions")
    if not isinstance(versions, list):
        return []
    return [str(v) for v in versions]


def _fetch_crates_versions(package: str, *, timeout: int = 10) -> list[str]:
    """Return all versions of *package* from crates.io (requires User-Agent)."""
    url = f"https://crates.io/api/v1/crates/{urllib.parse.quote(package, safe='')}/versions"
    data = _fetch_json(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
    if not isinstance(data, dict):
        return []
    versions = data.get("versions")
    if not isinstance(versions, list):
        return []
    result: list[str] = []
    for v in versions:
        if isinstance(v, dict):
            num = v.get("num")
            if num is not None:
                result.append(str(num))
    return result


def _quote_vendor_name_package(package: str) -> str:
    """Percent-encode a Packagist ``vendor/name`` identifier, segment by segment.

    Packagist routes on a literal two-segment ``vendor/name`` path, so the
    single separating ``/`` must stay literal — but each segment (and any
    *extra* ``/`` beyond the first, e.g. a ``../`` traversal attempt) is
    percent-encoded with ``safe=""`` so the value cannot smuggle additional
    path segments (CWE-20).
    """
    return "/".join(urllib.parse.quote(part, safe="") for part in package.split("/"))


def _fetch_packagist_versions(package: str, *, timeout: int = 10) -> list[str]:
    """Return all versions of *package* from Packagist (vendor/name format)."""
    url = f"https://packagist.org/packages/{_quote_vendor_name_package(package)}.json"
    data = _fetch_json(url, timeout=timeout)
    if not isinstance(data, dict):
        return []
    pkg = data.get("package")
    if not isinstance(pkg, dict):
        return []
    versions = pkg.get("versions")
    if not isinstance(versions, dict):
        return []
    return [str(k) for k in versions]


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def fetch_versions(package: str, provider: str = "pypi", *, timeout: int = 10) -> list[str]:
    """Return all released versions of *package* from *provider*; [] on error/unknown provider.

    Supported providers: pypi, npm, nuget, crates, packagist.
    Unknown provider values silently return an empty list (no exception raised).
    """
    if provider == "pypi":
        return fetch_pypi_versions(package, timeout=timeout)
    if provider == "npm":
        return _fetch_npm_versions(package, timeout=timeout)
    if provider == "nuget":
        return _fetch_nuget_versions(package, timeout=timeout)
    if provider == "crates":
        return _fetch_crates_versions(package, timeout=timeout)
    if provider == "packagist":
        return _fetch_packagist_versions(package, timeout=timeout)
    return []
