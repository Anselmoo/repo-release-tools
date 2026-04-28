"""Tests for ui/prompt.py helpers."""

from __future__ import annotations

import io

from repo_release_tools.ui import prompt


def test_confirm_returns_default_when_not_tty(monkeypatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert prompt.confirm("Continue?", default=True) is True
    assert prompt.confirm("Continue?", default=False) is False


def test_ask_returns_default_when_not_tty(monkeypatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert prompt.ask("Name?", default="Alice") == "Alice"


def test_ask_returns_empty_string_when_no_default_and_not_tty(monkeypatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert prompt.ask("Name?") == ""


def test_confirm_yes_when_tty(monkeypatch) -> None:
    class _FakeTTY(io.StringIO):
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr("sys.stdin", _FakeTTY("y\n"))
    monkeypatch.setattr("builtins.input", lambda prompt_str: "y")
    assert prompt.confirm("Continue?") is True


def test_confirm_no_when_tty(monkeypatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("n\n"))
    monkeypatch.setattr(
        "sys.stdin",
        type("TTY", (io.StringIO,), {"isatty": lambda self: True})("n\n"),
    )
    monkeypatch.setattr("builtins.input", lambda prompt_str: "n")
    assert prompt.confirm("Continue?", default=True) is False


def test_confirm_blank_returns_default_when_tty(monkeypatch) -> None:
    monkeypatch.setattr(
        "sys.stdin",
        type("TTY", (io.StringIO,), {"isatty": lambda self: True})("\n"),
    )
    monkeypatch.setattr("builtins.input", lambda prompt_str: "")
    assert prompt.confirm("Continue?", default=True) is True
    assert prompt.confirm("Continue?", default=False) is False


def test_ask_reply_when_tty(monkeypatch) -> None:
    monkeypatch.setattr(
        "sys.stdin",
        type("TTY", (io.StringIO,), {"isatty": lambda self: True})("Bob\n"),
    )
    monkeypatch.setattr("builtins.input", lambda prompt_str: "Bob")
    assert prompt.ask("Name?") == "Bob"


def test_ask_blank_returns_default_when_tty(monkeypatch) -> None:
    monkeypatch.setattr(
        "sys.stdin",
        type("TTY", (io.StringIO,), {"isatty": lambda self: True})("\n"),
    )
    monkeypatch.setattr("builtins.input", lambda prompt_str: "")
    assert prompt.ask("Name?", default="Alice") == "Alice"


def test_confirm_eof_returns_default(monkeypatch) -> None:
    def _raise(_: str) -> str:
        raise EOFError

    monkeypatch.setattr(
        "sys.stdin",
        type("TTY", (io.StringIO,), {"isatty": lambda self: True})(""),
    )
    monkeypatch.setattr("builtins.input", _raise)
    assert prompt.confirm("Continue?", default=True) is True


def test_ask_eof_returns_default(monkeypatch) -> None:
    def _raise(_: str) -> str:
        raise EOFError

    monkeypatch.setattr(
        "sys.stdin",
        type("TTY", (io.StringIO,), {"isatty": lambda self: True})(""),
    )
    monkeypatch.setattr("builtins.input", _raise)
    assert prompt.ask("Name?", default="default") == "default"
