"""Live terminal progress helpers — spinner and progress bar."""

from __future__ import annotations

import sys
import threading
from contextlib import contextmanager
from typing import IO, Generator

from repo_release_tools.ui.glyphs import GLYPHS, IS_LEGACY_TERMINAL


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
    from repo_release_tools.ui.glyphs import display_width

    message_width = display_width(message)
    padding = " " * max(0, last_width[0] - message_width)
    print(f"\r{message}{padding}", end="\n" if newline else "", flush=True, file=out)
    last_width[0] = 0 if newline else message_width


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
        print(f"\r{message}\x1b[K", end="", flush=True, file=self.out)
        self._visible = True

    def clear(self) -> None:
        """Erase the progress line, leaving the cursor at the start of that line."""
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
