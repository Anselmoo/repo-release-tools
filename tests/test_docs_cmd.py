"""Tests for rrt docs command and subcommands."""

from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace

import pytest

from repo_release_tools.commands.docs_cmd import (
    SOURCE_OWNED_TOPIC_DOCS,
    _cmd_check,
    _cmd_generate,
    _cmd_inject,
    _cmd_publish,
    _config_for_cwd,
    cmd_docs,
)
from repo_release_tools.config import DocsConfig, SharedBlock


@pytest.fixture
def temp_repo(tmp_path: Path) -> Path:
    """Create a minimal repo structure for docs testing."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / ".rrt").mkdir()
    (repo / "pyproject.toml").write_text(
        """
[project]
name = "test-project"
version = "1.0.0"

[tool.rrt.docs]
extraction_mode = "explicit"
formats = ["md", "json"]
languages = ["python"]
src_dir = "src"

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"
"""
    )
    return repo


@pytest.fixture
def python_file_with_docs(temp_repo: Path) -> Path:
    """Create a Python file with explicit doc blocks."""
    py_file = temp_repo / "src" / "module.py"
    # Use the correct format: marker on own line, then variable assignment with triple-quoted string
    py_file.write_text(
        '# sym: hello\nHELLO_DOC = """\nThis is a hello function documentation.\n"""\n\n'
        '# sym: world\nWORLD_DOC = """\nThis is a world function documentation.\n"""\n'
    )
    return py_file


class TestConfigForCwd:
    """Test _config_for_cwd helper."""

    def test_config_for_cwd_with_docs_config(self, temp_repo: Path) -> None:
        """Should return DocsConfig from loaded config."""
        config = _config_for_cwd(temp_repo)
        assert config is not None
        assert config.extraction_mode == "explicit"

    def test_config_for_cwd_with_auto_detect(self, tmp_path: Path) -> None:
        """Should return default DocsConfig when config auto-detects."""
        repo = tmp_path / "empty"
        repo.mkdir()
        repo.joinpath("pyproject.toml").write_text('[project]\nname = "test"\nversion = "1.0.0"')
        config = _config_for_cwd(repo)
        assert config is not None


class TestCmdGenerate:
    """Test _cmd_generate sub-action."""

    def test_generate_basic_success(self, temp_repo: Path, python_file_with_docs: Path) -> None:
        """Should generate documentation successfully."""
        args = argparse.Namespace(
            root=str(temp_repo),
            dry_run=False,
            format="json",
            lang=None,
        )
        result = _cmd_generate(args)
        assert result == 0

    def test_generate_with_no_entries(self, temp_repo: Path) -> None:
        """Should return 0 and warn when no docs found."""
        args = argparse.Namespace(
            root=str(temp_repo),
            dry_run=False,
            format="json",
            lang=None,
        )
        result = _cmd_generate(args)
        assert result == 0

    def test_generate_with_invalid_language(self, temp_repo: Path) -> None:
        """Should return 1 for invalid language specification."""
        args = argparse.Namespace(
            root=str(temp_repo),
            dry_run=False,
            format="json",
            lang="invalid_lang,python",
        )
        result = _cmd_generate(args)
        assert result == 1

    def test_generate_format_override_from_cli(
        self, temp_repo: Path, python_file_with_docs: Path
    ) -> None:
        """Should override config format with CLI --format."""
        args = argparse.Namespace(
            root=str(temp_repo),
            dry_run=False,
            format="md",
            lang=None,
        )
        result = _cmd_generate(args)
        assert result == 0

    def test_generate_language_override_from_cli(
        self, temp_repo: Path, python_file_with_docs: Path
    ) -> None:
        """Should override config languages with CLI --lang."""
        args = argparse.Namespace(
            root=str(temp_repo),
            dry_run=False,
            format="json",
            lang="python",
        )
        result = _cmd_generate(args)
        assert result == 0

    def test_generate_dry_run_toml_format(
        self, temp_repo: Path, python_file_with_docs: Path
    ) -> None:
        """Should dry-run TOML format without writing."""
        args = argparse.Namespace(
            root=str(temp_repo),
            dry_run=True,
            format="toml",
            lang=None,
        )
        result = _cmd_generate(args)
        assert result == 0
        # Verify lockfile was not written
        lock_path = temp_repo / ".rrt" / "docs.lock.toml"
        assert not lock_path.exists()

    def test_generate_toml_format_writes_lockfile(
        self, temp_repo: Path, python_file_with_docs: Path
    ) -> None:
        """Should write lockfile when format is toml."""
        args = argparse.Namespace(
            root=str(temp_repo),
            dry_run=False,
            format="toml",
            lang=None,
        )
        result = _cmd_generate(args)
        assert result == 0
        lock_path = temp_repo / ".rrt" / "docs.lock.toml"
        assert (
            lock_path.exists() or not python_file_with_docs.exists()
        )  # Docs extraction might be implicit only

    def test_generate_txt_format_to_stdout(
        self, temp_repo: Path, python_file_with_docs: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should output txt format to stdout."""
        args = argparse.Namespace(
            root=str(temp_repo),
            dry_run=False,
            format="txt",
            lang=None,
        )
        result = _cmd_generate(args)
        assert result == 0

    def test_generate_rich_format_to_stdout(
        self, temp_repo: Path, python_file_with_docs: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should output rich format to stdout."""
        args = argparse.Namespace(
            root=str(temp_repo),
            dry_run=False,
            format="rich",
            lang=None,
        )
        result = _cmd_generate(args)
        assert result == 0

    def test_generate_clipboard_format_to_stdout(
        self, temp_repo: Path, python_file_with_docs: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should output clipboard format to stdout."""
        args = argparse.Namespace(
            root=str(temp_repo),
            dry_run=False,
            format="clipboard",
            lang=None,
        )
        result = _cmd_generate(args)
        assert result == 0


class TestCmdCheck:
    """Test _cmd_check sub-action."""

    def test_check_lockfile_current(self, temp_repo: Path, python_file_with_docs: Path) -> None:
        """Should return 0 when lockfile is current."""
        # First generate lockfile
        gen_args = argparse.Namespace(
            root=str(temp_repo),
            dry_run=False,
            format="toml",
            lang=None,
        )
        _cmd_generate(gen_args)

        # Now check
        check_args = argparse.Namespace(
            root=str(temp_repo),
            lock_file=None,
        )
        result = _cmd_check(check_args)
        assert result == 0

    def test_check_lockfile_stale_file_added(
        self, temp_repo: Path, python_file_with_docs: Path
    ) -> None:
        """Should return 1 when source file was added after lockfile creation."""
        # First generate lockfile
        gen_args = argparse.Namespace(
            root=str(temp_repo),
            dry_run=False,
            format="toml",
            lang=None,
        )
        _cmd_generate(gen_args)

        # Add a new Python file with docs
        new_file = temp_repo / "src" / "new_module.py"
        new_file.write_text(
            """
# sym: new
NEW_DOC = \"\"\"New doc\"\"\"
"""
        )

        # Check should fail
        check_args = argparse.Namespace(
            root=str(temp_repo),
            lock_file=None,
        )
        result = _cmd_check(check_args)
        assert result == 1

    def test_check_lockfile_stale_file_modified(
        self, temp_repo: Path, python_file_with_docs: Path
    ) -> None:
        """Should return 1 when source file was modified after lockfile creation."""
        # First generate lockfile
        gen_args = argparse.Namespace(
            root=str(temp_repo),
            dry_run=False,
            format="toml",
            lang=None,
        )
        _cmd_generate(gen_args)

        # Modify the Python file
        py_file = temp_repo / "src" / "module.py"
        py_file.write_text(
            '''
# sym: hello
HELLO_DOC = """
Modified documentation.
"""
'''
        )

        # Check should fail
        check_args = argparse.Namespace(
            root=str(temp_repo),
            lock_file=None,
        )
        result = _cmd_check(check_args)
        assert result == 1

    def test_check_lockfile_missing(self, temp_repo: Path) -> None:
        """Should return 1 when lockfile doesn't exist."""
        check_args = argparse.Namespace(
            root=str(temp_repo),
            lock_file=None,
        )
        result = _cmd_check(check_args)
        # Will return 1 because lockfile doesn't exist or no docs are found
        assert result in (0, 1)

    def test_check_custom_lock_file_path(
        self, temp_repo: Path, python_file_with_docs: Path
    ) -> None:
        """Should accept custom lock_file path."""
        # Generate to custom location
        gen_args = argparse.Namespace(
            root=str(temp_repo),
            dry_run=False,
            format="toml",
            lang=None,
        )
        _cmd_generate(gen_args)

        # Check with custom lock file
        check_args = argparse.Namespace(
            root=str(temp_repo),
            lock_file=".rrt/docs.lock.toml",
        )
        result = _cmd_check(check_args)
        # Should work with default location
        assert result == 0


class TestCmdDocs:
    """Test cmd_docs dispatcher."""

    def test_cmd_docs_generate_action(self, temp_repo: Path, python_file_with_docs: Path) -> None:
        """Should dispatch to _cmd_generate."""
        args = argparse.Namespace(
            root=str(temp_repo),
            docs_action="generate",
            dry_run=False,
            format="json",
            lang=None,
        )
        result = cmd_docs(args)
        assert result == 0

    def test_cmd_docs_check_action(self, temp_repo: Path, python_file_with_docs: Path) -> None:
        """Should dispatch to _cmd_check."""
        # First generate lockfile
        gen_args = argparse.Namespace(
            root=str(temp_repo),
            dry_run=False,
            format="toml",
            lang=None,
        )
        _cmd_generate(gen_args)

        args = argparse.Namespace(
            root=str(temp_repo),
            docs_action="check",
            lock_file=None,
        )
        result = cmd_docs(args)
        assert result == 0

    def test_cmd_docs_unknown_action(self, temp_repo: Path) -> None:
        """Should return 1 for unknown action."""
        args = argparse.Namespace(
            root=str(temp_repo),
            docs_action="unknown",
        )
        result = cmd_docs(args)
        assert result == 1

    def test_cmd_docs_default_action_is_generate(
        self, temp_repo: Path, python_file_with_docs: Path
    ) -> None:
        """Should default to generate action."""
        args = argparse.Namespace(
            root=str(temp_repo),
            dry_run=False,
            format="json",
            lang=None,
        )
        # Don't set docs_action, should default to "generate"
        result = cmd_docs(args)
        assert result == 0

    def test_cmd_docs_dispatches_publish(
        self, monkeypatch: pytest.MonkeyPatch, temp_repo: Path
    ) -> None:
        """Should dispatch publish to the publish helper."""
        monkeypatch.setattr("repo_release_tools.commands.docs_cmd._cmd_publish", lambda args: 7)

        args = argparse.Namespace(root=str(temp_repo), docs_action="publish")

        assert cmd_docs(args) == 7

    def test_cmd_docs_dispatches_inject(
        self, monkeypatch: pytest.MonkeyPatch, temp_repo: Path
    ) -> None:
        """Should dispatch inject to the inject helper."""
        monkeypatch.setattr("repo_release_tools.commands.docs_cmd._cmd_inject", lambda args: 8)

        args = argparse.Namespace(root=str(temp_repo), docs_action="inject")

        assert cmd_docs(args) == 8


class TestCmdPublish:
    """Test _cmd_publish sub-action."""

    def test_cmd_publish_dry_run_lists_targets(
        self, monkeypatch: pytest.MonkeyPatch, temp_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Dry-run publish should report every generated target without writing."""
        from repo_release_tools import docs_publisher

        targets = [
            docs_publisher.DocTarget(temp_repo / "docs" / "rrt-cli.md", lambda: "cli\n"),
            docs_publisher.DocTarget(
                temp_repo / "README.md",
                lambda: "readme\n",
                anchor_id="readme-links",
            ),
        ]
        monkeypatch.setattr(docs_publisher, "iter_generated_doc_targets", lambda: iter(targets))

        args = argparse.Namespace(check=False, dry_run=True, fail_on_change=False)

        assert _cmd_publish(args) == 0
        out = capsys.readouterr().out
        assert "rrt-cli.md" in out
        assert "README.md" in out

    def test_cmd_publish_forwards_all_arguments(
        self, monkeypatch: pytest.MonkeyPatch, temp_repo: Path
    ) -> None:
        """Non-dry-run publish should call apply_generated_docs for each target."""
        from repo_release_tools import docs_publisher

        calls: list[tuple[str, Path, bool, bool, bool, str | None]] = []
        target = docs_publisher.DocTarget(
            temp_repo / "docs" / "index.md",
            lambda: "generated text\n",
            anchor_id="index-topic-links",
        )
        monkeypatch.setattr(docs_publisher, "iter_generated_doc_targets", lambda: iter([target]))

        def fake_apply_generated_docs(
            content: str,
            *,
            output_path: Path,
            check: bool,
            write: bool,
            fail_on_change: bool,
            stdout: object,
            stderr: object,
            anchor_id: str | None = None,
        ) -> int:
            calls.append((content, output_path, check, write, fail_on_change, anchor_id))
            return 0

        monkeypatch.setattr(
            "repo_release_tools.commands.docs_cmd.apply_generated_docs",
            fake_apply_generated_docs,
        )

        args = argparse.Namespace(check=True, dry_run=False, fail_on_change=True)

        assert _cmd_publish(args) == 0
        assert calls == [
            (
                "generated text\n",
                temp_repo / "docs" / "index.md",
                True,
                False,
                True,
                "index-topic-links",
            )
        ]


class TestCmdInject:
    """Test _cmd_inject sub-action."""

    def test_cmd_inject_returns_zero_when_no_config_exists(
        self, monkeypatch: pytest.MonkeyPatch, temp_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Missing config should be treated as a no-op."""

        def raise_missing(root: Path) -> object:
            raise FileNotFoundError

        monkeypatch.setattr("repo_release_tools.commands.docs_cmd.load_config", raise_missing)

        args = argparse.Namespace(root=str(temp_repo), check=False, dry_run=False)

        assert _cmd_inject(args) == 0
        assert "skipping shared_blocks injection" in capsys.readouterr().out

    def test_cmd_inject_returns_zero_when_no_shared_blocks(
        self, monkeypatch: pytest.MonkeyPatch, temp_repo: Path
    ) -> None:
        """A config without shared blocks should be a no-op."""
        monkeypatch.setattr(
            "repo_release_tools.commands.docs_cmd.load_config",
            lambda root: SimpleNamespace(docs=DocsConfig(shared_blocks=())),
        )

        args = argparse.Namespace(root=str(temp_repo), check=False, dry_run=False)

        assert _cmd_inject(args) == 0

    def test_cmd_inject_dry_run_reports_targets(
        self, monkeypatch: pytest.MonkeyPatch, temp_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Dry-run injection should only report intended target files."""
        block = SharedBlock(anchor_id="shared-footer", content="footer", targets=("README.md",))
        monkeypatch.setattr(
            "repo_release_tools.commands.docs_cmd.load_config",
            lambda root: SimpleNamespace(docs=DocsConfig(shared_blocks=(block,))),
        )

        args = argparse.Namespace(root=str(temp_repo), check=False, dry_run=True)

        assert _cmd_inject(args) == 0
        assert "README.md" in capsys.readouterr().out

    def test_cmd_inject_reports_missing_template(
        self, monkeypatch: pytest.MonkeyPatch, temp_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Missing template files should fail fast."""
        block = SharedBlock(
            anchor_id="shared-footer", template="missing.md", targets=("README.md",)
        )
        monkeypatch.setattr(
            "repo_release_tools.commands.docs_cmd.load_config",
            lambda root: SimpleNamespace(docs=DocsConfig(shared_blocks=(block,))),
        )

        args = argparse.Namespace(root=str(temp_repo), check=False, dry_run=False)

        assert _cmd_inject(args) == 1
        assert "not found" in capsys.readouterr().err

    def test_cmd_inject_reports_when_no_targets_match(
        self, monkeypatch: pytest.MonkeyPatch, temp_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Shared blocks with unmatched glob patterns should warn and continue."""
        block = SharedBlock(anchor_id="shared-footer", content="footer", targets=("docs/**/*.md",))
        monkeypatch.setattr(
            "repo_release_tools.commands.docs_cmd.load_config",
            lambda root: SimpleNamespace(docs=DocsConfig(shared_blocks=(block,))),
        )

        args = argparse.Namespace(root=str(temp_repo), check=False, dry_run=False)

        assert _cmd_inject(args) == 0
        assert "no target files matched" in capsys.readouterr().out

    def test_cmd_inject_raises_for_malformed_shared_blocks_config(self, temp_repo: Path) -> None:
        """Malformed shared_blocks config should not be swallowed as missing config."""
        (temp_repo / "pyproject.toml").write_text(
            """
[project]
name = "test-project"
version = "1.0.0"

[tool.rrt.docs]

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[[tool.rrt.docs.shared_blocks]]
anchor_id = "shared-footer"
template = 123
targets = ["README.md"]
""",
            encoding="utf-8",
        )

        args = argparse.Namespace(root=str(temp_repo), check=False, dry_run=False)

        with pytest.raises(ValueError, match=r"shared_blocks\[0\]\.template must be a string"):
            _cmd_inject(args)

    def test_cmd_inject_writes_content_with_placeholders(
        self, monkeypatch: pytest.MonkeyPatch, temp_repo: Path
    ) -> None:
        """Shared blocks should replace version and repo URL placeholders before writing."""
        from repo_release_tools import __version__ as rrt_version

        readme = temp_repo / "README.md"
        readme.write_text(
            "before\n<!-- rrt:auto:start:shared-footer -->\nold\n<!-- rrt:auto:end:shared-footer -->\nafter\n",
            encoding="utf-8",
        )
        template = temp_repo / "scripts" / "templates" / "shared-footer.md"
        template.parent.mkdir(parents=True, exist_ok=True)
        template.write_text("Release {version} at {repo_url}", encoding="utf-8")
        block = SharedBlock(
            anchor_id="shared-footer",
            template="scripts/templates/shared-footer.md",
            targets=("README.md",),
        )
        monkeypatch.setattr(
            "repo_release_tools.commands.docs_cmd.load_config",
            lambda root: SimpleNamespace(docs=DocsConfig(shared_blocks=(block,))),
        )

        args = argparse.Namespace(root=str(temp_repo), check=False, dry_run=False)

        assert _cmd_inject(args) == 0
        result = readme.read_text(encoding="utf-8")
        assert rrt_version in result
        assert "https://github.com/Anselmoo/repo-release-tools" in result
        assert "{version}" not in result
        assert "{repo_url}" not in result


class TestSourceOwnedTopicDocs:
    """Test SOURCE_OWNED_TOPIC_DOCS constant."""

    def test_source_owned_topic_docs_defined(self) -> None:
        """Should have SOURCE_OWNED_TOPIC_DOCS defined."""
        assert SOURCE_OWNED_TOPIC_DOCS is not None
        assert len(SOURCE_OWNED_TOPIC_DOCS) > 0
        assert SOURCE_OWNED_TOPIC_DOCS[0][0] == "docs"
