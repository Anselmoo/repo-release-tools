"""Runtime and project-version detection helpers for EOL checks."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from .data import _EOL_API_SLUG


def _canonical_slug(language: str) -> str:
    """Normalise a user-supplied language name to the endoflife.date slug."""
    key = language.lower().strip()
    return _EOL_API_SLUG.get(key, key)


def detect_host_version(language: str) -> str | None:
    """Return the installed version string for *language* on the host."""
    slug = _canonical_slug(language)

    if slug == "python":
        v = sys.version_info
        return f"{v.major}.{v.minor}.{v.micro}"

    commands: dict[str, list[str]] = {
        "nodejs": ["node", "--version"],
        "go": ["go", "version"],
        "rust": ["rustc", "--version"],
    }
    cmd = commands.get(slug)
    if cmd is None:
        return None

    try:
        result = subprocess.run(  # noqa: S603
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        return _extract_version(result.stdout.strip(), slug)
    except (subprocess.TimeoutExpired, OSError):
        return None


def _extract_version(output: str, slug: str) -> str | None:
    """Extract the version string from command output for the given slug."""
    if slug == "nodejs":
        return m[1] if (m := re.match(r"v?(\d+\.\d+\.\d+)", output)) else None

    if slug == "go":
        return m[1] if (m := re.search(r"go(\d+\.\d+(?:\.\d+)?)", output)) else None

    if slug == "rust":
        return m[1] if (m := re.search(r"rustc (\d+\.\d+\.\d+)", output)) else None

    return None


def detect_project_minimum(language: str, root: Path) -> str | None:
    """Return the project's declared minimum version for *language*."""
    slug = _canonical_slug(language)

    if slug == "python":
        return _detect_python_minimum(root)
    if slug == "go":
        return _detect_go_minimum(root)
    if slug == "nodejs":
        return _detect_node_minimum(root)
    if slug == "rust":
        return _detect_rust_minimum(root)
    return None


def _detect_python_minimum(root: Path) -> str | None:
    """Read ``requires-python`` from ``pyproject.toml``."""
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return None
    try:
        import tomllib as _tomllib

        with pyproject.open("rb") as handle:
            data = _tomllib.load(handle)
        raw: object = data.get("project", {}).get("requires-python")
        if not isinstance(raw, str):
            return None
        return m[1] if (m := re.search(r"(\d+\.\d+(?:\.\d+)?)", raw)) else None
    except Exception:  # noqa: BLE001
        return None


def _detect_go_minimum(root: Path) -> str | None:
    """Read the ``go`` directive from ``go.mod``."""
    gomod = root / "go.mod"
    if not gomod.exists():
        return None
    try:
        text = gomod.read_text(encoding="utf-8")
        return (
            m[1]
            if (m := re.search(r"^\s*go\s+(\d+\.\d+(?:\.\d+)?)\s*$", text, re.MULTILINE))
            else None
        )
    except OSError:
        return None


def _detect_node_minimum(root: Path) -> str | None:
    """Read ``engines.node`` from ``package.json``."""
    package_json = root / "package.json"
    if not package_json.exists():
        return None
    try:
        data = json.loads(package_json.read_text(encoding="utf-8"))
        raw: object = data.get("engines", {}).get("node")
        if not isinstance(raw, str):
            return None
        return m[1] if (m := re.search(r"(\d+\.\d+(?:\.\d+)?)", raw)) else None
    except (json.JSONDecodeError, OSError):
        return None


def _detect_rust_minimum(root: Path) -> str | None:
    """Read ``rust-version`` from ``Cargo.toml``."""
    cargo = root / "Cargo.toml"
    if not cargo.exists():
        return None
    try:
        import tomllib as _tomllib

        with cargo.open("rb") as handle:
            data = _tomllib.load(handle)
        raw: object = data.get("package", {}).get("rust-version")
        if not isinstance(raw, str):
            return None
        return m[1] if (m := re.search(r"(\d+\.\d+(?:\.\d+)?)", raw)) else None
    except Exception:  # noqa: BLE001
        return None
