"""Tests for ``[tool.rrt.architecture]`` loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from repo_release_tools.config import (
    ArchitectureConfig,
    ArchLayer,
    ArchLayerEntry,
    ArchUnit,
    load_config,
)
from repo_release_tools.config.arch_config import _load_architecture_config
from repo_release_tools.config.model import parse_arch_layer

DESIGN_EXAMPLE = {
    "root": "src/acme",
    "top_level_files": ["__init__.py", "errors.py", "py.typed", "README.md"],
    "layers": ["api", "domain | storage", "core | models", "errors"],
    "layers_sync": "importlinter",
    "required_files": {
        "door": ["__init__.py", "README.md"],
        "unit": ["__init__.py", "README.md"],
        "foundation": ["__init__.py", "README.md"],
    },
    "units": [
        {"name": "api", "role": "door"},
        {"name": "domain"},
        {"name": "storage"},
        {"name": "transform", "package": "xform", "role": "unit", "prefix": "xform"},
        {"name": "core", "role": "foundation"},
        {"name": "models", "role": "foundation", "required_files": ["py.typed"]},
        {"name": "errors", "module": "errors", "role": "foundation"},
    ],
}


def test_none_means_not_configured() -> None:
    """A missing table loads as ``None``."""
    assert _load_architecture_config(None) is None


def test_design_example_loads() -> None:
    """The sample configuration loads with every default applied."""
    cfg = _load_architecture_config(DESIGN_EXAMPLE)
    assert cfg is not None
    assert cfg.root == "src/acme"
    assert cfg.layers_sync == "importlinter"
    transform = cfg.unit_named("transform")
    assert transform is not None
    assert transform.import_name == "xform"
    assert transform.entry_name == "xform"
    assert transform.template_prefix == "xform"
    assert not transform.is_module
    errors = cfg.unit_named("errors")
    assert errors is not None
    assert errors.is_module
    assert errors.entry_name == "errors.py"
    assert errors.template_prefix == "errors"
    assert cfg.required_files_for(errors) == ()
    models = cfg.unit_named("models")
    assert models is not None
    assert cfg.required_files_for(models) == ("__init__.py", "README.md", "py.typed")
    domain = cfg.unit_named("domain")
    assert domain is not None
    assert domain.role == "unit"
    assert domain.import_name == "domain"
    assert cfg.unit_named("nope") is None


def test_required_files_dedupe_role_and_unit() -> None:
    """A unit file already required by its role is listed once."""
    cfg = ArchitectureConfig(
        root="src/p",
        required_files={"unit": ("README.md",)},
        units=(ArchUnit("a", required_files=("README.md", "x.py")),),
    )
    assert cfg.required_files_for(cfg.units[0]) == ("README.md", "x.py")


def test_minimal_defaults() -> None:
    """Only ``root`` is required."""
    cfg = _load_architecture_config({"root": "src/p/"})
    assert cfg == ArchitectureConfig(root="src/p")


def test_loaded_through_load_config(tmp_path: Path) -> None:
    """``load_config`` attaches the table to ``RrtConfig.architecture``."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "t"\nversion = "0.1.0"\n\n'
        '[tool.rrt]\n\n[[tool.rrt.version_targets]]\npath = "pyproject.toml"\nkind = "pep621"\n\n'
        '[tool.rrt.architecture]\nroot = "src/t"\n\n'
        '[[tool.rrt.architecture.units]]\nname = "core"\n',
        encoding="utf-8",
    )
    conf = load_config(tmp_path)
    assert conf.architecture == ArchitectureConfig(root="src/t", units=(ArchUnit("core"),))


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("a", ArchLayer((ArchLayerEntry("a"),), "")),
        (" a | b ", ArchLayer((ArchLayerEntry("a"), ArchLayerEntry("b")), "|")),
        ("a : (b)", ArchLayer((ArchLayerEntry("a"), ArchLayerEntry("b", optional=True)), ":")),
        ("(a)", ArchLayer((ArchLayerEntry("a", optional=True),), "")),
    ],
)
def test_parse_arch_layer(spec: str, expected: ArchLayer) -> None:
    """Layer strings follow import-linter's grammar."""
    layer = parse_arch_layer(spec)
    assert layer == expected
    assert layer.names == tuple(e.name for e in expected.entries)
    assert layer.independent is (expected.separator == "|")


@pytest.mark.parametrize(
    ("spec", "match"),
    [("", "non-empty"), ("a | b : c", "mixes"), ("a | ", "invalid name"), ("a-b", "invalid")],
)
def test_parse_arch_layer_rejects(spec: str, match: str) -> None:
    """Malformed layer strings raise ``ValueError``."""
    with pytest.raises(ValueError, match=match):
        parse_arch_layer(spec)


def _with(**changes: object) -> dict[str, object]:
    raw: dict[str, object] = {
        "root": "src/p",
        "units": [{"name": "api", "role": "door"}, {"name": "core"}, {"name": "base"}],
    }
    raw.update(changes)
    return raw


@pytest.mark.parametrize(
    ("raw", "match"),
    [
        ("x", "must be a table"),
        (_with(bogus=1), "unknown keys: bogus"),
        ({"units": []}, "root must be a non-empty string"),
        (_with(root="  "), "root must be a non-empty string"),
        (_with(root="/abs"), "relative path inside"),
        (_with(root="src/../x"), "relative path inside"),
        (_with(layers_sync=3), "layers_sync must be a string"),
        (_with(layers_sync="maybe"), "layers_sync must be one of"),
        (_with(top_level_files="x"), "top_level_files must be a list of strings"),
        (_with(layers=[1]), "layers must be a list of strings"),
        (_with(required_files=[]), "required_files must be a table"),
        (_with(required_files={"door": [1]}), "required_files.door must be a list"),
        (_with(required_files={"boss": []}), "unknown role 'boss'"),
        (_with(units={}), "units must be an array of tables"),
        (_with(units=["x"]), r"units\[0\] must be a table"),
        (_with(units=[{"name": "a", "bad": 1}]), r"units\[0\] has unknown keys: bad"),
        (_with(units=[{"role": "unit"}]), r"units\[0\].name must be a non-empty string"),
        (_with(units=[{"name": "a", "role": ""}]), r"units\[0\].role must be a non-empty"),
        (_with(units=[{"name": "a b"}]), "name must be an identifier"),
        (_with(units=[{"name": "a\n"}]), "name must be an identifier"),
        (_with(units=[{"name": "a", "package": "p\n"}]), "package/module must be an identifier"),
        (_with(units=[{"name": "a"}, {"name": "a"}]), "duplicate name 'a'"),
        (_with(units=[{"name": "a", "package": "p", "module": "m"}]), "both package and module"),
        (_with(units=[{"name": "a", "package": "p-q"}]), "package/module must be an identifier"),
        (_with(units=[{"name": "a", "role": "boss"}]), "role must be one of"),
        (
            _with(units=[{"name": "a", "module": "m", "required_files": ["x"]}]),
            "package units only",
        ),
        (_with(units=[{"name": "a"}, {"name": "b", "package": "a"}]), "duplicate package 'a'"),
        (
            _with(units=[{"name": "a", "module": "m"}, {"name": "b", "module": "m"}]),
            "duplicate module 'm'",
        ),
        (_with(layers=["a | b : c"]), "layers: layer"),
        (_with(layers=["ghost"]), "no declared unit"),
        (_with(layers=["core", "core"]), "more than once"),
        (_with(layers=["core", "api"]), "places unit 'core' above door 'api'"),
        (
            _with(
                layers=["api", "base", "core"],
                units=[
                    {"name": "api", "role": "door"},
                    {"name": "core"},
                    {"name": "base", "role": "foundation"},
                ],
            ),
            "places foundation 'base' above unit 'core'",
        ),
    ],
)
def test_invalid_configs(raw: object, match: str) -> None:
    """Every rejected shape names the offending key."""
    with pytest.raises(ValueError, match=match):
        _load_architecture_config(raw)


def test_door_and_foundation_may_share_layers_with_units_in_order() -> None:
    """Correct role order validates; siblings of different roles in one layer are allowed."""
    cfg = _load_architecture_config(_with(layers=["api", "core | base"]))
    assert cfg is not None
    assert [layer.names for layer in cfg.parsed_layers()] == [("api",), ("core", "base")]
