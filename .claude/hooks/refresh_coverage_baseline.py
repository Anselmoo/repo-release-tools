#!/usr/bin/env python3
"""Auto-refresh `.claude/coverage-baseline.json` from latest `coverage.xml`."""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from contextlib import suppress
from pathlib import Path
from typing import Any


def _read_payload() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _extract_command(payload: dict[str, Any]) -> str:
    candidates = [
        payload.get("tool_input", {}).get("command"),
        payload.get("command"),
        payload.get("input", {}).get("command"),
        payload.get("tool", {}).get("input", {}).get("command"),
    ]
    return next(
        (item for item in candidates if isinstance(item, str) and item.strip()),
        "",
    )


def _extract_success(payload: dict[str, Any]) -> bool:
    """Best-effort success extraction for PostToolUse payload variants."""
    if payload.get("error") or payload.get("is_error") is True:
        return False

    # Common explicit booleans.
    for key in ("success", "ok"):
        if key in payload and isinstance(payload[key], bool):
            return payload[key]

    # Common nested output objects.
    for parent in ("tool_output", "output", "result", "tool_result"):
        nested = payload.get(parent)
        if not isinstance(nested, dict):
            continue

        if nested.get("error") or nested.get("is_error") is True:
            return False

        if "exit_code" in nested:
            with suppress(TypeError, ValueError):
                return int(nested["exit_code"]) == 0

        for key in ("success", "ok"):
            if key in nested and isinstance(nested[key], bool):
                return nested[key]

    # Direct exit code fallback.
    if "exit_code" in payload:
        try:
            return int(payload["exit_code"]) == 0
        except (TypeError, ValueError):
            return False

    # Unknown schema: fail closed so we never refresh on uncertain outcomes.
    return False


def _read_coverage_pct(coverage_xml: Path) -> float:
    text = coverage_xml.read_text(encoding="utf-8", errors="replace")
    if not (match := re.search(r'line-rate="([0-9]*\.?[0-9]+)"', text)):
        raise ValueError("Could not find line-rate in coverage.xml")
    return float(match.group(1)) * 100.0


def _write_baseline(baseline_file: Path, coverage_pct: float) -> None:
    baseline_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "baseline_pct": round(coverage_pct, 2),
        "source": "auto-refresh from coverage.xml",
        "captured_at": dt.date.today().isoformat(),
    }
    baseline_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    """Refresh baseline only after successful pytest invocations."""
    payload = _read_payload()
    command = _extract_command(payload)

    if "pytest" not in command:
        return 0

    if not _extract_success(payload):
        return 0

    repo_root = Path.cwd()
    coverage_xml = repo_root / "coverage.xml"
    if not coverage_xml.exists():
        return 0

    try:
        coverage_pct = _read_coverage_pct(coverage_xml)
        _write_baseline(repo_root / ".claude" / "coverage-baseline.json", coverage_pct)
    except Exception:
        # Never block the parent tool execution for refresh helper issues.
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
