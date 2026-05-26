"""Main FastMCP server for rrt — exposes rrt capabilities as MCP tools, resources, and prompts."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

from fastmcp import FastMCP

from repo_release_tools import __version__

from .apps import register_apps
from .prompts import register_prompts
from .resources import register_resources
from .tools import register_tools


def _find_repo_root() -> Path:
    """Walk up from cwd to find the repo root (first dir containing .rrt/ or pyproject.toml)."""
    cwd = Path.cwd()
    return next(
        (
            p
            for p in [cwd, *cwd.parents]
            if (p / ".rrt").is_dir() or (p / "pyproject.toml").exists()
        ),
        cwd,
    )


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


def create_server() -> FastMCP[Any]:
    """Create and configure the rrt FastMCP server."""
    mcp: FastMCP[Any] = FastMCP(
        name="repo-release-tools",
        instructions=(
            "MCP server for repo-release-tools (rrt). "
            "Exposes version management, changelog, health/drift/tree/artifact lock inspection, "
            "branch and commit validation, and config introspection as MCP tools and resources. "
            "Mutating tools rrt_bump, rrt_branch_new, and rrt_init_run default to dry_run=True "
            "for safety."
        ),
        version=__version__,
        lifespan=_lifespan,
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
    args = parser.parse_args()

    server = create_server()
    if args.transport == "http":
        server.run(transport="http", host=args.host, port=args.port)
    else:
        server.run(transport="stdio")


if __name__ == "__main__":  # pragma: no cover
    main()
