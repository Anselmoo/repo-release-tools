#!/usr/bin/env python3
"""Generate the CLI reference and topic docs from live source data."""

from __future__ import annotations

import argparse
import inspect
import os
import sys
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

import repo_release_tools as rrt_package
from repo_release_tools import action as action_module
from repo_release_tools import cli
from repo_release_tools import eol as eol_module
from repo_release_tools import git as git_helpers
from repo_release_tools import hooks as hooks_module
from repo_release_tools.commands import branch as branch_module
from repo_release_tools.commands import doctor as doctor_module
from repo_release_tools.commands import eol_check as eol_check_module
from repo_release_tools.commands import skill as skill_module


class SupportsWrite(Protocol):
    """Minimal text stream protocol for stdout/stderr injection."""

    def write(self, text: str) -> object:
        """Write text to the underlying stream-like object."""


DEFAULT_OUTPUT = Path("docs/rrt-cli.md")
PINNED_COLUMNS = "120"
AUTOGEN_NOTE = (
    "<!-- Auto-generated from repo_release_tools.cli.build_parser(); "
    "run `poe docs-generate` to refresh. -->"
)


@dataclass(frozen=True)
class HelpSection:
    """One CLI help section to render in the generated Markdown."""

    argv: tuple[str, ...]
    heading_level: int

    @property
    def title(self) -> str:
        """Return the Markdown title for this section."""
        if not self.argv:
            return "Global help"
        return f"`{' '.join(('rrt', *self.argv))}`"


@dataclass(frozen=True)
class DocTarget:
    """One generated docs output and the callable that renders it."""

    output_path: Path
    render: Callable[[], str]


@dataclass(frozen=True)
class CommandDocSource:
    """A renderer for a top-level command's long-form docs."""

    render: Callable[[], str]


def _find_subparsers_action(
    parser: argparse.ArgumentParser,
) -> argparse._SubParsersAction | None:
    """Return the parser's subparsers action when present."""
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return cast(argparse._SubParsersAction, action)
    return None


def _command_group_order() -> list[str]:
    """Return top-level commands in the user-facing grouped help order."""
    ordered: list[str] = []
    seen: set[str] = set()
    for names in cli.COMMAND_GROUPS.values():
        for name in names:
            if name in seen:
                continue
            seen.add(name)
            ordered.append(name)
    return ordered


COMMAND_DOC_MODULES: dict[str, object] = {
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
}

def _collect_source_owned_topic_docs(modules: Sequence[object]) -> dict[str, str]:
    """Collect source-owned topic docs exported by modules."""
    collected: dict[str, str] = {}
    for module in modules:
        for slug, markdown in getattr(module, "SOURCE_OWNED_TOPIC_DOCS", ()):
            collected[slug] = markdown
    return collected


SOURCE_OWNED_TOPIC_DOCS = _collect_source_owned_topic_docs(
    (rrt_package, branch_module, git_helpers, hooks_module, action_module, skill_module,
     doctor_module, eol_module)
)


def _render_topic_doc(slug: str) -> str:
    """Return a source-owned topic doc by slug."""
    return SOURCE_OWNED_TOPIC_DOCS[slug]

COMMAND_DOC_SOURCES: dict[str, CommandDocSource] = {
    "branch": CommandDocSource(render=lambda: _render_topic_doc("semantic-branches")),
    "git": CommandDocSource(render=lambda: _render_topic_doc("git-magic")),
    "doctor": CommandDocSource(render=lambda: _render_topic_doc("doctor")),
    "eol": CommandDocSource(render=lambda: inspect.getdoc(eol_check_module) or ""),
}


def _heading_level(line: str) -> int | None:
    """Return the Markdown heading level for *line*, or None if it is not a heading."""
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
    """Shift Markdown headings in *text* so the shallowest one nests under *min_level*."""
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


def render_command_docs(argv: Sequence[str], *, heading_level: int) -> str:
    """Return Markdown docs for a top-level command section, or an empty string."""
    if len(argv) != 1:
        return ""
    command_name = argv[0]
    source = COMMAND_DOC_SOURCES.get(command_name)
    if source is not None:
        docstring = source.render()
    else:
        module = COMMAND_DOC_MODULES.get(command_name)
        if module is None:
            return ""
        docstring = inspect.getdoc(module) or ""
    if not docstring.strip():
        return ""
    return _normalize_markdown_headings(docstring, min_level=heading_level + 1)


def _ordered_subcommand_names(
    action: argparse._SubParsersAction,
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
    parser = cli.build_parser()
    current = parser
    for part in argv:
        action = _find_subparsers_action(current)
        if action is None or part not in action.choices:
            joined = " ".join(("rrt", *argv)).strip()
            raise KeyError(f"unknown parser path: {joined}")
        current = cast(argparse.ArgumentParser, action.choices[part])
    return current


def iter_help_sections() -> Iterator[HelpSection]:
    """Yield the root and all nested command help sections."""
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
            child = cast(argparse.ArgumentParser, subparsers.choices[name])
            yield from walk((*argv, name), child)

    for name in _ordered_subcommand_names(root_subparsers, preferred=_command_group_order()):
        child = cast(argparse.ArgumentParser, root_subparsers.choices[name])
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
    with pinned_help_environment():
        parser = _resolve_parser(argv)
        return cli._strip_ansi(parser.format_help()).rstrip()


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
        "Use `poe docs-generate` to rewrite this file or `poe docs-check` to",
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
    return _render_topic_doc("semantic-branches")


def generate_git_magic_markdown() -> str:
    """Return the generated Git magic topic page."""
    return _render_topic_doc("git-magic")


TOPIC_PAGE_OUTPUTS: dict[str, Path] = {
    "index": Path("docs/index.md"),
    "semantic-branches": Path("docs/semantic-branches.md"),
    "git-magic": Path("docs/git-magic.md"),
    "pre-commit": Path("docs/pre-commit.md"),
    "github-action": Path("docs/github-action.md"),
    "skill": Path("docs/skill.md"),
    "agent-instructions": Path("docs/agent-instructions.md"),
    "doctor": Path("docs/doctor.md"),
    "eol": Path("docs/eol.md"),
}


def _build_generated_doc_targets() -> tuple[DocTarget, ...]:
    """Build the registry of generated docs outputs."""
    targets = [DocTarget(DEFAULT_OUTPUT, generate_markdown)]
    for slug, output_path in TOPIC_PAGE_OUTPUTS.items():
        targets.append(DocTarget(output_path, lambda slug=slug: _render_topic_doc(slug)))
    return tuple(targets)


GENERATED_DOC_TARGETS: tuple[DocTarget, ...] = _build_generated_doc_targets()


def iter_generated_doc_targets() -> Iterator[DocTarget]:
    """Yield every generated docs target and its rendered Markdown."""
    yield from GENERATED_DOC_TARGETS


def apply_generated_docs(
    content: str,
    *,
    output_path: Path,
    check: bool,
    write: bool,
    fail_on_change: bool,
    stdout: SupportsWrite[str],
    stderr: SupportsWrite[str],
) -> int:
    """Check and/or write generated docs, returning the desired exit code."""
    current = output_path.read_text(encoding="utf-8") if output_path.exists() else None
    if current == content:
        stdout.write(f"{output_path} is up-to-date.\n")
        return 0

    if check and not write:
        stderr.write(f"{output_path} is stale. Run: poe docs-generate\n")
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")

    if fail_on_change:
        stderr.write(
            f"Updated {output_path}. Review the generated diff and re-stage the file before retrying.\n"
        )
        return 1

    stdout.write(f"Wrote {output_path}.\n")
    return 0


def task_generate() -> int:
    """Poe task entrypoint for writing all generated docs."""
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
            ),
        )
    return exit_code


def task_check() -> int:
    """Poe task entrypoint for verifying all generated docs."""
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
            ),
        )
    return exit_code


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the generator CLI parser."""
    parser = argparse.ArgumentParser(description="Generate docs/rrt-cli.md from the live rrt parser.")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Destination Markdown file. Defaults to docs/rrt-cli.md.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the generated content differs from the on-disk file.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write the generated content to disk. This is the default when --check is not used.",
    )
    parser.add_argument(
        "--fail-on-change",
        action="store_true",
        help="After writing updated content, exit non-zero so hook workflows stop for restaging.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI docs generator."""
    args = build_arg_parser().parse_args(list(argv) if argv is not None else None)
    write = args.write or not args.check
    return apply_generated_docs(
        generate_markdown(),
        output_path=args.output,
        check=args.check,
        write=write,
        fail_on_change=args.fail_on_change,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )


if __name__ == "__main__":
    raise SystemExit(main())
