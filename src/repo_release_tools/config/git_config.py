"""Git workflow and gate-list config parsing helpers for rrt.

Parses ``[tool.rrt.git]`` (generated-path patterns) and ``[[tool.rrt.gates]]``
(check lines that each record their expected exit code). Patterns are kept
verbatim: git, not this module, interprets them as glob pathspecs.
"""

from __future__ import annotations

from typing import cast

from .model import GateSpec, GitConfig


def _load_git_config(raw: object) -> GitConfig:
    """Parse an optional ``[tool.rrt.git]`` table; absent means no generated paths."""
    if raw is None:
        return GitConfig()
    if not isinstance(raw, dict):
        raise ValueError("tool.rrt.git must be a table")
    d = cast("dict[str, object]", raw)
    return GitConfig(generated=_pattern_tuple(d.get("generated"), label="tool.rrt.git.generated"))


def _load_gates(raw: object) -> tuple[GateSpec, ...]:
    """Parse an optional ``[[tool.rrt.gates]]`` array of tables."""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError("tool.rrt.gates must be an array of tables")

    gates: list[GateSpec] = []
    seen: set[str] = set()
    for index, entry in enumerate(raw):
        label = f"tool.rrt.gates[{index}]"
        if not isinstance(entry, dict):
            raise ValueError(f"{label} must be a table")
        item = cast("dict[str, object]", entry)
        gate = GateSpec(
            name=_required_string(item.get("name"), label=f"{label}.name"),
            run=_run_value(item.get("run"), label=f"{label}.run"),
            expect=_expect_value(item.get("expect"), label=f"{label}.expect"),
            timeout=_timeout_value(item.get("timeout"), label=f"{label}.timeout"),
            description=_optional_string(item.get("description"), label=f"{label}.description"),
        )
        gate.validate()
        if gate.name in seen:
            raise ValueError(f"{label}.name {gate.name!r} is a duplicate gate name")
        seen.add(gate.name)
        gates.append(gate)
    return tuple(gates)


def _pattern_tuple(raw: object, *, label: str) -> tuple[str, ...]:
    """Parse a list of non-empty pattern strings, de-duplicated in order."""
    if raw is None:
        return ()
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise ValueError(f"{label} must be a list of strings")
    values: list[str] = []
    for item in cast("list[str]", raw):
        stripped = item.strip()
        if not stripped:
            raise ValueError(f"{label} must not contain empty strings")
        if stripped not in values:
            values.append(stripped)
    return tuple(values)


def _required_string(raw: object, *, label: str) -> str:
    """Return a required non-empty string, stripped of surrounding whitespace."""
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return raw.strip()


def _optional_string(raw: object, *, label: str) -> str:
    """Return an optional string, defaulting to empty."""
    if raw is None:
        return ""
    if not isinstance(raw, str):
        raise ValueError(f"{label} must be a string")
    return raw.strip()


def _run_value(raw: object, *, label: str) -> str | tuple[str, ...]:
    """Return a gate command: a shell string or a non-empty argv list."""
    if isinstance(raw, str):
        if not raw.strip():
            raise ValueError(f"{label} must not be empty")
        return raw
    if isinstance(raw, list) and raw and all(isinstance(item, str) and item for item in raw):
        return tuple(cast("list[str]", raw))
    raise ValueError(f"{label} must be a string or a non-empty list of non-empty strings")


def _expect_value(raw: object, *, label: str) -> int:
    """Return the expected exit code (default 0)."""
    if raw is None:
        return 0
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError(f"{label} must be an integer")
    return raw


def _timeout_value(raw: object, *, label: str) -> float | None:
    """Return an optional timeout in seconds; ``GateSpec.validate`` checks the range."""
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        raise ValueError(f"{label} must be a number of seconds")
    return float(raw)
