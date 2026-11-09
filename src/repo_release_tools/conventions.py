"""Commit and branch type definitions shared by hooks, changelog, bump and creators.

The built-in Conventional Commit and branch types are typed definitions here.
A repository adds its own types, or overrides fields of a built-in one, with
``[[tool.rrt.commit_types]]`` and ``[[tool.rrt.branch_types]]`` tables; the
flat ``extra_commit_types``, ``extra_branch_types`` and ``extra_section_map``
keys stay as shorthand. Every consumer reads one :class:`TypeRegistry`, so the
validators, the generators, changelog rendering and bump inference agree on
the same set of types.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Literal, Protocol, cast

BumpLevel = Literal["none", "patch", "minor"]
SlugPolicy = Literal["kebab", "any"]
BranchKind = Literal["conventional", "agent", "bot", "custom"]

BUMP_LEVELS: tuple[BumpLevel, ...] = ("none", "patch", "minor")
SLUG_POLICIES: tuple[SlugPolicy, ...] = ("kebab", "any")

BREAKING_SECTION = "Breaking Changes"
MAINTENANCE_SECTION = "Maintenance"
# Built-in sections in render order; user-defined sections follow them and
# precede Maintenance, which always comes last.
BASE_SECTION_ORDER: tuple[str, ...] = (
    BREAKING_SECTION,
    "Added",
    "Fixed",
    "Changed",
    "Documentation",
)

# Valid type identifier after normalization: starts with a lowercase letter,
# then lowercase letters, digits, hyphens or underscores.
TYPE_IDENTIFIER_RE = re.compile(r"[a-z][a-z0-9_-]*")

MAGIC_BRANCH_TYPES: tuple[str, ...] = ("claude", "codex", "copilot")
BOT_BRANCH_TYPES: tuple[str, ...] = ("dependabot", "renovate")

_COMMIT_TABLE = "tool.rrt.commit_types"
_BRANCH_TABLE = "tool.rrt.branch_types"
_COMMIT_KEYS = frozenset({"name", "description", "changelog_section", "changelog_required", "bump"})
_BRANCH_KEYS = frozenset({"name", "description", "commit_types", "slug", "changelog_required"})


def default_changelog_required(section: str | None) -> bool:
    """Return the default changelog policy for a type rendered into *section*."""
    return section is not None and section != MAINTENANCE_SECTION


@dataclass(frozen=True)
class CommitType:
    """One Conventional Commit type and the policy attached to it."""

    name: str
    description: str
    changelog_section: str | None = None
    changelog_required: bool = False
    bump: BumpLevel = "patch"


@dataclass(frozen=True)
class BranchType:
    """One branch type prefix (``<type>/<slug>``) and the policy attached to it."""

    name: str
    description: str
    commit_types: tuple[str, ...] = ()
    slug: SlugPolicy = "kebab"
    changelog_required: bool = False
    kind: BranchKind = "custom"


class _NamedType(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...


def _builtin_commit(
    name: str, description: str, section: str, bump: BumpLevel = "patch"
) -> CommitType:
    return CommitType(
        name=name,
        description=description,
        changelog_section=section,
        changelog_required=default_changelog_required(section),
        bump=bump,
    )


BUILTIN_COMMIT_TYPES: tuple[CommitType, ...] = (
    _builtin_commit("feat", "A new feature", "Added", "minor"),
    _builtin_commit("fix", "A bug fix", "Fixed"),
    _builtin_commit("chore", "Housekeeping that changes no shipped behaviour", MAINTENANCE_SECTION),
    _builtin_commit("docs", "Documentation only", "Documentation"),
    _builtin_commit("refactor", "Restructure code without changing behaviour", "Changed"),
    _builtin_commit("test", "Add or correct tests", MAINTENANCE_SECTION),
    _builtin_commit("ci", "CI configuration and scripts", MAINTENANCE_SECTION),
    _builtin_commit("perf", "A performance improvement", "Changed"),
    _builtin_commit("style", "Formatting only, no change in meaning", "Changed"),
    _builtin_commit("build", "Build system or packaging", MAINTENANCE_SECTION),
    _builtin_commit("deps", "Dependency updates", MAINTENANCE_SECTION),
)

# Conventional types that are also branch prefixes (``deps`` is commit-only).
CONVENTIONAL_BRANCH_TYPE_NAMES: tuple[str, ...] = tuple(
    ct.name for ct in BUILTIN_COMMIT_TYPES if ct.name != "deps"
)

BUILTIN_BRANCH_TYPES: tuple[BranchType, ...] = (
    *(
        BranchType(
            name=ct.name,
            description=ct.description,
            changelog_required=ct.changelog_required,
            kind="conventional",
        )
        for ct in BUILTIN_COMMIT_TYPES
        if ct.name in CONVENTIONAL_BRANCH_TYPE_NAMES
    ),
    BranchType(name="claude", description="AI agent branch (Claude)", kind="agent"),
    BranchType(name="codex", description="AI agent branch (Codex)", kind="agent"),
    BranchType(name="copilot", description="AI agent branch (Copilot)", kind="agent"),
    BranchType(name="dependabot", description="Dependabot update", slug="any", kind="bot"),
    BranchType(name="renovate", description="Renovate update", slug="any", kind="bot"),
)


@dataclass(frozen=True)
class TypeRegistry:
    """Resolved commit and branch types for one repository."""

    commit_types: tuple[CommitType, ...] = BUILTIN_COMMIT_TYPES
    branch_types: tuple[BranchType, ...] = BUILTIN_BRANCH_TYPES

    @property
    def commit_type_names(self) -> tuple[str, ...]:
        """Return all commit type names in definition order."""
        return tuple(ct.name for ct in self.commit_types)

    @property
    def branch_type_names(self) -> tuple[str, ...]:
        """Return all branch type names in definition order."""
        return tuple(bt.name for bt in self.branch_types)

    def commit_type(self, name: str) -> CommitType | None:
        """Return the commit type called *name* (case-insensitive), if any."""
        lowered = name.lower()
        return next((ct for ct in self.commit_types if ct.name == lowered), None)

    def branch_type(self, name: str) -> BranchType | None:
        """Return the branch type called *name* (case-insensitive), if any."""
        lowered = name.lower()
        return next((bt for bt in self.branch_types if bt.name == lowered), None)

    def section_for(self, name: str, *, breaking: bool = False) -> str | None:
        """Return the changelog section a commit of type *name* lands in."""
        if breaking:
            return BREAKING_SECTION
        ct = self.commit_type(name)
        return ct.changelog_section if ct is not None else None

    def requires_changelog(self, name: str, *, breaking: bool = False) -> bool:
        """Return whether a commit of type *name* must update the changelog."""
        if breaking:
            return True
        ct = self.commit_type(name)
        return ct is not None and ct.changelog_required

    def bump_for(self, name: str) -> BumpLevel:
        """Return the bump impact of a commit of type *name* (``none`` if unknown)."""
        ct = self.commit_type(name)
        return ct.bump if ct is not None else "none"

    @property
    def section_order(self) -> tuple[str, ...]:
        """Return changelog sections in render order."""
        custom: list[str] = []
        for ct in self.commit_types:
            section = ct.changelog_section
            if (
                section is not None
                and section not in BASE_SECTION_ORDER
                and section != MAINTENANCE_SECTION
                and section not in custom
            ):
                custom.append(section)
        return (*BASE_SECTION_ORDER, *custom, MAINTENANCE_SECTION)

    def branch_requires_changelog(self, name: str) -> bool:
        """Return whether commits on a ``<name>/...`` branch must update the changelog."""
        bt = self.branch_type(name)
        return bt is not None and bt.changelog_required

    def allowed_commit_types_on(self, branch_name: str) -> tuple[str, ...]:
        """Return the commit types *branch_name* restricts to (empty means any)."""
        if "/" not in branch_name:
            return ()
        bt = self.branch_type(branch_name.split("/", 1)[0])
        return bt.commit_types if bt is not None else ()

    def inferred_commit_type(self, branch_type_name: str) -> str | None:
        """Return the commit type a ``<branch_type_name>/...`` branch implies, if unambiguous."""
        bt = self.branch_type(branch_type_name)
        if bt is None or bt.kind in ("agent", "bot"):
            return None
        if bt.commit_types:
            if bt.name in bt.commit_types:
                return bt.name
            return bt.commit_types[0] if len(bt.commit_types) == 1 else None
        return bt.name if self.commit_type(bt.name) is not None else None

    def suggested_commit_type(self, branch_type_name: str) -> str:
        """Return the commit type to suggest for a new ``<branch_type_name>/...`` branch.

        The inferred type when unambiguous, else the first allowed commit type,
        else the branch type name itself.
        """
        inferred = self.inferred_commit_type(branch_type_name)
        if inferred is not None:
            return inferred
        bt = self.branch_type(branch_type_name)
        if bt is not None and bt.commit_types:
            return bt.commit_types[0]
        return branch_type_name.lower()

    @property
    def creatable_branch_types(self) -> tuple[BranchType, ...]:
        """Return the branch types ``rrt branch new`` may create (no agent or bot types)."""
        return tuple(bt for bt in self.branch_types if bt.kind in ("conventional", "custom"))


def format_type_lines(types: Iterable[_NamedType]) -> list[str]:
    """Render ``name — description`` lines for error messages and ``rrt config``."""
    return [f"  {t.name} — {t.description}" if t.description else f"  {t.name}" for t in types]


# ---------------------------------------------------------------------------
# Building a registry from [tool.rrt]
# ---------------------------------------------------------------------------


def _table_entries(raw: object, table: str) -> list[dict[str, object]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"{table} must be an array of tables")
    entries: list[dict[str, object]] = []
    for item in cast("list[object]", raw):
        if not isinstance(item, dict):
            raise ValueError(f"Each {table} entry must be a table")
        entries.append(cast("dict[str, object]", item))
    return entries


def _entry_name(entry: Mapping[str, object], table: str, allowed: frozenset[str]) -> str:
    raw_name = entry.get("name")
    if not isinstance(raw_name, str) or not raw_name.strip():
        raise ValueError(f"Each {table} entry needs a non-empty name")
    name = raw_name.strip().lower()
    if not TYPE_IDENTIFIER_RE.fullmatch(name):
        raise ValueError(
            f"{table} entry {raw_name!r} is not a valid identifier "
            "(use lowercase letters, digits, hyphens, or underscores, starting with a letter)",
        )
    for key in entry:
        if key not in allowed:
            raise ValueError(f"{table} entry {name!r} has unknown key {key!r}")
    return name


def _entry_description(
    entry: Mapping[str, object], table: str, name: str, *, required: bool
) -> str | None:
    if "description" not in entry:
        if required:
            raise ValueError(f"{table} entry {name!r} needs a non-empty description")
        return None
    value = entry["description"]
    if not isinstance(value, str):
        raise ValueError(f"{table} entry {name!r}: description must be a string")
    text = value.strip()
    if required and not text:
        raise ValueError(f"{table} entry {name!r} needs a non-empty description")
    return text


def _entry_bool(entry: Mapping[str, object], table: str, name: str, key: str) -> bool | None:
    if key not in entry:
        return None
    value = entry[key]
    if not isinstance(value, bool):
        raise ValueError(f"{table} entry {name!r}: {key} must be a boolean")
    return value


def _entry_choice[T: str](
    entry: Mapping[str, object], table: str, name: str, key: str, choices: Sequence[T]
) -> T | None:
    if key not in entry:
        return None
    value = entry[key]
    if value not in choices:
        raise ValueError(f"{table} entry {name!r}: {key} must be one of: {', '.join(choices)}")
    return cast("T", value)


def _entry_section(entry: Mapping[str, object], name: str) -> tuple[bool, str | None]:
    """Return ``(given, section)``; ``false`` in TOML means "not in the changelog"."""
    if "changelog_section" not in entry:
        return False, None
    value = entry["changelog_section"]
    if value is False:
        return True, None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{_COMMIT_TABLE} entry {name!r}: changelog_section must be a non-empty string or false",
        )
    return True, value.strip()


def _check_duplicate(name: str, seen: set[str], kind: str, table: str) -> None:
    if name in seen:
        raise ValueError(f"Duplicate {kind} type {name!r} in [[{table}]]")
    seen.add(name)


def _shorthand_conflict(name: str, shorthand: str, table: str) -> ValueError:
    return ValueError(f"{name!r} is defined in both {shorthand} and [[{table}]]; use one")


def _resolve_commit_types(
    extra_commit_types: Sequence[str],
    extra_section_map: Mapping[str, str],
    raw_tables: object,
) -> tuple[CommitType, ...]:
    commits: dict[str, CommitType] = {ct.name: ct for ct in BUILTIN_COMMIT_TYPES}
    shorthand = {name.strip().lower() for name in extra_commit_types}
    for name in (n.strip().lower() for n in extra_commit_types):
        commits.setdefault(name, CommitType(name=name, description=""))

    seen: set[str] = set()
    sections_from_tables: set[str] = set()
    required_from_tables: set[str] = set()
    for entry in _table_entries(raw_tables, _COMMIT_TABLE):
        name = _entry_name(entry, _COMMIT_TABLE, _COMMIT_KEYS)
        _check_duplicate(name, seen, "commit", _COMMIT_TABLE)
        base = next((ct for ct in BUILTIN_COMMIT_TYPES if ct.name == name), None)
        if name in shorthand and base is None:
            raise _shorthand_conflict(name, "extra_commit_types", _COMMIT_TABLE)
        description = _entry_description(entry, _COMMIT_TABLE, name, required=base is None)
        section_given, section = _entry_section(entry, name)
        required = _entry_bool(entry, _COMMIT_TABLE, name, "changelog_required")
        bump = _entry_choice(entry, _COMMIT_TABLE, name, "bump", BUMP_LEVELS)
        current = base or CommitType(name=name, description="")
        effective_section = section if section_given else current.changelog_section
        commits[name] = CommitType(
            name=name,
            description=description if description is not None else current.description,
            changelog_section=effective_section,
            changelog_required=(
                required if required is not None else default_changelog_required(effective_section)
            ),
            bump=bump if bump is not None else current.bump,
        )
        if section_given:
            sections_from_tables.add(name)
        if required is not None:
            required_from_tables.add(name)

    for raw_key, raw_section in extra_section_map.items():
        key = raw_key.strip().lower()
        section = raw_section.strip()
        if key not in commits:
            raise ValueError(
                f"tool.rrt.extra_section_map key {raw_key!r} is not a known commit type"
            )
        if not section:
            raise ValueError(f"tool.rrt.extra_section_map value for {raw_key!r} must not be empty")
        if key in sections_from_tables:
            raise ValueError(
                f"changelog section for {key!r} is set in both extra_section_map and "
                f"[[{_COMMIT_TABLE}]]; use one",
            )
        current = commits[key]
        commits[key] = replace(
            current,
            changelog_section=section,
            changelog_required=(
                current.changelog_required
                if key in required_from_tables
                else default_changelog_required(section)
            ),
        )
    return tuple(commits.values())


def _resolve_branch_types(
    extra_branch_types: Sequence[str],
    raw_tables: object,
    commits: TypeRegistry,
) -> tuple[BranchType, ...]:
    branches: dict[str, BranchType] = {bt.name: bt for bt in BUILTIN_BRANCH_TYPES}
    shorthand = {name.strip().lower() for name in extra_branch_types}
    for name in (n.strip().lower() for n in extra_branch_types):
        branches.setdefault(name, BranchType(name=name, description="", slug="any"))

    seen: set[str] = set()
    for entry in _table_entries(raw_tables, _BRANCH_TABLE):
        name = _entry_name(entry, _BRANCH_TABLE, _BRANCH_KEYS)
        _check_duplicate(name, seen, "branch", _BRANCH_TABLE)
        base = next((bt for bt in BUILTIN_BRANCH_TYPES if bt.name == name), None)
        if name in shorthand and base is None:
            raise _shorthand_conflict(name, "extra_branch_types", _BRANCH_TABLE)
        description = _entry_description(entry, _BRANCH_TABLE, name, required=base is None)
        allowed = _entry_commit_types(entry, name, commits)
        slug = _entry_choice(entry, _BRANCH_TABLE, name, "slug", SLUG_POLICIES)
        required = _entry_bool(entry, _BRANCH_TABLE, name, "changelog_required")
        if base is None:
            base = BranchType(
                name=name,
                description="",
                changelog_required=commits.requires_changelog(name),
            )
        branches[name] = BranchType(
            name=name,
            description=description if description is not None else base.description,
            commit_types=allowed if allowed is not None else base.commit_types,
            slug=slug if slug is not None else base.slug,
            changelog_required=required if required is not None else base.changelog_required,
            kind=base.kind,
        )
    return tuple(branches.values())


def _entry_commit_types(
    entry: Mapping[str, object], name: str, commits: TypeRegistry
) -> tuple[str, ...] | None:
    if "commit_types" not in entry:
        return None
    value = entry["commit_types"]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{_BRANCH_TABLE} entry {name!r}: commit_types must be a list of strings")
    allowed: list[str] = []
    for item in cast("list[str]", value):
        normalized = item.strip().lower()
        if commits.commit_type(normalized) is None:
            raise ValueError(f"branch type {name!r} allows unknown commit type {item!r}")
        if normalized not in allowed:
            allowed.append(normalized)
    return tuple(allowed)


def build_registry(
    *,
    extra_commit_types: Sequence[str] = (),
    extra_branch_types: Sequence[str] = (),
    extra_section_map: Mapping[str, str] | None = None,
    commit_types: object = None,
    branch_types: object = None,
) -> TypeRegistry:
    """Resolve built-in types, shorthand lists and typed tables into one registry.

    *commit_types* and *branch_types* are the raw ``[[tool.rrt.commit_types]]``
    and ``[[tool.rrt.branch_types]]`` arrays. A table entry with a built-in
    name overrides only the fields it sets. Raises ``ValueError`` with the
    offending key for any invalid or conflicting definition.
    """
    commits = _resolve_commit_types(extra_commit_types, extra_section_map or {}, commit_types)
    commit_registry = TypeRegistry(commit_types=commits)
    branches = _resolve_branch_types(extra_branch_types, branch_types, commit_registry)
    return TypeRegistry(commit_types=commits, branch_types=branches)


__all__ = [
    "BASE_SECTION_ORDER",
    "BOT_BRANCH_TYPES",
    "BREAKING_SECTION",
    "BUILTIN_BRANCH_TYPES",
    "BUILTIN_COMMIT_TYPES",
    "BUMP_LEVELS",
    "CONVENTIONAL_BRANCH_TYPE_NAMES",
    "MAGIC_BRANCH_TYPES",
    "MAINTENANCE_SECTION",
    "SLUG_POLICIES",
    "TYPE_IDENTIFIER_RE",
    "BranchKind",
    "BranchType",
    "BumpLevel",
    "CommitType",
    "SlugPolicy",
    "TypeRegistry",
    "build_registry",
    "default_changelog_required",
    "format_type_lines",
]
