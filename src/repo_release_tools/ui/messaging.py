"""Semantic message renderers for CLI errors and hints."""

from __future__ import annotations

import sys
from typing import IO

from repo_release_tools.ui.color import (
    apply_style,
    supports_color,
)
from repo_release_tools.ui.color import (
    info as _c_info,
)
from repo_release_tools.ui.color import (
    subtle as _c_subtle,
)
from repo_release_tools.ui.color import (
    success as _c_success,
)
from repo_release_tools.ui.color import (
    warning as _c_warning,
)
from repo_release_tools.ui.context import OutputContext
from repo_release_tools.ui.font import bold
from repo_release_tools.ui.glyphs import GLYPHS, Glyph
from repo_release_tools.ui.layout import rule, terminal_width


def error(
    message: str,
    *,
    hint: str | None = None,
    ctx: OutputContext | None = None,
    stream: IO[str] | None = None,
) -> str:
    """Render a consistent CLI error with an optional hint line."""
    out = stream if stream is not None else sys.stderr
    use_color = False if ctx and ctx.no_color else supports_color(out)

    if use_color:
        prefix = apply_style("✖  error:", color="error", bold=True, stream=out)
        rendered_message = apply_style(message, bold=True, stream=out)
        lines = [f"{prefix} {rendered_message}"]
        if hint:
            lines.append(f"   {bold('Hint:')} {hint}")
        return "\n".join(lines)

    lines = [f"[ERROR] {message}"]
    if hint:
        lines.append(f"Hint: {hint}")
    return "\n".join(lines)


# ── Free-function line renderers (migrated from output.py) ───────────────────
# These build and return styled strings; they do not print themselves.
# For printing, use DryRunPrinter methods or call print(render_*(…)) explicitly.


def render_status(symbol: Glyph | str, message: str, *, indent: int = 2) -> str:
    """Render an indented status line: ``<indent><symbol> <message>``."""
    return f"{' ' * indent}{symbol} {message}"


def render_info(message: str, *, indent: int = 2, stream: IO[str] | None = None) -> str:
    """Render an informational line: ``→ <message>``."""
    return render_status(GLYPHS.arrow.right, _c_info(message, stream=stream), indent=indent)


def render_hint(message: str, *, indent: int = 2, stream: IO[str] | None = None) -> str:
    """Render a hint line: ``… <message>``."""
    return render_status(
        GLYPHS.typography.ellipsis,
        _c_subtle(message, stream=stream),
        indent=indent,
    )


def render_ok(message: str, *, indent: int = 2, stream: IO[str] | None = None) -> str:
    """Render a success line: ``✔ <message>``."""
    return render_status(GLYPHS.bullet.ok, _c_success(message, stream=stream), indent=indent)


def render_warning(message: str, *, indent: int = 2, stream: IO[str] | None = None) -> str:
    """Render a warning line: ``▲ <message>``."""
    return render_status(GLYPHS.bullet.warning, _c_warning(message, stream=stream), indent=indent)


def render_error_line(message: str, *, indent: int = 2, stream: IO[str] | None = None) -> str:
    """Render an error status line: ``✖ <message>`` (not a CLI error block)."""
    from repo_release_tools.ui.color import error as _c_error

    return render_status(GLYPHS.bullet.error, _c_error(message, stream=stream), indent=indent)


def render_dry_run(message: str, *, indent: int = 2, stream: IO[str] | None = None) -> str:
    """Render a dry-run preview line: ``⊖ [dry-run] <message>``."""
    return render_status(
        GLYPHS.bullet.skip,
        _c_subtle(f"[dry-run] {message}", stream=stream),
        indent=indent,
    )


def render_action(message: str, *, indent: int = 0, stream: IO[str] | None = None) -> str:
    """Render an action line: ``→ <message>`` (no indent)."""
    return render_status(GLYPHS.arrow.right, _c_info(message, stream=stream), indent=indent)


def render_dry_run_complete(message: str) -> str:
    """Render the canonical dry-run completion line."""
    return render_dry_run(f"complete {GLYPHS.typography.mdash} {message}", indent=0)


class BasePrinter:
    """Common glyph-prefixed structured output for rrt subcommands.

    All lines are emitted at column 0 (no leading indent).  Glyphs degrade
    automatically to ASCII equivalents on legacy terminals and when
    ``NO_COLOR`` is set.

    This is the shared implementation behind :class:`DryRunPrinter` (which adds
    dry-run preview rendering) and :class:`VerbosePrinter` (the named printer for
    non-dry-run flows).  It is an implementation detail and is intentionally not
    part of the public ``repo_release_tools.ui`` surface.

    Verbose diagnostics live here because verbosity is a cross-cutting capability
    shared by every printer: both dry-run and non-dry-run flows may emit
    ``-v/-vv/-vvv`` output "on top" of their normal rendering.  The ``-v`` count
    maps to gating levels ``-v`` → 1 (:meth:`debug`), ``-vv`` → 2 (:meth:`trace`),
    ``-vvv`` → 3 (``verbose_line(..., level=3)``).
    """

    def __init__(self, verbose: int = 0) -> None:
        """Initialize the printer with an optional ``verbose`` gating level."""
        self.verbose = verbose
        self._width = terminal_width()

    def header(self, title: str, **metadata: str) -> None:
        """Print the command header with optional key→value metadata lines."""
        print(f"{GLYPHS.bullet.ok} {_c_success(title)}")
        for key, value in metadata.items():
            print(f"{GLYPHS.arrow.right} {bold(key)}: {_c_info(value)}")
        print()

    def section(self, name: str) -> None:
        """Print a full-width section rule."""
        print(rule(name, width=self._width))

    def action(self, message: str, *, stream: IO[str] | None = None) -> None:
        """Print an informational action line (→ message)."""
        out = stream if stream is not None else sys.stdout
        print(f"{GLYPHS.arrow.right} {_c_info(message)}", file=out)

    def meta(self, key: str, value: str, *, stream: IO[str] | None = None) -> None:
        """Print a key: value metadata line (→ bold(key): value)."""
        out = stream if stream is not None else sys.stdout
        print(f"{GLYPHS.arrow.right} {bold(key)}: {_c_info(value)}", file=out)

    def ok(self, message: str) -> None:
        """Print a success line (✔ message)."""
        print(f"{GLYPHS.bullet.ok} {_c_success(message)}")

    def line(
        self,
        message: str,
        *,
        ok: bool | None = None,
        newline: bool = True,
        stream: IO[str] | None = None,
    ) -> None:
        """Print a generic single-line message.

        ok=True  -> success glyph + success color
        ok=False -> error glyph + error color
        ok=None  -> informational arrow + info color

        newline controls whether a trailing newline is emitted (default True).
        stream overrides the output stream (default: sys.stdout).
        """
        from repo_release_tools.ui.color import error as _c_error

        out = stream if stream is not None else sys.stdout
        end = "\n" if newline else ""
        if ok is True:
            print(f"{GLYPHS.bullet.ok} {_c_success(message)}", file=out, end=end)
        elif ok is False:
            print(f"{GLYPHS.bullet.error} {_c_error(message)}", file=out, end=end)
        else:
            print(f"{GLYPHS.arrow.right} {_c_info(message)}", file=out, end=end)

    def blank_line(self, count: int = 1, *, stream: IO[str] | None = None) -> None:
        """Emit blank lines to the output stream."""
        out = stream if stream is not None else sys.stdout
        for _ in range(count):
            print(file=out)

    def warn(self, message: str, *, stream: IO[str] | None = None) -> None:
        """Print a warning line (▲ message)."""
        out = stream if stream is not None else sys.stdout
        print(f"{GLYPHS.bullet.warning} {_c_warning(message)}", file=out)

    def verbose_line(self, message: str, *, level: int = 1, stream: IO[str] | None = None) -> None:
        """Print message only when ``self.verbose >= level``."""
        if self.verbose >= level:
            out = stream if stream is not None else sys.stderr
            print(f"{GLYPHS.arrow.right} {_c_subtle(message)}", file=out)

    def debug(self, message: str, *, stream: IO[str] | None = None) -> None:
        """Print *message* only when ``self.verbose >= 1`` (``-v``, level-1 diagnostics)."""
        self.verbose_line(message, level=1, stream=stream)

    def trace(self, message: str, *, stream: IO[str] | None = None) -> None:
        """Print *message* only when ``self.verbose >= 2`` (``-vv``, level-2 diagnostics)."""
        self.verbose_line(message, level=2, stream=stream)

    def file_entry(self, kind: str, path_text: str, *, stream: IO[str] | None = None) -> None:
        """Print a git-status entry with a semantic diff glyph and path color.

        *kind* must be one of ``"added"``, ``"removed"``, ``"modified"``,
        ``"renamed"``, ``"conflict"``, or ``"untracked"``.
        """
        from repo_release_tools.ui.color import error as _c_error

        out = stream if stream is not None else sys.stdout
        glyph_map = {
            "added": GLYPHS.diff.added,
            "removed": GLYPHS.diff.removed,
            "modified": GLYPHS.diff.modified,
            "renamed": GLYPHS.diff.renamed,
            "conflict": GLYPHS.diff.conflict,
            "untracked": GLYPHS.git.untracked,
        }
        color_map = {
            "added": _c_success,
            "removed": _c_error,
            "modified": _c_warning,
            "renamed": _c_info,
            "conflict": _c_error,
            "untracked": _c_subtle,
        }
        glyph = glyph_map.get(kind, GLYPHS.bullet.dot)
        color_fn = color_map.get(kind, _c_info)
        path_colored = path_text if kind == "conflict" else _c_subtle(path_text)
        print(f"  {color_fn(str(glyph))} {path_colored}", file=out)

    def list_item(self, text: str, *, stream: IO[str] | None = None) -> None:
        """Print a bullet list item (• text) without an arrow prefix."""
        out = stream if stream is not None else sys.stdout
        print(f"  {GLYPHS.bullet.dot} {_c_subtle(text)}", file=out)

    def footer(self, message: str) -> None:
        """Print the command footer."""
        print(f"{GLYPHS.bullet.ok} {_c_success(message)}")
        print()


class DryRunPrinter(BasePrinter):
    """Structured output with dry-run preview rendering for rrt subcommands.

    Usage::

        p = DryRunPrinter(dry_run=args.dry_run)
        p.header("Version bump", current=f"{old} → {new}", branch=branch_name)
        p.section("Updating version strings")
        p.would_run(f"git checkout -b {branch_name}")
        p.footer("Done.")

    When ``dry_run=True``, :meth:`header` prepends ``[DRY RUN]`` to the title
    and :meth:`footer` appends the canonical dry-run completion line.
    """

    def __init__(self, dry_run: bool, verbose: int = 0) -> None:
        """Initialize printer; pass ``dry_run=True`` to prefix commands with ``[DRY RUN]``."""
        super().__init__(verbose=verbose)
        self.dry_run = dry_run

    def header(self, title: str, **metadata: str) -> None:
        """Print the command header, prefixing ``[DRY RUN]`` when ``dry_run=True``."""
        label = f"[DRY RUN] {title}" if self.dry_run else title
        super().header(label, **metadata)

    def would_run(self, cmd: str) -> None:
        """Print a dry-run 'Would run: <cmd>' line with shell syntax highlighting."""
        from repo_release_tools.ui.syntax import highlight_terminal

        prefix = _c_subtle(f"{GLYPHS.bullet.skip} [dry-run] Would run: ")
        print(f"{prefix}{highlight_terminal(cmd, 'shell')}")

    def would_write(self, path: str, detail: str = "") -> None:
        """Print a dry-run 'Would update <path>' line with path underlined."""
        from repo_release_tools.ui.font import underline

        suffix = f": {detail}" if detail else ""
        print(_c_subtle(f"{GLYPHS.bullet.skip} [dry-run] Would update {underline(path)}{suffix}"))

    def would_install(self, name: str, target: str, location: str) -> None:
        """Print a dry-run 'Would install <name> to <target>' line with location underlined."""
        from repo_release_tools.ui.font import underline

        print(
            _c_subtle(
                f"{GLYPHS.bullet.skip} [dry-run] Would install {name} to {target}: "
                f"{underline(location)}",
            ),
        )

    def footer(self, message: str) -> None:
        """Print the command footer and, when dry_run=True, the completion line."""
        super().footer(message)
        if self.dry_run:
            print(
                _c_subtle(
                    f"{GLYPHS.bullet.skip} [dry-run] complete {GLYPHS.typography.mdash} no changes made",
                ),
            )


class VerbosePrinter(BasePrinter):
    """Structured output for non-dry-run flows, carrying ``-v/-vv/-vvv`` verbosity.

    Use this as the default printer for any command path that does **not** render
    dry-run previews.  It is the named, intent-revealing counterpart to
    :class:`DryRunPrinter`: both inherit the same verbosity-aware API
    (:meth:`verbose_line`, :meth:`debug`, :meth:`trace`) from :class:`BasePrinter`,
    so output stays uniform whether or not a flow is a dry run.

    Verbosity remains opt-in: with the default ``verbose=0`` nothing from
    :meth:`debug`, :meth:`trace`, or :meth:`verbose_line` is emitted.
    """
