"""CLI reference and topic-page generation for ``rrt docs publish``.

This module is the authoritative source for generating the full CLI reference
Markdown (``docs/commands/rrt-cli.md``) and all source-owned topic pages from
live argparse configuration and source-module docstrings.

It is consumed by ``rrt docs publish`` (``commands/docs_cmd.py``) and
re-exported by ``scripts/generate_cli_docs.py`` for backward compatibility
with the ``poe docs-*`` tasks during the transition period.

## Import discipline

``repo_release_tools.cli`` is imported *lazily* (inside function bodies) to
avoid a circular-import cycle:
  ``cli`` → ``docs_cmd`` → ``docs_publisher`` → ``cli``
All other package imports are at module level.
"""

from __future__ import annotations

import argparse
import inspect
import os
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import repo_release_tools as rrt_package
from repo_release_tools import action as action_module
from repo_release_tools import eol as eol_module
from repo_release_tools import git as git_helpers
from repo_release_tools import hooks as hooks_module
from repo_release_tools.commands import branch as branch_module
from repo_release_tools.commands import doctor as doctor_module
from repo_release_tools.commands import eol_check as eol_check_module
from repo_release_tools.commands import skill as skill_module
from repo_release_tools.commands import toc as toc_module
from repo_release_tools.commands import tree as tree_module
from repo_release_tools.tools.inject import apply_generated_docs as apply_generated_docs

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_OUTPUT: Path = Path("docs/commands/rrt-cli.md")
PINNED_COLUMNS: str = "120"
AUTOGEN_NOTE: str = (
    "<!-- Auto-generated from repo_release_tools.cli.build_parser(); "
    "run `rrt docs publish` to refresh. -->"
)

_README_BASE: str = "https://github.com/Anselmoo/repo-release-tools/blob/main"


# ---------------------------------------------------------------------------
# Protocols and data structures
# ---------------------------------------------------------------------------


class SupportsWrite(Protocol):
    """Minimal text stream protocol for stdout/stderr injection."""

    def write(self, s: str, /) -> object:
        """Write text to the underlying stream-like object."""


@dataclass(frozen=True)
class HelpSection:
    """One node in the argparse tree (root or a subcommand path)."""

    argv: tuple[str, ...]
    heading_level: int

    @property
    def title(self) -> str:
        """Return a display title for the section."""
        if not self.argv:
            return "Global help"
        return "`rrt " + " ".join(self.argv) + "`"


@dataclass(frozen=True)
class DocTarget:
    """A generated documentation output: destination path + render callable."""

    output_path: Path
    render: Callable[[], str]
    anchor_id: str | None = None


@dataclass(frozen=True)
class CommandDocSource:
    """A callable that returns topic-doc prose for a command."""

    render: Callable[[], str]


# ---------------------------------------------------------------------------
# Source-owned topic doc collection
# ---------------------------------------------------------------------------


def _collect_source_owned_topic_docs(modules: Sequence[object]) -> dict[str, str]:
    """Collect ``SOURCE_OWNED_TOPIC_DOCS`` tuples exported by *modules* into a dict."""
    collected: dict[str, str] = {}
    for module in modules:
        for slug, markdown in getattr(module, "SOURCE_OWNED_TOPIC_DOCS", ()):
            collected[slug] = markdown
    return collected


SOURCE_OWNED_TOPIC_DOCS: dict[str, str] = _collect_source_owned_topic_docs(
    (
        rrt_package,
        branch_module,
        git_helpers,
        hooks_module,
        action_module,
        skill_module,
        doctor_module,
        eol_module,
        tree_module,
    )
)


def _render_topic_doc(slug: str) -> str:
    """Return a source-owned topic doc by slug."""
    return SOURCE_OWNED_TOPIC_DOCS[slug]


# ---------------------------------------------------------------------------
# Module registry (lazy to avoid circular cli import)
# ---------------------------------------------------------------------------


def _get_command_doc_modules() -> dict[str, object]:
    """Return the per-command module registry (lazily importing cli)."""
    from repo_release_tools import cli  # noqa: PLC0415  (lazy – avoid circular)

    return {
        "branch": cli.branch,
        "bump": cli.bump,
        "ci-version": cli.ci_version,
        "config": cli.config_cmd,
        "doctor": cli.doctor,
        "env": cli.env_cmd,
        "eol": cli.eol_check,
        "git": cli.git_cmd,
        "init": cli.init,
        "skill": cli.skill,
        "toc": toc_module,
        "tree": cli.tree,
    }


# Patchable sentinel: None means «use _get_command_doc_modules() lazily».
# Tests can set this to a custom dict via setattr/monkeypatch.
COMMAND_DOC_MODULES: dict[str, object] | None = None

COMMAND_DOC_SOURCES: dict[str, CommandDocSource] = {
    "branch": CommandDocSource(render=lambda: _render_topic_doc("branch")),
    "git": CommandDocSource(render=lambda: _render_topic_doc("git")),
    "doctor": CommandDocSource(render=lambda: _render_topic_doc("doctor")),
    "eol": CommandDocSource(render=lambda: inspect.getdoc(eol_check_module) or ""),
    "tree": CommandDocSource(render=lambda: _render_topic_doc("tree")),
}


# ---------------------------------------------------------------------------
# Heading normalisation
# ---------------------------------------------------------------------------


def _heading_level(line: str) -> int | None:
    """Return the Markdown heading level for *line*, or ``None`` if not a heading."""
    stripped = line.lstrip()
    if not stripped.startswith("#"):
        return None
    hashes = len(stripped) - len(stripped.lstrip("#"))
    if hashes < 1 or hashes > 6:
        return None
    if len(stripped) <= hashes or stripped[hashes] != " ":
        return None
    return hashes


def _normalize_markdown_headings(text: str, *, min_level: int) -> str:
    """Shift headings in *text* so the shallowest heading nests under *min_level*."""
    lines = text.splitlines()
    heading_levels: list[int] = []
    in_fence = False

    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        level = _heading_level(line)
        if level is not None:
            heading_levels.append(level)

    if not heading_levels:
        return text.strip()

    offset = max(min_level - min(heading_levels), 0)
    if offset == 0:
        return text.strip()

    normalized: list[str] = []
    in_fence = False
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            normalized.append(line)
            continue
        if in_fence:
            normalized.append(line)
            continue
        level = _heading_level(line)
        if level is None:
            normalized.append(line)
            continue
        content = stripped[level + 1 :]
        normalized.append(f"{'#' * min(level + offset, 6)} {content}")
    return "\n".join(normalized).strip()


# ---------------------------------------------------------------------------
# Argparse tree walker (lazy cli import throughout)
# ---------------------------------------------------------------------------


def _find_subparsers_action(
    parser: argparse.ArgumentParser,
) -> argparse._SubParsersAction | None:  # type: ignore[type-arg]
    """Return the parser's subparsers action when present."""
    return next(
        (a for a in parser._actions if isinstance(a, argparse._SubParsersAction)),
        None,
    )


def _command_group_order() -> list[str]:
    """Return top-level commands in the user-facing grouped help order."""
    from repo_release_tools import cli  # noqa: PLC0415

    ordered: list[str] = []
    seen: set[str] = set()
    for names in cli.COMMAND_GROUPS.values():
        for name in names:
            if name not in seen:
                seen.add(name)
                ordered.append(name)
    return ordered


def render_command_docs(argv: Sequence[str], *, heading_level: int) -> str:
    """Return Markdown prose docs for a top-level command section, or empty string."""
    if len(argv) != 1:
        return ""
    command_name = argv[0]
    source = COMMAND_DOC_SOURCES.get(command_name)
    if source is not None:
        docstring = source.render()
    else:
        modules = (
            COMMAND_DOC_MODULES if COMMAND_DOC_MODULES is not None else _get_command_doc_modules()
        )
        module = modules.get(command_name)
        if module is None:
            return ""
        docstring = inspect.getdoc(module) or ""
    if not docstring.strip():
        return ""
    return _normalize_markdown_headings(docstring, min_level=heading_level + 1)


def _ordered_subcommand_names(
    action: argparse._SubParsersAction[argparse.ArgumentParser],
    *,
    preferred: Sequence[str] = (),
) -> list[str]:
    """Return subcommand names in stable display order."""
    names = list(action.choices)
    ordered: list[str] = []
    seen: set[str] = set()
    for name in preferred:
        if name in action.choices and name not in seen:
            seen.add(name)
            ordered.append(name)
    for name in names:
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


def _resolve_parser(argv: Sequence[str]) -> argparse.ArgumentParser:
    """Return the parser addressed by *argv*."""
    from repo_release_tools import cli  # noqa: PLC0415

    parser = cli.build_parser()
    current: argparse.ArgumentParser = parser
    for part in argv:
        action = _find_subparsers_action(current)
        if action is None or part not in action.choices:
            joined = " ".join(("rrt", *argv)).strip()
            raise KeyError(f"unknown parser path: {joined}")
        current = action.choices[part]
    return current


def iter_help_sections() -> Iterator[HelpSection]:
    """Yield the root and all nested command help sections."""
    from repo_release_tools import cli  # noqa: PLC0415

    yield HelpSection(argv=(), heading_level=2)

    root = cli.build_parser()
    root_subparsers = _find_subparsers_action(root)
    if root_subparsers is None:
        return

    def walk(
        argv: tuple[str, ...],
        parser: argparse.ArgumentParser,
        *,
        preferred: Sequence[str] = (),
    ) -> Iterator[HelpSection]:
        yield HelpSection(argv=argv, heading_level=min(2 + len(argv) - 1, 6))
        subparsers = _find_subparsers_action(parser)
        if subparsers is None:
            return
        for name in _ordered_subcommand_names(subparsers, preferred=preferred):
            child = subparsers.choices[name]
            yield from walk((*argv, name), child)

    for name in _ordered_subcommand_names(root_subparsers, preferred=_command_group_order()):
        child = root_subparsers.choices[name]
        yield from walk((name,), child)


@contextmanager
def pinned_help_environment() -> Iterator[None]:
    """Pin environment settings so help rendering is deterministic."""
    original_columns = os.environ.get("COLUMNS")
    original_no_color = os.environ.get("NO_COLOR")
    os.environ["COLUMNS"] = PINNED_COLUMNS
    os.environ["NO_COLOR"] = "1"
    try:
        yield
    finally:
        if original_columns is None:
            os.environ.pop("COLUMNS", None)
        else:
            os.environ["COLUMNS"] = original_columns
        if original_no_color is None:
            os.environ.pop("NO_COLOR", None)
        else:
            os.environ["NO_COLOR"] = original_no_color


def render_help(argv: Sequence[str]) -> str:
    """Render help text for the parser addressed by *argv*."""
    from repo_release_tools import cli  # noqa: PLC0415

    with pinned_help_environment():
        parser = _resolve_parser(argv)
        return cli._strip_ansi(parser.format_help()).rstrip()


# ---------------------------------------------------------------------------
# Markdown generators
# ---------------------------------------------------------------------------


def generate_markdown() -> str:
    """Return the generated CLI reference Markdown."""
    parts = [
        "# RRT CLI",
        "",
        AUTOGEN_NOTE,
        "",
        "This reference is generated from the live `argparse` configuration in",
        "`repo_release_tools.cli` and `src/repo_release_tools/commands/*.py`.",
        "",
        "Use `rrt docs publish` to rewrite this file or `rrt docs publish --check` to",
        "verify it is current.",
        "",
    ]

    for section in iter_help_sections():
        prose = render_command_docs(section.argv, heading_level=section.heading_level)
        parts.extend(
            [
                f"{'#' * section.heading_level} {section.title}",
                "",
            ]
        )
        if prose:
            parts.extend([prose, ""])
        parts.extend(
            [
                "```text",
                render_help(section.argv),
                "```",
                "",
            ]
        )

    return "\n".join(parts).rstrip() + "\n"


def generate_semantic_branches_markdown() -> str:
    """Return the generated semantic branches topic page."""
    return _render_topic_doc("branch")


def generate_git_magic_markdown() -> str:
    """Return the generated Git magic topic page."""
    return _render_topic_doc("git")


def generate_index_topic_links_markdown() -> str:
    """Return the generated topic-link bullets for docs/index.md."""
    links = [
        "- [Semantic branches](commands/branch.md) — generated branch naming model and allowed branch types",
        "- [Git magic](commands/git_cmd.md) — generated Git helpers and workflow shortcuts",
        "- [Project tree](commands/tree.md) — generated guide for `rrt tree` output modes, "
        "ignore behavior, and traversal controls",
    ]
    return "\n".join(links)


def generate_readme_links_markdown() -> str:
    """Return the generated doc-link bullets for README.md."""
    links = [
        f"- Docs index: <{_README_BASE}/docs/index.md>",
        f"- GitHub Action: <{_README_BASE}/docs/action.md>",
        f"- CLI reference: <{_README_BASE}/docs/commands/rrt-cli.md>",
        f"- Hook setup: <{_README_BASE}/docs/commands/hooks.md>",
        f"- Conventional branches: <{_README_BASE}/docs/commands/branch.md>",
        f"- Git workflow helpers: <{_README_BASE}/docs/commands/git_cmd.md>",
        f"- Agent skills: <{_README_BASE}/docs/commands/skill.md>",
        f"- Project tree: <{_README_BASE}/docs/commands/tree.md>",
        f"- Markdown TOC: <{_README_BASE}/docs/commands/toc.md>",
        f"- Config health checks: <{_README_BASE}/docs/commands/doctor.md>",
        f"- Runtime EOL tracking: <{_README_BASE}/docs/commands/eol_check.md>",
        f"- Agent instructions: <{_README_BASE}/docs/agent-instructions.md>",
    ]
    return "\n".join(links)


# ---------------------------------------------------------------------------
# Topic-page output registry
# ---------------------------------------------------------------------------

TOPIC_PAGE_OUTPUTS: dict[str, Path] = {
    "branch": Path("docs/commands/branch.md"),
    "git": Path("docs/commands/git_cmd.md"),
    "tree": Path("docs/commands/tree.md"),
    "hooks": Path("docs/commands/hooks.md"),
    "action": Path("docs/action.md"),
    "skill": Path("docs/commands/skill.md"),
    "agent-instructions": Path("docs/agent-instructions.md"),
    "doctor": Path("docs/commands/doctor.md"),
    "eol": Path("docs/commands/eol_check.md"),
}


def _build_generated_doc_targets() -> tuple[DocTarget, ...]:
    """Build the registry of generated doc outputs."""
    targets: list[DocTarget] = [
        DocTarget(DEFAULT_OUTPUT, generate_markdown),
        DocTarget(
            Path("docs/index.md"),
            generate_index_topic_links_markdown,
            anchor_id="index-topic-links",
        ),
        DocTarget(
            Path("README.md"),
            generate_readme_links_markdown,
            anchor_id="readme-links",
        ),
    ]
    for slug, output_path in TOPIC_PAGE_OUTPUTS.items():
        targets.append(DocTarget(output_path, lambda slug=slug: _render_topic_doc(slug)))
    return tuple(targets)


GENERATED_DOC_TARGETS: tuple[DocTarget, ...] = _build_generated_doc_targets()


def iter_generated_doc_targets() -> Iterator[DocTarget]:
    """Yield every generated doc target."""
    yield from GENERATED_DOC_TARGETS


# ---------------------------------------------------------------------------
# Poe task entrypoints (canonical home)
# ---------------------------------------------------------------------------


def task_generate() -> int:
    """Write all generated docs to disk."""
    import sys  # noqa: PLC0415

    exit_code = 0
    for target in iter_generated_doc_targets():
        exit_code = max(
            exit_code,
            apply_generated_docs(
                target.render(),
                output_path=target.output_path,
                check=False,
                write=True,
                fail_on_change=False,
                stdout=sys.stdout,
                stderr=sys.stderr,
                anchor_id=target.anchor_id,
            ),
        )
    return exit_code


def task_check() -> int:
    """Verify all generated docs are up to date."""
    import sys  # noqa: PLC0415

    exit_code = 0
    for target in iter_generated_doc_targets():
        exit_code = max(
            exit_code,
            apply_generated_docs(
                target.render(),
                output_path=target.output_path,
                check=True,
                write=False,
                fail_on_change=False,
                stdout=sys.stdout,
                stderr=sys.stderr,
                anchor_id=target.anchor_id,
            ),
        )
    return exit_code


def _apply_shared_blocks(*, check: bool) -> int:
    """Inject or verify all shared anchor blocks defined in [tool.rrt.docs.shared_blocks]."""
    import sys  # noqa: PLC0415

    from repo_release_tools.config import load_config  # noqa: PLC0415

    root = Path.cwd()
    try:
        cfg = load_config(root)
    except (FileNotFoundError, ValueError):
        sys.stdout.write("No rrt config found; skipping shared_blocks injection.\n")
        return 0

    if cfg.docs is None or not cfg.docs.shared_blocks:
        return 0

    repo_url = "https://github.com/Anselmoo/repo-release-tools"
    exit_code = 0
    for block in cfg.docs.shared_blocks:
        if block.template is not None:
            template_path = root / block.template
            if not template_path.exists():
                sys.stderr.write(
                    f"SharedBlock {block.anchor_id!r}: template {block.template!r} not found.\n"
                )
                exit_code = 1
                continue
            content = template_path.read_text(encoding="utf-8").rstrip("\n")
        else:
            assert block.content is not None
            content = block.content.rstrip("\n")

        content = content.replace("{version}", rrt_package.__version__)
        content = content.replace("{repo_url}", repo_url)

        matched = sorted({p for pattern in block.targets for p in root.glob(pattern)})
        if not matched:
            sys.stdout.write(f"SharedBlock {block.anchor_id!r}: no target files matched.\n")
            continue

        for target_path in matched:
            exit_code = max(
                exit_code,
                apply_generated_docs(
                    content,
                    output_path=target_path,
                    check=check,
                    write=not check,
                    fail_on_change=False,
                    stdout=sys.stdout,
                    stderr=sys.stderr,
                    anchor_id=block.anchor_id,
                ),
            )

    return exit_code


def task_inject_shared_blocks() -> int:
    """Write all shared anchor blocks to their target files."""
    return _apply_shared_blocks(check=False)


def task_check_shared_blocks() -> int:
    """Verify all shared anchor blocks are up to date."""
    return _apply_shared_blocks(check=True)
