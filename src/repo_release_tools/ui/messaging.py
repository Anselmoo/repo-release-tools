"""Semantic message renderers for CLI errors and hints."""

from __future__ import annotations

import sys

from typing import IO

from repo_release_tools.ui import OutputContext, apply_style, bold, supports_color


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
