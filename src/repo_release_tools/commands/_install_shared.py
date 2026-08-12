"""Cross-cutting helpers shared by two or more install-family commands.

`agents_cmd.py`, `hooks_cmd.py`, `install_cmd.py`, and `skill.py` each install
bundled assets (agents, hooks, skills) into per-tool target directories. A
handful of helpers -- `dedupe_targets`, `display_path`, `emit_install_error`,
and `resolve_install_plan` -- are identical logic duplicated across those
modules, so they live here instead of in any single family module. This
module holds no command handlers of its own and is not registered as a
subcommand; it exists purely as internal infrastructure imported by the
family modules.

`hooks_cmd.py`'s target-plan resolver returns `(target, hooks_dir,
hook_files)` triples instead of `(target, path)` tuples, since it also needs
to enumerate hook files per target -- that variant is genuinely different and
stays local to `hooks_cmd.py` rather than living here.
"""

from __future__ import annotations

import contextlib
import sys
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

from repo_release_tools.ui import VerbosePrinter


def dedupe_targets(targets: Iterable[str]) -> list[str]:
    """Return targets in first-seen order without duplicates."""
    seen: set[str] = set()
    ordered: list[str] = []
    for target in targets:
        if target in seen:
            continue
        seen.add(target)
        ordered.append(target)
    return ordered


def display_path(path: Path, *, cwd: Path, home: Path) -> str:
    """Render *path* relative to cwd or home when possible."""
    with contextlib.suppress(ValueError):
        return str(path.relative_to(cwd))
    with contextlib.suppress(ValueError):
        return f"~/{path.relative_to(home)}"
    return str(path)


def emit_install_error(message: str) -> int:
    """Print *message* as a failure line to stderr and return exit code 1."""
    p = VerbosePrinter()
    p.line(message, ok=False, stream=sys.stderr)
    return 1


def resolve_install_plan(
    targets: list[str],
    target_paths: Mapping[str, Callable[[Path, Path], Path]],
    *,
    cwd: Path,
    home: Path,
) -> list[tuple[str, Path]]:
    """Resolve target names into base install directories via *target_paths*."""
    return [(target, target_paths[target](cwd, home)) for target in dedupe_targets(targets)]
