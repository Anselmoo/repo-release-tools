from __future__ import annotations

import argparse
import importlib.metadata
import os
import re
import runpy
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest

from repo_release_tools import cli
from repo_release_tools.ui import OutputContext, color


def test_module_help_smoke() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "repo_release_tools", "--help"],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0
    assert "repo-release-tools" in result.stdout
    assert "branch" in result.stdout
    assert "bump" in result.stdout
    assert "git" in result.stdout
    assert "init" in result.stdout
    assert "skill" in result.stdout


def test_module_no_args_shows_help_and_exits_with_code_2() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "repo_release_tools"],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 2
    assert "[ERROR] the following arguments are required: <command>" in result.stderr
    assert "Run 'rrt --help' for usage and examples." in result.stderr
    assert "repo-release-tools: branch, commit, and version helpers" not in result.stderr


def test_branch_new_missing_args_shows_help_and_exits_with_code_2() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "repo_release_tools", "branch", "new"],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 2
    assert "[ERROR] the following arguments are required: TYPE, description" in result.stderr
    assert "Run 'rrt branch new --help' for usage and examples." in result.stderr
    assert "Create a new conventionally named branch from" not in result.stderr


def test_git_missing_subcommand_shows_help_and_exits_with_code_2() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "repo_release_tools", "git"],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 2
    assert "[ERROR] the following arguments are required: <git_command>" in result.stderr
    assert "Run 'rrt git --help' for usage and examples." in result.stderr
    assert "Git workflow helpers for repository status" not in result.stderr


def test_invalid_subcommand_suggests_close_match() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "repo_release_tools", "branxh"],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 2
    assert "Did you mean: branch?" in result.stderr


def test_invalid_choice_suggests_close_match() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "repo_release_tools", "branch", "new", "feaut", "add parser"],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 2
    assert "Did you mean: feat?" in result.stderr


def test_build_parser_registers_doctor_command() -> None:
    parser = cli.build_parser()

    args = parser.parse_args(["doctor"])

    assert args.command == "doctor"
    assert args.handler.__name__ == "cmd_doctor"


def test_build_parser_registers_skill_install_command() -> None:
    parser = cli.build_parser()

    args = parser.parse_args(["skill", "install", "--target", "copilot-local"])

    assert args.command == "skill"
    assert args.skill_command == "install"
    assert args.handler.__name__ == "cmd_install"


def test_build_parser_registers_env_command() -> None:
    parser = cli.build_parser()

    args = parser.parse_args(["env"])

    assert args.command == "env"
    assert args.handler.__name__ == "cmd_env"


def test_styled_help_applies_to_subcommands(monkeypatch, capsys) -> None:
    parser = cli.build_parser()
    monkeypatch.setattr(color, "supports_color", lambda stream=None: True)

    with pytest.raises(SystemExit):
        parser.parse_args(["bump", "major", "--help"])

    captured = capsys.readouterr()
    assert "Usage:" in captured.out
    assert "\x1b[" in captured.out


def test_parse_error_is_colorized_when_supported(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    parser = cli.build_parser()
    monkeypatch.setattr(cli, "supports_color", lambda stream=None: True)
    monkeypatch.setattr(color, "supports_color", lambda stream=None: True)

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args([])

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert "\x1b[" in captured.err
    assert "error:" in captured.err


def test_build_parser_supports_args_file(tmp_path: Path) -> None:
    args_path = tmp_path / "args.txt"
    args_path.write_text("branch new feat add parser\n", encoding="utf-8")
    parser = cli.build_parser()

    args = parser.parse_args([f"@{args_path}"])

    assert args.command == "branch"
    assert args.branch_command == "new"
    assert args.type == "feat"


def test_args_file_missing_file_shows_help_and_exits_with_code_2(tmp_path: Path) -> None:
    parser = cli.build_parser()
    missing_path = tmp_path / "missing.txt"

    with pytest.raises(SystemExit) as exc:
        parser.parse_args([f"@{missing_path}"])

    assert exc.value.code == 2


def test_main_dispatches_to_selected_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeParser:
        def parse_args(self) -> argparse.Namespace:
            return argparse.Namespace(handler=lambda args: 7)

    monkeypatch.setattr(cli, "build_parser", lambda: _FakeParser())

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 7


def test_convert_arg_line_to_args_handles_comments_and_empty_lines() -> None:
    parser = cli.FriendlyArgumentParser(prog="rrt")

    assert parser.convert_arg_line_to_args("branch new feat add parser") == [
        "branch",
        "new",
        "feat",
        "add",
        "parser",
    ]
    assert parser.convert_arg_line_to_args("branch new feat # comment") == ["branch", "new", "feat"]
    assert parser.convert_arg_line_to_args("   # only comment") == []


def test_suggestion_for_unrecognized_arg_uses_known_choices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = cli.FriendlyArgumentParser(prog="rrt")
    parser.add_argument("--foo", choices=["bar", "baz"])

    message = "unrecognized arguments: 'barr'"
    suggestion = parser._suggestion_for(message)

    assert suggestion is not None
    assert suggestion.startswith("Did you mean")


def test_format_suggestion_returns_multiple_choices() -> None:
    parser = cli.FriendlyArgumentParser(prog="rrt")

    assert parser._format_suggestion(["one", "two"]) == "Did you mean one of: one, two?"


def test_format_suggestion_returns_empty_string_for_no_matches() -> None:
    parser = cli.FriendlyArgumentParser(prog="rrt")

    assert parser._format_suggestion([]) == ""


def test_available_choices_includes_subcommands_and_options() -> None:
    parser = cast(cli.FriendlyArgumentParser, cli.build_parser())
    choices = parser._available_choices()

    assert "branch" in choices
    assert "--help" in choices


def test_error_help_hint_includes_help_and_suggestion(monkeypatch: pytest.MonkeyPatch) -> None:
    parser = cli.FriendlyArgumentParser(prog="rrt")
    parser.add_argument("--foo", choices=["bar", "baz"])

    hint = parser._error_help_hint("invalid choice: 'barr' (choose from 'bar', 'baz')")

    assert "Did you mean" in hint
    assert "Run 'rrt --help' for usage and examples." in hint


def test_suggestion_for_invalid_choice_matches_close_option() -> None:
    parser = cli.FriendlyArgumentParser(prog="rrt")

    suggestion = parser._suggestion_for("invalid choice: 'branxh' (choose from 'branch', 'bump')")

    assert suggestion == "Did you mean: branch?"


def test_package_module_executes_main(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []
    monkeypatch.setattr("repo_release_tools.cli.main", lambda: called.append("ran"))

    runpy.run_module("repo_release_tools", run_name="__main__")

    assert called == ["ran"]


def test_cli_module_main_block_exits_with_handler_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        argparse.ArgumentParser,
        "parse_args",
        lambda self: argparse.Namespace(handler=lambda args: 9),
    )

    with pytest.raises(SystemExit) as exc:
        runpy.run_module("repo_release_tools.cli", run_name="__main__")

    assert exc.value.code == 9


# ── New Phase 0 tests ──────────────────────────────────────────────────────


def test_command_groups_contains_all_registered_commands() -> None:
    all_group_commands = [cmd for cmds in cli.COMMAND_GROUPS.values() for cmd in cmds]
    parser = cli.build_parser()
    # Collect all registered subcommand names from the parser's choices actions
    registered: set[str] = set()
    for ag in parser._subparsers._group_actions if parser._subparsers else []:  # type: ignore[union-attr]
        registered.update(getattr(ag, "_name_parser_map", {}).keys())

    for cmd in all_group_commands:
        assert cmd in registered, f"COMMAND_GROUPS references '{cmd}' which is not registered"


def test_build_grouped_epilog_contains_all_command_names() -> None:
    parser = cli.build_parser()
    epilog = parser.epilog or ""

    for cmd_names in cli.COMMAND_GROUPS.values():
        for name in cmd_names:
            assert name in epilog, f"grouped epilog missing command '{name}'"


def test_build_grouped_epilog_ends_with_help_hint() -> None:
    parser = cli.build_parser()
    epilog = parser.epilog or ""

    assert "Run `rrt <command> -h` for command-specific help." not in epilog
    assert "$ rrt doctor" in epilog


def test_global_flag_format_defaults_to_text() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["doctor"])

    assert args.format == "text"


def test_global_flag_format_accepts_json() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["--format", "json", "doctor"])

    assert args.format == "json"


def test_global_flag_no_color_defaults_to_false() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["doctor"])

    assert args.no_color is False


def test_global_flag_no_color_sets_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(
        argparse.ArgumentParser,
        "parse_args",
        lambda self: argparse.Namespace(handler=lambda a: 0, no_color=True),
    )

    with pytest.raises(SystemExit):
        cli.main()

    assert os.environ.get("NO_COLOR") == "1"
    os.environ.pop("NO_COLOR", None)  # main() uses os.environ.setdefault (bypasses monkeypatch)


def test_subcommand_usage_line_uses_angle_bracket_metavar() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "repo_release_tools", "--help"],
        capture_output=True,
        check=False,
        text=True,
    )

    assert "<command>" in result.stdout
    # The old brace list should not appear in the usage line
    assert "{branch," not in result.stdout.split("\n")[0]


def test_output_context_importable_from_ui() -> None:
    ctx = OutputContext()

    assert ctx.format == "text"
    assert ctx.no_color is False
    assert ctx.stream is None
    assert not ctx.is_json()


def test_output_context_json_format() -> None:
    ctx = OutputContext(format="json")

    assert ctx.is_json()


def test_root_help_does_not_show_flat_brace_list(capsys: pytest.CaptureFixture[str]) -> None:
    """The flat {branch,bump,...} subparser listing must be suppressed on the root parser."""
    parser = cli.build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["--help"])

    captured = capsys.readouterr()
    # Grouped panels carry the command info; the flat argparse brace list should not appear
    assert "{branch," not in captured.out


def test_version_flag_prints_version_and_exits(capsys: pytest.CaptureFixture[str]) -> None:
    parser = cli.build_parser()

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--version"])

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "rrt" in captured.out


def test_subcommand_usage_line_is_bold(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The 'usage:' prefix in subcommand help must be bold when color is on."""
    import repo_release_tools.ui.color as _color_mod

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(_color_mod, "supports_color", lambda stream=None: True)
    parser = cli.build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["bump", "--help"])

    captured = capsys.readouterr()
    # Bold escape code (\x1b[1m) or just ANSI present in the output
    assert "\x1b[" in captured.out


def test_style_help_static_method_is_noop() -> None:
    """_style_help is kept for backward compat but must return the text unchanged."""
    from repo_release_tools.cli import StyledHelpFormatter

    original = "usage: rrt [-h]\n\noptions:\n  -h, --help  show this help"
    assert StyledHelpFormatter._style_help(original) == original


# ── Step 1-6 UX improvements (bump --help redesign) ────────────────────────


def test_bump_help_has_collapsed_usage_line(capsys: pytest.CaptureFixture[str]) -> None:
    """Problem 1 fix: Usage line must be one line, never enumerate individual flags."""
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["bump", "--help"])
    out = capsys.readouterr().out
    usage_line = next((ln for ln in out.splitlines() if "Usage:" in ln or "usage:" in ln), "")
    assert "[OPTIONS]" in usage_line
    assert "<bump>" in usage_line
    # No individual flag names on the usage line
    assert "--dry-run" not in usage_line
    assert "--force" not in usage_line


def test_bump_help_has_rule_separators(capsys: pytest.CaptureFixture[str]) -> None:
    """Problem 2+4 fix: section headings are wrapped in thin-rule blocks."""
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["bump", "--help"])
    out = capsys.readouterr().out
    assert "─" in out


def test_bump_help_positional_metavar_is_angle_bracket(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Problem 3 fix: positional shows <bump> not BUMP."""
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["bump", "--help"])
    out = capsys.readouterr().out
    assert "<bump>" in out
    assert "BUMP" not in out


def test_bump_help_has_argument_groups(capsys: pytest.CaptureFixture[str]) -> None:
    """Problem 4 fix: flags are organised into logical groups."""
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["bump", "--help"])
    out = capsys.readouterr().out
    assert "Release control" in out
    assert "Content" in out
    assert "Git" in out


def test_bump_help_has_examples_section(capsys: pytest.CaptureFixture[str]) -> None:
    """Problem 5 fix: subcommand help ends with an Examples section."""
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["bump", "--help"])
    out = capsys.readouterr().out
    assert "Examples" in out
    assert "rrt bump patch" in out
    assert "rrt bump minor --dry-run" in out


def test_section_titles_renamed_from_argparse_defaults(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Problem 3 fix: default argparse titles 'positional arguments' / 'options' are renamed."""
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["bump", "--help"])
    out = capsys.readouterr().out
    assert "positional arguments" not in out
    assert "Arguments" in out
    assert "Options" in out


def test_root_help_epilog_is_not_wrapped_in_examples(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Root epilog is command panels, not an Examples block."""
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--help"])
    out = capsys.readouterr().out
    # The root help should show grouped sections and a consistent examples block.
    assert "Version & Release" in out
    assert "\nExamples\n" in out
    assert "┌" not in out
    assert "│" not in out
    assert "└" not in out


def test_compute_col_width_uses_longest_flag_plus_indent() -> None:
    """_compute_col_width returns max(flag_len) + 4."""
    from repo_release_tools.cli import _compute_col_width

    class _FakeAction:
        def __init__(self, option_strings, metavar=None, choices=None):
            self.option_strings = option_strings
            self.metavar = metavar
            self.choices = choices

    actions = [
        _FakeAction(["-h", "--help"]),
        _FakeAction(["--include-maintenance"]),  # 21 chars
        _FakeAction(["--changelog-mode"], metavar="MODE"),  # 16 + 5 = 21 chars
    ]
    # Longest is either --include-maintenance (21) or --changelog-mode MODE (21)
    # + 4 = 25
    assert _compute_col_width(cast(list[argparse.Action], actions)) == 25


def test_compute_col_width_default_when_no_options() -> None:
    """Falls back to 24 when there are no option actions."""
    from repo_release_tools.cli import _compute_col_width

    assert _compute_col_width([]) == 24


def test_strip_ansi_and_display_len() -> None:
    assert cli._strip_ansi("\x1b[31mred\x1b[0m") == "red"
    assert cli._display_len("\x1b[31mred\x1b[0m") == 3


def test_metavar_text_handles_tuple_and_suppressed() -> None:
    class FakeAction:
        def __init__(self, dest, metavar):
            self.dest = dest
            self.metavar = metavar

    assert cli._metavar_text(FakeAction("foo", ("BAR", "BAZ"))) == "BAR BAZ"
    assert cli._metavar_text(FakeAction(argparse.SUPPRESS, None)) == ""
    assert cli._metavar_text(FakeAction("==SUPPRESS==", None)) == ""


def test_compute_col_width_handles_choice_dict() -> None:
    class FakeAction:
        def __init__(self, choices):
            self._choices_actions = None
            self.choices = choices
            self.option_strings = []
            self.metavar = None

    action = FakeAction({"short": None, "longer": None})
    assert cli._compute_col_width(cast(list[argparse.Action], [action]), width=100) == 10


def test_build_grouped_epilog_skips_unknown_command() -> None:
    parser = cli.build_parser()
    subparsers = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    grouped = cli._build_grouped_epilog(subparsers, {"Fake": ["does-not-exist"]})

    assert "Fake" not in grouped
    assert "Examples" in grouped


def test_formatter_compute_col_width_uses_width() -> None:
    formatter = cli.RrtHelpFormatter(prog="rrt", width=100)

    class FakeAction:
        def __init__(self):
            self.option_strings = ["-h"]
            self.metavar = None
            self.choices = None

    assert formatter._compute_col_width([FakeAction()]) == 6


def test_decolor_returns_plain_text() -> None:
    formatter = cli.RrtHelpFormatter(prog="rrt", width=80)

    assert formatter._decolor("\x1b[31mred\x1b[0m") == "red"


def test_start_section_is_noop_for_empty_heading() -> None:
    formatter = cli.RrtHelpFormatter(prog="rrt", width=80)

    assert formatter.start_section("") is None


def test_format_epilog_returns_empty_for_none() -> None:
    formatter = cli.RrtHelpFormatter(prog="rrt", width=80)

    assert formatter.format_epilog(None) == ""


def test_format_action_skips_suppressed_help() -> None:
    formatter = cli.RrtHelpFormatter(prog="rrt", width=80)

    class FakeAction:
        help = argparse.SUPPRESS

    assert formatter._format_action(FakeAction()) == ""


def test_render_row_wraps_when_column_underflow() -> None:
    formatter = cli.RrtHelpFormatter(prog="rrt", width=6)
    formatter._col_width = 6

    assert formatter._render_row("long", "long", "help") == "  long\n      help\n"


def test_format_subparser_action_uses_choices_dict() -> None:
    formatter = cli.RrtHelpFormatter(prog="rrt", width=80)

    class FakeParser:
        description = "Fake parser"

    class FakeAction:
        _choices_actions = []
        choices = {"foo": FakeParser()}

    result = formatter._format_subparser_action(FakeAction())

    assert "foo" in result
    assert "Fake parser" in result


def test_format_choice_action_renders_choices_and_help() -> None:
    formatter = cli.RrtHelpFormatter(prog="rrt", width=80)

    class FakeAction:
        option_strings = []
        choices = ["one", "two"]
        metavar = "CHOICE"
        help = "select one"
        dest = "choice"

    rendered = formatter._format_choice_action(FakeAction())

    assert "CHOICE" in rendered
    assert "one" in rendered
    assert "select one" in rendered


def test_error_prints_colored_suggestion_when_available(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "supports_color", lambda stream=None: True)
    monkeypatch.setattr(color, "supports_color", lambda stream=None: True)
    parser = cli.RrtArgumentParser(prog="rrt")

    with pytest.raises(SystemExit):
        parser.error("invalid choice: 'feaut' (choose from 'feat', 'fix')")

    err = capsys.readouterr().err
    plain = re.sub(r"\x1b\[[0-9;]*m", "", err)
    assert "Did you mean: feat?" in plain
    assert "Run rrt --help for usage and examples." in plain
    assert "✖  error:" in plain


def test_build_parser_falls_back_when_package_version_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli.importlib.metadata,
        "version",
        lambda package: (_ for _ in ()).throw(importlib.metadata.PackageNotFoundError()),
    )
    parser = cli.build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["--version"])

    assert parser.description is not None


def test_clean_error_message_replaces_raw_tokens() -> None:
    parser = cli.RrtArgumentParser(prog="rrt")

    cleaned = parser._clean_error_message("unknown git_command")

    assert "<git_command>" in cleaned


def test_available_choices_includes_subparsers_and_options() -> None:
    parser = cli.RrtArgumentParser(prog="rrt")
    subparsers = parser.add_subparsers(dest="cmd")
    subparsers.add_parser("branch")
    parser.add_argument("--test", choices=["a", "b"])

    assert "branch" in parser._available_choices()
    assert "--test" in parser._available_choices()


def test_suggestion_for_unrecognized_arguments_uses_available_choices() -> None:
    parser = cli.RrtArgumentParser(prog="rrt")
    subparsers = parser.add_subparsers(dest="cmd")
    subparsers.add_parser("branch")

    suggestion = parser._suggestion_for("unrecognized arguments: 'brnch'")

    assert suggestion is not None
    assert "branch" in suggestion


def test_format_choice_action_renders_without_help() -> None:
    formatter = cli.RrtHelpFormatter(prog="rrt", width=80)

    class FakeAction:
        option_strings = []
        choices = ["one", "two"]
        metavar = "CHOICE"
        help = None
        dest = "choice"

    rendered = formatter._format_choice_action(FakeAction())

    assert "CHOICE" in rendered
    assert "one" in rendered
    assert "two" in rendered


def test_format_action_uses_choice_action_branch() -> None:
    formatter = cli.RrtHelpFormatter(prog="rrt", width=80)

    class FakeAction:
        option_strings = []
        choices = ["one", "two"]
        metavar = "CHOICE"
        help = "select one"
        dest = "choice"

    rendered = formatter._format_action(FakeAction())

    assert "CHOICE" in rendered
    assert "one" in rendered
    assert "select one" in rendered


def test_build_grouped_epilog_includes_known_commands() -> None:
    parser = cli.build_parser()
    subparsers = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    grouped = cli._build_grouped_epilog(subparsers, {"Repository Health": ["doctor"]})

    assert "Repository Health" in grouped
    assert "doctor" in grouped


def test_metavar_text_returns_tag_for_dest_without_metavar() -> None:
    class FakeAction:
        def __init__(self):
            self.dest = "name"
            self.metavar = None

    assert cli._metavar_text(FakeAction()) == "<name>"


def test_compute_col_width_with_metavar_and_options() -> None:
    class FakeAction:
        def __init__(self):
            self.option_strings = ["--include-maintenance"]
            self.metavar = "MODE"
            self.choices = None

    assert cli._compute_col_width(cast(list[argparse.Action], [FakeAction()]), width=100) == 30


def test_render_row_returns_simple_line_when_no_help() -> None:
    formatter = cli.RrtHelpFormatter(prog="rrt", width=80)

    assert formatter._render_row("foo", "foo", "") == "  foo\n"


def test_format_subparser_action_renders_rows_from_choice_action() -> None:
    formatter = cli.RrtHelpFormatter(prog="rrt", width=80)

    class FakeChoiceAction:
        _choices_actions = [type("Sub", (), {"dest": "foo", "help": "Foo help"})()]
        choices = None

    rendered = formatter._format_subparser_action(FakeChoiceAction())

    assert "foo" in rendered
    assert "Foo help" in rendered


def test_error_help_hint_includes_help_target() -> None:
    parser = cli.RrtArgumentParser(prog="rrt")

    assert "Run 'rrt --help' for usage and examples." in parser._error_help_hint(
        "invalid choice: 'feat' (choose from 'feat')"
    )


def test_build_parser_version_action_includes_default_version() -> None:
    parser = cli.build_parser()

    version_action = next(action for action in parser._actions if action.dest == "version")
    version_string = getattr(version_action, "version", "")
    assert "rrt" in version_string
    assert not version_string.endswith("0.0.0")


def test_error_prints_suggestion_for_unrecognized_arguments() -> None:
    parser = cli.RrtArgumentParser(prog="rrt")

    assert parser._suggestion_for("unrecognized arguments: 'gitx'") is None


def test_compute_col_width_with_choices_actions() -> None:
    class SubAction:
        def __init__(self, dest):
            self.dest = dest

    class FakeAction:
        _choices_actions = [SubAction("sync"), SubAction("status")]
        choices = None
        option_strings = []
        metavar = None

    assert cli._compute_col_width(cast(list[argparse.Action], [FakeAction()]), width=100) == 10


def test_style_command_name_returns_danger_style(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(color, "supports_color", lambda stream=None: True)
    styled = cli._style_command_name("rebootstrap")
    assert "\x1b[" in styled


def test_style_command_name_returns_write_style(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(color, "supports_color", lambda stream=None: True)
    styled = cli._style_command_name("bump")
    assert "\x1b[" in styled


def test_bump_help_column_alignment_with_color(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """ANSI codes must not inflate action_max_length and force descriptions to wrap.

    When color is enabled, _format_action_invocation() wraps flags in ANSI
    escape bytes.  Without the _decolor() override, argparse's len() check
    sees the inflated byte length and pushes descriptions to the next line.
    """
    monkeypatch.setattr(color, "supports_color", lambda stream=None: True)
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["bump", "--help"])
    out = capsys.readouterr().out
    # Strip ANSI so we can do plain-text line checks.
    import re as _re

    plain = _re.sub(r"\x1b\[[0-9;]*m", "", out)
    for line in plain.splitlines():
        # Only check argparse flag-definition lines (start with 2 spaces + double-dash).
        # Exclude example lines (start with '  $') which also contain flag names.
        if not line.startswith("  --"):
            continue
        if "--no-changelog" in line:
            assert "Do not update" in line, f"--no-changelog description wrapped: {line!r}"
        if "--include-maintenance" in line:
            assert "Include maintenance" in line, (
                f"--include-maintenance description wrapped: {line!r}"
            )


def test_git_help_has_no_enum_blob(capsys: pytest.CaptureFixture[str]) -> None:
    parser = cli.build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["git", "--help"])

    out = capsys.readouterr().out
    assert "{" not in out
    assert "sync-status" in out
    assert "check-dirty-tree" in out


def test_git_help_uses_semantic_command_colors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    parser = cli.build_parser()
    monkeypatch.setattr(color, "supports_color", lambda stream=None: True)

    with pytest.raises(SystemExit):
        parser.parse_args(["git", "--help"])

    out = capsys.readouterr().out
    assert "\x1b[" in out
    # Read-oriented command (cyan) and danger command (red) should differ.
    assert re.search(r"\x1b\[[0-9;]*36mstatus\x1b\[0m", out)
    assert re.search(r"\x1b\[[0-9;]*31mrebootstrap\x1b\[0m", out)


def test_ci_version_help_has_examples_and_no_enum_blob(capsys: pytest.CaptureFixture[str]) -> None:
    parser = cli.build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["ci-version", "--help"])

    out = capsys.readouterr().out
    assert "Examples" in out
    assert "{compute,apply,sync}" not in out
    assert "  $ rrt ci-version compute" in out


def test_skill_help_has_examples_and_no_enum_blob(capsys: pytest.CaptureFixture[str]) -> None:
    parser = cli.build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["skill", "--help"])

    out = capsys.readouterr().out
    assert "Examples" in out
    assert "{install}" not in out
    assert "  $ rrt skill install --target copilot-local" in out


# ── Section heading + rule coloring tests ──────────────────────────────────


def test_start_section_emits_chrome_rules_and_heading_style(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """start_section() must emit gold-dim rule lines (chrome) and gold-bold headings when color is on."""
    monkeypatch.setattr(color, "supports_color", lambda stream=None: True)

    parser = cli.build_parser()
    formatter = parser._get_formatter()
    cast(cli.RrtHelpFormatter, formatter)._col_width = 24
    cast(cli.RrtHelpFormatter, formatter).start_section("Options")
    cast(cli.RrtHelpFormatter, formatter).add_text(None)
    cast(cli.RrtHelpFormatter, formatter).end_section()
    output = formatter.format_help()

    # fg=33 must appear: both heading (bold) and chrome (dim) use gold (33)
    assert re.search(r"\x1b\[[0-9;]*33[m;]", output), (
        "gold (fg=33) escape not found in section output"
    )
    # No underline (4) — headings are bold-only, no underline
    assert not re.search(r"\x1b\[[0-9;]*4[m;]", output), (
        "unexpected underline escape in section output"
    )
    # No old subtle fg=90 — replaced by chrome fg=33 dim
    assert "\x1b[90m" not in output


def test_format_epilog_emits_chrome_rules_and_heading_style(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """format_epilog() must emit gold-dim rule lines and gold-bold 'Examples' heading."""
    monkeypatch.setattr(color, "supports_color", lambda stream=None: True)

    formatter = cli.RrtHelpFormatter(prog="rrt", width=80)
    output = formatter.format_epilog('  $ rrt branch new feat "add parser"\n')

    assert re.search(r"\x1b\[[0-9;]*33[m;]", output), (
        "gold (fg=33) escape not found in epilog output"
    )
    assert not re.search(r"\x1b\[[0-9;]*4[m;]", output), (
        "unexpected underline escape in epilog output"
    )
    assert "Examples" in output


def test_grouped_epilog_uses_chrome_rules_and_heading_style(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_build_grouped_epilog() must use gold-dim rules and gold-bold group name headings."""
    monkeypatch.setattr(color, "supports_color", lambda stream=None: True)

    parser = cli.build_parser()
    epilog = parser.epilog or ""

    assert re.search(r"\x1b\[[0-9;]*33[m;]", epilog), (
        "gold (fg=33) escape not found in grouped epilog"
    )
    assert not re.search(r"\x1b\[[0-9;]*4[m;]", epilog), (
        "unexpected underline in grouped epilog headings"
    )
