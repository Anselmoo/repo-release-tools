"""State management for rrt — owns the .rrt/ directory and lock files."""

from __future__ import annotations

import hashlib
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from repo_release_tools import __version__

_RRT_DIR = ".rrt"
_DOCS_LOCK_NAME = "docs.lock.toml"


def rrt_dir(root: Path) -> Path:
    """Return the .rrt/ state directory path (does not create it)."""
    return root / _RRT_DIR


def docs_lock_path(root: Path, lock_file: str = _DOCS_LOCK_NAME) -> Path:
    """Return the path to the docs lockfile."""
    p = Path(lock_file)
    if p.is_absolute():
        return p
    if p.parts[0] == _RRT_DIR:
        return root / p
    return root / _RRT_DIR / p


def hash_content(content: str) -> str:
    """Return a stable sha256 hex digest prefixed with 'sha256:'."""
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def now_utc() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


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

    return (len(drifted) == 0, drifted)


# ---------------------------------------------------------------------------
# Minimal TOML serialiser (stdlib only, no tomli-w dependency)
# ---------------------------------------------------------------------------


def _toml_value(v: Any) -> str:  # noqa: ANN401
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, str):
        escaped = v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return f'"{escaped}"'
    if isinstance(v, list):
        items = ", ".join(_toml_value(i) for i in v)
        return f"[{items}]"
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
                    f'"{escaped_key}"'
                    if ("/" in nt_key or "." in nt_key or '"' in nt_key or "\\" in nt_key)
                    else nt_key
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
