"""Ensure command modules provide rich, multi-line module docstrings.

Rules enforced by this test:
- Module-level docstring must exist.
- Docstring must be multi-line (contain a newline).
- Docstring must be at least MIN_CHARS characters long (default 150).
- Files may opt out by including the marker "rrt:docs-exempt" anywhere in the file.
- `__init__.py` and `__main__.py` are automatically exempt.

The minimum length may be adjusted by setting the environment variable
`RRT_DOCSTRING_MIN_CHARS`.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

MIN_DEFAULT = 150

ROOT = Path(__file__).resolve().parents[2]
COMMANDS_DIR = ROOT / "src" / "repo_release_tools" / "commands"


def _load_min_chars() -> int:
    raw = os.getenv("RRT_DOCSTRING_MIN_CHARS")
    if raw is None:
        return MIN_DEFAULT
    try:
        return int(raw)
    except ValueError:
        pytest.fail(f"RRT_DOCSTRING_MIN_CHARS must be an integer; got {raw!r}")


def _should_exempt(path: Path, text: str) -> bool:
    return path.name in ("__init__.py", "__main__.py") or "rrt:docs-exempt" in text


def test_command_modules_have_rich_module_docstrings() -> None:
    """Fail if any command module has a missing/insufficient module docstring."""
    if not COMMANDS_DIR.exists():
        pytest.skip("commands directory not present")

    min_chars = _load_min_chars()
    offenses: list[str] = []
    for py in sorted(COMMANDS_DIR.glob("*.py")):
        text = py.read_text(encoding="utf-8")
        if _should_exempt(py, text):
            continue

        try:
            module = ast.parse(text)
        except SyntaxError as exc:  # pragma: no cover - defensive
            offenses.append(f"{py}: could not parse: {exc}")
            continue

        doc = ast.get_docstring(module)
        if not doc:
            offenses.append(f"{py}: missing module docstring")
            continue

        doc_stripped = doc.strip()
        if "\n" not in doc_stripped:
            offenses.append(f"{py}: module docstring is single-line")
            continue

        if len(doc_stripped) < min_chars:
            offenses.append(f"{py}: module docstring too short ({len(doc_stripped)} < {min_chars})")

    if offenses:
        errors = "\n".join(offenses)
        pytest.fail("Insufficient module docstrings in command modules:\n" + errors)
