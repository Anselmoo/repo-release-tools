"""Semantic message renderers for CLI errors and hints."""

from __future__ import annotations

import sys

from typing import IO

from repo_release_tools.ui.color import apply_style, info, subtle, success, supports_color
from repo_release_tools.ui.context import OutputContext
from repo_release_tools.ui.font import bold
from repo_release_tools.ui.glyphs import GLYPHS
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


class DryRunPrinter:
    """Consistent glyph-prefixed output for rrt subcommands.

    All lines are emitted at column 0 (no leading indent).  Glyphs degrade
    automatically to ASCII equivalents on legacy terminals and when
    ``NO_COLOR`` is set.

    Usage::

        p = DryRunPrinter(dry_run=args.dry_run)
        p.header("Version bump", current=f"{old} → {new}", branch=branch_name)
        p.section("Updating version strings")
        p.would_run(f"git checkout -b {branch_name}")
        p.footer("Done.")

    When ``dry_run=True``, :meth:`header` prepends ``[DRY RUN]`` to the title
    and :meth:`footer` appends the canonical dry-run completion line.
    """

    def __init__(self, dry_run: bool) -> None:
        self.dry_run = dry_run
        self._width = terminal_width()

    def header(self, title: str, **metadata: str) -> None:
        """Print the command header with optional key→value metadata lines."""
        label = f"[DRY RUN] {title}" if self.dry_run else title
        print(f"{GLYPHS.bullet.ok} {success(label)}")
        for key, value in metadata.items():
            print(f"{GLYPHS.arrow.right} {info(f'{key}: {value}')}")
        print()

    def section(self, name: str) -> None:
        """Print a full-width section rule."""
        print(rule(name, width=self._width))

    def would_run(self, cmd: str) -> None:
        """Print a dry-run 'Would run: <cmd>' line."""
        print(subtle(f"{GLYPHS.bullet.skip} [dry-run] Would run: {cmd}"))

    def would_write(self, path: str, detail: str = "") -> None:
        """Print a dry-run 'Would update <path>' line."""
        suffix = f": {detail}" if detail else ""
        print(subtle(f"{GLYPHS.bullet.skip} [dry-run] Would update {path}{suffix}"))

    def would_install(self, name: str, target: str, location: str) -> None:
        """Print a dry-run 'Would install <name> to <target>' line."""
        print(
            subtle(f"{GLYPHS.bullet.skip} [dry-run] Would install {name} to {target}: {location}")
        )

    def action(self, message: str) -> None:
        """Print an informational action line (→ message)."""
        print(f"{GLYPHS.arrow.right} {info(message)}")

    def meta(self, key: str, value: str) -> None:
        """Print a key: value metadata line (→ key: value)."""
        print(f"{GLYPHS.arrow.right} {info(f'{key}: {value}')}")

    def ok(self, message: str) -> None:
        """Print a success line (✔ message)."""
        print(f"{GLYPHS.bullet.ok} {success(message)}")

    def warn(self, message: str) -> None:
        """Print a warning line (▲ message)."""
        from repo_release_tools.ui.color import warning  # local import to avoid unused warning

        print(f"{GLYPHS.bullet.warning} {warning(message)}")

    def footer(self, message: str) -> None:
        """Print the command footer and, when dry_run=True, the completion line."""
        print(f"{GLYPHS.bullet.ok} {success(message)}")
        print()
        if self.dry_run:
            print(
                subtle(
                    f"{GLYPHS.bullet.skip} [dry-run] complete {GLYPHS.typography.mdash} no changes made"
                )
            )
