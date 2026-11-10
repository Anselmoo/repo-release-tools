"""Render ``.rrt/templates/<kind>/`` for ``rrt arch new``, and self-test kinds.

Library code only: no printing. Rendering uses :class:`string.Template`
(``$name`` / ``${name}``, ``$$`` escapes ``$``), so braces in Python, TS or
f-strings need no escaping. A missing variable is an error, never ``""``.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from string import Template
from tempfile import TemporaryDirectory

from repo_release_tools.config import ArchitectureConfig, ArchUnit
from repo_release_tools.state import arch_templates_dir

NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
KIND_KEYS: frozenset[str] = frozenset({"description", "requires_unit", "next_steps", "variables"})
BUILTIN_VARIABLES: frozenset[str] = frozenset(
    {"name", "Name", "root", "root_module", "unit", "unit_package", "unit_prefix", "unit_module"},
)
TEMPLATE_SUFFIX = ".tmpl"


class TemplateError(ValueError):
    """A kind, its variables or a rendered target is invalid; nothing was written."""


@dataclass(frozen=True)
class TemplateKind:
    """One parsed ``.rrt/templates/<kind>/`` directory."""

    name: str
    directory: Path
    description: str = ""
    requires_unit: bool = False
    next_steps: tuple[str, ...] = ()
    variables: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RenderedFile:
    """One rendered target: repo-relative POSIX *target*, absolute *path*, *body*."""

    target: str
    path: Path
    body: str
    exists: bool


def pascal_case(name: str) -> str:
    """Return ``prep_step`` as ``PrepStep``."""
    return "".join(part[:1].upper() + part[1:] for part in name.split("_") if part)


def list_kinds(repo_root: Path) -> list[str]:
    """Return the sorted kind names under ``.rrt/templates/`` (dirs with a ``kind.toml``)."""
    templates = arch_templates_dir(repo_root)
    if not templates.is_dir():
        return []
    return sorted(
        entry.name
        for entry in templates.iterdir()
        if entry.is_dir() and (entry / "kind.toml").is_file()
    )


def load_kind(repo_root: Path, kind: str) -> TemplateKind:
    """Load and validate one kind; raise :class:`TemplateError` if unknown or invalid."""
    available = list_kinds(repo_root)
    if kind not in available:
        listing = ", ".join(available) or "(none)"
        raise TemplateError(f"Unknown template kind {kind!r}. Available kinds: {listing}.")
    directory = arch_templates_dir(repo_root) / kind
    data = _read_kind_toml(kind, directory / "kind.toml")

    unknown = sorted(set(data) - KIND_KEYS)
    if unknown:
        raise TemplateError(
            f"kind {kind!r}: unknown key(s) in kind.toml: {', '.join(unknown)}. "
            f"Allowed: {', '.join(sorted(KIND_KEYS))}.",
        )

    description = data.get("description", "")
    if not isinstance(description, str):
        raise TemplateError(f"kind {kind!r}: 'description' must be a string.")
    requires_unit = data.get("requires_unit", False)
    if not isinstance(requires_unit, bool):
        raise TemplateError(f"kind {kind!r}: 'requires_unit' must be a boolean.")
    next_steps = data.get("next_steps", [])
    if not isinstance(next_steps, list) or not all(isinstance(item, str) for item in next_steps):
        raise TemplateError(f"kind {kind!r}: 'next_steps' must be a list of strings.")
    variables = data.get("variables", {})
    if not isinstance(variables, dict) or not all(
        isinstance(value, str) for value in variables.values()
    ):
        raise TemplateError(f"kind {kind!r}: 'variables' must be a table of string values.")
    shadowed = sorted(set(variables) & BUILTIN_VARIABLES)
    if shadowed:
        raise TemplateError(
            f"kind {kind!r}: variables cannot override built-ins: {', '.join(shadowed)}.",
        )

    loaded = TemplateKind(
        name=kind,
        directory=directory,
        description=description,
        requires_unit=requires_unit,
        next_steps=tuple(next_steps),
        variables=dict(variables),
    )
    _template_files(loaded)  # fail early on a kind without files or with a non-.tmpl file
    return loaded


def build_variables(
    *,
    config: ArchitectureConfig,
    root_module: str,
    name: str,
    unit: ArchUnit | None,
    kind: TemplateKind,
) -> dict[str, str]:
    """Return built-in variables merged with the kind's constants.

    Raises :class:`TemplateError` for a bad *name*, a kind that requires a
    unit when *unit* is ``None``, or a kind constant that shadows a built-in.
    """
    if not NAME_RE.fullmatch(name):
        raise TemplateError(
            f"Invalid name {name!r}. Use lowercase letters, digits and underscores; "
            "it must start with a letter.",
        )
    if kind.requires_unit and unit is None:
        raise TemplateError(f"kind {kind.name!r} requires a unit; pass one with --unit.")
    shadowed = sorted(set(kind.variables) & BUILTIN_VARIABLES)
    if shadowed:
        raise TemplateError(
            f"kind {kind.name!r}: variables cannot override built-ins: {', '.join(shadowed)}.",
        )

    variables = {
        "name": name,
        "Name": pascal_case(name),
        "root": config.root,
        "root_module": root_module,
    }
    if unit is not None:
        variables["unit"] = unit.name
        variables["unit_package"] = unit.import_name
        variables["unit_prefix"] = unit.template_prefix
        variables["unit_module"] = f"{root_module}.{unit.import_name}"
    variables.update(kind.variables)
    return variables


def render_kind(
    kind: TemplateKind,
    variables: dict[str, str],
    repo_root: Path,
    *,
    force: bool = False,
) -> list[RenderedFile]:
    """Render every target and check all of them before anything is written.

    Raises :class:`TemplateError` for an unresolved placeholder, a target
    that is absolute, contains ``..`` or resolves outside *repo_root*, or an
    existing target without *force*. Sorted by target.
    """
    root = repo_root.resolve()
    rendered: list[RenderedFile] = []
    seen: dict[Path, str] = {}
    for source in _template_files(kind):
        relative = source.relative_to(kind.directory / _FILES_DIR).as_posix()
        label = f"kind {kind.name!r}, file {relative!r}"
        target = _substitute(relative.removesuffix(TEMPLATE_SUFFIX), variables, f"{label} (path)")
        path = _checked_target(target, root, label)
        if path in seen:
            raise TemplateError(
                f"{label}: target {target!r} is also produced by {seen[path]!r}.",
            )
        seen[path] = relative
        if path.exists() and not force:
            raise TemplateError(f"{label}: target {target!r} already exists; use --force.")
        body = _substitute(_read_text(source, label), variables, label)
        rendered.append(RenderedFile(target=target, path=path, body=body, exists=path.exists()))
    return sorted(rendered, key=lambda item: item.target)


def write_rendered(files: list[RenderedFile]) -> None:
    """Write every rendered file, creating parent directories."""
    for item in files:
        item.path.parent.mkdir(parents=True, exist_ok=True)
        item.path.write_text(item.body, encoding="utf-8")


def check_templates(
    config: ArchitectureConfig,
    repo_root: Path,
    root_module: str,
) -> dict[str, list[str]]:
    """Self-test every kind; return ``{kind: [problem, ...]}`` (empty list = ok).

    Sample values: ``name = "example"`` and the first unit with role
    ``unit``. Renders into a temporary directory, checks targets stay
    inside it, compiles every rendered ``.py`` and runs no commands.
    """
    unit = next((candidate for candidate in config.units if candidate.role == "unit"), None)
    results: dict[str, list[str]] = {}
    for kind_name in list_kinds(repo_root):
        results[kind_name] = _check_kind(config, repo_root, root_module, kind_name, unit)
    return results


_FILES_DIR = "files"


def _read_kind_toml(kind: str, path: Path) -> dict[str, object]:
    """Return the parsed ``kind.toml`` or raise :class:`TemplateError`."""
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise TemplateError(f"kind {kind!r}: cannot read kind.toml: {exc}") from exc


def _read_text(path: Path, label: str) -> str:
    """Read a template source as UTF-8 or raise :class:`TemplateError`."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise TemplateError(f"{label}: cannot read template: {exc}") from exc


def _template_files(kind: TemplateKind) -> list[Path]:
    """Return the sorted ``files/**/*.tmpl`` sources of *kind*, validating them."""
    files_dir = kind.directory / _FILES_DIR
    sources: list[Path] = []
    if files_dir.is_dir():
        for path in sorted(files_dir.rglob("*")):
            if not path.is_file() or _is_ignored(path.relative_to(files_dir)):
                continue
            if not path.name.endswith(TEMPLATE_SUFFIX):
                raise TemplateError(
                    f"kind {kind.name!r}: file {path.relative_to(files_dir).as_posix()!r} "
                    f"must end in {TEMPLATE_SUFFIX!r}.",
                )
            sources.append(path)
    if not sources:
        raise TemplateError(
            f"kind {kind.name!r}: no template files under {_FILES_DIR}/ "
            f"(expected *{TEMPLATE_SUFFIX}).",
        )
    return sources


def _is_ignored(relative: Path) -> bool:
    """Return whether a ``files/`` entry is skipped (editor droppings, caches)."""
    if "__pycache__" in relative.parts:
        return True
    return relative.name.startswith(".") and not relative.name.endswith(TEMPLATE_SUFFIX)


def _substitute(text: str, variables: dict[str, str], label: str) -> str:
    """Return ``string.Template(text).substitute(variables)`` or raise :class:`TemplateError`."""
    try:
        return Template(text).substitute(variables)
    except KeyError as exc:
        raise TemplateError(f"{label}: unknown placeholder ${{{exc.args[0]}}}.") from exc
    except ValueError as exc:
        raise TemplateError(
            f"{label}: invalid placeholder ({exc}); use $$ for a literal $."
        ) from exc


def _checked_target(target: str, root: Path, label: str) -> Path:
    """Return the absolute path of *target* or raise if it is unsafe."""
    pure = PurePosixPath(target)
    if not pure.parts:
        raise TemplateError(f"{label}: rendered target {target!r} is empty.")
    if pure.is_absolute() or Path(target).is_absolute():
        raise TemplateError(f"{label}: target {target!r} must be relative to the repo root.")
    if ".." in pure.parts:
        raise TemplateError(f"{label}: target {target!r} must not contain '..'.")
    path = (root / target).resolve()
    if not path.is_relative_to(root):
        raise TemplateError(f"{label}: target {target!r} resolves outside the repo root.")
    if path.is_dir():
        raise TemplateError(f"{label}: target {target!r} is a directory.")
    for parent in path.parents:
        if parent == root:
            break
        if parent.exists() and not parent.is_dir():
            blocker = parent.relative_to(root).as_posix()
            raise TemplateError(
                f"{label}: target {target!r} needs directory {blocker!r}, which is a file."
            )
    return path


def _check_kind(
    config: ArchitectureConfig,
    repo_root: Path,
    root_module: str,
    kind_name: str,
    unit: ArchUnit | None,
) -> list[str]:
    """Return the problems found while self-testing one kind."""
    try:
        kind = load_kind(repo_root, kind_name)
    except TemplateError as exc:
        return [str(exc)]
    if kind.requires_unit and unit is None:
        return ["requires a unit but no unit with role 'unit' is declared"]
    problems: list[str] = []
    with TemporaryDirectory() as tmp:
        try:
            variables = build_variables(
                config=config,
                root_module=root_module,
                name="example",
                unit=unit,
                kind=kind,
            )
            rendered = render_kind(kind, variables, Path(tmp))
            write_rendered(rendered)
        except (TemplateError, OSError) as exc:
            return [str(exc)]
        for item in rendered:
            if not item.target.endswith(".py"):
                continue
            try:
                compile(item.body, item.target, "exec")
            except SyntaxError as exc:
                problems.append(f"{item.target}: line {exc.lineno}: {exc.msg}")
    return problems
