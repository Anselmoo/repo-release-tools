"""Architecture config parsing helpers for rrt (``[tool.rrt.architecture]``)."""

from __future__ import annotations

from typing import cast

from .model import ArchitectureConfig, ArchUnit

_PREFIX = "tool.rrt.architecture"
_UNIT_KEYS = frozenset({"name", "role", "package", "module", "prefix", "required_files"})
_TOP_KEYS = frozenset(
    {"root", "top_level_files", "layers", "layers_sync", "required_files", "units"},
)


def _load_architecture_config(raw: object) -> ArchitectureConfig | None:
    """Parse an optional ``[tool.rrt.architecture]`` table into an ArchitectureConfig."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(f"{_PREFIX} must be a table")

    d: dict[str, object] = cast("dict[str, object]", raw)
    unknown = sorted(set(d) - _TOP_KEYS)
    if unknown:
        raise ValueError(f"{_PREFIX} has unknown keys: {', '.join(unknown)}")

    root = d.get("root")
    if not isinstance(root, str) or not root.strip():
        raise ValueError(f"{_PREFIX}.root must be a non-empty string")

    layers_sync = d.get("layers_sync", "none")
    if not isinstance(layers_sync, str):
        raise ValueError(f"{_PREFIX}.layers_sync must be a string")

    cfg = ArchitectureConfig(
        root=root.strip().rstrip("/"),
        top_level_files=_string_tuple(d.get("top_level_files"), label="top_level_files"),
        layers=_string_tuple(d.get("layers"), label="layers"),
        layers_sync=layers_sync,
        required_files=_load_required_files(d.get("required_files")),
        units=_load_units(d.get("units")),
    )
    cfg.validate()
    return cfg


def _string_tuple(raw: object, *, label: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list) or not all(isinstance(x, str) for x in raw):
        raise ValueError(f"{_PREFIX}.{label} must be a list of strings")
    return tuple(cast("list[str]", raw))


def _load_required_files(raw: object) -> dict[str, tuple[str, ...]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"{_PREFIX}.required_files must be a table")
    return {
        str(role): _string_tuple(files, label=f"required_files.{role}")
        for role, files in cast("dict[str, object]", raw).items()
    }


def _load_units(raw: object) -> tuple[ArchUnit, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError(f"{_PREFIX}.units must be an array of tables")
    units: list[ArchUnit] = []
    for index, entry in enumerate(raw):
        label = f"{_PREFIX}.units[{index}]"
        if not isinstance(entry, dict):
            raise ValueError(f"{label} must be a table")
        item = cast("dict[str, object]", entry)
        unknown = sorted(set(item) - _UNIT_KEYS)
        if unknown:
            raise ValueError(f"{label} has unknown keys: {', '.join(unknown)}")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{label}.name must be a non-empty string")
        units.append(
            ArchUnit(
                name=name,
                role=_optional_string(item, "role", label=label) or "unit",
                package=_optional_string(item, "package", label=label),
                module=_optional_string(item, "module", label=label),
                prefix=_optional_string(item, "prefix", label=label),
                required_files=_string_tuple(
                    item.get("required_files"), label=f"units[{index}].required_files"
                ),
            ),
        )
    return tuple(units)


def _optional_string(item: dict[str, object], key: str, *, label: str) -> str | None:
    value = item.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}.{key} must be a non-empty string")
    return value
