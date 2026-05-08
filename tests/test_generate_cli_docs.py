from __future__ import annotations

import importlib
import io
import os
from pathlib import Path
from types import ModuleType

import pytest


def _load_generator_module() -> ModuleType:
    """Return a freshly-reloaded docs_publisher module for test isolation."""
    import repo_release_tools.docs.publisher as pub

    importlib.reload(pub)
    return pub


def test_iter_help_sections_covers_root_commands_and_nested_subcommands() -> None:
    docs = _load_generator_module()

    sections = list(docs.iter_help_sections())
    argvs = [section.argv for section in sections]

    assert argvs[0] == ()
    assert ("branch",) in argvs
    assert ("branch", "new") in argvs
    assert ("git", "diff") in argvs
    assert ("ci-version", "compute") in argvs
    assert ("skill", "install") in argvs


def test_generate_markdown_has_stable_sections_without_ansi_sequences() -> None:
    docs = _load_generator_module()

    content = docs.generate_markdown()

    assert content.startswith("# rrt CLI\n")
    assert "## Global help" in content
    assert "## `rrt branch`" in content
    assert "conventional branches" in content
    assert "rrt git" in content
    assert "### `rrt branch new`" in content
    assert "### `rrt git diff`" in content
    assert "### `rrt ci-version compute`" in content
    assert "### `rrt skill install`" in content
    assert "RRT CLI" not in content
    assert "\x1b[" not in content


def test_render_command_docs_only_for_top_level_commands() -> None:
    docs = _load_generator_module()

    class DummyModule:
        __doc__ = "# Overview\n\nParagraph.\n\n## Details\n\nMore."

    setattr(docs, "COMMAND_DOC_MODULES", {"branch": DummyModule})
    setattr(docs, "COMMAND_DOC_SOURCES", {})

    rendered = docs.render_command_docs(("branch",), heading_level=2)

    assert rendered == "### Overview\n\nParagraph.\n\n#### Details\n\nMore."
    assert docs.render_command_docs((), heading_level=2) == ""
    assert docs.render_command_docs(("branch", "new"), heading_level=3) == ""


def test_render_command_docs_prefers_source_owned_topic_docs_for_branch_and_git() -> None:
    docs = _load_generator_module()

    branch_rendered = docs.render_command_docs(("branch",), heading_level=2)
    git_rendered = docs.render_command_docs(("git",), heading_level=2)

    assert "conventional branches" in branch_rendered
    assert "rrt git" in git_rendered
    assert "branch helpers for repo-release-tools" not in branch_rendered
    assert "Git helpers for repo-release-tools" not in git_rendered


def test_generate_markdown_places_command_docs_before_help_block() -> None:
    docs = _load_generator_module()
    setattr(
        docs,
        "iter_help_sections",
        lambda: iter([docs.HelpSection(argv=("branch",), heading_level=2)]),
    )
    setattr(docs, "render_command_docs", lambda argv, heading_level: "### Overview\n\nDoc text")
    setattr(docs, "render_help", lambda argv: "Usage: rrt branch")

    content = docs.generate_markdown()

    assert "## `rrt branch`\n\n### Overview\n\nDoc text\n\n```text" in content
    assert content.index("Doc text") < content.index("```text")


def test_heading_level_rejects_invalid_heading_variants() -> None:
    docs = _load_generator_module()

    assert docs._heading_level("####### Too many") is None
    assert docs._heading_level("###No space") is None


def test_normalize_markdown_headings_returns_trimmed_text_without_headings() -> None:
    docs = _load_generator_module()

    text = "plain text\n\n```python\n# fenced heading\n```\n"

    assert docs._normalize_markdown_headings(text, min_level=2) == text.strip()


def test_normalize_markdown_headings_leaves_already_nested_headings_unchanged() -> None:
    docs = _load_generator_module()

    text = "## Title\n\nBody\n"

    assert docs._normalize_markdown_headings(text, min_level=2) == text.strip()


def test_render_command_docs_returns_empty_for_blank_docstring() -> None:
    docs = _load_generator_module()

    class BlankModule:
        __doc__ = "   "

    setattr(docs, "COMMAND_DOC_SOURCES", {})
    setattr(docs, "COMMAND_DOC_MODULES", {"branch": BlankModule})

    assert docs.render_command_docs(("branch",), heading_level=2) == ""


def test_resolve_parser_raises_for_unknown_parser_path() -> None:
    docs = _load_generator_module()

    with pytest.raises(KeyError, match="unknown parser path"):
        docs._resolve_parser(("branch", "missing"))


def test_iter_help_sections_without_subparsers_yields_root_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docs = _load_generator_module()

    monkeypatch.setattr(
        "repo_release_tools.cli.build_parser", lambda: __import__("argparse").ArgumentParser()
    )

    sections = list(docs.iter_help_sections())
    assert sections == [docs.HelpSection(argv=(), heading_level=2)]


def test_pinned_help_environment_restores_existing_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docs = _load_generator_module()

    monkeypatch.setenv("COLUMNS", "99")
    monkeypatch.setenv("NO_COLOR", "0")

    with docs.pinned_help_environment():
        assert os.environ["COLUMNS"] == docs.PINNED_COLUMNS
        assert os.environ["NO_COLOR"] == "1"

    assert os.environ["COLUMNS"] == "99"
    assert os.environ["NO_COLOR"] == "0"


def test_generate_index_topic_links_markdown_lists_expected_entries() -> None:
    docs = _load_generator_module()

    content = docs.generate_index_topic_links_markdown()

    assert "commands/branch.md" in content
    assert "commands/git_cmd.md" in content
    assert "commands/tree.md" in content


def test_iter_generated_doc_targets_exposes_all_targets() -> None:
    docs = _load_generator_module()

    targets = list(docs.iter_generated_doc_targets())

    assert targets
    assert targets[0].output_path.name == "rrt-cli.md"
    assert any(target.anchor_id == "index-topic-links" for target in targets)
    assert any(target.anchor_id == "readme-links" for target in targets)


def test_topic_doc_generators_use_source_owned_markdown_constants() -> None:
    docs = _load_generator_module()

    assert docs.generate_semantic_branches_markdown() == docs.branch_module.SEMANTIC_BRANCHES_DOC
    assert docs.generate_git_markdown() == docs.git_helpers.GIT_DOC
    assert docs.generate_semantic_branches_markdown().startswith("# rrt branch")
    assert docs.generate_git_markdown().startswith("# rrt git")
    assert docs.GENERATED_DOC_TARGETS[0].output_path.name == "rrt-cli.md"
    assert len(docs.GENERATED_DOC_TARGETS) >= 3
    assert "branch" in docs.TOPIC_PAGE_OUTPUTS
    assert "git" in docs.TOPIC_PAGE_OUTPUTS


def test_generated_doc_targets_include_anchored_index_block() -> None:
    docs = _load_generator_module()

    index_targets = [
        target
        for target in docs.GENERATED_DOC_TARGETS
        if str(target.output_path).endswith("docs/index.md")
    ]

    assert len(index_targets) == 1
    assert index_targets[0].anchor_id == "index-topic-links"
    assert not index_targets[0].render().startswith("---\n")


def test_generated_doc_targets_include_anchored_readme_links_block() -> None:
    docs = _load_generator_module()

    readme_targets = [
        target for target in docs.GENERATED_DOC_TARGETS if str(target.output_path) == "README.md"
    ]

    assert len(readme_targets) == 1
    assert readme_targets[0].anchor_id == "readme-links"


def test_generated_command_topics_have_frontmatter_and_command_h1() -> None:
    docs = _load_generator_module()

    by_name = {target.output_path.name: target for target in docs.GENERATED_DOC_TARGETS}

    doctor = by_name["doctor.md"].render()
    eol = by_name["eol_check.md"].render()
    git_doc = by_name["git_cmd.md"].render()

    assert doctor.startswith("---\n")
    assert 'title: "rrt doctor"' in doctor
    assert "\n# rrt doctor\n" in doctor

    assert eol.startswith("---\n")
    assert 'title: "rrt eol"' in eol
    assert "\n# rrt eol\n" in eol

    assert git_doc.startswith("---\n")
    assert 'title: "rrt git"' in git_doc
    assert "\n# rrt git\n" in git_doc


def test_validate_generated_pages_returns_no_issues_for_current_registry() -> None:
    docs = _load_generator_module()

    assert docs.validate_generated_pages() == []


def test_extract_first_h1_and_compute_permalink_helpers() -> None:
    docs = _load_generator_module()

    assert docs._extract_first_h1("# Title\n\nBody\n") == "Title"
    assert docs._extract_first_h1("No heading here\n") is None

    assert docs._compute_permalink_for_output(Path("docs/index.md")) == "/"
    assert (
        docs._compute_permalink_for_output(Path("docs/commands/rrt-cli.md")) == "/commands/rrt-cli/"
    )
    assert docs._compute_permalink_for_output(Path("README.md")) == ""


def test_wrap_with_frontmatter_falls_back_to_h1_or_stem_for_unknown_slug() -> None:
    docs = _load_generator_module()

    wrapped_h1 = docs._wrap_with_frontmatter(
        Path("docs/commands/custom-topic.md"),
        lambda: "# Custom Topic\n\nBody\n",
        title_override=None,
        slug="custom-topic",
    )
    rendered_h1 = wrapped_h1()
    assert 'title: "Custom Topic"' in rendered_h1
    assert "\n# Custom Topic\n" in rendered_h1

    wrapped_stem = docs._wrap_with_frontmatter(
        Path("docs/commands/no-heading.md"),
        lambda: "Body without heading\n",
        title_override=None,
        slug="not-registered",
    )
    rendered_stem = wrapped_stem()
    assert 'title: "no-heading"' in rendered_stem
    assert "\n# no-heading\n" in rendered_stem


def test_wrap_with_frontmatter_uses_title_override_registry_when_slug_known() -> None:
    docs = _load_generator_module()

    wrapped = docs._wrap_with_frontmatter(
        Path("docs/commands/doctor.md"),
        lambda: "# Something else\n\nBody\n",
        title_override=None,
        slug="doctor",
    )
    rendered = wrapped()

    assert 'title: "rrt doctor"' in rendered
    assert "\n# rrt doctor\n" in rendered


def test_validate_generated_pages_reports_each_invalid_render_shape() -> None:
    docs = _load_generator_module()
    original_targets = docs.GENERATED_DOC_TARGETS  # ty: ignore[unresolved-attribute]
    try:
        docs.GENERATED_DOC_TARGETS = (  # ty: ignore[unresolved-attribute]
            docs.DocTarget(Path("docs/commands/no-frontmatter.md"), lambda: "# heading\n"),
            docs.DocTarget(
                Path("docs/commands/malformed-frontmatter.md"), lambda: "---\nname: x\n# heading\n"
            ),
            docs.DocTarget(
                Path("docs/commands/no-h1.md"), lambda: "---\nname: x\n---\nplain body\n"
            ),
        )
        issues = docs.validate_generated_pages()
    finally:
        docs.GENERATED_DOC_TARGETS = original_targets  # ty: ignore[unresolved-attribute]

    assert any("missing YAML frontmatter" in issue for issue in issues)
    assert any("malformed YAML frontmatter" in issue for issue in issues)
    assert any("missing top-level H1" in issue for issue in issues)


def test_generate_readme_links_markdown_contains_all_doc_entries() -> None:
    docs = _load_generator_module()

    content = docs.generate_readme_links_markdown()

    assert "docs/index.md" in content
    assert "docs/action.md" in content
    assert "docs/commands/rrt-cli.md" in content
    assert "docs/commands/hooks.md" in content
    assert "docs/commands/branch.md" in content
    assert "docs/commands/git_cmd.md" in content
    assert "docs/commands/skill.md" in content
    assert "docs/commands/tree.md" in content
    assert "docs/commands/toc.md" in content
    assert "docs/commands/doctor.md" in content
    assert "docs/commands/eol_check.md" in content
    assert "docs/agent-instructions.md" in content


def test_task_generate_and_check_cover_all_generated_docs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    docs = _load_generator_module()
    semantic_path = tmp_path / "branch.md"
    git_path = tmp_path / "git.md"
    cli_path = tmp_path / "rrt-cli.md"

    setattr(
        docs,
        "iter_generated_doc_targets",
        lambda: iter(
            [
                docs.DocTarget(cli_path, lambda: "cli\n"),
                docs.DocTarget(semantic_path, lambda: "semantic\n"),
                docs.DocTarget(git_path, lambda: "git\n"),
            ]
        ),
    )

    assert docs.task_generate() == 0
    assert cli_path.read_text(encoding="utf-8") == "cli\n"
    assert semantic_path.read_text(encoding="utf-8") == "semantic\n"
    assert git_path.read_text(encoding="utf-8") == "git\n"

    semantic_path.write_text("stale\n", encoding="utf-8")
    assert docs.task_check() == 1

    captured = capsys.readouterr()
    assert "branch.md is stale" in captured.err


def test_apply_generated_docs_check_mode_fails_for_stale_file(tmp_path: Path) -> None:
    docs = _load_generator_module()
    output_path = tmp_path / "rrt-cli.md"
    output_path.write_text("old\n", encoding="utf-8")

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = docs.apply_generated_docs(
        "new\n",
        output_path=output_path,
        check=True,
        write=False,
        fail_on_change=False,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 1
    assert output_path.read_text(encoding="utf-8") == "old\n"
    assert stdout.getvalue() == ""
    assert "is stale" in stderr.getvalue()


def test_apply_generated_docs_write_and_fail_on_change_updates_file(tmp_path: Path) -> None:
    docs = _load_generator_module()
    output_path = tmp_path / "rrt-cli.md"
    output_path.write_text("old\n", encoding="utf-8")

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = docs.apply_generated_docs(
        "new\n",
        output_path=output_path,
        check=False,
        write=True,
        fail_on_change=True,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 1
    assert output_path.read_text(encoding="utf-8") == "new\n"
    assert stdout.getvalue() == ""
    assert "re-stage" in stderr.getvalue()


def test_apply_generated_docs_noops_when_content_matches(tmp_path: Path) -> None:
    docs = _load_generator_module()
    output_path = tmp_path / "rrt-cli.md"
    output_path.write_text("same\n", encoding="utf-8")

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = docs.apply_generated_docs(
        "same\n",
        output_path=output_path,
        check=True,
        write=False,
        fail_on_change=False,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert "up-to-date" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_replace_anchored_block_updates_between_markers() -> None:
    from repo_release_tools.tools.inject import replace_anchored_block

    existing = (
        "# header\n"
        "<!-- rrt:auto:start:example -->\n"
        "old content\n"
        "<!-- rrt:auto:end:example -->\n"
        "# footer\n"
    )

    updated = replace_anchored_block(existing, anchor_id="example", content="new line")

    assert updated is not None
    assert "old content" not in updated
    assert "new line\n" in updated
    assert "# header" in updated and "# footer" in updated


def test_replace_anchored_block_returns_none_when_markers_absent() -> None:
    from repo_release_tools.tools.inject import replace_anchored_block

    existing = "plain text\nwithout markers\n"

    updated = replace_anchored_block(existing, anchor_id="missing", content="x")

    assert updated is None


def test_replace_anchored_block_does_not_match_prefix_anchor_ids() -> None:
    from repo_release_tools.tools.inject import replace_anchored_block

    existing = (
        "<!-- rrt:auto:start:index-topic-links -->\nold\n<!-- rrt:auto:end:index-topic-links -->\n"
    )

    updated = replace_anchored_block(existing, anchor_id="index", content="new")

    assert updated is None


def test_replace_anchored_block_raises_for_missing_end_marker() -> None:
    from repo_release_tools.tools.inject import replace_anchored_block

    existing = "<!-- rrt:auto:start:broken -->\ncontent\n"

    with pytest.raises(ValueError, match="Missing end anchor"):
        replace_anchored_block(existing, anchor_id="broken", content="x")


def test_replace_anchored_block_raises_for_invalid_anchor_id() -> None:
    from repo_release_tools.tools.inject import replace_anchored_block

    with pytest.raises(ValueError, match="Invalid anchor id"):
        replace_anchored_block("any content", anchor_id="!invalid", content="x")


def test_apply_generated_docs_anchor_mode_replaces_only_block(tmp_path: Path) -> None:
    docs = _load_generator_module()
    output_path = tmp_path / "target.md"
    output_path.write_text(
        "before\n<!-- rrt:auto:start:block -->\nold\n<!-- rrt:auto:end:block -->\nafter\n",
        encoding="utf-8",
    )

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = docs.apply_generated_docs(
        "new\ncontent\n",
        output_path=output_path,
        check=False,
        write=True,
        fail_on_change=False,
        stdout=stdout,
        stderr=stderr,
        anchor_id="block",
    )

    rendered = output_path.read_text(encoding="utf-8")
    assert exit_code == 0
    assert "before\n" in rendered and "\nafter\n" in rendered
    assert "old" not in rendered
    assert "new\ncontent\n" in rendered
    assert stderr.getvalue() == ""


def test_apply_generated_docs_anchor_mode_fails_when_anchor_missing(tmp_path: Path) -> None:
    docs = _load_generator_module()
    output_path = tmp_path / "target.md"
    output_path.write_text("before\nafter\n", encoding="utf-8")

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = docs.apply_generated_docs(
        "new\n",
        output_path=output_path,
        check=False,
        write=True,
        fail_on_change=False,
        stdout=stdout,
        stderr=stderr,
        anchor_id="block",
    )

    assert exit_code == 1
    assert "missing required anchors" in stderr.getvalue()
    assert output_path.read_text(encoding="utf-8") == "before\nafter\n"


def test_apply_generated_docs_anchor_mode_stale_hint_uses_docs_inject(tmp_path: Path) -> None:
    docs = _load_generator_module()
    output_path = tmp_path / "target.md"
    output_path.write_text(
        "before\n<!-- rrt:auto:start:block -->\nold\n<!-- rrt:auto:end:block -->\nafter\n",
        encoding="utf-8",
    )

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = docs.apply_generated_docs(
        "new\n",
        output_path=output_path,
        check=True,
        write=False,
        fail_on_change=False,
        stdout=stdout,
        stderr=stderr,
        anchor_id="block",
        stale_hint="rrt docs inject --check",
    )

    assert exit_code == 1
    assert "rrt docs inject --check" in stderr.getvalue()


def test_apply_generated_docs_anchor_mode_fails_when_file_missing(tmp_path: Path) -> None:
    docs = _load_generator_module()
    output_path = tmp_path / "missing-target.md"

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = docs.apply_generated_docs(
        "new\n",
        output_path=output_path,
        check=False,
        write=True,
        fail_on_change=False,
        stdout=stdout,
        stderr=stderr,
        anchor_id="block",
    )

    assert exit_code == 1
    assert "missing required anchor block" in stderr.getvalue()
    assert not output_path.exists()


def test_task_inject_shared_blocks_raises_for_malformed_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    docs = _load_generator_module()
    monkeypatch.chdir(tmp_path)

    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "example"
version = "0.1.0"

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[[tool.rrt.docs.shared_blocks]]
anchor_id = "test-footer"
content = 123
targets = ["docs/**/*.md"]
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"shared_blocks\[0\]\.content must be a string"):
        docs.task_inject_shared_blocks()


# ---------------------------------------------------------------------------
# _apply_shared_blocks / task_inject_shared_blocks / task_check_shared_blocks
# ---------------------------------------------------------------------------

_PYPROJECT_SHARED_BLOCK_RICH_INLINE = '''\
[project]
name = "example"
version = "0.1.0"

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[[tool.rrt.docs.shared_blocks]]
anchor_id = "test-footer"
content = """---
[Docs]({repo_url})
<iframe src=\"https://example.test/embed\"></iframe>"""
targets = ["docs/**/*.md"]
'''

_PYPROJECT_SHARED_BLOCK_INLINE = """\
[project]
name = "example"
version = "0.1.0"

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[[tool.rrt.docs.shared_blocks]]
anchor_id = "test-footer"
content = "inline footer"
targets = ["docs/**/*.md"]
"""


def _make_docs_file(tmp_path: Path, subdir: str = "docs") -> Path:
    """Create a doc file with anchor markers for test-footer."""
    doc_dir = tmp_path / subdir
    doc_dir.mkdir(parents=True, exist_ok=True)
    doc_file = doc_dir / "test.md"
    doc_file.write_text(
        "# Hello\n\n<!-- rrt:auto:start:test-footer -->\n<!-- rrt:auto:end:test-footer -->\n",
        encoding="utf-8",
    )
    return doc_file


def test_apply_shared_blocks_writes_rich_inline_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rich inline shared block content is injected unchanged apart from placeholders."""
    docs = _load_generator_module()
    monkeypatch.chdir(tmp_path)

    (tmp_path / "pyproject.toml").write_text(_PYPROJECT_SHARED_BLOCK_RICH_INLINE, encoding="utf-8")
    doc_file = _make_docs_file(tmp_path)

    exit_code = docs.task_inject_shared_blocks()
    assert exit_code == 0

    result = doc_file.read_text(encoding="utf-8")
    assert "[Docs](https://github.com/Anselmoo/repo-release-tools)" in result
    assert '<iframe src="https://example.test/embed"></iframe>' in result
    assert "<!-- rrt:auto:start:test-footer -->" in result
    assert "<!-- rrt:auto:end:test-footer -->" in result


def test_apply_shared_blocks_writes_inline_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Shared block with inline content is injected into matching doc files."""
    docs = _load_generator_module()
    monkeypatch.chdir(tmp_path)

    (tmp_path / "pyproject.toml").write_text(_PYPROJECT_SHARED_BLOCK_INLINE, encoding="utf-8")
    doc_file = _make_docs_file(tmp_path)

    exit_code = docs.task_inject_shared_blocks()
    assert exit_code == 0
    assert "inline footer" in doc_file.read_text(encoding="utf-8")


def test_apply_shared_blocks_check_mode_fails_for_stale_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check mode returns 1 when a block is stale (not yet injected)."""
    docs = _load_generator_module()
    monkeypatch.chdir(tmp_path)

    (tmp_path / "pyproject.toml").write_text(_PYPROJECT_SHARED_BLOCK_INLINE, encoding="utf-8")
    _make_docs_file(tmp_path)  # file has empty anchors — stale

    exit_code = docs.task_check_shared_blocks()
    assert exit_code == 1


def test_apply_shared_blocks_check_mode_passes_for_current_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check mode returns 0 when all blocks are already up to date."""
    docs = _load_generator_module()
    monkeypatch.chdir(tmp_path)

    (tmp_path / "pyproject.toml").write_text(_PYPROJECT_SHARED_BLOCK_INLINE, encoding="utf-8")
    _make_docs_file(tmp_path)

    # Write first so the file is up to date
    docs.task_inject_shared_blocks()

    exit_code = docs.task_check_shared_blocks()
    assert exit_code == 0


def test_apply_shared_blocks_noop_when_no_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Returns 0 gracefully when no rrt config exists in cwd."""
    docs = _load_generator_module()
    monkeypatch.chdir(tmp_path)

    exit_code = docs.task_inject_shared_blocks()
    assert exit_code == 0


def test_apply_shared_blocks_noop_when_no_shared_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Returns 0 gracefully when config exists but has no shared_blocks."""
    docs = _load_generator_module()
    monkeypatch.chdir(tmp_path)

    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.1.0"\n'
        '[[tool.rrt.version_targets]]\npath = "pyproject.toml"\nkind = "pep621"\n',
        encoding="utf-8",
    )

    exit_code = docs.task_inject_shared_blocks()
    assert exit_code == 0


def test_apply_shared_blocks_warns_when_no_targets_matched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Logs a message when no target files match the glob patterns."""
    docs = _load_generator_module()
    monkeypatch.chdir(tmp_path)

    (tmp_path / "pyproject.toml").write_text(_PYPROJECT_SHARED_BLOCK_INLINE, encoding="utf-8")
    # No docs/ directory — glob matches nothing

    exit_code = docs.task_inject_shared_blocks()
    assert exit_code == 0
    assert "no target files matched" in capsys.readouterr().out


def test_apply_shared_blocks_rejects_legacy_template_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Legacy template-backed shared blocks still work with deprecation warning."""
    docs = _load_generator_module()
    monkeypatch.chdir(tmp_path)

    (tmp_path / "scripts" / "templates").mkdir(parents=True, exist_ok=True)
    (tmp_path / "scripts" / "templates" / "test-footer.md").write_text(
        "legacy footer\n", encoding="utf-8"
    )
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "guide.md").write_text(
        "# Guide\n\n<!-- rrt:auto:start:test-footer -->\n<!-- rrt:auto:end:test-footer -->\n",
        encoding="utf-8",
    )

    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "example"
version = "0.1.0"

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[[tool.rrt.docs.shared_blocks]]
anchor_id = "test-footer"
template = "scripts/templates/test-footer.md"
targets = ["docs/**/*.md"]
""",
        encoding="utf-8",
    )

    with pytest.warns(DeprecationWarning, match="template is deprecated"):
        exit_code = docs.task_inject_shared_blocks()
    assert exit_code == 0
    assert "legacy footer" in (tmp_path / "docs" / "guide.md").read_text(encoding="utf-8")
