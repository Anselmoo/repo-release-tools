"""Configuration loading for rrt."""

from __future__ import annotations

import re
import tomllib

from dataclasses import dataclass
from pathlib import Path


DEFAULT_RELEASE_BRANCH = "release/v{version}"
DEFAULT_CHANGELOG = "CHANGELOG.md"
DEFAULT_LOCK_COMMAND = ["uv", "lock", "-U"]
DEFAULT_GENERIC_LOCK_COMMAND: list[str] = []

CONFIG_FILE_CANDIDATES = ("pyproject.toml", ".rrt.toml", ".config/rrt.toml")

VALID_TARGET_KINDS = frozenset({"pep621", "package_json"})

VALID_CI_FORMATS = frozenset({"pep440", "semver_pre"})


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
            raise ValueError(
                "Each version target must define either "
                "kind='pep621', kind='package_json', pattern, or section+field"
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


def load_config(root: Path) -> RrtConfig:
    """Load [tool.rrt] from the first supported config file in the repository root."""
    missing_tool_rrt: list[Path] = []
    for config_file in iter_config_files(root):
        try:
            return load_config_from_path(root, config_file)
        except ValueError as exc:
            if not _is_missing_tool_rrt_error(exc):
                raise
            missing_tool_rrt.append(config_file)

    if missing_tool_rrt:
        checked = ", ".join(str(path.relative_to(root)) for path in missing_tool_rrt)
        raise ValueError(f"Missing [tool.rrt] configuration in supported config files: {checked}")

    expected = ", ".join(CONFIG_FILE_CANDIDATES)
    raise FileNotFoundError(f"Missing supported config file in {root} (checked: {expected})")


def find_config_file(root: Path) -> Path:
    """Find the first supported config file that contains [tool.rrt]."""
    return load_config(root).config_file


def iter_config_files(root: Path) -> list[Path]:
    """Return supported config files that exist in discovery order."""
    return [root / candidate for candidate in CONFIG_FILE_CANDIDATES if (root / candidate).exists()]


def load_config_from_path(root: Path, config_file: Path) -> RrtConfig:
    """Load [tool.rrt] from a specific config file."""
    with config_file.open("rb") as handle:
        data = tomllib.load(handle)

    tool = data.get("tool", {})
    raw = tool.get("rrt")
    if raw is None:
        raise ValueError(f"Missing [tool.rrt] configuration in {config_file.name}")

    raw_groups = raw.get("version_groups")
    has_flat_targets = "version_targets" in raw
    if raw_groups is not None and has_flat_targets:
        raise ValueError("Use either flat version_targets or version_groups, not both")

    default_group_name = raw.get("default_group")
    if default_group_name is not None and not isinstance(default_group_name, str):
        raise ValueError("tool.rrt.default_group must be a string")

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
    )


def _default_lock_command(config_file: Path) -> list[str]:
    """Return the default lock command for a config file location."""
    if config_file.name == "pyproject.toml":
        return list(DEFAULT_LOCK_COMMAND)
    return list(DEFAULT_GENERIC_LOCK_COMMAND)


def _default_generated_files(config_file: Path) -> list[str]:
    """Return default generated files for a config file location."""
    if config_file.name == "pyproject.toml":
        return ["uv.lock"]
    return []


def _is_missing_tool_rrt_error(exc: ValueError) -> bool:
    """Return whether a config-loading error means [tool.rrt] was absent."""
    return str(exc).startswith("Missing [tool.rrt] configuration in ")


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

    lock_command = raw_group.get("lock_command", defaults["lock_command"])
    if not isinstance(lock_command, list) or not all(
        isinstance(part, str) for part in lock_command
    ):
        raise ValueError("lock_command must be a list of strings")

    generated_files = raw_group.get("generated_files", defaults["generated_files"])
    if not isinstance(generated_files, list) or not all(
        isinstance(path, str) for path in generated_files
    ):
        raise ValueError("generated_files must be a list of strings")

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
