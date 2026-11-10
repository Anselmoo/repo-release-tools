"""Findings for ``rrt arch check``: units, files, layers, imports and sync.

Library code only: no printing, no git calls, no writes. Every finding id is
``<kind>:<subject>`` with *subject* a POSIX path relative to the repo root,
so ids are identical on every machine and can live in the baseline.
"""

from __future__ import annotations

import ast
import os
import tomllib
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from repo_release_tools.config import ArchitectureConfig, ignore_dir_names
from repo_release_tools.config.model import ArchLayer, ArchUnit, parse_arch_layer
from repo_release_tools.folders.core import scan_directory

#: Finding kinds in report order.
FINDING_KINDS: tuple[str, ...] = (
    "missing-unit",
    "undeclared",
    "missing-file",
    "unplaced",
    "layer-import",
    "unparsable",
    "layers-sync",
)

#: ``is_ignored(paths) -> ignored_subset``; *paths* are repo-relative POSIX strings.
IgnoreFilter = Callable[[list[str]], set[str]]

#: A layer reduced to what import-linter compares: ``((name, optional), ...)`` plus separator.
_LayerSignature = tuple[tuple[tuple[str, bool], ...], str]


@dataclass(frozen=True, order=True)
class Finding:
    """One architecture finding. Ordering and equality use ``kind`` and ``subject`` only."""

    kind: str
    subject: str
    message: str = field(default="", compare=False)

    @property
    def id(self) -> str:
        """Return the stable baseline id ``<kind>:<subject>``."""
        return f"{self.kind}:{self.subject}"


@dataclass(frozen=True)
class _Module:
    """One Python module found under the root: dotted name, repo-relative path, kind."""

    name: str
    path: str
    is_package: bool


@dataclass(frozen=True)
class _Placement:
    """Where a unit sits in ``layers``: its layer index and the layer's separator."""

    unit: str
    index: int
    independent: bool


def root_module_name(root_dir: Path, stop: Path | None = None) -> str:
    """Return the dotted module name of *root_dir*.

    Walks up while the parent directory has an ``__init__.py``:
    ``src/acme`` gives ``acme``; ``src/a/b`` with
    ``src/a/__init__.py`` gives ``a.b``. The walk never reaches *stop*
    (normally the repo root), so a stray ``__init__.py`` above it is ignored.
    """
    root_dir = root_dir.absolute()
    limit = stop.absolute() if stop is not None else None
    parts = [root_dir.name]
    parent = root_dir.parent
    while (
        parent != parent.parent
        and parent != limit
        and (limit is None or parent.is_relative_to(limit))
        and (parent / "__init__.py").is_file()
    ):
        parts.append(parent.name)
        parent = parent.parent
    return ".".join(reversed(parts))


def collect_findings(
    config: ArchitectureConfig,
    repo_root: Path,
    *,
    is_ignored: IgnoreFilter | None = None,
) -> list[Finding]:
    """Return every finding for *config*, sorted by id, without duplicates.

    *repo_root* must be absolute and resolved, and ``repo_root / config.root``
    must be an existing directory (the command checks both). *is_ignored*
    filters ``undeclared`` candidates (e.g. gitignored files); ``None``
    ignores nothing beyond ``__pycache__``, dot-entries and
    ``ignore_dir_names()``.
    """
    root_dir = repo_root / config.root
    root_module = root_module_name(root_dir, repo_root)
    existing = [unit for unit in config.units if _unit_exists(unit, root_dir)]

    findings: list[Finding] = []
    findings.extend(_missing_units(config, root_dir, repo_root))
    findings.extend(_undeclared(config, root_dir, repo_root, is_ignored))
    findings.extend(_missing_files(config, existing, root_dir, repo_root))
    findings.extend(_unplaced(config, existing, root_dir, repo_root))
    findings.extend(_layer_imports(config, root_dir, repo_root, root_module))
    findings.extend(_layers_sync(config, repo_root, root_module))
    return sorted({finding.id: finding for finding in findings}.values(), key=_finding_id)


def _finding_id(finding: Finding) -> str:
    """Return the sort key of a finding: its id."""
    return finding.id


def _unit_exists(unit: ArchUnit, root_dir: Path) -> bool:
    """Return whether the unit's package directory or module file exists."""
    entry = root_dir / unit.entry_name
    return entry.is_file() if unit.is_module else entry.is_dir()


def _unit_subject(unit: ArchUnit, root_dir: Path, repo_root: Path) -> str:
    """Return the repo-relative POSIX path of the unit's entry."""
    return (root_dir / unit.entry_name).relative_to(repo_root).as_posix()


def _missing_units(config: ArchitectureConfig, root_dir: Path, repo_root: Path) -> list[Finding]:
    """Return a ``missing-unit`` finding for every declared unit that is absent."""
    findings: list[Finding] = []
    for unit in config.units:
        if not _unit_exists(unit, root_dir):
            subject = _unit_subject(unit, root_dir, repo_root)
            findings.append(
                Finding(
                    "missing-unit",
                    subject,
                    f"unit {unit.name!r} is declared but {subject} does not exist",
                )
            )
    return findings


def _hidden_name(name: str) -> bool:
    """Return whether a directory entry is never scanned for modules (cache or dot-entry)."""
    return name == "__pycache__" or name.startswith(".")


def _skipped_name(name: str) -> bool:
    """Return whether a root entry is never reported as ``undeclared``.

    Adds ``ignore_dir_names()`` (``build``, ``env``, ...) to the hidden names.
    That list describes tool output at the top of a tree, so it is not applied
    to the module walk, where ``build`` may be a real subpackage.
    """
    return _hidden_name(name) or name in ignore_dir_names()


def _undeclared(
    config: ArchitectureConfig,
    root_dir: Path,
    repo_root: Path,
    is_ignored: IgnoreFilter | None,
) -> list[Finding]:
    """Return ``undeclared`` findings for unexpected entries directly under the root."""
    allowed = (*(unit.entry_name for unit in config.units), *config.top_level_files)
    violations = scan_directory(
        base_path=root_dir,
        root=repo_root,
        name="architecture",
        allowed_files=allowed,
        exact=True,
    )
    candidates = [
        violation.path
        for violation in violations
        if violation.code == "unexpected-entry"
        and not _skipped_name(violation.path.rsplit("/")[-1])
    ]
    ignored = is_ignored(candidates) if is_ignored is not None and candidates else set()
    return [
        Finding(
            "undeclared",
            path,
            f"{path} is neither a declared unit nor one of top_level_files",
        )
        for path in candidates
        if path not in ignored
    ]


def _missing_files(
    config: ArchitectureConfig,
    existing: list[ArchUnit],
    root_dir: Path,
    repo_root: Path,
) -> list[Finding]:
    """Return ``missing-file`` findings for required files of existing package units."""
    return [
        Finding("missing-file", violation.path, violation.message)
        for unit in existing
        for violation in scan_directory(
            base_path=root_dir / unit.entry_name,
            root=repo_root,
            name=unit.name,
            required_files=config.required_files_for(unit),
        )
        if violation.code == "missing-file"
    ]


def _unplaced(
    config: ArchitectureConfig,
    existing: list[ArchUnit],
    root_dir: Path,
    repo_root: Path,
) -> list[Finding]:
    """Return ``unplaced`` findings: existing units absent from a non-empty ``layers``."""
    if not config.layers:
        return []
    placed = {name for layer in config.parsed_layers() for name in layer.names}
    return [
        Finding(
            "unplaced",
            _unit_subject(unit, root_dir, repo_root),
            f"unit {unit.name!r} exists but is not placed in layers",
        )
        for unit in existing
        if unit.name not in placed
    ]


# ---------------------------------------------------------------------------
# Import graph and layer-import findings
# ---------------------------------------------------------------------------


def _collect_modules(root_dir: Path, repo_root: Path, root_module: str) -> dict[str, _Module]:
    """Return every ``.py`` module under *root_dir*, keyed by dotted name (sorted walk)."""
    modules: dict[str, _Module] = {}
    for current, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = sorted(name for name in dirnames if not _hidden_name(name))
        for filename in sorted(filenames):
            if not filename.endswith(".py") or filename.startswith("."):
                continue
            file = Path(current) / filename
            parts = list(file.relative_to(root_dir).with_suffix("").parts)
            is_package = parts[-1] == "__init__"
            if is_package:
                parts.pop()
            name = ".".join([root_module, *parts])
            modules.setdefault(
                name, _Module(name, file.relative_to(repo_root).as_posix(), is_package)
            )
    return modules


def _longest_known_prefix(name: str, modules: dict[str, _Module]) -> str | None:
    """Return the longest dotted prefix of *name* that is a known module, else ``None``."""
    parts = name.split(".")
    for size in range(len(parts), 0, -1):
        candidate = ".".join(parts[:size])
        if candidate in modules:
            return candidate
    return None


def _imported_modules(
    tree: ast.AST, module: _Module, modules: dict[str, _Module]
) -> dict[str, int]:
    """Return ``{imported module: first line}`` for every import inside *tree*.

    The edge target is the named module only, never its parent ``__init__``s.
    """
    package = module.name if module.is_package else module.name.rpartition(".")[0]
    found: dict[str, int] = {}

    def record(target: str | None, line: int) -> None:
        """Keep the smallest line number seen for each distinct target."""
        if target is not None and target != module.name:
            found[target] = min(line, found.get(target, line))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                record(_longest_known_prefix(alias.name, modules), node.lineno)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                keep = len(package.split(".")) - (node.level - 1)
                if keep < 1:
                    continue
                base_parts = package.split(".")[:keep]
                if node.module:
                    base_parts.extend(node.module.split("."))
                base = ".".join(base_parts)
            else:
                base = node.module or ""
            for alias in node.names:
                candidate = f"{base}.{alias.name}"
                target = candidate if candidate in modules else _longest_known_prefix(base, modules)
                record(target, node.lineno)
    return found


def _build_import_graph(
    modules: dict[str, _Module], repo_root: Path
) -> tuple[dict[str, dict[str, int]], list[Finding]]:
    """Return ``{importer: {imported: first line}}`` plus an ``unparsable`` finding per failure.

    A module that cannot be read or parsed has unknown imports, so it is
    reported instead of being treated as importing nothing.
    """
    graph: dict[str, dict[str, int]] = {}
    unparsable: list[Finding] = []
    for module in modules.values():
        try:
            tree = ast.parse((repo_root / module.path).read_bytes())
        except (OSError, SyntaxError, ValueError) as exc:
            reason = exc.msg if isinstance(exc, SyntaxError) else str(exc)
            unparsable.append(
                Finding(
                    "unparsable",
                    module.path,
                    f"{module.path} could not be parsed, so its imports are unchecked: {reason}",
                )
            )
            continue
        graph[module.name] = _imported_modules(tree, module, modules)
    return graph, unparsable


def _placements(config: ArchitectureConfig) -> dict[str, _Placement]:
    """Return ``{unit import name: placement}`` for every unit named in ``layers``."""
    import_names = {unit.name: unit.import_name for unit in config.units}
    placements: dict[str, _Placement] = {}
    for index, layer in enumerate(config.parsed_layers()):
        for name in layer.names:
            placements[import_names.get(name, name)] = _Placement(name, index, layer.independent)
    return placements


def _module_placement(
    module: str, root_module: str, placements: dict[str, _Placement]
) -> _Placement | None:
    """Return the placement of the unit containing *module*, or ``None`` (unlayered)."""
    first = module.removeprefix(root_module).lstrip(".").split(".")[0]
    return placements.get(first)


def _violation_reason(
    importer: _Placement, imported: _Placement, layers: tuple[str, ...]
) -> str | None:
    """Return why importer -> imported breaks the layering, or ``None`` if it does not."""
    if importer.unit == imported.unit:
        return None
    if imported.index < importer.index:
        return (
            f"unit {importer.unit!r} (layer {layers[importer.index]!r}) sits below "
            f"{imported.unit!r} (layer {layers[imported.index]!r}) and must not import it"
        )
    if importer.index == imported.index and importer.independent:
        return (
            f"units {importer.unit!r} and {imported.unit!r} are independent siblings "
            f"in layer {layers[importer.index]!r}"
        )
    return None


def _layer_imports(
    config: ArchitectureConfig, root_dir: Path, repo_root: Path, root_module: str
) -> list[Finding]:
    """Return ``layer-import`` findings: direct edges and chains through unlayered modules."""
    placements = _placements(config)
    if not placements:
        return []
    modules = _collect_modules(root_dir, repo_root, root_module)
    graph, findings = _build_import_graph(modules, repo_root)
    layers = config.layers

    for start in sorted(graph):
        start_place = _module_placement(start, root_module, placements)
        if start_place is None:
            continue
        seen = {start}
        queue: deque[list[str]] = deque([[start]])
        while queue:
            path = queue.popleft()
            for nxt in sorted(graph.get(path[-1], {})):
                if nxt in seen:
                    continue
                seen.add(nxt)
                place = _module_placement(nxt, root_module, placements)
                if place is None:
                    queue.append([*path, nxt])
                    continue
                reason = _violation_reason(start_place, place, layers)
                if reason is None:
                    continue
                line = graph[start][path[1] if len(path) > 1 else nxt]
                via = f" via {' -> '.join(path[1:])}" if len(path) > 1 else ""
                findings.append(
                    Finding(
                        "layer-import",
                        f"{modules[start].path} -> {modules[nxt].path}",
                        f"{start} imports {nxt}{via} (line {line} of {modules[start].path}): "
                        f"{reason}",
                    )
                )
    return findings


# ---------------------------------------------------------------------------
# layers-sync (import-linter)
# ---------------------------------------------------------------------------


def _signature(layer: ArchLayer, import_names: dict[str, str]) -> _LayerSignature:
    """Return *layer* with unit names translated to import names."""
    entries = tuple(
        (import_names.get(entry.name, entry.name), entry.optional) for entry in layer.entries
    )
    return entries, layer.separator


def _render(signature: _LayerSignature) -> str:
    """Return a layer signature in import-linter grammar."""
    entries, separator = signature
    names = [f"({name})" if optional else name for name, optional in entries]
    return f" {separator} ".join(names)


def _dig(node: object, *keys: str) -> object:
    """Return ``node[k1][k2]...``, or ``None`` when a step is not a table or is absent."""
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def _importlinter_layer_specs(pyproject: Path, root_module: str) -> list[list[str]]:
    """Return the ``layers`` of each layers contract whose containers are ``[root_module]``."""
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return []
    raw = _dig(data, "tool", "importlinter", "contracts")
    contracts = raw if isinstance(raw, list) else []
    return [
        list(contract["layers"])
        for contract in contracts
        if isinstance(contract, dict)
        and contract.get("type") == "layers"
        and contract.get("containers") == [root_module]
        and isinstance(contract.get("layers"), list)
        and all(isinstance(spec, str) for spec in contract["layers"])
    ]


def _comparable(signatures: list[_LayerSignature]) -> list[tuple[frozenset[tuple[str, bool]], str]]:
    """Return *signatures* with each layer's entries as a set.

    Siblings within one layer have no order in import-linter, so
    ``a | b`` and ``b | a`` are the same layer.
    """
    return [(frozenset(entries), separator) for entries, separator in signatures]


def _parse_specs(specs: list[str]) -> list[_LayerSignature] | None:
    """Return the signatures of import-linter layer strings, or ``None`` if any is invalid.

    Contract layers already use import names, so nothing is translated.
    """
    try:
        return [_signature(parse_arch_layer(spec), {}) for spec in specs]
    except ValueError:
        return None


def _layers_sync(config: ArchitectureConfig, repo_root: Path, root_module: str) -> list[Finding]:
    """Return the ``layers-sync`` finding, if any (``layers_sync = "importlinter"`` only)."""
    if config.layers_sync != "importlinter" or not config.layers:
        return []
    import_names = {unit.name: unit.import_name for unit in config.units}
    expected = [_signature(layer, import_names) for layer in config.parsed_layers()]
    candidates = _importlinter_layer_specs(repo_root / "pyproject.toml", root_module)
    wanted_layers = _comparable(expected)
    for specs in candidates:
        parsed = _parse_specs(specs)
        if parsed is not None and _comparable(parsed) == wanted_layers:
            return []
    wanted = ", ".join(repr(_render(signature)) for signature in expected)
    if not candidates:
        message = (
            f"no [[tool.importlinter.contracts]] layers contract with "
            f'containers = ["{root_module}"] in pyproject.toml; expected layers: {wanted}'
        )
    else:
        found = ", ".join(repr(spec) for spec in candidates[0])
        message = (
            f'the layers contract with containers = ["{root_module}"] differs from '
            f"[tool.rrt.architecture].layers; expected: {wanted}; found: {found}"
        )
    return [Finding("layers-sync", "pyproject.toml", message)]
