"""Runtime end-of-life (EOL) tracking for repo-release-tools.

Supports Python, Go, Node.js, and Rust.  Bundled data provides offline
operation; pass ``fetch_live=True`` to pull fresh data from
https://endoflife.date/api/<language>.json.

Rust uses a rolling-release model — only the latest stable is supported.
The meaningful check for Rust is how many releases behind the host/project
minimum is, not a date-based deadline.

## Supported languages

| Keyword | Checked via | EOL model |
|---|---|---|
| `python` | `python --version` / `requires-python` | Date-based |
| `go` | `go version` / `go.mod` | Date-based (two latest minors supported) |
| `nodejs` / `node` | `node --version` / `.nvmrc` / `engines.node` | Date-based (LTS only) |
| `rust` | `rustc --version` / `rust-toolchain.toml` | Rolling-release (lag-based) |

Pass the lowercase keyword to `--language` or `languages` in `[tool.rrt.eol]`.

## Data sources

rrt ships a bundled snapshot of EOL data (updated with each release). This
enables fully offline operation with no external requests.

Pass `--fetch-live` to pull fresh records from
[endoflife.date](https://endoflife.date/api/<language>.json) for the current
invocation. Live data is never cached — the bundled snapshot is always the
default.

## Rust rolling-release model

Rust does not use date-based EOL windows. The community supports only the
latest stable release. rrt models this as a lag-based check:

- `RUST_WARN_LAG = 2` — warn if the detected version is 2 or more releases
  behind the latest stable
- `RUST_ERROR_LAG = 4` — error if 4 or more releases behind

These thresholds are not configurable in `[tool.rrt.eol]`; they reflect the
upstream support model.

## `[tool.rrt.eol]` configuration

Add to `pyproject.toml` (or `.rrt.toml`):

```toml
[tool.rrt.eol]
languages = ["python", "node"]
warn_days   = 90    # warn N days before EOL (default: 90)
error_days  = 30    # error N days before EOL (default: 30)
allow_eol   = false # downgrade EOL errors to warnings (default: false)
fetch_live  = false # refresh from endoflife.date at runtime (default: false)

# Per-cycle EOL date overrides (optional)
[[tool.rrt.eol.overrides]]
language = "python"
cycle    = "3.9"
eol      = "2026-06-01"   # ISO 8601
```

| Key | Type | Default | Description |
|---|---|---|---|
| `languages` | list[str] | `["python"]` | Languages to check |
| `warn_days` | int | `90` | Days-before-EOL warning threshold |
| `error_days` | int | `30` | Days-before-EOL error threshold |
| `allow_eol` | bool | `false` | Downgrade EOL failures to warnings |
| `fetch_live` | bool | `false` | Pull fresh data from endoflife.date |
| `overrides` | list | `[]` | Per-cycle EOL date overrides |

## Version detection

For each language rrt tries to detect two versions:

- **Host runtime** — the interpreter or toolchain installed on the current
  machine (e.g. `python --version`)
- **Project minimum** — the minimum version declared in the repository (e.g.
  `requires-python` in `pyproject.toml`)

| Language | Host detection | Project minimum detection |
|---|---|---|
| Python | `sys.version` | `requires-python` in `pyproject.toml` |
| Go | `go version` | `go` directive in `go.mod` |
| Node.js | `node --version` | `engines.node` in `package.json` or `.nvmrc` |
| Rust | `rustc --version` | `channel` in `rust-toolchain.toml` |

When a version cannot be detected, rrt reports `not detected` without failing
that specific check.

## EOL status labels

| Status | Meaning |
|---|---|
| `ok` | Version is supported with more than `warn_days` remaining |
| `info` | Version is supported but EOL date is unknown or far future |
| `warn` | EOL within `warn_days` days |
| `error` | EOL within `error_days` days or already past EOL |
| `unknown` | Version string could not be matched to a known cycle |

## Related docs

- [rrt eol (CLI)](rrt-cli.md)
- [rrt doctor](doctor.md)
- [GitHub Action](github-action.md)
- [pre-commit / lefthook](pre-commit.md)
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

EolStatus = Literal["ok", "info", "warn", "error", "unknown"]

# How many major Rust releases behind counts as a warning / error.
RUST_WARN_LAG = 2
RUST_ERROR_LAG = 4

# ---------------------------------------------------------------------------
# Bundled EOL data snapshot (as of 2026-05-01)
# Keys match endoflife.date product slugs: "python", "nodejs", "go", "rust"
# Each entry: {"cycle": str, "eol": str|bool, "releaseDate": str}
# ---------------------------------------------------------------------------

BUNDLED_EOL_DATA: dict[str, list[dict[str, object]]] = {
    "python": [
        {"cycle": "3.14", "releaseDate": "2025-10-07", "eol": "2030-10-31"},
        {"cycle": "3.13", "releaseDate": "2024-10-07", "eol": "2029-10-31"},
        {"cycle": "3.12", "releaseDate": "2023-10-02", "eol": "2028-10-31"},
        {"cycle": "3.11", "releaseDate": "2022-10-24", "eol": "2027-10-31"},
        {"cycle": "3.10", "releaseDate": "2021-10-04", "eol": "2026-10-31"},
        {"cycle": "3.9", "releaseDate": "2020-10-05", "eol": "2025-10-31"},
        {"cycle": "3.8", "releaseDate": "2019-10-14", "eol": "2024-10-07"},
        {"cycle": "3.7", "releaseDate": "2018-06-27", "eol": "2023-06-27"},
    ],
    "nodejs": [
        {"cycle": "24", "releaseDate": "2025-05-06", "eol": "2028-04-30"},
        {"cycle": "23", "releaseDate": "2024-10-16", "eol": "2025-06-01"},
        {"cycle": "22", "releaseDate": "2024-04-24", "eol": "2027-04-30"},
        {"cycle": "21", "releaseDate": "2023-10-17", "eol": "2024-06-01"},
        {"cycle": "20", "releaseDate": "2023-04-18", "eol": "2026-04-30"},
        {"cycle": "18", "releaseDate": "2022-04-19", "eol": "2025-04-30"},
        {"cycle": "16", "releaseDate": "2021-04-20", "eol": "2023-09-11"},
    ],
    "go": [
        {"cycle": "1.26", "releaseDate": "2026-02-11", "eol": False},
        {"cycle": "1.25", "releaseDate": "2025-08-12", "eol": False},
        {"cycle": "1.24", "releaseDate": "2025-02-11", "eol": "2026-02-11"},
        {"cycle": "1.23", "releaseDate": "2024-08-13", "eol": "2025-08-12"},
        {"cycle": "1.22", "releaseDate": "2024-02-06", "eol": "2025-02-11"},
        {"cycle": "1.21", "releaseDate": "2023-08-08", "eol": "2024-08-13"},
    ],
    # Rust: rolling-release — only latest stable is "supported"
    # eol=False means supported; eol=<date> means superseded on that date
    "rust": [
        {"cycle": "1.95", "releaseDate": "2026-04-16", "eol": False},
        {"cycle": "1.94", "releaseDate": "2026-03-06", "eol": "2026-04-16"},
        {"cycle": "1.93", "releaseDate": "2026-01-22", "eol": "2026-03-06"},
        {"cycle": "1.92", "releaseDate": "2025-12-11", "eol": "2026-01-22"},
        {"cycle": "1.91", "releaseDate": "2025-10-30", "eol": "2025-12-11"},
        {"cycle": "1.90", "releaseDate": "2025-09-04", "eol": "2025-10-30"},
        {"cycle": "1.89", "releaseDate": "2025-07-10", "eol": "2025-09-04"},
        {"cycle": "1.88", "releaseDate": "2025-05-15", "eol": "2025-07-10"},
    ],
}

# endoflife.date API product slug for each language keyword
_EOL_API_SLUG: dict[str, str] = {
    "python": "python",
    "nodejs": "nodejs",
    "node": "nodejs",
    "go": "go",
    "rust": "rust",
}

SUPPORTED_LANGUAGES = frozenset(_EOL_API_SLUG.keys())


# ---------------------------------------------------------------------------
# Data records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EolRecord:
    """A single release cycle's EOL metadata."""

    cycle: str
    release_date: date | None
    eol_date: date | None  # None means "actively supported / no end date yet"
    is_eol: bool
    days_until_eol: int | None  # None when already EOL or no date

    @classmethod
    def from_api_dict(cls, entry: dict[str, object], today: date | None = None) -> "EolRecord":
        """Parse an endoflife.date API dict into an EolRecord."""
        if today is None:
            today = date.today()

        cycle = str(entry["cycle"])

        release_date: date | None = None
        if "releaseDate" in entry:
            try:
                release_date = date.fromisoformat(str(entry["releaseDate"]))
            except (ValueError, TypeError):
                pass

        raw_eol = entry.get("eol")
        eol_date: date | None = None
        is_eol = False

        if isinstance(raw_eol, bool):
            # eol: false → actively supported; eol: true → already EOL (no exact date)
            is_eol = raw_eol
        elif isinstance(raw_eol, str):
            try:
                eol_date = date.fromisoformat(raw_eol)
                is_eol = eol_date <= today
            except (ValueError, TypeError):
                pass

        days_until_eol: int | None = None
        if eol_date is not None and not is_eol:
            days_until_eol = (eol_date - today).days

        return cls(
            cycle=cycle,
            release_date=release_date,
            eol_date=eol_date,
            is_eol=is_eol,
            days_until_eol=days_until_eol,
        )


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def _canonical_slug(language: str) -> str:
    """Normalise a user-supplied language name to the endoflife.date slug."""
    key = language.lower().strip()
    slug = _EOL_API_SLUG.get(key, key)
    return slug


def fetch_live_data(language: str) -> list[dict[str, object]]:
    """Fetch EOL data from endoflife.date API.

    Returns an empty list on any network or parse error so callers can safely
    fall back to bundled data.
    """
    slug = _canonical_slug(language)
    url = f"https://endoflife.date/api/v1/products/{slug}/"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310
            raw = json.loads(resp.read().decode("utf-8"))
            # API returns {"result": [...]} wrapper in v1
            if isinstance(raw, dict) and "result" in raw:
                return list(raw["result"])
            if isinstance(raw, list):
                return raw  # type: ignore[return-value]
            return []
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        return []


def get_eol_records(
    language: str,
    *,
    fetch_live: bool = False,
    today: date | None = None,
) -> list[EolRecord]:
    """Return EolRecord list for *language*, optionally refreshed from the API."""
    slug = _canonical_slug(language)
    raw: list[dict[str, object]] = []

    if fetch_live:
        raw = fetch_live_data(language)

    if not raw:
        raw = list(BUNDLED_EOL_DATA.get(slug, []))

    if today is None:
        today = date.today()

    return [EolRecord.from_api_dict(entry, today=today) for entry in raw]


# ---------------------------------------------------------------------------
# Version parsing helpers
# ---------------------------------------------------------------------------

_VERSION_RE = re.compile(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?")


def _parse_cycle(version_string: str) -> str | None:
    """Extract the major.minor cycle string from a version string.

    Examples::
        "3.12.4"   → "3.12"
        "3.12"     → "3.12"
        "1.26.2"   → "1.26"
        "22.14.0"  → "22"     (Node uses single-digit major)
        "1.95.0"   → "1.95"   (Rust uses major.minor as cycle)
    """
    m = _VERSION_RE.search(version_string)
    if not m:
        return None
    major = m.group(1)
    minor = m.group(2)
    if minor is not None:
        return f"{major}.{minor}"
    return major


def _find_record(cycle: str, records: list[EolRecord]) -> EolRecord | None:
    """Find the best matching EolRecord for *cycle*."""
    # Exact match first
    for r in records:
        if r.cycle == cycle:
            return r
    # Prefix match (e.g. "22.14" → cycle "22")
    parts = cycle.split(".")
    for r in records:
        if r.cycle == parts[0]:
            return r
    return None


# ---------------------------------------------------------------------------
# Rust-specific lag check
# ---------------------------------------------------------------------------


def _rust_lag_position(cycle: str, records: list[EolRecord]) -> int:
    """Return how many releases behind *cycle* is relative to the latest stable.

    0 = latest, 1 = one behind, etc.  Returns ``len(records)`` if not found.
    """
    latest_idx = next((i for i, r in enumerate(records) if not r.is_eol and r.eol_date is None), 0)
    for i, r in enumerate(records):
        if r.cycle == cycle:
            return i - latest_idx
    return len(records)


# ---------------------------------------------------------------------------
# EOL status computation
# ---------------------------------------------------------------------------


def check_eol_status(
    version_string: str,
    records: list[EolRecord],
    *,
    language: str = "python",
    warn_days: int = 180,
    error_days: int = 0,
    allow_eol: bool = False,
    override_eol: date | None = None,
    today: date | None = None,
) -> tuple[EolStatus, EolRecord | None]:
    """Compute the EOL status for *version_string* against *records*.

    Returns ``(status, record)`` where *record* is the matching EolRecord or
    ``None`` when no match is found.

    Rust uses lag-based logic rather than date-based.
    """
    if today is None:
        today = date.today()

    slug = _canonical_slug(language)
    cycle = _parse_cycle(version_string)
    if cycle is None:
        return ("unknown", None)

    record = _find_record(cycle, records)
    if record is None:
        return ("unknown", None)

    # ------------------------------------------------------------------
    # Rust: lag-based
    # ------------------------------------------------------------------
    if slug == "rust":
        lag = _rust_lag_position(cycle, records)
        if lag >= RUST_ERROR_LAG:
            return ("warn", record) if allow_eol else ("error", record)
        if lag >= RUST_WARN_LAG:
            return ("warn", record)
        return ("ok", record)

    # ------------------------------------------------------------------
    # All others: date-based
    # ------------------------------------------------------------------
    effective_eol: date | None = override_eol or record.eol_date

    if effective_eol is None:
        # No EOL date means actively supported
        return ("ok", record)

    if effective_eol <= today:
        return ("warn", record) if allow_eol else ("error", record)

    days_left = (effective_eol - today).days

    if error_days > 0 and days_left <= error_days:
        return ("warn", record) if allow_eol else ("error", record)

    if warn_days > 0 and days_left <= warn_days:
        return ("warn", record)

    return ("ok", record)


# ---------------------------------------------------------------------------
# Host version detection
# ---------------------------------------------------------------------------


def detect_host_version(language: str) -> str | None:
    """Return the installed version string for *language* on the host.

    Returns ``None`` when the runtime is not found or cannot be detected.
    """
    slug = _canonical_slug(language)

    if slug == "python":
        v = sys.version_info
        return f"{v.major}.{v.minor}.{v.micro}"

    commands: dict[str, list[str]] = {
        "nodejs": ["node", "--version"],
        "go": ["go", "version"],
        "rust": ["rustc", "--version"],
    }
    cmd = commands.get(slug)
    if cmd is None:
        return None

    try:
        result = subprocess.run(  # noqa: S603
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        return _extract_version(result.stdout.strip(), slug)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def _extract_version(output: str, slug: str) -> str | None:
    """Extract the version string from command output for the given slug."""
    if slug == "nodejs":
        # "v22.14.0" → "22.14.0"
        m = re.match(r"v?(\d+\.\d+\.\d+)", output)
        return m.group(1) if m else None

    if slug == "go":
        # "go version go1.26.2 darwin/arm64" → "1.26.2"
        m = re.search(r"go(\d+\.\d+(?:\.\d+)?)", output)
        return m.group(1) if m else None

    if slug == "rust":
        # "rustc 1.95.0 (32fc4b338 2026-04-15)" → "1.95.0"
        m = re.search(r"rustc (\d+\.\d+\.\d+)", output)
        return m.group(1) if m else None

    return None


# ---------------------------------------------------------------------------
# Project minimum version detection
# ---------------------------------------------------------------------------


def detect_project_minimum(language: str, root: Path) -> str | None:
    """Return the project's declared minimum version for *language*.

    Reads from the project configuration file at *root*:
    - Python:  ``requires-python`` in ``pyproject.toml``
    - Go:      ``go`` directive in ``go.mod``
    - Node.js: ``engines.node`` in ``package.json``
    - Rust:    ``rust-version`` in ``Cargo.toml``
    """
    slug = _canonical_slug(language)

    if slug == "python":
        return _detect_python_minimum(root)
    if slug == "go":
        return _detect_go_minimum(root)
    if slug == "nodejs":
        return _detect_node_minimum(root)
    if slug == "rust":
        return _detect_rust_minimum(root)
    return None


def _detect_python_minimum(root: Path) -> str | None:
    """Read ``requires-python`` from ``pyproject.toml``."""
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return None
    try:
        import tomllib as _tomllib

        with pyproject.open("rb") as f:
            data = _tomllib.load(f)
        raw: object = data.get("project", {}).get("requires-python")
        if not isinstance(raw, str):
            return None
        # ">=3.12" or "==3.12.*" → extract first version number
        m = re.search(r"(\d+\.\d+(?:\.\d+)?)", raw)
        return m.group(1) if m else None
    except Exception:  # noqa: BLE001
        return None


def _detect_go_minimum(root: Path) -> str | None:
    """Read the ``go`` directive from ``go.mod``."""
    gomod = root / "go.mod"
    if not gomod.exists():
        return None
    try:
        text = gomod.read_text(encoding="utf-8")
        m = re.search(r"^\s*go\s+(\d+\.\d+(?:\.\d+)?)\s*$", text, re.MULTILINE)
        return m.group(1) if m else None
    except OSError:
        return None


def _detect_node_minimum(root: Path) -> str | None:
    """Read ``engines.node`` from ``package.json``."""
    pkg = root / "package.json"
    if not pkg.exists():
        return None
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
        raw: object = data.get("engines", {}).get("node")
        if not isinstance(raw, str):
            return None
        m = re.search(r"(\d+\.\d+(?:\.\d+)?)", raw)
        return m.group(1) if m else None
    except (json.JSONDecodeError, OSError):
        return None


def _detect_rust_minimum(root: Path) -> str | None:
    """Read ``rust-version`` from ``Cargo.toml``."""
    cargo = root / "Cargo.toml"
    if not cargo.exists():
        return None
    try:
        import tomllib as _tomllib

        with cargo.open("rb") as f:
            data = _tomllib.load(f)
        raw: object = data.get("package", {}).get("rust-version")
        if not isinstance(raw, str):
            return None
        m = re.search(r"(\d+\.\d+(?:\.\d+)?)", raw)
        return m.group(1) if m else None
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Documentation
# ---------------------------------------------------------------------------

# Docs live in the module docstring above — consistent with bump.py / ci_version.py.
SOURCE_OWNED_TOPIC_DOCS: tuple[tuple[str, str], ...] = (("eol", __doc__ or ""),)
