from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_generator_module() -> ModuleType:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "generate_cli_docs.py"
    spec = importlib.util.spec_from_file_location("generate_cli_docs", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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

    assert content.startswith("# RRT CLI\n")
    assert "## Global help" in content
    assert "## `rrt branch`" in content
    assert "Conventional branches for trunk-based publishing" in content
    assert "Git magic" in content
    assert "### `rrt branch new`" in content
    assert "### `rrt git diff`" in content
    assert "### `rrt ci-version compute`" in content
    assert "### `rrt skill install`" in content
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

    assert "Conventional branches for trunk-based publishing" in branch_rendered
    assert "Git magic" in git_rendered
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


def test_topic_doc_generators_use_source_owned_markdown_constants() -> None:
    docs = _load_generator_module()

    assert docs.generate_semantic_branches_markdown() == docs.branch_module.SEMANTIC_BRANCHES_DOC
    assert docs.generate_git_magic_markdown() == docs.git_helpers.GIT_MAGIC_DOC
    assert docs.generate_semantic_branches_markdown().startswith("# Conventional branches")
    assert docs.generate_git_magic_markdown().startswith("# Git magic")
    assert docs.GENERATED_DOC_TARGETS[0].output_path.name == "rrt-cli.md"
    assert len(docs.GENERATED_DOC_TARGETS) >= 3
    assert "branch" in docs.TOPIC_PAGE_OUTPUTS
    assert "git" in docs.TOPIC_PAGE_OUTPUTS


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
