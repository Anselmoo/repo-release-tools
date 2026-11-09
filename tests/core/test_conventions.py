"""Tests for the commit/branch type registry (built-in and user-defined types)."""

from __future__ import annotations

import pytest

from repo_release_tools.conventions import (
    BOT_BRANCH_TYPES,
    BUILTIN_BRANCH_TYPES,
    BUILTIN_COMMIT_TYPES,
    MAGIC_BRANCH_TYPES,
    BranchType,
    CommitType,
    TypeRegistry,
    build_registry,
    format_type_lines,
)


def test_builtin_registry_lists_conventional_types_in_legacy_order() -> None:
    reg = TypeRegistry()
    assert reg.commit_type_names == (
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
        "deps",
    )
    assert reg.branch_type_names == (
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
        *MAGIC_BRANCH_TYPES,
        *BOT_BRANCH_TYPES,
    )
    assert all(ct.description for ct in BUILTIN_COMMIT_TYPES)
    assert all(bt.description for bt in BUILTIN_BRANCH_TYPES)


def test_builtin_sections_and_changelog_policy_match_legacy_section_map() -> None:
    reg = TypeRegistry()
    assert reg.section_for("feat") == "Added"
    assert reg.section_for("fix") == "Fixed"
    assert reg.section_for("refactor") == "Changed"
    assert reg.section_for("docs") == "Documentation"
    assert reg.section_for("chore") == "Maintenance"
    assert reg.section_for("feat", breaking=True) == "Breaking Changes"
    assert reg.section_for("unknown") is None
    assert reg.requires_changelog("feat") is True
    assert reg.requires_changelog("chore") is False
    assert reg.requires_changelog("chore", breaking=True) is True
    assert reg.requires_changelog("unknown") is False
    assert reg.section_order == (
        "Breaking Changes",
        "Added",
        "Fixed",
        "Changed",
        "Documentation",
        "Maintenance",
    )


def test_builtin_bump_levels() -> None:
    reg = TypeRegistry()
    assert reg.bump_for("feat") == "minor"
    assert reg.bump_for("fix") == "patch"
    assert reg.bump_for("FEAT") == "minor"
    assert reg.bump_for("unknown") == "none"


def test_bot_branches_accept_any_slug_and_agents_need_kebab() -> None:
    reg = TypeRegistry()
    renovate = reg.branch_type("renovate")
    claude = reg.branch_type("claude")
    assert renovate is not None and renovate.slug == "any" and renovate.kind == "bot"
    assert claude is not None and claude.slug == "kebab" and claude.kind == "agent"
    assert reg.branch_type("nope") is None


def test_builtin_branch_changelog_policy_follows_commit_type() -> None:
    reg = TypeRegistry()
    assert reg.branch_requires_changelog("feat") is True
    assert reg.branch_requires_changelog("chore") is False
    assert reg.branch_requires_changelog("claude") is False
    assert reg.branch_requires_changelog("unknown") is False


def test_shorthand_extras_keep_legacy_behaviour() -> None:
    reg = build_registry(
        extra_commit_types=("security", "feat"),
        extra_branch_types=("design", "feat"),
    )
    security = reg.commit_type("security")
    assert security == CommitType(name="security", description="")
    assert reg.section_for("security") is None
    assert reg.requires_changelog("security") is False
    assert reg.bump_for("security") == "patch"
    # A built-in name in the shorthand list stays a harmless no-op.
    assert reg.commit_type_names.count("feat") == 1
    design = reg.branch_type("design")
    assert design == BranchType(name="design", description="", slug="any", kind="custom")
    assert reg.branch_type_names.count("feat") == 1


def test_extra_section_map_is_applied() -> None:
    reg = build_registry(
        extra_commit_types=("security",),
        extra_section_map={"security": "Security", "refactor": "Refactoring"},
    )
    assert reg.section_for("security") == "Security"
    assert reg.requires_changelog("security") is True
    assert reg.section_for("refactor") == "Refactoring"
    assert reg.section_order == (
        "Breaking Changes",
        "Added",
        "Fixed",
        "Changed",
        "Documentation",
        "Refactoring",
        "Security",
        "Maintenance",
    )


def test_extra_section_map_rejects_unknown_type() -> None:
    with pytest.raises(
        ValueError, match="extra_section_map key 'ghost' is not a known commit type"
    ):
        build_registry(extra_section_map={"ghost": "Ghosts"})


def test_extra_section_map_rejects_empty_section() -> None:
    with pytest.raises(ValueError, match="extra_section_map value for 'feat' must not be empty"):
        build_registry(extra_section_map={"feat": "  "})


def test_extra_section_map_keeps_explicit_changelog_required() -> None:
    reg = build_registry(
        commit_types=[{"name": "ux", "description": "UX", "changelog_required": False}],
        extra_section_map={"ux": "UX"},
    )
    assert reg.section_for("ux") == "UX"
    assert reg.requires_changelog("ux") is False


def test_typed_commit_type_definition() -> None:
    reg = build_registry(
        commit_types=[
            {
                "name": "security",
                "description": "Security fix or hardening",
                "changelog_section": "Security",
                "bump": "patch",
            },
            {
                "name": "infra",
                "description": "Infrastructure change",
                "changelog_section": "Infrastructure",
                "changelog_required": False,
                "bump": "none",
            },
            {"name": "ux", "description": "UX polish", "bump": "minor"},
        ],
    )
    assert reg.commit_type("security") == CommitType(
        name="security",
        description="Security fix or hardening",
        changelog_section="Security",
        changelog_required=True,
        bump="patch",
    )
    assert reg.requires_changelog("infra") is False
    assert reg.section_for("infra") == "Infrastructure"
    assert reg.bump_for("infra") == "none"
    assert reg.section_for("ux") is None
    assert reg.bump_for("ux") == "minor"
    assert reg.commit_type_names[-3:] == ("security", "infra", "ux")


def test_typed_commit_type_overrides_builtin_fieldwise() -> None:
    reg = build_registry(
        commit_types=[
            {"name": "refactor", "changelog_section": "Maintenance"},
            {"name": "docs", "description": "Docs only", "bump": "none"},
        ],
    )
    refactor = reg.commit_type("refactor")
    assert refactor is not None
    builtin_refactor = TypeRegistry().commit_type("refactor")
    assert builtin_refactor is not None
    assert refactor.description == builtin_refactor.description
    assert refactor.changelog_section == "Maintenance"
    # changelog_required follows the new section unless given explicitly.
    assert refactor.changelog_required is False
    docs = reg.commit_type("docs")
    assert docs is not None
    assert docs.description == "Docs only"
    assert docs.changelog_section == "Documentation"
    assert docs.bump == "none"
    # Overrides keep the built-in position.
    assert reg.commit_type_names.index("refactor") == 4


def test_typed_commit_type_can_drop_builtin_from_changelog() -> None:
    reg = build_registry(commit_types=[{"name": "style", "changelog_section": False}])
    assert reg.section_for("style") is None
    assert reg.requires_changelog("style") is False


def test_typed_branch_type_definition() -> None:
    reg = build_registry(
        commit_types=[{"name": "security", "description": "Security", "changelog_section": "Sec"}],
        branch_types=[
            {
                "name": "design",
                "description": "Design records",
                "commit_types": ["docs", "chore"],
            },
            {"name": "security", "description": "Security work"},
            {"name": "spike", "description": "Throwaway spike", "slug": "any"},
        ],
    )
    design = reg.branch_type("design")
    assert design == BranchType(
        name="design",
        description="Design records",
        commit_types=("docs", "chore"),
        slug="kebab",
        changelog_required=False,
        kind="custom",
    )
    # A custom branch named like a commit type inherits that type's changelog policy.
    assert reg.branch_requires_changelog("security") is True
    spike = reg.branch_type("spike")
    assert spike is not None
    assert spike.slug == "any"


def test_typed_branch_type_overrides_builtin() -> None:
    reg = build_registry(branch_types=[{"name": "docs", "commit_types": ["docs"]}])
    docs = reg.branch_type("docs")
    assert docs is not None
    assert docs.commit_types == ("docs",)
    assert docs.kind == "conventional"
    builtin_docs = TypeRegistry().branch_type("docs")
    assert builtin_docs is not None
    assert docs.description == builtin_docs.description
    assert reg.allowed_commit_types_on("docs/fix-typo") == ("docs",)
    assert reg.allowed_commit_types_on("feat/x") == ()
    assert reg.allowed_commit_types_on("main") == ()
    assert reg.allowed_commit_types_on("") == ()


def test_inferred_commit_type_for_branch() -> None:
    reg = build_registry(
        branch_types=[
            {"name": "design", "description": "Design", "commit_types": ["docs"]},
            {"name": "wip", "description": "WIP", "commit_types": ["docs", "chore"]},
            {"name": "free", "description": "Free"},
            {"name": "docs", "commit_types": ["chore", "docs"]},
        ],
    )
    assert reg.inferred_commit_type("docs") == "docs"
    assert reg.inferred_commit_type("feat") == "feat"
    assert reg.inferred_commit_type("design") == "docs"
    assert reg.inferred_commit_type("wip") is None
    assert reg.inferred_commit_type("free") is None
    assert reg.inferred_commit_type("claude") is None
    assert reg.inferred_commit_type("renovate") is None
    assert reg.inferred_commit_type("unknown") is None


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {"commit_types": [{"name": "security"}]},
            r"commit_types entry 'security' needs a non-empty description",
        ),
        (
            {"commit_types": [{"name": "security", "description": "  "}]},
            r"commit_types entry 'security' needs a non-empty description",
        ),
        ({"commit_types": "nope"}, r"commit_types must be an array of tables"),
        ({"commit_types": ["nope"]}, r"Each tool.rrt.commit_types entry must be a table"),
        ({"commit_types": [{"description": "x"}]}, r"needs a non-empty name"),
        ({"commit_types": [{"name": "Bad Name", "description": "x"}]}, r"not a valid identifier"),
        (
            {
                "commit_types": [
                    {"name": "a", "description": "x"},
                    {"name": "a", "description": "y"},
                ]
            },
            r"Duplicate commit type 'a'",
        ),
        (
            {"commit_types": [{"name": "a", "description": "x", "bump": "major"}]},
            r"bump must be one of: none, patch, minor",
        ),
        (
            {"commit_types": [{"name": "a", "description": "x", "changelog_section": 3}]},
            r"changelog_section must be a non-empty string or false",
        ),
        (
            {"commit_types": [{"name": "a", "description": "x", "changelog_section": ""}]},
            r"changelog_section must be a non-empty string or false",
        ),
        (
            {"commit_types": [{"name": "a", "description": "x", "changelog_section": True}]},
            r"changelog_section must be a non-empty string or false",
        ),
        (
            {"commit_types": [{"name": "a", "description": "x", "changelog_required": "yes"}]},
            r"changelog_required must be a boolean",
        ),
        (
            {"commit_types": [{"name": "a", "description": 5}]},
            r"description must be a string",
        ),
        (
            {"commit_types": [{"name": "a", "description": "x", "colour": "red"}]},
            r"unknown key 'colour'",
        ),
        (
            {"commit_types": [{"name": "a", "description": "x"}], "extra_commit_types": ("a",)},
            r"'a' is defined in both extra_commit_types and \[\[tool.rrt.commit_types\]\]",
        ),
        (
            {
                "commit_types": [{"name": "a", "description": "x", "changelog_section": "A"}],
                "extra_section_map": {"a": "B"},
            },
            r"changelog section for 'a' is set in both extra_section_map and",
        ),
        ({"branch_types": "nope"}, r"branch_types must be an array of tables"),
        (
            {"branch_types": [{"name": "design"}]},
            r"branch_types entry 'design' needs a non-empty description",
        ),
        (
            {"branch_types": [{"name": "design", "description": "d", "slug": "loose"}]},
            r"slug must be one of: kebab, any",
        ),
        (
            {"branch_types": [{"name": "design", "description": "d", "commit_types": "docs"}]},
            r"commit_types must be a list of strings",
        ),
        (
            {"branch_types": [{"name": "design", "description": "d", "commit_types": ["ghost"]}]},
            r"branch type 'design' allows unknown commit type 'ghost'",
        ),
        (
            {
                "branch_types": [{"name": "design", "description": "d"}],
                "extra_branch_types": ("design",),
            },
            r"'design' is defined in both extra_branch_types and \[\[tool.rrt.branch_types\]\]",
        ),
    ],
)
def test_build_registry_rejects_invalid_definitions(kwargs: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        build_registry(**kwargs)


def test_format_type_lines_shows_descriptions_when_present() -> None:
    lines = format_type_lines(
        (
            CommitType(name="feat", description="A new feature"),
            CommitType(name="security", description=""),
        ),
    )
    assert lines == ["  feat — A new feature", "  security"]


def test_suggested_commit_type_and_creatable_branch_types() -> None:
    reg = build_registry(
        branch_types=[
            {"name": "wip", "description": "WIP", "commit_types": ["chore", "docs"]},
            {"name": "free", "description": "Free"},
        ],
    )
    assert reg.suggested_commit_type("feat") == "feat"
    assert reg.suggested_commit_type("wip") == "chore"
    assert reg.suggested_commit_type("Free") == "chore"
    creatable = [bt.name for bt in reg.creatable_branch_types]
    assert "wip" in creatable
    assert "claude" not in creatable
    assert "renovate" not in creatable


def test_suggested_commit_type_for_branch_only_type_is_a_registered_commit_type() -> None:
    reg = build_registry(branch_types=[{"name": "free", "description": "Free-form work"}])
    suggested = reg.suggested_commit_type("free")
    assert reg.commit_type(suggested) is not None


def test_builtin_branch_changelog_policy_follows_overridden_commit_type() -> None:
    reg = build_registry(commit_types=[{"name": "refactor", "changelog_section": "Maintenance"}])
    assert reg.requires_changelog("refactor") is False
    assert reg.branch_requires_changelog("refactor") is False
    explicit = build_registry(
        commit_types=[{"name": "refactor", "changelog_section": "Maintenance"}],
        branch_types=[{"name": "refactor", "changelog_required": True}],
    )
    assert explicit.branch_requires_changelog("refactor") is True
