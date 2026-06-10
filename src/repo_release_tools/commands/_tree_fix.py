"""Interactive resolver for phantom (untrackable) empty directories.

Used by ``rrt tree --fix-empty-dirs``. For every directory in the supplied
list, prompt the user to either add a ``.gitkeep`` placeholder (so git keeps
the directory and CI manifests match local) or delete the directory. Honors
``--dry-run``, ``--yes``, and ``--auto-resolve``.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from repo_release_tools.ui import DryRunPrinter
from repo_release_tools.ui.prompt import ask

AUTO_RESOLVE_CHOICES: tuple[str, ...] = ("gitkeep", "delete", "hard", "git-rm")


def fix_empty_dirs(
    root: Path,
    phantom_dirs: list[str],
    *,
    printer: DryRunPrinter,
    dry_run: bool = False,
    assume_yes: bool = False,
    auto_resolve: str | None = None,
) -> int:
    """Resolve phantom empty directories interactively.

    Parameters
    ----------
    root:        Scan root used as the base for each posix path.
    phantom_dirs: Directories with no children and no .gitkeep.
    printer:     Active DryRunPrinter (preserves --dry-run formatting).
    dry_run:     When True, only print planned actions.
    assume_yes:  When True, add .gitkeep for every entry without prompting.
    auto_resolve: One of ``"gitkeep"``, ``"delete"``, ``"hard"``, ``"git-rm"``.
                 When set, every phantom directory is resolved with that
                 action without prompting. Takes precedence over
                 ``assume_yes``.

    Returns 0 on success, 1 when at least one action failed.
    """
    if auto_resolve is not None and auto_resolve not in AUTO_RESOLVE_CHOICES:
        printer.line(
            f"Unknown --auto-resolve choice: {auto_resolve!r}. "
            f"Expected one of: {', '.join(AUTO_RESOLVE_CHOICES)}.",
            ok=False,
        )
        return 1

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
        choice = _resolve_choice(rel, assume_yes=assume_yes, auto_resolve=auto_resolve)

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
            case "hard-delete":
                if dry_run:
                    printer.action(f"[dry-run] Would hard-remove {rel}/")
                    removed.append(rel)
                else:
                    try:
                        shutil.rmtree(target)
                        printer.ok(f"Removed {rel}/")
                        removed.append(rel)
                    except OSError as exc:
                        printer.line(f"Failed to remove {rel}/: {exc}", ok=False)
                        failed.append((rel, str(exc)))
            case "git-rm":
                if dry_run:
                    printer.action(f"[dry-run] Would git-rm {rel}/")
                    removed.append(rel)
                else:
                    result = subprocess.run(
                        ["git", "rm", "-rf", "--", rel],
                        cwd=root,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if result.returncode == 0:
                        printer.ok(f"git-removed {rel}/ (staged for next commit)")
                        removed.append(rel)
                    else:
                        message = (result.stderr or result.stdout or "").strip() or (
                            f"git rm exited with {result.returncode}"
                        )
                        printer.line(f"Failed to git-rm {rel}/: {message}", ok=False)
                        failed.append((rel, message))
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


def _resolve_choice(rel: str, *, assume_yes: bool, auto_resolve: str | None) -> str:
    """Return the resolution choice for *rel* honoring `auto_resolve` and `assume_yes`.

    Output values are the canonical action labels used by the match-case in
    :func:`fix_empty_dirs`: ``"gitkeep"``, ``"delete"``, ``"hard-delete"``,
    ``"git-rm"``, or ``"skip"``.
    """
    if auto_resolve is not None:
        if auto_resolve == "hard":
            return "hard-delete"
        return auto_resolve  # "gitkeep" | "delete" | "git-rm"
    return _choose_action(rel, assume_yes=assume_yes)


def _choose_action(rel: str, *, assume_yes: bool) -> str:
    """Return one of: 'gitkeep', 'delete', 'hard-delete', 'git-rm', 'skip'."""
    if assume_yes:
        return "gitkeep"
    answer = (
        ask(
            f"  {rel}/ — (k)eep+gitkeep, (d)elete, (h)ard-delete, (g)it-rm, (s)kip",
            default="k",
        )
        .strip()
        .lower()
    )
    match answer:
        case "d" | "delete":
            return "delete"
        case "h" | "hard" | "hard-delete":
            return "hard-delete"
        case "g" | "git" | "git-rm" | "gitrm":
            return "git-rm"
        case "s" | "skip":
            return "skip"
        case _:
            return "gitkeep"
