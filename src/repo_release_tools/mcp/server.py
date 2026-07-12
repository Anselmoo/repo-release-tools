"""Main FastMCP server for rrt — exposes rrt capabilities as MCP tools, resources, and prompts.

HTTP transport authentication (SEC-002)
----------------------------------------
``stdio`` transport (the default) is process-local, piped over stdin/stdout, and
needs no authentication. ``--transport http`` binds a real network listener —
anyone who can reach ``--host``:``--port`` can invoke every ``rrt_*`` tool,
including destructive ones like ``rrt_bump`` and ``rrt_publish_snapshot``.

To prevent that, ``--transport http`` requires a bearer token, supplied via
``--auth-token`` or the ``RRT_MCP_AUTH_TOKEN`` environment variable. The token
is wired in via FastMCP's built-in ``StaticTokenVerifier``
(``fastmcp.server.auth``); comparison happens inside FastMCP/starlette, not by
hand-rolled string comparison here. If ``--transport http`` is selected and no
token is configured, the server refuses to start rather than opening an
unauthenticated port. ``--host`` still defaults to ``127.0.0.1``.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

from fastmcp import FastMCP

from repo_release_tools import __version__
from repo_release_tools.config import find_repo_root
from repo_release_tools.ui import cli_error

from .apps import register_apps
from .prompts import register_prompts
from .resources import register_resources
from .tools import register_tools

AUTH_TOKEN_ENV_VAR = "RRT_MCP_AUTH_TOKEN"


def _find_repo_root() -> Path:
    """Return the nearest repo root based on supported rrt config files."""
    return find_repo_root(Path.cwd())


@asynccontextmanager
async def _lifespan(server: FastMCP[Any]) -> AsyncGenerator[dict[str, Any], None]:
    """Load repo root and resolved config once at server startup."""
    from repo_release_tools.config import load_or_autodetect_config

    root = _find_repo_root()
    config = None
    config_error: str | None = None
    try:
        config = load_or_autodetect_config(root)
    except FileNotFoundError:
        pass
    except (ValueError, RuntimeError) as exc:
        config_error = str(exc)
    yield {"root": root, "config": config, "config_error": config_error}


def _build_auth_provider(token: str) -> Any:
    """Build a FastMCP token verifier for the given bearer token.

    Uses FastMCP's built-in ``StaticTokenVerifier`` rather than hand-rolled
    comparison — token matching happens inside FastMCP/starlette.
    """
    from fastmcp.server.auth import StaticTokenVerifier

    return StaticTokenVerifier(tokens={token: {"client_id": "rrt-mcp-http"}})


def create_server(*, auth_token: str | None = None) -> FastMCP[Any]:
    """Create and configure the rrt FastMCP server.

    ``auth_token``, when provided, wires a bearer-token verifier into the
    server for the HTTP transport (see module docstring for SEC-002 context).
    """
    mcp: FastMCP[Any] = FastMCP(
        name="repo-release-tools",
        instructions=(
            "MCP server for repo-release-tools (rrt). "
            "Exposes version management, changelog, health/drift/tree/artifact lock inspection, "
            "branch and commit validation, config introspection, and eol/release/sync/folder/docs "
            "checks as MCP tools and resources. "
            "Mutating tools rrt_bump, rrt_branch_new, and rrt_init_run default to dry_run=True "
            "for safety."
        ),
        version=__version__,
        lifespan=_lifespan,
        auth=_build_auth_provider(auth_token) if auth_token else None,
    )

    register_tools(mcp)
    register_resources(mcp)
    register_prompts(mcp)
    register_apps(mcp)

    from fastmcp.apps.generative import GenerativeUI

    mcp.add_provider(GenerativeUI())

    return mcp


def main() -> None:
    """Entry point for the rrt-mcp CLI."""
    import argparse
    import sys

    try:
        import fastmcp  # noqa: F401
    except ImportError:
        sys.stderr.write("FastMCP is not installed. Run: pip install repo-release-tools[mcp]\n")
        sys.exit(1)

    parser = argparse.ArgumentParser(
        prog="rrt-mcp",
        description="Run the repo-release-tools MCP server.",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport protocol (default: stdio for Claude Desktop)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind host for HTTP transport (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for HTTP transport (default: 8000)",
    )
    parser.add_argument(
        "--auth-token",
        default=None,
        help=(
            "Bearer token required by HTTP transport clients "
            f"(default: read from {AUTH_TOKEN_ENV_VAR}). Ignored for stdio transport."
        ),
    )
    args = parser.parse_args()

    if args.transport == "http":
        token = args.auth_token or os.environ.get(AUTH_TOKEN_ENV_VAR)
        if not token:
            sys.stderr.write(
                cli_error(
                    "refusing to start unauthenticated HTTP transport",
                    hint=(f"set --auth-token or {AUTH_TOKEN_ENV_VAR}, or use --transport stdio"),
                )
                + "\n"
            )
            sys.exit(1)
        server = create_server(auth_token=token)
        server.run(transport="http", host=args.host, port=args.port)
    else:
        server = create_server()
        server.run(transport="stdio")


if __name__ == "__main__":  # pragma: no cover
    main()
