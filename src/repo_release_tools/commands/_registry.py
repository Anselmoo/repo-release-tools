"""Self-registering command declaration for `rrt`'s argparse subcommands.

Before this module existed, every subcommand required hand-syncing three to
five separate places in ``cli.py`` and ``docs/publisher.py``: an import block,
a tuple of registrar callables, flat name sets used for help-text coloring,
and a command-group mapping duplicated (in prose only, not code) between the
two files. Missing the coloring/grouping sets was silent — commands still
worked, they just rendered with the wrong style or vanished from grouped
help, exactly what happened to the ``mcp`` and ``project`` commands.

Each command module now declares itself once, at its own ``register()``
function, via :func:`register_command`. ``cli.py`` and ``docs/publisher.py``
both read the resulting :data:`registry` instead of maintaining their own
copies.

``ensure_registered`` still needs an explicit list of command modules to
import — a decorator only runs once its module has been imported, and
nothing else does so on `rrt`'s behalf. That single, `noqa`'d import list is
the one place left that needs a new line when a command module is added.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse
    from collections.abc import Callable

    RegisterFn = Callable[[argparse._SubParsersAction[argparse.ArgumentParser]], None]


class CommandCategory(StrEnum):
    """Semantic classification of a top-level command, used for help styling."""

    READ = "read"
    WRITE = "write"
    DANGER = "danger"


class CommandGroup(StrEnum):
    """The command groups shown in grouped `--help` output, in display order.

    The first five are also used to generate the command-group reference doc
    pages (see ``_DOC_PAGE_GROUPS`` below). ``OTHER`` is a CLI-help-only
    fallback bucket: a command that reaches this far without an explicit
    group still shows up somewhere in `--help` instead of silently
    vanishing — the exact failure mode this module exists to prevent.
    """

    VERSION_RELEASE = "version-release"
    REPO_HEALTH = "repo-health"
    CI_AUTOMATION = "ci-automation"
    GIT_WORKFLOW = "git-workflow"
    SETUP_TOOLING = "setup-tooling"
    OTHER = "other"


COMMAND_GROUP_LABELS: dict[CommandGroup, str] = {
    CommandGroup.VERSION_RELEASE: "Version & Release",
    CommandGroup.REPO_HEALTH: "Repository Health",
    CommandGroup.CI_AUTOMATION: "CI & Automation",
    CommandGroup.GIT_WORKFLOW: "Git Workflow",
    CommandGroup.SETUP_TOOLING: "Setup & Tooling",
    CommandGroup.OTHER: "Other",
}

# Groups rendered as their own doc page by docs/publisher.py. OTHER never gets a
# dedicated page — it's a CLI-help-only fallback, not a real documented group.
_DOC_PAGE_GROUPS: tuple[CommandGroup, ...] = (
    CommandGroup.VERSION_RELEASE,
    CommandGroup.REPO_HEALTH,
    CommandGroup.CI_AUTOMATION,
    CommandGroup.GIT_WORKFLOW,
    CommandGroup.SETUP_TOOLING,
)


@dataclass(frozen=True, slots=True)
class CommandSpec:
    """A single top-level command's full declaration."""

    name: str
    register: RegisterFn
    category: CommandCategory
    group: CommandGroup = CommandGroup.OTHER


@dataclass(slots=True)
class CommandRegistry:
    """Holds every registered :class:`CommandSpec`, in declaration order."""

    _specs: dict[str, CommandSpec] = field(default_factory=dict)

    def add(self, spec: CommandSpec) -> None:
        """Register *spec*, raising if its name was already registered."""
        if spec.name in self._specs:
            raise ValueError(f"command {spec.name!r} already registered")
        self._specs[spec.name] = spec

    def register_all(self, subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
        """Call every registered command's ``register()`` against *subparsers*."""
        for spec in self._specs.values():
            spec.register(subparsers)
            if spec.name not in subparsers.choices:
                raise RuntimeError(
                    f"CommandSpec name {spec.name!r} does not match the parser name "
                    "its register() function added — decorator and add_parser() "
                    "have drifted apart."
                )

    def names_in_category(self, category: CommandCategory) -> set[str]:
        """Return the names of every top-level command in *category*."""
        return {spec.name for spec in self._specs.values() if spec.category is category}

    def _names_by_group(self) -> dict[CommandGroup, list[str]]:
        by_group: dict[CommandGroup, list[str]] = {}
        for spec in self._specs.values():
            by_group.setdefault(spec.group, []).append(spec.name)
        return by_group

    def groups_by_label(self) -> dict[str, list[str]]:
        """Return ``{group display name: [command names]}`` for grouped help output.

        Ordered by :class:`CommandGroup` declaration order (including ``OTHER``,
        so a command is never silently omitted), each group's commands sorted
        by name — independent of import/registration order.
        """
        by_group = self._names_by_group()
        return {
            COMMAND_GROUP_LABELS[group]: sorted(names)
            for group in CommandGroup
            if (names := by_group.get(group))
        }

    def groups_config(self) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
        """Return ``((slug, label, (command names, ...)), ...)`` for doc generation.

        Ordered by ``_DOC_PAGE_GROUPS`` (``OTHER`` excluded — it never gets a doc
        page), each group's commands sorted by name — independent of
        import/registration order.
        """
        by_group = self._names_by_group()
        return tuple(
            (group.value, COMMAND_GROUP_LABELS[group], tuple(sorted(names)))
            for group in _DOC_PAGE_GROUPS
            if (names := by_group.get(group))
        )


registry = CommandRegistry()


def register_command(
    *,
    name: str,
    category: CommandCategory,
    group: CommandGroup = CommandGroup.OTHER,
) -> Callable[[RegisterFn], RegisterFn]:
    """Decorate a command module's ``register()`` function to self-register it."""

    def decorator(fn: RegisterFn) -> RegisterFn:
        registry.add(CommandSpec(name=name, register=fn, category=category, group=group))
        return fn

    return decorator


def ensure_registered() -> None:
    """Import every command module so its ``@register_command`` decorator runs.

    Idempotent: Python caches each import in ``sys.modules``, so calling this
    more than once (cli.py and docs/publisher.py both need to) re-executes no
    module body and re-registers nothing.
    """
    from repo_release_tools.commands import (  # noqa: F401
        action_cmd,
        agents_cmd,
        artifacts_cmd,
        branch,
        bump,
        changelog_cmd,
        ci_version,
        config_cmd,
        docs_cmd,
        doctor,
        drift_cmd,
        env_cmd,
        eol_check,
        fields_cmd,
        folder,
        git_cmd,
        hooks_cmd,
        init,
        install_cmd,
        mcp_cmd,
        project_cmd,
        release_cmd,
        skill,
        sync_cmd,
        tag,
        toc,
        tree,
        workspace,
    )
