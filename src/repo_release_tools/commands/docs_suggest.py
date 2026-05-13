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
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent

from repo_release_tools.ui import DryRunPrinter

DEFAULT_MIN_CHARS = 150
DEFAULT_ROOT = Path("src") / "repo_release_tools" / "commands"
EXEMPT_FILES = {"__init__.py", "__main__.py"}


@dataclass(frozen=True)
class _DocstringFinding:
    path: Path
    reason: str
    scaffold: str


def _iter_targets(paths: Iterable[Path]) -> list[Path]:
    """Return the Python files to inspect."""
    targets: list[Path] = []
    for path in paths:
        if path.is_dir():
            targets.extend(sorted(path.rglob("*.py")))
        elif path.is_file() and path.suffix == ".py":
            targets.append(path)
    return targets


def _resolve_target_path(path: Path, root: Path) -> Path:
    """Resolve a caller-supplied target path against *root* when needed."""
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _should_exempt(path: Path, text: str) -> bool:
    """Return whether *path* should be skipped by the scanner."""
    return path.name in EXEMPT_FILES or "rrt:docs-exempt" in text


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


def scan(paths: Iterable[Path], *, min_chars: int = DEFAULT_MIN_CHARS) -> list[_DocstringFinding]:
    """Find files whose module docstrings should be expanded."""
    findings: list[_DocstringFinding] = []
    for path in _iter_targets(paths):
        text = path.read_text(encoding="utf-8")
        if _should_exempt(path, text):
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
    root = Path(getattr(args, "root", ".")).resolve()
    raw_paths = list(getattr(args, "paths", ()) or ())
    paths = (
        [_resolve_target_path(Path(p), root) for p in raw_paths]
        if raw_paths
        else [root / DEFAULT_ROOT]
    )
    min_chars = int(getattr(args, "min_chars", DEFAULT_MIN_CHARS))
    apply = bool(getattr(args, "apply", False))

    p = DryRunPrinter(dry_run=False)
    findings = scan(paths, min_chars=min_chars)

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
