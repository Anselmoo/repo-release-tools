"""Read and write configured version targets."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from repo_release_tools.config import PinTarget, RrtConfig, VersionGroup, VersionTarget
from repo_release_tools.ui import GLYPHS, DryRunPrinter, VerbosePrinter
from repo_release_tools.version.semver import Version

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
    r')([^"]+)(")',
)
# Rust Cargo.toml: [package] section, version field.
CARGO_TOML_PATTERN = re.compile(r'(?ms)(^\[package\]\s.*?^version\s*=\s*")([^"]+)(")')
# Java Maven pom.xml: first <version> tag (project-level).
MAVEN_POM_PATTERN = re.compile(r"(<version>)([^<]+)(</version>)")
# Ruby gemspec: spec.version = "..." or s.version = "...".
GEMSPEC_VERSION_PATTERN = re.compile(r'(?m)^(\s*\w+\.version\s*=\s*)(["\'])([^"\']+)\2')
# .NET .csproj: <Version>...</Version> tag.
CSPROJ_VERSION_PATTERN = re.compile(r"(<Version>)([^<]+)(</Version>)")


def _compute_updated_content(target: VersionTarget, text: str, new_version: str) -> str:
    """Compute the updated file content for a version target without writing to disk."""
    match target.kind:
        case "pep621":
            return PEP621_PATTERN.sub(rf"\g<1>{new_version}\g<3>", text, count=1)
        case "package_json":
            return replace_package_json_version(text, new_version)
        case "python_version":
            return PYTHON_VERSION_PATTERN.sub(rf"\g<1>\g<2>{new_version}\g<2>", text, count=1)
        case "go_version":
            return GO_VERSION_PATTERN.sub(rf"\g<1>{new_version}\g<3>", text, count=1)
        case "cargo_toml":
            return CARGO_TOML_PATTERN.sub(rf"\g<1>{new_version}\g<3>", text, count=1)
        case "maven_pom":
            return MAVEN_POM_PATTERN.sub(rf"\g<1>{new_version}\g<3>", text, count=1)
        case "gemspec":
            return GEMSPEC_VERSION_PATTERN.sub(rf"\g<1>\g<2>{new_version}\g<2>", text, count=1)
        case "csproj":
            return CSPROJ_VERSION_PATTERN.sub(rf"\g<1>{new_version}\g<3>", text, count=1)
        case "pattern":
            assert target.pattern is not None
            return replace_kind_pattern_version(text, target.pattern, new_version)
    if target.pattern:
        return replace_pattern_version(text, target.pattern, new_version)
    return replace_toml_field(
        text,
        new_version,
        section=target.section or "",
        field=target.field or "",
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

    updated = _compute_updated_content(target, text, new_version)

    if dry_run:
        p = DryRunPrinter(dry_run=True)
        p.would_write(str(path), detail=f'version = "{new_version}"')
        return

    path.write_text(updated, encoding="utf-8")
    msg = f'{path}  {GLYPHS.arrow.right}  version = "{new_version}"'
    p = VerbosePrinter()
    p.ok(msg)


def replace_all_versions_atomic(
    targets: list[VersionTarget],
    new_version: str,
    *,
    dry_run: bool,
) -> None:
    """Update all version targets atomically: validate all substitutions first, then flush.

    If any target fails to produce a valid substitution, no files are written and
    the original content of any already-written files is restored.
    """
    if dry_run:
        for target in targets:
            p = DryRunPrinter(dry_run=True)
            p.would_write(str(target.path), detail=f'version = "{new_version}"')
        return

    # Phase 1: compute all updates in memory before touching disk.
    pending: list[tuple[Path, str, str]] = []  # (path, old_content, new_content)
    for target in targets:
        path = target.path
        text = path.read_text(encoding="utf-8")
        current_version = read_version_string(target)
        if current_version == new_version:
            raise RuntimeError(f"{path} version replacement had no effect")
        updated = _compute_updated_content(target, text, new_version)
        pending.append((path, text, updated))

    # Phase 2: flush all files; roll back on any failure.
    written: list[tuple[Path, str]] = []
    try:
        for path, _old, new_content in pending:
            path.write_text(new_content, encoding="utf-8")
            written.append((path, _old))
    except Exception:
        for path, original in written:
            try:
                path.write_text(original, encoding="utf-8")
            except OSError:
                pass
        raise

    p = VerbosePrinter()
    for path, _, _ in pending:
        p.ok(f'{path}  {GLYPHS.arrow.right}  version = "{new_version}"')


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

    match target.kind:
        case "pep621":
            m = PEP621_PATTERN.search(text)
            if m is None:
                raise RuntimeError(f"Could not find [project].version in {target.path}")
            return m.group(2)
        case "package_json":
            return read_package_json_version(target.path)
        case "python_version":
            m = PYTHON_VERSION_PATTERN.search(text)
            if m is None:
                raise RuntimeError(f"Could not find __version__ in {target.path}")
            return m.group(3)
        case "go_version":
            m = GO_VERSION_PATTERN.search(text)
            if m is None:
                raise RuntimeError(f"Could not find Version constant/variable in {target.path}")
            return m.group(2)
        case "cargo_toml":
            m = CARGO_TOML_PATTERN.search(text)
            if m is None:
                raise RuntimeError(f"Could not find [package].version in {target.path}")
            return m.group(2)
        case "maven_pom":
            m = MAVEN_POM_PATTERN.search(text)
            if m is None:
                raise RuntimeError(f"Could not find <version> in {target.path}")
            return m.group(2)
        case "gemspec":
            m = GEMSPEC_VERSION_PATTERN.search(text)
            if m is None:
                raise RuntimeError(f"Could not find .version in {target.path}")
            return m.group(3)
        case "csproj":
            m = CSPROJ_VERSION_PATTERN.search(text)
            if m is None:
                raise RuntimeError(f"Could not find <Version> in {target.path}")
            return m.group(2)
        case "pattern":
            assert target.pattern is not None
            m = search_pattern(text, target.pattern)
            if m is None:
                raise RuntimeError(f"Could not match configured pattern in {target.path}")
            return m.group(1)

    if target.pattern:
        m = search_pattern(text, target.pattern)
        if m is None:
            raise RuntimeError(f"Could not match configured pattern in {target.path}")
        return m.group(2)

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
    if indent is not None or text.endswith("\n"):
        updated += "\n"
    return updated


def replace_pattern_version(text: str, pattern: str, new_version: str, *, count: int = 1) -> str:
    """Replace a regex-based version, tolerating legacy TOML double escaping.

    *count* defaults to 1 (replace only the first occurrence).  Pass ``count=0``
    for unlimited replacements, i.e. all occurrences (used for pin-target substitutions).
    """
    for compiled in compile_pattern_variants(pattern):
        updated, n = compiled.subn(rf"\g<1>{new_version}\g<3>", text, count=count)
        if n:
            return updated
    raise RuntimeError("Configured pattern did not match the target file")


def replace_kind_pattern_version(text: str, pattern: str, new_version: str) -> str:
    """Replace the version string captured in group 1 of a kind='pattern' regex."""
    for compiled in compile_pattern_variants(pattern):

        def _replacer(m: re.Match[str], _nv: str = new_version) -> str:
            return m.string[m.start(0) : m.start(1)] + _nv + m.string[m.end(1) : m.end(0)]

        updated, n = compiled.subn(_replacer, text, count=1)
        if n:
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
        if candidate not in seen:
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


def replace_pin_in_file(
    target: PinTarget,
    new_version: str,
    *,
    dry_run: bool,
    pin_target_missing: str = "error",
) -> None:
    """Update a single doc/CI pin reference to ``new_version``.

    *pin_target_missing* controls what happens when the pattern does not match:
    - ``"warn"`` (legacy): print a warning and continue without error.
    - ``"error"`` (default): raise ``RuntimeError``.
    """
    path = target.path
    text = path.read_text(encoding="utf-8")

    match = search_pattern(text, target.pattern)
    if match is None:
        p = DryRunPrinter(dry_run=dry_run)
        if pin_target_missing == "warn":
            p.warn(f"Pin pattern did not match in {path} — skipping")
            return
        raise RuntimeError(
            f"Pin pattern did not match in {path}. "
            'Set pin_target_missing = "warn" in [tool.rrt] to downgrade to a warning.'
        )

    current = match.group(2)
    if current == new_version:
        p = DryRunPrinter(dry_run=dry_run)
        p.line(f"{path}  already at {new_version}", ok=None)
        return

    updated = replace_pattern_version(text, target.pattern, new_version, count=0)

    if dry_run:
        p = DryRunPrinter(dry_run=True)
        p.would_write(str(path), detail=f'pin = "{new_version}"')
        return

    path.write_text(updated, encoding="utf-8")
    msg = f'{path}  {GLYPHS.arrow.right}  pin = "{new_version}"'
    p = VerbosePrinter()
    p.ok(msg)
