"""Tests for the schema-to-TOML config reference generator."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

from repo_release_tools.config.reference import render_reference_toml

_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "src"
    / "repo_release_tools"
    / "_data"
    / "rrt-config.schema.json"
)

# ---------------------------------------------------------------------------
# Minimal schemas for focused unit tests
# ---------------------------------------------------------------------------

_ENUM_SCHEMA: dict = {
    "properties": {
        "workflow": {
            "type": "string",
            "enum": ["incremental", "squash"],
            "description": "How entries are written.",
        }
    }
}

_SCALAR_SCHEMA: dict = {
    "properties": {
        "name": {"type": "string", "description": "A string field."},
        "count": {"type": "integer", "description": "An integer field."},
        "flag": {"type": "boolean", "description": "A boolean field."},
    }
}

_ARRAY_OF_OBJECTS_SCHEMA: dict = {
    "properties": {
        "targets": {
            "type": "array",
            "description": "A list of targets.",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file."},
                    "kind": {"type": "string", "description": "Target kind."},
                },
            },
        }
    }
}

_NESTED_OBJECT_SCHEMA: dict = {
    "properties": {
        "eol": {
            "type": "object",
            "description": "EOL tracking config.",
            "properties": {
                "warn_days": {"type": "integer", "description": "Days before warning."},
                "fetch_live": {"type": "boolean", "description": "Fetch live data."},
            },
        }
    }
}

_ARRAY_OF_SCALARS_SCHEMA: dict = {
    "properties": {
        "tags": {
            "type": "array",
            "description": "List of tag strings.",
            "items": {"type": "string"},
        }
    }
}


# ---------------------------------------------------------------------------
# Test 1: descriptions and enum comments
# ---------------------------------------------------------------------------


def test_description_emitted_as_comment() -> None:
    """Description is emitted as '# ...' line before the key."""
    result = render_reference_toml(_ENUM_SCHEMA)
    assert "# How entries are written." in result


def test_enum_comment_sorted() -> None:
    """Enum values are listed as '# one of: ...' in sorted order."""
    result = render_reference_toml(_ENUM_SCHEMA)
    assert "# one of: incremental, squash" in result


def test_enum_first_value_as_placeholder() -> None:
    """First sorted enum value is used as the placeholder for the key."""
    result = render_reference_toml(_ENUM_SCHEMA)
    # 'incremental' < 'squash' alphabetically — must appear as value
    assert 'workflow = "incremental"' in result


# ---------------------------------------------------------------------------
# Test 2: scalar placeholders by type
# ---------------------------------------------------------------------------


def test_string_placeholder() -> None:
    """String type emits '...' as placeholder."""
    result = render_reference_toml(_SCALAR_SCHEMA)
    assert 'name = "..."' in result


def test_integer_placeholder() -> None:
    """Integer type emits 0 as placeholder."""
    result = render_reference_toml(_SCALAR_SCHEMA)
    assert "count = 0" in result


def test_boolean_placeholder() -> None:
    """Boolean type emits false as placeholder."""
    result = render_reference_toml(_SCALAR_SCHEMA)
    assert "flag = false" in result


# ---------------------------------------------------------------------------
# Test 3: array-of-objects emits [[tool.rrt.<name>]] block
# ---------------------------------------------------------------------------


def test_array_of_objects_block_header() -> None:
    """Array of objects emits [[tool.rrt.<name>]] header."""
    result = render_reference_toml(_ARRAY_OF_OBJECTS_SCHEMA)
    assert "[[tool.rrt.targets]]" in result


def test_array_of_objects_item_fields() -> None:
    """Array-of-object block includes item fields with placeholders."""
    result = render_reference_toml(_ARRAY_OF_OBJECTS_SCHEMA)
    assert 'path = "..."' in result
    assert 'kind = "..."' in result


# ---------------------------------------------------------------------------
# Test 4: nested object emits [tool.rrt.<name>] sub-table
# ---------------------------------------------------------------------------


def test_nested_object_sub_table_header() -> None:
    """Nested object emits [tool.rrt.<name>] sub-table header."""
    result = render_reference_toml(_NESTED_OBJECT_SCHEMA)
    assert "[tool.rrt.eol]" in result


def test_nested_object_fields() -> None:
    """Nested object sub-table includes its own fields."""
    result = render_reference_toml(_NESTED_OBJECT_SCHEMA)
    assert "warn_days = 0" in result
    assert "fetch_live = false" in result


# ---------------------------------------------------------------------------
# Test 5: round-trip invariant
# ---------------------------------------------------------------------------


def test_round_trip_minimal_schema() -> None:
    """render_reference_toml output parses cleanly with tomllib for a minimal schema."""
    schema: dict = {
        "properties": {
            "changelog_file": {"type": "string", "description": "Path to changelog."},
            "dry_run": {"type": "boolean", "description": "Enable dry-run."},
            "max_depth": {"type": "integer", "description": "Max recursion depth."},
        }
    }
    rendered = render_reference_toml(schema)
    parsed = tomllib.loads(rendered)
    assert "tool" in parsed


def test_round_trip_array_of_scalars() -> None:
    """Array-of-scalars renders as empty list and parses cleanly."""
    rendered = render_reference_toml(_ARRAY_OF_SCALARS_SCHEMA)
    parsed = tomllib.loads(rendered)
    assert parsed["tool"]["rrt"]["tags"] == []


def test_round_trip_enum_schema() -> None:
    """Enum schema renders and parses cleanly."""
    rendered = render_reference_toml(_ENUM_SCHEMA)
    tomllib.loads(rendered)  # must not raise


def test_round_trip_array_of_objects_schema() -> None:
    """Array-of-objects schema renders and parses cleanly."""
    rendered = render_reference_toml(_ARRAY_OF_OBJECTS_SCHEMA)
    tomllib.loads(rendered)  # must not raise


def test_round_trip_nested_object_schema() -> None:
    """Nested-object schema renders and parses cleanly."""
    rendered = render_reference_toml(_NESTED_OBJECT_SCHEMA)
    tomllib.loads(rendered)  # must not raise


def test_round_trip_real_bundled_schema() -> None:
    """Rendered output of the real bundled JSON schema parses cleanly with tomllib."""
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    rendered = render_reference_toml(schema)
    parsed = tomllib.loads(rendered)
    assert "tool" in parsed
    assert "rrt" in parsed["tool"]


# ---------------------------------------------------------------------------
# Test 6: determinism
# ---------------------------------------------------------------------------


def test_determinism_minimal() -> None:
    """Calling render_reference_toml twice returns identical output."""
    first = render_reference_toml(_SCALAR_SCHEMA)
    second = render_reference_toml(_SCALAR_SCHEMA)
    assert first == second


def test_determinism_real_schema() -> None:
    """render_reference_toml is deterministic on the real bundled schema."""
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert render_reference_toml(schema) == render_reference_toml(schema)


# ---------------------------------------------------------------------------
# Test 7: header format
# ---------------------------------------------------------------------------


def test_header_line_present() -> None:
    """Output starts with the canonical 'Generated by' comment header."""
    result = render_reference_toml(_SCALAR_SCHEMA)
    first_line = result.splitlines()[0]
    assert first_line == "# Generated by 'rrt config reference' — do not edit by hand."


def test_tool_rrt_table_header_present() -> None:
    """Output contains [tool.rrt] as the top-level table header."""
    result = render_reference_toml(_SCALAR_SCHEMA)
    assert "[tool.rrt]" in result


def test_sorted_key_order() -> None:
    """Properties are emitted in sorted key order."""
    schema: dict = {
        "properties": {
            "zebra": {"type": "string", "description": "Z field."},
            "alpha": {"type": "string", "description": "A field."},
            "mango": {"type": "string", "description": "M field."},
        }
    }
    result = render_reference_toml(schema)
    pos_alpha = result.index("alpha")
    pos_mango = result.index("mango")
    pos_zebra = result.index("zebra")
    assert pos_alpha < pos_mango < pos_zebra


# ---------------------------------------------------------------------------
# Test 8: edge cases
# ---------------------------------------------------------------------------


def test_unknown_type_fallback_to_string_placeholder() -> None:
    """A property with an unknown type falls back to string placeholder '\"...\"'."""
    schema: dict = {
        "properties": {
            "mystery": {"type": "null", "description": "Unknown type field."},
        }
    }
    result = render_reference_toml(schema)
    assert 'mystery = "..."' in result


def test_ref_only_property_skipped() -> None:
    """A property that is only a $ref emits a skip comment, not a value."""
    schema: dict = {
        "properties": {
            "targets": {"$ref": "#/properties/version_targets"},
        }
    }
    result = render_reference_toml(schema)
    assert "targets:" in result
    assert "$ref" in result
    # Must not emit a bare 'targets = ...' value line
    assert "targets =" not in result


def test_empty_properties_produces_valid_toml() -> None:
    """Schema with no properties emits only the header + [tool.rrt]."""
    result = render_reference_toml({})
    parsed = tomllib.loads(result)
    assert parsed["tool"]["rrt"] == {}
