"""Terminal output helpers with a small shared glyph registry."""

from __future__ import annotations

import sys
import threading
from contextlib import contextmanager
from typing import IO, Generator

from repo_release_tools.glyphs import (
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


SECTION_WIDTH = 52

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
    fill = max(1, SECTION_WIDTH - display_width(title))
    return f"{GLYPHS.box.h * 2} {title} {GLYPHS.box.h * fill}"


def panel(title: str, rows: list[tuple[str, str]], *, style: BoxStyle = "single") -> str:
    """Render a compact two-column summary panel.

    ``style`` selects the box-drawing character set:

    * ``"single"``  — thin lines (┌ ┐ └ ┘ │ ─)  *default*
    * ``"rounded"`` — rounded corners (╭ ╮ ╰ ╯ │ ─)
    * ``"bold"``    — thick/heavy borders (┏ ┓ ┗ ┛ ┃ ━)
    * ``"mixed"``   — bold outer frame + thin inner dividers
    """
    if not rows:
        return title

    # Resolve outer (frame) and inner (divider) glyph sets.
    outer: _AnyBoxGlyphs = GLYPHS.bold_box if style == "mixed" else _resolve_box(style)
    inner: _AnyBoxGlyphs = GLYPHS.box if style in {"mixed", "single"} else outer

    label_width = max(display_width(label) for label, _ in rows)
    # Keep one trailing cell in the value column so the body width matches the title bar.
    value_width = max(display_width(value) for _, value in rows) + 1
    title_text = f" {title} "
    row_width = label_width + value_width + 7
    min_width = display_width(title_text) + 2
    if row_width < min_width:
        value_width += min_width - row_width
        row_width = min_width

    top_fill = row_width - display_width(title_text) - 2
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

    # Top border uses outer corners + outer horizontal; rows use inner vertical for column divider.
    lines = [f"{outer.tl}{title_text}{_repeat_to_width(outer.h, top_fill)}{outer.tr}"]
    for index, (label, value) in enumerate(rows):
        lines.append(
            f"{outer.v} {pad_right(label, label_width)} {inner.v} "
            f"{pad_right(value, value_width)} {outer.v}"
        )
        if index != len(rows) - 1:
            lines.append(row_sep)
    lines.append(bottom)
    return "\n".join(lines)


def status(symbol: Glyph | str, message: str, *, indent: int = 2) -> str:
    """Render an indented status line."""
    return f"{' ' * indent}{symbol} {message}"


def ok(message: str, *, indent: int = 2) -> str:
    """Render a success line."""
    return status(GLYPHS.bullet.ok, message, indent=indent)


def warning(message: str, *, indent: int = 2) -> str:
    """Render a warning line."""
    return status(GLYPHS.bullet.warning, message, indent=indent)


def error(message: str, *, indent: int = 2) -> str:
    """Render an error line."""
    return status(GLYPHS.bullet.error, message, indent=indent)


def dry_run(message: str, *, indent: int = 2) -> str:
    """Render a dry-run preview line."""
    return status(GLYPHS.bullet.skip, f"[dry-run] {message}", indent=indent)


def action(message: str, *, indent: int = 0) -> str:
    """Render an action line."""
    return status(GLYPHS.arrow.right, message, indent=indent)


def dry_run_complete(message: str) -> str:
    """Render the dry-run completion line."""
    return dry_run(f"complete {GLYPHS.typography.mdash} {message}", indent=0)


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
        """Overwrite the current line with *message* (no trailing newline)."""
        if not self.enabled:
            return
        print(f"\r{message}", end="", flush=True, file=self.out)
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
    try:
        yield
    except Exception:
        success[0] = False
        raise
    finally:
        stop_event.set()
        thread.join(timeout=0.5)
        check = GLYPHS.bullet.ok if success[0] else GLYPHS.bullet.error
        _write_live_line(
            f"  {check}  {label}{suffix}",
            out=out,
            last_width=last_width,
            newline=True,
        )
