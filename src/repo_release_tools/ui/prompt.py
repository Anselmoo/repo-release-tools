"""Simple interactive prompt helpers for rrt CLI commands.

These helpers degrade gracefully in non-interactive environments:
* ``confirm`` returns *default* when stdin is not a tty.
* ``ask`` returns *default* (or an empty string) when stdin is not a tty.
"""

from __future__ import annotations

import sys
from typing import IO


def confirm(
    message: str,
    default: bool = False,
    *,
    stream: IO[str] | None = None,
) -> bool:
    """Prompt the user for a yes/no confirmation.

    Returns *default* immediately when stdin is not interactive (CI, pipes).

    Parameters
    ----------
    message:    Question to display.
    default:    Value returned for a blank reply and in non-interactive mode.
    stream:     Output stream (default: ``sys.stdout``).
    """
    out = stream if stream is not None else sys.stdout
    if not sys.stdin.isatty():
        return default
    hint = "[Y/n]" if default else "[y/N]"
    try:
        reply = input(f"{message} {hint} ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        out.write("\n")
        return default
    if not reply:
        return default
    return reply in {"y", "yes"}


def ask(
    message: str,
    default: str | None = None,
    *,
    stream: IO[str] | None = None,
) -> str:
    """Prompt the user for a freeform text reply.

    Returns *default* (or ``""`` when *default* is ``None``) immediately when
    stdin is not interactive.

    Parameters
    ----------
    message:    Prompt text.
    default:    Value returned for a blank reply and in non-interactive mode.
    stream:     Output stream (default: ``sys.stdout``).
    """
    out = stream if stream is not None else sys.stdout
    fallback = default if default is not None else ""
    if not sys.stdin.isatty():
        return fallback
    hint = f" [{default}]" if default else ""
    try:
        reply = input(f"{message}{hint}: ").strip()
    except (EOFError, KeyboardInterrupt):
        out.write("\n")
        return fallback
    return reply if reply else fallback
