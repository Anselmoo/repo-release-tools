"""Pre-flight validation helpers for mutating rrt commands."""

from __future__ import annotations

from pathlib import Path

from repo_release_tools.config import RrtConfig, VersionGroup
from repo_release_tools.ui import DryRunPrinter
from repo_release_tools.version.targets import read_version_string
from repo_release_tools.workflow import git


class PreflightError(RuntimeError):
    """Raised when a pre-flight check fails."""


def check_working_tree_clean(root: Path) -> None:
    """Raise :class:`PreflightError` when the working tree has uncommitted changes."""
    if not git.working_tree_clean(root):
        raise PreflightError(
            "Working tree has uncommitted changes. Commit or stash them first, or use --dry-run."
        )


def check_version_targets_readable(group: VersionGroup) -> None:
    """Raise :class:`PreflightError` when any version target cannot be read."""
    errors: list[str] = []
    for target in group.version_targets:
        if not target.path.exists():
            errors.append(f"Version target {target.path} does not exist")
            continue
        try:
            read_version_string(target)
        except (RuntimeError, OSError) as exc:
            errors.append(f"Version target {target.path}: {exc}")
    if errors:
        raise PreflightError("Version target pre-flight checks failed:\n" + "\n".join(errors))


def check_config_consistent(config: RrtConfig) -> None:
    """Raise :class:`PreflightError` for obviously inconsistent config."""
    if not config.version_groups:
        raise PreflightError("No version groups are configured in [tool.rrt].")


def run_preflight(config: RrtConfig, *, dry_run: bool, group: VersionGroup) -> None:
    """Run all pre-flight checks for a mutating command.

    Checks:
    - Working tree is clean (skipped when *dry_run* is True)
    - Config is self-consistent
    - All version targets are readable

    Raises :class:`PreflightError` with a description of the first failure.
    """
    p = DryRunPrinter(dry_run)
    p.section("Pre-flight checks")

    check_config_consistent(config)
    p.ok("Config is consistent")

    check_version_targets_readable(group)
    p.ok("Version targets are readable")

    if not dry_run:
        check_working_tree_clean(config.root)
        p.ok("Working tree is clean")
