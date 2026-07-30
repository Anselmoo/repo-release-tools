"""Tests for shared `commands/_common.py` helpers."""

from __future__ import annotations

from repo_release_tools.commands._common import (
    find_duplicate_group_names,
    parse_group_names,
)


def test_parse_group_names_splits_and_strips() -> None:
    """Splits a comma-separated value into stripped names, order preserved."""
    assert parse_group_names("alpha,beta,gamma") == ["alpha", "beta", "gamma"]
    assert parse_group_names(" alpha , beta ") == ["alpha", "beta"]


def test_parse_group_names_drops_empty_segments() -> None:
    """Drops empty/whitespace-only segments (trailing commas, doubled commas)."""
    assert parse_group_names("alpha,,beta") == ["alpha", "beta"]
    assert parse_group_names("alpha,beta,") == ["alpha", "beta"]
    assert parse_group_names(" , , ") == []
    assert parse_group_names("") == []


def test_find_duplicate_group_names_detects_repeats() -> None:
    """Returns each repeated name once, in first-seen order."""
    assert find_duplicate_group_names(["alpha", "alpha", "beta"]) == ["alpha"]
    assert find_duplicate_group_names(["a", "b", "a", "b", "c"]) == ["a", "b"]


def test_find_duplicate_group_names_empty_when_all_unique() -> None:
    """Returns an empty list when every name is unique."""
    assert find_duplicate_group_names(["alpha", "beta", "gamma"]) == []
    assert find_duplicate_group_names([]) == []
