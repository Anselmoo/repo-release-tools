"""Pure-Python token-based syntax highlighting for terminal output.

Uses regex tokenization to apply ANSI colours to TOML, env, and Python
source snippets.  No third-party packages are required.  Falls back to
plain text when colour support is unavailable or the language is unknown.
"""

from __future__ import annotations

import json as _json
import pprint as _pprint
import re
from typing import IO

from repo_release_tools.ui.color import detect_color_level, supports_color

# ── ANSI colour codes ─────────────────────────────────────────────────────────

_RESET = "\x1b[0m"
_ANSI: dict[str, str] = {
    "comment": "\x1b[2;32m",  # dim green
    "section": "\x1b[1;36m",  # bold cyan  — TOML [table] headers
    "key": "\x1b[36m",  # cyan
    "string": "\x1b[33m",  # yellow
    "number": "\x1b[35m",  # magenta
    "bool": "\x1b[34m",  # blue
    "envkey": "\x1b[36m",  # cyan   — env KEY=
    "envval": "\x1b[33m",  # yellow — env =VALUE
    "kw": "\x1b[34m",  # blue   — Python keywords
    "added": "\x1b[32m",  # green  — diff added lines
    "removed": "\x1b[31m",  # red    — diff removed lines
    # shell-specific tokens
    "cmd": "\x1b[1;36m",  # bold cyan — first word (command name)
    "flag": "\x1b[2m",  # dim       — --flags and -options
    "path": "\x1b[33m",  # yellow   — / or ./ prefixed paths
}

# ── Token rules per language ──────────────────────────────────────────────────
# Each rule is (token_type, compiled_pattern).
# The pattern must have exactly one capturing group that is the span to colour.

_TOML_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("comment", re.compile(r"(#.+)$")),
    ("section", re.compile(r"^(\s*\[[\w.\-_\"' ]+\])")),
    ("key", re.compile(r"^([a-zA-Z_][a-zA-Z0-9_.\-]*)\s*=")),
    ("string", re.compile(r'(""".*?"""|\'\'\'.*?\'\'\'|"[^"]*"|\'[^\']*\')', re.DOTALL)),
    ("bool", re.compile(r"\b(true|false)\b")),
    ("number", re.compile(r"\b(\d+(?:\.\d+)?)\b")),
]

_ENV_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("comment", re.compile(r"(#.+)$")),
    ("envkey", re.compile(r"^([A-Z_][A-Z0-9_]*)=")),
    ("envval", re.compile(r"=(.+)$")),
]

_PYTHON_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("comment", re.compile(r"(#.+)$")),
    ("string", re.compile(r'(""".*?"""|\'\'\'.*?\'\'\'|"[^"]*"|\'[^\']*\')', re.DOTALL)),
    ("bool", re.compile(r"\b(True|False|None)\b")),
    ("number", re.compile(r"\b(\d+(?:\.\d+)?)\b")),
    (
        "kw",
        re.compile(
            r"\b(def|class|import|from|return|if|else|elif|for|while|with|as|in|not|"
            r"and|or|is|lambda|yield|raise|try|except|finally|pass|break|continue)\b"
        ),
    ),
]

_JSON_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("key", re.compile(r'"([^"]+)"\s*:')),
    ("string", re.compile(r':\s*"([^"]*)"')),
    ("bool", re.compile(r"\b(true|false|null)\b")),
    ("number", re.compile(r":\s*(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\b")),
]

_DIFF_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("section", re.compile(r"^(@@.+@@)")),
    ("comment", re.compile(r"^((?:---|\+\+\+).+)$")),
    ("removed", re.compile(r"^(-.*)$")),
    ("added", re.compile(r"^(\+.*)$")),
]

# Shell tokenizer: highlight first word (command), flags, and paths.
# Rules are applied in order; only the *first* matching rule per token is used
# via _colour_first_match, so cmd must come before flag and path.
_SHELL_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("cmd", re.compile(r"^(\S+)")),  # first word = command name
    ("flag", re.compile(r"(?:^|\s)(--?[a-zA-Z][a-zA-Z0-9\-]*)")),  # --flag or -f
    ("path", re.compile(r"(?:^|\s)(\./\S+|/\S+)")),  # ./path or /abs/path
    ("string", re.compile(r'("[^"]*"|\'[^\']*\')')),  # quoted strings
]

_RULES: dict[str, list[tuple[str, re.Pattern[str]]]] = {
    "toml": _TOML_RULES,
    "env": _ENV_RULES,
    "python": _PYTHON_RULES,
    "py": _PYTHON_RULES,
    "json": _JSON_RULES,
    "diff": _DIFF_RULES,
    "shell": _SHELL_RULES,
    "sh": _SHELL_RULES,
    "bash": _SHELL_RULES,
}


def _colour_first_match(line: str, rules: list[tuple[str, re.Pattern[str]]]) -> str:
    """Apply colour to the first matching token span in a line."""
    for token_type, pattern in rules:
        m = pattern.search(line)
        if m:
            code = _ANSI.get(token_type, "")
            if not code:
                continue
            grp = 1 if m.lastindex else 0
            start, end = m.span(grp)
            return line[:start] + code + line[start:end] + _RESET + line[end:]
    return line


def _colour_all_matches(line: str, rules: list[tuple[str, re.Pattern[str]]]) -> str:
    """Apply colour to *all* non-overlapping token spans in a line.

    Used for multi-token languages like shell where a single line may contain
    both a command name and flags.
    """
    matches: list[tuple[int, int, str]] = []
    for token_type, pattern in rules:
        for m in pattern.finditer(line):
            code = _ANSI.get(token_type, "")
            if not code:
                continue
            grp = 1 if m.lastindex else 0
            start, end = m.span(grp)
            # Skip if already covered by an earlier (higher-priority) match.
            if any(s <= start < e or s < end <= e for s, e, _ in matches):
                continue
            matches.append((start, end, code))

    matches.sort()
    parts: list[str] = []
    prev = 0
    for start, end, code in matches:
        parts.append(line[prev:start])
        parts.append(f"{code}{line[start:end]}{_RESET}")
        prev = end
    parts.append(line[prev:])
    return "".join(parts)


def highlight_terminal(
    code: str,
    language: str,
    *,
    stream: IO[str] | None = None,
) -> str:
    """Highlight *code* for terminal display using built-in regex tokenization.

    Falls back to plain text when colour is not supported or *language* is
    unknown (no third-party packages required).
    """
    if not supports_color(stream) or detect_color_level() == "none":
        return code

    rules = _RULES.get(language.lower(), [])
    if not rules:
        return code

    if language.lower() in {"shell", "sh", "bash"}:
        return "\n".join(_colour_all_matches(line, rules) for line in code.splitlines())
    return "\n".join(_colour_first_match(line, rules) for line in code.splitlines())


# ── Convenience formatters (migrated from output.py) ─────────────────────────


def fmt_cmd(cmd: str, *, stream: IO[str] | None = None) -> str:
    """Return *cmd* with shell syntax highlighting applied."""
    return highlight_terminal(cmd, "shell", stream=stream)


def pretty_print(obj: object, *, indent: int = 2, stream: IO[str] | None = None) -> str:
    """Return a pretty-printed and optionally highlighted Python representation."""
    text = _pprint.pformat(obj, indent=indent)
    return highlight_terminal(text, "python", stream=stream)


def json_highlight(obj: object | str, *, indent: int = 2, stream: IO[str] | None = None) -> str:
    """Return a pretty-printed JSON string with syntax highlighting.

    *obj* may be a Python object or an already-serialised JSON string.
    """
    if isinstance(obj, str):
        try:
            obj = _json.loads(obj)
        except _json.JSONDecodeError:
            return obj
    text = _json.dumps(obj, indent=indent, ensure_ascii=False)
    return highlight_terminal(text, "json", stream=stream)


def diff_highlight(text: str, *, stream: IO[str] | None = None) -> str:
    """Return a unified diff string with syntax highlighting."""
    return highlight_terminal(text, "diff", stream=stream)
