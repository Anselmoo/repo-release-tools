"""Architecture skeleton check tools for the rrt MCP server."""

from __future__ import annotations

from pathlib import Path

from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from repo_release_tools import __version__ as _PKG_VERSION
from repo_release_tools.mcp.models import ArchCheckResponse, ArchFindingEntry, ArchTemplateEntry


def register(mcp: FastMCP) -> None:
    """Register architecture-check tools on *mcp*."""

    @mcp.tool(
        title="Does the code still match its declared architecture?",
        tags={"architecture", "inspection"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        meta={"domain": "rrt", "surface": "mcp", "audience": "agent"},
    )
    def rrt_arch_check(
        ctx: Context,
        root: str | None = None,
        strict: bool = False,
        check_templates: bool = False,
    ) -> ArchCheckResponse:
        """Check the tree against [tool.rrt.architecture] and its findings baseline.

        Use before adding a module, a unit or a cross-unit import, and before a PR:
        the `rrt-arch-check` hook runs the same check with strict=True. Each finding
        is `new` (not in .rrt/architecture.baseline.toml), `baselined`, or `stale`
        (recorded but resolved). `exit_code` matches `rrt arch check`. Pass
        check_templates=True to also self-test every .rrt/templates/ kind. Read-only:
        never writes the baseline or renders templates; `rrt arch baseline` and
        `rrt arch new` stay CLI-only.
        """
        from repo_release_tools.architecture.core import root_module_name
        from repo_release_tools.architecture.templates import check_templates as run_self_test
        from repo_release_tools.commands.arch_cmd import ArchCheckError, load_arch_findings
        from repo_release_tools.state import arch_baseline_diff, arch_baseline_path

        base: Path = ctx.lifespan_context.get("root", Path.cwd())
        repo_root = (base / root).resolve() if root else Path(base).resolve()
        try:
            arch, findings = load_arch_findings(repo_root)
        except ArchCheckError as exc:
            return ArchCheckResponse(ok=False, exit_code=1, strict=strict, error=str(exc))

        baseline_file = arch_baseline_path(repo_root)
        new, stale = arch_baseline_diff(baseline_file, [f.id for f in findings])
        new_ids = set(new)
        entries = [
            ArchFindingEntry(
                kind=f.kind,
                id=f.id,
                path=f.subject,
                message=f.message,
                status="new" if f.id in new_ids else "baselined",
            )
            for f in findings
        ]
        for entry in stale:
            kind, _, path = entry.partition(":")
            entries.append(
                ArchFindingEntry(
                    kind=kind,
                    id=entry,
                    path=path,
                    message="Resolved; remove it with `rrt arch baseline`.",
                    status="stale",
                )
            )
        exit_code = 1 if strict and (new or stale) else 0

        templates: list[ArchTemplateEntry] | None = None
        if check_templates:
            results = run_self_test(
                arch, repo_root, root_module_name(repo_root / arch.root, repo_root)
            )
            templates = [
                ArchTemplateEntry(kind=name, ok=not problems, problems=problems)
                for name, problems in sorted(results.items())
            ]
            if any(not t.ok for t in templates):
                exit_code = 1

        return ArchCheckResponse(
            ok=exit_code == 0,
            exit_code=exit_code,
            strict=strict,
            root=arch.root,
            baseline=(
                baseline_file.relative_to(repo_root).as_posix() if baseline_file.exists() else None
            ),
            new_count=len(new),
            baselined_count=len(findings) - len(new),
            stale_count=len(stale),
            findings=entries,
            templates=templates,
        )
