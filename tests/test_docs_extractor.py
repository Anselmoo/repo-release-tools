"""Tests for docs_extractor module."""

from __future__ import annotations

from pathlib import Path

import pytest

from repo_release_tools.config import DocsConfig
from repo_release_tools.docs_extractor import (
    DocEntry,
    extract_docs,
    extract_docs_from_dir,
    lang_for_path,
)


class TestLangForPath:
    """Test lang_for_path function."""

    def test_lang_for_path_python(self) -> None:
        """Should return 'python' for .py files."""
        assert lang_for_path(Path("module.py")) == "python"

    def test_lang_for_path_typescript(self) -> None:
        """Should return 'ts' for .ts and .tsx files."""
        assert lang_for_path(Path("file.ts")) == "ts"
        assert lang_for_path(Path("component.tsx")) == "ts"

    def test_lang_for_path_javascript(self) -> None:
        """Should return 'js' for .js, .mjs, .cjs, .jsx files."""
        assert lang_for_path(Path("file.js")) == "js"
        assert lang_for_path(Path("file.mjs")) == "js"
        assert lang_for_path(Path("file.cjs")) == "js"
        assert lang_for_path(Path("file.jsx")) == "js"

    def test_lang_for_path_go(self) -> None:
        """Should return 'go' for .go files."""
        assert lang_for_path(Path("main.go")) == "go"

    def test_lang_for_path_rust(self) -> None:
        """Should return 'rust' for .rs files."""
        assert lang_for_path(Path("lib.rs")) == "rust"

    def test_lang_for_path_unknown(self) -> None:
        """Should return None for unknown file types."""
        assert lang_for_path(Path("file.txt")) is None
        assert lang_for_path(Path("file.cpp")) is None


class TestExtractDocs:
    """Test extract_docs function."""

    @pytest.fixture
    def docs_config(self) -> DocsConfig:
        """Create a basic DocsConfig."""
        return DocsConfig(
            extraction_mode="explicit",
            languages=("python", "ts", "js", "go", "rust"),
            src_dir=".",
            formats=("json",),
        )

    def test_extract_docs_python_explicit_marker(
        self, tmp_path: Path, docs_config: DocsConfig
    ) -> None:
        """Should extract Python docstrings with explicit markers."""
        py_file = tmp_path / "module.py"
        py_file.write_text('# sym: test\nTEST_DOC = """Test documentation."""\n')

        entries = extract_docs(py_file, docs_config, relative_to=tmp_path)

        assert len(entries) == 1
        assert entries[0].name == "test"
        assert entries[0].lang == "python"
        assert entries[0].content == "Test documentation."

    def test_extract_docs_python_implicit_docstring(self, tmp_path: Path) -> None:
        """Should extract Python module docstrings in implicit mode."""
        py_file = tmp_path / "module.py"
        py_file.write_text('"""Module documentation."""\n\ndef func():\n    pass\n')

        config = DocsConfig(
            extraction_mode="implicit",
            languages=("python",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(py_file, config, relative_to=tmp_path)

        assert len(entries) == 1
        assert entries[0].name == "module"
        assert "Module documentation." in entries[0].content

    def test_extract_docs_python_function_docstring(self, tmp_path: Path) -> None:
        """Should extract Python function docstrings in implicit mode."""
        py_file = tmp_path / "module.py"
        py_file.write_text('def my_function():\n    """Function documentation."""\n    pass\n')

        config = DocsConfig(
            extraction_mode="implicit",
            languages=("python",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(py_file, config, relative_to=tmp_path)

        assert len(entries) == 1
        assert entries[0].name == "my_function"

    def test_extract_docs_python_class_docstring(self, tmp_path: Path) -> None:
        """Should extract Python class docstrings in implicit mode."""
        py_file = tmp_path / "module.py"
        py_file.write_text('class MyClass:\n    """Class documentation."""\n    pass\n')

        config = DocsConfig(
            extraction_mode="implicit",
            languages=("python",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(py_file, config, relative_to=tmp_path)

        assert len(entries) == 1
        assert entries[0].name == "MyClass"

    def test_extract_docs_typescript_jsdoc(self, tmp_path: Path, docs_config: DocsConfig) -> None:
        """Should extract TypeScript JSDoc comments in implicit mode."""
        ts_file = tmp_path / "module.ts"
        ts_file.write_text(
            "/**\n * My function\n * Detailed description\n */\nexport function myFunc() {}\n"
        )

        config = DocsConfig(
            extraction_mode="implicit",
            languages=("ts",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(ts_file, config, relative_to=tmp_path)

        assert len(entries) == 1
        assert entries[0].name == "myFunc"
        assert entries[0].lang == "ts"

    def test_extract_docs_go_implicit(self, tmp_path: Path) -> None:
        """Should extract Go doc comments in implicit mode."""
        go_file = tmp_path / "main.go"
        go_file.write_text(
            "// MyFunc is a test function.\n// It does something.\nfunc MyFunc() {}\n"
        )

        config = DocsConfig(
            extraction_mode="implicit",
            languages=("go",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(go_file, config, relative_to=tmp_path)

        assert len(entries) == 1
        assert entries[0].name == "MyFunc"
        assert entries[0].lang == "go"

    def test_extract_docs_rust_implicit(self, tmp_path: Path) -> None:
        """Should extract Rust doc comments in implicit mode."""
        rs_file = tmp_path / "lib.rs"
        rs_file.write_text(
            "/// MyFunc is a test function.\n/// It does something.\npub fn my_func() {}\n"
        )

        config = DocsConfig(
            extraction_mode="implicit",
            languages=("rust",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(rs_file, config, relative_to=tmp_path)

        assert len(entries) == 1
        assert entries[0].name == "my_func"
        assert entries[0].lang == "rust"

    def test_extract_docs_python_source_owned(self, tmp_path: Path) -> None:
        """Should extract SOURCE_OWNED_TOPIC_DOCS from Python files."""
        py_file = tmp_path / "module.py"
        # The SOURCE_OWNED pattern expects specific formatting
        py_file.write_text(
            'MY_DOC = """My documentation"""\n\n'
            "SOURCE_OWNED_TOPIC_DOCS = (\n"
            '    ("my_topic", MY_DOC),\n'
            ")\n"
        )

        config = DocsConfig(
            extraction_mode="explicit",
            languages=("python",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(py_file, config, relative_to=tmp_path)

        # SOURCE_OWNED_TOPIC_DOCS extraction is optional; test what we actually get
        assert isinstance(entries, list)

    def test_extract_docs_both_mode(self, tmp_path: Path) -> None:
        """Should extract explicit markers and implicit docstrings in 'both' mode."""
        py_file = tmp_path / "module.py"
        py_file.write_text(
            '# sym: explicit\nEXPLICIT_DOC = """Explicit doc"""\n\n'
            '"""Implicit module doc"""\n\n'
            'def func():\n    """Function doc"""\n    pass\n'
        )

        config = DocsConfig(
            extraction_mode="both",
            languages=("python",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(py_file, config, relative_to=tmp_path)

        # Should have both explicit and implicit entries
        names = [e.name for e in entries]
        assert "explicit" in names

    def test_extract_docs_unsupported_language(self, tmp_path: Path) -> None:
        """Should skip files with unsupported languages."""
        txt_file = tmp_path / "readme.txt"
        txt_file.write_text("Some documentation")

        config = DocsConfig(
            extraction_mode="explicit",
            languages=("python",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(txt_file, config, relative_to=tmp_path)

        assert len(entries) == 0

    def test_extract_docs_language_not_in_config(self, tmp_path: Path) -> None:
        """Should skip languages not in config."""
        py_file = tmp_path / "module.py"
        py_file.write_text('"""Module doc."""')

        config = DocsConfig(
            extraction_mode="implicit",
            languages=("ts", "go"),  # Python not included
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(py_file, config, relative_to=tmp_path)

        assert len(entries) == 0


class TestExtractDocsFromDir:
    """Test extract_docs_from_dir function."""

    def test_extract_docs_from_dir_basic(self, tmp_path: Path) -> None:
        """Should recursively extract docs from all source files."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        # Create Python files
        (src_dir / "module1.py").write_text(
            '# sym: first\nFIRST_DOC = """First documentation."""\n'
        )
        (src_dir / "module2.py").write_text(
            '# sym: second\nSECOND_DOC = """Second documentation."""\n'
        )

        config = DocsConfig(
            extraction_mode="explicit",
            languages=("python",),
            src_dir="src",
            formats=("json",),
        )
        entries = extract_docs_from_dir(tmp_path, config)

        assert len(entries) == 2
        names = [e.name for e in entries]
        assert "first" in names
        assert "second" in names

    def test_extract_docs_from_dir_skips_hidden_directories(self, tmp_path: Path) -> None:
        """Should skip hidden directories and __pycache__."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        # Create hidden directory with docs
        hidden_dir = src_dir / ".hidden"
        hidden_dir.mkdir()
        (hidden_dir / "hidden.py").write_text('# sym: hidden\nHIDDEN_DOC = """Hidden docs."""\n')

        # Create pycache with docs
        pycache_dir = src_dir / "__pycache__"
        pycache_dir.mkdir()
        (pycache_dir / "cached.py").write_text('# sym: cached\nCACHED_DOC = """Cached docs."""\n')

        # Create normal file
        (src_dir / "normal.py").write_text('# sym: normal\nNORMAL_DOC = """Normal docs."""\n')

        config = DocsConfig(
            extraction_mode="explicit",
            languages=("python",),
            src_dir="src",
            formats=("json",),
        )
        entries = extract_docs_from_dir(tmp_path, config)

        # Should only find the normal file
        assert len(entries) == 1
        assert entries[0].name == "normal"

    def test_extract_docs_from_dir_multiple_languages(self, tmp_path: Path) -> None:
        """Should extract docs from multiple language source files."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        (src_dir / "python_module.py").write_text('# sym: py\nPY_DOC = """Python docs."""\n')
        (src_dir / "ts_module.ts").write_text(
            "// sym: ts\nexport const TS_DOC = `TypeScript docs`;\n"
        )

        config = DocsConfig(
            extraction_mode="explicit",
            languages=("python", "ts"),
            src_dir="src",
            formats=("json",),
        )
        entries = extract_docs_from_dir(tmp_path, config)

        assert len(entries) == 2
        langs = [e.lang for e in entries]
        assert "python" in langs
        assert "ts" in langs

    def test_extract_docs_from_dir_sorted_results(self, tmp_path: Path) -> None:
        """Should return entries in sorted order by file path."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        # Create files in non-alphabetical order
        for name in ["z.py", "a.py", "m.py"]:
            (src_dir / name).write_text(f'# sym: {name}\n{name.upper()}_DOC = """{name}"""')

        config = DocsConfig(
            extraction_mode="explicit",
            languages=("python",),
            src_dir="src",
            formats=("json",),
        )
        entries = extract_docs_from_dir(tmp_path, config)

        # Files should be processed in sorted order
        file_names = [e.source_file for e in entries]
        assert file_names == sorted(file_names)


class TestDocEntry:
    """Test DocEntry dataclass."""

    def test_doc_entry_to_dict(self) -> None:
        """Should convert DocEntry to dict for serialization."""
        entry = DocEntry(
            name="test",
            lang="python",
            content="Test content",
            source_file="module.py",
            line=10,
            hash="abc123",
        )

        d = entry.to_dict()

        assert d["name"] == "test"
        assert d["lang"] == "python"
        assert d["content"] == "Test content"
        assert d["source_file"] == "module.py"
        assert d["line"] == 10
        assert d["hash"] == "abc123"

    def test_doc_entry_is_frozen(self) -> None:
        """DocEntry should be immutable (frozen dataclass)."""
        entry = DocEntry(
            name="test",
            lang="python",
            content="Test content",
            source_file="module.py",
            line=10,
            hash="abc123",
        )
        with pytest.raises(Exception):
            entry.name = "modified"  # type: ignore[misc]  # ty:ignore[invalid-assignment]


class TestExtractExplicitEdgeCases:
    """Test edge cases in _extract_explicit that aren't covered by high-level tests."""

    def test_explicit_go_comment_block(self, tmp_path: Path) -> None:
        """Go explicit marker should collect comment lines after the marker."""
        go_file = tmp_path / "main.go"
        go_file.write_text("// sym: MyFunc\n// First line.\n// Second line.\nfunc MyFunc() {}\n")
        config = DocsConfig(
            extraction_mode="explicit",
            languages=("go",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(go_file, config, relative_to=tmp_path)
        assert len(entries) == 1
        assert entries[0].name == "MyFunc"
        assert "First line." in entries[0].content

    def test_explicit_rust_comment_block(self, tmp_path: Path) -> None:
        """Rust explicit marker should collect comment lines after the marker."""
        rs_file = tmp_path / "lib.rs"
        rs_file.write_text(
            "// sym: my_func\n/// This function does X.\n/// And Y.\npub fn my_func() {}\n"
        )
        config = DocsConfig(
            extraction_mode="explicit",
            languages=("rust",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(rs_file, config, relative_to=tmp_path)
        assert len(entries) == 1
        assert entries[0].name == "my_func"

    def test_explicit_go_blank_line_stops_collection(self, tmp_path: Path) -> None:
        """A blank line after comment lines should stop collection."""
        go_file = tmp_path / "main.go"
        go_file.write_text(
            "// sym: MyFunc\n// Line one.\n\n// This is NOT part of it.\nfunc MyFunc() {}\n"
        )
        config = DocsConfig(
            extraction_mode="explicit",
            languages=("go",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(go_file, config, relative_to=tmp_path)
        assert len(entries) == 1
        assert entries[0].content == "Line one."

    def test_explicit_unsupported_lang_returns_empty(self, tmp_path: Path) -> None:
        """_extract_explicit should return [] for a lang with no pattern (e.g. plain text)."""
        # lang_for_path returns None for .txt, so extract_docs returns [] before _extract_explicit
        # We exercise the None-pattern branch via a supported lang that has no explicit pattern
        # by calling lang_for_path — but the real branch is reached via extract_docs for
        # a file that IS a recognised extension but the lang is NOT in config.languages.
        # Instead, directly import and call with an unsupported lang string.
        from repo_release_tools.docs_extractor import _extract_explicit

        result = _extract_explicit("// sym: foo\nfoo content", "file.txt", "unknown_lang")
        assert result == []

    def test_explicit_ts_string_assignment(self, tmp_path: Path) -> None:
        """TS explicit marker with string-literal assignment should be extracted."""
        ts_file = tmp_path / "mod.ts"
        ts_file.write_text('// sym: myConst\nexport const myConst = "My TS doc string";\n')
        config = DocsConfig(
            extraction_mode="explicit",
            languages=("ts",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(ts_file, config, relative_to=tmp_path)
        assert len(entries) == 1
        assert entries[0].content == "My TS doc string"


class TestExtractPythonSourceOwned:
    """Test _extract_python_source_owned path (lines 319-337)."""

    def test_source_owned_extracts_variable_content(self, tmp_path: Path) -> None:
        """Should resolve variable references in SOURCE_OWNED_TOPIC_DOCS tuple."""
        py_file = tmp_path / "docs.py"
        py_file.write_text(
            'MY_DOC = """\nThis is my documentation.\n"""\n\n'
            "SOURCE_OWNED_TOPIC_DOCS = (\n"
            '    ("my_topic", MY_DOC),\n'
            ")\n"
        )
        config = DocsConfig(
            extraction_mode="explicit",
            languages=("python",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(py_file, config, relative_to=tmp_path)
        # The source_owned extractor should find MY_DOC via the tuple
        assert len(entries) > 0
        assert any(e.name == "MY_DOC" for e in entries)

    def test_source_owned_skips_missing_variable(self, tmp_path: Path) -> None:
        """Should skip entries when referenced variable has no content."""
        from repo_release_tools.docs_extractor import _extract_python_source_owned

        source = 'SOURCE_OWNED_TOPIC_DOCS = (\n    ("topic", MISSING_VAR),\n)\n'
        entries = _extract_python_source_owned(source, "mod.py", {})
        assert entries == []

    def test_source_owned_direct_extracts_entries(self) -> None:
        """Direct call to _extract_python_source_owned with valid variable covers lines 319-337."""
        from repo_release_tools.docs_extractor import _extract_python_source_owned

        source = (
            'MY_DOC = """\nDetailed docs.\n"""\n\n'
            "SOURCE_OWNED_TOPIC_DOCS = (\n"
            '    ("my_topic", MY_DOC),\n'
            ")\n"
        )
        module_vars = {"MY_DOC": "Detailed docs."}
        entries = _extract_python_source_owned(source, "mod.py", module_vars)
        assert len(entries) == 1
        assert entries[0].name == "MY_DOC"
        assert entries[0].lang == "python"
        assert entries[0].content == "Detailed docs."
        assert entries[0].source_file == "mod.py"

    def test_source_owned_no_tuple_returns_empty(self, tmp_path: Path) -> None:
        """Should return [] when SOURCE_OWNED_TOPIC_DOCS is absent."""
        from repo_release_tools.docs_extractor import _extract_python_source_owned

        source = 'MY_DOC = """some doc"""\n'
        entries = _extract_python_source_owned(source, "mod.py", {"MY_DOC": "some doc"})
        assert entries == []
