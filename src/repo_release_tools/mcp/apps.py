"""FastMCP app tools for the rrt MCP server — interactive PrefabApp dashboards, charts, and forms.

## Overview

This module registers the **interactive UI surface** of the rrt MCP server.  While the tool
modules in `mcp/tools/` return structured JSON, the app tools here return `PrefabApp`
objects — rich composable UI components rendered directly inside the AI assistant's chat
window (supported by Claude Desktop, VS Code Copilot chat, and other FastMCP 3.x hosts with
PrefabApp rendering).

All app tools are registered with `app=True` in the `@mcp.tool(...)` decorator, which tells
FastMCP to treat the return value as a UI widget rather than plain text.

## Available dashboards

### `rrt_health_dashboard`

The primary health overview screen.  Shows:
- **Metric summary** — total checks, passing, warnings, and errors
- **Ring chart** — percentage of passing checks (green ≥ 100%, yellow, or red)
- **Bar chart** — per-lock-file breakdown (health, tree, artifacts, drift)
- **Check cards** — one card per health check with badge and message
- **Detail table** — all entries across all locks, sortable and searchable

Data sources: `.rrt/health.lock.toml`, `.rrt/tree.lock.toml`,
`.rrt/artifacts.lock.toml`, `.rrt/drift.lock.toml`.

### `rrt_version_overview`

A version-target map showing every configured file, kind, and current version string.
Reads all version groups from the `[tool.rrt]` lifespan config.  Each target is displayed
in a card with the file path, kind (`pep621`, `package_json`, `go_version`, etc.), and
the current version string (or an error message when the file is missing).

### `rrt_doctor_dashboard`

Health check cards for the automation tooling: pre-commit, lefthook, husky, and GitHub
Actions workflows.  Each card shows a severity badge (ok / obsolete / warning / error) and the
diagnostic message.  An overall badge summarises the worst severity across all checks.

### `rrt_tree_dashboard`

Repository tree snapshot browser.  Displays:
- Lock metadata: tree hash (truncated), entry count, and updated_at timestamp
- A live `git ls-files` listing of tracked files (up to 200 lines)
- Falls back gracefully when git is unavailable or the snapshot lock is missing

### `rrt_locks_overview`

High-level summary of all four lock files in a single carousel.  Each slide shows:
- **Health** — all checks with status badges
- **Tree** — snapshot hash and entry count
- **Artifacts** — registered artifact files
- **Drift** — drift-tracked source files

Useful for a quick "what does rrt know about my repo?" overview.

### `rrt_init` and `rrt_init_run`

An interactive form for scaffolding rrt configuration.

- **`rrt_init`** — renders the `RrtInitForm` with target, dry_run, and force fields
- **`rrt_init_run`** — async tool that executes `rrt init` with the form values and
  returns the command output as text

`rrt_init_run` defaults to `dry_run=True` so it will only preview the init without
writing files unless the user explicitly disables dry-run.

## Helper functions

### `_severity_icon(severity)`

Maps `"ok"` → `"✓"`, `"obsolete"` → `"○"`, `"warning"` → `"⚠"`, `"error"` → `"✗"`, anything else → `"?"`.

### `_badge_variant(severity)`

Maps severity strings to PrefabUI badge variants:
`"ok"` → `"success"`, `"warning"` → `"warning"`, `"error"` → `"destructive"`,
other → `"secondary"`.

### `_overall_badge(severities)`

Given a list of severity strings, returns `(label, variant)` for the worst:
- All ok or empty → `("All Healthy", "success")`
- Any warning → `("Warnings", "warning")`
- Any error → `("Errors", "destructive")`

## `RrtInitForm`

Pydantic `BaseModel` used as the form schema for `rrt_init`.  Fields:
- `target` — config format: one of `"rrt-toml"`, `"pyproject"`, `"cargo"`, `"node"`, `"go"`
  (default `"rrt-toml"`)
- `dry_run` — preview without writing (default `True`)
- `force` — overwrite existing config (default `False`)

## Layout components used

`Column`, `Row`, `Grid`, `Card`, `CardContent`, `Heading`, `Badge`, `Metric`, `Ring`,
`BarChart`, `PieChart`, `DataTable`, `Separator`, `Text`, `Muted`, `Carousel`,
`ExpandableRow`, `Form` (all from `prefab_ui`).
"""

from __future__ import annotations

from typing import Any, Literal

from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from prefab_ui.actions.mcp import CallTool
from prefab_ui.app import PrefabApp
from prefab_ui.components import (
    Badge,
    Card,
    CardContent,
    Carousel,
    Column,
    DataTable,
    DataTableColumn,
    ExpandableRow,
    Form,
    Grid,
    Heading,
    Metric,
    Muted,
    Ring,
    Row,
    Separator,
    Text,
)
from prefab_ui.components.charts import BarChart, ChartSeries, PieChart
from pydantic import BaseModel, Field

from repo_release_tools import __version__ as _PKG_VERSION


def _severity_icon(severity: str) -> str:
    return {"ok": "✓", "obsolete": "○", "warning": "⚠", "error": "✗"}.get(severity, "?")


def _badge_variant(severity: str) -> str:
    return {
        "ok": "success",
        "obsolete": "secondary",
        "warning": "warning",
        "error": "destructive",
    }.get(severity, "secondary")


def _healthy_status_count(severities: list[str]) -> int:
    return sum(1 for severity in severities if severity in {"ok", "obsolete"})


def _overall_badge(severities: list[str]) -> tuple[str, str]:
    if "error" in severities:
        return "Errors", "destructive"
    if "warning" in severities:
        return "Warnings", "warning"
    return "All Healthy", "success"


# Mirrors the --target choices in commands/init.py's argparse spec (SEC-007:
# rrt_init_run validates LLM-supplied `target` against this set before it
# reaches subprocess argv, the same pattern git_tools.py uses for commit_type).
INIT_TARGETS: tuple[str, ...] = ("rrt-toml", "pyproject", "cargo", "node", "go")


class RrtInitForm(BaseModel):
    """Form model for rrt init configuration."""

    target: Literal["rrt-toml", "pyproject", "cargo", "node", "go"] = Field(
        default="rrt-toml", title="Config target"
    )
    dry_run: bool = Field(default=True, title="Dry run (preview only)")
    force: bool = Field(default=False, title="Force overwrite if exists")


def register_apps(mcp: FastMCP) -> None:
    """Register FastMCP app tools (interactive UI) on *mcp*."""

    @mcp.tool(
        app=True,
        title="RRT Health Dashboard",
        tags={"ui", "dashboard"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        meta={"domain": "rrt", "surface": "mcp"},
    )
    def rrt_health_dashboard(ctx: Context) -> PrefabApp:
        """Health overview: Metric summary, health Ring, per-lock status chart, check cards, and detail table."""
        from pathlib import Path

        from repo_release_tools.state import (
            artifacts_lock_path,
            health_lock_path,
            read_lock,
            rrt_dir,
            tree_lock_path,
        )

        root: Path = ctx.lifespan_context.get("root", Path.cwd())
        rows: list[dict[str, Any] | ExpandableRow] = []
        lock_counts: dict[str, dict[str, int]] = {}
        check_entries: list[dict[str, Any]] = []

        health = read_lock(health_lock_path(root))
        hc: dict[str, int] = {"ok": 0, "obsolete": 0, "warning": 0, "error": 0}
        for name, entry in health.get("checks", {}).items():
            sev = entry.get("status", "ok")
            hc[sev if sev in hc else "ok"] += 1
            msg = entry.get("message", "")
            rows.append(
                {
                    "lock": "health",
                    "name": name,
                    "status": f"{_severity_icon(sev)} {sev}",
                    "severity": sev,
                    "message": msg,
                    "updated_at": entry.get("updated_at", ""),
                }
            )
            check_entries.append({"name": name, "severity": sev, "message": msg})
        lock_counts["health"] = hc

        tree = read_lock(tree_lock_path(root))
        snap = tree.get("snapshot", {})
        tc: dict[str, int] = {"ok": 0, "warning": 0, "error": 0}
        if snap:
            tree_hash = snap.get("tree_hash", "")
            rows.append(
                {
                    "lock": "tree",
                    "name": "snapshot",
                    "status": f"{_severity_icon('ok')} ok",
                    "severity": "ok",
                    "message": f"{snap.get('entry_count', '?')} entries, hash {tree_hash[:16]}…",
                    "updated_at": snap.get("updated_at", ""),
                }
            )
            tc["ok"] += 1
        lock_counts["tree"] = tc

        artifacts = read_lock(artifacts_lock_path(root))
        ac: dict[str, int] = {"ok": 0, "warning": 0, "error": 0}
        for rel, entry in artifacts.get("files", {}).items():
            rows.append(
                {
                    "lock": "artifacts",
                    "name": rel,
                    "status": f"{_severity_icon('ok')} ok",
                    "severity": "ok",
                    "message": entry.get("description", ""),
                    "updated_at": entry.get("updated_at", ""),
                }
            )
            ac["ok"] += 1
        lock_counts["artifacts"] = ac

        drift = read_lock(rrt_dir(root) / "drift.lock.toml")
        dc: dict[str, int] = {"ok": 0, "warning": 0, "error": 0}
        for source, entry in drift.get("sources", {}).items():
            rows.append(
                {
                    "lock": "drift",
                    "name": source,
                    "status": f"{_severity_icon('ok')} ok",
                    "severity": "ok",
                    "message": entry.get("lang", ""),
                    "updated_at": entry.get("updated_at", ""),
                }
            )
            dc["ok"] += 1
        lock_counts["drift"] = dc

        all_sevs = [r["severity"] for r in rows if isinstance(r, dict)]
        badge_label, badge_variant = _overall_badge(all_sevs)
        ok_n = _healthy_status_count(all_sevs)
        warn_n = all_sevs.count("warning")
        err_n = all_sevs.count("error")
        total = len(rows)
        ok_pct = round(ok_n / max(total, 1) * 100)
        ring_variant = "success" if ok_pct == 100 else ("warning" if err_n == 0 else "destructive")
        chart_data = [{"lock": lk, **cnts} for lk, cnts in lock_counts.items()]
        table_rows: list[dict[str, Any] | ExpandableRow] = [
            {k: v for k, v in r.items() if k != "severity"} for r in rows if isinstance(r, dict)
        ]

        with Column(gap=4, css_class="p-6") as view:
            with Row(gap=2, align="center"):
                Heading("RRT Health Overview")
                Badge(badge_label, variant=badge_variant)

            with Grid(columns=4, gap=4):
                with Card(css_class="p-4"):
                    Metric(label="Total Checks", value=str(total))
                with Card(css_class="p-4"):
                    Metric(
                        label="Passing",
                        value=str(ok_n),
                        trend="up" if ok_n > 0 else None,
                        trendSentiment="positive" if ok_n > 0 else "neutral",
                    )
                with Card(css_class="p-4"):
                    Metric(label="Warnings", value=str(warn_n))
                with Card(css_class="p-4"):
                    Metric(label="Errors", value=str(err_n))

            with Grid(columns=2, gap=4):
                with Card():
                    with CardContent(css_class="flex items-center justify-center p-6"):
                        Ring(value=ok_pct, label=f"{ok_pct}%", variant=ring_variant, size="lg")
                with Card():
                    with CardContent():
                        BarChart(
                            data=chart_data,
                            series=[
                                ChartSeries(dataKey="ok", label="OK"),
                                ChartSeries(dataKey="obsolete", label="Obsolete"),
                                ChartSeries(dataKey="warning", label="Warning"),
                                ChartSeries(dataKey="error", label="Error"),
                            ],
                            xAxis="lock",
                            showLegend=True,
                            barRadius=4,
                            showGrid=True,
                            showTooltip=True,
                        )

            if check_entries:
                with Grid(columns=2, gap=3):
                    for ce in check_entries:
                        with Card():
                            with CardContent():
                                with Row(gap=2, align="center"):
                                    Text(ce["name"], css_class="font-medium")
                                    Badge(ce["severity"], variant=_badge_variant(ce["severity"]))
                                if ce["message"]:
                                    Muted(ce["message"])
            Separator()
            DataTable(
                columns=[
                    DataTableColumn(key="lock", header="Lock", sortable=True),
                    DataTableColumn(key="name", header="Name", sortable=True),
                    DataTableColumn(key="status", header="Status", sortable=True),
                    DataTableColumn(key="message", header="Message"),
                    DataTableColumn(key="updated_at", header="Updated At", sortable=True),
                ],
                rows=table_rows,
                search=True,
            )
        return PrefabApp(view=view)

    @mcp.tool(
        app=True,
        title="RRT Version Overview",
        tags={"ui", "dashboard", "versioning"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        meta={"domain": "rrt", "surface": "mcp"},
    )
    def rrt_version_overview(ctx: Context) -> PrefabApp:
        """Version target map: each configured file, kind, and current version."""
        from repo_release_tools.version.targets import read_version_string

        config = ctx.lifespan_context.get("config")
        rows: list[dict[str, Any] | ExpandableRow] = []

        if config is None:
            rows.append({"group": "—", "file": "—", "kind": "—", "version": "No rrt config found"})
        else:
            for group in config.version_groups:
                for target in group.version_targets:
                    try:
                        ver = read_version_string(target)
                    except (RuntimeError, OSError) as exc:
                        ver = f"error: {exc}"
                    rows.append(
                        {
                            "group": group.name,
                            "file": str(target.path),
                            "kind": target.kind or "custom",
                            "version": ver,
                        }
                    )

        with Column(gap=4, css_class="p-6") as view:
            with Row(gap=2, align="center"):
                Heading("Version Targets")
                Badge(f"{len(rows)} targets")
            DataTable(
                columns=[
                    DataTableColumn(key="group", header="Group", sortable=True),
                    DataTableColumn(key="file", header="File"),
                    DataTableColumn(key="kind", header="Kind", sortable=True),
                    DataTableColumn(key="version", header="Version", sortable=True),
                ],
                rows=rows,
                search=True,
            )
        return PrefabApp(view=view)

    @mcp.tool(
        app=True,
        title="RRT Doctor Dashboard",
        tags={"ui", "dashboard", "inspection"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        meta={"domain": "rrt", "surface": "mcp"},
    )
    def rrt_doctor_dashboard(ctx: Context) -> PrefabApp:
        """Doctor check results: pass-rate Ring, per-check Metrics, status cards, and detail table."""
        from pathlib import Path

        from repo_release_tools.state import health_lock_path, read_lock

        root: Path = ctx.lifespan_context.get("root", Path.cwd())
        health = read_lock(health_lock_path(root))
        check_entries: list[dict[str, Any]] = [
            {
                "check": name,
                "severity": entry.get("status", "ok"),
                "message": entry.get("message", ""),
                "updated_at": entry.get("updated_at", ""),
            }
            for name, entry in health.get("checks", {}).items()
        ]
        badge_label, badge_variant = _overall_badge([ce["severity"] for ce in check_entries])
        ok_n = _healthy_status_count([ce["severity"] for ce in check_entries])
        total = max(len(check_entries), 1)
        ok_pct = round(ok_n / total * 100)
        ring_variant = "success" if ok_pct == 100 else ("warning" if ok_pct > 0 else "destructive")
        table_rows: list[dict[str, Any] | ExpandableRow] = [
            {
                "check": ce["check"],
                "status": f"{_severity_icon(ce['severity'])} {ce['severity']}",
                "message": ce["message"],
                "updated_at": ce["updated_at"],
            }
            for ce in check_entries
        ]

        with Column(gap=4, css_class="p-6") as view:
            with Row(gap=2, align="center"):
                Heading("Doctor Dashboard")
                Badge(badge_label, variant=badge_variant)

            with Grid(columns=2, gap=4):
                with Card():
                    with CardContent(css_class="flex items-center justify-center p-6"):
                        Ring(value=ok_pct, label=f"{ok_pct}%", variant=ring_variant, size="lg")
                with Card():
                    with CardContent():
                        with Grid(columns=2, gap=3):
                            for ce in check_entries:
                                with Card(css_class="p-3"):
                                    Metric(label=ce["check"], value=ce["severity"])

            if check_entries:
                with Grid(columns=2, gap=3):
                    for ce in check_entries:
                        with Card():
                            with CardContent():
                                with Row(gap=2, align="center"):
                                    Text(ce["check"], css_class="font-medium")
                                    Badge(ce["severity"], variant=_badge_variant(ce["severity"]))
                                if ce["message"]:
                                    Muted(ce["message"])
            DataTable(
                columns=[
                    DataTableColumn(key="check", header="Check", sortable=True),
                    DataTableColumn(key="status", header="Status", sortable=True),
                    DataTableColumn(key="message", header="Message"),
                    DataTableColumn(key="updated_at", header="Updated At", sortable=True),
                ],
                rows=table_rows,
                search=True,
            )
        return PrefabApp(view=view)

    @mcp.tool(
        app=True,
        title="RRT Tree Dashboard",
        tags={"ui", "dashboard", "inspection"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        meta={"domain": "rrt", "surface": "mcp"},
    )
    def rrt_tree_dashboard(ctx: Context) -> PrefabApp:
        """Repository tree: snapshot Metric cards, per-directory bar chart, and clean file table."""
        import subprocess
        from collections import Counter
        from pathlib import Path

        from repo_release_tools.state import read_lock, tree_lock_path

        root: Path = ctx.lifespan_context.get("root", Path.cwd())
        tree = read_lock(tree_lock_path(root))
        snap = tree.get("snapshot", {})
        chart_data: list[dict[str, Any]] = []
        dir_rows: list[dict[str, Any] | ExpandableRow] = []
        total = 0

        try:
            result = subprocess.run(
                ["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True
            )
            counts: Counter[str] = Counter()
            for line in result.stdout.splitlines():
                top = line.split("/")[0] if "/" in line else "."
                counts[top] += 1
            total = sum(counts.values())
            for top, count in sorted(counts.items()):
                chart_data.append({"directory": top, "files": count})
                dir_rows.append({"directory": top, "files": count})
        except Exception:
            dir_rows.append({"directory": "(git ls-files failed)", "files": 0})

        with Column(gap=4, css_class="p-6") as view:
            with Row(gap=2, align="center"):
                Heading("Repository File Tree")
                Badge(f"{total} tracked files")

            if snap:
                tree_hash = str(snap.get("tree_hash", ""))
                entry_count = snap.get("entry_count", "?")
                updated_at = str(snap.get("updated_at", ""))
                with Grid(columns=3, gap=4):
                    with Card(css_class="p-4"):
                        Metric(label="Total Files", value=str(total))
                    with Card(css_class="p-4"):
                        Metric(label="Directories", value=str(len(chart_data)))
                    with Card(css_class="p-4"):
                        Metric(
                            label="Snapshot", value=str(entry_count), delta=f"hash {tree_hash[:8]}…"
                        )
                        if updated_at:
                            Muted(updated_at[:10])
            else:
                with Grid(columns=2, gap=4):
                    with Card(css_class="p-4"):
                        Metric(label="Total Files", value=str(total))
                    with Card(css_class="p-4"):
                        Metric(label="Directories", value=str(len(chart_data)))

            if chart_data:
                BarChart(
                    data=chart_data,
                    series=[ChartSeries(dataKey="files", label="Files")],
                    xAxis="directory",
                    barRadius=4,
                    showGrid=True,
                    showTooltip=True,
                )
            Separator()
            DataTable(
                columns=[
                    DataTableColumn(key="directory", header="Directory", sortable=True),
                    DataTableColumn(key="files", header="Files", sortable=True),
                ],
                rows=dir_rows,
                search=True,
            )
        return PrefabApp(view=view)

    @mcp.tool(
        app=True,
        title="RRT Init",
        tags={"ui", "init", "config"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        meta={"domain": "rrt", "surface": "mcp"},
    )
    def rrt_init(ctx: Context) -> PrefabApp:
        """Form to initialize rrt configuration — pick target format, preview, then apply."""
        with Column(gap=4, css_class="p-6") as view:
            Heading("Initialize rrt Configuration")
            Form.from_model(RrtInitForm, on_submit=CallTool("rrt_init_run"))
        return PrefabApp(view=view)

    @mcp.tool(
        title="RRT Init Run",
        tags={"init", "config"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(destructiveHint=True),
        meta={"domain": "rrt", "surface": "mcp"},
    )
    async def rrt_init_run(
        ctx: Context,
        target: str = "rrt-toml",
        dry_run: bool = True,
        force: bool = False,
    ) -> str:
        """Run rrt init with the given target format. Defaults to dry_run=True for safety."""
        import subprocess
        import sys
        from pathlib import Path

        if target not in INIT_TARGETS:
            allowed = ", ".join(INIT_TARGETS)
            return f"[error]: Invalid target {target!r}. Choose one of: {allowed}"

        root: Path = ctx.lifespan_context.get("root", Path.cwd())
        cmd = [sys.executable, "-m", "repo_release_tools.cli", "init", f"--target={target}"]
        if dry_run:
            cmd.append("--dry-run")
        if force:
            cmd.append("--force")
        try:
            result = subprocess.run(
                cmd, cwd=str(root), capture_output=True, text=True, timeout=20.0
            )
        except subprocess.TimeoutExpired:
            return "[error]: rrt init timed out after 20 seconds"
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]: {result.stderr}"
        if result.returncode != 0:
            details = (result.stderr or result.stdout).strip()
            if details:
                return f"[error]: rrt init exited with code {result.returncode}: {details}"
            return f"[error]: rrt init exited with code {result.returncode}"
        return output.strip() or "Init complete."

    @mcp.tool(
        app=True,
        title="RRT Locks Overview",
        tags={"ui", "dashboard", "locks"},
        version=_PKG_VERSION,
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        meta={"domain": "rrt", "surface": "mcp"},
    )
    def rrt_locks_overview(ctx: Context) -> PrefabApp:
        """All lock files at a glance: status donut chart, Carousel of lock summaries, and full detail table."""
        from pathlib import Path

        from repo_release_tools.state import (
            artifacts_lock_path,
            health_lock_path,
            read_lock,
            rrt_dir,
            tree_lock_path,
        )

        root: Path = ctx.lifespan_context.get("root", Path.cwd())
        rows: list[dict[str, Any] | ExpandableRow] = []
        lock_summaries: list[dict[str, Any]] = []

        health = read_lock(health_lock_path(root))
        h_checks = health.get("checks", {})
        h_ok = sum(1 for e in h_checks.values() if e.get("status") in {"ok", "obsolete"})
        h_obsolete = sum(1 for e in h_checks.values() if e.get("status") == "obsolete")
        h_warn = sum(1 for e in h_checks.values() if e.get("status") == "warning")
        h_err = sum(1 for e in h_checks.values() if e.get("status") == "error")
        for name, entry in h_checks.items():
            sev = entry.get("status", "ok")
            rows.append(
                {
                    "lock": "health",
                    "name": name,
                    "status": f"{_severity_icon(sev)} {sev}",
                    "severity": sev,
                    "message": entry.get("message", ""),
                    "updated_at": entry.get("updated_at", ""),
                }
            )
        overall_sev = "error" if h_err else ("warning" if h_warn else "ok")
        lock_summaries.append(
            {
                "lock": "Health",
                "desc": (
                    f"{len(h_checks)} checks: {h_ok} healthy, "
                    f"{h_obsolete} obsolete, {h_warn} warn, {h_err} err"
                ),
                "severity": overall_sev,
                "value": str(h_ok),
                "delta": f"{h_warn + h_err} issues" if h_warn + h_err else "all clear",
            }
        )

        tree = read_lock(tree_lock_path(root))
        snap = tree.get("snapshot", {})
        if snap:
            tree_hash = str(snap.get("tree_hash", ""))
            entry_count = snap.get("entry_count", "?")
            rows.append(
                {
                    "lock": "tree",
                    "name": "snapshot",
                    "status": f"{_severity_icon('ok')} ok",
                    "severity": "ok",
                    "message": f"{entry_count} entries, hash {tree_hash[:16]}…",
                    "updated_at": snap.get("updated_at", ""),
                }
            )
            lock_summaries.append(
                {
                    "lock": "Tree",
                    "desc": f"{entry_count} entries tracked",
                    "severity": "ok",
                    "value": str(entry_count),
                    "delta": f"hash {tree_hash[:8]}…",
                }
            )
        else:
            lock_summaries.append(
                {
                    "lock": "Tree",
                    "desc": "No snapshot",
                    "severity": "warning",
                    "value": "—",
                    "delta": "no snapshot",
                }
            )

        artifacts = read_lock(artifacts_lock_path(root))
        art_files = artifacts.get("files", {})
        for rel, entry in art_files.items():
            rows.append(
                {
                    "lock": "artifacts",
                    "name": rel,
                    "status": f"{_severity_icon('ok')} ok",
                    "severity": "ok",
                    "message": entry.get("description", ""),
                    "updated_at": entry.get("updated_at", ""),
                }
            )
        lock_summaries.append(
            {
                "lock": "Artifacts",
                "desc": f"{len(art_files)} tracked files",
                "severity": "ok",
                "value": str(len(art_files)),
                "delta": "files tracked",
            }
        )

        drift = read_lock(rrt_dir(root) / "drift.lock.toml")
        drift_sources = drift.get("sources", {})
        for source, entry in drift_sources.items():
            rows.append(
                {
                    "lock": "drift",
                    "name": source,
                    "status": f"{_severity_icon('ok')} ok",
                    "severity": "ok",
                    "message": entry.get("lang", ""),
                    "updated_at": entry.get("updated_at", ""),
                }
            )
        lock_summaries.append(
            {
                "lock": "Drift",
                "desc": f"{len(drift_sources)} tracked sources",
                "severity": "ok",
                "value": str(len(drift_sources)),
                "delta": "sources pinned",
            }
        )

        all_sevs = [r["severity"] for r in rows if isinstance(r, dict)]
        badge_label, badge_variant = _overall_badge(all_sevs)
        ok_n = _healthy_status_count(all_sevs)
        obsolete_n = all_sevs.count("obsolete")
        warn_n = all_sevs.count("warning")
        err_n = all_sevs.count("error")
        pie_data = [
            {"status": "ok", "count": ok_n},
            {"status": "obsolete", "count": obsolete_n},
            {"status": "warning", "count": warn_n},
            {"status": "error", "count": err_n},
        ]
        table_rows: list[dict[str, Any] | ExpandableRow] = [
            {k: v for k, v in r.items() if k != "severity"} for r in rows if isinstance(r, dict)
        ]

        with Column(gap=4, css_class="p-6") as view:
            with Row(gap=2, align="center"):
                Heading("Lock File Overview")
                Badge(badge_label, variant=badge_variant)

            PieChart(
                data=pie_data, dataKey="count", nameKey="status", showLegend=True, innerRadius=40
            )
            Separator()

            with Carousel(autoAdvance=3000, showControls=True, showDots=True):
                for ls in lock_summaries:
                    with Card(css_class="p-4"):
                        with Row(gap=2, align="center"):
                            Text(ls["lock"], css_class="font-semibold text-lg")
                            Badge(
                                _severity_icon(ls["severity"]),
                                variant=_badge_variant(ls["severity"]),
                            )
                        Metric(label=ls["desc"], value=ls["value"], delta=ls["delta"])

            Separator()
            DataTable(
                columns=[
                    DataTableColumn(key="lock", header="Lock", sortable=True),
                    DataTableColumn(key="name", header="Name", sortable=True),
                    DataTableColumn(key="status", header="Status", sortable=True),
                    DataTableColumn(key="message", header="Message"),
                    DataTableColumn(key="updated_at", header="Updated At", sortable=True),
                ],
                rows=table_rows,
                search=True,
            )
        return PrefabApp(view=view)
