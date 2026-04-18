"""Configuration loading for rrt."""

from __future__ import annotations

import json
import re
import tomllib

from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent


DEFAULT_RELEASE_BRANCH = "release/v{version}"
DEFAULT_CHANGELOG = "CHANGELOG.md"
DEFAULT_LOCK_COMMAND = ["uv", "lock", "-U"]
DEFAULT_GENERIC_LOCK_COMMAND: list[str] = []

CONFIG_FILE_CANDIDATES = (
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    ".rrt.toml",
    ".config/rrt.toml",
)

# Per-file rrt config section names used in user-facing guidance messages.
CONFIG_SECTION_BY_FILE: dict[str, str] = {
    "pyproject.toml": "[tool.rrt]",
    "package.json": "rrt (top-level key)",
    "Cargo.toml": "[package.metadata.rrt] / [workspace.metadata.rrt]",
    ".rrt.toml": "[tool.rrt]",
    ".config/rrt.toml": "[tool.rrt]",
}

# Sentinel: lock_command / generated_files not explicitly configured → auto-detect.
_AUTO: list[str] | None = None

VALID_TARGET_KINDS = frozenset({"pep621", "package_json", "python_version", "go_version"})

# Directory names to skip when scanning for Python __version__ files.
_IGNORE_DIR_NAMES: frozenset[str] = frozenset(
    {".venv", "venv", "env", ".env", "node_modules", "__pycache__", ".git", ".tox", "dist", "build"}
)

# Matches the first occurrence of a `__version__ = "..."` / `'...'` declaration,
# allowing optional leading whitespace before the assignment.
_PYTHON_VERSION_VAR_RE: re.Pattern[str] = re.compile(r"(?m)^\s*__version__\s*=\s*['\"]")

# Branch type prefixes that are built-in and must not appear in extra_branch_types.
# Mirrors CONVENTIONAL_TYPES, MAGIC_BRANCH_TYPES, and BOT_BRANCH_TYPES from hooks.py.
_RESERVED_BRANCH_TYPES = frozenset(
    {
        # conventional commit types
        "feat",
        "fix",
        "chore",
        "docs",
        "refactor",
        "test",
        "ci",
        "perf",
        "style",
        "build",
        # AI agent magic types
        "claude",
        "codex",
        "copilot",
        # dependency bot types
        "dependabot",
        "renovate",
    }
)

# Valid identifier pattern for extra_branch_types entries (after normalization).
# Must start with a lowercase letter; remaining chars may be lowercase letters,
# digits, hyphens, or underscores.  Empty strings and entries starting with a
# digit or special character are rejected.
_BRANCH_TYPE_IDENTIFIER_RE = re.compile(r"[a-z][a-z0-9_-]*")

VALID_CI_FORMATS = frozenset({"pep440", "semver_pre"})

AUTODETECTED_CONFIG_BASENAME = ".rrt.autodetected.toml"
DEFAULT_INIT_CONFIG = ".rrt.toml"

PYTHON_TOOL_RRT_EXAMPLE = dedent(
    """\
    [tool.rrt]
    release_branch = "release/v{version}"

    [[tool.rrt.version_targets]]
    path = "pyproject.toml"
    kind = "pep621"
    """
).strip()

NODE_TOOL_RRT_EXAMPLE = dedent(
    """\
    [tool.rrt]
    release_branch = "release/v{version}"

    [[tool.rrt.version_targets]]
    path = "package.json"
    kind = "package_json"
    ci_format = "semver_pre"
    """
).strip()

RUST_TOOL_RRT_EXAMPLE = dedent(
    """\
    [tool.rrt]
    release_branch = "release/v{version}"

    [[tool.rrt.version_targets]]
    path = "Cargo.toml"
    section = "package"
    field = "version"
    ci_format = "semver_pre"
    """
).strip()

GO_TOOL_RRT_EXAMPLE = dedent(
    """\
    [tool.rrt]
    release_branch = "release/v{version}"

    [[tool.rrt.version_targets]]
    path = "internal/version/version.go"
    kind = "go_version"
    """
).strip()

GENERIC_TOOL_RRT_EXAMPLE = dedent(
    """\
    [tool.rrt]
    release_branch = "release/v{version}"
    changelog_file = "CHANGELOG.md"

    # Replace this starter target with the file that owns your version string.
    [[tool.rrt.version_targets]]
    path = "path/to/version-file"
    pattern = '^(const Version = ")([^"]+)(")$'
    """
).strip()


@dataclass(frozen=True)
class VersionTarget:
    """A single version target."""

    path: Path
    kind: str | None = None
    pattern: str | None = None
    section: str | None = None
    field: str | None = None
    ci_format: str | None = None

    def validate(self) -> None:
        """Validate target shape.

        All checks run unconditionally so that ``ci_format`` is always
        validated regardless of which replacement mechanism is configured.
        """
        if self.kind is not None and self.kind not in VALID_TARGET_KINDS:
            allowed = ", ".join(sorted(VALID_TARGET_KINDS))
            raise ValueError(f"kind must be one of {allowed}, got {self.kind!r}")

        has_kind = self.kind in VALID_TARGET_KINDS
        has_pattern = self.pattern is not None
        has_section = self.section is not None
        has_field = self.field is not None

        if has_section != has_field:
            raise ValueError("section and field must be configured together")

        has_section_field = has_section and has_field
        configured_modes = sum((has_kind, has_pattern, has_section_field))
        if configured_modes == 0:
            kind_opts = " or ".join(f"kind={k!r}" for k in sorted(VALID_TARGET_KINDS))
            raise ValueError(
                f"Each version target must define either {kind_opts}, pattern, or section+field"
            )
        if configured_modes > 1:
            raise ValueError(
                "Version target replacement selectors are mutually exclusive: "
                "use exactly one of kind, pattern, or section+field"
            )

        if has_pattern:
            re.compile(self.pattern)
        if self.ci_format is not None:
            if not isinstance(self.ci_format, str):
                raise ValueError(
                    f"ci_format must be a string equal to 'pep440' or 'semver_pre', "
                    f"got {type(self.ci_format).__name__}: {self.ci_format!r}"
                )
            if self.ci_format not in VALID_CI_FORMATS:
                raise ValueError(
                    f"ci_format must be 'pep440' or 'semver_pre', got {self.ci_format!r}"
                )


@dataclass(frozen=True)
class VersionGroup:
    """A coordinated release unit inside a repository."""

    name: str
    release_branch: str
    changelog_file: Path
    lock_command: list[str]
    generated_files: list[Path]
    version_targets: list[VersionTarget]
    version_source: Path | None = None

    def primary_target(self) -> VersionTarget:
        """Return the target used as the canonical version source."""
        if self.version_source is None:
            return self.version_targets[0]

        for target in self.version_targets:
            if target.path == self.version_source:
                return target

        raise ValueError(
            f"Group {self.name!r} version_source {self.version_source} does not match any target"
        )


@dataclass(frozen=True)
class RrtConfig:
    """Loaded rrt configuration."""

    root: Path
    config_file: Path
    version_groups: list[VersionGroup]
    default_group_name: str | None = None
    autodetected: bool = False
    extra_branch_types: tuple[str, ...] = ()

    def resolve_group(self, name: str | None = None) -> VersionGroup:
        """Resolve a version group by name or default selection rules."""
        if name is not None:
            for group in self.version_groups:
                if group.name == name:
                    return group
            available = ", ".join(group.name for group in self.version_groups)
            raise ValueError(f"Unknown version group {name!r}. Available groups: {available}")

        if self.default_group_name is not None:
            return self.resolve_group(self.default_group_name)

        if len(self.version_groups) == 1:
            return self.version_groups[0]

        available = ", ".join(group.name for group in self.version_groups)
        raise ValueError(
            "Multiple version groups configured. Select one explicitly with --group "
            f"(available: {available})."
        )

    @property
    def release_branch(self) -> str:
        """Backward-compatible access to the default group's release branch."""
        return self.resolve_group().release_branch

    @property
    def changelog_file(self) -> Path:
        """Backward-compatible access to the default group's changelog file."""
        return self.resolve_group().changelog_file

    @property
    def lock_command(self) -> list[str]:
        """Backward-compatible access to the default group's lock command."""
        return self.resolve_group().lock_command

    @property
    def generated_files(self) -> list[Path]:
        """Backward-compatible access to the default group's generated files."""
        return self.resolve_group().generated_files

    @property
    def version_targets(self) -> list[VersionTarget]:
        """Backward-compatible access to the default group's version targets."""
        return self.resolve_group().version_targets


class MissingRrtConfigError(ValueError):
    """Raised when a supported config file exists but does not contain rrt config."""


def is_missing_tool_rrt_error(exc: Exception) -> bool:
    """Return whether *exc* means supported config files exist without rrt config."""
    if isinstance(exc, MissingRrtConfigError):
        return True

    message = str(exc)
    return message.startswith("Missing rrt configuration in supported config files:")


def load_config(root: Path) -> RrtConfig:
    """Load explicit rrt config, or fall back to supported zero-config detection."""
    missing_tool_rrt: list[Path] = []
    for config_file in iter_config_files(root):
        try:
            return load_config_from_path(root, config_file)
        except MissingRrtConfigError:
            missing_tool_rrt.append(config_file)
        except ValueError:
            raise

    autodetected = autodetect_config(root)
    if autodetected is not None:
        return autodetected

    if missing_tool_rrt:
        checked = ", ".join(str(path.relative_to(root)) for path in missing_tool_rrt)
        raise ValueError(f"Missing rrt configuration in supported config files: {checked}")

    expected = ", ".join(CONFIG_FILE_CANDIDATES)
    raise FileNotFoundError(f"Missing supported config file in {root} (checked: {expected})")


def load_extra_branch_types(cwd: Path) -> tuple[str, ...]:
    """Load extra_branch_types from the rrt config in *cwd*, if available.

    Returns an empty tuple when no config file exists or when the config does not
    contain an ``[tool.rrt]`` section.  Raises ``ValueError`` for any other
    configuration error (e.g. TOML parse errors or invalid ``extra_branch_types``
    values) so that misconfiguration is visible rather than silently ignored.
    """
    try:
        cfg = load_config(cwd)
        return cfg.extra_branch_types
    except FileNotFoundError:
        return ()
    except ValueError as exc:
        if is_missing_tool_rrt_error(exc):
            return ()
        raise ValueError(f"Failed to load extra_branch_types configuration: {exc}") from exc


def find_config_file(root: Path) -> Path:
    """Find the first supported config file that contains [tool.rrt]."""
    return load_config(root).config_file


def iter_config_files(root: Path) -> list[Path]:
    """Return supported config files that exist in discovery order."""
    return [root / candidate for candidate in CONFIG_FILE_CANDIDATES if (root / candidate).exists()]


def load_or_autodetect_config(root: Path) -> RrtConfig:
    """Load explicit config, or fall back to safe auto-detection."""
    try:
        return load_config(root)
    except FileNotFoundError:
        autodetected = autodetect_config(root)
        if autodetected is not None:
            return autodetected
        raise
    except ValueError as exc:
        if not is_missing_tool_rrt_error(exc):
            raise
        autodetected = autodetect_config(root)
        if autodetected is not None:
            return autodetected
        raise


def autodetect_config(root: Path) -> RrtConfig | None:
    """Build an implicit config from common root-level version files."""
    targets = _autodetect_version_targets(root)
    if len(targets) > 1:
        lock_cmd, gen_files = _recommended_lock_settings(root, targets)
        group = VersionGroup(
            name="default",
            release_branch=DEFAULT_RELEASE_BRANCH,
            changelog_file=root / DEFAULT_CHANGELOG,
            lock_command=lock_cmd,
            generated_files=[root / f for f in gen_files],
            version_targets=targets,
            version_source=targets[0].path,
        )
        return RrtConfig(
            root=root,
            config_file=root / AUTODETECTED_CONFIG_BASENAME,
            version_groups=[group],
            default_group_name="default",
            autodetected=True,
        )

    single = auto_detect_config(root)
    if single is not None:
        return RrtConfig(
            root=single.root,
            config_file=single.config_file,
            version_groups=single.version_groups,
            default_group_name=single.default_group_name,
            autodetected=True,
        )

    return None


def format_autodetected_config_notice(config: RrtConfig) -> str:
    """Describe the implicit version targets chosen for zero-config mode."""
    group = config.resolve_group()
    targets = ", ".join(
        _describe_version_target(target, root=config.root) for target in group.version_targets
    )
    file_guidance = "; ".join(
        f"{name} \u2192 {CONFIG_SECTION_BY_FILE[name]}" for name in CONFIG_FILE_CANDIDATES
    )
    return (
        "Using auto-detected version targets: "
        f"{targets}. For optional fine-tuning (groups, release branches, changelog path, "
        "lock commands, generated files, or custom patterns), add rrt config using the "
        f"appropriate section for your project file: {file_guidance}. "
        f"Run `rrt init` to write the recommended {DEFAULT_INIT_CONFIG}."
    )


def format_missing_tool_rrt_guidance(root: Path, checked_files: list[Path] | None = None) -> str:
    """Render actionable setup guidance when [tool.rrt] is missing."""
    checked_files = iter_config_files(root) if checked_files is None else checked_files

    lines: list[str] = []
    if checked_files:
        checked = ", ".join(str(path.relative_to(root)) for path in checked_files)
        lines.append(f"No rrt configuration was found in supported config files: {checked}")
    else:
        supported = ", ".join(CONFIG_FILE_CANDIDATES)
        lines.append(f"No supported config file was found. Supported locations: {supported}")

    lines.extend(
        [
            "",
            "Zero-config mode auto-detects these version files:",
            "  - pyproject.toml -> [project].version",
            "  - src/<package>/__init__.py, src/<package>/__version__.py -> __version__",
            "  - package.json -> top-level version",
            "  - Cargo.toml -> [package].version",
            "",
            "If none of those exist, add rrt config using the appropriate section for your project file:",
        ]
    )
    for name in CONFIG_FILE_CANDIDATES:
        lines.append(f"  - {name} \u2192 {CONFIG_SECTION_BY_FILE[name]}")

    lines.extend(
        [
            "",
            f"Run `rrt init` to generate a recommended {DEFAULT_INIT_CONFIG} starter.",
            "",
            "Examples:",
            "",
            "Python / PEP 621:",
            *[f"    {line}" for line in PYTHON_TOOL_RRT_EXAMPLE.splitlines()],
            "",
            "Node / package.json:",
            *[f"    {line}" for line in NODE_TOOL_RRT_EXAMPLE.splitlines()],
            "",
            "Rust / Cargo.toml:",
            *[f"    {line}" for line in RUST_TOOL_RRT_EXAMPLE.splitlines()],
            "",
            "Go example (Go projects with an in-file version constant or variable):",
            *[f"    {line}" for line in GO_TOOL_RRT_EXAMPLE.splitlines()],
            "",
            "Local repo config works too: put that table in .rrt.toml or .config/rrt.toml",
            "if you do not want to keep release-tool config in pyproject.toml.",
        ]
    )
    return "\n".join(lines)


def _find_python_version_files(root: Path) -> list[Path]:
    """Find Python files that declare ``__version__`` in common src/flat package layouts.

    Scans one level deep under ``src/`` and directly under *root* for
    ``__version__.py`` and ``__init__.py`` files that contain a
    ``__version__ = ...`` assignment.  Common non-package directories are
    skipped.
    """
    found: list[Path] = []
    seen: set[Path] = set()
    for base in (root / "src", root):
        if not base.is_dir():
            continue
        try:
            children = sorted(base.iterdir())
        except OSError:
            continue
        for pkg_dir in children:
            if not pkg_dir.is_dir() or pkg_dir.name in _IGNORE_DIR_NAMES:
                continue
            for name in ("__version__.py", "__init__.py"):
                candidate = pkg_dir / name
                if candidate in seen or not candidate.exists():
                    continue
                try:
                    text = candidate.read_text(encoding="utf-8")
                except OSError:
                    continue
                if _PYTHON_VERSION_VAR_RE.search(text):
                    seen.add(candidate)
                    found.append(candidate)
    return found


def _autodetect_version_targets(root: Path) -> list[VersionTarget]:
    """Discover common version targets in the repository root."""
    targets: list[VersionTarget] = []

    pyproject = root / "pyproject.toml"
    if _toml_string_field_exists(pyproject, section="project", field="version"):
        targets.append(VersionTarget(path=pyproject, kind="pep621", ci_format="pep440"))
    elif _toml_string_field_exists(pyproject, section="tool.poetry", field="version"):
        targets.append(
            VersionTarget(
                path=pyproject,
                section="tool.poetry",
                field="version",
                ci_format="pep440",
            )
        )

    package_json = root / "package.json"
    if _json_string_field_exists(package_json, field="version"):
        targets.append(
            VersionTarget(path=package_json, kind="package_json", ci_format="semver_pre")
        )

    cargo_toml = root / "Cargo.toml"
    if _toml_string_field_exists(cargo_toml, section="package", field="version"):
        targets.append(
            VersionTarget(
                path=cargo_toml,
                section="package",
                field="version",
                ci_format="semver_pre",
            )
        )
    elif _toml_string_field_exists(cargo_toml, section="workspace.package", field="version"):
        targets.append(
            VersionTarget(
                path=cargo_toml,
                section="workspace.package",
                field="version",
                ci_format="semver_pre",
            )
        )

    # Python __version__ variable files (secondary targets alongside pep621/poetry).
    has_python = any(t.kind == "pep621" or t.section == "tool.poetry" for t in targets)
    if has_python:
        for py_file in _find_python_version_files(root):
            if any(t.path == py_file for t in targets):
                continue
            targets.append(VersionTarget(path=py_file, kind="python_version", ci_format="pep440"))

    return targets


def _toml_string_field_exists(path: Path, *, section: str, field: str) -> bool:
    """Return whether a TOML file contains a string field in a named section."""
    if not path.exists():
        return False

    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except (tomllib.TOMLDecodeError, OSError):
        return False

    current: object = data
    for part in section.split("."):
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]

    return isinstance(current, dict) and isinstance(current.get(field), str)


def _json_string_field_exists(path: Path, *, field: str) -> bool:
    """Return whether a JSON file contains a string field at the top level."""
    if not path.exists():
        return False

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False

    return isinstance(data, dict) and isinstance(data.get(field), str)


def _describe_version_target(target: VersionTarget, *, root: Path) -> str:
    """Render a short human label for a version target."""
    relative = str(target.path.relative_to(root))
    if target.kind == "pep621":
        return f"{relative} ([project].version)"
    if target.kind == "package_json":
        return f"{relative} (version)"
    if target.kind == "python_version":
        return f"{relative} (__version__)"
    if target.kind == "go_version":
        return f"{relative} (Version)"
    if target.section and target.field:
        return f"{relative} ([{target.section}].{target.field})"
    if target.pattern:
        return f"{relative} (pattern)"
    return relative


def find_explicit_config_file(root: Path) -> Path | None:
    """Return the first config file that contains explicit rrt configuration."""
    for config_file in iter_config_files(root):
        try:
            load_config_from_path(root, config_file)
        except MissingRrtConfigError:
            continue
        return config_file
    return None


def recommend_init_config(root: Path) -> str:
    """Return a recommended .rrt.toml file for the current repository."""
    config = autodetect_config(root)
    if config is not None:
        return _render_recommended_rrt_toml(root, config.resolve_group())

    if (root / "go.mod").exists():
        return "\n".join(
            [
                "# Edit the starter target below before using `rrt bump`.",
                GO_TOOL_RRT_EXAMPLE,
            ]
        )

    return GENERIC_TOOL_RRT_EXAMPLE


def recommend_init_section_for_pyproject(root: Path) -> str:
    """Return a [tool.rrt] TOML snippet to append to an existing pyproject.toml."""
    config = autodetect_config(root)
    if config is not None:
        return _render_recommended_rrt_toml(root, config.resolve_group())
    return PYTHON_TOOL_RRT_EXAMPLE


def recommend_init_section_for_cargo(root: Path) -> str:
    """Return a [package.metadata.rrt] TOML snippet to append to an existing Cargo.toml."""
    config = autodetect_config(root)
    if config is not None:
        return _render_recommended_rrt_toml(
            root, config.resolve_group(), prefix="package.metadata.rrt"
        )
    return RUST_TOOL_RRT_EXAMPLE


def _render_recommended_rrt_toml(
    root: Path, group: VersionGroup, *, prefix: str = "tool.rrt"
) -> str:
    """Render an rrt config block mirroring the current recommended defaults.

    *prefix* controls the TOML table header used (e.g. ``tool.rrt`` for
    ``.rrt.toml`` / ``pyproject.toml``, or ``package.metadata.rrt`` for
    ``Cargo.toml``).
    """
    lines = [
        f"[{prefix}]",
        f"release_branch = {_toml_basic_string(group.release_branch)}",
        f"changelog_file = {_toml_basic_string(str(group.changelog_file.relative_to(root)))}",
    ]

    lock_command, generated_files = _recommended_lock_settings(root, group.version_targets)
    if lock_command:
        lines.append(f"lock_command = {_toml_string_list(lock_command)}")
    if generated_files:
        lines.append(f"generated_files = {_toml_string_list(generated_files)}")
    if len(group.version_targets) > 1:
        lines.append(
            f"version_source = {_toml_basic_string(str(group.primary_target().path.relative_to(root)))}"
        )

    for target in group.version_targets:
        lines.extend(["", f"[[{prefix}.version_targets]]"])
        lines.append(f"path = {_toml_basic_string(str(target.path.relative_to(root)))}")
        if target.kind is not None:
            lines.append(f"kind = {_toml_basic_string(target.kind)}")
        if target.pattern is not None:
            lines.append(f"pattern = {_toml_literal_string(target.pattern)}")
        if target.section is not None:
            lines.append(f"section = {_toml_basic_string(target.section)}")
        if target.field is not None:
            lines.append(f"field = {_toml_basic_string(target.field)}")
        if target.ci_format is not None:
            lines.append(f"ci_format = {_toml_basic_string(target.ci_format)}")

    return "\n".join(lines)


def _recommended_lock_settings(
    root: Path,
    targets: list[VersionTarget],
) -> tuple[list[str], list[str]]:
    """Return lockfile settings worth materialising into generated local config."""
    ecosystems = {_target_ecosystem(target) for target in targets}
    ecosystems.discard(None)
    if len(ecosystems) != 1:
        return [], []

    ecosystem = next(iter(ecosystems))
    if ecosystem == "python-pep621":
        return list(DEFAULT_LOCK_COMMAND), ["uv.lock"]
    if ecosystem == "python-poetry":
        return ["poetry", "lock"], ["poetry.lock"]
    if ecosystem in {"node", "rust", "go"}:
        return _detect_lock_and_files(root, targets)
    return [], []


def _target_ecosystem(target: VersionTarget) -> str | None:
    """Classify a version target by ecosystem for config recommendations."""
    if target.kind == "pep621":
        return "python-pep621"
    if target.kind == "package_json":
        return "node"
    if target.kind == "python_version":
        # Ecosystem-neutral: a secondary __version__ file inherits the lock
        # settings of whatever primary target (pep621/poetry) it accompanies.
        return None
    if target.kind == "go_version":
        return "go"
    if target.section == "tool.poetry":
        return "python-poetry"
    if target.path.name == "Cargo.toml" and target.section in {"package", "workspace.package"}:
        return "rust"
    if target.path.name == "go.mod" or target.path.suffix == ".go":
        return "go"
    return None


def _toml_basic_string(value: str) -> str:
    """Render a TOML basic string."""
    return json.dumps(value)


def _toml_literal_string(value: str) -> str:
    """Render a TOML literal string."""
    return "'" + value.replace("'", "''") + "'"


def _toml_string_list(values: list[str]) -> str:
    """Render a TOML string list."""
    rendered = ", ".join(_toml_basic_string(value) for value in values)
    return f"[{rendered}]"


def load_config_from_path(root: Path, config_file: Path) -> RrtConfig:
    """Load native rrt configuration from a specific config file."""
    raw = _load_raw_config(config_file)
    if not isinstance(raw, dict):
        raise ValueError(f"rrt configuration in {config_file.name} must be a table/object")

    raw_groups = raw.get("version_groups")
    has_flat_targets = "version_targets" in raw
    if raw_groups is not None and has_flat_targets:
        raise ValueError("Use either flat version_targets or version_groups, not both")

    default_group_name = raw.get("default_group")
    if default_group_name is not None and not isinstance(default_group_name, str):
        raise ValueError("tool.rrt.default_group must be a string")

    raw_extra_branch_types = raw.get("extra_branch_types", [])
    if not isinstance(raw_extra_branch_types, list) or not all(
        isinstance(item, str) for item in raw_extra_branch_types
    ):
        raise ValueError("tool.rrt.extra_branch_types must be a list of strings")
    seen_extra: set[str] = set()
    extra_branch_types_list: list[str] = []
    for raw_item in raw_extra_branch_types:
        normalized = raw_item.strip().lower()
        if not normalized:
            raise ValueError("tool.rrt.extra_branch_types entries must be non-empty identifiers")
        if not _BRANCH_TYPE_IDENTIFIER_RE.fullmatch(normalized):
            raise ValueError(
                f"tool.rrt.extra_branch_types entry {raw_item!r} is not a valid identifier "
                "(use lowercase letters, digits, hyphens, or underscores, starting with a letter)"
            )
        if normalized in _RESERVED_BRANCH_TYPES:
            raise ValueError(
                f"tool.rrt.extra_branch_types entry {normalized!r} overlaps with a built-in "
                "branch type and must not be listed here"
            )
        if normalized not in seen_extra:
            seen_extra.add(normalized)
            extra_branch_types_list.append(normalized)
    extra_branch_types = tuple(extra_branch_types_list)

    group_defaults = {
        "release_branch": raw.get("release_branch", DEFAULT_RELEASE_BRANCH),
        "changelog_file": raw.get("changelog_file", DEFAULT_CHANGELOG),
        "lock_command": raw.get("lock_command", _default_lock_command(config_file)),
        "generated_files": raw.get("generated_files", _default_generated_files(config_file)),
    }

    if raw_groups is None:
        version_groups = [
            _load_version_group(
                root,
                config_file=config_file,
                group_name="default",
                raw_group=raw,
                defaults=group_defaults,
            )
        ]
        default_group_name = "default"
    else:
        if not isinstance(raw_groups, list):
            raise ValueError("tool.rrt.version_groups must be an array of tables")
        version_groups = []
        seen_names: set[str] = set()
        for item in raw_groups:
            if not isinstance(item, dict):
                raise ValueError("Each tool.rrt.version_groups entry must be a table")
            name = item.get("name")
            if not isinstance(name, str) or not name:
                raise ValueError("Each tool.rrt.version_groups entry needs a non-empty name")
            if name in seen_names:
                raise ValueError(f"Duplicate version group name {name!r}")
            seen_names.add(name)
            version_groups.append(
                _load_version_group(
                    root,
                    config_file=config_file,
                    group_name=name,
                    raw_group=item,
                    defaults=group_defaults,
                )
            )

        if default_group_name is not None and default_group_name not in seen_names:
            available = ", ".join(sorted(seen_names))
            raise ValueError(
                f"tool.rrt.default_group {default_group_name!r} is not defined. "
                f"Available groups: {available}"
            )

    return RrtConfig(
        root=root,
        config_file=config_file,
        version_groups=version_groups,
        default_group_name=default_group_name,
        extra_branch_types=extra_branch_types,
    )


def _default_lock_command(config_file: Path) -> list[str] | None:
    """Return the default lock command, or None to trigger auto-detection."""
    if config_file.name == "pyproject.toml":
        return list(DEFAULT_LOCK_COMMAND)
    return _AUTO


def _default_generated_files(config_file: Path) -> list[str] | None:
    """Return default generated files, or None to trigger auto-detection."""
    if config_file.name == "pyproject.toml":
        return ["uv.lock"]
    return _AUTO


def _detect_lock_and_files(
    root: Path,
    targets: list[VersionTarget],
) -> tuple[list[str], list[str]]:
    """Infer the lock command and generated lockfiles from targets and the project root.

    Detection priority for JS/TS projects: pnpm > yarn > npm.
    Returns ``(lock_command, generated_files)`` as lists of strings.
    """
    has_package_json = any(t.kind == "package_json" for t in targets)
    if has_package_json:
        if (root / "pnpm-lock.yaml").exists():
            return ["pnpm", "install"], ["pnpm-lock.yaml"]
        if (root / "yarn.lock").exists():
            return ["yarn", "install"], ["yarn.lock"]
        if (root / "package-lock.json").exists():
            return ["npm", "install"], ["package-lock.json"]
        return [], []

    has_poetry = any(t.section == "tool.poetry" for t in targets)
    if has_poetry:
        return ["poetry", "lock"], ["poetry.lock"]

    has_cargo = (root / "Cargo.toml").exists() and any(
        target.path.name == "Cargo.toml" or target.path.suffix == ".rs" for target in targets
    )
    if has_cargo:
        if (root / "Cargo.lock").exists():
            return ["cargo", "update", "--workspace"], ["Cargo.lock"]
        return [], []

    has_go = (root / "go.mod").exists() and any(
        target.path.name == "go.mod" or target.path.suffix == ".go" for target in targets
    )
    if has_go:
        return ["go", "mod", "tidy"], ["go.mod", "go.sum"]

    return [], []


def auto_detect_config(root: Path) -> RrtConfig | None:
    """Create a synthetic RrtConfig by inspecting well-known project files.

    Supports PEP 621 (``[project]``), Poetry (``[tool.poetry]``),
    JS/TS (``package.json``), and Rust (``Cargo.toml``) projects. Returns
    *None* when no recognisable project structure is found.
    """
    pyproject = root / "pyproject.toml"

    if pyproject.exists():
        with pyproject.open("rb") as handle:
            data = tomllib.load(handle)

        project_section = data.get("project", {})
        poetry_section = data.get("tool", {}).get("poetry", {})

        # PEP 621 – requires an explicit version field.
        if isinstance(project_section, dict) and "version" in project_section:
            target = VersionTarget(path=pyproject, kind="pep621", ci_format="pep440")
            group = VersionGroup(
                name="default",
                release_branch=DEFAULT_RELEASE_BRANCH,
                changelog_file=root / DEFAULT_CHANGELOG,
                lock_command=list(DEFAULT_LOCK_COMMAND),
                generated_files=[root / "uv.lock"],
                version_targets=[target],
            )
            return RrtConfig(
                root=root,
                config_file=pyproject,
                version_groups=[group],
                default_group_name="default",
            )

        # Poetry – requires an explicit version field.
        if isinstance(poetry_section, dict) and "version" in poetry_section:
            target = VersionTarget(
                path=pyproject,
                section="tool.poetry",
                field="version",
                ci_format="pep440",
            )
            lock_cmd, gen_files = _detect_lock_and_files(root, [target])
            if not lock_cmd:
                lock_cmd = ["poetry", "lock"]
                gen_files = ["poetry.lock"]
            group = VersionGroup(
                name="default",
                release_branch=DEFAULT_RELEASE_BRANCH,
                changelog_file=root / DEFAULT_CHANGELOG,
                lock_command=lock_cmd,
                generated_files=[root / f for f in gen_files],
                version_targets=[target],
            )
            return RrtConfig(
                root=root,
                config_file=pyproject,
                version_groups=[group],
                default_group_name="default",
            )

    package_json = root / "package.json"
    if package_json.exists():
        target = VersionTarget(path=package_json, kind="package_json", ci_format="semver_pre")
        lock_cmd, gen_files = _detect_lock_and_files(root, [target])
        group = VersionGroup(
            name="default",
            release_branch=DEFAULT_RELEASE_BRANCH,
            changelog_file=root / DEFAULT_CHANGELOG,
            lock_command=lock_cmd,
            generated_files=[root / f for f in gen_files],
            version_targets=[target],
        )
        return RrtConfig(
            root=root,
            config_file=package_json,
            version_groups=[group],
            default_group_name="default",
        )

    cargo_toml = root / "Cargo.toml"
    if cargo_toml.exists():
        with cargo_toml.open("rb") as handle:
            data = tomllib.load(handle)

        package_section = data.get("package", {})
        workspace_package_section = data.get("workspace", {}).get("package", {})

        if isinstance(package_section, dict) and "version" in package_section:
            target = VersionTarget(
                path=cargo_toml,
                section="package",
                field="version",
                ci_format="semver_pre",
            )
        elif isinstance(workspace_package_section, dict) and "version" in workspace_package_section:
            target = VersionTarget(
                path=cargo_toml,
                section="workspace.package",
                field="version",
                ci_format="semver_pre",
            )
        else:
            target = None

        if target is not None:
            lock_cmd, gen_files = _detect_lock_and_files(root, [target])
            group = VersionGroup(
                name="default",
                release_branch=DEFAULT_RELEASE_BRANCH,
                changelog_file=root / DEFAULT_CHANGELOG,
                lock_command=lock_cmd,
                generated_files=[root / f for f in gen_files],
                version_targets=[target],
            )
            return RrtConfig(
                root=root,
                config_file=cargo_toml,
                version_groups=[group],
                default_group_name="default",
            )

    return None


def _load_raw_config(config_file: Path) -> dict[str, object]:
    """Load the raw rrt config object from a supported native config file."""
    if config_file.name == "package.json":
        return _load_package_json_config(config_file)
    if config_file.name == "Cargo.toml":
        return _load_cargo_toml_config(config_file)
    return _load_tool_rrt_toml_config(config_file)


def _load_tool_rrt_toml_config(config_file: Path) -> dict[str, object]:
    """Load [tool.rrt] from a TOML-based config file."""
    with config_file.open("rb") as handle:
        data = tomllib.load(handle)

    tool = data.get("tool", {})
    raw = tool.get("rrt")
    if raw is None:
        raise MissingRrtConfigError(f"Missing [tool.rrt] configuration in {config_file.name}")
    if not isinstance(raw, dict):
        raise ValueError(f"[tool.rrt] in {config_file.name} must be a table")
    return raw


def _load_package_json_config(config_file: Path) -> dict[str, object]:
    """Load the top-level rrt object from package.json."""
    data = json.loads(config_file.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{config_file.name} must contain a top-level object")

    raw = data.get("rrt")
    if raw is None:
        raise MissingRrtConfigError(f"Missing rrt configuration in {config_file.name}")
    if not isinstance(raw, dict):
        raise ValueError(f"rrt in {config_file.name} must be an object")
    return raw


def _load_cargo_toml_config(config_file: Path) -> dict[str, object]:
    """Load [package.metadata.rrt] or [workspace.metadata.rrt] from Cargo.toml."""
    with config_file.open("rb") as handle:
        data = tomllib.load(handle)

    package_rrt = data.get("package", {}).get("metadata", {}).get("rrt")
    if isinstance(package_rrt, dict):
        return package_rrt

    workspace_rrt = data.get("workspace", {}).get("metadata", {}).get("rrt")
    if isinstance(workspace_rrt, dict):
        return workspace_rrt

    if package_rrt is not None or workspace_rrt is not None:
        raise ValueError(
            "[package.metadata.rrt] or [workspace.metadata.rrt] in Cargo.toml must be a table"
        )
    raise MissingRrtConfigError(
        "Missing [package.metadata.rrt] or [workspace.metadata.rrt] configuration in Cargo.toml"
    )


def _load_version_group(
    root: Path,
    *,
    config_file: Path,
    group_name: str,
    raw_group: dict[str, object],
    defaults: dict[str, object],
) -> VersionGroup:
    """Load a version group using top-level defaults where appropriate."""
    raw_targets = raw_group.get("version_targets", [])
    if not isinstance(raw_targets, list) or not raw_targets:
        raise ValueError("Missing [[tool.rrt.version_targets]] configuration")

    targets: list[VersionTarget] = []
    for item in raw_targets:
        if not isinstance(item, dict):
            raise ValueError("Each version target must be a table")
        target = VersionTarget(
            path=root / item["path"],
            kind=item.get("kind"),
            pattern=item.get("pattern"),
            section=item.get("section"),
            field=item.get("field"),
            ci_format=item.get("ci_format"),
        )
        target.validate()
        targets.append(target)

    release_branch = raw_group.get("release_branch", defaults["release_branch"])
    if not isinstance(release_branch, str):
        raise ValueError("release_branch must be a string")

    changelog_value = raw_group.get("changelog_file", defaults["changelog_file"])
    if not isinstance(changelog_value, str):
        raise ValueError("changelog_file must be a string")

    lock_command_raw = raw_group.get("lock_command", defaults["lock_command"])
    auto_gen: list[str] = []
    if lock_command_raw is None:
        # Not explicitly configured – infer from targets and project root.
        auto_lock, auto_gen = _detect_lock_and_files(root, targets)
        lock_command = auto_lock
    elif not isinstance(lock_command_raw, list) or not all(
        isinstance(part, str) for part in lock_command_raw
    ):
        raise ValueError("lock_command must be a list of strings")
    else:
        lock_command = lock_command_raw

    generated_files_raw = raw_group.get("generated_files", defaults["generated_files"])
    if generated_files_raw is None:
        # Not explicitly configured – use whatever auto-detection produced.
        generated_files = auto_gen
    elif not isinstance(generated_files_raw, list) or not all(
        isinstance(path, str) for path in generated_files_raw
    ):
        raise ValueError("generated_files must be a list of strings")
    else:
        generated_files = generated_files_raw

    raw_version_source = raw_group.get("version_source")
    if raw_version_source is not None and not isinstance(raw_version_source, str):
        raise ValueError("version_source must be a string when provided")
    version_source = root / raw_version_source if isinstance(raw_version_source, str) else None
    if version_source is not None and all(target.path != version_source for target in targets):
        raise ValueError(
            f"version_source {raw_version_source!r} for group {group_name!r} does not match any target path"
        )

    return VersionGroup(
        name=group_name,
        release_branch=release_branch,
        changelog_file=root / changelog_value,
        lock_command=lock_command,
        generated_files=[root / path for path in generated_files],
        version_targets=targets,
        version_source=version_source,
    )
