"""Tests for the rrt FastMCP server lifecycle (server.py)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("fastmcp", reason="[mcp] extra not installed")

from fastmcp import FastMCP

from repo_release_tools.mcp.server import (
    AUTH_TOKEN_ENV_VAR,
    _build_auth_provider,
    _find_repo_root,
    _lifespan,
    create_server,
    main,
)

pytestmark = pytest.mark.mcp


# ── _find_repo_root ───────────────────────────────────────────────────────────


def test_find_repo_root_via_rrt_dir(tmp_path: Path, monkeypatch: Any) -> None:
    (tmp_path / ".rrt").mkdir()
    monkeypatch.chdir(tmp_path)
    assert _find_repo_root() == tmp_path


def test_find_repo_root_via_pyproject(tmp_path: Path, monkeypatch: Any) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.rrt]")
    monkeypatch.chdir(tmp_path)
    assert _find_repo_root() == tmp_path


def test_find_repo_root_fallback_to_cwd(tmp_path: Path, monkeypatch: Any) -> None:
    # Subdirectory with no markers; parents are all temp (no pyproject.toml above tmp_path)
    sub = tmp_path / "a" / "b" / "c"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)
    root = _find_repo_root()
    # Should fall back to cwd (sub) since no marker found in ancestors under tmp_path
    assert root == sub


# ── _lifespan ─────────────────────────────────────────────────────────────────


def test_lifespan_config_success(tmp_path: Path, monkeypatch: Any) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.rrt]")
    monkeypatch.chdir(tmp_path)

    async def _run() -> dict[str, Any]:
        server: MagicMock = MagicMock()
        mock_config = MagicMock()
        with patch("repo_release_tools.config.load_or_autodetect_config", return_value=mock_config):
            async with _lifespan(server) as ctx:
                return ctx

    ctx = asyncio.run(_run())
    assert "root" in ctx
    assert "config" in ctx
    assert ctx["config"] is not None
    assert ctx["config_error"] is None


def test_lifespan_config_failure(tmp_path: Path, monkeypatch: Any) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.rrt]")
    monkeypatch.chdir(tmp_path)

    async def _run() -> dict[str, Any]:
        server: MagicMock = MagicMock()
        with patch(
            "repo_release_tools.config.load_or_autodetect_config",
            side_effect=FileNotFoundError("no config"),
        ):
            async with _lifespan(server) as ctx:
                return ctx

    ctx = asyncio.run(_run())
    assert ctx["config"] is None
    assert ctx["config_error"] is None


def test_lifespan_value_error(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)

    async def _run() -> dict[str, Any]:
        server: MagicMock = MagicMock()
        with patch(
            "repo_release_tools.config.load_or_autodetect_config",
            side_effect=ValueError("bad config"),
        ):
            async with _lifespan(server) as ctx:
                return ctx

    ctx = asyncio.run(_run())
    assert ctx["config"] is None
    assert ctx["config_error"] is not None
    assert "bad config" in ctx["config_error"]


def test_lifespan_runtime_error(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)

    async def _run() -> dict[str, Any]:
        server: MagicMock = MagicMock()
        with patch(
            "repo_release_tools.config.load_or_autodetect_config",
            side_effect=RuntimeError("runtime"),
        ):
            async with _lifespan(server) as ctx:
                return ctx

    ctx = asyncio.run(_run())
    assert ctx["config"] is None
    assert ctx["config_error"] is not None
    assert "runtime" in ctx["config_error"]


# ── create_server ─────────────────────────────────────────────────────────────


def test_create_server_returns_fastmcp() -> None:
    server = create_server()
    assert isinstance(server, FastMCP)


# ── main ──────────────────────────────────────────────────────────────────────


def test_main_no_fastmcp(monkeypatch: Any) -> None:
    """main() exits with code 1 when fastmcp is not importable."""
    orig_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

    def fail_fastmcp(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "fastmcp":
            raise ImportError("no module")
        return orig_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fail_fastmcp):
        with pytest.raises(SystemExit) as exc_info:
            main()
    assert exc_info.value.code == 1


def test_main_stdio(monkeypatch: Any) -> None:
    monkeypatch.setattr(sys, "argv", ["rrt-mcp"])
    mock_server = MagicMock()
    with patch("repo_release_tools.mcp.server.create_server", return_value=mock_server):
        main()
    mock_server.run.assert_called_once_with(transport="stdio")


def test_main_http(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["rrt-mcp", "--transport", "http", "--port", "9000", "--auth-token", "s3cr3t"],
    )
    mock_server = MagicMock()
    with patch(
        "repo_release_tools.mcp.server.create_server", return_value=mock_server
    ) as mock_create:
        main()
    mock_create.assert_called_once_with(auth_token="s3cr3t")
    mock_server.run.assert_called_once_with(transport="http", host="127.0.0.1", port=9000)


# ── HTTP transport authentication (SEC-002) ─────────────────────────────────


def test_build_auth_provider_wires_token() -> None:
    """_build_auth_provider returns a FastMCP StaticTokenVerifier for the token."""
    from fastmcp.server.auth import StaticTokenVerifier

    provider = _build_auth_provider("my-token")
    assert isinstance(provider, StaticTokenVerifier)


def test_create_server_no_auth_by_default() -> None:
    """create_server() with no auth_token leaves the server unauthenticated (stdio use)."""
    server = create_server()
    assert server.auth is None


def test_create_server_with_auth_token_wires_provider() -> None:
    """create_server(auth_token=...) wires a StaticTokenVerifier into the FastMCP server."""
    from fastmcp.server.auth import StaticTokenVerifier

    server = create_server(auth_token="my-token")
    assert isinstance(server.auth, StaticTokenVerifier)


def test_main_stdio_ignores_auth_token_env(monkeypatch: Any) -> None:
    """stdio transport starts normally even with no token configured (no regression)."""
    monkeypatch.delenv(AUTH_TOKEN_ENV_VAR, raising=False)
    monkeypatch.setattr(sys, "argv", ["rrt-mcp"])
    mock_server = MagicMock()
    with patch(
        "repo_release_tools.mcp.server.create_server", return_value=mock_server
    ) as mock_create:
        main()
    mock_create.assert_called_once_with()
    mock_server.run.assert_called_once_with(transport="stdio")


def test_main_http_no_token_refuses_to_start(monkeypatch: Any) -> None:
    """http transport with no token (flag or env var) refuses to start."""
    monkeypatch.delenv(AUTH_TOKEN_ENV_VAR, raising=False)
    monkeypatch.setattr(sys, "argv", ["rrt-mcp", "--transport", "http"])
    mock_server = MagicMock()
    with patch("repo_release_tools.mcp.server.create_server", return_value=mock_server):
        with pytest.raises(SystemExit) as exc_info:
            main()
    assert exc_info.value.code == 1
    mock_server.run.assert_not_called()


def test_main_http_token_from_env_var(monkeypatch: Any) -> None:
    """http transport reads the token from RRT_MCP_AUTH_TOKEN when --auth-token is absent."""
    monkeypatch.setenv(AUTH_TOKEN_ENV_VAR, "env-token")
    monkeypatch.setattr(sys, "argv", ["rrt-mcp", "--transport", "http"])
    mock_server = MagicMock()
    with patch(
        "repo_release_tools.mcp.server.create_server", return_value=mock_server
    ) as mock_create:
        main()
    mock_create.assert_called_once_with(auth_token="env-token")
    mock_server.run.assert_called_once_with(transport="http", host="127.0.0.1", port=8000)


def test_main_http_flag_overrides_env_var(monkeypatch: Any) -> None:
    """--auth-token takes precedence over RRT_MCP_AUTH_TOKEN when both are set."""
    monkeypatch.setenv(AUTH_TOKEN_ENV_VAR, "env-token")
    monkeypatch.setattr(
        sys, "argv", ["rrt-mcp", "--transport", "http", "--auth-token", "flag-token"]
    )
    mock_server = MagicMock()
    with patch(
        "repo_release_tools.mcp.server.create_server", return_value=mock_server
    ) as mock_create:
        main()
    mock_create.assert_called_once_with(auth_token="flag-token")
