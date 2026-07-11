"""Lockfile management and drift detection for `rrt docs map`.

Stores a per-directory hash of the generated content block in a sibling lockfile
(default `.rrt/docs_map.lock.toml`, configurable via `MapConfig.lock_file`). The
file lives separately from the existing `docs.lock.toml` so source-doc drift
(`rrt docs check`) and map drift remain independent.

Lockfile schema::

    [meta]
    generated_at = "2026-06-13T20:00:00+00:00"

    [entries."src/repo_release_tools/commands"]
    hash = "sha256:abc..."
    updated_at = "2026-06-13T20:00:00+00:00"
"""

from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from repo_release_tools.commands.docs_map import build_full_block, iter_target_directories
from repo_release_tools.state import docs_map_lock_path

if TYPE_CHECKING:
    from repo_release_tools.config import MapConfig


def compute_block_hash(content: str) -> str:
    """Return ``sha256:<hex>`` for the given content string."""
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


@dataclass(frozen=True)
class DriftItem:
    """One drift between desired content and the lockfile."""

    kind: str  # "stale" | "missing-entry" | "orphan-entry"
    directory: str  # repo-relative posix path
    expected_hash: str | None
    actual_hash: str | None


def read_lockfile(path: Path) -> dict[str, str]:
    """Return a dict of ``directory → hash`` from *path*; empty dict if absent."""
    if not path.exists():
        return {}
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    entries = raw.get("entries", {})
    if not isinstance(entries, dict):
        raise ValueError(f"{path}: 'entries' must be a table")
    out: dict[str, str] = {}
    for key, value in entries.items():
        if not isinstance(value, dict):
            raise ValueError(f"{path}: 'entries.{key}' must be a table")
        h = value.get("hash")
        if not isinstance(h, str) or not h:
            raise ValueError(f"{path}: 'entries.{key}.hash' must be a non-empty string")
        out[key] = h
    return out


def write_lockfile(path: Path, entries: dict[str, str]) -> None:
    """Write a lockfile recording one hash per directory at *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    lines = ["[meta]", f'generated_at = "{now}"', ""]
    for directory in sorted(entries):
        lines.append(f'[entries."{directory}"]')
        lines.append(f'hash = "{entries[directory]}"')
        lines.append(f'updated_at = "{now}"')
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def compute_desired_hashes(config: MapConfig, repo_root: Path) -> dict[str, str]:
    """Return ``directory-relpath → hash`` for every target directory."""
    out: dict[str, str] = {}
    for directory in iter_target_directories(config, repo_root):
        block = build_full_block(directory, config, repo_root)
        rel = directory.relative_to(repo_root).as_posix()
        out[rel] = compute_block_hash(block)
    return out


def detect_drift(config: MapConfig, repo_root: Path) -> list[DriftItem]:
    """Compare desired hashes against the lockfile; return drift items."""
    lockfile_path = docs_map_lock_path(repo_root, config.lock_file)
    recorded = read_lockfile(lockfile_path)
    desired = compute_desired_hashes(config, repo_root)

    drift: list[DriftItem] = []
    for rel, expected in desired.items():
        actual = recorded.get(rel)
        if actual is None:
            drift.append(
                DriftItem(
                    kind="missing-entry",
                    directory=rel,
                    expected_hash=expected,
                    actual_hash=None,
                )
            )
        elif actual != expected:
            drift.append(
                DriftItem(
                    kind="stale",
                    directory=rel,
                    expected_hash=expected,
                    actual_hash=actual,
                )
            )
    for rel, actual in recorded.items():
        if rel not in desired:
            drift.append(
                DriftItem(
                    kind="orphan-entry",
                    directory=rel,
                    expected_hash=None,
                    actual_hash=actual,
                )
            )
    drift.sort(key=lambda d: (d.kind, d.directory))
    return drift


def refresh_lockfile(config: MapConfig, repo_root: Path) -> Path:
    """Write the lockfile to match the current desired hashes; return the path."""
    lockfile_path = repo_root / config.lock_file
    write_lockfile(lockfile_path, compute_desired_hashes(config, repo_root))
    return lockfile_path
