"""Tests for the published-docstring skeleton validator."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from repo_release_tools.config.model import DocsSkeletonConfig
from repo_release_tools.docs import skeleton

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

CONFORMING = """# Title

Lead paragraph.

## Overview

What it does.

## Examples

```bash
$ rrt thing
```

## Caveats

Something to watch.

## Related docs

- [other](/other/)
"""


def make_entry(
    markdown: str, *, slug: str = "thing", origin: str = "__doc__"
) -> skeleton.SkeletonEntry:
    """Build a SkeletonEntry around *markdown* without touching the filesystem."""
    return skeleton.SkeletonEntry(
        slug=slug,
        module="pkg.mod",
        source_path=Path("src/pkg/mod.py"),
        lineno=1,
        origin=origin,
        markdown=markdown,
    )


@pytest.fixture
def synthetic_package(tmp_path: Path) -> Iterator[Path]:
    """Create an importable ``synthpkg`` under tmp_path and yield its src root."""
    src = tmp_path / "src"
    pkg = src / "synthpkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text('"""Synthetic package."""\n', encoding="utf-8")
    sys.path.insert(0, str(src))
    try:
        yield src
    finally:
        sys.path.remove(str(src))
        for name in [n for n in sys.modules if n.startswith("synthpkg")]:
            del sys.modules[name]


class TestSkeletonEntry:
    def test_location_joins_path_and_line(self) -> None:
        entry = make_entry("x")
        assert entry.location == "src/pkg/mod.py:1"


class TestIterSections:
    def test_splits_on_h2_and_keeps_preamble(self) -> None:
        sections = skeleton.iter_sections(CONFORMING)
        assert [s.title for s in sections] == [
            "",
            "Overview",
            "Examples",
            "Caveats",
            "Related docs",
        ]

    def test_records_heading_line_numbers(self) -> None:
        overview = skeleton.iter_sections(CONFORMING)[1]
        assert overview.lineno == 5

    def test_fenced_content_is_retained_in_body(self) -> None:
        examples = next(s for s in skeleton.iter_sections(CONFORMING) if s.title == "Examples")
        assert any("rrt thing" in line.text for line in examples.body)

    def test_section_of_only_code_is_not_empty(self) -> None:
        examples = next(s for s in skeleton.iter_sections(CONFORMING) if s.title == "Examples")
        assert not examples.is_empty

    def test_section_with_no_content_is_empty(self) -> None:
        sections = skeleton.iter_sections("## Overview\n\n## Examples\n\ntext\n")
        assert sections[1].is_empty

    def test_prose_lines_exclude_fenced_code(self) -> None:
        examples = next(s for s in skeleton.iter_sections(CONFORMING) if s.title == "Examples")
        assert all("rrt thing" not in line for line in examples.prose_lines)


class TestHeadingHelpers:
    def test_section_titles_skips_preamble(self) -> None:
        assert skeleton.section_titles(CONFORMING) == (
            "Overview",
            "Examples",
            "Caveats",
            "Related docs",
        )

    def test_heading_levels_ignores_comments_in_fences(self) -> None:
        text = "# Real\n\n```bash\n# not a heading\n```\n"
        assert skeleton.heading_levels(text) == (1,)


class TestExtractProseSentences:
    def test_splits_paragraph_into_sentences(self) -> None:
        got = skeleton.extract_prose_sentences(("One two three. Four five six seven.",))
        assert len(got) == 2

    def test_drops_list_items_and_tables(self) -> None:
        body = ("- a bullet item here", "| col | col |", "1. ordered item here", "> quoted line")
        assert skeleton.extract_prose_sentences(body) == ()

    def test_drops_fragments_under_three_words(self) -> None:
        assert skeleton.extract_prose_sentences(("Hi. Nope.",)) == ()

    def test_blank_line_breaks_paragraph(self) -> None:
        body = ("First sentence here", "", "Second sentence here")
        assert len(skeleton.extract_prose_sentences(body)) == 2


class TestRequiredSections:
    def test_reports_each_missing_section(self) -> None:
        issues = skeleton.validate_skeleton_entry(
            make_entry("## Overview\n\ntext\n"), DocsSkeletonConfig()
        )
        assert sum("missing required section" in i for i in issues) == 3

    def test_conforming_document_has_no_issues(self) -> None:
        assert skeleton.validate_skeleton_entry(make_entry(CONFORMING), DocsSkeletonConfig()) == []

    def test_wrong_opening_section_is_reported(self) -> None:
        text = CONFORMING.replace("## Overview", "## Setup").replace(
            "## Caveats",
            "## Overview\n\nfiller\n\n## Caveats",
        )
        issues = skeleton.validate_skeleton_entry(make_entry(text), DocsSkeletonConfig())
        assert any("must open with" in i for i in issues)

    def test_wrong_closing_order_is_reported(self) -> None:
        text = "## Overview\n\na\n\n## Examples\n\nb\n\n## Related docs\n\nc\n\n## Caveats\n\nd\n"
        issues = skeleton.validate_skeleton_entry(make_entry(text), DocsSkeletonConfig())
        assert any("must end with" in i for i in issues)

    def test_empty_required_section_is_reported(self) -> None:
        text = "## Overview\n\n## Examples\n\nb\n\n## Caveats\n\nc\n\n## Related docs\n\nd\n"
        issues = skeleton.validate_skeleton_entry(make_entry(text), DocsSkeletonConfig())
        assert any("empty required section" in i for i in issues)

    def test_empty_document_is_reported_once(self) -> None:
        issues = skeleton.validate_skeleton_entry(make_entry("   "), DocsSkeletonConfig())
        assert issues == ["src/pkg/mod.py:1: slug 'thing' publishes an empty document"]

    def test_exempt_slug_is_skipped(self) -> None:
        cfg = DocsSkeletonConfig(exempt_slugs=("thing",))
        assert skeleton.validate_skeleton_entry(make_entry(""), cfg) == []


class TestHeadingRules:
    def test_multiple_h1_is_reported(self) -> None:
        text = CONFORMING + "\n# Second\n"
        issues = skeleton.validate_skeleton_entry(make_entry(text), DocsSkeletonConfig())
        assert any("top-level H1 headings" in i for i in issues)

    def test_h1_forbidden_for_commands_pages(self) -> None:
        issues = skeleton.validate_skeleton_entry(
            make_entry(CONFORMING),
            DocsSkeletonConfig(),
            forbid_h1=True,
        )
        assert any("must not define its own H1" in i for i in issues)

    def test_heading_deeper_than_maximum_is_reported(self) -> None:
        text = CONFORMING + "\n#### Too deep\n\nbody\n"
        issues = skeleton.validate_skeleton_entry(make_entry(text), DocsSkeletonConfig())
        assert any("deeper than" in i for i in issues)


class TestRegister:
    def test_long_sentences_are_reported(self) -> None:
        sentence = " ".join(["word"] * 30) + "."
        text = CONFORMING.replace("What it does.", "\n\n".join([sentence] * 4))
        issues = skeleton.validate_skeleton_entry(make_entry(text), DocsSkeletonConfig())
        assert any("words per sentence" in i for i in issues)

    def test_small_sections_are_not_measured(self) -> None:
        sentence = " ".join(["word"] * 40) + "."
        text = CONFORMING.replace("What it does.", sentence)
        issues = skeleton.validate_skeleton_entry(make_entry(text), DocsSkeletonConfig())
        assert not any("words per sentence" in i for i in issues)

    def test_preamble_is_labelled_when_measured(self) -> None:
        sentence = " ".join(["word"] * 30) + "."
        text = "\n\n".join([sentence] * 4) + "\n\n" + CONFORMING
        issues = skeleton.validate_skeleton_entry(make_entry(text), DocsSkeletonConfig())
        assert any("the opening prose" in i for i in issues)

    def test_em_dash_density_is_reported(self) -> None:
        text = CONFORMING.replace("What it does.", "a — b — c — d — e")
        issues = skeleton.validate_skeleton_entry(make_entry(text), DocsSkeletonConfig())
        assert any("em-dashes per 100" in i for i in issues)

    def test_register_thresholds_are_configurable(self) -> None:
        sentence = " ".join(["word"] * 30) + "."
        text = CONFORMING.replace("What it does.", "\n\n".join([sentence] * 4))
        cfg = DocsSkeletonConfig(max_words_per_sentence=99.0, max_em_dashes_per_100_words=99.0)
        assert not any(
            "words per sentence" in i
            for i in skeleton.validate_skeleton_entry(make_entry(text), cfg)
        )


class TestIsSubstantiveDocstring:
    @pytest.mark.parametrize(
        ("doc", "expected"),
        [
            ("Single summary line.", False),
            ("", False),
            ("Summary.\n\nA second paragraph of explanation.", True),
            ("Summary.\n\n\n\nSecond paragraph.", True),
        ],
    )
    def test_paragraph_count_decides(self, doc: str, expected: bool) -> None:
        assert skeleton.is_substantive_docstring(doc) is expected


class TestCollection:
    def test_collects_declared_entry_from_docstring(self, synthetic_package: Path) -> None:
        mod = synthetic_package / "synthpkg" / "plain.py"
        mod.write_text(
            '"""Summary.\n\n## Overview\n\nbody\n"""\n\n'
            'SOURCE_OWNED_TOPIC_DOCS = (("plain", __doc__ or ""),)\n',
            encoding="utf-8",
        )
        entries = skeleton.collect_declared_entries(synthetic_package)
        assert [(e.slug, e.origin, e.lineno) for e in entries] == [("plain", "__doc__", 1)]

    def test_collects_declared_entry_from_constant(self, synthetic_package: Path) -> None:
        mod = synthetic_package / "synthpkg" / "viaconst.py"
        mod.write_text(
            '"""Summary."""\n\nTHING_DOC = "## Overview\\n\\nbody\\n"\n'
            'SOURCE_OWNED_TOPIC_DOCS = (("viaconst", THING_DOC),)\n',
            encoding="utf-8",
        )
        entry = skeleton.collect_declared_entries(synthetic_package)[0]
        assert (entry.origin, entry.lineno) == ("THING_DOC", 3)

    def test_annotated_assignment_is_collected(self, synthetic_package: Path) -> None:
        mod = synthetic_package / "synthpkg" / "annotated.py"
        mod.write_text(
            '"""Summary."""\n\n'
            "SOURCE_OWNED_TOPIC_DOCS: tuple[tuple[str, str], ...] = "
            '(("annotated", __doc__ or ""),)\n',
            encoding="utf-8",
        )
        assert skeleton.collect_declared_entries(synthetic_package)[0].slug == "annotated"

    def test_non_tuple_declaration_yields_nothing(self, synthetic_package: Path) -> None:
        mod = synthetic_package / "synthpkg" / "weird.py"
        mod.write_text('"""S."""\n\nSOURCE_OWNED_TOPIC_DOCS = dict()\n', encoding="utf-8")
        assert skeleton.collect_declared_entries(synthetic_package) == ()

    def test_file_without_symbol_is_ignored(self, synthetic_package: Path) -> None:
        (synthetic_package / "synthpkg" / "quiet.py").write_text('"""S."""\n', encoding="utf-8")
        assert skeleton.collect_declared_entries(synthetic_package) == ()


class TestDeclaredSlugParsing:
    """Unit-level coverage of the AST scan, independent of importability."""

    @staticmethod
    def parse(source: str) -> tuple[tuple[str, str], ...]:
        return skeleton._declared_slugs(ast.parse(source))

    def test_starred_and_short_elements_are_skipped(self) -> None:
        source = "EXTRA = ()\nSOURCE_OWNED_TOPIC_DOCS = (('ok', DOC), ('a', 'b', 'c'), *EXTRA)\n"
        assert self.parse(source) == (("ok", "DOC"),)

    def test_non_string_slug_is_skipped(self) -> None:
        assert self.parse("SOURCE_OWNED_TOPIC_DOCS = ((1, DOC), ('ok', DOC))\n") == (("ok", "DOC"),)

    def test_non_tuple_value_yields_nothing(self) -> None:
        assert self.parse("SOURCE_OWNED_TOPIC_DOCS = dict()\n") == ()

    def test_absent_symbol_yields_nothing(self) -> None:
        assert self.parse("OTHER = ((1, 2),)\n") == ()

    def test_docstring_origin_detected_over_constant(self) -> None:
        assert self.parse("SOURCE_OWNED_TOPIC_DOCS = (('s', __doc__ or ''),)\n") == (
            ("s", "__doc__"),
        )

    def test_bare_annotation_without_value_is_skipped(self) -> None:
        assert self.parse("SOURCE_OWNED_TOPIC_DOCS: tuple[str, ...]\n") == ()


class TestSymbolLineno:
    def test_docstring_symbol_is_line_one(self) -> None:
        assert skeleton._symbol_lineno(ast.parse("X = 1\n"), "__doc__") == 1

    def test_missing_symbol_falls_back_to_line_one(self) -> None:
        assert skeleton._symbol_lineno(ast.parse("X = 1\n"), "ABSENT") == 1

    def test_found_symbol_returns_its_line(self) -> None:
        assert skeleton._symbol_lineno(ast.parse("A = 1\nB = 2\n"), "B") == 2


class TestRelativeSourcePath:
    def test_returns_relative_path_when_inside_root(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        (src / "pkg").mkdir(parents=True)
        target = src / "pkg" / "mod.py"
        target.touch()
        assert skeleton._relative_source_path(target, src) == Path("src/pkg/mod.py")

    def test_returns_original_when_outside_root(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        outside = Path("/usr/lib/python3/other.py")
        assert skeleton._relative_source_path(outside, src) == outside


class TestValidateSkeleton:
    def test_absent_config_disables_the_check(self) -> None:
        assert skeleton.validate_skeleton(Path("src"), None) == []

    def test_real_corpus_reports_only_known_issue_classes(self) -> None:
        issues = skeleton.validate_skeleton(Path("src"), DocsSkeletonConfig())
        known = (
            "missing required section",
            "must open with",
            "must end with",
            "empty required section",
            "H1",
            "deeper than",
            "words per sentence",
            "em-dashes",
            "not in publisher",
            "does not publish",
            "publishes an empty document",
        )
        assert all(any(k in issue for k in known) for issue in issues)

    def test_every_declaring_module_is_collected(self) -> None:
        """Regression guard: a declaration publisher never collects is dead prose."""
        assert skeleton.check_collection_coverage(Path("src")) == []

    def test_collection_coverage_flags_an_uncollected_module(
        self,
        synthetic_package: Path,
    ) -> None:
        mod = synthetic_package / "synthpkg" / "uncollected.py"
        mod.write_text(
            '"""Summary."""\n\n'
            'DOC = "## Overview\\n\\nbody\\n"\n'
            'SOURCE_OWNED_TOPIC_DOCS = (("nowhere", DOC),)\n',
            encoding="utf-8",
        )
        issues = skeleton.check_collection_coverage(synthetic_package)
        assert len(issues) == 1
        assert "'nowhere'" in issues[0]

    def test_entries_are_deduplicated_across_routes(self) -> None:
        entries = skeleton.collect_skeleton_entries(Path("src"))
        keys = [(e.module, e.markdown.strip()) for e in entries]
        assert len(keys) == len(set(keys))


class TestOrphanedDocstrings:
    def test_docstring_origin_is_skipped(self) -> None:
        entry = make_entry("text", origin="__doc__")
        assert skeleton.check_orphaned_docstrings((entry,)) == []

    def test_exempt_marker_suppresses_the_issue(self, synthetic_package: Path) -> None:
        mod = synthetic_package / "synthpkg" / "exempted.py"
        mod.write_text(
            '"""Summary.\n\nInternal rationale paragraph that is not documentation.\n"""\n\n'
            "# rrt:docs-exempt\n"
            'OTHER_DOC = "## Overview\\n\\nbody\\n"\n'
            'SOURCE_OWNED_TOPIC_DOCS = (("exempted", OTHER_DOC),)\n',
            encoding="utf-8",
        )
        entries = skeleton.collect_declared_entries(synthetic_package)
        assert skeleton.check_orphaned_docstrings(entries) == []

    def test_orphaned_substantive_docstring_is_reported(self, synthetic_package: Path) -> None:
        mod = synthetic_package / "synthpkg" / "orphan.py"
        mod.write_text(
            '"""Summary.\n\nReal documentation paragraph that never ships anywhere.\n"""\n\n'
            'OTHER_DOC = "## Overview\\n\\nunrelated\\n"\n'
            'SOURCE_OWNED_TOPIC_DOCS = (("orphan", OTHER_DOC),)\n',
            encoding="utf-8",
        )
        entries = skeleton.collect_declared_entries(synthetic_package)
        issues = skeleton.check_orphaned_docstrings(entries)
        assert len(issues) == 1
        assert "does not publish" in issues[0]

    def test_retitled_docstring_body_is_accepted(self, synthetic_package: Path) -> None:
        mod = synthetic_package / "synthpkg" / "retitled.py"
        mod.write_text(
            '"""Summary line.\n\n## Overview\n\nThe body paragraph.\n"""\n\n'
            'RETITLED_DOC = "# New title\\n\\n" + (__doc__ or "").split("\\n\\n", 1)[1]\n'
            'SOURCE_OWNED_TOPIC_DOCS = (("retitled", RETITLED_DOC),)\n',
            encoding="utf-8",
        )
        entries = skeleton.collect_declared_entries(synthetic_package)
        assert skeleton.check_orphaned_docstrings(entries) == []

    def test_thin_docstring_is_not_substantive(self, synthetic_package: Path) -> None:
        mod = synthetic_package / "synthpkg" / "thin.py"
        mod.write_text(
            '"""Just a summary."""\n\n'
            'OTHER_DOC = "## Overview\\n\\nbody\\n"\n'
            'SOURCE_OWNED_TOPIC_DOCS = (("thin", OTHER_DOC),)\n',
            encoding="utf-8",
        )
        entries = skeleton.collect_declared_entries(synthetic_package)
        assert skeleton.check_orphaned_docstrings(entries) == []


class TestDocsSkeletonConfigValidation:
    def test_defaults_are_valid(self) -> None:
        DocsSkeletonConfig().validate()

    @pytest.mark.parametrize(
        ("make_config", "message"),
        [
            (lambda: DocsSkeletonConfig(required_sections=()), "must not be empty"),
            (lambda: DocsSkeletonConfig(required_sections=("A", "A")), "duplicates"),
            (lambda: DocsSkeletonConfig(opening_section="Nope"), "opening_section"),
            (lambda: DocsSkeletonConfig(closing_sections=("Nope",)), "closing_sections"),
            (lambda: DocsSkeletonConfig(max_heading_depth=1), "max_heading_depth"),
            (lambda: DocsSkeletonConfig(max_heading_depth=7), "max_heading_depth"),
            (lambda: DocsSkeletonConfig(max_words_per_sentence=0), "max_words_per_sentence"),
            (
                lambda: DocsSkeletonConfig(max_em_dashes_per_100_words=-1),
                "max_em_dashes_per_100_words",
            ),
            (
                lambda: DocsSkeletonConfig(min_sentences_for_register=0),
                "min_sentences_for_register",
            ),
        ],
    )
    def test_invalid_values_raise(
        self,
        make_config: Callable[[], DocsSkeletonConfig],
        message: str,
    ) -> None:
        with pytest.raises(ValueError, match=message):
            make_config().validate()
