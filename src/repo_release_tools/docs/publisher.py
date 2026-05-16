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
from repo_release_tools.commands import doctor as doctor_module
from repo_release_tools.commands import eol_check as eol_check_module
from repo_release_tools.commands import install_cmd as install_module
from repo_release_tools.commands import skill as skill_module
from repo_release_tools.commands import toc as toc_module
from repo_release_tools.commands import tree as tree_module
from repo_release_tools.config import is_missing_tool_rrt_error
from repo_release_tools.docs.markdown import heading_level, normalize_markdown_headings
from repo_release_tools.integrations import action as action_module
from repo_release_tools.tools.inject import apply_generated_docs as apply_generated_docs
from repo_release_tools.workflow import git as git_helpers
from repo_release_tools.workflow import hooks as hooks_module

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
        git_helpers,
        hooks_module,
        action_module,
        skill_module,
        doctor_module,
        install_module,
        eol_module,
        tree_module,
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
        "install": cli.install_cmd,
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


def generate_markdown() -> str:
    """Return the generated CLI reference Markdown."""
    parts = [
        "# rrt CLI",
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
            ],
        )
        if prose:
            parts.extend([prose, ""])
        parts.extend(
            [
                "```text",
                render_help(section.argv),
                "```",
                "",
            ],
        )

    return "\n".join(parts).rstrip() + "\n"


def generate_semantic_branches_markdown() -> str:
    """Return the generated semantic branches topic page."""
    return _render_topic_doc("branch")


def generate_git_markdown() -> str:
    """Return the generated rrt git topic page."""
    return _render_topic_doc("git")


def generate_index_topic_links_markdown() -> str:
    """Return the generated topic-link bullets for docs/index.md."""
    links = [
        "- [rrt branch](commands/branch.md) — generated branch naming model and allowed branch types",
        "- [rrt git](commands/git_cmd.md) — generated Git helpers and workflow shortcuts",
        "- [rrt tree](commands/tree.md) — generated guide for `rrt tree` output modes, "
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
    "install": Path("docs/commands/install.md"),
    "agent-instructions": Path("docs/agent-instructions.md"),
    "doctor": Path("docs/commands/doctor.md"),
    "eol": Path("docs/commands/eol_check.md"),
}


# ---------------------------------------------------------------------------
# Title / permalink helpers for generated pages
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
}


def _extract_first_h1(text: str) -> str | None:
    """Return the first top-level heading text from *text*, or ``None``."""
    m = re.search(r"(?m)^\s*#\s+(.+)$", text)
    return m[1].strip() if m else None


def _compute_permalink_for_output(output_path: Path) -> str:
    """Compute a reasonable permalink for *output_path* when under `docs/`.

    Examples:
    - `docs/index.md` -> `/`
    - `docs/commands/rrt-cli.md` -> `/commands/rrt-cli/`
    """
    try:
        rel = output_path.relative_to("docs")
    except ValueError:
        return ""
    if rel.name == "index.md":
        return "/"
    # drop the suffix and produce a posix path with trailing slash
    return "/" + str(rel.with_suffix("")).replace(os.sep, "/") + "/"


def _wrap_with_frontmatter(
    output_path: Path,
    render_func: Callable[[], str],
    *,
    title_override: str | None = None,
    slug: str | None = None,
) -> Callable[[], str]:
    """Return a render callable that prefixes generated content with YAML frontmatter.

    The frontmatter contains at least a `title:` and, when applicable, a
    `permalink:` so Jekyll/minima uses a stable label and URL for the page.
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

        if output_path.suffix.lower() == ".md" and output_path.parts[:2] == ("docs", "commands"):
            content = _ensure_primary_h1(content, title)

        permalink = _compute_permalink_for_output(output_path)

        fm_lines = [f'title: "{title}"']
        if permalink:
            fm_lines.append(f'permalink: "{permalink}"')

        frontmatter = "---\n" + "\n".join(fm_lines) + "\n---\n\n"
        return frontmatter + content

    return _wrapped


def _build_generated_doc_targets() -> tuple[DocTarget, ...]:
    """Build the registry of generated doc outputs."""
    targets: list[DocTarget] = [
        DocTarget(
            DEFAULT_OUTPUT,
            _wrap_with_frontmatter(
                DEFAULT_OUTPUT,
                generate_markdown,
                title_override=TITLE_OVERRIDES.get("rrt-cli"),
                slug="rrt-cli",
            ),
        ),
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
        render_fn = _wrap_with_frontmatter(
            output_path,
            lambda slug=slug: _render_topic_doc(slug),
            title_override=TITLE_OVERRIDES.get(slug),
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
    if target.output_path.parts[:2] != ("docs", "commands"):
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
        repo_url = "https://github.com/Anselmoo/repo-release-tools"
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
