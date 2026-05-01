from __future__ import annotations

import json

from repo_release_tools.ui import syntax
from repo_release_tools.ui import color


def test_highlight_toml_and_json_and_diff_and_shell(monkeypatch):
    # Enable color support and standard level
    monkeypatch.setattr(syntax, "supports_color", lambda stream=None: True)
    monkeypatch.setattr(syntax, "detect_color_level", lambda: "standard")

    toml_text = "# comment\n[tool.rrt]\nkey = \"value\"\n"
    out = syntax.highlight_terminal(toml_text, "toml")
    assert "#" in out and "\x1b[" in out

    json_obj = {"name": "rrt", "ok": True}
    out_json = syntax.json_highlight(json_obj)
    # keys should be highlighted (e.g. \x1b[36mname\x1b[0m)
    assert "\x1b[36mname\x1b[0m" in out_json and "\x1b[" in out_json

    diff = "--- a/file\n+++ b/file\n+added\n-removed\n"
    out_diff = syntax.diff_highlight(diff)
    assert "+added" in out_diff and "\x1b[" in out_diff

    shell_cmd = "git status --porcelain"
    out_shell = syntax.fmt_cmd(shell_cmd)
    # command name should be highlighted
    assert "git" in out_shell and "\x1b[" in out_shell


def test_pretty_print_and_json_string_handling(monkeypatch):
    monkeypatch.setattr(syntax, "supports_color", lambda stream=None: True)
    monkeypatch.setattr(syntax, "detect_color_level", lambda: "standard")

    data = {"a": 1, "b": [1, 2, 3]}
    pp = syntax.pretty_print(data)
    assert "{" in pp and "\x1b[" in pp

    # json_highlight should accept a JSON string and handle invalid JSON gracefully
    s = json.dumps(data)
    out = syntax.json_highlight(s)
    assert "\x1b[" in out

    bad = "not a json"
    out_bad = syntax.json_highlight(bad)
    assert out_bad == bad


def test_highlight_falls_back_when_no_color(monkeypatch):
    monkeypatch.setattr(syntax, "supports_color", lambda stream=None: False)
    monkeypatch.setattr(syntax, "detect_color_level", lambda: "none")

    code = "key = \"val\""
    assert syntax.highlight_terminal(code, "toml") == code
    assert syntax.fmt_cmd("echo hi") == "echo hi"
    # json_highlight pretty-prints input JSON strings, even when color is off
    out = syntax.json_highlight('{"x":1}')
    assert '\n' in out and '"x"' in out
