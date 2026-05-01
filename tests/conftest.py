"""Pytest configuration and UX contract enforcement for repo-release-tools tests."""

from __future__ import annotations

import ast
import re
import sys

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


# ── rrt UX contract enforcement ───────────────────────────────────────────────
# Parses the module docstring of test_user_experience_simulator.py to extract
# the declared "Affected entrypoints" list, then compares it against the live
# ArgumentParser subcommand names.  If they diverge, the entire test suite
# fails before a single test runs, making the docstring a machine-checked
# contract rather than just documentation.

_UX_SIMULATOR = ROOT / "tests" / "test_user_experience_simulator.py"
_ENTRYPOINT_LINE_RE = re.compile(r"^\s*-\s+([\w][\w-]*)")


def _parse_ux_entrypoints() -> set[str]:
    """Return subcommand names declared in the test_user_experience_simulator docstring."""
    src = _UX_SIMULATOR.read_text(encoding="utf-8")
    tree = ast.parse(src)
    docstring = ast.get_docstring(tree) or ""
    names: set[str] = set()
    for line in docstring.splitlines():
        if m := _ENTRYPOINT_LINE_RE.match(line):
            word = m.group(1)
            if word != "rrt":  # skip the native entry point itself
                names.add(word)
    return names


def _live_subcommands() -> set[str]:
    """Return the subcommand names registered in the live ArgumentParser."""
    import argparse

    from repo_release_tools.cli import build_parser

    parser = build_parser()
    subparsers = next(
        (a for a in parser._actions if isinstance(a, argparse._SubParsersAction)),
        None,
    )
    return set(subparsers._name_parser_map.keys()) if subparsers else set()  # pragma: no cover


def pytest_collection_finish(session: pytest.Session) -> None:
    """Enforce the UX simulator docstring contract against the live CLI.

    Called after all tests are collected, before any test runs.  Exits with
    ``returncode=2`` (same as an argparse error) if the documented entrypoints
    and the live subcommands disagree.
    """
    import pytest

    try:
        documented = _parse_ux_entrypoints()
        live = _live_subcommands()
    except Exception as exc:  # pragma: no cover
        pytest.exit(f"[rrt-ux-contract] Could not verify entrypoints: {exc}", returncode=3)

    missing_from_docs = live - documented
    extra_in_docs = documented - live

    if missing_from_docs or extra_in_docs:
        lines = ["", "[rrt-ux-contract] Entrypoint mismatch — fix before running tests."]
        if missing_from_docs:
            lines.append(
                f"  CLI subcommands missing from the test docstring: "
                f"{', '.join(sorted(missing_from_docs))}"
            )
            lines.append(
                "  → Add them under 'Affected entrypoints' in "
                "tests/test_user_experience_simulator.py"
            )
        if extra_in_docs:
            lines.append(
                f"  Docstring entries with no matching CLI subcommand: "
                f"{', '.join(sorted(extra_in_docs))}"
            )
            lines.append(
                "  → Either register the subcommand in cli.build_parser() "
                "or remove it from the docstring."
            )
        pytest.exit("\n".join(lines), returncode=2)
