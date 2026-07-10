#!/usr/bin/env python3
"""One-off topology extractor for repo-release-tools `src/repo_release_tools`.

Re-runnable, auditable. Produces analysis/the/topology.json (schema consumed by
the code-modernization TOPOLOGY.html viewer) and prints a human summary.

Method:
- Call graph: AST-parsed `import` / `from ... import` edges between in-package
  modules (absolute and relative imports resolved). Python has no external
  dispatcher config here; the CLI's "router" is commands/__init__.py's explicit
  import list, so import edges ARE the dispatch edges.
- Entry points come from deployment config: pyproject.toml [project.scripts]
  and action.yml (composite Action shells out to rrt-hooks).
- Data stores: file-based state (.rrt/*.toml locks, [tool.rrt] config sources,
  CHANGELOG.md, version-target files), the git repository (subprocess), and
  four HTTPS APIs. Code<->store joins derived from explicit tables + source
  pattern scan (both shown below, greppable).
- Dead ends: modules with zero inbound import edges, minus entry points.
  Suppression: modules registered via commands/__init__.py are reachable by
  construction; compat shims are flagged as genuinely dead-in-tree.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PKG = ROOT / "src" / "repo_release_tools"
PKG_NAME = "repo_release_tools"

# ---------------------------------------------------------------- domains
# Domain assignment mirrors analysis/the/ASSESSMENT.md (11 domains).
# First matching rule wins; order matters.
DOMAIN_RULES: list[tuple[str, str, str]] = [
    (r"^ui/", "dom:ui", "UI layer"),
    (r"^state\.py$", "dom:state", "State & .rrt locks"),
    (r"^config/", "dom:config", "Config"),
    (r"^commands/(config_cmd|init|project_cmd)\.py$", "dom:config", "Config"),
    (r"^(version/|changelog\.py$|preflight\.py$|sync/)", "dom:release", "Version & release"),
    (
        r"^commands/(bump|tag|ci_version|release_cmd|release_notes|release_repair|workspace"
        r"|sync_cmd|changelog_cmd|changelog_compare|changelog_lint)\.py$",
        "dom:release",
        "Version & release",
    ),
    (r"^workflow/git\.py$", "dom:git", "Git workflow"),
    (
        r"^commands/(branch|git_cmd|git_commit|git_inspect|git_sync|_git_shared)\.py$",
        "dom:git",
        "Git workflow",
    ),
    (r"^(workflow/hooks\.py|workflow/__init__\.py|hooks\.py)$", "dom:hooks", "Hooks & CI gates"),
    (r"^integrations/action\.py$", "dom:hooks", "Hooks & CI gates"),
    (r"^commands/hooks_cmd\.py$", "dom:hooks", "Hooks & CI gates"),
    (
        r"^commands/(doctor|drift_cmd|eol_check|folder|artifacts_cmd|tree|_tree_fix)\.py$",
        "dom:health",
        "Repo health & drift",
    ),
    (r"^(eol/|folders/)", "dom:health", "Repo health & drift"),
    (r"^(docs/|tools/)", "dom:docs", "Docs engine"),
    (r"^commands/(docs_cmd|docs_map|docs_map_lock|docs_suggest|toc)\.py$", "dom:docs", "Docs engine"),
    (
        r"^commands/(skill|agents_cmd|install_cmd|env_cmd|mcp_cmd)\.py$",
        "dom:setup",
        "Setup & integrations",
    ),
    (r"^integrations/", "dom:setup", "Setup & integrations"),
    (r"^mcp/", "dom:mcp", "MCP server (extra)"),
    # everything left (cli.py, __main__.py, commands/__init__.py, assets, _data,
    # folders helpers, misc commands) is the CLI shell
    (r"", "dom:cli", "CLI shell & assets"),
]

# ---------------------------------------------------------------- data stores
DATASTORES: list[tuple[str, str]] = [
    ("ds:rrt-config", "[tool.rrt] config (pyproject/.rrt.toml/Cargo.toml/package.json)"),
    ("ds:rrt-locks", ".rrt/ lock files (docs/health/tree/artifacts/drift/docs_map)"),
    ("ds:changelog", "CHANGELOG.md"),
    ("ds:version-targets", "Version-target files (pyproject, package.json, pins...)"),
    ("ds:git-repo", "Git repository (subprocess)"),
    ("ds:npm-registry", "registry.npmjs.org API"),
    ("ds:crates-io", "crates.io API"),
    ("ds:pypi", "pypi.org API"),
    ("ds:endoflife", "endoflife.date API"),
]

# Pattern-derived data edges: (source-regex on file text, datastore id, kind).
# "write" is claimed only where the module owns the mutation path.
DATA_PATTERNS: list[tuple[str, str, str]] = [
    (r"registry\.npmjs\.org", "ds:npm-registry", "read"),
    (r"crates\.io", "ds:crates-io", "read"),
    (r"pypi\.org", "ds:pypi", "read"),
    (r"endoflife\.date", "ds:endoflife", "read"),
    (r"\.rrt/|\.lock\.toml", "ds:rrt-locks", "read"),
    (r'\[\s*"git"', "ds:git-repo", "read"),
]

# Explicit data edges (verified by reading the modules; see ASSESSMENT.md).
EXPLICIT_DATA_EDGES: list[tuple[str, str, str]] = [
    ("state", "ds:rrt-locks", "write"),
    ("commands.drift_cmd", "ds:rrt-locks", "write"),
    ("commands.docs_map_lock", "ds:rrt-locks", "write"),
    ("commands.artifacts_cmd", "ds:rrt-locks", "write"),
    ("commands.tree", "ds:rrt-locks", "write"),
    ("config.core", "ds:rrt-config", "read"),
    ("commands.init", "ds:rrt-config", "write"),
    ("changelog", "ds:changelog", "read"),
    ("workflow.hooks", "ds:changelog", "write"),
    ("commands.bump", "ds:changelog", "write"),
    ("version.targets", "ds:version-targets", "write"),
    ("workflow.git", "ds:git-repo", "write"),
    ("workflow.hooks", "ds:git-repo", "write"),
]


def module_id(path: Path) -> str:
    rel = path.relative_to(PKG).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else PKG_NAME


def domain_of(path: Path) -> tuple[str, str]:
    rel = path.relative_to(PKG).as_posix()
    for pattern, dom_id, dom_name in DOMAIN_RULES:
        if re.search(pattern, rel):
            return dom_id, dom_name
    raise AssertionError(rel)


def resolve_import(node: ast.AST, current: Path) -> list[str]:
    """Resolve an import statement to in-package dotted module ids."""
    found: list[str] = []
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name == PKG_NAME or alias.name.startswith(PKG_NAME + "."):
                found.append(alias.name[len(PKG_NAME) + 1 :] or PKG_NAME)
    elif isinstance(node, ast.ImportFrom):
        if node.level:  # relative
            base_parts = list(current.relative_to(PKG).parent.parts)
            up = node.level - 1
            base_parts = base_parts[: len(base_parts) - up] if up else base_parts
            prefix = ".".join(base_parts)
            mod = f"{prefix}.{node.module}" if node.module and prefix else (node.module or prefix)
            for alias in node.names:
                found.append(f"{mod}.{alias.name}" if mod else alias.name)
        elif node.module and (
            node.module == PKG_NAME or node.module.startswith(PKG_NAME + ".")
        ):
            mod = node.module[len(PKG_NAME) + 1 :]
            for alias in node.names:
                found.append(f"{mod}.{alias.name}" if mod else alias.name)
    return found


def main() -> None:
    files = sorted(
        p for p in PKG.rglob("*.py") if "__pycache__" not in p.parts
    )
    ids = {module_id(p): p for p in files}

    # --- nodes grouped by domain
    domains: dict[str, dict] = {}
    for p in files:
        dom_id, dom_name = domain_of(p)
        dom = domains.setdefault(
            dom_id, {"id": dom_id, "name": dom_name, "kind": "domain", "children": []}
        )
        dom["children"].append(
            {
                "id": module_id(p),
                "name": module_id(p),
                "kind": "module",
                "language": "python",
                "loc": sum(1 for _ in p.open(encoding="utf-8")),
                "file": p.relative_to(ROOT).as_posix(),
            }
        )

    # action.yml is a deployment artifact that dispatches into rrt-hooks
    domains["dom:hooks"]["children"].append(
        {"id": "action.yml", "name": "action.yml (GitHub Action)", "kind": "job",
         "language": "yaml", "loc": sum(1 for _ in (ROOT / "action.yml").open()),
         "file": "action.yml"}
    )
    domains["dom:data"] = {
        "id": "dom:data", "name": "Data stores", "kind": "domain",
        "children": [{"id": i, "name": n, "kind": "datastore"} for i, n in DATASTORES],
    }

    # --- call edges from AST imports
    edges: set[tuple[str, str, str]] = set()
    for p in files:
        src_id = module_id(p)
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            for target in resolve_import(node, p):
                # normalise "pkg.mod.symbol" -> deepest existing module id
                cand = target
                while cand and cand not in ids:
                    cand = ".".join(cand.split(".")[:-1])
                if cand and cand != src_id:
                    edges.add((src_id, cand, "call"))

    edges.add(("action.yml", "workflow.hooks", "dispatch"))
    # cli dispatches every registered subcommand (explicit imports already
    # captured via commands/__init__.py; mark the shell edge as dispatch)
    edges.add(("cli", "commands", "dispatch"))

    # --- data edges
    for p in files:
        text = p.read_text(encoding="utf-8")
        src_id = module_id(p)
        for pattern, ds, kind in DATA_PATTERNS:
            if re.search(pattern, text):
                edges.add((src_id, ds, kind))
    for src, ds, kind in EXPLICIT_DATA_EDGES:
        if src in ids:
            # explicit write supersedes pattern-derived read
            edges.discard((src, ds, "read"))
            edges.add((src, ds, kind))
    edges.add(("action.yml", "ds:git-repo", "read"))

    # --- entry points (from deployment config: pyproject [project.scripts],
    # action.yml, and `python -m` __main__ modules)
    entry_points = [
        "cli", "workflow.hooks", "mcp.server", "action.yml",
        "__main__", "assets.badges.__main__",
    ]

    # --- dead ends: no inbound call/dispatch edge, not an entry point.
    # Suppression: package __init__ modules are public-API re-export surfaces —
    # importable from outside the tree, so "no in-tree inbound edge" does not
    # mean dead. They are excluded here and noted in observations instead.
    inbound = {t for _, t, k in edges if k in ("call", "dispatch")}
    dead = sorted(
        m
        for m, p in ids.items()
        if m not in inbound
        and m not in entry_points
        and p.name != "__init__.py"
    )

    topo = {
        "system": "repo-release-tools (rrt)",
        "root": {
            "id": "sys",
            "name": "repo-release-tools",
            "kind": "system",
            "children": [domains[k] for k in sorted(domains)],
        },
        "edges": [
            {"source": s, "target": t, "kind": k} for s, t, k in sorted(edges)
        ],
        "entryPoints": entry_points,
        "deadEnds": dead,
        "observations": [
            "workflow/hooks.py is the widest fan-in consumer: it imports 15 commands/* "
            "modules directly and re-declares their argparse defaults by hand — any CLI "
            "flag change can silently drift the hook surface (issue #140 bug class).",
            "Git workflow <-> Hooks coupling is bidirectional: commands/git_commit.py and "
            "git_inspect.py import workflow.hooks validators while workflow/hooks.py "
            "imports commands/git_sync.py and commands/branch.py.",
            "docs/publisher.py and docs/api_index.py lazy-import cli to break an import "
            "cycle — the docs engine depends on the CLI shell it is documented by.",
            "The .rrt/ lock store has split ownership: state.py names four lock files but "
            "drift.lock.toml (commands/drift_cmd.py) and docs_map.lock.toml "
            "(commands/docs_map_lock.py) define their own filenames.",
            "mcp/tools/version_tools.py writes version targets directly (partial bump) "
            "instead of sharing commands/bump.py's full pipeline — two writers with "
            "different semantics for ds:version-targets.",
            "ui/ is a pure leaf imported by every domain — safest first extraction target.",
            "Data-edge kinds are heuristic (pattern scan + explicit table in "
            "extract_topology.py); read/write direction verified only for the explicit table.",
            "Eight package __init__ modules (assets, docs, integrations, mcp, sync, tools, "
            "version, workflow) have zero in-tree inbound imports — every consumer bypasses "
            "the package re-export surface and imports submodules directly. Suppressed from "
            "deadEnds because external code may import them.",
        ],
        "flows": [
            {
                "name": "Maintainer releases a new version",
                "persona": "Project maintainer",
                "description": "A maintainer runs `rrt bump` and every version string, "
                "pin, changelog section, and release branch updates together.",
                "steps": [
                    {"label": "Maintainer runs `rrt bump minor`", "nodes": ["cli", "commands.bump"]},
                    {"label": "Project config is loaded and validated", "nodes": ["config.core", "ds:rrt-config"]},
                    {"label": "Next version is computed (semver/calver)", "nodes": ["version.semver", "version.calver"]},
                    {"label": "Version strings are rewritten across all target files", "nodes": ["version.targets", "ds:version-targets"]},
                    {"label": "[Unreleased] changelog section becomes the release section", "nodes": ["changelog", "ds:changelog"]},
                    {"label": "Release branch and commit are created", "nodes": ["workflow.git", "ds:git-repo"]},
                    {"label": "Preflight checks confirm the release is consistent", "nodes": ["preflight"]},
                ],
            },
            {
                "name": "Contributor commits a change",
                "persona": "Contributor",
                "description": "On every `git commit`, hooks validate the branch name and "
                "commit message and auto-write the changelog entry.",
                "steps": [
                    {"label": "git commit triggers the pre-commit hook", "nodes": ["workflow.hooks", "ds:git-repo"]},
                    {"label": "Branch name is checked against <type>/<kebab-slug>", "nodes": ["workflow.hooks", "commands.branch"]},
                    {"label": "Commit subject is checked against Conventional Commits", "nodes": ["workflow.hooks"]},
                    {"label": "A changelog bullet is auto-written into [Unreleased]", "nodes": ["changelog", "ds:changelog"]},
                    {"label": "Updated changelog is re-staged into the commit", "nodes": ["workflow.git", "ds:git-repo"]},
                ],
            },
            {
                "name": "CI gates a pull request",
                "persona": "Reviewer / release manager",
                "description": "The GitHub Action re-runs the same policy checks in CI so "
                "nothing merges that a local hook would have rejected.",
                "steps": [
                    {"label": "PR triggers the composite Action", "nodes": ["action.yml"]},
                    {"label": "Action shells out to rrt-hooks checks", "nodes": ["workflow.hooks"]},
                    {"label": "Branch, commit, changelog, and tree cleanliness are validated", "nodes": ["workflow.hooks", "ds:changelog", "ds:git-repo"]},
                    {"label": "Repo health (doctor, EOL, folders, artifacts) is verified", "nodes": ["commands.doctor", "eol.core", "commands.folder", "commands.artifacts_cmd", "ds:rrt-locks"]},
                    {"label": "A health-summary JSON lands in the workflow output", "nodes": ["action.yml"]},
                ],
            },
            {
                "name": "AI agent operates the repo via MCP",
                "persona": "AI coding agent",
                "description": "An agent connected over MCP inspects versions, validates "
                "names, and previews bumps without shelling out to the CLI.",
                "steps": [
                    {"label": "Agent connects to the rrt-mcp server", "nodes": ["mcp.server"]},
                    {"label": "Agent inspects version and lock state", "nodes": ["mcp.tools.version_tools", "mcp.tools.lock_tools", "ds:rrt-locks"]},
                    {"label": "Agent validates branch/commit names with the same hook logic", "nodes": ["mcp.tools.validation_tools", "workflow.hooks"]},
                    {"label": "Agent previews (dry-run) a version bump", "nodes": ["mcp.tools.version_tools", "version.targets", "ds:version-targets"]},
                    {"label": "Results return as typed Pydantic models", "nodes": ["mcp.models"]},
                ],
            },
        ],
    }

    out = HERE / "topology.json"
    out.write_text(json.dumps(topo, indent=1), encoding="utf-8")

    # --- summary
    n_modules = sum(
        len(d["children"]) for d in domains.values() if d["id"] != "dom:data"
    )
    kinds: dict[str, int] = {}
    for _, _, k in edges:
        kinds[k] = kinds.get(k, 0) + 1
    print(f"topology.json written: {out}")
    print(f"  domains: {len(domains) - 1} + data stores")
    print(f"  modules: {n_modules} ({len(files)} python files + action.yml)")
    print(f"  datastores: {len(DATASTORES)}")
    print(f"  edges: {len(edges)} {kinds}")
    print(f"  entry points: {', '.join(entry_points)}")
    print(f"  dead-end candidates ({len(dead)}): {', '.join(dead)}")


if __name__ == "__main__":
    main()
