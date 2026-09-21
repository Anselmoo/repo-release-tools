"""Shape contract for docstrings that are published as documentation.

## Overview

Module docstrings in this package are not internal comments — they are rendered
into published pages by :mod:`repo_release_tools.docs.publisher`. This module
validates that every such docstring follows one skeleton, so the published
surface cannot drift section-by-section the way it did before issue #226.

A doc reaches publication by one of two routes, and both are governed here:

- an explicit ``SOURCE_OWNED_TOPIC_DOCS`` tuple exported by the module
- the ``inspect.getdoc()`` fallback in ``publisher.render_command_docs`` for any
  command module without an explicit entry

## Responsibilities

- collect every published doc with its provenance (``file:line`` and the symbol
  the text actually came from, which ``getattr`` erases)
- assert the required sections exist, in the required order, non-empty
- assert a substantive ``__doc__`` is never orphaned by a named constant
- assert every declaring module is actually wired into publisher's collection
- measure prose register per section against calibrated thresholds

## Examples

```python
from pathlib import Path

from repo_release_tools.config import load_config
from repo_release_tools.docs import skeleton

cfg = load_config(Path.cwd())
issues = skeleton.validate_skeleton(Path("src"), cfg.docs.skeleton)
```

## Caveats

Provenance comes from an AST scan, but the rendered text comes from importing
the module: constants such as ``GIT_DOC`` are built by slicing and re-titling
``__doc__`` at runtime, which no static pass can evaluate faithfully.

Register measurement is a heuristic. It reads only prose paragraphs — headings,
fenced blocks, tables and list items are excluded — and skips any section with
fewer than ``min_sentences_for_register`` sentences, because a mean over three
fragments is noise rather than signal.

## Related docs

- ``docs/src/content/docs/reference/internal-contracts.mdx`` — the cross-surface
  contract this check belongs to
- :mod:`repo_release_tools.docs.publisher` — the renderer this check guards
"""

from __future__ import annotations

import ast
import importlib
import inspect
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from repo_release_tools.docs.formats.markdown import MarkdownLine, parse_markdown_lines

if TYPE_CHECKING:  # pragma: no cover - typing only
    from types import ModuleType

    from repo_release_tools.config.model import DocsSkeletonConfig

SOURCE_OWNED_SYMBOL = "SOURCE_OWNED_TOPIC_DOCS"

# Opt-out marker, shared with tests/commands/test_commands_docstrings.py. A
# module whose docstring is deliberately internal — a maintainer note rather
# than user documentation — declares that by carrying this marker.
DOCS_EXEMPT_MARKER = "rrt:docs-exempt"

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_ORDERED_LIST_RE = re.compile(r"^\d+[.)]\s")
_NON_PROSE_PREFIXES = ("|", "-", "*", "+", ">", "#", ":::")


@dataclass(frozen=True)
class SkeletonEntry:
    """One published doc, with the provenance needed to report on it."""

    slug: str
    module: str
    source_path: Path
    lineno: int
    origin: str
    markdown: str

    @property
    def location(self) -> str:
        """Return a ``path:line`` label for error output."""
        return f"{self.source_path}:{self.lineno}"


@dataclass(frozen=True)
class DocSection:
    """One H2-delimited section of a published doc.

    ``body`` keeps every line, including fenced code, because emptiness and
    register are different questions: an ``## Examples`` section made purely of
    a code block is correct, but contributes no prose to measure.
    """

    title: str
    lineno: int
    body: tuple[MarkdownLine, ...]

    @property
    def is_empty(self) -> bool:
        """Return ``True`` when the section holds no content of any kind."""
        return not any(line.text.strip() for line in self.body)

    @property
    def prose_lines(self) -> tuple[str, ...]:
        """Return only narrative lines, excluding fenced code and headings."""
        return tuple(line.text for line in self.body if line.kind == "text")


# ---------------------------------------------------------------------------
# Markdown structure
# ---------------------------------------------------------------------------


def iter_sections(markdown: str) -> tuple[DocSection, ...]:
    """Split *markdown* into H2 sections, fence-aware.

    Content before the first H2 is returned under an empty title so callers can
    still measure it without mistaking it for a section.
    """
    sections: list[DocSection] = []
    title = ""
    lineno = 1
    body: list[MarkdownLine] = []

    for offset, line in enumerate(parse_markdown_lines(markdown), start=1):
        if line.kind == "heading" and line.level == 2:
            sections.append(DocSection(title=title, lineno=lineno, body=tuple(body)))
            title, lineno, body = line.text, offset, []
            continue
        body.append(line)

    sections.append(DocSection(title=title, lineno=lineno, body=tuple(body)))
    return tuple(sections)


def section_titles(markdown: str) -> tuple[str, ...]:
    """Return the ordered H2 titles in *markdown*."""
    return tuple(s.title for s in iter_sections(markdown) if s.title)


def heading_levels(markdown: str) -> tuple[int, ...]:
    """Return every heading level in *markdown*, fence-aware."""
    return tuple(
        line.level
        for line in parse_markdown_lines(markdown)
        if line.kind == "heading" and line.level is not None
    )


def extract_prose_sentences(body: tuple[str, ...]) -> tuple[str, ...]:
    """Return prose sentences from *body*, excluding non-prose constructs.

    List items, table rows, blockquotes and directive markers are dropped
    wholesale: they are routinely sentence fragments, and averaging their length
    alongside real prose is what makes naive readability metrics meaningless on
    reference documentation.
    """
    paragraphs: list[str] = []
    current: list[str] = []

    for raw in body:
        line = raw.strip()
        if not line or line.startswith(_NON_PROSE_PREFIXES) or _ORDERED_LIST_RE.match(line):
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        current.append(line)

    if current:
        paragraphs.append(" ".join(current))

    sentences: list[str] = []
    for paragraph in paragraphs:
        sentences.extend(
            part for part in _SENTENCE_SPLIT_RE.split(paragraph) if len(part.split()) >= 3
        )
    return tuple(sentences)


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------


def _module_name_for(path: Path, src_root: Path) -> str:
    rel = path.relative_to(src_root).with_suffix("")
    parts = [p for p in rel.parts if p != "__init__"]
    return ".".join(parts)


def _origin_of(node: ast.expr) -> str:
    """Return the symbol a ``SOURCE_OWNED_TOPIC_DOCS`` value came from."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and sub.id != "__doc__":
            return sub.id
    return "__doc__"


def _declared_slugs(tree: ast.Module) -> tuple[tuple[str, str], ...]:
    """Return ``(slug, origin)`` pairs declared by a module's tuple."""
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names = {t.id for t in targets if isinstance(t, ast.Name)}
        if SOURCE_OWNED_SYMBOL not in names or node.value is None:
            continue
        if not isinstance(node.value, ast.Tuple):
            return ()
        pairs: list[tuple[str, str]] = []
        for element in node.value.elts:
            if not isinstance(element, ast.Tuple) or len(element.elts) != 2:
                continue
            slug_node, value_node = element.elts
            if isinstance(slug_node, ast.Constant) and isinstance(slug_node.value, str):
                pairs.append((slug_node.value, _origin_of(value_node)))
        return tuple(pairs)
    return ()


def _symbol_lineno(tree: ast.Module, symbol: str) -> int:
    if symbol == "__doc__":
        return 1
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == symbol for t in node.targets
        ):
            return node.lineno
    return 1


def collect_declared_entries(src_root: Path) -> tuple[SkeletonEntry, ...]:
    """Collect every module-declared published doc under *src_root*."""
    entries: list[SkeletonEntry] = []

    for path in sorted(src_root.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if SOURCE_OWNED_SYMBOL not in source:
            continue
        tree = ast.parse(source)
        declared = _declared_slugs(tree)
        if not declared:
            continue

        module_name = _module_name_for(path, src_root)
        module = importlib.import_module(module_name)
        resolved = dict(getattr(module, SOURCE_OWNED_SYMBOL, ()))

        for slug, origin in declared:
            entries.append(
                SkeletonEntry(
                    slug=slug,
                    module=module_name,
                    source_path=path,
                    lineno=_symbol_lineno(tree, origin),
                    origin=origin,
                    markdown=resolved.get(slug, ""),
                ),
            )

    return tuple(entries)


def collect_fallback_entries(src_root: Path) -> tuple[SkeletonEntry, ...]:
    """Collect command docs published through publisher's ``getdoc`` fallback.

    The command registry is repo-release-tools' own. A downstream project that
    opts into this check must not have rrt's installed command modules graded
    against its docs, so entries are kept only when the module's file actually
    lives under *src_root*.
    """
    from repo_release_tools.docs import publisher  # noqa: PLC0415

    anchor = src_root.resolve()
    modules = cast("dict[str, ModuleType]", publisher._get_command_doc_modules())
    return tuple(
        SkeletonEntry(
            slug=command,
            module=module.__name__,
            source_path=_relative_source_path(Path(module.__file__ or ""), src_root),
            lineno=1,
            origin="__doc__",
            markdown=inspect.getdoc(module) or "",
        )
        for command, module in sorted(modules.items())
        if command not in publisher.COMMAND_DOC_SOURCES
        and anchor in Path(module.__file__ or "").resolve().parents
    )


def _relative_source_path(path: Path, src_root: Path) -> Path:
    """Return *path* relative to *src_root*'s parent when possible."""
    anchor = src_root.resolve().parent
    resolved = path.resolve()
    try:
        return resolved.relative_to(anchor)
    except ValueError:
        return path


def collect_skeleton_entries(src_root: Path) -> tuple[SkeletonEntry, ...]:
    """Collect every published doc, declared or fallback, deduplicated.

    Five docs (``artifacts``, ``docs``, ``fields``, ``install``, ``skill``) are
    reachable by both routes. They are the same text and must be reported once.
    """
    seen: set[tuple[str, str]] = set()
    unique: list[SkeletonEntry] = []

    for entry in (*collect_declared_entries(src_root), *collect_fallback_entries(src_root)):
        # getdoc() dedents and strips where __doc__ does not, so the two routes
        # yield the same prose with different surrounding whitespace.
        key = (entry.module, entry.markdown.strip())
        if key in seen:
            continue
        seen.add(key)
        unique.append(entry)

    return tuple(unique)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _check_required_sections(
    entry: SkeletonEntry,
    cfg: DocsSkeletonConfig,
    titles: tuple[str, ...],
) -> list[str]:
    issues = [
        f"{entry.location}: slug {entry.slug!r} is missing required section '## {required}'"
        for required in cfg.required_sections
        if required not in titles
    ]
    if issues or not titles:
        return issues

    if titles[0] != cfg.opening_section:
        issues.append(
            f"{entry.location}: slug {entry.slug!r} must open with "
            f"'## {cfg.opening_section}', found '## {titles[0]}'",
        )

    if cfg.closing_sections:
        tail = titles[-len(cfg.closing_sections) :]
        if tail != tuple(cfg.closing_sections):
            expected = ", ".join(f"'## {s}'" for s in cfg.closing_sections)
            issues.append(
                f"{entry.location}: slug {entry.slug!r} must end with {expected} in that "
                f"order, found {', '.join(repr(t) for t in tail)}",
            )

    return issues


def _check_section_bodies(
    entry: SkeletonEntry,
    cfg: DocsSkeletonConfig,
    sections: tuple[DocSection, ...],
) -> list[str]:
    return [
        f"{entry.location}: slug {entry.slug!r} has an empty required section '## {section.title}'"
        for section in sections
        if section.title in cfg.required_sections and section.is_empty
    ]


def _check_headings(
    entry: SkeletonEntry,
    cfg: DocsSkeletonConfig,
    *,
    forbid_h1: bool,
) -> list[str]:
    issues: list[str] = []
    levels = heading_levels(entry.markdown)
    h1_count = sum(1 for level in levels if level == 1)

    if h1_count > 1:
        issues.append(
            f"{entry.location}: slug {entry.slug!r} has {h1_count} top-level H1 headings; "
            f"at most one is allowed",
        )
    if forbid_h1 and h1_count:
        issues.append(
            f"{entry.location}: slug {entry.slug!r} must not define its own H1 — the "
            f"publisher injects one from TITLE_OVERRIDES for pages under commands/",
        )

    deepest = max(levels, default=0)
    if deepest > cfg.max_heading_depth:
        issues.append(
            f"{entry.location}: slug {entry.slug!r} uses an H{deepest} heading, deeper than "
            f"the configured maximum of H{cfg.max_heading_depth}; headings are shifted when "
            f"spliced into group pages and would clip at H6",
        )

    return issues


def _check_register(
    entry: SkeletonEntry,
    cfg: DocsSkeletonConfig,
    sections: tuple[DocSection, ...],
) -> list[str]:
    issues: list[str] = []

    for section in sections:
        sentences = extract_prose_sentences(section.prose_lines)
        if len(sentences) < cfg.min_sentences_for_register:
            continue
        mean_words = sum(len(s.split()) for s in sentences) / len(sentences)
        if mean_words > cfg.max_words_per_sentence:
            label = f"'## {section.title}'" if section.title else "the opening prose"
            issues.append(
                f"{entry.location}: slug {entry.slug!r} section {label} averages "
                f"{mean_words:.1f} words per sentence over {len(sentences)} sentences, "
                f"above the limit of {cfg.max_words_per_sentence:.0f}",
            )

    words = len(entry.markdown.split())
    if words:
        density = entry.markdown.count("—") / words * 100
        if density > cfg.max_em_dashes_per_100_words:
            issues.append(
                f"{entry.location}: slug {entry.slug!r} uses {density:.1f} em-dashes per 100 "
                f"words, above the limit of {cfg.max_em_dashes_per_100_words:.1f}",
            )

    return issues


def validate_skeleton_entry(
    entry: SkeletonEntry,
    cfg: DocsSkeletonConfig,
    *,
    forbid_h1: bool = False,
) -> list[str]:
    """Return every skeleton violation for one published doc."""
    if entry.slug in cfg.exempt_slugs:
        return []
    if not entry.markdown.strip():
        return [f"{entry.location}: slug {entry.slug!r} publishes an empty document"]

    sections = iter_sections(entry.markdown)
    titles = tuple(s.title for s in sections if s.title)

    return [
        *_check_required_sections(entry, cfg, titles),
        *_check_section_bodies(entry, cfg, sections),
        *_check_headings(entry, cfg, forbid_h1=forbid_h1),
        *_check_register(entry, cfg, sections),
    ]


def is_substantive_docstring(docstring: str) -> bool:
    """Return ``True`` when *docstring* is documentation rather than a summary.

    A summary docstring is a single paragraph. Anything that goes on to a
    second paragraph is making an explanation, and an explanation that never
    reaches the published page is content a reader will never see. This matches
    the "thin docstring" test already used by ``rrt docs suggest`` and by
    ``tests/commands/test_commands_docstrings.py``.
    """
    paragraphs = [block for block in docstring.strip().split("\n\n") if block.strip()]
    return len(paragraphs) > 1


def check_orphaned_docstrings(entries: tuple[SkeletonEntry, ...]) -> list[str]:
    """Return issues for modules whose substantive ``__doc__`` is never published.

    A named constant may re-title or extend ``__doc__``, but it may not replace
    it — that silently strips the text a contributor sees when they open the
    file. A module whose docstring is deliberately internal opts out with the
    :data:`DOCS_EXEMPT_MARKER`.
    """
    issues: list[str] = []

    for entry in entries:
        if entry.origin == "__doc__":
            continue
        module = importlib.import_module(entry.module)
        docstring = module.__doc__ or ""
        if not is_substantive_docstring(docstring):
            continue
        if DOCS_EXEMPT_MARKER in entry.source_path.read_text(encoding="utf-8"):
            continue
        # git.py and branch.py re-title by dropping the summary paragraph, so
        # compare on the body rather than the whole docstring.
        body = docstring.split("\n\n", 1)[-1].strip()
        if body and body not in entry.markdown:
            issues.append(
                f"{entry.location}: {entry.module}.__doc__ carries {len(docstring.split())} "
                f"words that {entry.origin} does not publish; a constant may extend or "
                f"re-title __doc__ but must not replace it (add a "
                f"'{DOCS_EXEMPT_MARKER}' marker if the docstring is deliberately internal)",
            )

    return issues


def check_collection_coverage(src_root: Path) -> list[str]:
    """Return issues for declaring modules that publisher never collects."""
    from repo_release_tools.docs import publisher  # noqa: PLC0415

    collected = set(publisher.SOURCE_OWNED_TOPIC_DOCS)
    return [
        f"{entry.location}: slug {entry.slug!r} declares {SOURCE_OWNED_SYMBOL} but is not in "
        f"publisher's collection tuple, so its prose is never collected"
        for entry in collect_declared_entries(src_root)
        if entry.slug not in collected
    ]


def validate_skeleton(
    src_root: Path,
    cfg: DocsSkeletonConfig | None,
) -> list[str]:
    """Return every skeleton violation across all published docs.

    Returns an empty list when *cfg* is ``None``: a project that has not
    declared ``[tool.rrt.docs.skeleton]`` has not opted into this contract.
    """
    if cfg is None:
        return []

    from repo_release_tools.docs import publisher  # noqa: PLC0415

    commands_slugs = {
        slug
        for slug, path in publisher.TOPIC_PAGE_OUTPUTS.items()
        if path.parent.name == "commands"
    }

    entries = collect_skeleton_entries(src_root)
    issues: list[str] = []
    for entry in entries:
        issues.extend(
            validate_skeleton_entry(entry, cfg, forbid_h1=entry.slug in commands_slugs),
        )

    if cfg.canonical_docstring:
        issues.extend(check_orphaned_docstrings(collect_declared_entries(src_root)))
    issues.extend(check_collection_coverage(src_root))

    return issues
