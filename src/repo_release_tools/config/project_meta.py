"""Project metadata loader for `rrt project info`.

Reads ``name``, ``description``, ``version``, ``authors``, ``license``, and
``urls`` from the manifest that ships with the project. Supports
``pyproject.toml`` (PEP 621 ``[project]`` and legacy ``[tool.poetry]``),
``Cargo.toml`` (``[package]``), and ``package.json``.

This is a read-only helper. It never raises for malformed manifests beyond
``OSError`` or ``ValueError`` from the parser itself — missing fields land
as ``None``/empty so callers can decide how to render.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast


@dataclass(frozen=True)
class ProjectMetadata:
    """Project metadata extracted from a project manifest.

    ``source`` is the filename the metadata came from (e.g. ``"pyproject.toml"``).
    ``urls`` is a dict of label → url pairs (PEP 621 ``[project.urls]`` /
    Cargo ``[package].homepage`` etc.).
    """

    name: str | None = None
    version: str | None = None
    description: str | None = None
    authors: list[str] = field(default_factory=list)
    license: str | None = None
    urls: dict[str, str] = field(default_factory=dict)
    source: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable dict."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "authors": list(self.authors),
            "license": self.license,
            "urls": dict(self.urls),
            "source": self.source,
        }


_MANIFEST_FILES: tuple[str, ...] = ("pyproject.toml", "Cargo.toml", "package.json")


def load_project_metadata(root: Path) -> ProjectMetadata:
    """Return the first manifest's metadata found under *root*.

    Search order: ``pyproject.toml`` (PEP 621, then poetry fallback),
    ``Cargo.toml``, ``package.json``. Returns an empty :class:`ProjectMetadata`
    when no manifest exists.
    """
    for filename in _MANIFEST_FILES:
        path = root / filename
        if not path.exists():
            continue
        if filename == "pyproject.toml":
            return _read_pyproject_metadata(path)
        if filename == "Cargo.toml":
            return _read_cargo_metadata(path)
        if filename == "package.json":
            return _read_node_metadata(path)
    return ProjectMetadata()


def _read_pyproject_metadata(path: Path) -> ProjectMetadata:
    """Parse ``pyproject.toml`` honoring PEP 621 first, poetry as fallback."""
    raw = tomllib.loads(path.read_text(encoding="utf-8"))

    project = raw.get("project") if isinstance(raw.get("project"), dict) else None
    poetry: dict[str, object] | None = None
    tool = raw.get("tool")
    if isinstance(tool, dict):
        poetry_block = tool.get("poetry")
        if isinstance(poetry_block, dict):
            poetry = poetry_block

    if project:
        return ProjectMetadata(
            name=_as_str(project.get("name")),
            version=_as_str(project.get("version")),
            description=_as_str(project.get("description")),
            authors=_pep621_authors(project.get("authors")),
            license=_pep621_license(project.get("license")),
            urls=_dict_of_strings(project.get("urls")),
            source=path.name,
        )

    if poetry:
        return ProjectMetadata(
            name=_as_str(poetry.get("name")),
            version=_as_str(poetry.get("version")),
            description=_as_str(poetry.get("description")),
            authors=_string_list(poetry.get("authors")),
            license=_as_str(poetry.get("license")),
            urls={
                **_dict_of_strings(poetry.get("urls")),
                **_optional_url("Homepage", _as_str(poetry.get("homepage"))),
                **_optional_url("Repository", _as_str(poetry.get("repository"))),
                **_optional_url("Documentation", _as_str(poetry.get("documentation"))),
            },
            source=path.name,
        )

    return ProjectMetadata(source=path.name)


def _read_cargo_metadata(path: Path) -> ProjectMetadata:
    """Parse a Cargo ``[package]`` block."""
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    package_raw = raw.get("package")
    package: dict[str, object] = package_raw if isinstance(package_raw, dict) else {}

    return ProjectMetadata(
        name=_as_str(package.get("name")),
        version=_as_str(package.get("version")),
        description=_as_str(package.get("description")),
        authors=_string_list(package.get("authors")),
        license=_as_str(package.get("license")),
        urls={
            **_optional_url("Homepage", _as_str(package.get("homepage"))),
            **_optional_url("Repository", _as_str(package.get("repository"))),
            **_optional_url("Documentation", _as_str(package.get("documentation"))),
        },
        source=path.name,
    )


def _read_node_metadata(path: Path) -> ProjectMetadata:
    """Parse a ``package.json`` top-level block."""
    raw_text = path.read_text(encoding="utf-8")
    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError:
        return ProjectMetadata(source=path.name)
    if not isinstance(raw, dict):
        return ProjectMetadata(source=path.name)

    return ProjectMetadata(
        name=_as_str(raw.get("name")),
        version=_as_str(raw.get("version")),
        description=_as_str(raw.get("description")),
        authors=_node_authors(raw.get("author"), raw.get("contributors")),
        license=_as_str(raw.get("license")),
        urls=_node_urls(raw),
        source=path.name,
    )


# ---------------------------------------------------------------------------
# value coercion helpers
# ---------------------------------------------------------------------------


def _as_str(value: object) -> str | None:
    """Return *value* coerced to a stripped string or None."""
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _string_list(value: object) -> list[str]:
    """Coerce a sequence-of-strings to a list, dropping non-strings."""
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _dict_of_strings(value: object) -> dict[str, str]:
    """Coerce a TOML table to a string→string dict, dropping non-strings."""
    if not isinstance(value, dict):
        return {}
    return {k: v.strip() for k, v in value.items() if isinstance(k, str) and isinstance(v, str)}


def _optional_url(label: str, value: str | None) -> dict[str, str]:
    """Return ``{label: value}`` when value is set, else an empty dict."""
    return {label: value} if value else {}


def _pep621_authors(value: object) -> list[str]:
    """Render the PEP 621 ``authors`` list as ``"Name <email>"`` strings."""
    if not isinstance(value, list):
        return []
    rendered: list[str] = []
    for item in value:
        if isinstance(item, str):
            stripped = item.strip()
            if stripped:
                rendered.append(stripped)
            continue
        if not isinstance(item, dict):
            continue
        item_dict = cast("dict[str, object]", item)
        name = item_dict.get("name")
        email = item_dict.get("email")
        if isinstance(name, str) and isinstance(email, str) and email.strip():
            rendered.append(f"{name.strip()} <{email.strip()}>")
        elif isinstance(name, str) and name.strip():
            rendered.append(name.strip())
        elif isinstance(email, str) and email.strip():
            rendered.append(email.strip())
    return rendered


def _pep621_license(value: object) -> str | None:
    """Resolve the PEP 621 ``license`` field (string or ``{text|file}``)."""
    if isinstance(value, str):
        return _as_str(value)
    if isinstance(value, dict):
        value_dict = cast("dict[str, object]", value)
        text = value_dict.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
        file = value_dict.get("file")
        if isinstance(file, str) and file.strip():
            return f"file: {file.strip()}"
    return None


def _node_authors(author: object, contributors: object) -> list[str]:
    """Combine package.json ``author`` and ``contributors`` into one list."""
    out: list[str] = []
    rendered = _node_person(author)
    if rendered:
        out.append(rendered)
    if isinstance(contributors, list):
        for entry in contributors:
            rendered = _node_person(entry)
            if rendered:
                out.append(rendered)
    return out


def _node_person(value: object) -> str | None:
    """Render a package.json person entry as ``"Name <email>"``."""
    if isinstance(value, str):
        return _as_str(value)
    if not isinstance(value, dict):
        return None
    value_dict = cast("dict[str, object]", value)
    name = value_dict.get("name")
    email = value_dict.get("email")
    if isinstance(name, str) and isinstance(email, str) and email.strip():
        return f"{name.strip()} <{email.strip()}>"
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


def _node_urls(raw: dict[str, object]) -> dict[str, str]:
    """Collect ``homepage``, ``repository``, ``bugs`` URLs from package.json."""
    urls: dict[str, str] = {}
    homepage = _as_str(raw.get("homepage"))
    if homepage:
        urls["Homepage"] = homepage
    repository = raw.get("repository")
    if isinstance(repository, str) and repository.strip():
        urls["Repository"] = repository.strip()
    elif isinstance(repository, dict):
        repository_dict = cast("dict[str, object]", repository)
        url = repository_dict.get("url")
        if isinstance(url, str) and url.strip():
            urls["Repository"] = url.strip()
    bugs = raw.get("bugs")
    if isinstance(bugs, str) and bugs.strip():
        urls["Bugs"] = bugs.strip()
    elif isinstance(bugs, dict):
        bugs_dict = cast("dict[str, object]", bugs)
        url = bugs_dict.get("url")
        if isinstance(url, str) and url.strip():
            urls["Bugs"] = url.strip()
    return urls
