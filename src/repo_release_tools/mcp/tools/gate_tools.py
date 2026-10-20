"""Gate-list runner tools for the rrt MCP server."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from repo_release_tools import __version__ as _PKG_VERSION
from repo_release_tools.mcp.models import GateLineModel, GateRunResult


def register(mcp: FastMCP) -> None:
    """Register gate-runner tools on *mcp*."""

    @mcp.tool(
        title="Run the declared check lines against their expected exits",
        tags={"ci", "checks"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(destructiveHint=True, openWorldHint=True),
        timeout=1800.0,
        meta={"domain": "rrt", "surface": "mcp", "audience": "agent"},
    )
    async def rrt_gate_run(
        ctx: Context, names: list[str] | None = None, dry_run: bool = True
    ) -> GateRunResult:
        """Run [[tool.rrt.gates]] lines; every line runs and is judged against `expect`.

        Each line returns `exit`, `expected_exit` and `ok`, so a deliberately-red check
        that fails as designed reads as ok, and an unexpected failure does not. Use instead
        of chaining checks with `&&`, which stops at the first expected red line.
        dry_run=True by default, because the lines are repository-declared commands.
        """
        from repo_release_tools.commands.gate_cmd import run_gates, select_gates
        from repo_release_tools.config import load_gates

        root: Path = ctx.lifespan_context.get("root", Path.cwd())
        try:
            specs = select_gates(load_gates(root), list(names or []))
        except ValueError as exc:
            return GateRunResult(ok=False, dry_run=dry_run, error=str(exc))
        if not specs:
            return GateRunResult(
                ok=False, dry_run=dry_run, error="No [[tool.rrt.gates]] lines are configured."
            )
        if not dry_run:
            await ctx.warning(f"Running {len(specs)} repository-declared gate command(s)")
        results = await asyncio.to_thread(run_gates, root, specs, dry_run=dry_run)
        lines = [
            GateLineModel(
                name=r.name,
                command=r.command,
                exit=r.exit,
                expected_exit=r.expected_exit,
                ok=r.ok,
                error=r.error,
                output_tail=r.output_tail,
            )
            for r in results
        ]
        return GateRunResult(
            ok=not dry_run and all(line.ok for line in lines), dry_run=dry_run, lines=lines
        )
