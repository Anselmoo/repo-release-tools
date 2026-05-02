"""Tests for the eol module."""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from repo_release_tools.eol import (
    EolRecord,
    _extract_version,
    _find_record,
    _parse_cycle,
    _rust_lag_position,
    check_eol_status,
    detect_host_version,
    detect_project_minimum,
    fetch_live_data,
    get_eol_records,
)

# ---------------------------------------------------------------------------
# EolRecord.from_api_dict
# ---------------------------------------------------------------------------


class TestEolRecordFromApiDict:
    def test_active_cycle_false_eol(self) -> None:
        today = date(2025, 6, 1)
        entry: dict[str, object] = {
            "cycle": "3.12",
            "releaseDate": "2023-10-02",
            "eol": False,
        }
        r = EolRecord.from_api_dict(entry, today=today)
        assert r.cycle == "3.12"
        assert r.is_eol is False
        assert r.eol_date is None
        assert r.days_until_eol is None
        assert r.release_date == date(2023, 10, 2)

    def test_future_eol_date(self) -> None:
        today = date(2025, 6, 1)
        entry: dict[str, object] = {
            "cycle": "3.10",
            "releaseDate": "2021-10-04",
            "eol": "2026-10-31",
        }
        r = EolRecord.from_api_dict(entry, today=today)
        assert r.is_eol is False
        assert r.eol_date == date(2026, 10, 31)
        assert r.days_until_eol == (date(2026, 10, 31) - today).days

    def test_past_eol_date(self) -> None:
        today = date(2025, 6, 1)
        entry: dict[str, object] = {
            "cycle": "3.8",
            "eol": "2024-10-07",
            "releaseDate": "2019-10-14",
        }
        r = EolRecord.from_api_dict(entry, today=today)
        assert r.is_eol is True
        assert r.days_until_eol is None

    def test_eol_true_bool(self) -> None:
        entry: dict[str, object] = {"cycle": "2.7", "eol": True}
        r = EolRecord.from_api_dict(entry)
        assert r.is_eol is True
        assert r.eol_date is None

    def test_missing_release_date(self) -> None:
        entry: dict[str, object] = {"cycle": "3.14", "eol": "2030-10-31"}
        r = EolRecord.from_api_dict(entry)
        assert r.release_date is None
        assert r.cycle == "3.14"


# ---------------------------------------------------------------------------
# _parse_cycle
# ---------------------------------------------------------------------------


class TestParseCycle:
    @pytest.mark.parametrize(
        "version,expected",
        [
            ("3.12.4", "3.12"),
            ("3.12", "3.12"),
            ("3.12.0", "3.12"),
            ("1.26.2", "1.26"),
            ("22.14.0", "22.14"),
            ("1.95.0", "1.95"),
            ("22", "22"),
            ("invalid", None),
            ("", None),
        ],
    )
    def test_parse(self, version: str, expected: str | None) -> None:
        assert _parse_cycle(version) == expected


# ---------------------------------------------------------------------------
# _find_record
# ---------------------------------------------------------------------------


class TestFindRecord:
    @pytest.fixture()
    def records(self) -> list[EolRecord]:
        return get_eol_records("python", today=date(2025, 6, 1))

    def test_exact_match(self, records: list[EolRecord]) -> None:
        r = _find_record("3.12", records)
        assert r is not None
        assert r.cycle == "3.12"

    def test_prefix_match(self, records: list[EolRecord]) -> None:
        # Node uses single-digit cycle; "22.14" should match cycle "22"
        node_records = get_eol_records("nodejs", today=date(2025, 6, 1))
        r = _find_record("22.14", node_records)
        assert r is not None
        assert r.cycle == "22"

    def test_not_found(self, records: list[EolRecord]) -> None:
        r = _find_record("9.99", records)
        assert r is None


# ---------------------------------------------------------------------------
# get_eol_records
# ---------------------------------------------------------------------------


class TestGetEolRecords:
    def test_bundled_python(self) -> None:
        records = get_eol_records("python")
        assert len(records) > 0
        assert all(isinstance(r, EolRecord) for r in records)

    def test_bundled_nodejs(self) -> None:
        records = get_eol_records("nodejs")
        assert len(records) > 0

    def test_bundled_node_alias(self) -> None:
        records = get_eol_records("node")
        assert len(records) == len(get_eol_records("nodejs"))

    def test_bundled_go(self) -> None:
        records = get_eol_records("go")
        assert len(records) > 0

    def test_bundled_rust(self) -> None:
        records = get_eol_records("rust")
        assert len(records) > 0

    def test_unknown_language_returns_empty(self) -> None:
        records = get_eol_records("cobol")
        assert records == []

    def test_fetch_live_falls_back_to_bundled_on_error(self) -> None:
        with patch("repo_release_tools.eol.fetch_live_data", return_value=[]):
            records = get_eol_records("python", fetch_live=True)
        assert len(records) > 0  # fell back to bundled

    def test_fetch_live_uses_fetched_data(self) -> None:
        fake_entry = {"cycle": "4.0", "eol": "2035-01-01", "releaseDate": "2030-01-01"}
        with patch("repo_release_tools.eol.fetch_live_data", return_value=[fake_entry]):
            records = get_eol_records("python", fetch_live=True)
        assert any(r.cycle == "4.0" for r in records)


# ---------------------------------------------------------------------------
# fetch_live_data
# ---------------------------------------------------------------------------


class TestFetchLiveData:
    def test_returns_empty_list_on_network_error(self) -> None:
        import urllib.error

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
            result = fetch_live_data("python")
        assert result == []

    def test_parses_v1_wrapper(self) -> None:
        payload = json.dumps({"result": [{"cycle": "3.12", "eol": False}]}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = payload
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_live_data("python")
        assert result == [{"cycle": "3.12", "eol": False}]

    def test_parses_list_directly(self) -> None:
        payload = json.dumps([{"cycle": "3.12", "eol": False}]).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = payload
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_live_data("python")
        assert result == [{"cycle": "3.12", "eol": False}]

    def test_returns_empty_on_invalid_json(self) -> None:
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"not-json"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_live_data("python")
        assert result == []

    def test_returns_empty_on_unexpected_dict(self) -> None:
        payload = json.dumps({"other": "data"}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = payload
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_live_data("python")
        assert result == []


# ---------------------------------------------------------------------------
# check_eol_status
# ---------------------------------------------------------------------------


class TestCheckEolStatus:
    def _make_records(self, cycles: list[tuple[str, str | bool]]) -> list[EolRecord]:
        today = date(2025, 6, 1)
        entries: list[dict[str, object]] = [
            {"cycle": c, "eol": e, "releaseDate": "2020-01-01"} for c, e in cycles
        ]
        return [EolRecord.from_api_dict(e, today=today) for e in entries]

    def test_ok_active_cycle(self) -> None:
        today = date(2025, 6, 1)
        records = self._make_records([("3.12", False)])
        status, record = check_eol_status(
            "3.12.4", records, language="python", warn_days=180, error_days=0, today=today
        )
        assert status == "ok"
        assert record is not None

    def test_error_on_past_eol(self) -> None:
        today = date(2025, 6, 1)
        records = self._make_records([("3.8", "2024-10-07")])
        status, record = check_eol_status(
            "3.8.18", records, language="python", warn_days=180, error_days=0, today=today
        )
        assert status == "error"

    def test_warn_within_warn_days(self) -> None:
        today = date(2025, 6, 1)
        soon = (today + timedelta(days=90)).isoformat()
        records = self._make_records([("3.10", soon)])
        status, record = check_eol_status(
            "3.10.12",
            records,
            language="python",
            warn_days=180,
            error_days=0,
            today=today,
        )
        assert status == "warn"

    def test_ok_beyond_warn_days(self) -> None:
        today = date(2025, 6, 1)
        far = (today + timedelta(days=365)).isoformat()
        records = self._make_records([("3.12", far)])
        status, _ = check_eol_status(
            "3.12.4", records, language="python", warn_days=180, error_days=0, today=today
        )
        assert status == "ok"

    def test_error_within_error_days(self) -> None:
        today = date(2025, 6, 1)
        soon = (today + timedelta(days=20)).isoformat()
        records = self._make_records([("3.10", soon)])
        status, _ = check_eol_status(
            "3.10.0", records, language="python", warn_days=180, error_days=30, today=today
        )
        assert status == "error"

    def test_allow_eol_downgrades_error_to_warn(self) -> None:
        today = date(2025, 6, 1)
        records = self._make_records([("3.8", "2024-10-07")])
        status, _ = check_eol_status(
            "3.8.18",
            records,
            language="python",
            warn_days=180,
            error_days=0,
            allow_eol=True,
            today=today,
        )
        assert status == "warn"

    def test_override_eol_date(self) -> None:
        today = date(2025, 6, 1)
        # Override makes 3.8 expire far in future
        records = self._make_records([("3.8", "2024-10-07")])
        override = today + timedelta(days=400)
        status, _ = check_eol_status(
            "3.8.18",
            records,
            language="python",
            warn_days=180,
            error_days=0,
            override_eol=override,
            today=today,
        )
        assert status == "ok"

    def test_unknown_cycle(self) -> None:
        records = self._make_records([("3.12", False)])
        status, record = check_eol_status(
            "9.99.0", records, language="python", warn_days=180, error_days=0
        )
        assert status == "unknown"
        assert record is None

    def test_unparseable_version(self) -> None:
        records = self._make_records([("3.12", False)])
        status, record = check_eol_status(
            "invalid", records, language="python", warn_days=180, error_days=0
        )
        assert status == "unknown"
        assert record is None


# ---------------------------------------------------------------------------
# Rust lag-based checks
# ---------------------------------------------------------------------------


class TestRustLagCheck:
    @pytest.fixture()
    def rust_records(self) -> list[EolRecord]:
        today = date(2025, 6, 1)
        entries: list[dict[str, object]] = [
            {"cycle": "1.95", "eol": False, "releaseDate": "2026-04-16"},
            {"cycle": "1.94", "eol": "2026-04-16", "releaseDate": "2026-03-06"},
            {"cycle": "1.93", "eol": "2026-03-06", "releaseDate": "2026-01-22"},
            {"cycle": "1.92", "eol": "2026-01-22", "releaseDate": "2025-12-11"},
            {"cycle": "1.91", "eol": "2025-12-11", "releaseDate": "2025-10-30"},
        ]
        return [EolRecord.from_api_dict(e, today=today) for e in entries]

    def test_lag_position_latest(self, rust_records: list[EolRecord]) -> None:
        lag = _rust_lag_position("1.95", rust_records)
        assert lag == 0

    def test_lag_position_one_behind(self, rust_records: list[EolRecord]) -> None:
        lag = _rust_lag_position("1.94", rust_records)
        assert lag == 1

    def test_ok_on_latest(self, rust_records: list[EolRecord]) -> None:
        status, _ = check_eol_status(
            "1.95.0", rust_records, language="rust", warn_days=180, error_days=0
        )
        assert status == "ok"

    def test_warn_when_behind_by_warn_lag(self, rust_records: list[EolRecord]) -> None:
        # 1.93 is 2 behind 1.95 → RUST_WARN_LAG == 2 → warn
        status, _ = check_eol_status(
            "1.93.0", rust_records, language="rust", warn_days=180, error_days=0
        )
        assert status == "warn"

    def test_error_when_behind_by_error_lag(self, rust_records: list[EolRecord]) -> None:
        entries: list[dict[str, object]] = [
            {"cycle": "1.95", "eol": False, "releaseDate": "2026-04-16"},
            {"cycle": "1.94", "eol": "2026-04-16", "releaseDate": "2026-03-06"},
            {"cycle": "1.93", "eol": "2026-03-06", "releaseDate": "2026-01-22"},
            {"cycle": "1.92", "eol": "2026-01-22", "releaseDate": "2025-12-11"},
            {"cycle": "1.91", "eol": "2025-12-11", "releaseDate": "2025-10-30"},
            {"cycle": "1.90", "eol": "2025-10-30", "releaseDate": "2025-09-04"},
        ]
        today = date(2025, 6, 1)
        records = [EolRecord.from_api_dict(e, today=today) for e in entries]
        # 1.91 is 4 behind 1.95 → RUST_ERROR_LAG == 4 → error
        status, _ = check_eol_status(
            "1.91.0", records, language="rust", warn_days=180, error_days=0
        )
        assert status == "error"


# ---------------------------------------------------------------------------
# _extract_version
# ---------------------------------------------------------------------------


class TestExtractVersion:
    @pytest.mark.parametrize(
        "output,slug,expected",
        [
            ("v22.14.0", "nodejs", "22.14.0"),
            ("v20.0.0\n", "nodejs", "20.0.0"),
            ("go version go1.26.2 darwin/arm64", "go", "1.26.2"),
            ("go version go1.24 linux/amd64", "go", "1.24"),
            ("rustc 1.95.0 (32fc4b338 2026-04-15)", "rust", "1.95.0"),
            ("bad output", "nodejs", None),
            ("bad output", "go", None),
            ("bad output", "rust", None),
        ],
    )
    def test_extract(self, output: str, slug: str, expected: str | None) -> None:
        assert _extract_version(output, slug) == expected


# ---------------------------------------------------------------------------
# detect_host_version
# ---------------------------------------------------------------------------


class TestDetectHostVersion:
    def test_python_returns_current_version(self) -> None:
        v = detect_host_version("python")
        assert v is not None
        parts = v.split(".")
        assert len(parts) == 3
        assert int(parts[0]) == sys.version_info.major

    def test_node_calls_subprocess(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "v22.14.0"
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            v = detect_host_version("nodejs")
        mock_run.assert_called_once()
        assert v == "22.14.0"

    def test_go_calls_subprocess(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "go version go1.26.2 darwin/arm64"
        with patch("subprocess.run", return_value=mock_result):
            v = detect_host_version("go")
        assert v == "1.26.2"

    def test_rust_calls_subprocess(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "rustc 1.95.0 (32fc4b338 2026-04-15)"
        with patch("subprocess.run", return_value=mock_result):
            v = detect_host_version("rust")
        assert v == "1.95.0"

    def test_returns_none_on_subprocess_failure(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch("subprocess.run", return_value=mock_result):
            v = detect_host_version("nodejs")
        assert v is None

    def test_returns_none_when_not_found(self) -> None:
        with patch("subprocess.run", side_effect=FileNotFoundError):
            v = detect_host_version("go")
        assert v is None

    def test_unknown_language_returns_none(self) -> None:
        v = detect_host_version("cobol")
        assert v is None


# ---------------------------------------------------------------------------
# detect_project_minimum
# ---------------------------------------------------------------------------


class TestDetectProjectMinimum:
    def test_python_reads_requires_python(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nrequires-python = ">=3.12"\n', encoding="utf-8"
        )
        v = detect_project_minimum("python", tmp_path)
        assert v == "3.12"

    def test_python_no_pyproject(self, tmp_path: Path) -> None:
        v = detect_project_minimum("python", tmp_path)
        assert v is None

    def test_python_no_requires_python(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
        v = detect_project_minimum("python", tmp_path)
        assert v is None

    def test_go_reads_go_directive(self, tmp_path: Path) -> None:
        (tmp_path / "go.mod").write_text("module example.com/x\n\ngo 1.24\n", encoding="utf-8")
        v = detect_project_minimum("go", tmp_path)
        assert v == "1.24"

    def test_go_no_go_mod(self, tmp_path: Path) -> None:
        v = detect_project_minimum("go", tmp_path)
        assert v is None

    def test_nodejs_reads_engines(self, tmp_path: Path) -> None:
        data = json.dumps({"engines": {"node": ">=20.0.0"}})
        (tmp_path / "package.json").write_text(data, encoding="utf-8")
        v = detect_project_minimum("nodejs", tmp_path)
        assert v == "20.0.0"

    def test_nodejs_no_engines(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text('{"name": "x"}', encoding="utf-8")
        v = detect_project_minimum("nodejs", tmp_path)
        assert v is None

    def test_nodejs_no_package_json(self, tmp_path: Path) -> None:
        v = detect_project_minimum("nodejs", tmp_path)
        assert v is None

    def test_rust_reads_rust_version(self, tmp_path: Path) -> None:
        (tmp_path / "Cargo.toml").write_text(
            '[package]\nname = "x"\nrust-version = "1.85"\n', encoding="utf-8"
        )
        v = detect_project_minimum("rust", tmp_path)
        assert v == "1.85"

    def test_rust_no_cargo_toml(self, tmp_path: Path) -> None:
        v = detect_project_minimum("rust", tmp_path)
        assert v is None

    def test_unknown_language_returns_none(self, tmp_path: Path) -> None:
        v = detect_project_minimum("cobol", tmp_path)
        assert v is None
