"""Runtime end-of-life (EOL) tracking for repo-release-tools.

Supports Python, Go, Node.js, and Rust. Bundled data provides offline
operation; pass ``fetch_live=True`` to pull fresh data from
``https://endoflife.date/api/v1/products/<slug>/``.

Rust uses a rolling-release model — only the latest stable is supported.
The meaningful check for Rust is how many releases behind the host/project
minimum is, not a date-based deadline.

## Supported languages

| Keyword | Checked via | EOL model |
|---|---|---|
| `python` | `python --version` / `requires-python` | Date-based |
| `go` | `go version` / `go.mod` | Date-based (two latest minors supported) |
| `nodejs` / `node` | `node --version` / `engines.node` | Date-based (LTS only) |
| `rust` | `rustc --version` / `Cargo.toml` `rust-version` | Rolling-release (lag-based) |

Pass the lowercase keyword to `--language` or `languages` in `[tool.rrt.eol]`.

## Data sources

rrt ships a bundled snapshot of EOL data (updated with each release). This
enables fully offline operation with no external requests.

Pass `--fetch-live` to pull fresh records from
[endoflife.date](https://endoflife.date/api/v1/products/python/) for the current
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
warn_days   = 180
error_days  = 0
allow_eol   = false
fetch_live  = false

[[tool.rrt.eol.overrides]]
language = "python"
cycle    = "3.9"
eol      = "2026-06-01"
```

## Related docs

- [rrt eol (CLI)](rrt-cli.md)
- [rrt doctor](doctor.md)
- [GitHub Action](action.md)
- [pre-commit / lefthook](hooks.md)
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Literal

from repo_release_tools.config import EolOverride

from .data import BUNDLED_EOL_DATA, RUST_ERROR_LAG, RUST_WARN_LAG, SUPPORTED_LANGUAGES
from .detect import _canonical_slug, _extract_version, detect_host_version, detect_project_minimum

EolStatus = Literal["ok", "info", "warn", "error", "unknown"]


@dataclass(frozen=True)
class EolRecord:
    """A single release cycle's EOL metadata."""

    cycle: str
    release_date: date | None
    eol_date: date | None
    is_eol: bool
    days_until_eol: int | None

    @classmethod
    def from_api_dict(cls, entry: dict[str, object], today: date | None = None) -> EolRecord:
        """Parse an endoflife.date API dict into an EolRecord."""
        if today is None:
            today = date.today()

        cycle = str(entry["cycle"])
        release_date: date | None = None
        if "releaseDate" in entry:
            try:
                release_date = date.fromisoformat(str(entry["releaseDate"]))
            except ValueError:
                release_date = None

        raw_eol = entry.get("eol")
        if raw_eol is False:
            return cls(
                cycle=cycle,
                release_date=release_date,
                eol_date=None,
                is_eol=False,
                days_until_eol=None,
            )
        if raw_eol is True:
            return cls(
                cycle=cycle,
                release_date=release_date,
                eol_date=None,
                is_eol=True,
                days_until_eol=None,
            )

        eol_date: date | None = None
        if isinstance(raw_eol, str):
            try:
                eol_date = date.fromisoformat(raw_eol)
            except ValueError:
                eol_date = None

        is_eol = eol_date is not None and eol_date < today
        days_until_eol = None if eol_date is None or is_eol else (eol_date - today).days
        return cls(
            cycle=cycle,
            release_date=release_date,
            eol_date=eol_date,
            is_eol=is_eol,
            days_until_eol=days_until_eol,
        )


def fetch_live_data(language: str) -> list[dict[str, object]]:
    """Fetch EOL data from endoflife.date API."""
    slug = _canonical_slug(language)
    url = f"https://endoflife.date/api/v1/products/{slug}/"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310
            raw = json.loads(response.read().decode("utf-8"))
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


_VERSION_RE = re.compile(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?")


def _parse_cycle(version_string: str) -> str | None:
    """Extract the major.minor cycle string from a version string."""
    if not (match := _VERSION_RE.search(version_string)):
        return None
    return f"{match[1]}.{match[2]}" if match[2] is not None else match[1]


def resolve_override_eol(
    language: str,
    version: str,
    overrides: Iterable[EolOverride],
) -> date | None:
    """Return a configured EOL date override for ``(language, cycle)``, or ``None``."""
    cycle = _parse_cycle(version)
    if cycle is None:
        return None
    lang_lower = language.lower()
    for override in overrides:
        if override.language.lower() == lang_lower and override.cycle == cycle:
            try:
                return date.fromisoformat(override.eol)
            except ValueError:
                return None
    return None


def _find_record(cycle: str, records: list[EolRecord]) -> EolRecord | None:
    """Find the best matching EolRecord for *cycle*."""
    parts = cycle.split(".")
    return next((r for r in records if r.cycle == cycle), None) or next(
        (r for r in records if r.cycle == parts[0]), None
    )


def _rust_lag_position(cycle: str, records: list[EolRecord]) -> int:
    """Return how many releases behind *cycle* is relative to the latest stable."""
    latest_idx = next(
        (i for i, record in enumerate(records) if not record.is_eol and record.eol_date is None),
        0,
    )
    return next((i - latest_idx for i, r in enumerate(records) if r.cycle == cycle), len(records))


def check_eol_status(
    version_string: str,
    records_or_language: list[EolRecord] | str,
    language: str | None = None,
    *,
    warn_days: int = 180,
    error_days: int = 0,
    allow_eol: bool = False,
    fetch_live: bool = False,
    overrides: Iterable[EolOverride] = (),
    override_eol: date | None = None,
    today: date | None = None,
) -> tuple[EolStatus, EolRecord | None]:
    """Return the EOL status and matching record for a detected version string.

    Accepts both the legacy call shape:
        check_eol_status(version, records, language="python", ...)

    and the newer convenience shape:
        check_eol_status(version, "python", fetch_live=True, overrides=..., ...)
    """
    if today is None:
        today = date.today()

    cycle = _parse_cycle(version_string)
    if cycle is None:
        return ("unknown", None)

    if isinstance(records_or_language, str):
        language_name = records_or_language
        records = get_eol_records(language_name, fetch_live=fetch_live, today=today)
    else:
        if language is None:
            raise TypeError("language is required when passing records explicitly")
        language_name = language
        records = records_or_language

    if not records:
        return ("info", None)

    record = _find_record(cycle, records)
    if record is None:
        return ("unknown", None)

    if override_eol is None:
        override_eol = resolve_override_eol(language_name, version_string, overrides)
    if override_eol is not None:
        days_until = (override_eol - today).days
        if days_until < error_days:
            return (("warn" if allow_eol else "error"), record)
        if days_until < warn_days:
            return ("warn", record)
        return ("ok", record)

    slug = _canonical_slug(language_name)
    if slug == "rust":
        lag = _rust_lag_position(cycle, records)
        if lag >= RUST_ERROR_LAG:
            return (("warn" if allow_eol else "error"), record)
        if lag >= RUST_WARN_LAG:
            return ("warn", record)
        return ("ok", record)

    if record.eol_date is None:
        return ("ok", record)
    if record.is_eol:
        return (("warn" if allow_eol else "error"), record)
    assert record.days_until_eol is not None
    if record.days_until_eol <= error_days:
        return (("warn" if allow_eol else "error"), record)
    if record.days_until_eol <= warn_days:
        return ("warn", record)
    return ("ok", record)


SOURCE_OWNED_TOPIC_DOCS: tuple[tuple[str, str], ...] = (("eol", __doc__ or ""),)

__all__ = [
    "SOURCE_OWNED_TOPIC_DOCS",
    "SUPPORTED_LANGUAGES",
    "EolRecord",
    "EolStatus",
    "_extract_version",
    "_find_record",
    "_parse_cycle",
    "_rust_lag_position",
    "check_eol_status",
    "detect_host_version",
    "detect_project_minimum",
    "fetch_live_data",
    "get_eol_records",
    "resolve_override_eol",
]
