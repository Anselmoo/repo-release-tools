"""Additional focused tests for docs API coverage gaps.

These target the sub-parser traversal and the branch that skips non-dict
`action.choices` values inside `build_api_index` as well as exercising
the recursion path for nested sub-commands.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from repo_release_tools.docs.api_index import build_api_index


def test_build_api_index_skips_non_dict_choices() -> None:
    """If a SubParsersAction has a non-dict .choices value, the walker should
    skip it cleanly and not raise.
    """
    parser = argparse.ArgumentParser(prog="fake", description="Top-level")
    subs = parser.add_subparsers(dest="cmd")
    subs.add_parser("one", description="one")

    # Force the SubParsersAction.choices to a non-dict value to hit the
    # defensive `isinstance(..., dict)` branch.
    sp_action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    # Force a non-dict choices value; use setattr to avoid attribute-type lint.
    setattr(sp_action, "choices", [])  # type: ignore[arg-type]

    entries = build_api_index(parser)
    # Should still return at least the root/top-level entry and not raise.
    assert any(e.name == "fake" for e in entries)


def test_build_api_index_recurses_nested_subparsers() -> None:
    """Ensure nested sub-parsers are traversed (recursion path exercised)."""
    parser = argparse.ArgumentParser(prog="tool", description="Top")
    subs = parser.add_subparsers(dest="cmd")
    a = subs.add_parser("alpha", description="alpha")
    a_sub = a.add_subparsers(dest="sub")
    inner = a_sub.add_parser("inner", description="inner")
    inner.add_argument("--opt", help="option")

    entries = build_api_index(parser)
    # Look for the nested full name used by build_api_index: "tool alpha inner"
    assert any(e.name == "tool alpha inner" for e in entries)


def test_build_api_index_skips_non_parser_choice_value() -> None:
    """When a choices dict contains a non-ArgumentParser value the walker
    should skip that member without error.
    """
    parser = argparse.ArgumentParser(prog="fake2", description="Top-level")
    subs = parser.add_subparsers(dest="cmd")
    subs.add_parser("one", description="one")

    sp_action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    # Ensure choices is a dict and inject a non-parser value under a key
    raw_choices: dict[str, object] = dict(sp_action.choices)
    raw_choices["broken"] = "not-a-parser"
    setattr(sp_action, "choices", raw_choices)  # type: ignore[arg-type]

    entries = build_api_index(parser)
    # Should not raise and should not produce an entry for the broken key
    assert any(e.name == "fake2" for e in entries)
    assert not any("broken" in e.name for e in entries)


def test_cmd_api_resolves_relative_output_path(tmp_path: Path) -> None:
    """Explicitly ensure a relative --output is written under --root.

    This directly exercises the branch that resolves relative output paths
    against the provided root (the `if not output_path.is_absolute()` line).
    """
    from repo_release_tools.commands.docs_cmd import _cmd_api

    args = argparse.Namespace(
        docs_action="api",
        format="md",
        output="out/api2.md",
        root=str(tmp_path),
        dry_run=False,
    )
    rc = _cmd_api(args)
    assert rc == 0
    expected = tmp_path / "out" / "api2.md"
    assert expected.exists()


def test_cmd_api_dry_run_resolves_relative_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dry-run with a relative --output should resolve against --root and
    emit a would_write line pointing at the resolved path.
    """
    from repo_release_tools.commands.docs_cmd import _cmd_api

    args = argparse.Namespace(
        docs_action="api",
        format="md",
        output="out/api3.md",
        root=str(tmp_path),
        dry_run=True,
    )
    rc = _cmd_api(args)
    assert rc == 0
    out = capsys.readouterr().out
    expected = str(tmp_path / "out" / "api3.md")
    assert expected in out
