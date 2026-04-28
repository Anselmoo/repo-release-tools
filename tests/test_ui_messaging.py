"""Tests for ui/messaging.py helpers."""

from __future__ import annotations

from repo_release_tools.ui import OutputContext
from repo_release_tools.ui import messaging


def test_error_renders_plain_text_when_color_disabled(monkeypatch) -> None:
    monkeypatch.setattr(messaging, "supports_color", lambda stream=None: True)
    ctx = OutputContext(no_color=True)

    result = messaging.error("bad input", hint="try again", ctx=ctx)

    assert result.startswith("[ERROR]")
    assert "Hint: try again" in result
    assert "\x1b[" not in result


def test_error_renders_colored_message_when_supported(monkeypatch) -> None:
    monkeypatch.setattr(messaging, "supports_color", lambda stream=None: True)
    monkeypatch.setattr("repo_release_tools.ui.color.supports_color", lambda stream=None: True)

    result = messaging.error("bad input", hint="try again")

    assert "✖  error:" in result
    assert "Hint:" in result
