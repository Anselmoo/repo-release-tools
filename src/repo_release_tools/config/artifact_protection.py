"""Artifact protection config parsing helpers for rrt.

Parses ``[tool.rrt.artifact_protection]`` — the declaration half of the
artifact-protection lens. The scanner half (which finds artifact fetches in
CI config) lives in ``repo_release_tools.tools.ci_artifact_refs`` and is not
touched here; a later task joins the two by matching a scanned fetch's
``job`` string against a declared :class:`ConsumedArtifact.job` by exact
equality.
"""

from __future__ import annotations

from typing import cast

from .model import ArtifactProtection, ConsumedArtifact


def _load_artifact_protection(raw: object) -> ArtifactProtection | None:
    """Parse an optional ``[tool.rrt.artifact_protection]`` table."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("tool.rrt.artifact_protection must be a table")

    d: dict[str, object] = cast("dict[str, object]", raw)
    config = ArtifactProtection(
        protected_refs=_string_tuple(d.get("protected_refs"), label="protected_refs"),
        consumed=_load_consumed(d.get("consumed")),
    )
    config.validate()
    return config


def _load_consumed(raw: object) -> tuple[ConsumedArtifact, ...]:
    """Parse the ``consumed`` array of tables."""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError("tool.rrt.artifact_protection.consumed must be an array of tables")

    consumed: list[ConsumedArtifact] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"tool.rrt.artifact_protection.consumed[{index}] must be a table")
        item = cast("dict[str, object]", entry)

        artifacts = _string_tuple(item.get("artifacts"), label=f"consumed[{index}].artifacts")
        if not artifacts:
            raise ValueError(
                f"tool.rrt.artifact_protection.consumed[{index}].artifacts must not be empty",
            )
        consumed_by = _string_tuple(item.get("consumed_by"), label=f"consumed[{index}].consumed_by")
        if not consumed_by:
            raise ValueError(
                f"tool.rrt.artifact_protection.consumed[{index}].consumed_by must not be empty",
            )

        consumed.append(
            ConsumedArtifact(
                job=_required_job(item.get("job"), label=f"consumed[{index}].job"),
                ref=_required_string(item.get("ref"), label=f"consumed[{index}].ref"),
                artifacts=artifacts,
                consumed_by=consumed_by,
                reason=_optional_string(item.get("reason"), default="", label="reason"),
            ),
        )
    return tuple(consumed)


def _required_job(raw: object, *, label: str) -> str:
    """Return the job value exactly as declared.

    ``job`` is matched together with ``ref`` (never ``job`` alone) by exact
    string equality elsewhere, and may legitimately contain colons (e.g.
    ``build:report_html:bundle``), so this helper validates non-emptiness
    only — it must never split, strip, or otherwise transform the value. For
    a GitHub ``run-id:``-without-``name:`` fetch (download every artifact
    from the run), the scanner records the literal marker ``"*"`` as its
    ``job``; that value is not special-cased here — it is just a string.
    """
    if raw is None:
        raise ValueError(f"tool.rrt.artifact_protection.{label} is required")
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"tool.rrt.artifact_protection.{label} must be a non-empty string")
    return raw


def _required_string(raw: object, *, label: str) -> str:
    """Return a required non-empty string, stripped of surrounding whitespace."""
    if raw is None:
        raise ValueError(f"tool.rrt.artifact_protection.{label} is required")
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"tool.rrt.artifact_protection.{label} must be a non-empty string")
    return raw.strip()


def _optional_string(raw: object, *, default: str, label: str) -> str:
    """Return an optional string with a default."""
    if raw is None:
        return default
    if not isinstance(raw, str):
        raise ValueError(f"tool.rrt.artifact_protection.{label} must be a string")
    return raw.strip() or default


def _string_tuple(raw: object, *, label: str) -> tuple[str, ...]:
    """Parse a list of strings into a normalized tuple."""
    if raw is None:
        return ()
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise ValueError(f"tool.rrt.artifact_protection.{label} must be a list of strings")
    seen: set[str] = set()
    values: list[str] = []
    for item in cast("list[str]", raw):
        stripped = item.strip()
        if not stripped:
            raise ValueError(
                f"tool.rrt.artifact_protection.{label} must not contain empty strings",
            )
        if stripped not in seen:
            seen.add(stripped)
            values.append(stripped)
    return tuple(values)
