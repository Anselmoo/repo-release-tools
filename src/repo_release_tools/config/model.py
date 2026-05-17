"""Configuration loading for rrt."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from textwrap import dedent

DEFAULT_RELEASE_BRANCH = "release/v{version}"
DEFAULT_CHANGELOG = "CHANGELOG.md"
DEFAULT_CHANGELOG_WORKFLOW = "incremental"
DEFAULT_LOCK_COMMAND = ["uv", "lock", "-U"]
DEFAULT_GENERIC_LOCK_COMMAND: list[str] = []
VALID_CHANGELOG_WORKFLOWS = frozenset({"incremental", "squash"})

# Well-known changelog filenames probed in order when autodetecting.
CHANGELOG_CANDIDATES = (
    "CHANGELOG.md",
    "CHANGELOG.rst",
    "CHANGELOG.txt",
    "CHANGELOG",
    "changelog.md",
    "changelog.rst",
    "CHANGES.md",
    "CHANGES.rst",
    "CHANGES",
)

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

VALID_TARGET_KINDS = frozenset(
    {
        "pep621",
        "package_json",
        "python_version",
        "go_version",
        "cargo_toml",
        "maven_pom",
        "gemspec",
        "csproj",
    }
)

# Directory names to skip when scanning for Python __version__ files.
_IGNORE_DIR_NAMES: frozenset[str] = frozenset(
    {
        ".venv",
        "venv",
        "env",
        ".env",
        "node_modules",
        "__pycache__",
        ".git",
        ".tox",
        "dist",
        "build",
    },
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
    },
)

# Valid identifier pattern for extra_branch_types entries (after normalization).
# Must start with a lowercase letter; remaining chars may be lowercase letters,
# digits, hyphens, or underscores.  Empty strings and entries starting with a
# digit or special character are rejected.
_BRANCH_TYPE_IDENTIFIER_RE = re.compile(r"[a-z][a-z0-9_-]*")

VALID_CI_FORMATS = frozenset({"pep440", "semver_pre"})
VALID_FOLDER_MODES = frozenset({"strict", "warn", "off"})
VALID_TEMPLATE_STRICTNESS = frozenset({"strict", "loose"})
VALID_BADGE_STYLES = frozenset({"svg", "shields", "text"})
VALID_BADGE_VARIANTS = frozenset({"color", "dark", "light"})

AUTODETECTED_CONFIG_BASENAME = ".rrt.autodetected.toml"
DEFAULT_INIT_CONFIG = ".rrt.toml"

PYTHON_TOOL_RRT_EXAMPLE = dedent(
    """\
    [tool.rrt]
    release_branch = "release/v{version}"

    [[tool.rrt.version_targets]]
    path = "pyproject.toml"
    kind = "pep621"
    """,
).strip()

NODE_TOOL_RRT_EXAMPLE = dedent(
    """\
    [tool.rrt]
    release_branch = "release/v{version}"

    [[tool.rrt.version_targets]]
    path = "package.json"
    kind = "package_json"
    ci_format = "semver_pre"
    """,
).strip()

RUST_TOOL_RRT_EXAMPLE = dedent(
    """\
    [package.metadata.rrt]
    release_branch = "release/v{version}"

    [[package.metadata.rrt.version_targets]]
    path = "Cargo.toml"
    section = "package"
    field = "version"
    ci_format = "semver_pre"
    """,
).strip()

GO_TOOL_RRT_EXAMPLE = dedent(
    """\
    [tool.rrt]
    release_branch = "release/v{version}"

    [[tool.rrt.version_targets]]
    path = "internal/version/version.go"
    kind = "go_version"
    """,
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
    """,
).strip()


def find_changelog_file(root: Path) -> str:
    """Return the name of the first existing changelog file under *root*.

    Searches ``CHANGELOG_CANDIDATES`` in order.  Falls back to
    ``DEFAULT_CHANGELOG`` when none of the candidates are found.
    """
    return next(
        (name for name in CHANGELOG_CANDIDATES if (root / name).exists()), DEFAULT_CHANGELOG
    )


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
                f"Each version target must define either {kind_opts}, pattern, or section+field",
            )
        if configured_modes > 1:
            raise ValueError(
                "Version target replacement selectors are mutually exclusive: "
                "use exactly one of kind, pattern, or section+field",
            )

        if has_pattern:
            assert self.pattern is not None
            re.compile(self.pattern)
        if self.ci_format is not None:
            if not isinstance(self.ci_format, str):
                raise ValueError(
                    f"ci_format must be a string equal to 'pep440' or 'semver_pre', "
                    f"got {type(self.ci_format).__name__}: {self.ci_format!r}",
                )
            if self.ci_format not in VALID_CI_FORMATS:
                raise ValueError(
                    f"ci_format must be 'pep440' or 'semver_pre', got {self.ci_format!r}",
                )


@dataclass(frozen=True)
class PinTarget:
    r"""A single doc/CI pin target updated by 'rrt bump'.

    Unlike ``VersionTarget``, ``PinTarget`` is write-only and does not
    participate in version consistency checks.  Use it to keep version pins
    in documentation and CI configs (e.g. ``@v1.2.3`` or ``rev: v1.2.3``)
    in sync with every release.

    The ``pattern`` must follow the 3-group convention used by
    ``VersionTarget`` custom patterns:
    - Group 1: constant prefix (e.g. ``(Anselmoo/repo-release-tools@v)``)
    - Group 2: bare semver being replaced (e.g. ``(\\d+\\.\\d+\\.\\d+)``)
    - Group 3: constant suffix (e.g. ``()``)
    """

    path: Path
    pattern: str

    def validate(self) -> None:
        """Validate the pin target."""
        try:
            compiled = re.compile(self.pattern)
        except re.error as exc:
            raise ValueError(f"pin_targets pattern is not a valid regex: {exc}") from exc
        if compiled.groups != 3:
            raise ValueError(
                "pin_targets pattern must have exactly 3 capture groups (prefix, version, suffix)",
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
    pin_targets: list[PinTarget] = field(default_factory=list)
    changelog_workflow: str = DEFAULT_CHANGELOG_WORKFLOW

    def primary_target(self) -> VersionTarget:
        """Return the target used as the canonical version source."""
        if self.version_source is None:
            return self.version_targets[0]

        for target in self.version_targets:
            if target.path == self.version_source:
                return target

        raise ValueError(
            f"Group {self.name!r} version_source {self.version_source} does not match any target",
        )


@dataclass(frozen=True)
class EolOverride:
    """A per-cycle EOL date override for a specific language."""

    language: str
    cycle: str
    eol: str  # YYYY-MM-DD


@dataclass(frozen=True)
class EolConfig:
    """EOL lifecycle tracking configuration under [tool.rrt.eol]."""

    languages: tuple[str, ...] = ("python",)
    warn_days: int = 180
    error_days: int = 0
    fetch_live: bool = False
    allow_eol: bool = False
    overrides: tuple[EolOverride, ...] = ()


@dataclass(frozen=True)
class SharedBlock:
    """A single anchor-injected shared block stamped across doc target files."""

    anchor_id: str
    content: str  # inline Markdown/HTML content from pyproject.toml or .rrt.toml
    position: str = "prepend"
    before_blank_lines: int = 0
    after_blank_lines: int = 1
    targets: tuple[str, ...] = ()  # glob patterns relative to the project root

    def validate(self) -> None:
        """Validate the shared block configuration."""
        if not self.anchor_id or not self.anchor_id.strip():
            raise ValueError("shared_blocks anchor_id must be a non-empty string")
        if self.content is None:
            raise ValueError(f"shared_blocks entry {self.anchor_id!r} must define 'content'")
        if self.position not in {"prepend", "append"}:
            raise ValueError(
                f"shared_blocks entry {self.anchor_id!r} position must be 'prepend' or 'append'",
            )
        if self.before_blank_lines < 0:
            raise ValueError(
                f"shared_blocks entry {self.anchor_id!r} before_blank_lines must be >= 0",
            )
        if self.after_blank_lines < 0:
            raise ValueError(
                f"shared_blocks entry {self.anchor_id!r} after_blank_lines must be >= 0",
            )
        if not self.targets:
            raise ValueError(
                f"shared_blocks entry {self.anchor_id!r} must define at least one target glob",
            )


@dataclass(frozen=True)
class DocsConfig:
    """Documentation tree configuration under [tool.rrt.docs]."""

    mirror_src_tree: bool = False
    docs_dir: str = "docs"
    src_dir: str = "."
    stubs: tuple[str, ...] = ()
    # Multi-language doc extraction settings
    extraction_mode: str = "explicit"  # "explicit" | "implicit" | "both"
    languages: tuple[str, ...] = ("python",)
    lock_file: str = ".rrt/docs.lock.toml"
    formats: tuple[str, ...] = ("md",)
    source_repo_url: str | None = None
    source_ref: str | None = None
    source_url_template: str | None = None
    shared_blocks: tuple[SharedBlock, ...] = ()
    # Platform badge / source-anchor settings
    platform: str | None = None  # auto-detected from source_repo_url when None
    badge_style: str = "svg"  # "svg" | "shields" | "text"
    badge_assets_dir: str = "docs/assets/badges"
    badge_variant: str = "color"  # "color" | "dark" | "light"
    source_link_badge: bool = False  # prefix per-file source links with a badge
    # suggest settings
    suggest_roots: tuple[str, ...] = ()
    suggest_exempt: tuple[str, ...] = ()
    suggest_min_chars: int | None = None

    def validate(self) -> None:
        """Validate badge_style and badge_variant values."""
        if self.badge_style not in VALID_BADGE_STYLES:
            allowed = ", ".join(sorted(VALID_BADGE_STYLES))
            raise ValueError(
                f"docs badge_style must be one of {allowed}, got {self.badge_style!r}",
            )
        if self.badge_variant not in VALID_BADGE_VARIANTS:
            allowed = ", ".join(sorted(VALID_BADGE_VARIANTS))
            raise ValueError(
                f"docs badge_variant must be one of {allowed}, got {self.badge_variant!r}",
            )


def _validate_relative_folder_path(path: str, *, label: str) -> None:
    """Validate that *path* is a repository-relative folder contract path."""
    if not path or not path.strip():
        raise ValueError(f"{label} must be a non-empty string")

    normalized = Path(path)
    if normalized.is_absolute():
        raise ValueError(f"{label} must be a relative path, got {path!r}")
    if any(part == ".." for part in normalized.parts):
        raise ValueError(f"{label} must not escape the repository root, got {path!r}")


@dataclass(frozen=True)
class FolderScaffoldFile:
    """A file emitted by a folder scaffold template."""

    path: str
    content: str = ""
    executable: bool = False

    def validate(self) -> None:
        """Validate the scaffold file entry."""
        _validate_relative_folder_path(self.path, label="folder scaffold file path")
        if not isinstance(self.content, str):
            raise ValueError(f"folder scaffold file {self.path!r} content must be a string")


@dataclass(frozen=True)
class FolderTemplate:
    """A reusable folder supervision and scaffold template."""

    name: str
    description: str = ""
    strictness: str = "strict"
    exact: bool = False
    required_files: tuple[str, ...] = ()
    required_dirs: tuple[str, ...] = ()
    allowed_files: tuple[str, ...] = ()
    allowed_dirs: tuple[str, ...] = ()
    allow_patterns: tuple[str, ...] = ()
    scaffold_dirs: tuple[str, ...] = ()
    scaffold_files: tuple[FolderScaffoldFile, ...] = ()

    def validate(self) -> None:
        """Validate the folder template."""
        if not self.name or not self.name.strip():
            raise ValueError("folder template name must be a non-empty string")
        if self.strictness not in VALID_TEMPLATE_STRICTNESS:
            allowed = ", ".join(sorted(VALID_TEMPLATE_STRICTNESS))
            raise ValueError(
                f"folder template {self.name!r} strictness must be one of {allowed}, got {self.strictness!r}",
            )

        for label, entries in (
            ("required_files", self.required_files),
            ("required_dirs", self.required_dirs),
            ("allowed_files", self.allowed_files),
            ("allowed_dirs", self.allowed_dirs),
            ("scaffold_dirs", self.scaffold_dirs),
        ):
            for entry in entries:
                _validate_relative_folder_path(
                    entry,
                    label=f"folder template {self.name!r} {label}",
                )

        for scaffold_file in self.scaffold_files:
            scaffold_file.validate()


@dataclass(frozen=True)
class FolderRule:
    """A path-scoped folder supervision rule."""

    name: str
    selector: str = "."
    mode: str | None = None
    templates: tuple[str, ...] = ()
    exact: bool | None = None
    required_files: tuple[str, ...] = ()
    required_dirs: tuple[str, ...] = ()
    allowed_files: tuple[str, ...] = ()
    allowed_dirs: tuple[str, ...] = ()
    allow_patterns: tuple[str, ...] = ()
    scaffold_dirs: tuple[str, ...] = ()
    scaffold_files: tuple[FolderScaffoldFile, ...] = ()

    def validate(self) -> None:
        """Validate the rule shape."""
        if not self.name or not self.name.strip():
            raise ValueError("folder rule name must be a non-empty string")
        if not self.selector or not self.selector.strip():
            raise ValueError(f"folder rule {self.name!r} selector must be a non-empty string")
        if self.mode is not None and self.mode not in VALID_FOLDER_MODES:
            allowed = ", ".join(sorted(VALID_FOLDER_MODES))
            raise ValueError(
                f"folder rule {self.name!r} mode must be one of {allowed}, got {self.mode!r}",
            )

        for label, entries in (
            ("required_files", self.required_files),
            ("required_dirs", self.required_dirs),
            ("allowed_files", self.allowed_files),
            ("allowed_dirs", self.allowed_dirs),
            ("scaffold_dirs", self.scaffold_dirs),
        ):
            for entry in entries:
                _validate_relative_folder_path(entry, label=f"folder rule {self.name!r} {label}")

        for scaffold_file in self.scaffold_files:
            scaffold_file.validate()


@dataclass(frozen=True)
class FolderPolicyConfig:
    """Folder supervision policy under ``[tool.rrt.folders]``."""

    mode: str = "strict"
    templates: tuple[FolderTemplate, ...] = ()
    rules: tuple[FolderRule, ...] = ()

    def validate(self) -> None:
        """Validate the folder policy."""
        if self.mode not in VALID_FOLDER_MODES:
            allowed = ", ".join(sorted(VALID_FOLDER_MODES))
            raise ValueError(f"tool.rrt.folders.mode must be one of {allowed}, got {self.mode!r}")

        seen_template_names: set[str] = set()
        for template in self.templates:
            template.validate()
            if template.name in seen_template_names:
                raise ValueError(f"Duplicate folder template name {template.name!r}")
            seen_template_names.add(template.name)

        seen_rule_names: set[str] = set()
        for rule in self.rules:
            rule.validate()
            if rule.name in seen_rule_names:
                raise ValueError(f"Duplicate folder rule name {rule.name!r}")
            seen_rule_names.add(rule.name)


VALID_PIN_TARGET_MISSING = frozenset({"warn", "error"})


@dataclass(frozen=True)
class RrtConfig:
    """Loaded rrt configuration."""

    root: Path
    config_file: Path
    version_groups: list[VersionGroup]
    default_group_name: str | None = None
    autodetected: bool = False
    extra_branch_types: tuple[str, ...] = ()
    global_pin_targets: list[PinTarget] = field(default_factory=list)
    eol: EolConfig | None = None
    docs: DocsConfig | None = None
    folders: FolderPolicyConfig | None = None
    pin_target_missing: str = "error"
    extra_commit_types: tuple[str, ...] = ()
    extra_section_map: dict[str, str] = field(default_factory=dict)

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
            f"(available: {available}).",
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

    @property
    def changelog_workflow(self) -> str:
        """Backward-compatible access to the default group's changelog workflow."""
        return self.resolve_group().changelog_workflow


class MissingRrtConfigError(ValueError):
    """Raised when a supported config file exists but does not contain rrt config."""


def is_missing_tool_rrt_error(exc: Exception) -> bool:
    """Return whether *exc* means supported config files exist without rrt config."""
    if isinstance(exc, MissingRrtConfigError):
        return True

    message = str(exc)
    return message.startswith("Missing rrt configuration in supported config files:")
