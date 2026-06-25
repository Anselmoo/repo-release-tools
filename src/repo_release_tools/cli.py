"""CLI entrypoint for rrt."""

from __future__ import annotations

import argparse
import difflib
import importlib.metadata
import os
import re
import sys
from collections.abc import Callable, Iterable
from typing import IO, Any, NoReturn, cast

from repo_release_tools.assets.banner import get_cached_banner
from repo_release_tools.commands import (
    agents_cmd,
    artifacts_cmd,
    branch,
    bump,
    changelog_cmd,
    ci_version,
    config_cmd,
    docs_cmd,
    doctor,
    drift_cmd,
    env_cmd,
    eol_check,
    folder,
    git_cmd,
    hooks_cmd,
    init,
    install_cmd,
    mcp_cmd,
    project_cmd,
    release_cmd,
    skill,
    sync_cmd,
    tag,
    toc,
    tree,
    workspace,
)
from repo_release_tools.commands.action_cmd import register as action_register
from repo_release_tools.ui import (
    IS_LEGACY_TERMINAL,
    Style,
    VerbosePrinter,
    apply_style,
    bold,
    chrome,
    cli_error,
    rule,
    subtle,
    supports_color,
    terminal_width,
)
from repo_release_tools.ui import (
    heading as heading_style,
)

_ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def _strip_ansi(text: str) -> str:
    """Return *text* without ANSI escape sequences."""
    return _ANSI_RE.sub("", text)


def _display_len(text: str) -> int:
    """Return the visible width of help-column text."""
    return len(_strip_ansi(text))


def _metavar_text(action: argparse.Action) -> str:
    """Return the display metavar for an argparse action."""
    metavar = action.metavar
    if isinstance(metavar, tuple):
        return " ".join(str(part) for part in metavar)
    if metavar is not None:
        return str(metavar)
    if action.dest in (argparse.SUPPRESS, "==SUPPRESS=="):
        return ""
    return f"<{action.dest}>"


def _compute_col_width(actions: list[argparse.Action], width: int | None = None) -> int:
    """Return the left-column width for a parser's action list."""
    max_left = 0
    for action in actions:
        if choices_actions := getattr(action, "_choices_actions", None):
            for sub in choices_actions:
                max_left = max(max_left, len(str(sub.dest)))
            continue
        action_choices = getattr(action, "choices", None)
        if action_choices and isinstance(action_choices, dict):
            for name in action_choices:
                max_left = max(max_left, len(str(name)))
            continue
        if action.option_strings:
            flags = ", ".join(action.option_strings)
            metavar = f" {_metavar_text(action)}" if action.metavar else ""
            max_left = max(max_left, len(flags + metavar))
            continue
        max_left = max(max_left, len(_metavar_text(action)))

    if max_left == 0:
        return 24

    total_width = width if width is not None else terminal_width()
    return min(2 + max_left + 2, total_width // 2)


COMMAND_GROUPS: dict[str, list[str]] = {
    "Version & Release": ["bump", "changelog", "ci-version", "release", "sync", "workspace", "tag"],
    "Repository Health": [
        "doctor",
        "artifacts",
        "config",
        "env",
        "eol",
        "toc",
        "tree",
        "docs",
        "drift",
        "folder",
    ],
    "CI & Automation": ["action"],
    "Git Workflow": ["branch", "git"],
    "Setup & Tooling": ["install", "init", "skill", "agents", "hooks"],
}

READ_COMMANDS = {
    "status",
    "diff",
    "log",
    "doctor",
    "release",
    "sync-status",
    "check-dirty-tree",
    "config",
    "env",
}

WRITE_COMMANDS = {
    "action",
    "agents",
    "branch",
    "bump",
    "ci-version",
    "drift",
    "git",
    "hooks",
    "init",
    "install",
    "skill",
    "commit",
    "commit-all",
    "sync",
    "move",
    "squash-local",
}

DANGER_COMMANDS = {
    "undo-safe",
    "rebootstrap",
}

COMMAND_REGISTRARS = (
    agents_cmd.register,
    artifacts_cmd.register,
    branch.register,
    bump.register,
    changelog_cmd.register,
    ci_version.register,
    action_register,
    config_cmd.register,
    doctor.register,
    drift_cmd.register,
    env_cmd.register,
    eol_check.register,
    folder.register,
    git_cmd.register,
    hooks_cmd.register,
    init.register,
    install_cmd.register,
    mcp_cmd.register,
    project_cmd.register,
    release_cmd.register,
    skill.register,
    sync_cmd.register,
    tag.register,
    toc.register,
    tree.register,
    docs_cmd.register,
    workspace.register,
)


def _register_command_parsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Register all top-level command modules on the root parser."""
    for register in COMMAND_REGISTRARS:
        register(subparsers)


_ROOT_EXAMPLES = (
    '  $ rrt branch new feat "add parser"\n'
    '  $ rrt branch rename --type fix --scope api "repair config loader"\n'
    "  $ rrt bump patch --dry-run\n"
    "  $ rrt release check\n"
    "  $ rrt action init\n"
    "  $ rrt drift check\n"
    "  $ rrt git status\n"
    "  $ rrt doctor\n"
    "  $ rrt install --target claude-local\n"
    "  $ rrt skill install --target copilot-local\n"
    "  $ rrt @args.txt"
)


def _style_command_name(name: str) -> str:
    """Return a semantic style for command names shown in help tables."""
    if name in DANGER_COMMANDS:
        return apply_style(name, color=Style(fg=31, bold=True))
    if name in WRITE_COMMANDS:
        return apply_style(name, color=Style(fg=32, bold=True))
    return apply_style(name, color=Style(fg=36, bold=True))


def _build_grouped_epilog(
    subparsers: argparse._SubParsersAction,
    groups: dict[str, list[str]],
) -> str:
    """Build grouped root-help sections without box-drawing panels."""
    parser_map: dict[str, argparse.ArgumentParser] = getattr(subparsers, "_name_parser_map", {})
    help_map: dict[str, str] = {
        action.dest: (action.help or "") for action in getattr(subparsers, "_choices_actions", [])
    }

    width = terminal_width()
    rule_line = chrome(rule(width=width))
    parts: list[str] = []

    for group_name, command_names in groups.items():
        rows: list[tuple[str, str]] = []
        for name in command_names:
            parser = parser_map.get(name)
            if parser is None:
                continue
            description = parser.description or help_map.get(name) or ""
            rows.append((name, description.splitlines()[0].strip()))
        if not rows:
            continue

        name_width = max(len(name) for name, _ in rows)
        parts.extend([rule_line, heading_style(group_name), rule_line])
        for name, description in rows:
            pad = max(2, name_width - len(name) + 2)
            styled_name = _style_command_name(name)
            parts.append(f"  {styled_name}{' ' * pad}{description}")
        parts.append("")

    parts.extend([rule_line, heading_style("Examples"), rule_line, _ROOT_EXAMPLES])
    return "\n".join(parts).rstrip()


class RrtHelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Help formatter with stable columns and thin-rule sections."""

    _suppress_subparsers: bool = False
    _raw_epilog: bool = False

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize formatter with fixed column width and stable ANSI stripping."""
        super().__init__(*args, **kwargs)
        self._col_width = 24
        # Python 3.14 added _set_color() to HelpFormatter which sets self._decolor as
        # an instance attribute (_identity for non-TTY, _colorize.decolor for TTY),
        # shadowing this class's _decolor method.  Re-pin it so ANSI codes are always
        # stripped with our own implementation regardless of Python version or TTY state.
        self._decolor: Callable[[str], str] = _strip_ansi

    def _compute_col_width(self, actions: list[argparse.Action]) -> int:
        """Return column width for the given action list."""
        return _compute_col_width(actions, self._width)

    def format_help(self) -> str:
        """Return formatted help text."""
        return super().format_help()

    def _format_usage(
        self,
        usage: str | None,
        actions: Iterable[argparse.Action],
        groups: Iterable[argparse._MutuallyExclusiveGroup],
        prefix: str | None,
    ) -> str:  # type: ignore[override]
        positionals = [
            _metavar_text(action)
            for action in actions
            if not action.option_strings and action.dest not in (argparse.SUPPRESS, "==SUPPRESS==")
        ]
        has_options = any(action.option_strings for action in actions)
        options = " [OPTIONS]" if has_options else ""
        positional_text = f" {' '.join(positionals)}" if positionals else ""
        if prefix == "":
            return f"{self._prog}{options}{positional_text}\n\n"
        usage_label = heading_style("Usage:")
        return f"{usage_label}  {bold(self._prog)}{options}{positional_text}\n\n"

    def start_section(self, heading: str | None) -> None:  # type: ignore[override]
        """Render a styled rule+heading section opener."""
        if not heading:
            return
        normalized = {
            "positional arguments": "Arguments",
            "optional arguments": "Options",
            "options": "Options",
        }.get(heading, heading)
        rule_line = chrome(rule(width=self._width))
        styled_heading = heading_style(normalized)
        self._add_item(lambda h=styled_heading, r=rule_line: f"\n{r}\n{h}\n{r}\n", [])

    def end_section(self) -> None:
        """End the current section (no-op override)."""
        return

    def format_epilog(self, epilog: str | None) -> str:  # type: ignore[override]
        """Return formatted epilog with rule and Examples heading."""
        if not epilog:
            return ""
        if self._raw_epilog:
            return f"\n{epilog.rstrip()}\n"
        rule_line = chrome(rule(width=self._width))
        examples_heading = heading_style("Examples")
        return f"\n{rule_line}\n{examples_heading}\n{rule_line}\n{epilog.rstrip()}\n"

    def _format_action(self, action: argparse.Action) -> str:  # type: ignore[override]
        if action.help is argparse.SUPPRESS:
            return ""
        if self._suppress_subparsers and isinstance(action, argparse._SubParsersAction):
            return ""
        if isinstance(action, argparse._SubParsersAction):
            return self._format_subparser_action(action)
        if (
            action.choices is not None
            and not action.option_strings
            and not isinstance(action.choices, dict)
        ):
            return self._format_choice_action(action)

        left = self._left_column_text(action)
        styled_left = self._styled_left_column(action, left)
        help_text = self._help_text(action)
        return self._render_row(left, styled_left, help_text)

    def _left_column_text(self, action: argparse.Action) -> str:
        if action.option_strings:
            flags = ", ".join(action.option_strings)
            metavar = f" {_metavar_text(action)}" if action.metavar else ""
            return flags + metavar
        return _metavar_text(action)

    def _styled_left_column(self, action: argparse.Action, text: str) -> str:
        return apply_style(text, color=Style(fg=36, bold=True)) if action.option_strings else text

    def _help_text(self, action: argparse.Action) -> str:
        if action.dest == "help" and action.default == argparse.SUPPRESS:
            return "Show this message and exit."
        return self._expand_help(action) if action.help else ""

    def _render_row(self, left: str, styled_left: str, help_text: str) -> str:
        if not help_text:
            return f"  {styled_left}\n"
        pad = self._col_width - 2 - _display_len(left)
        if pad < 2:
            return f"  {styled_left}\n{' ' * self._col_width}{help_text}\n"
        return f"  {styled_left}{' ' * pad}{help_text}\n"

    def _format_subparser_action(self, action: argparse._SubParsersAction) -> str:
        rows: list[tuple[str, str]] = []
        for sub in getattr(action, "_choices_actions", []):
            description = (sub.help or "").splitlines()[0].strip()
            rows.append((str(sub.dest), description))
        if not rows and action.choices:
            for name, subparser in action.choices.items():
                description = (subparser.description or "").splitlines()[0].strip()
                rows.append((str(name), description))
        rendered: list[str] = []
        for name, description in rows:
            styled_name = _style_command_name(name)
            rendered.append(self._render_row(name, styled_name, description))
        return "".join(rendered)

    def _format_choice_action(self, action: argparse.Action) -> str:
        metavar = _metavar_text(action)
        lines = [f"  {metavar}\n"]
        lines.extend(f"    {choice}\n" for choice in action.choices or [])
        if help_text := self._help_text(action):
            lines.append(f"{' ' * self._col_width}{help_text}\n")
        return "".join(lines)

    @staticmethod
    def _style_help(help_text: str) -> str:
        """Return legacy externally-provided help text unchanged."""
        return help_text


class RrtArgumentParser(argparse.ArgumentParser):
    """Argument parser with friendlier parse-error output."""

    _INVALID_CHOICE_RE = re.compile(
        r"invalid choice: ['\"](?P<invalid>.+?)['\"] \(choose from (?P<choices>.+)\)",
    )
    _INVALID_VALUE_RE = re.compile(
        r"invalid [^:]+: ['\"](?P<invalid>.+?)['\"] \(choose one of: (?P<choices>.+)\)",
    )
    _UNRECOGNIZED_RE = re.compile(r"unrecognized arguments: (?P<args>.+)")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize parser with rrt defaults and friendly error output."""
        kwargs.setdefault("fromfile_prefix_chars", "@")
        kwargs.setdefault("formatter_class", RrtHelpFormatter)
        super().__init__(*args, **kwargs)
        self._positionals.title = "Arguments"
        self._optionals.title = "Options"

    def _get_formatter(self) -> argparse.HelpFormatter:  # type: ignore[override]
        formatter_class = cast("type[RrtHelpFormatter]", self.formatter_class)
        return formatter_class(
            prog=self.prog,
            width=terminal_width(),
            max_help_position=24,
        )

    def format_help(self) -> str:  # type: ignore[override]
        """Return formatted help text including epilog."""
        formatter = self._get_formatter()
        all_actions = [action for group in self._action_groups for action in group._group_actions]
        cast("RrtHelpFormatter", formatter)._col_width = _compute_col_width(
            all_actions,
            terminal_width(),
        )
        formatter.add_usage(self.usage, self._actions, self._mutually_exclusive_groups)
        formatter.add_text(self.description)
        for action_group in self._action_groups:
            formatter.start_section(action_group.title)
            formatter.add_text(action_group.description)
            formatter.add_arguments(action_group._group_actions)
            formatter.end_section()
        help_text = formatter.format_help()
        if self.epilog:
            help_text += cast("RrtHelpFormatter", formatter).format_epilog(self.epilog)
        return help_text

    def print_help(self, file: IO[str] | None = None) -> None:  # type: ignore[override]  # ty: ignore[invalid-method-override]
        """Write help text to *file* (defaults to stdout)."""
        if file is None:
            file = sys.stdout
        cast("IO[str]", file).write(self.format_help())

    def convert_arg_line_to_args(self, arg_line: str) -> list[str]:  # type: ignore[override]
        """Strip inline comments and split response-file lines."""
        line = arg_line.split("#", 1)[0].strip()
        return line.split() if line else []

    def error(self, message: str) -> NoReturn:  # type: ignore[override]
        """Print a styled error message and exit with code 2."""
        message = self._clean_error_message(message)
        use_color = supports_color(sys.stderr)
        suggestion = self._suggestion_for(message)

        p = VerbosePrinter()
        p.blank_line(stream=sys.stderr)
        if use_color:
            prefix = apply_style("✖  error:", color="error", bold=True, stream=sys.stderr)
            detail = apply_style(message, bold=True, stream=sys.stderr)
            help_target = bold(f"{self.prog} --help")
            p.line(f"{prefix} {detail}", ok=False, stream=sys.stderr)
        else:
            help_target = f"'{self.prog} --help'"
            p.line(message, ok=False, stream=sys.stderr)

        if suggestion:
            rendered_suggestion = apply_style(
                suggestion,
                color="warning",
                bold=True,
                stream=sys.stderr,
            )
            p.line(f"  {rendered_suggestion}", ok=False, stream=sys.stderr)
        help_hint = f"Run {help_target} for usage and examples."
        p.line(f"  {subtle(help_hint, stream=sys.stderr)}\n", ok=False, stream=sys.stderr)
        self.exit(2)

    def _clean_error_message(self, message: str) -> str:
        cleaned = message
        replacements = {
            "git_command": "<git_command>",
            "ci_version_cmd": "<ci_version_cmd>",
            "skill_command": "<skill_command>",
            "branch_command": "<branch_command>",
            "command": "<command>",
            "bump": "<bump>",
        }
        for raw, display in replacements.items():
            cleaned = re.sub(rf"(?<![\w<]){re.escape(raw)}(?![\w>])", display, cleaned)
        return cleaned

    def _error_help_hint(self, message: str) -> str:
        """Return suggestion and help-hint text for compatibility with older tests."""
        hints: list[str] = []
        if suggestion := self._suggestion_for(message):
            hints.append(suggestion)
        hints.append(f"Run '{self.prog} --help' for usage and examples.")
        return "\n\n" + "\n".join(hints) if hints else ""

    def _available_choices(self) -> list[str]:
        choices: list[str] = []
        if getattr(self, "_subparsers", None) is not None:
            subparsers = getattr(self._subparsers, "_name_parser_map", {})
            choices.extend(str(name) for name in subparsers)
        for action in self._actions:
            action_choices = getattr(action, "choices", None)
            if action_choices is not None:
                choices.extend(str(choice) for choice in action_choices)
            choices.extend(getattr(action, "option_strings", []))
        return list(dict.fromkeys(choices))

    def _suggestion_for(self, message: str) -> str | None:
        for pattern in (self._INVALID_CHOICE_RE, self._INVALID_VALUE_RE):
            if match := pattern.search(message):
                invalid = match.group("invalid")
                choices = [choice.strip(" '\"") for choice in match.group("choices").split(",")]
                if suggested := self._close_matches(invalid, choices):
                    return self._format_suggestion(suggested)
        if match := self._UNRECOGNIZED_RE.search(message):
            if invalid_args := match.group("args").replace("'", "").replace('"', "").split():
                invalid = invalid_args[0]
                if suggested := self._close_matches(invalid, self._available_choices()):
                    return self._format_suggestion(suggested)
        return None

    def _close_matches(self, invalid: str, choices: list[str]) -> list[str]:
        return difflib.get_close_matches(invalid, choices, n=3, cutoff=0.6)

    def _format_suggestion(self, matches: list[str]) -> str:
        if not matches:
            return ""
        if len(matches) == 1:
            return f"Did you mean: {matches[0]}?"
        return f"Did you mean one of: {', '.join(matches)}?"


StyledHelpFormatter = RrtHelpFormatter
FriendlyArgumentParser = RrtArgumentParser


def _generate_completion(shell: str, parser: argparse.ArgumentParser) -> str:
    """Generate a shell completion script for the given shell."""
    subparsers_action = next(
        (a for a in parser._actions if isinstance(a, argparse._SubParsersAction)),
        None,
    )
    subcommands: list[str] = []
    global_opts: list[str] = []
    subcommand_opts: dict[str, list[str]] = {}

    for action in parser._actions:
        global_opts.extend(getattr(action, "option_strings", []))

    if subparsers_action is not None:
        for name, sub in (subparsers_action.choices or {}).items():
            subcommands.append(name)
            opts: list[str] = []
            for action in sub._actions:
                opts.extend(getattr(action, "option_strings", []))
            subcommand_opts[name] = opts

    if shell == "bash":
        return _bash_completion(subcommands, global_opts, subcommand_opts)
    if shell == "zsh":
        return _zsh_completion(subcommands, global_opts, subcommand_opts)
    return _fish_completion(subcommands, global_opts, subcommand_opts)


def _bash_completion(
    subcommands: list[str],
    global_opts: list[str],
    subcommand_opts: dict[str, list[str]],
) -> str:
    cmds = " ".join(subcommands)
    global_flags = " ".join(global_opts)
    sub_cases = "\n".join(
        f"            {cmd})\n                opts='{' '.join(opts)}'\n                ;;"
        for cmd, opts in subcommand_opts.items()
    )
    return f"""\
# rrt bash completion
# Source this file or add to ~/.bash_completion.d/
_rrt_completions() {{
    local cur prev commands
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    prev="${{COMP_WORDS[COMP_CWORD-1]}}"
    commands="{cmds}"

    if [[ $COMP_CWORD -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "$commands {global_flags}" -- "$cur") )
        return
    fi

    local subcommand="${{COMP_WORDS[1]}}"
    local opts="{global_flags}"
    case "$subcommand" in
{sub_cases}
    esac
    COMPREPLY=( $(compgen -W "$opts" -- "$cur") )
}}
complete -F _rrt_completions rrt
"""


def _zsh_completion(
    subcommands: list[str],
    global_opts: list[str],
    subcommand_opts: dict[str, list[str]],
) -> str:
    cmd_list = "\n".join(f"    '{cmd}'" for cmd in subcommands)
    sub_cases = "\n".join(
        f"        ({cmd})\n            _arguments {' '.join(repr(o) for o in opts)}\n            ;;"
        for cmd, opts in subcommand_opts.items()
    )
    return f"""\
#compdef rrt
# rrt zsh completion
# Place in a directory listed in $fpath, e.g. ~/.zsh/completions/_rrt

_rrt() {{
    local -a commands
    commands=(
{cmd_list}
    )

    _arguments -C \\
        '(-h --help)'{"{"}'-h[Show help]','--help[Show help]'{"}"} \\
        '(--version)--version[Show version]' \\
        '(--no-color)--no-color[Disable color output]' \\
        '(--format)--format=[Output format]:format:(text json)' \\
        '1:command:->command' \\
        '*::args:->args'

    case $state in
        command)
            _describe 'rrt subcommand' commands
            ;;
        args)
            case $words[1] in
{sub_cases}
            esac
            ;;
    esac
}}

_rrt "$@"
"""


def _fish_completion(
    subcommands: list[str],
    global_opts: list[str],
    subcommand_opts: dict[str, list[str]],
) -> str:
    lines = [
        "# rrt fish completion",
        "# Place in ~/.config/fish/completions/rrt.fish",
        "",
        "# Disable file completion by default",
        "complete -c rrt -f",
        "",
        "# Global options",
    ]
    for opt in global_opts:
        long = opt.lstrip("-")
        lines.append(f"complete -c rrt -l {long} -d 'option'")

    lines.extend(
        [
            "",
            "# Subcommands",
        ]
    )
    lines.extend(f"complete -c rrt -n '__fish_use_subcommand' -a {cmd}" for cmd in subcommands)

    for cmd, opts in subcommand_opts.items():
        for opt in opts:
            long = opt.lstrip("-")
            lines.append(
                f"complete -c rrt -n '__fish_seen_subcommand_from {cmd}' -l {long} -d 'option'"
            )

    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    """Build the root parser."""

    class _RootFormatter(RrtHelpFormatter):
        _suppress_subparsers = True
        _raw_epilog = True

    parser = RrtArgumentParser(
        prog="rrt",
        description="repo-release-tools: branch, commit, and version helpers for Git repositories.",
        formatter_class=_RootFormatter,
    )
    try:
        version = importlib.metadata.version("repo-release-tools")
    except importlib.metadata.PackageNotFoundError:
        version = "0.0.0"

    parser.add_argument(
        "--version",
        action="version",
        version=f"rrt {version}",
        help="Show version and exit.",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        metavar="FORMAT",
        help="Output format. Defaults to text.",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        default=False,
        help="Disable all ANSI color output.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase output verbosity (-v summary, -vv details, -vvv debug).",
    )
    parser.add_argument(
        "--generate-completion",
        choices=["bash", "zsh", "fish"],
        default=None,
        metavar="SHELL",
        help="Print shell completion script for SHELL and exit.",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        metavar="<command>",
        required=True,
        parser_class=RrtArgumentParser,
    )
    _register_command_parsers(cast("argparse._SubParsersAction", subparsers))
    parser.epilog = _build_grouped_epilog(
        cast("argparse._SubParsersAction", subparsers),
        COMMAND_GROUPS,
    )
    return parser


def _startup_banner() -> str:
    """Return the platform-appropriate startup banner for bare ``rrt`` runs."""
    variant = "ascii" if IS_LEGACY_TERMINAL else "unicode"
    return get_cached_banner(variant)


def main() -> None:
    """Program entrypoint."""
    if len(sys.argv) == 1:
        sys.stdout.write(_startup_banner() + "\n")
    parser = build_parser()
    args, _ = parser.parse_known_args()
    if getattr(args, "generate_completion", None):
        sys.stdout.write(_generate_completion(args.generate_completion, parser))
        raise SystemExit(0)
    args = parser.parse_args()
    if getattr(args, "no_color", False):
        os.environ.setdefault("NO_COLOR", "1")
    try:
        raise SystemExit(args.handler(args))
    except (RuntimeError, ValueError) as exc:
        sys.stderr.write(cli_error(str(exc), stream=sys.stderr) + "\n")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    sys.exit(main())
