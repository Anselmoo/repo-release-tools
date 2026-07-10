"""Shared config-loading error handling for `commands/*.py` handlers.

`load_or_autodetect_config` raises three distinct error shapes that every
command entry point must translate into the same guidance-printing output:
``FileNotFoundError`` (no supported config file at all), ``ValueError``
signalling a missing ``[tool.rrt]`` table (checked via
:func:`~repo_release_tools.config.is_missing_tool_rrt_error`), any other
``ValueError``, and ``RuntimeError``. Before this module existed, the
``try/except`` block that renders these four outcomes was copy-pasted with
small print-call variations across ``bump.py``, ``doctor.py``,
``release_notes.py``, ``tag.py``, ``release_cmd.py``, ``ci_version.py``, and
``release_repair.py``.

:func:`describe_config_load_error` centralizes the *decision* (which of the
four outcomes occurred, and what text/severity it implies) without owning
*how* the caller prints or returns — call sites differ enough in those two
respects (some print two lines, some print one; some use ``p.line`` for the
guidance line, others use ``p.action``/``p.warn``; return values range over
``int``, ``None``, and a 3-tuple) that forcing a single print routine would
either drift a call site's exact bytes or require as many parameters as the
copy-pasted code had branches. Centralizing the *classification* removes all
of the duplicated ``isinstance``/``is_missing_tool_rrt_error`` branching and
the repeated `format_missing_tool_rrt_guidance` composition, while leaving
each call site's existing print calls (already covered by tests asserting
exact output) untouched in shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from repo_release_tools.config import (
    format_missing_tool_rrt_guidance,
    is_missing_tool_rrt_error,
    iter_config_files,
)


@dataclass(frozen=True)
class ConfigLoadError:
    """Classified outcome of a failed ``load_or_autodetect_config`` call.

    ``kind`` is one of ``"no_config_file"`` (``FileNotFoundError``),
    ``"missing_tool_rrt"`` (a ``ValueError`` recognized by
    :func:`is_missing_tool_rrt_error`), or ``"other"`` (any other
    ``ValueError`` or a ``RuntimeError``).

    ``text`` is the pre-rendered `format_missing_tool_rrt_guidance` output
    for ``"no_config_file"``/``"missing_tool_rrt"``, or ``str(exc)`` for
    ``"other"``. It is always a plain ``str`` (never ``None``) so callers can
    pass it straight to a printer without an extra narrowing check; which
    meaning it carries is determined by ``kind``.
    """

    kind: str
    text: str


def describe_config_load_error(
    exc: FileNotFoundError | ValueError | RuntimeError,
    root: Path,
    *,
    no_config_file_checked: list[Path] | None = None,
) -> ConfigLoadError:
    """Classify an exception raised by ``load_or_autodetect_config(root)``.

    *exc* is one of the three exception types ``load_or_autodetect_config``
    raises; callers narrow to this union via their own ``except`` clause
    before calling in, so no other exception type reaches this function.

    *no_config_file_checked* controls the file list passed to
    `format_missing_tool_rrt_guidance` for the ``FileNotFoundError`` case:
    most call sites pass ``[]`` (nothing was found so nothing was checked),
    but ``doctor.py`` and ``tag.py`` pass ``iter_config_files(root)``
    instead. Defaults to ``[]`` to match the majority (canonical) behavior.
    Only evaluated for the ``FileNotFoundError`` branch.
    """
    if isinstance(exc, FileNotFoundError):
        checked = no_config_file_checked if no_config_file_checked is not None else []
        return ConfigLoadError(
            kind="no_config_file",
            text=format_missing_tool_rrt_guidance(root, checked),
        )
    if isinstance(exc, ValueError) and is_missing_tool_rrt_error(exc):
        return ConfigLoadError(
            kind="missing_tool_rrt",
            text=format_missing_tool_rrt_guidance(root, iter_config_files(root)),
        )
    return ConfigLoadError(kind="other", text=str(exc))
