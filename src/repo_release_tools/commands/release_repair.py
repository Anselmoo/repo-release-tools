"""`rrt release repair` — fix or recreate a release branch.

## Overview

A release branch can drift in two ways:

1. **Polluted history** — feature commits land alongside the version bump on
   the same `release/v{ver}` branch. The PR ends up mixing feature work and
   the release commit.
2. **Drifted targets** — one or more `version_targets`, `pin_targets`, or the
   changelog `[VERSION]` section don't match the declared project version
   (typically because a manual edit was missed).

`rrt release repair` addresses both. Two modes share the same skeleton:

- **Recreate mode** (``--from BASE``): rewinds the current branch to ``BASE``
  via ``git reset --hard``, then replays the version bump cleanly against
  that base. The ``[VERSION]`` body is carried over from the polluted HEAD
  (or from ``--changelog-from PATH``), so no manually written entries are
  lost. A safety backup ref ``repair/backup/<branch>-<ts>`` is created first
  unless ``--no-backup`` is passed.
- **Verify mode** (no ``--from``): walks every version target, pin target,
  and the changelog `[VERSION]`/`[Unreleased]` sections. Reports drift to
  stdout. With ``--yes`` it also rewrites the drifted files and creates a
  ``chore(release): repair v{ver}`` commit on the current branch.

Both modes refuse to run when the working tree is dirty. Recreate mode also
refuses by default when the branch is ahead of ``origin/<branch>`` (the
caller must opt in with ``--force-allow-pushed`` because the recreate forces
a destructive rewrite that needs a force-push).

## Examples

- ``rrt release repair`` — verify drift, exit 1 if any.
- ``rrt release repair --yes`` — apply fixes in place, commit them.
- ``rrt release repair --from main --yes`` — rewind to main and replay the bump.
- ``rrt release repair --from main --hotfix`` — same as above, no prompt, uses
  ``chore(release): repair v{ver}`` as the commit subject.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from dataclasses import dataclass
from pathlib import Path

from repo_release_tools.changelog import (
    ChangelogFormat,
    clear_unreleased_section,
    detect_changelog_format,
    get_release_section_body,
    get_unreleased_entries,
    insert_generated_section,
)
from repo_release_tools.config import (
    PinTarget,
    RrtConfig,
    VersionGroup,
    VersionTarget,
    find_repo_root,
    format_missing_tool_rrt_guidance,
    is_missing_tool_rrt_error,
    iter_config_files,
    load_or_autodetect_config,
)
from repo_release_tools.ui import VerbosePrinter
from repo_release_tools.version.targets import (
    read_group_current_version,
    read_version_string,
    replace_all_versions_atomic,
    replace_pin_in_file,
    search_pattern,
)
from repo_release_tools.workflow import git

REPAIR_EPILOG = (
    "  $ rrt release repair\n"
    "  $ rrt release repair --yes\n"
    "  $ rrt release repair --from main --yes\n"
    "  $ rrt release repair --from main --hotfix"
)


@dataclass(frozen=True)
class Drift:
    """One mismatch between the declared project version and a tracked target.

    ``kind`` is a short identifier: ``"version_target"``, ``"pin_target"``,
    ``"changelog_missing_section"``, or ``"changelog_unreleased_dirty"``.
    ``path`` is the file's path relative to the repo root.
    """

    kind: str
    path: str
    expected: str
    actual: str


def cmd_release_repair(args: argparse.Namespace) -> int:
    """Verify or recreate the release state for the current branch."""
    verbose: int = getattr(args, "verbose", 0) or 0
    root = find_repo_root(Path.cwd())

    config, group, exit_code = _load_config_and_group(args, root, verbose)
    if config is None or group is None:
        return exit_code

    if not git.working_tree_clean(root):
        VerbosePrinter(verbose=verbose).line(
            "Repair refused: working tree has uncommitted changes. Commit or stash first.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    declared_version = str(read_group_current_version(group))
    changelog_path = group.changelog_file
    fmt = detect_changelog_format(changelog_path.name)
    existing_changelog = (
        changelog_path.read_text(encoding="utf-8") if changelog_path.exists() else ""
    )
    version_body = _resolve_version_body(args, declared_version, existing_changelog, fmt)

    base_ref: str | None = getattr(args, "from_ref", None)
    if base_ref:
        return _recreate(
            args=args,
            config=config,
            group=group,
            root=root,
            declared_version=declared_version,
            fmt=fmt,
            version_body=version_body,
            base_ref=base_ref,
            verbose=verbose,
        )

    return _verify_and_fix(
        args=args,
        config=config,
        group=group,
        root=root,
        declared_version=declared_version,
        fmt=fmt,
        existing_changelog=existing_changelog,
        version_body=version_body,
        verbose=verbose,
    )


# ---------------------------------------------------------------------------
# Recreate mode
# ---------------------------------------------------------------------------


def _recreate(
    *,
    args: argparse.Namespace,
    config: RrtConfig,
    group: VersionGroup,
    root: Path,
    declared_version: str,
    fmt: ChangelogFormat,
    version_body: str | None,
    base_ref: str,
    verbose: int,
) -> int:
    """Rewind the current branch to *base_ref* and replay the bump."""
    p = VerbosePrinter(verbose=verbose)

    if version_body is None:
        p.line(
            f"Repair refused: CHANGELOG.md has no [{declared_version}] section "
            "on this branch. Re-run with --changelog-from PATH.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    if not git.ref_exists(root, base_ref):
        p.line(
            f"Repair refused: base ref {base_ref!r} not found.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    branch = git.current_branch(root)
    if not getattr(args, "force_allow_pushed", False):
        upstream = f"origin/{branch}"
        if git.ref_exists(root, upstream) and git.commits_ahead(root, upstream):
            p.line(
                f"Repair refused: {branch} is ahead of {upstream}. "
                "Re-run with --force-allow-pushed; the new history must be "
                "force-pushed with `git push --force-with-lease`.",
                ok=False,
                stream=sys.stderr,
            )
            return 1

    apply = bool(getattr(args, "yes", False) or getattr(args, "hotfix", False))

    p.ok("rrt release repair (recreate)")
    p.action(f"Branch: {branch}")
    p.action(f"Base ref: {base_ref}")
    p.action(f"Version to restore: {declared_version}")
    p.action(f"Changelog body lines: {len(version_body.splitlines())}")
    p.blank_line()

    if not apply:
        p.warn("Preview only. Re-run with --yes (or --hotfix) to apply.")
        return 1

    if not getattr(args, "no_backup", False):
        backup_ref = _make_backup_ref(root, branch)
        p.ok(f"Backup ref: {backup_ref}")

    git.run(
        ["git", "reset", "--hard", base_ref],
        root,
        dry_run=False,
        label=f"git reset --hard {base_ref}",
    )

    targets_to_rewrite = _targets_needing_rewrite(group.version_targets, declared_version)
    if targets_to_rewrite:
        replace_all_versions_atomic(targets_to_rewrite, declared_version, dry_run=False)

    all_pins = _unique_pins(group, config)
    _rewrite_matching_pins(all_pins, declared_version, config)

    base_changelog = (
        group.changelog_file.read_text(encoding="utf-8") if group.changelog_file.exists() else ""
    )
    rebuilt = _stamp_version_section(base_changelog, declared_version, version_body, fmt)
    group.changelog_file.write_text(rebuilt, encoding="utf-8")

    files_to_stage = _files_to_stage(group, root, all_pins)
    git.run(
        ["git", "add", *dict.fromkeys(files_to_stage)],
        root,
        dry_run=False,
        label="git add",
    )

    commit_msg = _commit_message(args, declared_version, mode="recreate")
    git.run(
        ["git", "commit", "-m", commit_msg],
        root,
        dry_run=False,
        label="git commit",
    )

    p.ok(f"Done. Branch '{branch}' rewritten on top of {base_ref} ({commit_msg!r}).")
    upstream = f"origin/{branch}"
    if git.ref_exists(root, upstream):
        p.warn(
            f"Remote {upstream} exists; push with: `git push --force-with-lease origin {branch}`",
        )
    return 0


# ---------------------------------------------------------------------------
# Verify-and-fix mode
# ---------------------------------------------------------------------------


def _verify_and_fix(
    *,
    args: argparse.Namespace,
    config: RrtConfig,
    group: VersionGroup,
    root: Path,
    declared_version: str,
    fmt: ChangelogFormat,
    existing_changelog: str,
    version_body: str | None,
    verbose: int,
) -> int:
    """Detect drift on the current branch and optionally fix it in place."""
    p = VerbosePrinter(verbose=verbose)

    drifts = _collect_drifts(
        config=config,
        group=group,
        root=root,
        declared_version=declared_version,
        fmt=fmt,
        existing_changelog=existing_changelog,
    )

    p.ok("rrt release repair (verify)")
    p.action(f"Declared version: {declared_version}")
    p.action(f"Drift records: {len(drifts)}")
    p.blank_line()

    if not drifts:
        p.ok("No drift detected.")
        return 0

    p.section("Drift")
    for d in drifts:
        p.line(
            f"  [{d.kind}] {d.path}: expected={d.expected!r} actual={d.actual!r}",
            ok=False,
        )
    p.blank_line()

    apply = bool(getattr(args, "yes", False) or getattr(args, "hotfix", False))
    if not apply:
        p.warn("Preview only. Re-run with --yes to apply fixes.")
        return 1

    # When the changelog is missing the [VERSION] section, applying without
    # a body would silently rewrite the section as empty and drop the
    # intended release notes. Match the recreate-mode safety: refuse unless
    # the caller provided --changelog-from PATH.
    if any(d.kind == "changelog_missing_section" for d in drifts) and version_body is None:
        p.line(
            f"Repair refused: CHANGELOG.md has no [{declared_version}] section "
            "on this branch. Re-run with --changelog-from PATH.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    _apply_drift_fixes(
        drifts=drifts,
        config=config,
        group=group,
        declared_version=declared_version,
        existing_changelog=existing_changelog,
        version_body=version_body,
        fmt=fmt,
    )

    branch = git.current_branch(root)
    files_to_stage = _files_to_stage(group, root, _unique_pins(group, config))
    git.run(
        ["git", "add", *dict.fromkeys(files_to_stage)],
        root,
        dry_run=False,
        label="git add",
    )

    commit_msg = _commit_message(args, declared_version, mode="verify")
    git.run(
        ["git", "commit", "-m", commit_msg],
        root,
        dry_run=False,
        label="git commit",
    )

    p.ok(f"Done. Drift repaired on '{branch}' ({commit_msg!r}).")
    return 0


def _collect_drifts(
    *,
    config: RrtConfig,
    group: VersionGroup,
    root: Path,
    declared_version: str,
    fmt: ChangelogFormat,
    existing_changelog: str,
) -> list[Drift]:
    """Walk targets + changelog, return one Drift per mismatch."""
    drifts: list[Drift] = []

    for target in group.version_targets:
        relative = str(target.path.relative_to(root))
        if not target.path.exists():
            drifts.append(Drift("version_target", relative, declared_version, "<missing>"))
            continue
        try:
            actual = read_version_string(target)
        except (RuntimeError, ValueError):
            drifts.append(Drift("version_target", relative, declared_version, "<unreadable>"))
            continue
        if actual != declared_version:
            drifts.append(Drift("version_target", relative, declared_version, actual))

    for pin in _unique_pins(group, config):
        relative = str(pin.path.relative_to(root))
        if not pin.path.exists():
            drifts.append(Drift("pin_target", relative, declared_version, "<missing>"))
            continue
        text = pin.path.read_text(encoding="utf-8")
        match = search_pattern(text, pin.pattern)
        if match is None:
            continue
        actual = match.group(2)
        if actual != declared_version:
            drifts.append(Drift("pin_target", relative, declared_version, actual))

    changelog_rel = str(group.changelog_file.relative_to(root))
    # Drift is based on what's actually on disk, not the override source.
    on_disk_body = (
        get_release_section_body(existing_changelog, declared_version, fmt)
        if existing_changelog
        else None
    )
    if on_disk_body is None and existing_changelog:
        drifts.append(
            Drift(
                "changelog_missing_section",
                changelog_rel,
                f"[{declared_version}] present",
                "missing",
            )
        )
    if existing_changelog and get_unreleased_entries(existing_changelog, fmt):
        drifts.append(
            Drift(
                "changelog_unreleased_dirty",
                changelog_rel,
                "[Unreleased] empty",
                "<has entries>",
            )
        )

    return drifts


def _apply_drift_fixes(
    *,
    drifts: list[Drift],
    config: RrtConfig,
    group: VersionGroup,
    declared_version: str,
    existing_changelog: str,
    version_body: str | None,
    fmt: ChangelogFormat,
) -> None:
    """Apply every fix implied by *drifts*.

    Version-target drift writes via :func:`replace_all_versions_atomic`,
    pin-target drift via :func:`_rewrite_matching_pins` (which silently
    skips files whose pattern does not match, matching the drift-detection
    rule). Changelog drift is split:

    - ``changelog_missing_section`` requires *version_body*; the caller is
      expected to refuse earlier when no body is available so this function
      only runs when a body exists. The body is stamped via
      :func:`_stamp_version_section`.
    - ``changelog_unreleased_dirty`` calls :func:`clear_unreleased_section`
      to wipe ``[Unreleased]`` without touching the already-promoted
      versioned section below.
    """
    needs_version_rewrite = any(d.kind == "version_target" for d in drifts)
    needs_pin_rewrite = any(d.kind == "pin_target" for d in drifts)
    missing_section = any(d.kind == "changelog_missing_section" for d in drifts)
    unreleased_dirty = any(d.kind == "changelog_unreleased_dirty" for d in drifts)

    if needs_version_rewrite:
        targets_to_rewrite = _targets_needing_rewrite(group.version_targets, declared_version)
        if targets_to_rewrite:
            replace_all_versions_atomic(targets_to_rewrite, declared_version, dry_run=False)

    if needs_pin_rewrite:
        _rewrite_matching_pins(_unique_pins(group, config), declared_version, config)

    if (missing_section or unreleased_dirty) and group.changelog_file.exists():
        content = existing_changelog
        if missing_section:
            assert version_body is not None, (
                "missing_section drift reached _apply_drift_fixes without a body; "
                "the caller must refuse with --changelog-from guidance before this point."
            )
            content = _stamp_version_section(content, declared_version, version_body, fmt)
        if unreleased_dirty:
            content = clear_unreleased_section(content, fmt)
        group.changelog_file.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _resolve_version_body(
    args: argparse.Namespace,
    declared_version: str,
    existing_changelog: str,
    fmt: ChangelogFormat,
) -> str | None:
    """Resolve the [VERSION] body to restore, honoring --changelog-from."""
    override = getattr(args, "changelog_from", None)
    if override:
        override_path = Path(override)
        if not override_path.exists():
            return None
        override_text = override_path.read_text(encoding="utf-8")
        return get_release_section_body(override_text, declared_version, fmt)
    if not existing_changelog:
        return None
    return get_release_section_body(existing_changelog, declared_version, fmt)


def _stamp_version_section(
    base_changelog: str, version: str, body: str, fmt: ChangelogFormat
) -> str:
    """Insert a fresh ``[VERSION] - today`` section into *base_changelog*.

    Reuses :func:`insert_generated_section` so the new block lands either
    just after an existing ``[Unreleased]`` placeholder or, if the document
    has no placeholder, after the title line.
    """
    today = dt.datetime.now(dt.UTC).date().isoformat()
    body = body.strip()
    if fmt == ChangelogFormat.RST:
        header = f"{version} - {today}"
        section = f"{header}\n{'-' * max(len(header), 3)}\n\n{body}\n"
    else:
        section = f"## [{version}] - {today}\n\n{body}\n"
    return insert_generated_section(base_changelog, section, fmt)


def _targets_needing_rewrite(
    targets: list[VersionTarget], declared_version: str
) -> list[VersionTarget]:
    """Return targets whose on-disk version differs from *declared_version*.

    Filtering before calling :func:`replace_all_versions_atomic` matters
    because that helper deliberately raises when a write would be a no-op
    (the bump use case treats "no change" as a bug). In repair we want
    idempotent behavior — only touch what actually drifted.
    """
    drifted: list[VersionTarget] = []
    for target in targets:
        if not target.path.exists():
            continue
        try:
            current = read_version_string(target)
        except (RuntimeError, ValueError):
            drifted.append(target)
            continue
        if current != declared_version:
            drifted.append(target)
    return drifted


def _unique_pins(group: VersionGroup, config: RrtConfig) -> list[PinTarget]:
    """Return pin targets de-duplicated by (path, pattern), preserving order."""
    seen: set[tuple[object, str]] = set()
    result: list[PinTarget] = []
    for pin in (*group.pin_targets, *config.global_pin_targets):
        key = (pin.path, pin.pattern)
        if key in seen:
            continue
        seen.add(key)
        result.append(pin)
    return result


def _rewrite_matching_pins(pins: list[PinTarget], declared_version: str, config: RrtConfig) -> None:
    """Rewrite each pin target whose pattern actually matches.

    Mirrors the no-match policy used by :func:`_collect_drifts`: a pin file
    that exists but does not match its configured pattern is treated as
    non-drift and silently skipped. Without this guard,
    :func:`replace_pin_in_file` would raise ``RuntimeError`` under the
    default ``pin_target_missing="error"`` policy, aborting the entire
    repair even though there is nothing to fix for that pin.
    """
    for pin in pins:
        if not pin.path.exists():
            continue
        text = pin.path.read_text(encoding="utf-8")
        if search_pattern(text, pin.pattern) is None:
            continue
        replace_pin_in_file(
            pin,
            declared_version,
            dry_run=False,
            pin_target_missing=config.pin_target_missing,
        )


def _files_to_stage(group: VersionGroup, root: Path, pins: list[PinTarget]) -> list[str]:
    """Return the file list passed to ``git add`` after the rewrite."""
    files: list[str] = []
    seen: set[str] = set()

    def _add(target: Path) -> None:
        rel = str(target.relative_to(root))
        if rel in seen:
            return
        seen.add(rel)
        files.append(rel)

    for target in group.version_targets:
        if target.path.exists():
            _add(target.path)
    if group.changelog_file.exists():
        _add(group.changelog_file)
    for pin in pins:
        if pin.path.exists():
            _add(pin.path)
    return files


def _make_backup_ref(root: Path, branch: str) -> str:
    """Write a backup ref pointing at HEAD and return its name."""
    timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%S")
    safe_branch = branch.replace("/", "-")
    ref_name = f"refs/heads/repair/backup/{safe_branch}-{timestamp}"
    git.run(
        ["git", "update-ref", ref_name, "HEAD"],
        root,
        dry_run=False,
        label="backup ref",
    )
    return ref_name


def _commit_message(args: argparse.Namespace, version: str, *, mode: str) -> str:
    """Choose the commit subject for the repair commit."""
    if getattr(args, "hotfix", False):
        return f"chore(release): repair v{version}"
    if mode == "recreate":
        return f"chore: bump version to v{version}"
    return f"chore(release): repair v{version}"


# ---------------------------------------------------------------------------
# Config / group resolution boilerplate (mirrors release_notes.py / bump.py)
# ---------------------------------------------------------------------------


def _load_config_and_group(
    args: argparse.Namespace, root: Path, verbose: int
) -> tuple[RrtConfig | None, VersionGroup | None, int]:
    """Resolve the rrt config and the requested version group, or print why not."""
    p = VerbosePrinter(verbose=verbose)
    try:
        config = load_or_autodetect_config(root)
    except FileNotFoundError:
        p.line(
            format_missing_tool_rrt_guidance(root, iter_config_files(root)),
            ok=False,
            stream=sys.stderr,
        )
        return None, None, 1
    except ValueError as exc:
        if is_missing_tool_rrt_error(exc):
            p.line("No [tool.rrt] configuration found.", ok=False, stream=sys.stderr)
            p.line(
                format_missing_tool_rrt_guidance(root, iter_config_files(root)),
                ok=False,
                stream=sys.stderr,
            )
            return None, None, 1
        p.line(str(exc), ok=False, stream=sys.stderr)
        return None, None, 1
    except RuntimeError as exc:
        p.line(str(exc), ok=False, stream=sys.stderr)
        return None, None, 1

    requested_group = getattr(args, "group", None)
    if requested_group is None and len(config.version_groups) > 1:
        p.line(
            "Repair refused: multiple version groups configured. Pass --group NAME.",
            ok=False,
            stream=sys.stderr,
        )
        return None, None, 1

    try:
        group = config.resolve_group(requested_group)
    except ValueError as exc:
        p.line(str(exc), ok=False, stream=sys.stderr)
        return None, None, 1

    if not _verify_target_compatibility(group):
        p.line(
            "Repair refused: no version targets configured for the resolved group.",
            ok=False,
            stream=sys.stderr,
        )
        return None, None, 1

    return config, group, 0


def _verify_target_compatibility(group: VersionGroup) -> bool:
    """Return True when the group can be repaired (has at least one target)."""
    return bool(group.version_targets)


# ---------------------------------------------------------------------------
# Subparser registration
# ---------------------------------------------------------------------------


def register_subcommand(
    release_subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Register `repair` under the existing release subparser group."""
    parser = release_subparsers.add_parser(
        "repair",
        help="Fix drift or recreate a release branch cleanly.",
        description=(
            "Verify (and optionally fix) version target / pin target / "
            "changelog drift on the current branch, or recreate the branch "
            "cleanly from a base ref while preserving the declared version "
            "and its [VERSION] changelog body."
        ),
        epilog=REPAIR_EPILOG,
    )
    parser.add_argument(
        "--from",
        dest="from_ref",
        default=None,
        metavar="BASE",
        help=(
            "Recreate mode: rewind the current branch to BASE (commit, "
            "branch, or tag) and replay the version bump. Without this flag "
            "the command runs in verify-and-fix mode."
        ),
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        default=False,
        help="Required to apply changes; otherwise the command only previews.",
    )
    parser.add_argument(
        "--hotfix",
        action="store_true",
        default=False,
        help=(
            "Implies --yes and tags the commit as `chore(release): repair "
            "v{ver}` so hotfix recoveries are distinguishable from regular "
            "bumps."
        ),
    )
    parser.add_argument(
        "--changelog-from",
        dest="changelog_from",
        default=None,
        metavar="PATH",
        help=(
            "Read the [VERSION] body from PATH instead of the current "
            "branch's CHANGELOG.md. Useful when the polluted HEAD has "
            "lost the section."
        ),
    )
    parser.add_argument(
        "--force-allow-pushed",
        action="store_true",
        default=False,
        help=(
            "Allow recreate when the branch is ahead of origin/<branch>. "
            "The new history must then be force-pushed with "
            "`git push --force-with-lease`."
        ),
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        default=False,
        help=(
            "Skip the `repair/backup/<branch>-<ts>` ref that is otherwise "
            "written before any destructive operation."
        ),
    )
    parser.add_argument(
        "--group",
        default=None,
        metavar="GROUP",
        help="Pick the version group when multiple are configured.",
    )
    parser.set_defaults(handler=cmd_release_repair)
