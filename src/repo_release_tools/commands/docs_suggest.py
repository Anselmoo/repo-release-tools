"""Suggest or scaffold rich module docstrings for command modules.

`rrt docs suggest` scans Python command modules for missing or thin module
docstrings and emits a Markdown-rich scaffold that contributors can adapt in
place. The command is intentionally narrow: it only targets the command module
tree by default, focuses on human-readable module documentation, and supports
an ``--apply`` mode for writing the scaffold back to disk when a file needs a
full replacement.

## Responsibilities

- detect missing or underspecified top-level module docstrings
- generate a consistent scaffold with overview, responsibilities, and examples
- apply the scaffold in place when the caller requests it

## Usage

```bash
uv run rrt docs suggest
uv run rrt docs suggest --apply src/repo_release_tools/commands/branch.py
```

The implementation lives under ``src/`` so the feature stays aligned with the
rest of the CLI instead of depending on a standalone helper script.
"""

from __future__ import annotations

import argparse
import ast
import os
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent

from repo_release_tools.ui import DryRunPrinter

DEFAULT_MIN_CHARS = 150
EXEMPT_FILES = frozenset({"__init__.py", "__main__.py"})


@dataclass(frozen=True)
class _DocstringFinding:
    path: Path
    reason: str
    scaffold: str


def _iter_targets(paths: Iterable[Path]) -> list[Path]:
    """Return the Python files to inspect.

    Recursively scans directories while skipping well-known transient/system
    directories defined in the project's ignore list.
    """
    from repo_release_tools.config import ignore_dir_names

    targets: list[Path] = []
    ignored_dirs = ignore_dir_names()
    for path in paths:
        if path.is_dir():
            for root, dirs, files in os.walk(path):
                # Prune ignored directories in-place to prevent traversal.
                dirs[:] = [d for d in dirs if d not in ignored_dirs]
                for file in files:
                    if file.endswith(".py"):
                        targets.append(Path(root) / file)
        elif path.is_file() and path.suffix == ".py":
            targets.append(path)
    return sorted(targets)


def _resolve_target_path(path: Path, root: Path) -> Path:
    """Resolve a caller-supplied target path against *root* when needed."""
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _should_exempt(path: Path, text: str, exempt_files: set[str]) -> bool:
    """Return whether *path* should be skipped by the scanner."""
    if path.name in exempt_files:
        return True
    return "rrt:docs-exempt" in text


def _command_slug(path: Path) -> str:
    """Convert a module path into a command slug."""
    stem = path.stem
    stem = stem.removesuffix("_cmd")
    return stem.replace("_", "-")


def _read_module_docstring(path: Path) -> str | None:
    """Return the module docstring, or ``None`` when the file cannot be parsed."""
    try:
        module = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return None
    return ast.get_docstring(module)


def build_scaffold(path: Path) -> str:
    """Create a Markdown-rich docstring scaffold for *path*."""
    slug = _command_slug(path)
    title = f"`rrt {slug}` — rich command module docstring scaffold"
    body = dedent(
        f"""
        {title}

        ## Overview

        Describe what `rrt {slug}` does, which files or repositories it reads,
        and what side effects it may have. Keep the explanation specific to the
        module and useful to both contributors and automation.

        ## Responsibilities

        - explain the command family and any notable subcommands
        - note the main inputs, outputs, and safety constraints
        - mention any config keys or environment variables that affect behavior

        ## Examples

        ```bash
        rrt {slug} --help
        ```

        Replace this scaffold with a concise, accurate, multi-line module
        docstring that uses Markdown consistently.
        """,
    ).strip()
    return f'"""{body}\n"""\n'


def _insert_or_replace_docstring(path: Path, scaffold: str) -> bool:
    """Insert or replace the top-level module docstring in *path*."""
    source = path.read_text(encoding="utf-8")
    try:
        module = ast.parse(source)
    except SyntaxError as exc:
        sys.stderr.write(
            f"Skipping {path}: could not apply docstring scaffold because the file "
            f"failed to parse ({exc.msg}).\n",
        )
        return False
    lines = source.splitlines(keepends=True)

    if module.body and isinstance(module.body[0], ast.Expr):
        node = module.body[0]
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            start = node.lineno - 1
            end = node.end_lineno or node.lineno
            lines[start:end] = [scaffold]
            path.write_text("".join(lines), encoding="utf-8")
            return True

    insert_at = 1 if lines and lines[0].startswith("#!") else 0
    while (
        insert_at < len(lines) and lines[insert_at].startswith("#") and "coding" in lines[insert_at]
    ):
        insert_at += 1
    lines[insert_at:insert_at] = [scaffold, "\n"]
    path.write_text("".join(lines), encoding="utf-8")
    return True


def scan(
    paths: Iterable[Path],
    *,
    min_chars: int = DEFAULT_MIN_CHARS,
    exempt_files: set[str] | None = None,
) -> list[_DocstringFinding]:
    """Find files whose module docstrings should be expanded."""
    effective_exempt_files = set(EXEMPT_FILES)
    if exempt_files:
        effective_exempt_files.update(exempt_files)

    findings: list[_DocstringFinding] = []
    for path in _iter_targets(paths):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue

        if _should_exempt(path, text, exempt_files=effective_exempt_files):
            continue

        docstring = _read_module_docstring(path)
        doc = docstring.strip() if docstring else ""
        needs_help = not docstring or "\n" not in doc or len(doc) < min_chars
        if not needs_help:
            continue

        reason = "docstring is too short or too flat" if docstring else "missing docstring"
        findings.append(_DocstringFinding(path=path, reason=reason, scaffold=build_scaffold(path)))
    return findings


def cmd_docs_suggest(args: argparse.Namespace) -> int:
    """Suggest or apply rich module docstrings for command modules."""
    from repo_release_tools.config import load_config

    root = Path(getattr(args, "root", ".")).resolve()

    # Load config to get suggest settings
    cfg = None
    try:
        cfg = load_config(root)
    except (FileNotFoundError, ValueError):
        pass

    # Default to scanning the source directory or current directory if not specified
    suggest_roots_list: list[str] = ["."]
    exempt_files: set[str] | None = None
    arg_min_chars = getattr(args, "min_chars", None)
    min_chars = DEFAULT_MIN_CHARS if arg_min_chars is None else int(arg_min_chars)

    if cfg and cfg.docs:
        if cfg.docs.suggest_roots:
            suggest_roots_list = list(cfg.docs.suggest_roots)
        elif cfg.docs.src_dir:
            suggest_roots_list = [cfg.docs.src_dir]

        if cfg.docs.suggest_exempt:
            exempt_files = set(cfg.docs.suggest_exempt)
        if cfg.docs.suggest_min_chars is not None and arg_min_chars is None:
            min_chars = cfg.docs.suggest_min_chars

    raw_paths = list(getattr(args, "paths", ()) or ())
    paths = (
        [_resolve_target_path(Path(p), root) for p in raw_paths]
        if raw_paths
        else [_resolve_target_path(Path(p), root) for p in suggest_roots_list]
    )
    apply = bool(getattr(args, "apply", False))

    p = DryRunPrinter(dry_run=False)
    findings = scan(paths, min_chars=min_chars, exempt_files=exempt_files)

    if not findings:
        p.ok("No docstring scaffolds needed.")
        return 0

    for finding in findings:
        try:
            label = finding.path.relative_to(root)
        except ValueError:
            label = finding.path
        p.section(str(label))
        p.line(finding.reason, ok=False)
        sys.stdout.write(f"{finding.scaffold}\n")
        if apply and _insert_or_replace_docstring(finding.path, finding.scaffold):
            p.ok(f"Applied scaffold to {finding.path}")

    return 0
