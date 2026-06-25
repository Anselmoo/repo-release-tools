from __future__ import annotations

import io
import json
from types import TracebackType

import pytest

from repo_release_tools.sync import pypi


def test_fetch_pypi_versions_parses_releases(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"releases": {"0.1.0": [], "0.2.0": [], "0.2.0rc1": []}}

    class _Resp(io.BytesIO):
        def __enter__(self) -> _Resp:
            return self

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc_val: BaseException | None,
            exc_tb: TracebackType | None,
        ) -> None:
            return None

    def fake_urlopen(url: str, timeout: int = 10) -> _Resp:
        assert "pypi.org/pypi/ruff/json" in url
        return _Resp(json.dumps(payload).encode())

    monkeypatch.setattr(pypi.urllib.request, "urlopen", fake_urlopen)
    out = pypi.fetch_pypi_versions("ruff")
    assert set(out) == {"0.1.0", "0.2.0", "0.2.0rc1"}


def test_fetch_pypi_versions_returns_empty_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(url: str, timeout: int = 10) -> None:
        raise pypi.urllib.error.URLError("offline")

    monkeypatch.setattr(pypi.urllib.request, "urlopen", boom)
    assert pypi.fetch_pypi_versions("ruff") == []
