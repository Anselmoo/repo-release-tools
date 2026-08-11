from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Callable

import pytest

from repo_release_tools.commands import _registry
from repo_release_tools.commands._registry import (
    CommandCategory,
    CommandGroup,
    CommandRegistry,
    CommandSpec,
    register_command,
)


def _noop_register(name: str) -> Callable[[argparse._SubParsersAction], None]:
    def register(subparsers: argparse._SubParsersAction) -> None:
        subparsers.add_parser(name)

    return register


def test_add_duplicate_name_raises_value_error() -> None:
    registry = CommandRegistry()
    registry.add(
        CommandSpec(name="foo", register=_noop_register("foo"), category=CommandCategory.READ)
    )

    with pytest.raises(ValueError, match="foo"):
        registry.add(
            CommandSpec(name="foo", register=_noop_register("foo"), category=CommandCategory.WRITE)
        )


def test_register_all_happy_path() -> None:
    registry = CommandRegistry()
    registry.add(
        CommandSpec(name="foo", register=_noop_register("foo"), category=CommandCategory.READ)
    )
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()

    registry.register_all(subparsers)

    assert "foo" in subparsers.choices


def test_register_all_raises_on_name_mismatch() -> None:
    """A register() function that adds a differently-named parser than its
    CommandSpec.name is a drift bug the registry must catch immediately."""
    registry = CommandRegistry()
    registry.add(
        CommandSpec(name="foo", register=_noop_register("not-foo"), category=CommandCategory.READ)
    )
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()

    with pytest.raises(RuntimeError, match="foo"):
        registry.register_all(subparsers)


def test_names_in_category() -> None:
    registry = CommandRegistry()
    registry.add(CommandSpec(name="r", register=_noop_register("r"), category=CommandCategory.READ))
    registry.add(
        CommandSpec(name="w", register=_noop_register("w"), category=CommandCategory.WRITE)
    )
    registry.add(
        CommandSpec(name="d", register=_noop_register("d"), category=CommandCategory.DANGER)
    )

    assert registry.names_in_category(CommandCategory.READ) == {"r"}
    assert registry.names_in_category(CommandCategory.WRITE) == {"w"}
    assert registry.names_in_category(CommandCategory.DANGER) == {"d"}


def test_groups_by_label_falls_back_to_other_for_unassigned_group() -> None:
    """A CommandSpec with no explicit group must still show up somewhere in
    grouped help output — under "Other" — rather than vanishing silently."""
    registry = CommandRegistry()
    registry.add(
        CommandSpec(
            name="bump",
            register=_noop_register("bump"),
            category=CommandCategory.WRITE,
            group=CommandGroup.VERSION_RELEASE,
        )
    )
    registry.add(
        CommandSpec(name="mcp", register=_noop_register("mcp"), category=CommandCategory.READ)
    )

    groups = registry.groups_by_label()

    assert groups == {"Version & Release": ["bump"], "Other": ["mcp"]}


def test_groups_by_label_orders_groups_by_declaration_and_names_alphabetically() -> None:
    """Group and within-group order must come from CommandGroup's declaration order
    and name sorting — not from registration/import order."""
    registry = CommandRegistry()
    registry.add(
        CommandSpec(
            name="skill",
            register=_noop_register("skill"),
            category=CommandCategory.WRITE,
            group=CommandGroup.SETUP_TOOLING,
        )
    )
    registry.add(
        CommandSpec(
            name="workspace",
            register=_noop_register("workspace"),
            category=CommandCategory.READ,
            group=CommandGroup.VERSION_RELEASE,
        )
    )
    registry.add(
        CommandSpec(
            name="bump",
            register=_noop_register("bump"),
            category=CommandCategory.WRITE,
            group=CommandGroup.VERSION_RELEASE,
        )
    )

    assert list(registry.groups_by_label().items()) == [
        ("Version & Release", ["bump", "workspace"]),
        ("Setup & Tooling", ["skill"]),
    ]


def test_groups_config_matches_group_labels() -> None:
    registry = CommandRegistry()
    registry.add(
        CommandSpec(
            name="git",
            register=_noop_register("git"),
            category=CommandCategory.WRITE,
            group=CommandGroup.GIT_WORKFLOW,
        )
    )
    registry.add(
        CommandSpec(
            name="branch",
            register=_noop_register("branch"),
            category=CommandCategory.WRITE,
            group=CommandGroup.GIT_WORKFLOW,
        )
    )

    assert registry.groups_config() == (("git-workflow", "Git Workflow", ("branch", "git")),)


def test_groups_config_excludes_other() -> None:
    """OTHER is a CLI-help-only fallback; it must never produce a doc page."""
    registry = CommandRegistry()
    registry.add(
        CommandSpec(name="mcp", register=_noop_register("mcp"), category=CommandCategory.READ)
    )

    assert registry.groups_config() == ()


def test_register_command_decorator_populates_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    fresh = CommandRegistry()
    monkeypatch.setattr(_registry, "registry", fresh)

    @register_command(
        name="widget", category=CommandCategory.WRITE, group=CommandGroup.SETUP_TOOLING
    )
    def register(subparsers: argparse._SubParsersAction) -> None:
        subparsers.add_parser("widget")

    assert register.__name__ == "register"
    assert fresh.names_in_category(CommandCategory.WRITE) == {"widget"}
    assert fresh.groups_by_label() == {"Setup & Tooling": ["widget"]}


def test_register_command_rejects_duplicate_on_real_registry() -> None:
    """The real, fully-populated registry already has 'bump'; decorating a second
    register() with the same name must fail loudly at decoration time.

    Explicitly calls ensure_registered() first rather than relying on it having
    already run as a side effect of some other test/conftest import — otherwise
    this test only passes by incidental import ordering.
    """
    _registry.ensure_registered()

    with pytest.raises(ValueError, match="bump"):

        @register_command(name="bump", category=CommandCategory.WRITE)
        def register(subparsers: argparse._SubParsersAction) -> None:
            subparsers.add_parser("bump")


def test_ensure_registered_is_idempotent() -> None:
    """A second call must reuse the same registry and CommandSpec objects, not
    re-run any module's decorator (which would raise ValueError on the resulting
    duplicate registration)."""
    _registry.ensure_registered()
    registry_before = _registry.registry
    specs_before = dict(_registry.registry._specs)

    _registry.ensure_registered()

    assert _registry.registry is registry_before
    assert _registry.registry._specs.keys() == specs_before.keys()
    for name, spec in specs_before.items():
        assert _registry.registry._specs[name] is spec


def test_real_registry_has_all_28_top_level_commands() -> None:
    _registry.ensure_registered()
    names = set(_registry.registry._specs)

    assert len(names) == 28
    assert {"mcp", "project"} <= names


def test_every_registered_command_is_visible_in_groups_by_label() -> None:
    """Regression guard: a command must always show up somewhere in grouped
    `--help` output, even if a future command forgets to declare a group."""
    _registry.ensure_registered()
    all_names = set(_registry.registry._specs)
    visible_names = {
        name for names in _registry.registry.groups_by_label().values() for name in names
    }

    assert all_names <= visible_names


def test_docs_publisher_import_without_cli_first_populates_all_groups() -> None:
    """docs.publisher must fully populate COMMAND_GROUPS_CONFIG even when it is
    the first repo_release_tools module imported in the process (i.e. before
    cli.py has ever run ensure_registered() itself) — a regression guard for
    the partial-registry bug class documented in docs/publisher.py's "Import
    discipline" docstring section."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from repo_release_tools.docs import publisher\n"
            "names = {n for _, _, cmds in publisher.COMMAND_GROUPS_CONFIG for n in cmds}\n"
            "assert len(names) == 28, sorted(names)\n",
        ],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
