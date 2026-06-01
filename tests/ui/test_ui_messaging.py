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


def test_verbose_line_suppressed_at_level_zero() -> None:
    stream = io.StringIO()
    printer = messaging.DryRunPrinter(dry_run=False, verbose=0)
    printer.verbose_line("should not appear", stream=stream)
    assert stream.getvalue() == ""


def test_verbose_line_emitted_at_matching_level() -> None:
    stream = io.StringIO()
    printer = messaging.DryRunPrinter(dry_run=False, verbose=1)
    printer.verbose_line("hello", level=1, stream=stream)
    assert "hello" in stream.getvalue()


def test_verbose_line_suppressed_when_level_exceeds_verbosity() -> None:
    stream = io.StringIO()
    printer = messaging.DryRunPrinter(dry_run=False, verbose=1)
    printer.verbose_line("too detailed", level=2, stream=stream)
    assert stream.getvalue() == ""


def test_verbose_line_emitted_at_all_higher_levels() -> None:
    stream = io.StringIO()
    printer = messaging.DryRunPrinter(dry_run=False, verbose=3)
    printer.verbose_line("level1", level=1, stream=stream)
    printer.verbose_line("level2", level=2, stream=stream)
    printer.verbose_line("level3", level=3, stream=stream)
    out = stream.getvalue()
    assert "level1" in out
    assert "level2" in out
    assert "level3" in out


def test_base_printer_footer_has_no_dry_run_line(capsys: pytest.CaptureFixture[str]) -> None:
    messaging.BasePrinter().footer("Done.")
    out = capsys.readouterr().out
    assert "Done." in out
    assert "[dry-run]" not in out


def test_dry_run_printer_header_prefixes_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    messaging.DryRunPrinter(dry_run=True).header("Version bump")
    assert "[DRY RUN] Version bump" in capsys.readouterr().out


def test_dry_run_printer_header_no_prefix_when_disabled(
    capsys: pytest.CaptureFixture[str],
) -> None:
    messaging.DryRunPrinter(dry_run=False).header("Version bump")
    out = capsys.readouterr().out
    assert "Version bump" in out
    assert "[DRY RUN]" not in out


def test_dry_run_printer_footer_appends_completion_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    messaging.DryRunPrinter(dry_run=True).footer("Done.")
    out = capsys.readouterr().out
    assert "Done." in out
    assert "[dry-run] complete" in out


def test_dry_run_printer_footer_plain_when_disabled(
    capsys: pytest.CaptureFixture[str],
) -> None:
    messaging.DryRunPrinter(dry_run=False).footer("Done.")
    out = capsys.readouterr().out
    assert "Done." in out
    assert "[dry-run]" not in out


def test_verbose_printer_suppresses_at_level_zero() -> None:
    stream = io.StringIO()
    printer = messaging.VerbosePrinter()
    printer.debug("nope", stream=stream)
    printer.trace("nope", stream=stream)
    assert stream.getvalue() == ""


def test_verbose_printer_debug_emits_at_level_one() -> None:
    stream = io.StringIO()
    printer = messaging.VerbosePrinter(verbose=1)
    printer.debug("seen", stream=stream)
    printer.trace("hidden", stream=stream)
    out = stream.getvalue()
    assert "seen" in out
    assert "hidden" not in out


def test_verbose_printer_trace_emits_at_level_two() -> None:
    stream = io.StringIO()
    printer = messaging.VerbosePrinter(verbose=2)
    printer.trace("traced", stream=stream)
    assert "traced" in stream.getvalue()


def test_verbose_printer_defaults_to_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    messaging.VerbosePrinter(verbose=1).debug("to-stderr")
    captured = capsys.readouterr()
    assert "to-stderr" in captured.err
    assert captured.out == ""


def test_dry_run_printer_exposes_verbosity_helpers() -> None:
    """Dry-run flows must get -v/-vv verbose output 'on top' of previews."""
    stream = io.StringIO()
    printer = messaging.DryRunPrinter(dry_run=True, verbose=1)
    printer.debug("v1", stream=stream)
    printer.trace("v2", stream=stream)
    out = stream.getvalue()
    assert "v1" in out
    assert "v2" not in out


def test_dry_run_printer_trace_emits_at_level_two() -> None:
    stream = io.StringIO()
    messaging.DryRunPrinter(dry_run=True, verbose=2).trace("deep", stream=stream)
    assert "deep" in stream.getvalue()


def test_base_printer_debug_trace_gated() -> None:
    stream = io.StringIO()
    printer = messaging.BasePrinter(verbose=0)
    printer.debug("nope", stream=stream)
    printer.trace("nope", stream=stream)
    assert stream.getvalue() == ""
