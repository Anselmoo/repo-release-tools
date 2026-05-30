"""Content-addressed integrity tracking for generated repository artifacts.

## Overview

`rrt artifacts` provides a general-purpose fingerprinting mechanism for any
set of generated files in the repository. It hashes every file matched by
configured glob patterns, writes the hashes to `.rrt/artifacts.lock.toml`,
and can verify that freshly-generated artifacts still match the committed
fingerprints.

This closes the trust loop for generated assets: the code that produces them
is version-controlled, the expected hashes are committed, and CI re-generates
and re-verifies before any artifact reaches users.

## Configuration

Add `[[tool.rrt.artifact_targets]]` entries to `pyproject.toml` (or `.rrt.toml`):

```toml
[[tool.rrt.artifact_targets]]
path = "src/repo_release_tools/assets/badges/*.svg"
description = "Platform badge SVG files"

[[tool.rrt.artifact_targets]]
path = "docs/assets/banner-*.png"
description = "Banner PNG renders"
```

## Subcommands

- `--snapshot` — hash all configured targets, write `.rrt/artifacts.lock.toml`
- `--check` — verify hashes match (advisory, exits 0 on mismatch by default)
- `--check --strict` — exits 1 on any hash mismatch (for CI gates)
- `--list` — display all tracked artifacts and their current hash status

## Examples

```bash
rrt artifacts --snapshot
rrt artifacts --check
rrt artifacts --check --strict
rrt artifacts --list
```
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from repo_release_tools.config import (
    RrtConfig,
    find_repo_root,
    load_or_autodetect_config,
)
from repo_release_tools.state import (
    artifacts_lock_is_current,
    artifacts_lock_path,
    build_artifacts_lock,
    hash_file,
    write_lock,
)
from repo_release_tools.ui import (
    DryRunPrinter,
    rule,
    terminal_width,
)

SOURCE_OWNED_TOPIC_DOCS: tuple[tuple[str, str], ...] = (("artifacts", __doc__ or ""),)
ARTIFACTS_EPILOG = (
    "  $ rrt artifacts --snapshot\n  $ rrt artifacts --check --strict\n  $ rrt artifacts --list"
)


def _target_dicts(config: RrtConfig) -> list[dict[str, str]]:
    """Convert ArtifactTarget objects to the dict format expected by state functions."""
    return [{"path": t.path, "description": t.description} for t in config.artifact_targets]


def cmd_artifacts(args: argparse.Namespace) -> int:
    """Run artifact integrity check, snapshot, or list."""
    root = find_repo_root(Path.cwd())
    do_snapshot: bool = getattr(args, "snapshot", False)
    do_check: bool = getattr(args, "check", False)
    do_list: bool = getattr(args, "list", False)
    strict: bool = getattr(args, "strict", False)

    p = DryRunPrinter(dry_run=False)

    try:
        config = load_or_autodetect_config(root)
    except Exception as exc:
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1

    targets = _target_dicts(config)
    lock_path = artifacts_lock_path(root)

    if not targets:
        p.warn("No artifact_targets configured in [tool.rrt]. Nothing to track.")
        return 0

    if do_snapshot:
        data = build_artifacts_lock(targets, root)
        write_lock(lock_path, data)
        file_count = len(data.get("files", {}))
        p.line(
            f"Artifact snapshot written: {file_count} file(s) → {lock_path.relative_to(root)}",
            ok=True,
        )
        return 0

    if do_check:
        is_current, drift_msgs = artifacts_lock_is_current(lock_path, targets, root)
        if is_current:
            p.line("All artifact hashes verified — no drift detected.", ok=True)
            return 0
        for msg in drift_msgs:
            if strict:
                p.line(msg, ok=False, stream=sys.stderr)
            else:
                p.warn(msg)
        if strict:
            p.line(
                f"{len(drift_msgs)} artifact integrity issue(s) found. Run --snapshot to update.",
                ok=False,
                stream=sys.stderr,
            )
            return 1
        p.blank_line()
        p.warn("⊙ [advisory] Artifact drift detected — run rrt artifacts --snapshot to update.")
        return 0

    if do_list:
        _print_artifact_list(targets, root, lock_path)
        return 0

    # Default: show a brief status summary
    is_current, drift_msgs = artifacts_lock_is_current(lock_path, targets, root)
    if is_current:
        p.line("All artifact hashes verified — no drift detected.", ok=True)
    else:
        for msg in drift_msgs:
            p.warn(msg)
    return 0


def _print_artifact_list(
    targets: list[dict[str, str]],
    root: Path,
    lock_path: Path,
) -> None:
    """Print a status table of all tracked artifacts."""
    from repo_release_tools.state import read_lock

    locked = read_lock(lock_path).get("files", {})
    width = terminal_width()

    p = DryRunPrinter(dry_run=False)
    p.line(f"[ARTIFACTS] Lock: {lock_path.relative_to(root)}", ok=True)
    p.blank_line()

    for target in targets:
        pattern = target["path"]
        description = target.get("description", "")
        matched = sorted(root.glob(pattern))
        if description:
            p.line(rule(description, width=width))
        else:
            p.line(rule(pattern, width=width))

        if not matched:
            p.warn(f"no files matched: {pattern}")
            continue

        for path in matched:
            if not path.is_file():
                continue
            rel = str(path.relative_to(root))
            current_hash = hash_file(path)
            locked_entry = locked.get(rel)
            if locked_entry is None:
                p.line(f"{rel:<60}  NOT IN LOCK", ok=False)
            elif current_hash == locked_entry.get("hash", ""):
                p.line(f"{rel:<60}  ✓", ok=True)
            else:
                p.line(f"{rel:<60}  MISMATCH", ok=False)


def register(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Register the artifacts subcommand."""
    parser = subparsers.add_parser(
        "artifacts",
        help="Content-addressed integrity tracking for generated artifacts.",
        description=(
            "Hash and verify generated files against a committed fingerprint lock.\n"
            "Run --snapshot to record current hashes; --check to verify them in CI."
        ),
        epilog=ARTIFACTS_EPILOG,
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--snapshot",
        action="store_true",
        default=False,
        help="Hash all configured artifact_targets and write .rrt/artifacts.lock.toml.",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        default=False,
        help="Verify artifact hashes match the committed lock. Advisory by default.",
    )
    mode.add_argument(
        "--list",
        action="store_true",
        default=False,
        help="Display all tracked artifacts and their current hash status.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="With --check: exit 1 on any hash mismatch (for CI gates).",
    )
    parser.set_defaults(handler=cmd_artifacts)
