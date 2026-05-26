"""Resource and resource-template registration for the rrt MCP server."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastmcp import FastMCP


def _path_to_str(obj: Any) -> Any:
    """Recursively convert Path objects to strings for JSON serialisation."""
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _path_to_str(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_path_to_str(i) for i in obj]
    return obj


def register_resources(mcp: FastMCP) -> None:
    """Register resources and resource templates on *mcp*."""
    from repo_release_tools.mcp.server import _find_repo_root
    from repo_release_tools.state import (
        artifacts_lock_path,
        health_lock_path,
        read_lock,
        rrt_dir,
        tree_lock_path,
    )

    _LOCK_RESOLVER = {
        "drift": lambda root: rrt_dir(root) / "drift.lock.toml",
        "health": health_lock_path,
        "tree": tree_lock_path,
        "artifacts": artifacts_lock_path,
    }

    @mcp.resource("rrt://version", title="RRT Version", tags={"versioning"})
    def resource_version() -> str:
        """Current installed version of repo-release-tools."""
        from repo_release_tools import __version__

        return __version__

    @mcp.resource("rrt://config", mime_type="application/json", title="RRT Config", tags={"config"})
    def resource_config() -> str:
        """Resolved rrt configuration as JSON."""
        from repo_release_tools.config import load_or_autodetect_config

        root = _find_repo_root()
        try:
            config = load_or_autodetect_config(root)
            return json.dumps(_path_to_str(asdict(config)), indent=2)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    @mcp.resource(
        "rrt://schema/config",
        mime_type="application/json",
        title="RRT Config Schema",
        tags={"config", "schema"},
    )
    def resource_config_schema() -> str:
        """JSON Schema for [tool.rrt] configuration — discover valid keys and value types."""
        from repo_release_tools.commands.config_cmd import _load_schema

        return json.dumps(_load_schema(), indent=2)

    @mcp.resource("rrt://changelog", title="RRT Changelog", tags={"changelog"})
    def resource_changelog() -> str:
        """Full content of the repository CHANGELOG.md."""
        changelog = _find_repo_root() / "CHANGELOG.md"
        if not changelog.exists():
            return "No CHANGELOG.md found."
        return changelog.read_text(encoding="utf-8")

    @mcp.resource(
        "rrt://locks/{name}", mime_type="application/json", title="RRT Lock File", tags={"locks"}
    )
    def resource_lock(name: str) -> str:
        """Read a named rrt lock file. name: drift | health | tree | artifacts."""
        valid = ", ".join(_LOCK_RESOLVER)
        resolver = _LOCK_RESOLVER.get(name)
        if resolver is None:
            return json.dumps({"error": f"Unknown lock '{name}'. Valid: {valid}"})
        root = _find_repo_root()
        return json.dumps(read_lock(resolver(root)), indent=2)
