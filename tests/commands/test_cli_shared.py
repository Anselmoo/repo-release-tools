"""Tests for shared `commands/_cli_shared.py` helpers."""

from __future__ import annotations

import argparse

from repo_release_tools.commands._cli_shared import add_dry_run_flag


def _dry_run_help(parser: argparse.ArgumentParser) -> str:
    action = next(a for a in parser._actions if "--dry-run" in a.option_strings)
    assert action.help is not None
    return action.help


def test_add_dry_run_flag_default_verb() -> None:
    """Defaults to the "writing files" verb when none is given."""
    parser = argparse.ArgumentParser()
    add_dry_run_flag(parser)
    assert _dry_run_help(parser) == "Preview without writing files."


def test_add_dry_run_flag_custom_verb() -> None:
    """Renders the templated help text with a custom verb."""
    parser = argparse.ArgumentParser()
    add_dry_run_flag(parser, verb="touching git")
    assert _dry_run_help(parser) == "Preview without touching git."


def test_add_dry_run_flag_help_text_override() -> None:
    """An explicit help_text wins over the templated verb form."""
    parser = argparse.ArgumentParser()
    add_dry_run_flag(parser, verb="ignored", help_text="With --reference: print without writing.")
    assert _dry_run_help(parser) == "With --reference: print without writing."


def test_add_dry_run_flag_accepts_argument_group() -> None:
    """Works on an argument group, not just a top-level parser."""
    parser = argparse.ArgumentParser()
    group = parser.add_argument_group("Release control")
    add_dry_run_flag(group, verb="writing to disk")
    assert _dry_run_help(parser) == "Preview without writing to disk."


def test_add_dry_run_flag_stores_true() -> None:
    """Parses `--dry-run` as a boolean flag defaulting to False."""
    parser = argparse.ArgumentParser()
    add_dry_run_flag(parser)
    assert parser.parse_args([]).dry_run is False
    assert parser.parse_args(["--dry-run"]).dry_run is True
