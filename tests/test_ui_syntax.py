"""Tests for the pure-Python syntax highlighter (ui/syntax.py)."""

from __future__ import annotations

import io

import pytest

from repo_release_tools.ui import syntax

# ── Plain-text fallbacks ──────────────────────────────────────────────────────


def test_highlight_terminal_returns_plain_when_no_color(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(syntax, "detect_color_level", lambda: "none")
    assert syntax.highlight_terminal("key = 'val'", "toml") == "key = 'val'"


def test_highlight_terminal_returns_plain_when_not_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(syntax, "supports_color", lambda stream=None: False)
    assert syntax.highlight_terminal("key = 'val'", "toml") == "key = 'val'"


def test_highlight_terminal_returns_plain_for_unknown_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(syntax, "supports_color", lambda stream=None: True)
    monkeypatch.setattr(syntax, "detect_color_level", lambda: "standard")
    assert syntax.highlight_terminal("some code", "brainfuck") == "some code"


# ── TOML highlighting ─────────────────────────────────────────────────────────


def test_highlight_terminal_toml_key_emits_ansi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(syntax, "supports_color", lambda stream=None: True)
    monkeypatch.setattr(syntax, "detect_color_level", lambda: "standard")
    result = syntax.highlight_terminal("name = 'rrt'", "toml")
    assert "\x1b[" in result
    assert "name" in result


def test_highlight_terminal_toml_comment_emits_ansi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(syntax, "supports_color", lambda stream=None: True)
    monkeypatch.setattr(syntax, "detect_color_level", lambda: "standard")
    result = syntax.highlight_terminal("# a comment", "toml")
    assert "\x1b[" in result
    assert "# a comment" in result


def test_highlight_terminal_toml_section_emits_ansi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(syntax, "supports_color", lambda stream=None: True)
    monkeypatch.setattr(syntax, "detect_color_level", lambda: "standard")
    result = syntax.highlight_terminal("[tool.rrt]", "toml")
    assert "\x1b[" in result
    assert "[tool.rrt]" in result


def test_highlight_terminal_toml_bool_emits_ansi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(syntax, "supports_color", lambda stream=None: True)
    monkeypatch.setattr(syntax, "detect_color_level", lambda: "standard")
    result = syntax.highlight_terminal("enabled = true", "toml")
    assert "\x1b[" in result


def test_highlight_terminal_toml_number_emits_ansi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(syntax, "supports_color", lambda stream=None: True)
    monkeypatch.setattr(syntax, "detect_color_level", lambda: "standard")
    result = syntax.highlight_terminal("count = 42", "toml")
    assert "\x1b[" in result


# ── ENV highlighting ──────────────────────────────────────────────────────────


def test_highlight_terminal_env_key_emits_ansi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(syntax, "supports_color", lambda stream=None: True)
    monkeypatch.setattr(syntax, "detect_color_level", lambda: "standard")
    result = syntax.highlight_terminal("HOME=/home/user", "env")
    assert "\x1b[" in result
    assert "HOME" in result


# ── Python highlighting ───────────────────────────────────────────────────────


def test_highlight_terminal_python_keyword_emits_ansi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(syntax, "supports_color", lambda stream=None: True)
    monkeypatch.setattr(syntax, "detect_color_level", lambda: "standard")
    result = syntax.highlight_terminal("def foo():", "python")
    assert "\x1b[" in result


def test_highlight_terminal_python_bool_emits_ansi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(syntax, "supports_color", lambda stream=None: True)
    monkeypatch.setattr(syntax, "detect_color_level", lambda: "standard")
    result = syntax.highlight_terminal("x = True", "python")
    assert "\x1b[" in result


def test_highlight_terminal_py_alias_same_as_python(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(syntax, "supports_color", lambda stream=None: True)
    monkeypatch.setattr(syntax, "detect_color_level", lambda: "standard")
    py = syntax.highlight_terminal("x = True", "py")
    python = syntax.highlight_terminal("x = True", "python")
    assert py == python


# ── Multi-line input ──────────────────────────────────────────────────────────


def test_highlight_terminal_multiline_preserves_newlines(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(syntax, "supports_color", lambda stream=None: True)
    monkeypatch.setattr(syntax, "detect_color_level", lambda: "standard")
    code = "name = 'rrt'\n# comment\nversion = '1.0.0'"
    result = syntax.highlight_terminal(code, "toml")
    assert result.count("\n") == 2
    assert "# comment" in result


# ── JSON highlighting ─────────────────────────────────────────────────────────


def test_highlight_terminal_json_key_emits_ansi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(syntax, "supports_color", lambda stream=None: True)
    monkeypatch.setattr(syntax, "detect_color_level", lambda: "standard")
    result = syntax.highlight_terminal('  "name": "rrt"', "json")
    assert "\x1b[" in result
    assert "name" in result


def test_highlight_terminal_json_string_value_emits_ansi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(syntax, "supports_color", lambda stream=None: True)
    monkeypatch.setattr(syntax, "detect_color_level", lambda: "standard")
    result = syntax.highlight_terminal('  "version": "1.0.0"', "json")
    assert "\x1b[" in result


def test_highlight_terminal_json_bool_emits_ansi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(syntax, "supports_color", lambda stream=None: True)
    monkeypatch.setattr(syntax, "detect_color_level", lambda: "standard")
    result = syntax.highlight_terminal("  true", "json")
    assert "\x1b[" in result


def test_highlight_terminal_json_null_emits_ansi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(syntax, "supports_color", lambda stream=None: True)
    monkeypatch.setattr(syntax, "detect_color_level", lambda: "standard")
    result = syntax.highlight_terminal("  null", "json")
    assert "\x1b[" in result


def test_highlight_terminal_json_number_emits_ansi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(syntax, "supports_color", lambda stream=None: True)
    monkeypatch.setattr(syntax, "detect_color_level", lambda: "standard")
    result = syntax.highlight_terminal('  "count": 42', "json")
    assert "\x1b[" in result


def test_highlight_terminal_json_bracket_line_returns_plain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bare bracket line has no matching rule — plain text (covers no-match return)."""
    monkeypatch.setattr(syntax, "supports_color", lambda stream=None: True)
    monkeypatch.setattr(syntax, "detect_color_level", lambda: "standard")
    result = syntax.highlight_terminal("{", "json")
    assert result == "{"


# ── Diff highlighting ─────────────────────────────────────────────────────────


def test_highlight_terminal_diff_added_emits_green(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(syntax, "supports_color", lambda stream=None: True)
    monkeypatch.setattr(syntax, "detect_color_level", lambda: "standard")
    result = syntax.highlight_terminal("+new line", "diff")
    assert "\x1b[32m" in result
    assert "new line" in result


def test_highlight_terminal_diff_removed_emits_red(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(syntax, "supports_color", lambda stream=None: True)
    monkeypatch.setattr(syntax, "detect_color_level", lambda: "standard")
    result = syntax.highlight_terminal("-old line", "diff")
    assert "\x1b[31m" in result
    assert "old line" in result


def test_highlight_terminal_diff_hunk_emits_ansi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(syntax, "supports_color", lambda stream=None: True)
    monkeypatch.setattr(syntax, "detect_color_level", lambda: "standard")
    result = syntax.highlight_terminal("@@ -1,3 +1,4 @@", "diff")
    assert "\x1b[" in result


def test_highlight_terminal_diff_file_header_emits_ansi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(syntax, "supports_color", lambda stream=None: True)
    monkeypatch.setattr(syntax, "detect_color_level", lambda: "standard")
    result = syntax.highlight_terminal("--- a/file.py", "diff")
    assert "\x1b[" in result


def test_highlight_terminal_diff_context_line_returns_plain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A context line (space-prefixed) has no diff rule — plain text."""
    monkeypatch.setattr(syntax, "supports_color", lambda stream=None: True)
    monkeypatch.setattr(syntax, "detect_color_level", lambda: "standard")
    result = syntax.highlight_terminal(" unchanged line", "diff")
    assert result == " unchanged line"


# ── Coverage: _colour_first_match edge cases ──────────────────────────────────


def test_colour_first_match_skips_when_token_has_no_ansi_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cover the `if not code: continue` branch in _colour_first_match."""
    import re

    monkeypatch.setattr(syntax, "supports_color", lambda stream=None: True)
    monkeypatch.setattr(syntax, "detect_color_level", lambda: "standard")
    monkeypatch.setitem(syntax._RULES, "_test_lang", [("_no_such_token_", re.compile(r"(foo)"))])
    result = syntax.highlight_terminal("foo", "_test_lang")
    assert result == "foo"


def test_highlight_terminal_shell_colours_command_flag_and_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(syntax, "supports_color", lambda stream=None: True)
    monkeypatch.setattr(syntax, "detect_color_level", lambda: "standard")

    result = syntax.highlight_terminal("git status --short ./src /tmp/demo", "shell")

    assert f"{syntax._ANSI['cmd']}git{syntax._RESET}" in result
    assert f"{syntax._ANSI['flag']}--short{syntax._RESET}" in result
    assert f"{syntax._ANSI['path']}./src{syntax._RESET}" in result
    assert f"{syntax._ANSI['path']}/tmp/demo{syntax._RESET}" in result


def test_fmt_cmd_uses_shell_highlighting_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_highlight(code: str, language: str, *, stream: object = None) -> str:
        captured["code"] = code
        captured["language"] = language
        captured["stream"] = stream
        return "rendered"

    monkeypatch.setattr(syntax, "highlight_terminal", fake_highlight)

    stream = io.StringIO()
    result = syntax.fmt_cmd("git status", stream=stream)

    assert result == "rendered"
    assert captured == {"code": "git status", "language": "shell", "stream": stream}


def test_json_highlight_returns_original_string_for_invalid_json() -> None:
    invalid = "{not json}"

    assert syntax.json_highlight(invalid) == invalid


def test_colour_all_matches_skips_unknown_and_overlapping_tokens() -> None:
    import re

    rules = [
        ("cmd", re.compile(r"^(git)")),
        ("_no_such_token_", re.compile(r"^(git status)")),
        ("path", re.compile(r"^(git status)")),
    ]

    result = syntax._colour_all_matches("git status", rules)

    assert result == f"{syntax._ANSI['cmd']}git{syntax._RESET} status"
