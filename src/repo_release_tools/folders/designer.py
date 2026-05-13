"""Designer-mode helpers for inferring folder templates."""

from __future__ import annotations

import json
from pathlib import Path

from repo_release_tools.config import FolderTemplate


def capture_template(*, name: str, root: Path, loose: bool = False) -> FolderTemplate:
    """Infer a template from the immediate structure under *root*."""
    required_dirs: list[str] = []
    required_files: list[str] = []

    for child in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if child.is_dir():
            required_dirs.append(child.name)
            continue
        required_files.append(child.name)

    return FolderTemplate(
        name=name,
        description=f"Captured from {root.name}",
        strictness="loose" if loose else "strict",
        exact=not loose,
        required_files=tuple(required_files),
        required_dirs=tuple(required_dirs),
    )


def render_captured_template_toml(
    template: FolderTemplate,
    *,
    selector: str = ".",
    include_rule: bool = True,
) -> str:
    """Render a captured template as TOML snippet text."""
    lines = ["[tool.rrt.folders]", "", "[[tool.rrt.folders.templates]]"]
    lines.append(f"name = {json.dumps(template.name)}")
    lines.append(f"description = {json.dumps(template.description)}")
    lines.append(f"strictness = {json.dumps(template.strictness)}")
    lines.append(f"exact = {str(template.exact).lower()}")
    if template.required_files:
        lines.append(f"required_files = {_string_list(template.required_files)}")
    if template.required_dirs:
        lines.append(f"required_dirs = {_string_list(template.required_dirs)}")

    if include_rule:
        lines.extend(
            [
                "",
                "[[tool.rrt.folders.rules]]",
                f"name = {json.dumps(f'{template.name}-rule')}",
                f"selector = {json.dumps(selector)}",
                f"templates = [{json.dumps(template.name)}]",
            ],
        )

    return "\n".join(lines) + "\n"


def _string_list(values: tuple[str, ...]) -> str:
    """Render a tuple of strings as TOML list literal."""
    rendered = ", ".join(json.dumps(value) for value in values)
    return f"[{rendered}]"
