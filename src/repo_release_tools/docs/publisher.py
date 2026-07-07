"""CLI reference and topic-page generation for ``rrt docs publish``.

This module is the authoritative source for generating the full CLI reference
Markdown (``docs/commands/rrt-cli.md``) and all source-owned topic pages from
live argparse configuration and source-module docstrings.

It is consumed by ``rrt docs publish`` and ``rrt docs inject`` from the
package CLI surface.

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
import re
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import repo_release_tools as rrt_package
from repo_release_tools import eol as eol_module
from repo_release_tools.commands import branch as branch_module
from repo_release_tools.commands import bump as bump_module
from repo_release_tools.commands import doctor as doctor_module
from repo_release_tools.commands import eol_check as eol_check_module
from repo_release_tools.commands import install_cmd as install_module
from repo_release_tools.commands import release_cmd as release_cmd_module
from repo_release_tools.commands import skill as skill_module
from repo_release_tools.commands import sync_cmd as sync_cmd_module
from repo_release_tools.commands import toc as toc_module
from repo_release_tools.commands import tree as tree_module
from repo_release_tools.config import is_missing_tool_rrt_error
from repo_release_tools.docs.formats.markdown import heading_level, normalize_markdown_headings
from repo_release_tools.integrations import action as action_module
from repo_release_tools.tools.inject import (
    ANCHOR_END_TOKEN,
    ANCHOR_START_TOKEN,
    MDX_ANCHOR_END_TOKEN,
    MDX_ANCHOR_START_TOKEN,
    _detect_inject_format,
)
from repo_release_tools.tools.inject import apply_generated_docs as apply_generated_docs
from repo_release_tools.workflow import git as git_helpers
from repo_release_tools.workflow import hooks as hooks_module

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_OUTPUT: Path = Path("docs/src/content/docs/commands/rrt-cli.mdx")
PINNED_COLUMNS: str = "120"
_AUTOGEN_NOTE_TEXT: str = (
    "Auto-generated from repo_release_tools.cli.build_parser(); run `rrt docs publish` to refresh."
)
AUTOGEN_NOTE: str = f"<!-- {_AUTOGEN_NOTE_TEXT} -->"


def _autogen_note(output_path: Path) -> str:
    """Return the auto-generated banner comment, wrapped for *output_path*'s format.

    ``.mdx`` targets get an MDX-safe JSX comment (``{/* ... */}``); every other
    format (including RST, which never used ``AUTOGEN_NOTE`` historically) gets
    the original HTML-comment form unchanged.
    """
    if _detect_inject_format(output_path) == "mdx":
        return f"{{/* {_AUTOGEN_NOTE_TEXT} */}}"
    return AUTOGEN_NOTE


def _anchor_stub_pair(anchor_id: str, output_path: Path) -> tuple[str, str]:
    """Return the ``(start, end)`` anchor marker literals for *anchor_id*.

    The wrapper syntax is chosen by :func:`_detect_inject_format` on
    *output_path*, matching what
    :func:`~repo_release_tools.tools.inject.replace_anchored_block` will later
    look for when it fills in the block between these markers.
    """
    if _detect_inject_format(output_path) == "mdx":
        return (
            f"{{/* {MDX_ANCHOR_START_TOKEN}{anchor_id} */}}",
            f"{{/* {MDX_ANCHOR_END_TOKEN}{anchor_id} */}}",
        )
    return (
        f"<!-- {ANCHOR_START_TOKEN}{anchor_id} -->",
        f"<!-- {ANCHOR_END_TOKEN}{anchor_id} -->",
    )


_README_BASE: str = "https://github.com/Anselmoo/repo-release-tools/blob/main"

# ---------------------------------------------------------------------------
# Command-group reference page registry
# ---------------------------------------------------------------------------

# Maps a URL-safe slug to (group display name, tuple of CLI command names).
# Command names must match the argparse names used in cli.COMMAND_GROUPS.
COMMAND_GROUPS_CONFIG: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "version-release",
        "Version & Release",
        ("bump", "changelog", "ci-version", "release", "sync", "workspace", "tag"),
    ),
    (
        "repo-health",
        "Repository Health",
        ("doctor", "artifacts", "config", "env", "eol", "toc", "tree", "docs", "drift", "folder"),
    ),
    ("git-workflow", "Git Workflow", ("branch", "git")),
    ("ci-automation", "CI & Automation", ("action",)),
    ("setup-tooling", "Setup & Tooling", ("install", "init", "skill", "agents", "hooks")),
)


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
        return "Global help" if not self.argv else f"`rrt {' '.join(self.argv)}`"


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
        bump_module,
        git_helpers,
        hooks_module,
        action_module,
        skill_module,
        doctor_module,
        install_module,
        eol_module,
        tree_module,
        release_cmd_module,
        sync_cmd_module,
    ),
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
    from repo_release_tools.commands import action_cmd  # noqa: PLC0415

    return {
        "action": action_cmd,
        "agents": cli.agents_cmd,
        "artifacts": cli.artifacts_cmd,
        "branch": cli.branch,
        "bump": cli.bump,
        "changelog": cli.changelog_cmd,
        "ci-version": cli.ci_version,
        "config": cli.config_cmd,
        "docs": cli.docs_cmd,
        "doctor": cli.doctor,
        "drift": cli.drift_cmd,
        "env": cli.env_cmd,
        "eol": cli.eol_check,
        "folder": cli.folder,
        "git": cli.git_cmd,
        "hooks": cli.hooks_cmd,
        "init": cli.init,
        "install": cli.install_cmd,
        "release": cli.release_cmd,
        "skill": cli.skill,
        "tag": cli.tag,
        "toc": toc_module,
        "tree": cli.tree,
        "workspace": cli.workspace,
    }


# Patchable sentinel: None means «use _get_command_doc_modules() lazily».
# Tests can set this to a custom dict via setattr/monkeypatch.
COMMAND_DOC_MODULES: dict[str, object] | None = None

COMMAND_DOC_SOURCES: dict[str, CommandDocSource] = {
    "branch": CommandDocSource(render=lambda: _render_topic_doc("branch")),
    "bump": CommandDocSource(render=lambda: _render_topic_doc("bump")),
    "git": CommandDocSource(render=lambda: _render_topic_doc("git")),
    "doctor": CommandDocSource(render=lambda: _render_topic_doc("doctor")),
    "eol": CommandDocSource(render=lambda: inspect.getdoc(eol_check_module) or ""),
    "release": CommandDocSource(render=lambda: _render_topic_doc("release")),
    "sync": CommandDocSource(render=lambda: _render_topic_doc("sync")),
    "tree": CommandDocSource(render=lambda: _render_topic_doc("tree")),
}


# ---------------------------------------------------------------------------
# Heading normalisation
# ---------------------------------------------------------------------------


def _heading_level(line: str) -> int | None:
    """Return the Markdown heading level for *line*, or ``None`` if not a heading."""
    return heading_level(line)


def _normalize_markdown_headings(text: str, *, min_level: int) -> str:
    """Shift headings in *text* so the shallowest heading nests under *min_level*."""
    return normalize_markdown_headings(text, min_level=min_level)


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


def generate_markdown(output_path: Path = DEFAULT_OUTPUT) -> str:
    """Return the generated CLI reference Markdown (compact command index)."""
    toc_start, toc_end = _anchor_stub_pair("toc", output_path)
    parts = [
        "# rrt CLI",
        "",
        _autogen_note(output_path),
        "",
        toc_start,
        toc_end,
        "",
        "This reference is generated from the live `argparse` configuration in",
        "`repo_release_tools.cli` and `src/repo_release_tools/commands/*.py`.",
        "",
        "Use `rrt docs publish` to rewrite this file or `rrt docs publish --check` to",
        "verify it is current.",
        "",
        "## Global help",
        "",
        "```text",
        render_help(()),
        "```",
        "",
        "## Command reference",
        "",
        "Each command group has its own reference page with the full argparse help.",
        "",
        "| Group | Commands | Reference |",
        "|---|---|---|",
    ]

    for slug, display, commands in COMMAND_GROUPS_CONFIG:
        cmd_list = ", ".join(f"`{c}`" for c in commands)
        ref_href = f"/repo-release-tools/commands/{slug}/"
        parts.append(f"| **{display}** | {cmd_list} | [{display}]({ref_href}) |")

    parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def iter_help_sections_for_commands(commands: Sequence[str]) -> Iterator[HelpSection]:
    """Yield help sections for a specific subset of top-level CLI commands."""
    from repo_release_tools import cli  # noqa: PLC0415

    root = cli.build_parser()
    root_subparsers = _find_subparsers_action(root)
    if root_subparsers is None:
        return

    def walk(
        argv: tuple[str, ...],
        parser: argparse.ArgumentParser,
    ) -> Iterator[HelpSection]:
        yield HelpSection(argv=argv, heading_level=min(2 + len(argv) - 1, 6))
        subparsers = _find_subparsers_action(parser)
        if subparsers is None:
            return
        for name in _ordered_subcommand_names(subparsers):
            child = subparsers.choices[name]
            yield from walk((*argv, name), child)

    for name in commands:
        if name in root_subparsers.choices:
            child = root_subparsers.choices[name]
            yield from walk((name,), child)


def generate_group_reference_markdown(
    group_display_name: str, commands: Sequence[str], output_path: Path = DEFAULT_OUTPUT
) -> str:
    """Return generated reference Markdown for a CLI command group."""
    toc_start, toc_end = _anchor_stub_pair("toc", output_path)
    parts = [
        f"# rrt {group_display_name}",
        "",
        _autogen_note(output_path),
        "",
        toc_start,
        toc_end,
        "",
    ]

    for section in iter_help_sections_for_commands(commands):
        parts.append(f"{'#' * section.heading_level} {section.title}")
        parts.append("")
        if len(section.argv) == 1:
            prose = render_command_docs(section.argv, heading_level=section.heading_level)
            if prose:
                parts.append(prose)
                parts.append("")
        parts.extend(["```text", render_help(section.argv), "```", ""])

    return "\n".join(parts).rstrip() + "\n"


def generate_semantic_branches_markdown() -> str:
    """Return the generated semantic branches topic page."""
    return _render_topic_doc("branch")


def generate_git_markdown() -> str:
    """Return the generated rrt git topic page."""
    return _render_topic_doc("git")


def generate_index_topic_links_markdown() -> str:
    """Return the generated topic-link bullets for docs/src/content/docs/index.mdx."""
    links = [
        "- [rrt branch](/repo-release-tools/commands/branch/) — generated branch naming "
        "model and allowed branch types",
        "- [rrt git](/repo-release-tools/commands/git_cmd/) — generated Git helpers and "
        "workflow shortcuts",
        "- [rrt tree](/repo-release-tools/commands/tree/) — generated guide for `rrt tree` "
        "output modes, ignore behavior, and traversal controls",
        "- [MCP Server](/repo-release-tools/mcp-server/) — MCP install and connect guide",
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
        f"- MCP Server: <{_README_BASE}/docs/mcp-server.md>",
        f"- Agent instructions: <{_README_BASE}/docs/agent-instructions.md>",
    ]
    return "\n".join(links)


# ---------------------------------------------------------------------------
# Config-driven accessors (fall back to built-in defaults when config is absent)
# ---------------------------------------------------------------------------


def _get_command_groups_config(
    cfg_docs: object = None,
) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    """Return command groups from DocsConfig or the built-in RRT defaults."""
    from repo_release_tools.config.model import CommandGroupEntry  # noqa: PLC0415

    if cfg_docs is not None:
        groups = getattr(cfg_docs, "command_groups", ())
        if groups:
            return tuple(
                (e.slug, e.display, e.commands) for e in groups if isinstance(e, CommandGroupEntry)
            )
    return COMMAND_GROUPS_CONFIG


def _get_topic_page_outputs(cfg_docs: object = None) -> dict[str, Path]:
    """Return topic page outputs from DocsConfig or the built-in RRT defaults."""
    from repo_release_tools.config.model import TopicPageEntry  # noqa: PLC0415

    if cfg_docs is not None:
        pages = getattr(cfg_docs, "topic_pages", ())
        if pages:
            return {e.slug: Path(e.output) for e in pages if isinstance(e, TopicPageEntry)}
    return TOPIC_PAGE_OUTPUTS


def _get_title_overrides(cfg_docs: object = None) -> dict[str, str]:
    """Return title overrides from DocsConfig or the built-in RRT defaults."""
    if cfg_docs is not None:
        overrides = getattr(cfg_docs, "title_overrides", {})
        if overrides:
            return dict(overrides)
    return TITLE_OVERRIDES


# ---------------------------------------------------------------------------
# Topic-page output registry
# ---------------------------------------------------------------------------

TOPIC_PAGE_OUTPUTS: dict[str, Path] = {
    "branch": Path("docs/src/content/docs/commands/branch.mdx"),
    "git": Path("docs/src/content/docs/commands/git_cmd.mdx"),
    "tree": Path("docs/src/content/docs/commands/tree.mdx"),
    "hooks": Path("docs/src/content/docs/commands/hooks.mdx"),
    "action": Path("docs/src/content/docs/action.mdx"),
    "skill": Path("docs/src/content/docs/commands/skill.mdx"),
    "install": Path("docs/src/content/docs/commands/install.mdx"),
    "agent-instructions": Path("docs/src/content/docs/agent-instructions.mdx"),
    "doctor": Path("docs/src/content/docs/commands/doctor.mdx"),
    "eol": Path("docs/src/content/docs/commands/eol_check.mdx"),
}


# ---------------------------------------------------------------------------
# Title / description helpers for generated pages
# ---------------------------------------------------------------------------

TITLE_OVERRIDES: dict[str, str] = {
    "rrt-cli": "rrt CLI",
    "branch": "rrt branch",
    "git": "rrt git",
    "tree": "rrt tree",
    "hooks": "rrt hooks",
    "action": "GitHub Action",
    "skill": "rrt skill",
    "install": "rrt install",
    "agent-instructions": "Hook & Action Reference",
    "doctor": "rrt doctor",
    "eol": "rrt eol",
    **{slug: f"rrt {display}" for slug, display, _ in COMMAND_GROUPS_CONFIG},
}

DESCRIPTION_OVERRIDES: dict[str, str] = {
    "rrt-cli": (
        "Generated reference for the full rrt CLI, covering every command group and "
        "argparse option."
    ),
    "branch": (
        "Conventional branch naming model, allowed branch types, and validation rules "
        "for rrt branch."
    ),
    "git": "Git workflow helpers and shortcuts bundled with rrt git.",
    "tree": (
        "Guide to rrt tree output modes, ignore behavior, and traversal controls for "
        "project structure snapshots."
    ),
    "hooks": (
        "Pre-commit and lefthook setup for incremental or squash-based changelog "
        "workflows via rrt-hooks."
    ),
    "action": (
        "CI policy gate wrapping rrt-hooks for branch, commit, and changelog checks in "
        "GitHub Actions."
    ),
    "skill": "Bundled uvx and installed-CLI agent skills managed by rrt skill install.",
    "install": "Installing the rrt CLI and its optional extras with rrt install.",
    "agent-instructions": (
        "Reference for hook and Action enforcement points used by agent-driven workflows."
    ),
    "doctor": "Configuration health checks and diagnostics performed by rrt doctor.",
    "eol": "Runtime end-of-life tracking and warnings surfaced by rrt eol.",
    **{
        slug: f"Generated command reference for the {display} command group."
        for slug, display, _ in COMMAND_GROUPS_CONFIG
    },
}


def _extract_first_h1(text: str) -> str | None:
    """Return the first top-level heading text from *text*, or ``None``."""
    m = re.search(r"(?m)^\s*#\s+(.+)$", text)
    return m[1].strip() if m else None


def _wrap_with_frontmatter(
    output_path: Path,
    render_func: Callable[[], str],
    *,
    title_override: str | None = None,
    slug: str | None = None,
) -> Callable[[], str]:
    """Return a render callable that prefixes generated content with YAML frontmatter.

    The frontmatter contains at least a `title:` and, when a description
    override is registered for *slug*, a `description:` field for Starlight's
    SEO metadata. Starlight derives the page's route from its file path, so no
    explicit permalink/URL field is needed.
    """

    def _wrapped() -> str:
        content = render_func()
        # Determine title: overrides > TITLE_OVERRIDES > first H1 > fallback to filename
        if title_override:
            title = title_override
        elif slug and slug in TITLE_OVERRIDES:
            title = TITLE_OVERRIDES[slug]
        else:
            title = _extract_first_h1(content) or output_path.stem

        # Ensure quotes in title are escaped
        title = title.replace('"', '\\"')

        if output_path.suffix.lower() == ".mdx" and output_path.parent.name == "commands":
            content = _ensure_primary_h1(content, title)

        fm_lines = [f'title: "{title}"']
        description = DESCRIPTION_OVERRIDES.get(slug) if slug else None
        if description:
            description = description.replace('"', '\\"')
            fm_lines.append(f'description: "{description}"')

        frontmatter = "---\n" + "\n".join(fm_lines) + "\n---\n\n"
        return frontmatter + content

    return _wrapped


def _build_generated_doc_targets(cfg_docs: object = None) -> tuple[DocTarget, ...]:
    """Build the registry of generated doc outputs.

    When *cfg_docs* provides non-empty ``command_groups``, ``topic_pages``, or
    ``title_overrides``, those values override the built-in RRT defaults so that
    other projects can drive doc generation entirely from their own config.
    """
    command_groups = _get_command_groups_config(cfg_docs)
    topic_page_outputs = _get_topic_page_outputs(cfg_docs)
    title_overrides = _get_title_overrides(cfg_docs)
    group_ref_outputs: dict[str, Path] = {
        slug: Path(f"docs/src/content/docs/commands/{slug}.mdx") for slug, _, _ in command_groups
    }

    targets: list[DocTarget] = [
        DocTarget(
            DEFAULT_OUTPUT,
            _wrap_with_frontmatter(
                DEFAULT_OUTPUT,
                lambda: generate_markdown(DEFAULT_OUTPUT),
                title_override=title_overrides.get("rrt-cli"),
                slug="rrt-cli",
            ),
        ),
        DocTarget(
            Path("docs/src/content/docs/index.mdx"),
            generate_index_topic_links_markdown,
            anchor_id="index-topic-links",
        ),
        DocTarget(
            Path("README.md"),
            generate_readme_links_markdown,
            anchor_id="readme-links",
        ),
    ]

    for slug, output_path in topic_page_outputs.items():
        render_fn = _wrap_with_frontmatter(
            output_path,
            lambda slug=slug: _render_topic_doc(slug),
            title_override=title_overrides.get(slug),
            slug=slug,
        )
        targets.append(DocTarget(output_path, render_fn))

    for slug, display, commands in command_groups:
        output_path = group_ref_outputs[slug]
        title = f"rrt {display}"
        render_fn = _wrap_with_frontmatter(
            output_path,
            lambda d=display, c=commands, p=output_path: generate_group_reference_markdown(d, c, p),
            title_override=title,
            slug=slug,
        )
        targets.append(DocTarget(output_path, render_fn))

    return tuple(targets)


def _ensure_primary_h1(content: str, title: str) -> str:
    """Ensure *content* has a top-level H1 matching *title*.

    If a top-level H1 exists, it is replaced with ``# <title>``.
    If no top-level H1 exists, one is prepended.
    """
    lines = content.splitlines()
    for idx, line in enumerate(lines):
        if re.match(r"^\s*#\s+.+$", line):
            lines[idx] = f"# {title}"
            return "\n".join(lines).rstrip() + "\n"
    body = content.lstrip("\n")
    return f"# {title}\n\n{body}".rstrip() + "\n"


def validate_generated_pages() -> list[str]:
    """Return consistency issues for generated command pages.

    Rules:
    - top-level generated command pages must include frontmatter
    - top-level generated command pages must include a top-level H1
    """
    issues: list[str] = []
    for target in GENERATED_DOC_TARGETS:
        issues.extend(validate_generated_page(target, target.render()))

    return issues


def validate_generated_page(target: DocTarget, rendered: str) -> list[str]:
    """Return consistency issues for one generated command page rendering."""
    if target.anchor_id is not None:
        return []
    if not (
        target.output_path.suffix.lower() == ".mdx" and target.output_path.parent.name == "commands"
    ):
        return []

    issues: list[str] = []
    if not rendered.startswith("---\n"):
        issues.append(f"{target.output_path}: missing YAML frontmatter")
        return issues

    fm_close = rendered.find("\n---\n")
    if fm_close == -1:
        issues.append(f"{target.output_path}: malformed YAML frontmatter")
        return issues

    body = rendered[fm_close + len("\n---\n") :].lstrip("\n")
    if not body.startswith("# "):
        issues.append(f"{target.output_path}: missing top-level H1")

    return issues


GENERATED_DOC_TARGETS: tuple[DocTarget, ...] = _build_generated_doc_targets()


def iter_generated_doc_targets() -> Iterator[DocTarget]:
    """Yield every generated doc target."""
    yield from GENERATED_DOC_TARGETS


# ---------------------------------------------------------------------------
# Poe task entrypoints (canonical home)
# ---------------------------------------------------------------------------


def _load_cfg_docs() -> object:
    """Load DocsConfig from the current working directory, or return None."""
    from repo_release_tools.config import (
        is_missing_tool_rrt_error,  # noqa: PLC0415
        load_config,  # noqa: PLC0415
    )

    try:
        cfg = load_config(Path.cwd())
        return cfg.docs if cfg is not None else None
    except FileNotFoundError:
        return None
    except ValueError as exc:
        if is_missing_tool_rrt_error(exc):
            return None
        raise


def task_generate() -> int:
    """Write all generated docs to disk."""
    import sys  # noqa: PLC0415

    cfg_docs = _load_cfg_docs()
    targets = _build_generated_doc_targets(cfg_docs)
    exit_code = 0
    for target in targets:
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

    cfg_docs = _load_cfg_docs()
    targets = _build_generated_doc_targets(cfg_docs)
    exit_code = 0
    for target in targets:
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
    cfg = None
    try:
        cfg = load_config(root)
    except FileNotFoundError:
        pass
    except ValueError as exc:
        if not is_missing_tool_rrt_error(exc):
            raise

    if cfg is None:
        sys.stdout.write("No rrt config found; skipping shared_blocks injection.\n")
        return 0

    if cfg.docs is not None and cfg.docs.shared_blocks:
        repo_url = cfg.docs.source_repo_url or ""
        exit_code = 0
        for block in cfg.docs.shared_blocks:
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
                        stale_hint="rrt docs inject --check",
                    ),
                )

        return exit_code

    return 0


def task_inject_shared_blocks() -> int:
    """Write all shared anchor blocks to their target files."""
    return _apply_shared_blocks(check=False)


def task_check_shared_blocks() -> int:
    """Verify all shared anchor blocks are up to date."""
    return _apply_shared_blocks(check=True)
