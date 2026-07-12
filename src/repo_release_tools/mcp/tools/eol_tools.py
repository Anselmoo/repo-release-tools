"""End-of-life tracking tools for the rrt MCP server."""

from __future__ import annotations

from pathlib import Path

from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from repo_release_tools import __version__ as _PKG_VERSION
from repo_release_tools.mcp.models import EolCheckEntry, EolResponse


def register(mcp: FastMCP) -> None:
    """Register EOL tracking tools on *mcp*."""

    @mcp.tool(
        title="RRT EOL Check",
        tags={"eol", "inspection"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        meta={"domain": "rrt", "surface": "mcp"},
    )
    def rrt_eol(
        ctx: Context,
        language: str | None = None,
        fetch_live: bool = False,
    ) -> EolResponse:
        """Check host runtime and project minimum versions against EOL policy.

        Read-only — never writes to .rrt/health.lock.toml. Set fetch_live=True
        to refresh EOL data from endoflife.date instead of the bundled snapshot.
        """
        import contextlib
        import io

        from repo_release_tools.commands.eol_check import run_eol_checks
        from repo_release_tools.ui import VerbosePrinter

        root: Path = ctx.lifespan_context.get("root", Path.cwd())
        config = ctx.lifespan_context.get("config")
        eol_cfg = getattr(config, "eol", None) if config is not None else None

        if eol_cfg is not None:
            warn_days = eol_cfg.warn_days
            error_days = eol_cfg.error_days
            allow_eol = eol_cfg.allow_eol
            overrides = eol_cfg.overrides
            languages: tuple[str, ...] = (language,) if language else eol_cfg.languages
        else:
            warn_days = 180
            error_days = 0
            allow_eol = False
            overrides = ()
            languages = (language,) if language else ("python",)

        # run_eol_checks writes unconditional print() lines via VerbosePrinter,
        # which would corrupt the MCP stdio transport's JSON-RPC stream.
        with contextlib.redirect_stdout(io.StringIO()):
            all_ok, check_entries = run_eol_checks(
                languages=languages,
                root=root,
                warn_days=warn_days,
                error_days=error_days,
                fetch_live=fetch_live,
                allow_eol=allow_eol,
                overrides=overrides,
                p=VerbosePrinter(verbose=0),
            )

        return EolResponse(
            all_ok=all_ok,
            checks=[EolCheckEntry(**entry) for entry in check_entries],
        )
