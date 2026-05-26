"""Shared fixtures and helpers for MCP tests.

All tests in this package require the [mcp] optional extra.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("fastmcp", reason="[mcp] extra not installed")

pytestmark = pytest.mark.mcp


class _CaptureMCP:
    """Minimal FastMCP shim that captures inner decorated functions for unit testing.

    Replaces FastMCP in registration calls so that each inner tool/resource/prompt
    function can be extracted and called directly with a mocked Context.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Any] = {}
        self._resources: dict[str, Any] = {}
        self._prompts: dict[str, Any] = {}

    def tool(self, *args: Any, **kwargs: Any) -> Any:
        def decorator(fn: Any) -> Any:
            self._tools[fn.__name__] = fn
            return fn

        return decorator

    def resource(self, *args: Any, **kwargs: Any) -> Any:
        def decorator(fn: Any) -> Any:
            self._resources[fn.__name__] = fn
            return fn

        return decorator

    def prompt(self, *args: Any, **kwargs: Any) -> Any:
        def decorator(fn: Any) -> Any:
            self._prompts[fn.__name__] = fn
            return fn

        return decorator

    def add_provider(self, *args: Any, **kwargs: Any) -> None:
        pass


@pytest.fixture
def capture_mcp() -> _CaptureMCP:
    """Return a fresh _CaptureMCP instance."""
    return _CaptureMCP()


@pytest.fixture
def mock_ctx(tmp_path: Any) -> MagicMock:
    """Return a MagicMock Context with a tmp_path root and no config."""
    ctx = MagicMock()
    ctx.lifespan_context = {"root": tmp_path, "config": None}
    ctx.info = AsyncMock()
    ctx.warning = AsyncMock()
    ctx.report_progress = AsyncMock()
    return ctx
