from __future__ import annotations

import io

from repo_release_tools.ui import progress


class _TtyBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_clear_line_writes_escape_sequence_for_tty() -> None:
    tty = _TtyBuffer()

    progress.clear_line(out=tty)

    assert tty.getvalue() == "\r\x1b[2K"


def test_clear_line_is_noop_for_non_tty() -> None:
    out = io.StringIO()

    progress.clear_line(out=out)

    assert out.getvalue() == ""


def test_progress_line_clear_is_noop_when_not_visible() -> None:
    tty = _TtyBuffer()
    line = progress.ProgressLine(file=tty)

    line.clear()

    assert tty.getvalue() == ""
