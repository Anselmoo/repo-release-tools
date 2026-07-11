"""Tests for the `.claude/hooks/*.py` coverage governance scripts.

These are standalone scripts invoked by Claude Code (not part of the
`repo_release_tools` package), so they are exercised here as subprocesses,
mirroring how the Stop/PostToolUse hook runners actually call them. They sit
outside `[tool.coverage.run] source` and are therefore not counted toward the
100% `src/` coverage gate -- but they still deserve direct tests since they
enforce that very gate.

Covers:
- `coverage_non_regression.py`'s local allowance band (`TARGET_COVERAGE_PCT`,
  `MAX_ABSOLUTE_DROP_PCT`, `MAX_RELATIVE_DROP_PCT`), which `.claude/settings.json`
  widens for the Stop hook to absorb stale/partial `coverage.xml` noise.
- `refresh_coverage_baseline.py`'s large-drop guard (`MAX_AUTO_REFRESH_DROP_PCT`),
  which stops a narrow/partial pytest run from silently ratcheting the
  recorded baseline down.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"
COVERAGE_NON_REGRESSION = HOOKS_DIR / "coverage_non_regression.py"
REFRESH_BASELINE = HOOKS_DIR / "refresh_coverage_baseline.py"


def _write_coverage_xml(path: Path, line_rate: float) -> None:
    path.write_text(
        f'<?xml version="1.0" ?>\n<coverage line-rate="{line_rate}"></coverage>\n',
        encoding="utf-8",
    )


def _write_baseline(path: Path, baseline_pct: float) -> None:
    path.write_text(
        json.dumps({"baseline_pct": baseline_pct, "source": "test", "captured_at": "2026-01-01"}),
        encoding="utf-8",
    )


def _run_coverage_non_regression(
    cwd: Path,
    *,
    env_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    import os

    env = os.environ.copy()
    env.update(env_overrides or {})
    return subprocess.run(
        [sys.executable, str(COVERAGE_NON_REGRESSION)],
        cwd=cwd,
        input="{}",
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def _run_refresh_baseline(
    cwd: Path,
    *,
    stdin_payload: Mapping[str, object],
    env_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    import os

    env = os.environ.copy()
    env.update(env_overrides or {})
    return subprocess.run(
        [sys.executable, str(REFRESH_BASELINE)],
        cwd=cwd,
        input=json.dumps(stdin_payload),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


class TestCoverageNonRegressionAllowanceBand:
    """Exercise the Stop hook with the same env vars .claude/settings.json passes it."""

    ALLOWANCE_ENV = {
        "TARGET_COVERAGE_PCT": "90",
        "MAX_ABSOLUTE_DROP_PCT": "10",
        "MAX_RELATIVE_DROP_PCT": "10",
    }

    def test_stale_but_within_band_does_not_block(self, tmp_path: Path) -> None:
        """A coverage.xml within the 10pp allowance band should NOT block."""
        _write_coverage_xml(tmp_path / "coverage.xml", 0.91)  # 91%
        (tmp_path / ".claude").mkdir(exist_ok=True)
        _write_baseline(tmp_path / ".claude" / "coverage-baseline.json", 100.0)

        result = _run_coverage_non_regression(tmp_path, env_overrides=self.ALLOWANCE_ENV)

        assert result.returncode == 0, result.stdout

    def test_default_strict_band_blocks_same_reading(self, tmp_path: Path) -> None:
        """Without the widened env vars, the hook's own hard defaults (0pp/100%) block the same 91% reading."""
        _write_coverage_xml(tmp_path / "coverage.xml", 0.91)
        (tmp_path / ".claude").mkdir(exist_ok=True)
        _write_baseline(tmp_path / ".claude" / "coverage-baseline.json", 100.0)

        result = _run_coverage_non_regression(tmp_path, env_overrides={})

        assert result.returncode == 2
        payload = json.loads(result.stdout)
        assert payload["decision"] == "block"

    def test_genuine_severe_drop_still_blocks_within_band(self, tmp_path: Path) -> None:
        """A genuinely severe drop (e.g. stale coverage.xml far below baseline) still blocks
        even with the widened local allowance band."""
        _write_coverage_xml(tmp_path / "coverage.xml", 0.24)  # 24%, mirrors the real incident
        (tmp_path / ".claude").mkdir(exist_ok=True)
        _write_baseline(tmp_path / ".claude" / "coverage-baseline.json", 100.0)

        result = _run_coverage_non_regression(tmp_path, env_overrides=self.ALLOWANCE_ENV)

        assert result.returncode == 2
        payload = json.loads(result.stdout)
        assert payload["decision"] == "block"

    def test_exactly_at_band_boundary_passes(self, tmp_path: Path) -> None:
        """90% current coverage against a 100% baseline sits exactly on both the
        target floor and the 10pp drop allowance -- should pass."""
        _write_coverage_xml(tmp_path / "coverage.xml", 0.90)
        (tmp_path / ".claude").mkdir(exist_ok=True)
        _write_baseline(tmp_path / ".claude" / "coverage-baseline.json", 100.0)

        result = _run_coverage_non_regression(tmp_path, env_overrides=self.ALLOWANCE_ENV)

        assert result.returncode == 0, result.stdout

    def test_just_below_band_boundary_blocks(self, tmp_path: Path) -> None:
        """89.9% just breaches both the 90% floor and the 10pp drop allowance -- should block."""
        _write_coverage_xml(tmp_path / "coverage.xml", 0.899)
        (tmp_path / ".claude").mkdir(exist_ok=True)
        _write_baseline(tmp_path / ".claude" / "coverage-baseline.json", 100.0)

        result = _run_coverage_non_regression(tmp_path, env_overrides=self.ALLOWANCE_ENV)

        assert result.returncode == 2


class TestRefreshCoverageBaselineLargeDropGuard:
    """Exercise refresh_coverage_baseline.py's guard against silently ratcheting the baseline down."""

    SUCCESS_PAYLOAD = {"tool_input": {"command": "uv run pytest -q"}, "success": True}

    def test_small_drop_still_refreshes(self, tmp_path: Path) -> None:
        _write_coverage_xml(tmp_path / "coverage.xml", 0.95)  # 95%, 5pp drop from 100
        (tmp_path / ".claude").mkdir(exist_ok=True)
        baseline_file = tmp_path / ".claude" / "coverage-baseline.json"
        _write_baseline(baseline_file, 100.0)

        result = _run_refresh_baseline(tmp_path, stdin_payload=self.SUCCESS_PAYLOAD)

        assert result.returncode == 0, result.stdout
        data = json.loads(baseline_file.read_text(encoding="utf-8"))
        assert data["baseline_pct"] == pytest.approx(95.0)

    def test_large_drop_is_refused(self, tmp_path: Path) -> None:
        """A narrow/partial pytest run producing e.g. 24% coverage must not overwrite
        a 100% baseline -- the baseline file should remain unchanged."""
        _write_coverage_xml(tmp_path / "coverage.xml", 0.24)
        (tmp_path / ".claude").mkdir(exist_ok=True)
        baseline_file = tmp_path / ".claude" / "coverage-baseline.json"
        _write_baseline(baseline_file, 100.0)

        result = _run_refresh_baseline(tmp_path, stdin_payload=self.SUCCESS_PAYLOAD)

        assert result.returncode == 0, result.stdout
        data = json.loads(baseline_file.read_text(encoding="utf-8"))
        assert data["baseline_pct"] == pytest.approx(100.0)

    def test_large_drop_guard_configurable_via_env(self, tmp_path: Path) -> None:
        """MAX_AUTO_REFRESH_DROP_PCT can be widened via env var for explicit override scenarios."""
        _write_coverage_xml(tmp_path / "coverage.xml", 0.24)
        (tmp_path / ".claude").mkdir(exist_ok=True)
        baseline_file = tmp_path / ".claude" / "coverage-baseline.json"
        _write_baseline(baseline_file, 100.0)

        result = _run_refresh_baseline(
            tmp_path,
            stdin_payload=self.SUCCESS_PAYLOAD,
            env_overrides={"MAX_AUTO_REFRESH_DROP_PCT": "100"},
        )

        assert result.returncode == 0, result.stdout
        data = json.loads(baseline_file.read_text(encoding="utf-8"))
        assert data["baseline_pct"] == pytest.approx(24.0)

    def test_no_existing_baseline_always_writes(self, tmp_path: Path) -> None:
        """With no prior baseline recorded, any successful reading is written."""
        _write_coverage_xml(tmp_path / "coverage.xml", 0.24)
        (tmp_path / ".claude").mkdir(exist_ok=True)
        baseline_file = tmp_path / ".claude" / "coverage-baseline.json"

        result = _run_refresh_baseline(tmp_path, stdin_payload=self.SUCCESS_PAYLOAD)

        assert result.returncode == 0, result.stdout
        data = json.loads(baseline_file.read_text(encoding="utf-8"))
        assert data["baseline_pct"] == pytest.approx(24.0)
