"""Tests for CalVer helpers."""

from __future__ import annotations

import datetime as dt
from unittest.mock import patch

import pytest

from repo_release_tools.version.calver import CalVersion


def test_today_yyyy_mm() -> None:
    v = CalVersion.today("YYYY.MM")
    assert v.scheme == "YYYY.MM"
    assert v.day is None
    assert v.year >= 2024


def test_today_yyyy_mm_dd() -> None:
    v = CalVersion.today("YYYY.MM.DD")
    assert v.scheme == "YYYY.MM.DD"
    assert v.day is not None


def test_today_unknown_scheme_raises() -> None:
    with pytest.raises(ValueError, match="Unknown CalVer scheme"):
        CalVersion.today("INVALID")


def test_parse_invalid_raises() -> None:
    with pytest.raises(ValueError, match="Invalid CalVer"):
        CalVersion.parse("not-a-calver")


def test_parse_yyyy_mm() -> None:
    v = CalVersion.parse("2026.05")
    assert v.year == 2026
    assert v.month == 5
    assert v.day is None
    assert v.scheme == "YYYY.MM"


def test_parse_yyyy_mm_dd_padded() -> None:
    v = CalVersion.parse("2026.05.07")
    assert v.scheme == "YYYY.MM.DD"
    assert v.day == 7


def test_parse_yyyy_m_d_unpadded() -> None:
    v = CalVersion.parse("2026.5.15")
    assert v.scheme == "YYYY.M.D"
    assert v.day == 15


def test_parse_with_micro() -> None:
    v = CalVersion.parse("2026.05.15.3")
    assert v.micro == 3


def test_str_yyyy_mm() -> None:
    v = CalVersion(year=2026, month=5, scheme="YYYY.MM")
    assert str(v) == "2026.05"


def test_str_yyyy_mm_dd() -> None:
    v = CalVersion(year=2026, month=5, day=7, scheme="YYYY.MM.DD")
    assert str(v) == "2026.05.07"


def test_str_yyyy_m_d() -> None:
    v = CalVersion(year=2026, month=5, day=15, scheme="YYYY.M.D")
    assert str(v) == "2026.5.15"


def test_str_with_micro() -> None:
    v = CalVersion(year=2026, month=5, day=15, micro=2, scheme="YYYY.MM.DD")
    assert str(v) == "2026.05.15.2"


def test_str_yyyy_mm_with_micro() -> None:
    v = CalVersion(year=2026, month=5, micro=1, scheme="YYYY.MM")
    assert str(v) == "2026.05.1"


_FIXED_DATE = dt.date(2026, 5, 15)


def test_bump_same_date_increments_micro() -> None:
    with patch("repo_release_tools.version.calver.dt") as mock_dt:
        mock_dt.datetime.now.return_value.date.return_value = _FIXED_DATE
        mock_dt.UTC = dt.UTC
        v = CalVersion(year=2026, month=5, day=15, scheme="YYYY.MM.DD")
        bumped = v.bump()
    assert bumped.micro == 1
    assert bumped.year == 2026


def test_bump_same_date_increments_existing_micro() -> None:
    with patch("repo_release_tools.version.calver.dt") as mock_dt:
        mock_dt.datetime.now.return_value.date.return_value = _FIXED_DATE
        mock_dt.UTC = dt.UTC
        v = CalVersion(year=2026, month=5, day=15, micro=2, scheme="YYYY.MM.DD")
        bumped = v.bump()
    assert bumped.micro == 3


def test_bump_different_date_no_micro() -> None:
    future = dt.date(2026, 6, 1)
    with patch("repo_release_tools.version.calver.dt") as mock_dt:
        mock_dt.datetime.now.return_value.date.return_value = future
        mock_dt.UTC = dt.UTC
        v = CalVersion(year=2026, month=5, day=15, scheme="YYYY.MM.DD")
        bumped = v.bump()
    assert bumped.micro is None
    assert bumped.month == 6


def test_bump_yyyy_mm_same_month() -> None:
    with patch("repo_release_tools.version.calver.dt") as mock_dt:
        mock_dt.datetime.now.return_value.date.return_value = _FIXED_DATE
        mock_dt.UTC = dt.UTC
        v = CalVersion(year=2026, month=5, scheme="YYYY.MM")
        bumped = v.bump()
    assert bumped.micro == 1
    assert bumped.day is None
