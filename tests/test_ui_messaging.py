"""Tests for ui/messaging.py helpers."""

from __future__ import annotations

import io

import pytest

from repo_release_tools.ui import OutputContext, messaging


def test_error_renders_plain_text_when_color_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(messaging, "supports_color", lambda stream=None: True)
    ctx = OutputContext(no_color=True)

    result = messaging.error("bad input", hint="try again", ctx=ctx)

    assert result.startswith("[ERROR]")
    assert "Hint: try again" in result
    assert "\x1b[" not in result


def test_error_renders_colored_message_when_supported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(messaging, "supports_color", lambda stream=None: True)
    monkeypatch.setattr("repo_release_tools.ui.color.supports_color", lambda stream=None: True)

    result = messaging.error("bad input", hint="try again")

    assert "✖  error:" in result
    assert "Hint:" in result


def test_render_helpers_use_expected_glyphs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(messaging, "_c_info", lambda message, stream=None: message)
    monkeypatch.setattr(messaging, "_c_subtle", lambda message, stream=None: message)
    monkeypatch.setattr(messaging, "_c_success", lambda message, stream=None: message)
    monkeypatch.setattr(messaging, "_c_warning", lambda message, stream=None: message)
    monkeypatch.setattr("repo_release_tools.ui.color.error", lambda message, stream=None: message)

    assert messaging.render_ok("done").strip().startswith(str(messaging.GLYPHS.bullet.ok))
    assert (
        messaging.render_warning("careful").strip().startswith(str(messaging.GLYPHS.bullet.warning))
    )
    assert (
        messaging.render_error_line("broken").strip().startswith(str(messaging.GLYPHS.bullet.error))
    )
    assert messaging.render_action("running").startswith(f"{messaging.GLYPHS.arrow.right} ")


def test_dry_run_printer_line_variants_and_blank_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(messaging, "_c_info", lambda message, stream=None: message)
    monkeypatch.setattr(messaging, "_c_success", lambda message, stream=None: message)
    monkeypatch.setattr("repo_release_tools.ui.color.error", lambda message, stream=None: message)

    printer = messaging.DryRunPrinter(False)
    stream = io.StringIO()

    printer.line("ok", ok=True, stream=stream)
    printer.line("bad", ok=False, stream=stream)
    printer.line("info", ok=None, newline=False, stream=stream)
    printer.blank_line(2, stream=stream)

    assert stream.getvalue() == (
        f"{messaging.GLYPHS.bullet.ok} ok\n"
        f"{messaging.GLYPHS.bullet.error} bad\n"
        f"{messaging.GLYPHS.arrow.right} info\n\n"
    )
