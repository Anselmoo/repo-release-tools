"""Interactive resolver for phantom (untrackable) empty directories.

Used by ``rrt tree --fix-empty-dirs``. For every directory in the supplied
list, prompt the user to either add a ``.gitkeep`` placeholder (so git keeps
the directory and CI manifests match local) or delete the directory. Honors
``--dry-run`` and ``--yes``.
"""

from __future__ import annotations

from pathlib import Path

from repo_release_tools.ui import DryRunPrinter
from repo_release_tools.ui.prompt import ask


def fix_empty_dirs(
    root: Path,
    phantom_dirs: list[str],
    *,
    printer: DryRunPrinter,
    dry_run: bool = False,
    assume_yes: bool = False,
) -> int:
    """Resolve phantom empty directories interactively.

    Parameters
    ----------
    root:        Scan root used as the base for each posix path.
    phantom_dirs: Directories with no children and no .gitkeep.
    printer:     Active DryRunPrinter (preserves --dry-run formatting).
    dry_run:     When True, only print planned actions.
    assume_yes:  When True, add .gitkeep for every entry without prompting.

    Returns 0 on success, 1 when at least one action failed.
    """
    if not phantom_dirs:
        printer.ok("No phantom empty directories found. Tree is CI-stable.")
        return 0

    prefix = "[DRY RUN] " if dry_run else ""
    printer.ok(f"{prefix}Empty-directory fix")
    printer.meta("Root", str(root))
    printer.meta(
        "Found", f"{len(phantom_dirs)} empty director{'y' if len(phantom_dirs) == 1 else 'ies'}"
    )
    printer.blank_line()

    added: list[str] = []
    removed: list[str] = []
    skipped: list[str] = []
    failed: list[tuple[str, str]] = []

    for rel in phantom_dirs:
        target = root / rel
        choice = _choose_action(rel, assume_yes=assume_yes)

        match choice:
            case "gitkeep":
                if dry_run:
                    printer.action(f"[dry-run] Would create {rel}/.gitkeep")
                    added.append(rel)
                else:
                    try:
                        target.mkdir(parents=True, exist_ok=True)
                        (target / ".gitkeep").write_text("", encoding="utf-8")
                        printer.ok(f"Created {rel}/.gitkeep")
                        added.append(rel)
                    except OSError as exc:
                        printer.line(f"Failed to create {rel}/.gitkeep: {exc}", ok=False)
                        failed.append((rel, str(exc)))
            case "delete":
                if dry_run:
                    printer.action(f"[dry-run] Would remove {rel}/")
                    removed.append(rel)
                else:
                    try:
                        target.rmdir()
                        printer.ok(f"Removed {rel}/")
                        removed.append(rel)
                    except OSError as exc:
                        printer.line(f"Failed to remove {rel}/: {exc}", ok=False)
                        failed.append((rel, str(exc)))
            case _:
                printer.action(f"Skipped {rel}/")
                skipped.append(rel)

    printer.blank_line()
    printer.meta("Added .gitkeep", str(len(added)))
    printer.meta("Removed", str(len(removed)))
    printer.meta("Skipped", str(len(skipped)))
    if failed:
        printer.meta("Failed", str(len(failed)))
    if dry_run:
        printer.action("[dry-run] complete – no changes made")
    return 1 if failed else 0


def _choose_action(rel: str, *, assume_yes: bool) -> str:
    """Return one of: 'gitkeep', 'delete', 'skip'."""
    if assume_yes:
        return "gitkeep"
    answer = (
        ask(
            f"  {rel}/ — (k)eep+gitkeep, (d)elete, (s)kip",
            default="k",
        )
        .strip()
        .lower()
    )
    if answer in {"d", "delete"}:
        return "delete"
    if answer in {"s", "skip"}:
        return "skip"
    return "gitkeep"
