"""State management for rrt — owns the .rrt/ directory and lock files."""

from __future__ import annotations

import hashlib
import re
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from repo_release_tools import __version__
from repo_release_tools.ui import GLYPHS

_RRT_DIR = ".rrt"
_DOCS_LOCK_NAME = "docs.lock.toml"
_HEALTH_LOCK_NAME = "health.lock.toml"
_TREE_LOCK_NAME = "tree.lock.toml"
_ARTIFACTS_LOCK_NAME = "artifacts.lock.toml"
_DRIFT_LOCK_NAME = "drift.lock.toml"
_DOCS_MAP_LOCK_NAME = "docs_map.lock.toml"
_TREE_MANIFEST_NAME = "tree.manifest.json"
_TREE_MANIFEST_GZ_NAME = "tree.manifest.json.gz"

#: Public re-export of the bare lock filenames, for call sites that need the
#: name itself (e.g. an argparse ``help=`` string or a CLI default) rather
#: than a resolved :class:`~pathlib.Path`.
DOCS_LOCK_NAME = _DOCS_LOCK_NAME
HEALTH_LOCK_NAME = _HEALTH_LOCK_NAME
TREE_LOCK_NAME = _TREE_LOCK_NAME
ARTIFACTS_LOCK_NAME = _ARTIFACTS_LOCK_NAME
DRIFT_LOCK_NAME = _DRIFT_LOCK_NAME
DOCS_MAP_LOCK_NAME = _DOCS_MAP_LOCK_NAME
TREE_MANIFEST_NAME = _TREE_MANIFEST_NAME
TREE_MANIFEST_GZ_NAME = _TREE_MANIFEST_GZ_NAME

#: Public re-export of each lock's default ``.rrt/``-relative path string, for
#: call sites that store the *default value* of a configurable lock-file
#: field (e.g. a dataclass field default) rather than resolving an absolute
#: path against a repo root.
DOCS_LOCK_DEFAULT = f"{_RRT_DIR}/{_DOCS_LOCK_NAME}"
HEALTH_LOCK_DEFAULT = f"{_RRT_DIR}/{_HEALTH_LOCK_NAME}"
TREE_LOCK_DEFAULT = f"{_RRT_DIR}/{_TREE_LOCK_NAME}"
ARTIFACTS_LOCK_DEFAULT = f"{_RRT_DIR}/{_ARTIFACTS_LOCK_NAME}"
DRIFT_LOCK_DEFAULT = f"{_RRT_DIR}/{_DRIFT_LOCK_NAME}"
DOCS_MAP_LOCK_DEFAULT = f"{_RRT_DIR}/{_DOCS_MAP_LOCK_NAME}"


def rrt_dir(root: Path) -> Path:
    """Return the .rrt/ state directory path (does not create it)."""
    return root / _RRT_DIR


def docs_lock_path(root: Path, lock_file: str = _DOCS_LOCK_NAME) -> Path:
    """Return the path to the docs lockfile."""
    p = Path(lock_file)
    if p.is_absolute():
        return p
    return root / p if p.parts[0] == _RRT_DIR else root / _RRT_DIR / p


def health_lock_path(root: Path) -> Path:
    """Return the path to the health snapshot lockfile."""
    return root / _RRT_DIR / _HEALTH_LOCK_NAME


def tree_lock_path(root: Path) -> Path:
    """Return the path to the tree snapshot lockfile."""
    return root / _RRT_DIR / _TREE_LOCK_NAME


def artifacts_lock_path(root: Path) -> Path:
    """Return the path to the artifact integrity lockfile."""
    return root / _RRT_DIR / _ARTIFACTS_LOCK_NAME


def drift_lock_path(root: Path) -> Path:
    """Return the path to the source-drift lockfile."""
    return root / _RRT_DIR / _DRIFT_LOCK_NAME


def docs_map_lock_path(root: Path, lock_file: str = _DOCS_MAP_LOCK_NAME) -> Path:
    """Return the path to the per-directory docs-map lockfile.

    Mirrors :func:`docs_lock_path`'s handling of a configurable, possibly
    already-``.rrt/``-relative *lock_file* value.
    """
    p = Path(lock_file)
    if p.is_absolute():
        return p
    return root / p if p.parts[0] == _RRT_DIR else root / _RRT_DIR / p


def tree_manifest_path(root: Path) -> Path:
    """Return the path to the uncompressed tree manifest."""
    return root / _RRT_DIR / _TREE_MANIFEST_NAME


def tree_manifest_gz_path(root: Path) -> Path:
    """Return the path to the gzip-compressed tree manifest."""
    return root / _RRT_DIR / _TREE_MANIFEST_GZ_NAME


def hash_content(content: str) -> str:
    """Return a stable sha256 hex digest prefixed with 'sha256:'."""
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def now_utc() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(tz=UTC).isoformat(timespec="seconds")


def _short_hash(h: str) -> str:
    """Return an 8-character short prefix from a hash string like 'sha256:...'.

    Returns '?' on error or when the input is falsy. *h* ultimately comes
    from lockfile TOML data, so this guards against a malformed value whose
    ``__bool__``/``__eq__`` (or similar) raises rather than a plain string
    operation failing — see test_state_exceptions.py.
    """
    try:
        if not h:
            return "?"
        body = h.split(":", 1)[1] if ":" in h else h
        return body[:8]
    except Exception:
        return "?"


# ---------------------------------------------------------------------------
# Lock read / write
# ---------------------------------------------------------------------------


def read_lock(lock_path: Path) -> dict[str, Any]:
    """Read and parse a TOML lockfile; return an empty dict if missing."""
    if not lock_path.exists():
        return {}
    with lock_path.open("rb") as fh:
        return tomllib.load(fh)


def write_lock(lock_path: Path, data: dict[str, Any]) -> None:
    """Serialise *data* as TOML and write it to *lock_path*, creating dirs."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(_dict_to_toml(data), encoding="utf-8")


def build_lock(sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Construct a complete lock dict from a list of source entry dicts."""
    ts = now_utc()
    result: dict[str, Any] = {
        "meta": {
            "generated_at": ts,
            "rrt_version": __version__,
        },
        "sources": {},
    }
    for entry in sources:
        key = entry["source_file"]
        result["sources"][key] = {
            "hash": entry["hash"],
            "symbols": entry.get("symbols", []),
            "lang": entry["lang"],
            "updated_at": ts,
        }
    return result


def lock_is_current(lock_path: Path, sources: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    """Compare current source hashes against the lockfile.

    Returns (is_current, list_of_drift_messages).
    """
    current = read_lock(lock_path)
    locked_sources: dict[str, Any] = current.get("sources", {})

    drifted: list[str] = []
    seen_keys: set[str] = set()

    for entry in sources:
        key = entry["source_file"]
        seen_keys.add(key)
        locked = locked_sources.get(key)
        if locked is None:
            drifted.append(f"New source not in lockfile: {key}")
        elif locked.get("hash") != entry["hash"]:
            drifted.append(f"Hash mismatch for {key} (lockfile is stale)")

    for key in locked_sources:
        if key not in seen_keys:
            drifted.append(f"Source removed but still in lockfile: {key}")

    return (not drifted, drifted)


def upsert_health_lock_checks(lock_path: Path, checks: list[dict[str, Any]]) -> None:
    """Merge *checks* into the existing health lock, creating it if absent.

    Existing check entries for other subsystems are preserved; only keys
    present in *checks* are updated.
    """
    existing = read_lock(lock_path)
    ts = now_utc()
    if "meta" not in existing:
        existing["meta"] = {"generated_at": ts, "rrt_version": __version__}
    else:
        existing["meta"]["generated_at"] = ts
        existing["meta"]["rrt_version"] = __version__
    if "checks" not in existing:
        existing["checks"] = {}
    for entry in checks:
        existing["checks"][entry["name"]] = {
            "status": entry["status"],
            "message": entry.get("message", ""),
            "updated_at": ts,
        }
    write_lock(lock_path, existing)


def build_health_lock(checks: list[dict[str, Any]]) -> dict[str, Any]:
    """Construct a health snapshot lock dict from a list of check result dicts.

    Each entry must have ``name`` (str) and ``status`` (``"ok"``, ``"obsolete"``,
    ``"warning"``, or ``"error"``).  An optional ``message`` field is preserved verbatim.
    """
    ts = now_utc()
    result: dict[str, Any] = {
        "meta": {
            "generated_at": ts,
            "rrt_version": __version__,
        },
        "checks": {},
    }
    for entry in checks:
        name = entry["name"]
        result["checks"][name] = {
            "status": entry["status"],
            "message": entry.get("message", ""),
            "updated_at": ts,
        }
    return result


def health_lock_is_current(
    lock_path: Path,
    checks: list[dict[str, Any]],
) -> tuple[bool, list[str]]:
    """Compare current check statuses against the health lockfile.

    Only regressions are reported (ok/obsolete→warning/error, or new check added).
    Improvements (warning→ok/obsolete) are silently accepted.

    Returns ``(is_current, list_of_regression_messages)``.
    """
    current = read_lock(lock_path)
    locked_checks: dict[str, Any] = current.get("checks", {})

    _SEVERITY = {"ok": 0, "obsolete": 0, "warning": 1, "error": 2}

    regressions: list[str] = []
    for entry in checks:
        name = entry["name"]
        new_status = entry["status"]
        locked = locked_checks.get(name)
        if locked is None:
            regressions.append(f"New check not in health snapshot: {name} ({new_status})")
        else:
            old_severity = _SEVERITY.get(locked.get("status", "ok"), 0)
            new_severity = _SEVERITY.get(new_status, 0)
            if new_severity > old_severity:
                regressions.append(
                    f"Health regression for {name}: {locked.get('status', '?')} → {new_status}"
                )

    return (not regressions, regressions)


def build_tree_lock(tree_meta: dict[str, Any]) -> dict[str, Any]:
    """Construct a tree snapshot lock dict from tree metadata.

    *tree_meta* must contain ``entry_count`` (int) and ``tree_hash`` (str).
    An optional ``ignored_count`` (int) is preserved when present.
    """
    ts = now_utc()
    snapshot: dict[str, Any] = {
        "entry_count": tree_meta["entry_count"],
        "tree_hash": tree_meta["tree_hash"],
        "updated_at": ts,
    }
    if "ignored_count" in tree_meta:
        snapshot["ignored_count"] = tree_meta["ignored_count"]
    if "phantom_empty_dirs" in tree_meta:
        snapshot["phantom_empty_dirs"] = tree_meta["phantom_empty_dirs"]
    return {
        "meta": {
            "generated_at": ts,
            "rrt_version": __version__,
        },
        "snapshot": snapshot,
    }


def tree_lock_is_current(
    lock_path: Path,
    tree_meta: dict[str, Any],
) -> tuple[bool, list[str]]:
    """Compare current tree metadata against the tree lockfile.

    Drifts when the ``tree_hash`` differs from the snapshot.

    Returns ``(is_current, list_of_drift_messages)``.
    """
    current = read_lock(lock_path)
    locked_snapshot: dict[str, Any] = current.get("snapshot", {})

    drifted: list[str] = []
    locked_hash = locked_snapshot.get("tree_hash")
    if locked_hash is None:
        drifted.append("Tree snapshot not found in lockfile")
        return (not drifted, drifted)

    # If the snapshot hash differs from the current tree hash, build a
    # multi-line bulleted diagnostic that shows counts and both hashes.
    current_hash = tree_meta.get("tree_hash", "?")
    if locked_hash != current_hash:
        # Provide a clearer diagnostic when the snapshot hash differs.
        locked_count = locked_snapshot.get("entry_count", "?")
        new_count = tree_meta.get("entry_count", "?")

        # Compare raw counts when available (integers). Fall back to
        # conservative equality if types differ. This is diagnostic-message
        # formatting, not the drift decision itself (already made above) —
        # a malformed lock value (e.g. an object with a broken __eq__) must
        # not prevent the drift from being reported, so the broad guard here
        # is intentional; see test_state_exceptions.py for the pinned cases.
        counts_equal = False
        try:
            counts_equal = locked_snapshot.get("entry_count") == tree_meta.get("entry_count")
        except Exception:
            counts_equal = False

        header = "Tree structure changed since snapshot:"
        # Compute numeric delta when both counts are integers; otherwise show '?'.
        delta: str
        try:
            if isinstance(new_count, int) and isinstance(locked_count, int):
                delta = str(new_count - locked_count)
            else:
                # attempt to coerce numeric strings
                delta = (
                    str(int(new_count) - int(locked_count))
                    if (
                        isinstance(new_count, str)
                        and new_count.isdigit()
                        and isinstance(locked_count, str)
                        and locked_count.isdigit()
                    )
                    else "?"
                )
        except Exception:
            delta = "?"

        # Short prefixes of hashes for quick comparison (short-first display)
        locked_short = _short_hash(locked_hash) if locked_hash else "?"
        current_short = _short_hash(current_hash) if current_hash else "?"

        # Signed delta for human readers ("+N" when the working tree grew).
        signed_delta = delta
        try:
            if isinstance(new_count, int) and isinstance(locked_count, int):
                diff = new_count - locked_count
                signed_delta = f"+{diff}" if diff > 0 else str(diff)
        except Exception:
            signed_delta = delta

        # Choose a directional glyph for the delta when applicable. The
        # GLYPHS registry handles ASCII fallbacks for legacy terminals.
        glyph = ""
        try:
            if signed_delta.startswith("+"):
                glyph = f" {GLYPHS.arrow.up}"
            elif signed_delta.startswith("-"):
                glyph = f" {GLYPHS.arrow.down}"
        except Exception:
            glyph = ""

        # Present counts as 'was -> now (Δ ±N)' which reads naturally.
        message_lines = [
            header,
            f"  - entry count: was {locked_count} → now {new_count} (Δ {signed_delta}{glyph})",
            f"  - snapshot hash: {locked_short} ({locked_hash})",
            f"  - current hash: {current_short} ({current_hash})",
        ]
        if counts_equal:
            # When counts are equal but hashes differ, offer a remediation hint.
            message_lines.append("  - suggestion: run 'rrt tree --snapshot' to refresh")

        drifted.append("\n".join(message_lines))

    return (not drifted, drifted)


def hash_file(path: Path) -> str:
    """Return a stable sha256 hex digest of *path*'s content, prefixed with 'sha256:'."""
    h = hashlib.sha256(path.read_bytes())
    return f"sha256:{h.hexdigest()}"


def _compute_inputs_hash(inputs_globs: list[str], repo_root: Path) -> str | None:
    """Return a combined SHA-256 hash of all files matching *inputs_globs*.

    Files are sorted by path for determinism. Returns ``None`` when no globs
    are provided or no files match — callers should omit the key rather than
    storing ``None``.
    """
    if not inputs_globs:
        return None
    matched: list[Path] = []
    for pattern in inputs_globs:
        matched.extend(repo_root.glob(pattern))
    files = sorted(set(f for f in matched if f.is_file()))
    if not files:
        return None
    combined = hashlib.sha256()
    for f in files:
        # Include relative path as a boundary marker so that different file
        # splits with identical concatenated content produce different hashes
        # (e.g. files ["ab","c"] vs ["a","bc"] would otherwise collide).
        combined.update(str(f.relative_to(repo_root)).encode())
        combined.update(b"\x00")
        combined.update(f.read_bytes())
        combined.update(b"\x00")
    return f"sha256:{combined.hexdigest()}"


def build_artifacts_lock(
    artifact_targets: list[dict[str, Any]],
    repo_root: Path,
) -> dict[str, Any]:
    """Construct an artifact integrity lock from configured target globs.

    Each entry in *artifact_targets* must have a ``path`` key (glob pattern
    relative to *repo_root*) and an optional ``description`` string.  Every
    file matched by the glob is hashed with SHA-256 and recorded.

    When a target includes an ``inputs`` list of glob patterns, the combined
    hash of all matching input files is stored in a ``[targets]`` section
    keyed by the target's ``path``.  This enables ``--check`` to detect
    source-vs-output staleness.
    """
    ts = now_utc()
    result: dict[str, Any] = {
        "meta": {
            "generated_at": ts,
            "rrt_version": __version__,
        },
        "files": {},
    }
    targets_section: dict[str, Any] = {}
    for target in artifact_targets:
        pattern = str(target.get("path", ""))
        description = str(target.get("description", ""))
        inputs_globs: list[str] = target.get("inputs", [])  # type: ignore[assignment]
        inputs_hash = _compute_inputs_hash(inputs_globs, repo_root)
        if inputs_hash is not None:
            targets_section[pattern] = {"inputs_hash": inputs_hash}
        for matched in sorted(repo_root.glob(pattern)):
            if not matched.is_file():
                continue
            rel = str(matched.relative_to(repo_root))
            result["files"][rel] = {
                "hash": hash_file(matched),
                "size": matched.stat().st_size,
                "description": description,
                "updated_at": ts,
            }
    if targets_section:
        result["targets"] = targets_section
    return result


def artifacts_lock_is_current(
    lock_path: Path,
    artifact_targets: list[dict[str, Any]],
    repo_root: Path,
) -> tuple[bool, list[str]]:
    """Compare current artifact hashes against the artifacts lockfile.

    Drifts on: hash mismatch, file tracked in lock but now missing, file
    matched by a target but not yet in the lock, or input files changed
    since the lock was written.

    Returns ``(is_current, list_of_drift_messages)``.
    """
    current = read_lock(lock_path)
    locked_files: dict[str, Any] = current.get("files", {})
    locked_targets: dict[str, Any] = current.get("targets", {})

    drifted: list[str] = []
    seen_paths: set[str] = set()

    for target in artifact_targets:
        pattern = str(target.get("path", ""))
        inputs_globs: list[str] = target.get("inputs", [])  # type: ignore[assignment]

        # Input-staleness check
        if inputs_globs:
            current_inputs_hash = _compute_inputs_hash(inputs_globs, repo_root)
            stored = locked_targets.get(pattern, {})
            stored_inputs_hash = stored.get("inputs_hash") if stored else None
            if current_inputs_hash is not None and stored_inputs_hash is None:
                drifted.append(
                    f"Input tracking configured but no input hashes in lock"
                    f" (target: {pattern}) — run rrt artifacts --snapshot to initialize"
                )
            elif current_inputs_hash != stored_inputs_hash:
                drifted.append(
                    f"Input files changed since last snapshot"
                    f" (target: {pattern}) — run rrt artifacts --regenerate or --snapshot"
                )

        for matched in sorted(repo_root.glob(pattern)):
            if not matched.is_file():
                continue
            rel = str(matched.relative_to(repo_root))
            seen_paths.add(rel)
            locked = locked_files.get(rel)
            if locked is None:
                drifted.append(f"Artifact not in lock (run --snapshot): {rel}")
            else:
                current_hash = hash_file(matched)
                if current_hash != locked.get("hash", ""):
                    drifted.append(f"Artifact hash mismatch (content changed): {rel}")

    for rel in locked_files:
        if rel not in seen_paths and not (repo_root / rel).exists():
            drifted.append(f"Artifact in lock but file missing: {rel}")

    return (not drifted, drifted)


# ---------------------------------------------------------------------------
# Minimal TOML serialiser (stdlib only, no tomli-w dependency)
# ---------------------------------------------------------------------------


def _toml_value(v: Any) -> str:
    match v:
        case bool():
            return "true" if v else "false"
        case int():
            return str(v)
        case float():
            return repr(v)
        case str():
            escaped = v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            return f'"{escaped}"'
        case list():
            items = ", ".join(_toml_value(i) for i in v)
            return f"[{items}]"
        case _:
            raise TypeError(f"Unsupported TOML value type: {type(v)!r}")


def _dict_to_toml(d: dict[str, Any], _prefix: str = "") -> str:
    """Minimal two-level TOML serialiser sufficient for the lock schema."""
    lines: list[str] = []
    tables: list[tuple[str, dict[str, Any]]] = []

    for k, v in d.items():
        if isinstance(v, dict):
            tables.append((k, v))
        else:
            lines.append(f"{k} = {_toml_value(v)}")

    out = "\n".join(lines)

    for table_key, table_val in tables:
        full_key = f"{_prefix}{table_key}" if _prefix else table_key
        # Nested tables (e.g. sources."path/to/file.py")
        nested_tables: list[tuple[str, dict[str, Any]]] = []
        scalars: list[str] = []
        for k, v in table_val.items():
            if isinstance(v, dict):
                nested_tables.append((k, v))
            else:
                scalars.append(f"{k} = {_toml_value(v)}")
        if nested_tables:
            # sources."path" style
            for nt_key, nt_val in nested_tables:
                escaped_key = nt_key.replace("\\", "\\\\").replace('"', '\\"')
                quoted_key = (
                    f'"{escaped_key}"' if not re.fullmatch(r"[A-Za-z0-9_-]+", nt_key) else nt_key
                )
                header = f"[{full_key}.{quoted_key}]"
                if out:
                    out += "\n\n"
                out += header + "\n"
                out += "\n".join(f"{k} = {_toml_value(v)}" for k, v in nt_val.items())
        else:
            header = f"[{full_key}]"
            if out:
                out += "\n\n"
            out += header + "\n"
            out += "\n".join(scalars)

    return out.rstrip() + "\n"
