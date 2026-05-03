#!/usr/bin/env python3
"""Claude Stop hook: block when coverage regresses below policy or baseline."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _read_current_coverage_pct(coverage_xml: Path) -> float:
    if not coverage_xml.exists():
        raise FileNotFoundError(f"Coverage report not found: {coverage_xml}")

    text = coverage_xml.read_text(encoding="utf-8", errors="replace")
    if not (match := re.search(r'line-rate="([0-9]*\.?[0-9]+)"', text)):
        raise ValueError("Could not find line-rate in coverage.xml")

    return float(match.group(1)) * 100.0


def _read_baseline_pct(path: Path) -> float | None:
    if not path.exists():
        return None

    data = json.loads(path.read_text(encoding="utf-8"))
    baseline = data.get("baseline_pct")
    return float(baseline) if baseline is not None else None


def _block(reason: str) -> int:
    payload = {"decision": "block", "reason": reason}
    print(json.dumps(payload, ensure_ascii=False))
    return 2


def main() -> int:
    """Evaluate coverage non-regression policy and emit a Stop-hook decision."""
    # Ignore stdin payload (event JSON) for this deterministic check.
    _ = sys.stdin.read()

    repo_root = Path.cwd()
    coverage_xml = Path(os.getenv("COVERAGE_XML_PATH", str(repo_root / "coverage.xml")))
    baseline_file = Path(
        os.getenv("COVERAGE_BASELINE_FILE", str(repo_root / ".claude" / "coverage-baseline.json"))
    )

    target_pct = _env_float("TARGET_COVERAGE_PCT", 85.71)
    max_abs_drop_pct = _env_float("MAX_ABSOLUTE_DROP_PCT", 0.0)
    max_rel_drop_pct = _env_float("MAX_RELATIVE_DROP_PCT", 0.0)

    try:
        current_pct = _read_current_coverage_pct(coverage_xml)
    except Exception as exc:  # pragma: no cover - defensive for hook runtime
        return _block(f"Coverage gate failed to read current coverage: {exc}")

    failures: list[str] = []
    if current_pct + 1e-9 < target_pct:
        failures.append(
            f"Current coverage {current_pct:.2f}% is below target {target_pct:.2f}%"
        )

    baseline_pct = None
    try:
        baseline_pct = _read_baseline_pct(baseline_file)
    except Exception as exc:  # pragma: no cover - defensive for hook runtime
        failures.append(f"Could not parse baseline file {baseline_file}: {exc}")

    if baseline_pct is not None:
        abs_drop_pct = max(0.0, baseline_pct - current_pct)
        rel_drop_pct = (abs_drop_pct / baseline_pct * 100.0) if baseline_pct > 0 else 0.0

        if abs_drop_pct - 1e-9 > max_abs_drop_pct:
            failures.append(
                "Absolute coverage drop exceeded threshold: "
                f"current={current_pct:.2f}% baseline={baseline_pct:.2f}% "
                f"drop={abs_drop_pct:.2f}pp allowed={max_abs_drop_pct:.2f}pp"
            )
        if rel_drop_pct - 1e-9 > max_rel_drop_pct:
            failures.append(
                "Relative coverage drop exceeded threshold: "
                f"current={current_pct:.2f}% baseline={baseline_pct:.2f}% "
                f"drop={rel_drop_pct:.3f}% allowed={max_rel_drop_pct:.3f}%"
            )

    if failures:
        details = " | ".join(failures)
        return _block(f"Coverage non-regression gate failed. {details}")

    # Success: do not block.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
