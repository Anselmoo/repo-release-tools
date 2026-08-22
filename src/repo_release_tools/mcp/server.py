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
            "Use this server for any task in this repository that touches release policy: "
            "version numbers, the changelog, or branch or commit naming, or [tool.rrt] "
            "config. If your client cannot read files directly, that also includes the "
            "current .rrt/*.lock.toml state — a file-capable agent gets nothing from the "
            "lock-reader tools that `Read .rrt/<name>.lock.toml` does not already give it. "
            "If you were about to run `rrt ...` in a shell, check here first.\n"
            "\n"
            "Prefer these tools over shelling out to the CLI for three concrete reasons: "
            "(1) most tools return typed JSON (Pydantic models) instead of ANSI-formatted "
            "human output you would have to parse — the four lock readers and rrt_config "
            "return raw dicts, and rrt_init_run returns captured text, not a model; "
            "(2) arguments are passed directly, so a commit subject or branch name never "
            "goes through shell quoting — no escaping backticks, quotes, `!`, or newlines; "
            "(3) every mutating tool defaults to dry_run=True, so a preview is what you get "
            "unless you explicitly ask for a write. On the CLI the safety is a flag you must "
            "remember; here it is the default.\n"
            "\n"
            "Reach for it when you need to: read or bump a version (rrt_version, rrt_bump); "
            "read the changelog (rrt_changelog); check a branch name or a Conventional Commit "
            "subject BEFORE you use it (rrt_validate_branch, rrt_validate_commit); inspect "
            "resolved config (rrt_config); or run a policy check (rrt_doctor, "
            "rrt_release_check, rrt_folder_check, rrt_docs_check, rrt_eol, rrt_sync_check).\n"
            "\n"
            "Do NOT use it for: ordinary git (commit, push, rebase, status, log); running "
            "tests or linters; or rrt subcommands that have no tool here — `rrt docs map`, "
            "`rrt docs generate`, `rrt docs publish`, `rrt docs inject`, `rrt tree --check`, "
            "`rrt toc`, `rrt changelog lint`, `rrt changelog compare`, `rrt drift generate`, "
            "`rrt drift check`, `rrt artifacts --check`, any other `--snapshot` write, and "
            "every `rrt-hooks` subcommand still require the CLI. Shell out for those; that "
            "is the correct surface, not a fallback.\n"
            "\n"
            "Safety: rrt_bump, rrt_branch_new, and rrt_publish_snapshot mutate the "
            "repository. Call each with its default dry_run=True first, show the user the "
            "preview, and pass dry_run=False only after the user confirms. "
            "rrt_publish_snapshot force-pushes and additionally requires confirm=True. "
            "rrt_init_run also mutates but is the submit target of the rrt_init form, not a "
            "tool to call directly — if you are working from a shell, run `rrt init` "
            "instead."
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
