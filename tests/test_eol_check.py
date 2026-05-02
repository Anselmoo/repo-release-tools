"""Tests for the eol_check command module."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

import pytest

from repo_release_tools.commands.eol_check import (
    _emit_check,
    _override_for,
    _status_label,
    cmd_eol,
    run_eol_checks,
)
from repo_release_tools.config import EolConfig, EolOverride
from repo_release_tools.eol import EolRecord, EolStatus

# ---------------------------------------------------------------------------
# _status_label
# ---------------------------------------------------------------------------


class TestStatusLabel:
    @pytest.mark.parametrize(
        "status,expected",
        [
            ("ok", "supported"),
            ("info", "supported"),
            ("warn", "expiring soon"),
            ("error", "end-of-life"),
            ("unknown", "unknown"),
        ],
    )
    def test_label(self, status: str, expected: str) -> None:
        assert _status_label(cast(EolStatus, status)) == expected


# ---------------------------------------------------------------------------
# _emit_check output
# ---------------------------------------------------------------------------


class TestEmitCheck:
    def _make_printer(self) -> tuple[MagicMock, MagicMock, MagicMock]:
        p = MagicMock()
        return p, p.line, p.warn

    def _make_record(self, is_eol: bool = False, eol_date: date | None = None) -> EolRecord:
        return EolRecord(
            cycle="3.12",
            release_date=date(2023, 10, 2),
            eol_date=eol_date,
            is_eol=is_eol,
            days_until_eol=(eol_date - date.today()).days if eol_date and not is_eol else None,
        )

    def test_emits_warn_when_version_none(self) -> None:
        p = MagicMock()
        _emit_check(p, "Host runtime", None, "unknown", None)
        p.warn.assert_called_once()

    def test_emits_ok_on_ok_status(self) -> None:
        p = MagicMock()
        record = self._make_record()
        _emit_check(p, "Host runtime", "3.12.4", "ok", record)
        p.line.assert_called_once()
        args, kwargs = p.line.call_args
        assert kwargs.get("ok") is True

    def test_emits_warn_on_warn_status(self) -> None:
        p = MagicMock()
        record = self._make_record(eol_date=date(2026, 10, 31))
        _emit_check(p, "Host runtime", "3.12.4", "warn", record)
        p.warn.assert_called_once()

    def test_emits_warn_on_unknown_status(self) -> None:
        p = MagicMock()
        _emit_check(p, "Host runtime", "9.99.0", "unknown", None)
        p.warn.assert_called_once()

    def test_emits_error_on_error_status(self) -> None:
        p = MagicMock()
        record = self._make_record(is_eol=True)
        _emit_check(p, "Host runtime", "3.12.4", "error", record)
        p.line.assert_called_once()
        args, kwargs = p.line.call_args
        assert kwargs.get("ok") is False


# ---------------------------------------------------------------------------
# cmd_eol — integration
# ---------------------------------------------------------------------------


def _make_args(**kwargs: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "language": None,
        "fetch_live": False,
        "warn_days": None,
        "error_days": None,
        "allow_eol": False,
    }
    defaults.update(kwargs)  # type: ignore[arg-type]
    return argparse.Namespace(**defaults)


class TestCmdEol:
    def test_returns_0_on_all_ok(self, tmp_path: Path) -> None:
        eol_cfg = EolConfig(languages=("python",), warn_days=180, error_days=0)
        rrt_config = MagicMock()
        rrt_config.eol = eol_cfg

        with (
            patch(
                "repo_release_tools.commands.eol_check.load_or_autodetect_config",
                return_value=rrt_config,
            ),
            patch(
                "repo_release_tools.commands.eol_check.detect_host_version",
                return_value="3.12.4",
            ),
            patch(
                "repo_release_tools.commands.eol_check.detect_project_minimum",
                return_value="3.12",
            ),
            patch("pathlib.Path.cwd", return_value=tmp_path),
        ):
            result = cmd_eol(_make_args())
        assert result == 0

    def test_returns_1_on_eol_error(self, tmp_path: Path) -> None:
        eol_cfg = EolConfig(languages=("python",), warn_days=180, error_days=0)
        rrt_config = MagicMock()
        rrt_config.eol = eol_cfg

        with (
            patch(
                "repo_release_tools.commands.eol_check.load_or_autodetect_config",
                return_value=rrt_config,
            ),
            patch(
                "repo_release_tools.commands.eol_check.detect_host_version",
                return_value="3.8.18",  # EOL in bundled data
            ),
            patch(
                "repo_release_tools.commands.eol_check.detect_project_minimum",
                return_value=None,
            ),
            patch("pathlib.Path.cwd", return_value=tmp_path),
        ):
            result = cmd_eol(_make_args())
        assert result == 1

    def test_allow_eol_returns_0_despite_eol(self, tmp_path: Path) -> None:
        eol_cfg = EolConfig(languages=("python",), warn_days=180, error_days=0, allow_eol=True)
        rrt_config = MagicMock()
        rrt_config.eol = eol_cfg

        with (
            patch(
                "repo_release_tools.commands.eol_check.load_or_autodetect_config",
                return_value=rrt_config,
            ),
            patch(
                "repo_release_tools.commands.eol_check.detect_host_version",
                return_value="3.8.18",
            ),
            patch(
                "repo_release_tools.commands.eol_check.detect_project_minimum",
                return_value=None,
            ),
            patch("pathlib.Path.cwd", return_value=tmp_path),
        ):
            result = cmd_eol(_make_args(allow_eol=True))
        assert result == 0

    def test_falls_back_to_cli_defaults_when_no_config(self, tmp_path: Path) -> None:
        with (
            patch(
                "repo_release_tools.commands.eol_check.load_or_autodetect_config",
                side_effect=FileNotFoundError("no config"),
            ),
            patch(
                "repo_release_tools.commands.eol_check.detect_host_version",
                return_value="3.12.4",
            ),
            patch(
                "repo_release_tools.commands.eol_check.detect_project_minimum",
                return_value=None,
            ),
            patch("pathlib.Path.cwd", return_value=tmp_path),
        ):
            result = cmd_eol(_make_args())
        assert result == 0

    def test_single_language_override_from_cli(self, tmp_path: Path) -> None:
        eol_cfg = EolConfig(languages=("python", "go"), warn_days=180, error_days=0)
        rrt_config = MagicMock()
        rrt_config.eol = eol_cfg

        calls: list[str] = []

        def fake_host(lang: str) -> str | None:
            calls.append(lang)
            return "3.12.4" if lang == "python" else None

        with (
            patch(
                "repo_release_tools.commands.eol_check.load_or_autodetect_config",
                return_value=rrt_config,
            ),
            patch(
                "repo_release_tools.commands.eol_check.detect_host_version",
                side_effect=fake_host,
            ),
            patch(
                "repo_release_tools.commands.eol_check.detect_project_minimum",
                return_value=None,
            ),
            patch("pathlib.Path.cwd", return_value=tmp_path),
        ):
            result = cmd_eol(_make_args(language="python"))

        # Only python should be checked, not go
        assert calls == ["python"]
        assert result == 0

    def test_fetch_live_flag_respected(self, tmp_path: Path) -> None:
        eol_cfg = EolConfig(languages=("python",), warn_days=180, error_days=0, fetch_live=False)
        rrt_config = MagicMock()
        rrt_config.eol = eol_cfg

        with (
            patch(
                "repo_release_tools.commands.eol_check.load_or_autodetect_config",
                return_value=rrt_config,
            ),
            patch(
                "repo_release_tools.commands.eol_check.detect_host_version",
                return_value="3.12.4",
            ),
            patch(
                "repo_release_tools.commands.eol_check.detect_project_minimum",
                return_value=None,
            ),
            patch(
                "repo_release_tools.commands.eol_check.get_eol_records",
            ) as mock_get_records,
            patch("pathlib.Path.cwd", return_value=tmp_path),
        ):
            # Mock returns a simple record so check_eol_status can work
            mock_get_records.return_value = []
            cmd_eol(_make_args(fetch_live=True))

        # fetch_live should be True (CLI flag overrides config False)
        call_kwargs = mock_get_records.call_args[1]
        assert call_kwargs.get("fetch_live") is True

    def test_zero_thresholds_override_config(self, tmp_path: Path) -> None:
        eol_cfg = EolConfig(languages=("python",), warn_days=180, error_days=30)
        rrt_config = MagicMock()
        rrt_config.eol = eol_cfg

        with (
            patch(
                "repo_release_tools.commands.eol_check.load_or_autodetect_config",
                return_value=rrt_config,
            ),
            patch(
                "repo_release_tools.commands.eol_check.run_eol_checks",
                return_value=True,
            ) as mock_run_checks,
            patch("pathlib.Path.cwd", return_value=tmp_path),
        ):
            result = cmd_eol(_make_args(warn_days=0, error_days=0))

        assert result == 0
        assert mock_run_checks.call_args.kwargs["warn_days"] == 0
        assert mock_run_checks.call_args.kwargs["error_days"] == 0


# ---------------------------------------------------------------------------
# _override_for
# ---------------------------------------------------------------------------


class TestOverrideFor:
    def test_no_parseable_cycle_returns_none(self) -> None:
        """Version string that yields no cycle → None (line 107)."""
        result = _override_for("python", "not-a-version", ())
        assert result is None

    def test_matching_override_returns_date(self) -> None:
        """Matching language+cycle override → parsed date (lines 110-114)."""
        ov = EolOverride(language="python", cycle="3.12", eol="2026-12-31")
        result = _override_for("python", "3.12.4", (ov,))

        assert result == date(2026, 12, 31)

    def test_case_insensitive_language_match(self) -> None:
        """Language comparison is case-insensitive."""
        ov = EolOverride(language="Python", cycle="3.12", eol="2026-12-31")
        result = _override_for("python", "3.12.4", (ov,))
        assert result is not None

    def test_no_matching_override_returns_none(self) -> None:
        """No matching entry → None."""
        ov = EolOverride(language="python", cycle="3.11", eol="2024-10-31")
        result = _override_for("python", "3.12.4", (ov,))
        assert result is None

    def test_invalid_date_in_override_returns_none(self) -> None:
        """Matching override with invalid ISO date → ValueError caught, returns None (lines 113-114)."""
        ov = EolOverride(language="python", cycle="3.12", eol="not-a-date")
        result = _override_for("python", "3.12.4", (ov,))
        assert result is None


# ---------------------------------------------------------------------------
# _emit_check — days_until_eol branch
# ---------------------------------------------------------------------------


def test_emit_check_days_until_eol_detail() -> None:
    """When record has days_until_eol and no eol_date, detail shows '(EOL in Nd)' (line 148)."""
    p = MagicMock()
    record = EolRecord(
        cycle="3.12",
        release_date=None,
        eol_date=None,  # no eol_date → falls through to days_until_eol branch
        is_eol=False,
        days_until_eol=45,
    )
    _emit_check(p, "Host runtime", "3.12.4", "warn", record)
    call_args = p.warn.call_args[0][0]
    assert "(EOL in 45d)" in call_args


# ---------------------------------------------------------------------------
# run_eol_checks — host not detected + project error branches
# ---------------------------------------------------------------------------


def test_run_eol_checks_host_not_detected(tmp_path: Path) -> None:
    """When detect_host_version returns None, host_status is 'unknown' (line 196)."""
    p = MagicMock()
    with (
        patch("repo_release_tools.commands.eol_check.detect_host_version", return_value=None),
        patch(
            "repo_release_tools.commands.eol_check.detect_project_minimum",
            return_value="3.12.0",
        ),
        patch("repo_release_tools.commands.eol_check.get_eol_records", return_value=[]),
    ):
        all_ok = run_eol_checks(
            languages=("python",),
            root=tmp_path,
            warn_days=180,
            error_days=0,
            fetch_live=False,
            allow_eol=False,
            overrides=(),
            p=p,
        )
    # Host not detected → warn called; all_ok depends on project status
    assert all_ok  # project is ok (no records → "unknown" but not "error")


def test_run_eol_checks_project_eol_error(tmp_path: Path) -> None:
    """When project status is 'error', all_ok becomes False (line 219)."""
    p = MagicMock()
    eol_record = EolRecord(
        cycle="3.10",
        release_date=None,
        eol_date=date(2023, 10, 1),
        is_eol=True,
        days_until_eol=None,
    )
    with (
        patch(
            "repo_release_tools.commands.eol_check.detect_host_version",
            return_value="3.12.4",
        ),
        patch(
            "repo_release_tools.commands.eol_check.detect_project_minimum",
            return_value="3.10.0",
        ),
        patch(
            "repo_release_tools.commands.eol_check.get_eol_records",
            return_value=[eol_record],
        ),
    ):
        all_ok = run_eol_checks(
            languages=("python",),
            root=tmp_path,
            warn_days=180,
            error_days=0,
            fetch_live=False,
            allow_eol=False,
            overrides=(),
            p=p,
        )
    assert not all_ok


# ---------------------------------------------------------------------------
# cmd_eol — allow_eol returns 0 even when checks fail (lines 280-281)
# ---------------------------------------------------------------------------


def test_cmd_eol_allow_eol_with_failures_returns_0(tmp_path: Path) -> None:
    """allow_eol=True: even with all_ok=False, cmd_eol returns 0 (lines 280-281)."""
    eol_cfg = EolConfig(languages=("python",), warn_days=180, error_days=0, allow_eol=True)
    rrt_config = MagicMock()
    rrt_config.eol = eol_cfg

    with (
        patch(
            "repo_release_tools.commands.eol_check.load_or_autodetect_config",
            return_value=rrt_config,
        ),
        patch(
            "repo_release_tools.commands.eol_check.run_eol_checks",
            return_value=False,
        ),
        patch("pathlib.Path.cwd", return_value=tmp_path),
    ):
        result = cmd_eol(_make_args(allow_eol=True))
    assert result == 0
