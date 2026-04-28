"""Terminal output helpers with a small shared glyph registry."""

from __future__ import annotations

import json
import pprint
import sys
import textwrap
import threading
from contextlib import contextmanager
from typing import IO, Generator, Literal

from repo_release_tools.ui.glyphs import (
    GLYPHS,
    BoldBoxGlyphs,
    BoxGlyphs,
    BoxStyle,
    Glyph,
    IS_LEGACY_TERMINAL,
    RoundedBoxGlyphs,
    _repeat_to_width,
    display_width,
    pad_right,
)
from repo_release_tools.ui import color as ui_color
from repo_release_tools.ui.layout import rule, section_line, terminal_width  # noqa: F401
from repo_release_tools.ui.syntax import highlight_terminal


SECTION_WIDTH = 52

# OutputContext lives in ui.context to avoid a circular-import cycle
# (output → ui.glyphs → ui.__init__ → output).  Re-export it here so
# callers can do: from repo_release_tools.output import OutputContext
from repo_release_tools.ui.context import OutputContext  # noqa: F401 E402


# Union type for the box-drawing glyph sets accepted by panel().
_AnyBoxGlyphs = BoxGlyphs | RoundedBoxGlyphs | BoldBoxGlyphs


def _interactive_output_enabled(out: IO[str]) -> bool:
    """Return whether *out* supports live terminal redraws."""
    return not IS_LEGACY_TERMINAL and out.isatty()


def _write_live_line(
    message: str,
    *,
    out: IO[str],
    last_width: list[int],
    newline: bool = False,
) -> None:
    """Rewrite the current terminal line, clearing any leftover glyphs."""
    message_width = display_width(message)
    padding = " " * max(0, last_width[0] - message_width)
    print(f"\r{message}{padding}", end="\n" if newline else "", flush=True, file=out)
    last_width[0] = 0 if newline else message_width


def _resolve_box(style: BoxStyle) -> _AnyBoxGlyphs:
    """Return the glyph set matching the requested panel style."""
    if style == "rounded":
        return GLYPHS.rounded_box
    if style == "bold":
        return GLYPHS.bold_box
    # "mixed" and "single" both use single-line corners as the base;
    # for "mixed" the outer frame is switched to bold_box inside panel().
    return GLYPHS.box


def section(title: str) -> str:
    """Render a section heading."""
    return section_line(title, body_width=SECTION_WIDTH, glyph=str(GLYPHS.box.h), left=2)


def panel(
    title: str,
    rows: list[tuple[str, str]],
    *,
    style: BoxStyle = "single",
    expand: bool = False,
    title_mode: Literal["border", "row"] = "border",
) -> str:
    """Render a compact two-column summary panel.

    ``style`` selects the box-drawing character set:

    * ``"single"``  — thin lines (┌ ┐ └ ┘ │ ─)  *default*
    * ``"rounded"`` — rounded corners (╭ ╮ ╰ ╯ │ ─)
    * ``"bold"``    — thick/heavy borders (┏ ┓ ┗ ┛ ┃ ━)
    * ``"mixed"``   — bold outer frame + thin inner dividers

    When ``expand=True``, the value column is stretched so the panel fills the
    available terminal width (``terminal_width() - 4``).
    """
    if not rows:
        return title

    # Resolve outer (frame) and inner (divider) glyph sets.
    outer: _AnyBoxGlyphs = GLYPHS.bold_box if style == "mixed" else _resolve_box(style)
    inner: _AnyBoxGlyphs = GLYPHS.box if style in {"mixed", "single"} else outer

    label_width = max(display_width(label) for label, _ in rows)
    # Keep one trailing cell in the value column so the body width matches the title bar.
    value_width = max(display_width(value) for _, value in rows) + 1
    # Cap value_width so the panel doesn't overflow the terminal.
    max_value_width = terminal_width() - label_width - 11  # 11 = borders + padding
    if max_value_width > 4:
        value_width = min(value_width, max_value_width)

    # When expand=True, stretch value column to fill the terminal width.
    if expand:
        target_row_width = terminal_width() - 4
        current_row_width = label_width + value_width + 7
        if target_row_width > current_row_width:
            value_width += target_row_width - current_row_width

    row_width = label_width + value_width + 7
    border_title = f" {title} "
    row_title = f" {title}"
    min_width = display_width(border_title) + 2
    if title_mode == "row":
        min_width = max(min_width, display_width(row_title) + 3)
    if row_width < min_width:
        value_width += min_width - row_width
        row_width = min_width

    top_fill = row_width - display_width(border_title) - 2
    # Row separator: ├────────┼─────────────────┤  (inner dividers)
    row_sep = (
        f"{inner.left}"
        f"{_repeat_to_width(inner.h, label_width + 2)}"
        f"{inner.cross}"
        f"{_repeat_to_width(inner.h, value_width + 2)}"
        f"{inner.right}"
    )
    # Bottom border: └────────┴─────────────────┘  (outer corners + outer horizontal, inner bottom-T)
    bottom = (
        f"{outer.bl}"
        f"{_repeat_to_width(outer.h, label_width + 2)}"
        f"{inner.bottom}"
        f"{_repeat_to_width(outer.h, value_width + 2)}"
        f"{outer.br}"
    )
    title_sep = (
        f"{outer.left}"
        f"{_repeat_to_width(outer.h, label_width + 2)}"
        f"{inner.top}"
        f"{_repeat_to_width(outer.h, value_width + 2)}"
        f"{outer.right}"
    )

    # Top border uses outer corners + outer horizontal; rows use inner vertical for column divider.
    if title_mode == "row":
        title_width = row_width - 4
        lines = [
            f"{outer.tl}{_repeat_to_width(outer.h, row_width - 2)}{outer.tr}",
            f"{outer.v} {pad_right(title, title_width)} {outer.v}",
            title_sep,
        ]
    else:
        lines = [f"{outer.tl}{border_title}{_repeat_to_width(outer.h, top_fill)}{outer.tr}"]
    for index, (label, value) in enumerate(rows):
        # Wrap long values to value_width cells so the panel stays within terminal bounds.
        wrapped = textwrap.wrap(value, width=value_width) or [""]
        for line_idx, value_line in enumerate(wrapped):
            row_label = label if line_idx == 0 else ""
            lines.append(
                f"{outer.v} {pad_right(row_label, label_width)} {inner.v} "
                f"{pad_right(value_line, value_width)} {outer.v}"
            )
        if index != len(rows) - 1:
            lines.append(row_sep)
    lines.append(bottom)
    return "\n".join(lines)


def banner(title: str, *, style: BoxStyle = "bold") -> str:
    """Render a compact boxed banner around a title."""
    glyphs = _resolve_box(style)
    text = f" {title} "
    width = display_width(text)
    top = f"{glyphs.tl}{_repeat_to_width(glyphs.h, width)}{glyphs.tr}"
    middle = f"{glyphs.v}{text}{glyphs.v}"
    bottom = f"{glyphs.bl}{_repeat_to_width(glyphs.h, width)}{glyphs.br}"
    return "\n".join([top, middle, bottom])


def info(message: str, *, indent: int = 2, stream: IO[str] | None = None) -> str:
    """Render an informational line with an arrow glyph."""
    return status(GLYPHS.arrow.right, ui_color.info(message, stream=stream), indent=indent)


def hint(message: str, *, indent: int = 2, stream: IO[str] | None = None) -> str:
    """Render a hint line with ellipsis typography."""
    return status(
        GLYPHS.typography.ellipsis, ui_color.subtle(message, stream=stream), indent=indent
    )


def status(symbol: Glyph | str, message: str, *, indent: int = 2) -> str:
    """Render an indented status line."""
    return f"{' ' * indent}{symbol} {message}"


def ok(message: str, *, indent: int = 2, stream: IO[str] | None = None) -> str:
    """Render a success line."""
    return status(GLYPHS.bullet.ok, ui_color.success(message, stream=stream), indent=indent)


def warning(message: str, *, indent: int = 2, stream: IO[str] | None = None) -> str:
    """Render a warning line."""
    return status(GLYPHS.bullet.warning, ui_color.warning(message, stream=stream), indent=indent)


def error(message: str, *, indent: int = 2, stream: IO[str] | None = None) -> str:
    """Render an error line."""
    return status(GLYPHS.bullet.error, ui_color.error(message, stream=stream), indent=indent)


def dry_run(message: str, *, indent: int = 2, stream: IO[str] | None = None) -> str:
    """Render a dry-run preview line."""
    return status(
        GLYPHS.bullet.skip,
        ui_color.subtle(f"[dry-run] {message}", stream=stream),
        indent=indent,
    )


def action(message: str, *, indent: int = 0, stream: IO[str] | None = None) -> str:
    """Render an action line."""
    return status(GLYPHS.arrow.right, ui_color.info(message, stream=stream), indent=indent)


def syntax(
    text: str,
    language: str,
    *,
    stream: IO[str] | None = None,
) -> str:
    """Render syntax highlighting with plain-text fallback."""
    return highlight_terminal(text, language, stream=stream)


def dry_run_complete(message: str) -> str:
    """Render the dry-run completion line."""
    return dry_run(f"complete {GLYPHS.typography.mdash} {message}", indent=0)


def hyperlink(text: str, url: str, *, stream: IO[str] | None = None) -> str:
    """Render an OSC 8 terminal hyperlink, with a plain-text fallback.

    When the output stream does not support color (or ``NO_COLOR`` is set),
    returns ``text (url)`` so the URL is still visible.
    """
    if not ui_color.supports_color(stream):
        return f"{text} ({url})"
    return f"\x1b]8;;{url}\x1b\\{text}\x1b]8;;\x1b\\"


def pretty_print(obj: object, *, stream: IO[str] | None = None) -> str:
    """Return a pretty-printed representation of *obj*.

    When syntax highlighting is available the output is colorized.
    """
    text = pprint.pformat(obj, width=100)
    return syntax(text, "python", stream=stream)


def json_highlight(data: object, *, stream: IO[str] | None = None) -> str:
    """Return a syntax-highlighted JSON rendering of *data*.

    Falls back to plain ``json.dumps`` when colour output is unavailable.
    """
    text = json.dumps(data, indent=2, default=str)
    return syntax(text, "json", stream=stream)


def diff_highlight(text: str, *, stream: IO[str] | None = None) -> str:
    """Return a syntax-highlighted unified diff rendering of *text*.

    Falls back to plain text when colour output is unavailable or the diff
    is empty.
    """
    if not text.strip():
        return text
    return syntax(text, "diff", stream=stream)


class ProgressLine:
    """Render a sticky progress line that overwrites in place.

    Usage pattern
    -------------
    * Call ``update_bar()`` after printing a status line to render the bar.
    * Before printing the *next* status line, call ``clear()`` to erase the bar.
    * The caller does **not** need to track how many lines were printed.
    """

    def __init__(self, *, file: IO[str] | None = None) -> None:
        self.out = file if file is not None else sys.stdout
        self.enabled = _interactive_output_enabled(self.out)
        self._visible = False

    def update(self, message: str) -> None:
        """Overwrite the current line with *message* (no trailing newline).

        Emits a clear-to-EOL sequence (``\\x1b[K``) after the message so that
        any leftover characters from a previously longer render are erased.
        """
        if not self.enabled:
            return
        print(f"\r{message}\x1b[K", end="", flush=True, file=self.out)
        self._visible = True

    def clear(self) -> None:
        """Erase the progress line, leaving the cursor at the start of that line.

        Call this before printing a normal status line so the bar is removed
        and the status line is written in its place.
        """
        if not self.enabled or not self._visible:
            return
        print("\r\x1b[2K", end="", flush=True, file=self.out)
        self._visible = False

    def update_bar(self, value: float, *, width: int = 20) -> None:
        """Render a progress bar update on the sticky progress line."""
        self.update(f"  {GLYPHS.progress.render_bar(value, width)}")


@contextmanager
def spinner_lines(
    label: str,
    *,
    detail: str | None = None,
    file: IO[str] | None = None,
) -> Generator[None, None, None]:
    """Context manager that animates a spinner on *file* (default: sys.stderr).

    The spinner runs in a background thread and is cleared on exit.
    When the output is not a tty (CI, pipes) or the terminal is legacy
    (Windows cmd), the context manager is a no-op so nothing is printed.
    """
    out = file if file is not None else sys.stderr
    if not _interactive_output_enabled(out):
        yield
        return

    frames = GLYPHS.progress.spinner()
    stop_event = threading.Event()
    success: list[bool] = [True]
    last_width = [0]

    suffix = f"  {detail}" if detail else ""

    def _animate() -> None:
        while not stop_event.is_set():
            frame = next(frames)
            _write_live_line(f"  {frame}  {label}{suffix}", out=out, last_width=last_width)
            stop_event.wait(timeout=0.08)

    thread = threading.Thread(target=_animate, daemon=True)
    thread.start()
    _cancelled: list[bool] = [False]
    try:
        yield
    except KeyboardInterrupt:
        _cancelled[0] = True
        success[0] = False
        raise
    except Exception:
        success[0] = False
        raise
    finally:
        stop_event.set()
        thread.join(timeout=0.5)
        if _cancelled[0]:
            _write_live_line(
                f"  {GLYPHS.bullet.warning}  {label} \u2014 Cancelled",
                out=out,
                last_width=last_width,
                newline=True,
            )
        else:
            check = GLYPHS.bullet.ok if success[0] else GLYPHS.bullet.error
            _write_live_line(
                f"  {check}  {label}{suffix}",
                out=out,
                last_width=last_width,
                newline=True,
            )
