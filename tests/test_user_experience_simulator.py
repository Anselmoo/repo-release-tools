"""User Experience Simulator tests.


User Experience Simulator test should confirm the unique and user centered experience based on
the columns:

1. Use of design principles
2. Use of consistent and intuitive UI elements
3. Clear and concise communication
4. Accessibility and inclusivity
5. Responsiveness and performance


Test for:

1. Usage of colors
2. Usage of syntax highlighting
3. Usage of progress bars
4. Usage of sparklines
5. Usage of prompts
6. Usage of layout elements (align, box, rule, section_line)
7. Usage of emphasis (bold, italic, underline)
8. Usage of combined styles (apply_style)
9. Usage of terminal width and truncation
10. Usage of color levels and support detection
11. Usage of output context for consistent rendering
12. Usage of error, warning, info, success, subtle functions for appropriate messaging



Affected entrypoints:

## Native entry point
- rrt

## Version & Release
-   bump        Bump project version using [tool.rrt] config
-   ci-version  Compute and apply CI pre-release versions (PEP 440 / SemVer)

## Repository Health
-   doctor  Check the health of the rrt configuration (files, patterns, versions)
-   config  Show the resolved rrt configuration for this repository
-   env     Show environment variables and interpreter details that affect rrt behavior
-   eol     Check host runtimes and project minimums against EOL dates

## Git Workflow
-   branch  Branch management helpers for conventional branch naming
-   git     Git workflow helpers for repository status, commit, sync, and history operations

## Setup & Tooling
-   init   Generate a recommended rrt configuration for the current repository
-   skill  Install the bundled repo-release-tools agent skill

"""

from __future__ import annotations

import io

import pytest

from repo_release_tools.ui import (
    DryRunPrinter,
    apply,
    apply_style,
    bold,
    color,
    detect_color_level,
    error,
    font,
    info,
    italic,
    progress_bar,
    rule,
    section_line,
    sparkline,
    subtle,
    success,
    supports_color,
    syntax,
    truncate,
    underline,
    warning,
)
from repo_release_tools.ui.context import OutputContext
from repo_release_tools.ui.glyphs import display_width
from repo_release_tools.ui.layout import align, box
from repo_release_tools.ui.prompt import ask, confirm

# ── TestColors ────────────────────────────────────────────────────────────────


class TestColors:
    def test_apply_emits_ansi_when_color_supported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(color, "supports_color", lambda stream=None: True)
        result = apply("text", color.Style(fg=31, bold=True))
        assert "\x1b[" in result
        assert result.endswith("\x1b[0m")

    def test_apply_returns_plain_text_without_color(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(color, "supports_color", lambda stream=None: False)
        assert apply("text", color.Style(fg=31, bold=True)) == "text"

    def test_no_color_env_disables_supports_color(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NO_COLOR", "1")
        fake_stream = type("S", (io.StringIO,), {"isatty": lambda self: True})()
        assert not supports_color(fake_stream)

    def test_non_tty_stream_disables_color(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("RRT_COLOR", raising=False)
        assert not supports_color(io.StringIO())  # StringIO.isatty() → False


# ── TestSyntaxHighlight ───────────────────────────────────────────────────────


class TestSyntaxHighlight:
    def test_returns_plain_when_color_level_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(syntax, "detect_color_level", lambda: "none")
        result = syntax.highlight_terminal("key = 'val'", "toml")
        assert result == "key = 'val'"

    def test_returns_highlighted_when_color_on_and_toml(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(syntax, "supports_color", lambda stream=None: True)
        monkeypatch.setattr(syntax, "detect_color_level", lambda: "standard")
        result = syntax.highlight_terminal("key = 'val'", "toml")
        assert "\x1b[" in result
        assert "key" in result

    def test_returns_plain_when_non_tty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(syntax, "supports_color", lambda stream=None: False)
        result = syntax.highlight_terminal("key = 'val'", "toml")
        assert result == "key = 'val'"

    def test_json_key_highlighted_when_color_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(syntax, "supports_color", lambda stream=None: True)
        monkeypatch.setattr(syntax, "detect_color_level", lambda: "standard")
        result = syntax.highlight_terminal('  "name": "rrt"', "json")
        assert "\x1b[" in result

    def test_diff_added_line_green_when_color_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(syntax, "supports_color", lambda stream=None: True)
        monkeypatch.setattr(syntax, "detect_color_level", lambda: "standard")
        result = syntax.highlight_terminal("+added", "diff")
        assert "\x1b[32m" in result

    def test_diff_removed_line_red_when_color_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(syntax, "supports_color", lambda stream=None: True)
        monkeypatch.setattr(syntax, "detect_color_level", lambda: "standard")
        result = syntax.highlight_terminal("-removed", "diff")
        assert "\x1b[31m" in result


# ── TestProgressBar ───────────────────────────────────────────────────────────


class TestProgressBar:
    def test_half_full_bar_glyphs_and_percentage(self) -> None:
        result = progress_bar(0.5, width=10)
        assert "50%" in result
        assert result.count("█") == 5
        assert result.count("░") == 5

    def test_complete_bar_has_no_empty_glyphs(self) -> None:
        result = progress_bar(1.0, width=10)
        assert "100%" in result
        assert "░" not in result

    def test_empty_bar_has_no_filled_glyphs(self) -> None:
        result = progress_bar(0.0, width=10)
        assert "0%" in result
        assert "█" not in result

    def test_label_appears_in_output(self) -> None:
        result = progress_bar(0.75, width=8, label="Updating")
        assert "Updating" in result

    def test_ascii_fallback_when_dumb_term(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TERM", "dumb")
        monkeypatch.delenv("NO_COLOR", raising=False)
        result = progress_bar(0.5, width=6)
        assert "#" in result
        assert "-" in result


# ── TestSparkline ─────────────────────────────────────────────────────────────


class TestSparkline:
    def test_min_maps_to_lowest_glyph(self) -> None:
        result = sparkline([0.0, 5.0, 10.0])
        assert result[0] == "▁"

    def test_max_maps_to_highest_glyph(self) -> None:
        result = sparkline([0.0, 5.0, 10.0])
        assert result[-1] == "█"

    def test_uniform_values_all_lowest_glyph(self) -> None:
        result = sparkline([3.0, 3.0, 3.0])
        assert all(c == "▁" for c in result)

    def test_empty_list_returns_empty_string(self) -> None:
        assert sparkline([]) == ""

    def test_ascii_only_min_and_max_glyphs(self) -> None:
        result = sparkline([0.0, 5.0, 10.0], ascii_only=True)
        assert result[0] == "."
        assert result[-1] == "#"

    def test_width_limits_to_most_recent_values(self) -> None:
        result = sparkline([1.0, 2.0, 3.0, 4.0, 5.0], width=3)
        assert len(result) == 3


# ── TestPrompts ───────────────────────────────────────────────────────────────


class TestPrompts:
    def test_ask_returns_default_on_non_tty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        assert ask("Name?", default="rrt") == "rrt"

    def test_ask_returns_empty_when_no_default_on_non_tty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        assert ask("Name?") == ""

    def test_confirm_returns_true_default_on_non_tty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        assert confirm("Proceed?", default=True) is True

    def test_confirm_returns_false_default_on_non_tty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        assert confirm("Proceed?", default=False) is False

    def test_ask_uses_user_reply_on_tty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        FakeTTY = type("TTY", (io.StringIO,), {"isatty": lambda self: True})
        monkeypatch.setattr("sys.stdin", FakeTTY(""))
        monkeypatch.setattr("builtins.input", lambda _: "repo-release-tools")
        assert ask("Project?", default="rrt") == "repo-release-tools"


# ── TestLayout ────────────────────────────────────────────────────────────────


class TestLayout:
    def test_rule_without_title_fills_exact_width(self) -> None:
        result = rule(width=40)
        assert result.count("─") == 40

    def test_rule_with_title_contains_title_and_dashes(self) -> None:
        result = rule("Options", width=40)
        assert "Options" in result
        assert "─" in result

    def test_section_line_has_leading_glyph_and_title(self) -> None:
        result = section_line("Build", body_width=20, glyph="─", left=2)
        assert result.startswith("──")
        assert "Build" in result

    def test_align_left_pads_right_to_exact_width(self) -> None:
        result = align("hi", width=10, mode="left")
        assert len(result) == 10
        assert result.startswith("hi")

    def test_align_right_pads_left_to_exact_width(self) -> None:
        result = align("hi", width=10, mode="right")
        assert len(result) == 10
        assert result.endswith("hi")

    def test_align_center_is_symmetric(self) -> None:
        result = align("abc", width=9, mode="center")
        assert result.strip() == "abc"
        assert len(result) == 9

    def test_box_single_top_line_starts_with_corner(self) -> None:
        result = box("content", style="single")
        first = result.splitlines()[0]
        assert first.startswith("┌") or first.startswith("+")

    def test_box_rounded_top_line_starts_with_rounded_corner(self) -> None:
        result = box("content", style="rounded")
        first = result.splitlines()[0]
        assert first.startswith("╭") or first.startswith("+")

    def test_box_last_line_ends_with_bottom_right_corner(self) -> None:
        result = box("line one\nline two", style="single")
        last = result.splitlines()[-1]
        assert last.endswith("┘") or last.endswith("+")

    def test_section_line_total_length_near_body_width(self) -> None:
        result = section_line("Test", body_width=60, glyph="─")
        assert display_width(result) >= 10


# ── TestEmphasis ──────────────────────────────────────────────────────────────


class TestEmphasis:
    def test_bold_emits_sgr1_when_color_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            font, "apply", lambda text, style, *, stream=None: f"\x1b[1m{text}\x1b[0m"
        )
        assert "\x1b[1m" in bold("x")

    def test_bold_plain_when_color_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(color, "supports_color", lambda stream=None: False)
        assert bold("x") == "x"

    def test_italic_plain_when_color_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(color, "supports_color", lambda stream=None: False)
        assert italic("x") == "x"

    def test_underline_plain_when_color_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(color, "supports_color", lambda stream=None: False)
        assert underline("x") == "x"

    def test_bold_wraps_text_in_ansi_when_color_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(color, "supports_color", lambda stream=None: True)
        result = bold("hello")
        assert "\x1b[" in result
        assert "hello" in result


# ── TestApplyStyle ────────────────────────────────────────────────────────────


class TestApplyStyle:
    def test_combined_bold_and_named_color_emits_ansi(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(color, "supports_color", lambda stream=None: True)
        result = apply_style("Done!", bold=True, color="success")
        assert "\x1b[" in result
        assert "Done!" in result

    def test_returns_plain_text_when_color_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(color, "supports_color", lambda stream=None: False)
        assert apply_style("plain", bold=True, color="error") == "plain"

    def test_rgb_fg_uses_truecolor_escape(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(color, "supports_color", lambda stream=None: True)
        monkeypatch.setattr(color, "detect_color_level", lambda: "truecolor")
        result = apply_style("colored", fg=(255, 0, 0))
        assert "38;2;255;0;0" in result

    def test_rgb_fg_downsampled_in_standard_no_24bit_code(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(color, "supports_color", lambda stream=None: True)
        monkeypatch.setattr(color, "detect_color_level", lambda: "standard")
        result = apply_style("colored", fg=(255, 0, 0))
        assert "38;2" not in result
        assert "\x1b[" in result


# ── TestTruncation ────────────────────────────────────────────────────────────


class TestTruncation:
    def test_appends_ellipsis_when_text_too_long(self) -> None:
        result = truncate("hello world", width=8)
        assert result.endswith("…")

    def test_returns_text_unchanged_when_it_fits(self) -> None:
        assert truncate("hi", width=20) == "hi"

    def test_display_width_of_result_within_limit(self) -> None:
        result = truncate("abcdefghijklmnopqrstuvwxyz", width=10)
        assert display_width(result) <= 10

    def test_zero_width_returns_empty_string(self) -> None:
        assert truncate("anything", width=0) == ""


# ── TestColorLevels ───────────────────────────────────────────────────────────


class TestColorLevels:
    def test_no_color_env_returns_none_level(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NO_COLOR", "1")
        assert detect_color_level() == "none"

    def test_colorterm_truecolor_returns_truecolor_level(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.delenv("RRT_COLOR", raising=False)
        monkeypatch.setenv("COLORTERM", "truecolor")
        assert detect_color_level() == "truecolor"

    def test_colorterm_24bit_returns_truecolor_level(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.delenv("RRT_COLOR", raising=False)
        monkeypatch.setenv("COLORTERM", "24bit")
        assert detect_color_level() == "truecolor"

    def test_256color_term_returns_256_level(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.delenv("RRT_COLOR", raising=False)
        monkeypatch.delenv("COLORTERM", raising=False)
        monkeypatch.setenv("TERM", "xterm-256color")
        assert detect_color_level() == "256"

    def test_dumb_term_returns_none_level(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.delenv("RRT_COLOR", raising=False)
        monkeypatch.setenv("TERM", "dumb")
        assert detect_color_level() == "none"

    def test_rrt_color_override_off_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.setenv("RRT_COLOR", "0")
        assert detect_color_level() == "none"

    def test_rrt_color_override_truecolor_returns_truecolor(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.setenv("RRT_COLOR", "truecolor")
        assert detect_color_level() == "truecolor"


# ── TestOutputContext ─────────────────────────────────────────────────────────


class TestOutputContext:
    def test_default_format_is_text(self) -> None:
        ctx = OutputContext()
        assert ctx.format == "text"
        assert not ctx.is_json()

    def test_json_format_flag_makes_is_json_true(self) -> None:
        ctx = OutputContext(format="json")
        assert ctx.is_json()

    def test_no_color_flag_stored(self) -> None:
        ctx = OutputContext(no_color=True)
        assert ctx.no_color is True

    def test_stream_defaults_to_none(self) -> None:
        ctx = OutputContext()
        assert ctx.stream is None

    def test_custom_stream_is_stored(self) -> None:
        stream = io.StringIO()
        ctx = OutputContext(stream=stream)
        assert ctx.stream is stream

    def test_no_color_false_by_default(self) -> None:
        ctx = OutputContext()
        assert ctx.no_color is False


# ── TestMessaging ─────────────────────────────────────────────────────────────


class TestMessaging:
    def test_error_emits_ansi_when_color_supported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(color, "supports_color", lambda stream=None: True)
        result = error("bad input")
        assert "\x1b[" in result
        assert "bad input" in result

    def test_error_plain_when_no_color(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(color, "supports_color", lambda stream=None: False)
        assert error("bad input") == "bad input"

    def test_warning_emits_ansi_when_color_supported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(color, "supports_color", lambda stream=None: True)
        result = warning("watch out")
        assert "\x1b[" in result
        assert "watch out" in result

    def test_info_emits_ansi_when_color_supported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(color, "supports_color", lambda stream=None: True)
        result = info("note")
        assert "\x1b[" in result
        assert "note" in result

    def test_success_emits_ansi_when_color_supported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(color, "supports_color", lambda stream=None: True)
        result = success("done")
        assert "\x1b[" in result
        assert "done" in result

    def test_subtle_emits_ansi_when_color_supported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(color, "supports_color", lambda stream=None: True)
        result = subtle("quiet")
        assert "\x1b[" in result
        assert "quiet" in result

    def test_all_messaging_functions_plain_when_no_color(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(color, "supports_color", lambda stream=None: False)
        for fn in (error, warning, info, success, subtle):
            assert fn("msg") == "msg"


# ── TestDryRunPrinter ─────────────────────────────────────────────────────────


class TestDryRunPrinter:
    """Verify DryRunPrinter produces consistent, 0-indent output in both modes."""

    def test_header_live_contains_title(self, capsys: pytest.CaptureFixture[str]) -> None:
        p = DryRunPrinter(dry_run=False)
        p.header("My command")
        out = capsys.readouterr().out
        assert "My command" in out
        assert "[DRY RUN]" not in out

    def test_header_dry_run_labels_title(self, capsys: pytest.CaptureFixture[str]) -> None:
        p = DryRunPrinter(dry_run=True)
        p.header("My command")
        out = capsys.readouterr().out
        assert "[DRY RUN]" in out
        assert "My command" in out

    def test_header_metadata_key_value(self, capsys: pytest.CaptureFixture[str]) -> None:
        p = DryRunPrinter(dry_run=False)
        p.header("Cmd", Version="1.2.3", Branch="main")
        out = capsys.readouterr().out
        assert "Version" in out
        assert "1.2.3" in out
        assert "Branch" in out
        assert "main" in out

    def test_header_not_indented(self, capsys: pytest.CaptureFixture[str]) -> None:
        p = DryRunPrinter(dry_run=False)
        p.header("Zero indent check")
        out = capsys.readouterr().out
        first_line = out.splitlines()[0]
        # strip ANSI codes to check there is no leading space
        import re

        stripped = re.sub(r"\x1b\[[0-9;]*m", "", first_line)
        assert not stripped.startswith(" ")

    def test_section_outputs_rule(self, capsys: pytest.CaptureFixture[str]) -> None:
        p = DryRunPrinter(dry_run=False)
        p.section("My section")
        out = capsys.readouterr().out
        assert "My section" in out
        assert "─" in out or "-" in out  # rule character

    def test_would_run_only_in_dry_run(self, capsys: pytest.CaptureFixture[str]) -> None:
        p = DryRunPrinter(dry_run=True)
        p.would_run("git commit")
        out = capsys.readouterr().out
        assert "git commit" in out
        assert "[dry-run]" in out

    def test_would_write_shows_path(self, capsys: pytest.CaptureFixture[str]) -> None:
        p = DryRunPrinter(dry_run=True)
        p.would_write("CHANGELOG.md", "add entry")
        out = capsys.readouterr().out
        assert "CHANGELOG.md" in out
        assert "add entry" in out

    def test_would_install_shows_name_target_location(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        p = DryRunPrinter(dry_run=True)
        p.would_install("skill.md", "copilot-local", "/some/path")
        out = capsys.readouterr().out
        assert "skill.md" in out
        assert "copilot-local" in out
        assert "/some/path" in out

    def test_action_contains_message(self, capsys: pytest.CaptureFixture[str]) -> None:
        p = DryRunPrinter(dry_run=False)
        p.action("Cloning repo")
        out = capsys.readouterr().out
        assert "Cloning repo" in out

    def test_meta_shows_key_value(self, capsys: pytest.CaptureFixture[str]) -> None:
        p = DryRunPrinter(dry_run=False)
        p.meta("Ref", "refs/heads/main")
        out = capsys.readouterr().out
        assert "Ref" in out
        assert "refs/heads/main" in out

    def test_ok_contains_message(self, capsys: pytest.CaptureFixture[str]) -> None:
        p = DryRunPrinter(dry_run=False)
        p.ok("All done")
        out = capsys.readouterr().out
        assert "All done" in out

    def test_warn_contains_message(self, capsys: pytest.CaptureFixture[str]) -> None:
        p = DryRunPrinter(dry_run=False)
        p.warn("Proceeding anyway")
        out = capsys.readouterr().out
        assert "Proceeding anyway" in out

    def test_footer_live_shows_message_no_dry_run_suffix(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        p = DryRunPrinter(dry_run=False)
        p.footer("Completed")
        out = capsys.readouterr().out
        assert "Completed" in out
        assert "[dry-run]" not in out

    def test_footer_dry_run_shows_complete_line(self, capsys: pytest.CaptureFixture[str]) -> None:
        p = DryRunPrinter(dry_run=True)
        p.footer("no files were modified")
        out = capsys.readouterr().out
        assert "no files were modified" in out
        assert "[dry-run]" in out
        assert "complete" in out

    def test_no_color_fallback(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(color, "supports_color", lambda stream=None: False)
        p = DryRunPrinter(dry_run=False)
        p.ok("plain output")
        out = capsys.readouterr().out
        assert "\x1b[" not in out
        assert "plain output" in out


class TestFileEntry:
    """Verify DryRunPrinter.file_entry renders each kind with path and correct stream."""

    def test_added_contains_path(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("NO_COLOR", "1")
        p = DryRunPrinter(dry_run=False)
        p.file_entry("added", "src/foo.py")
        out = capsys.readouterr().out
        assert "src/foo.py" in out
        assert out.strip()

    def test_removed_contains_path(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("NO_COLOR", "1")
        p = DryRunPrinter(dry_run=False)
        p.file_entry("removed", "src/foo.py")
        out = capsys.readouterr().out
        assert "src/foo.py" in out

    def test_modified_contains_path(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("NO_COLOR", "1")
        p = DryRunPrinter(dry_run=False)
        p.file_entry("modified", "src/foo.py")
        out = capsys.readouterr().out
        assert "src/foo.py" in out

    def test_renamed_contains_path(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("NO_COLOR", "1")
        p = DryRunPrinter(dry_run=False)
        p.file_entry("renamed", "src/foo.py")
        out = capsys.readouterr().out
        assert "src/foo.py" in out

    def test_conflict_contains_path(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("NO_COLOR", "1")
        p = DryRunPrinter(dry_run=False)
        p.file_entry("conflict", "src/foo.py")
        out = capsys.readouterr().out
        assert "src/foo.py" in out

    def test_untracked_contains_path(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("NO_COLOR", "1")
        p = DryRunPrinter(dry_run=False)
        p.file_entry("untracked", "src/foo.py")
        out = capsys.readouterr().out
        assert "src/foo.py" in out

    def test_stream_routes_to_stderr(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import sys

        monkeypatch.setenv("NO_COLOR", "1")
        p = DryRunPrinter(dry_run=False)
        p.file_entry("added", "x.py", stream=sys.stderr)
        captured = capsys.readouterr()
        assert "x.py" in captured.err
        assert "x.py" not in captured.out


class TestListItem:
    """Verify DryRunPrinter.list_item renders bullet text and respects stream=."""

    def test_text_appears_in_stdout(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("NO_COLOR", "1")
        p = DryRunPrinter(dry_run=False)
        p.list_item("deploy to staging")
        captured = capsys.readouterr()
        assert "deploy to staging" in captured.out
        assert captured.err == ""

    def test_stream_routes_to_stderr(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import sys

        monkeypatch.setenv("NO_COLOR", "1")
        p = DryRunPrinter(dry_run=False)
        p.list_item("deploy to staging", stream=sys.stderr)
        captured = capsys.readouterr()
        assert "deploy to staging" in captured.err
        assert "deploy to staging" not in captured.out


class TestWarnStream:
    """Verify DryRunPrinter.warn routes output based on the stream= parameter."""

    def test_warn_defaults_to_stdout(self, capsys: pytest.CaptureFixture[str]) -> None:
        p = DryRunPrinter(dry_run=False)
        p.warn("low disk space")
        captured = capsys.readouterr()
        assert "low disk space" in captured.out
        assert captured.err == ""

    def test_warn_explicit_stderr(self, capsys: pytest.CaptureFixture[str]) -> None:
        import sys

        p = DryRunPrinter(dry_run=False)
        p.warn("low disk space", stream=sys.stderr)
        captured = capsys.readouterr()
        assert "low disk space" in captured.err
        assert "low disk space" not in captured.out
