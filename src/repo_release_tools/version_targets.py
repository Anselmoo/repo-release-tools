"""Read and write configured version targets."""

from __future__ import annotations

import json
import re
import tomllib

from pathlib import Path

from repo_release_tools import output
from repo_release_tools.config import RrtConfig, VersionGroup, VersionTarget
from repo_release_tools.versioning import Version


PEP621_PATTERN = re.compile(r'(?ms)(^\[project\]\s.*?^version\s*=\s*")([^"]+)(")')
# Allows optional leading whitespace; uses a backreference (\2) to enforce matching
# opening/closing quote types (both " or both ').
PYTHON_VERSION_PATTERN = re.compile(r'(?m)^(\s*__version__\s*=\s*)(["\'])([^"\']+)\2')
# Allows optional leading whitespace for simple declarations and also matches
# Version inside a const (...) grouped block via the (?ms) (DOTALL) alternation.
GO_VERSION_PATTERN = re.compile(
    r"(?ms)^("
    r"\s*(?:const|var)\s+Version\s*=\s*\""
    r"|"
    r"\s*(?:const|var)\s*\(\s*.*?^\s*Version\s*=\s*\""
    r')([^"]+)(")'
)


def replace_version_in_file(
    target: VersionTarget,
    new_version: str,
    *,
    dry_run: bool,
) -> None:
    """Update a single configured version target."""
    path = target.path
    text = path.read_text(encoding="utf-8")
    current_version = read_version_string(target)

    if current_version == new_version:
        raise RuntimeError(f"{path} version replacement had no effect")

    if target.kind == "pep621":
        updated = PEP621_PATTERN.sub(rf"\g<1>{new_version}\g<3>", text, count=1)
    elif target.kind == "package_json":
        updated = replace_package_json_version(text, new_version)
    elif target.kind == "python_version":
        updated = PYTHON_VERSION_PATTERN.sub(rf"\g<1>\g<2>{new_version}\g<2>", text, count=1)
    elif target.kind == "go_version":
        updated = GO_VERSION_PATTERN.sub(rf"\g<1>{new_version}\g<3>", text, count=1)
    elif target.pattern:
        updated = replace_pattern_version(text, target.pattern, new_version)
    else:
        updated = replace_toml_field(
            text, new_version, section=target.section or "", field=target.field or ""
        )

    if dry_run:
        print(output.dry_run(f'Would update {path}: version = "{new_version}"'))
        return

    path.write_text(updated, encoding="utf-8")
    print(output.ok(f'{path}  {output.GLYPHS.arrow.right}  version = "{new_version}"'))


def read_current_version(config: RrtConfig) -> Version:
    """Read the current version from the first target."""
    return read_group_current_version(config.resolve_group())


def read_group_current_version(group: VersionGroup) -> Version:
    """Read the current version from a version group's canonical source."""
    return Version.parse(read_version_string(group.primary_target()))


def read_group_version_strings(group: VersionGroup) -> list[tuple[VersionTarget, str]]:
    """Read the current version string from every target in a group."""
    return [(target, read_version_string(target)) for target in group.version_targets]


def check_autodetected_version_consistency(config: RrtConfig) -> str | None:
    """Return an error message when auto-detected targets disagree on the version.

    Returns ``None`` when all targets agree or config is not auto-detected.
    """
    if not config.autodetected:
        return None

    group = config.resolve_group()
    versions = read_group_version_strings(group)
    distinct_versions = {version for _, version in versions}
    if len(distinct_versions) <= 1:
        return None

    details = ", ".join(f"{target.path.name}={version}" for target, version in versions)
    return (
        "Auto-detected version files do not agree: "
        f"{details}. Make them consistent, or add rrt config to choose explicit targets/groups."
    )


def read_version_string(target: VersionTarget) -> str:
    """Read the current version string from a target."""
    text = target.path.read_text(encoding="utf-8")

    if target.kind == "pep621":
        match = PEP621_PATTERN.search(text)
        if match is None:
            raise RuntimeError(f"Could not find [project].version in {target.path}")
        return match.group(2)
    if target.kind == "package_json":
        return read_package_json_version(target.path)
    if target.kind == "python_version":
        match = PYTHON_VERSION_PATTERN.search(text)
        if match is None:
            raise RuntimeError(f"Could not find __version__ in {target.path}")
        return match.group(3)
    if target.kind == "go_version":
        match = GO_VERSION_PATTERN.search(text)
        if match is None:
            raise RuntimeError(f"Could not find Version constant/variable in {target.path}")
        return match.group(2)

    if target.pattern:
        match = search_pattern(text, target.pattern)
        if match is None:
            raise RuntimeError(f"Could not match configured pattern in {target.path}")
        return match.group(2)

    return read_toml_field(target.path, section=target.section or "", field=target.field or "")


def replace_toml_field(text: str, new_version: str, *, section: str, field: str) -> str:
    """Replace a TOML field inside a named section."""
    field_pattern = rf'(?ms)(^\[{re.escape(section)}\]\s*$.*?^{re.escape(field)}\s*=\s*")([^"]+)(")'
    pattern = re.compile(field_pattern)
    return pattern.sub(rf"\g<1>{new_version}\g<3>", text, count=1)


def read_toml_field(path: Path, *, section: str, field: str) -> str:
    """Read a field from a TOML file using a dotted section name."""
    with path.open("rb") as handle:
        data = tomllib.load(handle)

    current: object = data
    for part in section.split("."):
        if not isinstance(current, dict) or part not in current:
            raise RuntimeError(f"Missing section [{section}] in {path}")
        current = current[part]

    if not isinstance(current, dict) or field not in current:
        raise RuntimeError(f"Missing field {field!r} in section [{section}] of {path}")
    value = current[field]
    if not isinstance(value, str):
        raise RuntimeError(f"Field {field!r} in [{section}] of {path} is not a string")
    return value


def read_package_json_version(path: Path) -> str:
    """Read the top-level version string from package.json."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"{path} must contain a top-level object")
    if "version" not in data:
        raise RuntimeError(f"Could not find top-level version in {path}")
    version = data["version"]
    if not isinstance(version, str):
        raise RuntimeError(f"Top-level version in {path} is not a string")
    return version


def replace_package_json_version(text: str, new_version: str) -> str:
    """Replace the top-level version field in a package.json document."""
    current = json.loads(text)
    if not isinstance(current, dict):
        raise RuntimeError("package.json must contain a top-level object")
    if "version" not in current:
        raise RuntimeError("Could not find top-level version in package.json")
    if not isinstance(current["version"], str):
        raise RuntimeError("Top-level version in package.json must be a string")

    current["version"] = new_version
    indent = _detect_json_indent(text)
    updated = json.dumps(current, indent=indent, ensure_ascii=False)
    if indent is not None:
        updated += "\n"
    elif text.endswith("\n"):
        updated += "\n"
    return updated


def replace_pattern_version(text: str, pattern: str, new_version: str) -> str:
    """Replace a regex-based version, tolerating legacy TOML double escaping."""
    for compiled in compile_pattern_variants(pattern):
        updated, count = compiled.subn(rf"\g<1>{new_version}\g<3>", text, count=1)
        if count:
            return updated
    raise RuntimeError("Configured pattern did not match the target file")


def search_pattern(text: str, pattern: str) -> re.Match[str] | None:
    """Search a regex pattern and a compatible legacy-escaped variant."""
    for compiled in compile_pattern_variants(pattern):
        if match := compiled.search(text):
            return match
    return None


def compile_pattern_variants(pattern: str) -> list[re.Pattern[str]]:
    """Compile the configured pattern plus a legacy de-escaped compatibility form."""
    variants = [pattern]
    legacy_variant = pattern.replace("\\\\", "\\")
    if legacy_variant != pattern:
        variants.append(legacy_variant)

    compiled: list[re.Pattern[str]] = []
    seen: set[str] = set()
    for candidate in variants:
        if candidate in seen:
            continue
        compiled.append(re.compile(candidate, re.MULTILINE))
        seen.add(candidate)
    return compiled


def _detect_json_indent(text: str) -> int | str | None:
    """Infer indentation style from the original JSON document."""
    for line in text.splitlines():
        stripped = line.lstrip(" \t")
        if not stripped or stripped == line:
            continue
        indent = line[: len(line) - len(stripped)]
        if indent.startswith("\t"):
            return "\t"
        return len(indent)
    return None
