"""Unit tests for `repo_release_tools.config.project_meta.load_project_metadata`."""

from __future__ import annotations

from pathlib import Path

from repo_release_tools.config.project_meta import (
    ProjectMetadata,
    load_project_metadata,
)


def test_load_project_metadata_returns_empty_when_no_manifest(tmp_path: Path) -> None:
    meta = load_project_metadata(tmp_path)
    assert meta == ProjectMetadata()
    assert meta.source is None


def test_load_pyproject_pep621_metadata(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """\
[project]
name = "sample"
version = "0.1.0"
description = "A demo project"
authors = [
    { name = "Anselm Hahn", email = "anselm.hahn@gmail.com" },
    "Lone Wolf",
]
license = { text = "MIT" }

[project.urls]
Homepage = "https://example.com"
Repository = "https://example.com/repo"
""",
        encoding="utf-8",
    )
    meta = load_project_metadata(tmp_path)
    assert meta.source == "pyproject.toml"
    assert meta.name == "sample"
    assert meta.version == "0.1.0"
    assert meta.description == "A demo project"
    assert "Anselm Hahn <anselm.hahn@gmail.com>" in meta.authors
    assert "Lone Wolf" in meta.authors
    assert meta.license == "MIT"
    assert meta.urls == {
        "Homepage": "https://example.com",
        "Repository": "https://example.com/repo",
    }


def test_load_pyproject_falls_back_to_poetry(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """\
[tool.poetry]
name = "legacy"
version = "1.0.0"
description = "older-style metadata"
authors = ["Alice <alice@example.com>"]
license = "Apache-2.0"
homepage = "https://example.com"
repository = "https://example.com/repo"
""",
        encoding="utf-8",
    )
    meta = load_project_metadata(tmp_path)
    assert meta.name == "legacy"
    assert meta.version == "1.0.0"
    assert meta.description == "older-style metadata"
    assert meta.authors == ["Alice <alice@example.com>"]
    assert meta.license == "Apache-2.0"
    assert meta.urls == {
        "Homepage": "https://example.com",
        "Repository": "https://example.com/repo",
    }


def test_load_cargo_metadata(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text(
        """\
[package]
name = "rusty"
version = "0.2.3"
description = "Crates demo"
authors = ["Bob <bob@example.com>"]
license = "MIT"
homepage = "https://crates.io/sample"
""",
        encoding="utf-8",
    )
    meta = load_project_metadata(tmp_path)
    assert meta.source == "Cargo.toml"
    assert meta.name == "rusty"
    assert meta.version == "0.2.3"
    assert meta.description == "Crates demo"
    assert meta.authors == ["Bob <bob@example.com>"]
    assert meta.license == "MIT"
    assert meta.urls == {"Homepage": "https://crates.io/sample"}


def test_load_node_metadata(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        """{
            "name": "@scope/node-pkg",
            "version": "3.4.5",
            "description": "Node demo",
            "author": { "name": "Carol", "email": "carol@example.com" },
            "contributors": ["Dave"],
            "license": "ISC",
            "homepage": "https://node.example",
            "repository": { "url": "git+https://github.com/x/y.git" },
            "bugs": "https://issues.example"
        }""",
        encoding="utf-8",
    )
    meta = load_project_metadata(tmp_path)
    assert meta.source == "package.json"
    assert meta.name == "@scope/node-pkg"
    assert meta.version == "3.4.5"
    assert meta.description == "Node demo"
    assert meta.authors == ["Carol <carol@example.com>", "Dave"]
    assert meta.license == "ISC"
    assert meta.urls == {
        "Homepage": "https://node.example",
        "Repository": "git+https://github.com/x/y.git",
        "Bugs": "https://issues.example",
    }


def test_load_node_metadata_handles_malformed_json(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("not json at all", encoding="utf-8")
    meta = load_project_metadata(tmp_path)
    assert meta.source == "package.json"
    assert meta.name is None


def test_pyproject_precedes_cargo_when_both_present(tmp_path: Path) -> None:
    """Search order is pyproject → Cargo → package.json."""
    (tmp_path / "pyproject.toml").write_text('[project]\nname="py"\n', encoding="utf-8")
    (tmp_path / "Cargo.toml").write_text('[package]\nname="rs"\n', encoding="utf-8")
    meta = load_project_metadata(tmp_path)
    assert meta.source == "pyproject.toml"
    assert meta.name == "py"


def test_pyproject_with_no_known_block(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[build-system]\nrequires=[]\n", encoding="utf-8")
    meta = load_project_metadata(tmp_path)
    assert meta.source == "pyproject.toml"
    assert meta.name is None
    assert meta.authors == []
    assert meta.urls == {}


def test_pep621_license_file_form(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """\
[project]
name = "x"
license = { file = "LICENSE" }
""",
        encoding="utf-8",
    )
    meta = load_project_metadata(tmp_path)
    assert meta.license == "file: LICENSE"


# ---------------------------------------------------------------------------
# Coercion / fallback coverage
# ---------------------------------------------------------------------------


def test_node_metadata_with_non_dict_root_is_empty(tmp_path: Path) -> None:
    """A package.json that is a JSON list (not an object) yields empty metadata."""
    (tmp_path / "package.json").write_text("[1, 2, 3]", encoding="utf-8")
    meta = load_project_metadata(tmp_path)
    assert meta.source == "package.json"
    assert meta.name is None


def test_node_author_string_and_repository_string(tmp_path: Path) -> None:
    """package.json with string `author` / `repository` / `bugs` flattens correctly."""
    (tmp_path / "package.json").write_text(
        """{
            "name": "scalar-forms",
            "author": "Solo Dev",
            "contributors": [
                {"name": "Helper", "email": "help@example.com"},
                {"name": "NoEmail"},
                "Plain String"
            ],
            "repository": "git+https://example/repo",
            "bugs": "https://example/bugs"
        }""",
        encoding="utf-8",
    )
    meta = load_project_metadata(tmp_path)
    assert meta.authors == [
        "Solo Dev",
        "Helper <help@example.com>",
        "NoEmail",
        "Plain String",
    ]
    assert meta.urls["Repository"] == "git+https://example/repo"
    assert meta.urls["Bugs"] == "https://example/bugs"


def test_node_repository_and_bugs_objects(tmp_path: Path) -> None:
    """package.json with object `repository` / `bugs` reads the nested `url`."""
    (tmp_path / "package.json").write_text(
        """{
            "name": "x",
            "repository": {"url": "https://nested/repo"},
            "bugs": {"url": "https://nested/bugs"}
        }""",
        encoding="utf-8",
    )
    meta = load_project_metadata(tmp_path)
    assert meta.urls == {
        "Repository": "https://nested/repo",
        "Bugs": "https://nested/bugs",
    }


def test_pep621_author_email_only(tmp_path: Path) -> None:
    """A PEP 621 author with only an email still produces a string."""
    (tmp_path / "pyproject.toml").write_text(
        """\
[project]
name = "x"
authors = [
    { email = "anon@example.com" },
    { name = "" },
    { name = "Jane", email = "jane@example.com" }
]
""",
        encoding="utf-8",
    )
    meta = load_project_metadata(tmp_path)
    assert "anon@example.com" in meta.authors
    assert "Jane <jane@example.com>" in meta.authors


def test_pep621_authors_skips_non_dict_entries(tmp_path: Path) -> None:
    """Non-mapping entries in authors are dropped silently."""
    (tmp_path / "pyproject.toml").write_text(
        """\
[project]
name = "x"
authors = [12345, "Real Person"]
""",
        encoding="utf-8",
    )
    meta = load_project_metadata(tmp_path)
    assert meta.authors == ["Real Person"]


def test_pep621_license_dict_without_text_or_file_is_none(tmp_path: Path) -> None:
    """A `license` table without `text` or `file` yields None."""
    (tmp_path / "pyproject.toml").write_text(
        """\
[project]
name = "x"
[project.license]
spdx = "MIT"
""",
        encoding="utf-8",
    )
    meta = load_project_metadata(tmp_path)
    assert meta.license is None


def test_pep621_license_string_value(tmp_path: Path) -> None:
    """A PEP 621 `license = "MIT"` string value is read verbatim."""
    (tmp_path / "pyproject.toml").write_text(
        """\
[project]
name = "x"
license = "MIT"
""",
        encoding="utf-8",
    )
    meta = load_project_metadata(tmp_path)
    assert meta.license == "MIT"


def test_pep621_author_name_only(tmp_path: Path) -> None:
    """A PEP 621 author with only a name (no email) renders as the name."""
    (tmp_path / "pyproject.toml").write_text(
        """\
[project]
name = "x"
authors = [{ name = "OnlyName" }]
""",
        encoding="utf-8",
    )
    meta = load_project_metadata(tmp_path)
    assert meta.authors == ["OnlyName"]


def test_poetry_authors_non_list_yields_empty(tmp_path: Path) -> None:
    """Poetry `authors = "not a list"` collapses to []."""
    (tmp_path / "pyproject.toml").write_text(
        """\
[tool.poetry]
name = "legacy"
authors = "not a list"
""",
        encoding="utf-8",
    )
    meta = load_project_metadata(tmp_path)
    assert meta.authors == []


def test_node_contributor_dict_without_usable_fields_is_dropped(tmp_path: Path) -> None:
    """A contributor with neither a usable name nor email is silently dropped."""
    (tmp_path / "package.json").write_text(
        """{
            "name": "x",
            "contributors": [{"role": "qa"}]
        }""",
        encoding="utf-8",
    )
    meta = load_project_metadata(tmp_path)
    assert meta.authors == []
