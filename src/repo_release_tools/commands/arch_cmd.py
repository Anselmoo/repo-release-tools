"""Architecture skeleton command family: `rrt arch check`, `baseline` and `new`.

## Overview

`rrt arch` enforces a declared architecture skeleton from `[tool.rrt.architecture]`.
The table names a root package, its units, their roles and the layer order.
`rrt arch check` reports what the tree does not match.

Findings come in seven kinds:

- `missing-unit` — a declared unit's package or module does not exist.
- `undeclared` — an entry under the root is neither a unit nor a top-level file.
- `missing-file` — a unit package lacks a required file for its role.
- `unplaced` — an existing unit is not named in `layers`.
- `layer-import` — a Python import goes against the layer order.
- `unparsable` — a Python file under a layered root cannot be parsed, so its imports are unchecked.
- `layers-sync` — the import-linter layers contract differs from `layers`.

`rrt arch baseline` records today's findings in `.rrt/architecture.baseline.toml`.
The baseline only shrinks: `check --strict` fails on new findings and on stale entries.
`rrt arch new` renders a kind from `.rrt/templates/<kind>/` into the repository.

## Examples

```bash
rrt arch check
rrt arch check --strict
rrt arch baseline --dry-run
rrt arch new step normalize --unit prepare --dry-run
rrt arch new --check-templates
```

```toml
[tool.rrt.architecture]
root = "src/pkg"
top_level_files = ["__init__.py", "README.md"]
layers = ["api", "core", "errors"]

[tool.rrt.architecture.required_files]
unit = ["__init__.py", "README.md"]

[[tool.rrt.architecture.units]]
name = "api"
role = "door"

[[tool.rrt.architecture.units]]
name = "core"

[[tool.rrt.architecture.units]]
name = "errors"
module = "errors"
role = "foundation"
```

## Caveats

`check` is advisory and exits 0 unless `--strict` is given.
The import check reads Python files with `ast` only. Dynamic imports are not seen.
Imports inside `if TYPE_CHECKING:` blocks count as dependencies.
Other languages get no import check.
`layers` names units, not packages. The import-linter comparison translates each name.
Gitignored entries, `__pycache__` and dot-entries are never `undeclared`.
`baseline` without `--force` only removes resolved entries. It exits 1 when new findings remain.
`new` never edits a registry. It prints the kind's next steps instead.
`new` refuses an existing target unless `--force` is given, even in a dry run.

## Related docs

- [Repository health](/repo-release-tools/commands/repo-health/)
- [Internal contracts](/repo-release-tools/reference/internal-contracts/)
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from repo_release_tools.architecture.core import Finding, collect_findings, root_module_name
from repo_release_tools.architecture.templates import (
    TemplateError,
    build_variables,
    check_templates,
    load_kind,
    render_kind,
    write_rendered,
)
from repo_release_tools.commands._cli_shared import add_dry_run_flag
from repo_release_tools.commands._registry import CommandCategory, CommandGroup, register_command
from repo_release_tools.config import ArchitectureConfig, load_config
from repo_release_tools.state import (
    arch_baseline_diff,
    arch_baseline_path,
    read_arch_baseline,
    write_arch_baseline,
)
from repo_release_tools.ui import DryRunPrinter

ARCH_EPILOG = (
    "  $ rrt arch check --strict\n"
    "  $ rrt arch baseline --dry-run\n"
    "  $ rrt arch new step normalize --unit prepare --dry-run"
)


@dataclass(frozen=True)
class ArchOptions:
    """Typed view of ``argparse.Namespace`` for every ``rrt arch`` subcommand."""

    root: str
    verbose: int
    strict: bool
    dry_run: bool
    force: bool
    kind: str | None
    name: str | None
    unit: str | None
    check_templates: bool

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> ArchOptions:
        """Build options; subcommands that lack a flag get its neutral default."""
        return cls(
            root=getattr(args, "root", "."),
            verbose=getattr(args, "verbose", 0) or 0,
            strict=getattr(args, "strict", False),
            dry_run=getattr(args, "dry_run", False),
            force=getattr(args, "force", False),
            kind=getattr(args, "kind", None),
            name=getattr(args, "name", None),
            unit=getattr(args, "unit", None),
            check_templates=getattr(args, "check_templates", False),
        )


def _error(p: DryRunPrinter, message: str) -> int:
    """Print *message* to stderr and return exit code 1."""
    p.line(message, ok=False, stream=sys.stderr)
    return 1


class ArchCheckError(Exception):
    """Raised when the architecture check cannot run; the message says why."""


def load_architecture(repo_root: Path) -> ArchitectureConfig:
    """Return the ``[tool.rrt.architecture]`` config, or raise :class:`ArchCheckError`."""
    try:
        config = load_config(repo_root)
    except (FileNotFoundError, ValueError) as exc:
        raise ArchCheckError(f"Could not load [tool.rrt] config: {exc}") from exc
    if config.architecture is None:
        raise ArchCheckError("[tool.rrt.architecture] is not configured.")
    return config.architecture


def load_arch_findings(repo_root: Path) -> tuple[ArchitectureConfig, list[Finding]]:
    """Return the config and its findings for a resolved *repo_root*.

    Shared by ``rrt arch check``, ``rrt-hooks arch-check`` and the
    ``rrt_arch_check`` MCP tool. Raises :class:`ArchCheckError` when the
    config is missing or its root does not exist.
    """
    arch = load_architecture(repo_root)
    if not (repo_root / arch.root).is_dir():
        raise ArchCheckError(f"Architecture root {arch.root!r} does not exist.")
    return arch, collect_findings(arch, repo_root, is_ignored=_git_ignore_filter(repo_root))


def _load_architecture(p: DryRunPrinter, repo_root: Path) -> tuple[ArchitectureConfig | None, int]:
    """Return the architecture config, or ``(None, 1)`` after printing why."""
    try:
        return load_architecture(repo_root), 0
    except ArchCheckError as exc:
        return None, _error(p, str(exc))


def _git_ignore_filter(repo_root: Path) -> Callable[[list[str]], set[str]]:
    """Return a filter that drops gitignored paths (none outside a git checkout)."""
    from repo_release_tools.commands.tree import _batch_ignored_by_git  # noqa: PLC0415

    def _filter(paths: list[str]) -> set[str]:
        return _batch_ignored_by_git(paths, repo_root=repo_root)

    return _filter


def _findings(
    p: DryRunPrinter, opts: ArchOptions
) -> tuple[Path, ArchitectureConfig | None, list[Finding], int]:
    """Resolve the root, load config and collect findings; exit code 1 on failure."""
    repo_root = Path(opts.root).resolve()
    try:
        arch, findings = load_arch_findings(repo_root)
    except ArchCheckError as exc:
        return repo_root, None, [], _error(p, str(exc))
    return repo_root, arch, findings, 0


def cmd_arch_check(args: argparse.Namespace) -> int:
    """Report architecture findings against the baseline; ``--strict`` fails on drift."""
    opts = ArchOptions.from_args(args)
    p = DryRunPrinter(dry_run=False, verbose=opts.verbose)
    repo_root, arch, findings, code = _findings(p, opts)
    if arch is None:
        return code

    baseline_file = arch_baseline_path(repo_root)
    has_baseline = baseline_file.exists()
    new, stale = arch_baseline_diff(baseline_file, [f.id for f in findings])
    new_ids = set(new)

    p.header(
        "Architecture check",
        Root=arch.root,
        Baseline=baseline_file.relative_to(repo_root).as_posix() if has_baseline else "none",
    )
    p.section("Findings")
    if not findings:
        p.ok("No findings.")
    for finding in findings:
        if finding.id in new_ids:
            p.line(f"[new] {finding.id} — {finding.message}", ok=False)
        else:
            p.list_item(f"{finding.id} — {finding.message}")
    for entry in stale:
        p.warn(f"[stale] {entry} — resolved; remove it with `rrt arch baseline`.")

    summary = (
        f"{len(findings)} finding(s): {len(new)} new, "
        f"{len(findings) - len(new)} baselined, {len(stale)} stale"
    )
    if opts.strict and (new or stale):
        p.blank_line()
        return _error(
            p,
            f"Architecture drift: {summary}. Fix the new findings; "
            "run `rrt arch baseline` to drop stale entries.",
        )
    p.footer(f"Done. {summary}")
    return 0


def cmd_arch_baseline(args: argparse.Namespace) -> int:
    """Seed or shrink the findings baseline; ``--force`` rewrites it with additions."""
    opts = ArchOptions.from_args(args)
    p = DryRunPrinter(dry_run=opts.dry_run, verbose=opts.verbose)
    repo_root, arch, findings, code = _findings(p, opts)
    if arch is None:
        return code

    baseline_file = arch_baseline_path(repo_root)
    current = [f.id for f in findings]
    existing = read_arch_baseline(baseline_file)
    new, stale = arch_baseline_diff(baseline_file, current)
    if existing is None or opts.force:
        target = current
        refused: list[str] = []
    else:
        target = sorted(set(existing) - set(stale))
        refused = new

    rel = baseline_file.relative_to(repo_root).as_posix()
    p.header("Architecture baseline", File=rel, Entries=str(len(target)))
    p.section("Changes")
    added = [] if existing is None else sorted(set(target) - set(existing))
    for entry in added if existing is not None else target:
        p.list_item(f"+ {entry}")
    for entry in stale:
        p.list_item(f"- {entry}")

    changed = existing != sorted(set(target))
    if not changed:
        p.ok("Baseline is up to date.")
    elif p.dry_run:
        p.would_write(rel, detail=f"{len(target)} entr(ies)")
    else:
        write_arch_baseline(baseline_file, target)
        p.ok(f"Wrote {rel}")

    if refused:
        p.blank_line()
        for entry in refused:
            p.line(f"[new] {entry}", ok=False, stream=sys.stderr)
        return _error(
            p,
            f"{len(refused)} new finding(s) not added. Fix them, or run "
            "`rrt arch baseline --force` to accept them.",
        )
    p.footer("Done.")
    return 0


def cmd_arch_new(args: argparse.Namespace) -> int:
    """Render a template kind into the repository, or self-test every kind."""
    opts = ArchOptions.from_args(args)
    p = DryRunPrinter(dry_run=opts.dry_run, verbose=opts.verbose)
    repo_root = Path(opts.root).resolve()
    arch, code = _load_architecture(p, repo_root)
    if arch is None:
        return code
    root_module = root_module_name(repo_root / arch.root, repo_root)

    if opts.check_templates:
        if opts.kind or opts.name:
            return _error(p, "--check-templates takes no kind or name.")
        return _check_templates(p, arch, repo_root, root_module)
    if not opts.kind or not opts.name:
        return _error(p, "Usage: rrt arch new <kind> <name> [--unit UNIT].")

    unit = None
    if opts.unit is not None:
        unit = arch.unit_named(opts.unit)
        if unit is None:
            known = ", ".join(u.name for u in arch.units) or "none"
            return _error(p, f"Unknown unit {opts.unit!r}. Declared units: {known}.")
    try:
        kind = load_kind(repo_root, opts.kind)
        variables = build_variables(
            config=arch, root_module=root_module, name=opts.name, unit=unit, kind=kind
        )
        files = render_kind(kind, variables, repo_root, force=opts.force)
    except TemplateError as exc:
        return _error(p, str(exc))

    p.header(f"New {kind.name}: {opts.name}", Kind=kind.description or kind.name)
    p.section("Files")
    for rendered in files:
        detail = "overwrite" if rendered.exists else "create"
        if p.dry_run:
            p.would_write(rendered.target, detail=detail)
            sys.stdout.write(
                rendered.body if rendered.body.endswith("\n") else rendered.body + "\n"
            )
        else:
            p.action(f"{detail}: {rendered.target}")
    if not p.dry_run:
        try:
            write_rendered(files)
        except OSError as exc:
            return _error(p, f"Writing the rendered files failed: {exc}")
        for step in kind.next_steps:
            p.meta("Next step", step)
    p.footer(f"Done. {len(files)} file(s)")
    return 0


def _check_templates(
    p: DryRunPrinter, arch: ArchitectureConfig, repo_root: Path, root_module: str
) -> int:
    """Run ``check_templates`` and report each kind; exit 1 on any problem."""
    results = check_templates(arch, repo_root, root_module)
    p.header("Template self-test", Kinds=str(len(results)))
    p.section("Kinds")
    if not results:
        p.warn("No kinds under .rrt/templates/.")
    failed = 0
    for kind_name, problems in sorted(results.items()):
        if not problems:
            p.ok(kind_name)
            continue
        failed += 1
        p.line(kind_name, ok=False, stream=sys.stderr)
        for problem in problems:
            p.list_item(problem, stream=sys.stderr)
    if failed:
        return _error(p, f"{failed} of {len(results)} kind(s) failed the self-test.")
    p.footer(f"Done. {len(results)} kind(s) ok")
    return 0


def cmd_arch_hook(args: argparse.Namespace) -> int:
    """Run ``rrt-hooks arch-check``: a strict check, then the optional template self-test.

    Both steps always run, so one hook run reports every problem; the exit
    code is 1 if either step fails.
    """
    opts = ArchOptions.from_args(args)
    check_args = argparse.Namespace(root=opts.root, verbose=opts.verbose, strict=True)
    code = cmd_arch_check(check_args)
    if opts.check_templates:
        new_args = argparse.Namespace(
            root=opts.root, verbose=opts.verbose, check_templates=True, dry_run=False
        )
        code = max(code, cmd_arch_new(new_args))
    return code


def _add_arch_hook_arguments(parser: argparse.ArgumentParser) -> None:
    """Register the ``rrt-hooks arch-check`` flags; the shared spec for that hook."""
    parser.add_argument(
        "--check-templates",
        action="store_true",
        default=False,
        help="Also self-test every .rrt/templates/ kind (rrt arch new --check-templates).",
    )
    _add_root_flag(parser)


def _add_root_flag(parser: argparse.ArgumentParser) -> None:
    """Register the shared ``--root`` flag."""
    parser.add_argument(
        "--root",
        default=".",
        metavar="PATH",
        help="Project root directory (default: current directory).",
    )


@register_command(name="arch", category=CommandCategory.WRITE, group=CommandGroup.REPO_HEALTH)
def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the `arch` command group."""
    parser = subparsers.add_parser(
        "arch",
        help="Check and scaffold a declared architecture skeleton",
        description=(
            "Check the tree against [tool.rrt.architecture], keep a shrink-only "
            "findings baseline, and render templates from .rrt/templates/."
        ),
        epilog=ARCH_EPILOG,
    )
    arch_sub = parser.add_subparsers(dest="arch_command", metavar="<arch_command>")

    check = arch_sub.add_parser(
        "check",
        help="Report architecture findings against the baseline.",
        description="Report findings; advisory unless --strict.",
    )
    check.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Exit 1 on any finding not in the baseline, or a stale baseline entry.",
    )
    _add_root_flag(check)
    check.set_defaults(handler=cmd_arch_check)

    baseline = arch_sub.add_parser(
        "baseline",
        help="Seed or shrink .rrt/architecture.baseline.toml.",
        description=(
            "Without a baseline, record today's findings. With one, remove resolved "
            "entries only; --force also adds new findings."
        ),
    )
    baseline.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Rewrite the baseline with today's findings, including new ones.",
    )
    _add_root_flag(baseline)
    add_dry_run_flag(baseline, verb="writing the baseline")
    baseline.set_defaults(handler=cmd_arch_baseline)

    new = arch_sub.add_parser(
        "new",
        help="Render a template kind from .rrt/templates/<kind>/.",
        description=(
            "Render every file of a kind with string.Template. All targets are "
            "checked before anything is written."
        ),
    )
    new.add_argument("kind", nargs="?", default=None, help="Template kind (a .rrt/templates/ dir).")
    new.add_argument("name", nargs="?", default=None, help="Snake_case name, e.g. normalize.")
    new.add_argument("--unit", default=None, metavar="UNIT", help="Declared unit to render into.")
    new.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Overwrite existing target files.",
    )
    new.add_argument(
        "--check-templates",
        action="store_true",
        default=False,
        help="Self-test every kind with sample values; write nothing.",
    )
    _add_root_flag(new)
    add_dry_run_flag(new, help_text="Print each target and its body instead of writing.")
    new.set_defaults(handler=cmd_arch_new)

    parser.set_defaults(handler=_default_help(parser))


def _default_help(parser: argparse.ArgumentParser) -> Callable[[argparse.Namespace], int]:
    """Print help and exit 1 when no subcommand was given."""

    def _handler(_args: argparse.Namespace) -> int:
        parser.print_help()
        return 1

    return _handler
