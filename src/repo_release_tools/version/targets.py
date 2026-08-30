"""Read and write configured version targets."""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from repo_release_tools.config import PinTarget, RrtConfig, VersionGroup, VersionTarget
from repo_release_tools.ui import GLYPHS, DryRunPrinter, VerbosePrinter
from repo_release_tools.version import pep440
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


@dataclass(frozen=True)
class _RegexVersionKind:
    """One regex-shaped version target: read group, write template, error label."""

    pattern: re.Pattern[str]
    read_group: int
    write_template: str
    label: str


_REGEX_KINDS: dict[str, _RegexVersionKind] = {
    "pep621": _RegexVersionKind(PEP621_PATTERN, 2, r"\g<1>{version}\g<3>", "[project].version"),
    "python_version": _RegexVersionKind(
        PYTHON_VERSION_PATTERN,
        3,
        r"\g<1>\g<2>{version}\g<2>",
        "__version__",
    ),
    "go_version": _RegexVersionKind(
        GO_VERSION_PATTERN,
        2,
        r"\g<1>{version}\g<3>",
        "Version constant/variable",
    ),
    "cargo_toml": _RegexVersionKind(
        CARGO_TOML_PATTERN,
        2,
        r"\g<1>{version}\g<3>",
        "[package].version",
    ),
    "maven_pom": _RegexVersionKind(MAVEN_POM_PATTERN, 2, r"\g<1>{version}\g<3>", "<version>"),
    "gemspec": _RegexVersionKind(
        GEMSPEC_VERSION_PATTERN,
        3,
        r"\g<1>\g<2>{version}\g<2>",
        ".version",
    ),
    "csproj": _RegexVersionKind(CSPROJ_VERSION_PATTERN, 2, r"\g<1>{version}\g<3>", "<Version>"),
}


@dataclass(frozen=True, slots=True)
class VersionWriteEvent:
    """One version-target write, actual or dry-run-previewed.

    Emitted by :func:`replace_version_in_file` and
    :func:`replace_all_versions_atomic` instead of printing directly — the
    core write primitives stay headless; callers render this event through
    whichever printer matches their surface (CLI, hooks, MCP).
    """

    path: Path
    new_version: str
    dry_run: bool


def _validate_pep440_target(target: VersionTarget, new_version: str) -> None:
    """Reject writes that would put a non-publishable version into a PyPI-facing field.

    Applies to ``kind='pep621'`` targets (the ``[project].version`` field PyPI
    reads) and any target with ``ci_format='pep440'``. SemVer build metadata
    (``+build.N``) and PEP 440's local-version segment (``+local``) look
    similar but are not interchangeable: PyPI and most public indexes reject
    a local-version upload outright, so a version reaching one of these
    targets must be valid, local-segment-free PEP 440 before it reaches disk.
    """
    if target.kind != "pep621" and target.ci_format != "pep440":
        return
    if not pep440.is_valid(new_version):
        raise RuntimeError(
            f"{target.path}: {new_version!r} is not a valid PEP 440 version identifier "
            "(required for kind='pep621' / ci_format='pep440' targets)."
        )
    if pep440.has_local_segment(new_version):
        raise RuntimeError(
            f"{target.path}: {new_version!r} carries a PEP 440 local-version segment "
            "('+...'), which PyPI and other public indexes reject on upload. Remove "
            "the build-metadata suffix before writing to a pep621/pep440 target."
        )


def _compute_updated_content(target: VersionTarget, text: str, new_version: str) -> str:
    """Compute the updated file content for a version target without writing to disk."""
    if target.kind == "package_json":
        return replace_package_json_version(text, new_version)
    if target.kind == "mcp_server_json":
        return replace_mcp_server_json_version(text, new_version)
    if target.kind == "pattern":
        assert target.pattern is not None
        return replace_kind_pattern_version(text, target.pattern, new_version)
    if target.kind is not None and (spec := _REGEX_KINDS.get(target.kind)):
        return spec.pattern.sub(spec.write_template.format(version=new_version), text, count=1)
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
) -> VersionWriteEvent:
    """Update a single configured version target.

    Returns a :class:`VersionWriteEvent` describing the write (or, in
    dry-run mode, the write that would happen). This function performs no
    rendering — callers are responsible for printing.
    """
    path = target.path
    _validate_pep440_target(target, new_version)
    text = path.read_text(encoding="utf-8")
    current_version = read_version_string(target)

    if current_version == new_version:
        raise RuntimeError(f"{path} version replacement had no effect")

    updated = _compute_updated_content(target, text, new_version)

    if dry_run:
        return VersionWriteEvent(path=path, new_version=new_version, dry_run=True)

    path.write_text(updated, encoding="utf-8")
    return VersionWriteEvent(path=path, new_version=new_version, dry_run=False)


def replace_all_versions_atomic(
    targets: list[VersionTarget],
    new_version: str,
    *,
    dry_run: bool,
) -> list[VersionWriteEvent]:
    """Update all version targets atomically: validate all substitutions first, then flush.

    If any target fails to produce a valid substitution, no files are written and
    the original content of any already-written files is restored.

    Returns the list of :class:`VersionWriteEvent` describing every write (or,
    in dry-run mode, every write that would happen), in target order. This
    function performs no rendering — callers are responsible for printing.
    """
    for target in targets:
        _validate_pep440_target(target, new_version)

    if dry_run:
        return [
            VersionWriteEvent(path=target.path, new_version=new_version, dry_run=True)
            for target in targets
        ]

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
    except Exception as exc:
        failed_restores: list[str] = []
        for path, original in written:
            try:
                path.write_text(original, encoding="utf-8")
            except OSError as restore_exc:
                failed_restores.append(f"{path}: {restore_exc}")
        if failed_restores:
            detail = "; ".join(failed_restores)
            raise RuntimeError(
                f"Atomic version write failed ({exc}) and rollback could not restore "
                f"{len(failed_restores)} file(s): {detail}. The working tree is now "
                "inconsistent and must be fixed manually."
            ) from exc
        raise

    return [
        VersionWriteEvent(path=path, new_version=new_version, dry_run=False)
        for path, _, _ in pending
    ]


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

    if target.kind == "package_json":
        return read_package_json_version(target.path)
    if target.kind == "mcp_server_json":
        return read_mcp_server_json_version(target.path)
    if target.kind == "pattern":
        assert target.pattern is not None
        m = search_pattern(text, target.pattern)
        if m is None:
            raise RuntimeError(f"Could not match configured pattern in {target.path}")
        return m.group(1)
    if target.kind is not None and (spec := _REGEX_KINDS.get(target.kind)):
        m = spec.pattern.search(text)
        if m is None:
            raise RuntimeError(f"Could not find {spec.label} in {target.path}")
        return m.group(spec.read_group)

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


def read_mcp_server_json_version(path: Path) -> str:
    """Read the top-level version string from an MCP registry server.json."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"{path} must contain a top-level object")
    if "version" not in data:
        raise RuntimeError(f"Could not find top-level version in {path}")
    version = data["version"]
    if not isinstance(version, str):
        raise RuntimeError(f"Top-level version in {path} is not a string")
    return version


def replace_mcp_server_json_version(text: str, new_version: str) -> str:
    """Replace the version everywhere it appears in an MCP registry server.json.

    Updates the top-level ``version`` field, the ``version`` field of every
    entry in ``packages[]`` that has one (e.g. ``pypi``/``npm`` entries), and
    the trailing ``:<version>`` tag of any ``oci`` package's ``identifier``
    (e.g. ``ghcr.io/org/image:1.2.3``) — the three places a server.json
    documents its own release version, per the MCP Registry server.json
    schema (https://modelcontextprotocol.io/registry).
    """
    current = json.loads(text)
    if not isinstance(current, dict):
        raise RuntimeError("server.json must contain a top-level object")
    if "version" not in current:
        raise RuntimeError("Could not find top-level version in server.json")
    old_version = current["version"]
    if not isinstance(old_version, str):
        raise RuntimeError("Top-level version in server.json must be a string")

    current["version"] = new_version
    for pkg in current.get("packages") or []:
        if not isinstance(pkg, dict):
            continue
        if isinstance(pkg.get("version"), str):
            pkg["version"] = new_version
        identifier = pkg.get("identifier")
        if (
            pkg.get("registryType") == "oci"
            and isinstance(identifier, str)
            and identifier.endswith(f":{old_version}")
        ):
            pkg["identifier"] = identifier[: -len(old_version)] + new_version

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

    def _replacer(m: re.Match[str], _nv: str = new_version) -> str:
        return m.string[m.start(0) : m.start(1)] + _nv + m.string[m.end(1) : m.end(0)]

    for compiled in compile_pattern_variants(pattern):
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
