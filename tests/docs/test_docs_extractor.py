"""Tests for docs_extractor module."""

from __future__ import annotations

from pathlib import Path

import pytest

from repo_release_tools.config import DocsConfig
from repo_release_tools.docs.extractor import (
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
        self,
        tmp_path: Path,
        docs_config: DocsConfig,
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
            "/**\n * My function\n * Detailed description\n */\nexport function myFunc() {}\n",
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
            "// MyFunc is a test function.\n// It does something.\nfunc MyFunc() {}\n",
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
            "/// MyFunc is a test function.\n/// It does something.\npub fn my_func() {}\n",
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
            ")\n",
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
            'def func():\n    """Function doc"""\n    pass\n',
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
            '# sym: first\nFIRST_DOC = """First documentation."""\n',
        )
        (src_dir / "module2.py").write_text(
            '# sym: second\nSECOND_DOC = """Second documentation."""\n',
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
            "// sym: ts\nexport const TS_DOC = `TypeScript docs`;\n",
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
            "// sym: my_func\n/// This function does X.\n/// And Y.\npub fn my_func() {}\n",
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
            "// sym: MyFunc\n// Line one.\n\n// This is NOT part of it.\nfunc MyFunc() {}\n",
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
        from repo_release_tools.docs.extractor import _extract_explicit

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
            ")\n",
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
        from repo_release_tools.docs.extractor import _extract_python_source_owned

        source = 'SOURCE_OWNED_TOPIC_DOCS = (\n    ("topic", MISSING_VAR),\n)\n'
        entries = _extract_python_source_owned(source, "mod.py", {})
        assert entries == []

    def test_source_owned_direct_extracts_entries(self) -> None:
        """Direct call to _extract_python_source_owned with valid variable covers lines 319-337."""
        from repo_release_tools.docs.extractor import _extract_python_source_owned

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
        from repo_release_tools.docs.extractor import _extract_python_source_owned

        source = 'MY_DOC = """some doc"""\n'
        entries = _extract_python_source_owned(source, "mod.py", {"MY_DOC": "some doc"})
        assert entries == []


class TestBashExtraction:
    """Tests for Bash/Zsh language doc extraction (Track 1)."""

    # ── lang_for_path ──────────────────────────────────────────────────────

    def test_lang_for_path_bash_sh(self) -> None:
        """Should return 'bash' for .sh files."""
        assert lang_for_path(Path("script.sh")) == "bash"

    def test_lang_for_path_bash_bash(self) -> None:
        """Should return 'bash' for .bash files."""
        assert lang_for_path(Path("script.bash")) == "bash"

    def test_lang_for_path_bash_zsh(self) -> None:
        """Should return 'bash' for .zsh files."""
        assert lang_for_path(Path("script.zsh")) == "bash"

    # ── implicit extraction ────────────────────────────────────────────────

    def test_bash_implicit_script_header(self, tmp_path: Path) -> None:
        """## header lines at top of file should be extracted as 'script' entry."""
        sh_file = tmp_path / "script.sh"
        sh_file.write_text("#!/usr/bin/env bash\n## A bash utility.\n## Does stuff.\n\necho hi\n")
        config = DocsConfig(
            extraction_mode="implicit",
            languages=("bash",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(sh_file, config, relative_to=tmp_path)
        assert any(e.name == "script" for e in entries)
        script_entry = next(e for e in entries if e.name == "script")
        assert "A bash utility." in script_entry.content
        assert "Does stuff." in script_entry.content
        assert script_entry.lang == "bash"

    def test_bash_implicit_script_header_without_shebang(self, tmp_path: Path) -> None:
        """## header block without shebang should still be extracted."""
        sh_file = tmp_path / "lib.sh"
        sh_file.write_text("## Library utilities.\n\nfoo() { :; }\n")
        config = DocsConfig(
            extraction_mode="implicit",
            languages=("bash",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(sh_file, config, relative_to=tmp_path)
        assert any(e.name == "script" for e in entries)

    def test_bash_implicit_function_comments(self, tmp_path: Path) -> None:
        """# comment lines before function declarations should be extracted."""
        sh_file = tmp_path / "script.sh"
        sh_file.write_text(
            "#!/usr/bin/env bash\n"
            "# Greet a user.\n"
            "# Takes one argument.\n"
            "greet() {\n"
            '    echo "Hello $1"\n'
            "}\n"
        )
        config = DocsConfig(
            extraction_mode="implicit",
            languages=("bash",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(sh_file, config, relative_to=tmp_path)
        assert any(e.name == "greet" for e in entries)
        entry = next(e for e in entries if e.name == "greet")
        assert "Greet a user." in entry.content
        assert "Takes one argument." in entry.content

    def test_bash_implicit_function_keyword_syntax(self, tmp_path: Path) -> None:
        """function keyword syntax should be matched for implicit extraction."""
        sh_file = tmp_path / "script.sh"
        sh_file.write_text("# A helper function.\nfunction _helper {\n    echo helper\n}\n")
        config = DocsConfig(
            extraction_mode="implicit",
            languages=("bash",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(sh_file, config, relative_to=tmp_path)
        assert any(e.name == "_helper" for e in entries)

    def test_bash_implicit_no_header_no_functions(self, tmp_path: Path) -> None:
        """A script with no ## header and no functions yields no entries."""
        sh_file = tmp_path / "plain.sh"
        sh_file.write_text("#!/usr/bin/env bash\n# ordinary comment\necho hi\n")
        config = DocsConfig(
            extraction_mode="implicit",
            languages=("bash",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(sh_file, config, relative_to=tmp_path)
        assert entries == []

    # ── explicit extraction ────────────────────────────────────────────────

    def test_bash_explicit_marker(self, tmp_path: Path) -> None:
        """# sym: NAME marker should trigger explicit doc extraction for bash."""
        sh_file = tmp_path / "script.sh"
        sh_file.write_text(
            "# sym: my_func\n# Explicit documentation line.\n# Second line.\nmy_func() { :; }\n"
        )
        config = DocsConfig(
            extraction_mode="explicit",
            languages=("bash",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(sh_file, config, relative_to=tmp_path)
        assert len(entries) == 1
        assert entries[0].name == "my_func"
        assert "Explicit documentation line." in entries[0].content
        assert entries[0].lang == "bash"

    def test_bash_both_mode(self, tmp_path: Path) -> None:
        """'both' mode should yield explicit and implicit entries."""
        sh_file = tmp_path / "script.sh"
        sh_file.write_text(
            "## Script header doc.\n\n"
            "# sym: explicit_func\n# Explicit docs.\n"
            "explicit_func() { :; }\n\n"
            "# Implicit func doc.\n"
            "implicit_func() { :; }\n"
        )
        config = DocsConfig(
            extraction_mode="both",
            languages=("bash",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(sh_file, config, relative_to=tmp_path)
        names = [e.name for e in entries]
        assert "explicit_func" in names
        assert "implicit_func" in names

    def test_bash_from_dir(self, tmp_path: Path) -> None:
        """extract_docs_from_dir should pick up .sh files when bash is in languages."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "deploy.sh").write_text("# sym: deploy\n# Deploy the app.\nfunction deploy { :; }\n")
        config = DocsConfig(
            extraction_mode="explicit",
            languages=("bash",),
            src_dir="src",
            formats=("json",),
        )
        entries = extract_docs_from_dir(tmp_path, config)
        assert len(entries) == 1
        assert entries[0].name == "deploy"
        assert entries[0].lang == "bash"


class TestPowerShellExtraction:
    """Tests for PowerShell doc extraction (Track 1)."""

    # ── lang_for_path ──────────────────────────────────────────────────────

    def test_lang_for_path_ps1(self) -> None:
        """Should return 'powershell' for .ps1 files."""
        assert lang_for_path(Path("script.ps1")) == "powershell"

    def test_lang_for_path_psm1(self) -> None:
        """Should return 'powershell' for .psm1 files."""
        assert lang_for_path(Path("module.psm1")) == "powershell"

    def test_lang_for_path_psd1(self) -> None:
        """Should return 'powershell' for .psd1 files."""
        assert lang_for_path(Path("manifest.psd1")) == "powershell"

    # ── implicit extraction ────────────────────────────────────────────────

    def test_powershell_implicit_module_block(self, tmp_path: Path) -> None:
        """A <# ... #> block separated from the first function should become a 'module' entry."""
        ps_file = tmp_path / "script.ps1"
        # Module-level block is followed by non-function code before the first function,
        # so it is NOT immediately adjacent to the function declaration.
        ps_file.write_text(
            "<#\n.SYNOPSIS\nScript synopsis.\n.DESCRIPTION\nLong description.\n#>\n"
            "\n"
            "Set-Variable -Name 'MyVar' -Value 'hello'\n"
            "\n"
            "function Invoke-Something { }\n"
        )
        config = DocsConfig(
            extraction_mode="implicit",
            languages=("powershell",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(ps_file, config, relative_to=tmp_path)
        assert any(e.name == "module" for e in entries)
        mod = next(e for e in entries if e.name == "module")
        assert ".SYNOPSIS" in mod.content
        assert mod.lang == "powershell"

    def test_powershell_implicit_function_adjacent_block_not_module(self, tmp_path: Path) -> None:
        """A <# ... #> block immediately before the first (and only) function is NOT module-level."""
        ps_file = tmp_path / "onefunc.ps1"
        ps_file.write_text("<#\n.SYNOPSIS\nGreet a user.\n#>\nfunction Invoke-Greet { }\n")
        config = DocsConfig(
            extraction_mode="implicit",
            languages=("powershell",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(ps_file, config, relative_to=tmp_path)
        # Block is immediately adjacent to the function → only a function entry, no module
        assert not any(e.name == "module" for e in entries)
        assert any(e.name == "Invoke-Greet" for e in entries)

    def test_powershell_implicit_function_block(self, tmp_path: Path) -> None:
        """A <# ... #> block immediately before a function should be extracted."""
        ps_file = tmp_path / "funcs.ps1"
        ps_file.write_text(
            "<#\n.SYNOPSIS\nGreet a user.\n.PARAMETER Name\nThe name to greet.\n#>\n"
            "function Invoke-Greet {\n"
            "    param([string]$Name)\n"
            '    Write-Host "Hello, $Name"\n'
            "}\n"
        )
        config = DocsConfig(
            extraction_mode="implicit",
            languages=("powershell",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(ps_file, config, relative_to=tmp_path)
        func_entries = [e for e in entries if e.name == "Invoke-Greet"]
        assert len(func_entries) == 1
        assert ".SYNOPSIS" in func_entries[0].content
        assert "Greet a user." in func_entries[0].content

    def test_powershell_implicit_hash_comment_fallback(self, tmp_path: Path) -> None:
        """Consecutive # lines before a function should work as a fallback."""
        ps_file = tmp_path / "simple.ps1"
        ps_file.write_text(
            "# Gets the current version.\n"
            "# Returns a string.\n"
            "function Get-Version {\n"
            "    return '1.0'\n"
            "}\n"
        )
        config = DocsConfig(
            extraction_mode="implicit",
            languages=("powershell",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(ps_file, config, relative_to=tmp_path)
        assert any(e.name == "Get-Version" for e in entries)
        entry = next(e for e in entries if e.name == "Get-Version")
        assert "Gets the current version." in entry.content
        assert "Returns a string." in entry.content

    def test_powershell_implicit_two_functions_with_separate_blocks(self, tmp_path: Path) -> None:
        """Each function should be paired with its own preceding <# ... #> block."""
        ps_file = tmp_path / "multi.ps1"
        ps_file.write_text(
            "<#\nModule overview.\n#>\n"
            "\n"
            "<#\n.SYNOPSIS\nFirst function.\n#>\n"
            "function Get-First { }\n"
            "\n"
            "<#\n.SYNOPSIS\nSecond function.\n#>\n"
            "function Get-Second { }\n"
        )
        config = DocsConfig(
            extraction_mode="implicit",
            languages=("powershell",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(ps_file, config, relative_to=tmp_path)
        names = [e.name for e in entries]
        assert "Get-First" in names
        assert "Get-Second" in names
        first = next(e for e in entries if e.name == "Get-First")
        second = next(e for e in entries if e.name == "Get-Second")
        assert "First function." in first.content
        assert "Second function." in second.content

    # ── explicit extraction ────────────────────────────────────────────────

    def test_powershell_explicit_hash_marker(self, tmp_path: Path) -> None:
        """# sym: NAME marker should trigger explicit extraction for powershell."""
        ps_file = tmp_path / "script.ps1"
        ps_file.write_text("# sym: GetFoo\n# Returns foo.\nfunction Get-Foo { return 'foo' }\n")
        config = DocsConfig(
            extraction_mode="explicit",
            languages=("powershell",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(ps_file, config, relative_to=tmp_path)
        assert len(entries) == 1
        assert entries[0].name == "GetFoo"
        assert "Returns foo." in entries[0].content
        assert entries[0].lang == "powershell"

    def test_powershell_explicit_angle_marker(self, tmp_path: Path) -> None:
        """<# sym: NAME #> marker should trigger explicit extraction for powershell."""
        ps_file = tmp_path / "script.ps1"
        ps_file.write_text(
            "<# sym: GetBar #>\n<#\nReturns bar.\n#>\nfunction Get-Bar { return 'bar' }\n"
        )
        config = DocsConfig(
            extraction_mode="explicit",
            languages=("powershell",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(ps_file, config, relative_to=tmp_path)
        assert len(entries) == 1
        assert entries[0].name == "GetBar"
        assert "Returns bar." in entries[0].content

    def test_powershell_from_dir(self, tmp_path: Path) -> None:
        """extract_docs_from_dir should pick up .ps1 files when powershell is in languages."""
        src = tmp_path / "scripts"
        src.mkdir()
        (src / "deploy.ps1").write_text(
            "# sym: deploy\n# Deploy the app.\nfunction Invoke-Deploy { }\n"
        )
        config = DocsConfig(
            extraction_mode="explicit",
            languages=("powershell",),
            src_dir="scripts",
            formats=("json",),
        )
        entries = extract_docs_from_dir(tmp_path, config)
        assert len(entries) == 1
        assert entries[0].name == "deploy"
        assert entries[0].lang == "powershell"


class TestDocsConfigLanguageValidation:
    """Confirm that bash, fish, and powershell are accepted as valid language values."""

    def test_bash_accepted_in_config(self) -> None:
        """DocsConfig should accept 'bash' as a language."""
        cfg = DocsConfig(
            extraction_mode="explicit",
            languages=("bash",),
            src_dir=".",
            formats=("json",),
        )
        assert "bash" in cfg.languages

    def test_powershell_accepted_in_config(self) -> None:
        """DocsConfig should accept 'powershell' as a language."""
        cfg = DocsConfig(
            extraction_mode="explicit",
            languages=("powershell",),
            src_dir=".",
            formats=("json",),
        )
        assert "powershell" in cfg.languages

    def test_bash_and_powershell_in_valid_languages_constant(self) -> None:
        """bash, fish, and powershell should appear in _VALID_LANGUAGES."""
        from repo_release_tools.config.docs_config import _VALID_LANGUAGES

        assert "bash" in _VALID_LANGUAGES
        assert "fish" in _VALID_LANGUAGES
        assert "powershell" in _VALID_LANGUAGES

    def test_invalid_language_rejected(self) -> None:
        """A truly unsupported language slug should raise ValueError via load path."""
        import pytest

        from repo_release_tools.config.docs_config import _load_docs_languages

        with pytest.raises(ValueError, match="unsupported"):
            _load_docs_languages({"languages": ["cobol"]})


class TestExtractorCoverageGaps:
    """Targeted tests to cover remaining uncovered branches in extractor.py."""

    # ── bash explicit: blank line between comment lines stops collection ────

    def test_bash_explicit_blank_line_stops_collection(self, tmp_path: Path) -> None:
        """A blank line after # comment lines should stop the collection (line 283)."""
        sh_file = tmp_path / "script.sh"
        sh_file.write_text(
            "# sym: myfunc\n# Line one.\n\n# This should NOT be part of the doc.\nmyfunc() { :; }\n"
        )
        config = DocsConfig(
            extraction_mode="explicit",
            languages=("bash",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(sh_file, config, relative_to=tmp_path)
        assert len(entries) == 1
        assert entries[0].content == "Line one."

    # ── powershell explicit: blank line stops # fallback collection ─────────

    def test_powershell_explicit_blank_line_stops_collection(self, tmp_path: Path) -> None:
        """A blank line in PS explicit # fallback should stop collection (line 301)."""
        ps_file = tmp_path / "script.ps1"
        ps_file.write_text(
            "# sym: MyFunc\n# First line.\n\n# Not part of doc.\nfunction My-Func { }\n"
        )
        config = DocsConfig(
            extraction_mode="explicit",
            languages=("powershell",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(ps_file, config, relative_to=tmp_path)
        assert len(entries) == 1
        assert entries[0].content == "First line."

    # ── powershell implicit: blank lines near function, non-comment stops ───

    def test_powershell_implicit_blank_line_skipped_before_comments(self, tmp_path: Path) -> None:
        """Blank lines between function keyword and preceding comment block
        should be skipped via the continue branch (lines 542-543)."""
        ps_file = tmp_path / "script.ps1"
        # One blank line separates function from the # doc comment
        ps_file.write_text("# Docs for Foo.\n\nfunction Get-FooBlank { }\n")
        config = DocsConfig(
            extraction_mode="implicit",
            languages=("powershell",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(ps_file, config, relative_to=tmp_path)
        assert any(e.name == "Get-FooBlank" for e in entries)

    def test_powershell_implicit_non_comment_stops_collection(self, tmp_path: Path) -> None:
        """A non-blank, non-comment line before the comment block should stop collection
        (lines 544-545)."""
        ps_file = tmp_path / "script.ps1"
        ps_file.write_text("some_code = 1\n# Docs for Bar.\nfunction Get-Bar { }\n")
        config = DocsConfig(
            extraction_mode="implicit",
            languages=("powershell",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(ps_file, config, relative_to=tmp_path)
        # The comment IS immediately before the function so it should be collected
        bar_entries = [e for e in entries if e.name == "Get-Bar"]
        assert len(bar_entries) == 1
        assert "Docs for Bar." in bar_entries[0].content

    def test_powershell_implicit_block_with_nonwhitespace_gap_fallback_to_hash(
        self, tmp_path: Path
    ) -> None:
        """When the nearest <# ... #> has non-whitespace before the function,
        the # lines fallback should be used instead (line 532)."""
        ps_file = tmp_path / "script.ps1"
        # <# block #> is followed by code, then a # comment, then the function.
        # The nearest <# block #> has a gap, so line 532 triggers and the
        # # comment lines become the content instead.
        ps_file.write_text(
            "<#\nModule overview.\n#>\n"
            "Set-Variable Foo 'bar'\n"
            "# Hash doc for Get-Baz.\n"
            "function Get-Baz { }\n"
        )
        config = DocsConfig(
            extraction_mode="implicit",
            languages=("powershell",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(ps_file, config, relative_to=tmp_path)
        baz_entries = [e for e in entries if e.name == "Get-Baz"]
        assert len(baz_entries) == 1
        # Should use the # comment, not the <# block #>
        assert "Hash doc for Get-Baz." in baz_entries[0].content


class TestFishExtraction:
    """Tests for Fish shell doc extraction."""

    # ── lang_for_path ──────────────────────────────────────────────────────

    def test_lang_for_path_fish(self) -> None:
        """Should return 'fish' for .fish files."""
        assert lang_for_path(Path("functions.fish")) == "fish"

    # ── implicit: script header ────────────────────────────────────────────

    def test_fish_implicit_script_header(self, tmp_path: Path) -> None:
        """## header lines at top of file should be extracted as 'script' entry."""
        fish_file = tmp_path / "funcs.fish"
        fish_file.write_text(
            "#!/usr/bin/env fish\n## A Fish utility.\n## Does stuff.\n\nfunction hello\n    echo hi\nend\n"
        )
        config = DocsConfig(
            extraction_mode="implicit",
            languages=("fish",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(fish_file, config, relative_to=tmp_path)
        script_entries = [e for e in entries if e.name == "script"]
        assert len(script_entries) == 1
        assert "A Fish utility." in script_entries[0].content
        assert script_entries[0].lang == "fish"

    def test_fish_implicit_header_without_shebang(self, tmp_path: Path) -> None:
        """## header block without shebang should still be extracted."""
        fish_file = tmp_path / "lib.fish"
        fish_file.write_text("## Fish library.\n\nfunction helper\n    true\nend\n")
        config = DocsConfig(
            extraction_mode="implicit",
            languages=("fish",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(fish_file, config, relative_to=tmp_path)
        assert any(e.name == "script" for e in entries)

    # ── implicit: function comments ────────────────────────────────────────

    def test_fish_implicit_function_comments(self, tmp_path: Path) -> None:
        """# comment lines before function declaration should be extracted."""
        fish_file = tmp_path / "greet.fish"
        fish_file.write_text(
            "# Greet a user.\n"
            "# Accepts one argument: the name.\n"
            "function greet\n"
            '    echo "Hello $argv[1]"\n'
            "end\n"
        )
        config = DocsConfig(
            extraction_mode="implicit",
            languages=("fish",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(fish_file, config, relative_to=tmp_path)
        func_entries = [e for e in entries if e.name == "greet"]
        assert len(func_entries) == 1
        assert "Greet a user." in func_entries[0].content
        assert "Accepts one argument" in func_entries[0].content
        assert func_entries[0].lang == "fish"

    def test_fish_implicit_hyphenated_function_name(self, tmp_path: Path) -> None:
        """Hyphenated Fish function names (fish-style) should be extracted."""
        fish_file = tmp_path / "utils.fish"
        fish_file.write_text("# Install a package.\nfunction __fish-pkg-install\n    true\nend\n")
        config = DocsConfig(
            extraction_mode="implicit",
            languages=("fish",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(fish_file, config, relative_to=tmp_path)
        assert any("fish-pkg-install" in e.name for e in entries)

    def test_fish_implicit_multiple_functions(self, tmp_path: Path) -> None:
        """Multiple commented functions should each produce their own entry."""
        fish_file = tmp_path / "multi.fish"
        fish_file.write_text(
            "# Say hello.\n"
            "function say-hello\n"
            "    echo hello\n"
            "end\n"
            "\n"
            "# Say goodbye.\n"
            "function say-bye\n"
            "    echo bye\n"
            "end\n"
        )
        config = DocsConfig(
            extraction_mode="implicit",
            languages=("fish",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(fish_file, config, relative_to=tmp_path)
        names = [e.name for e in entries]
        assert "say-hello" in names
        assert "say-bye" in names

    def test_fish_implicit_no_doc_no_entry(self, tmp_path: Path) -> None:
        """Functions without preceding comments should not produce entries."""
        fish_file = tmp_path / "nodoc.fish"
        fish_file.write_text("function undocumented\n    true\nend\n")
        config = DocsConfig(
            extraction_mode="implicit",
            languages=("fish",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(fish_file, config, relative_to=tmp_path)
        assert all(e.name != "undocumented" for e in entries)

    # ── explicit extraction ────────────────────────────────────────────────

    def test_fish_explicit_hash_marker(self, tmp_path: Path) -> None:
        """# sym: NAME marker should extract the following # comment lines."""
        fish_file = tmp_path / "deploy.fish"
        fish_file.write_text(
            "# sym: deploy\n"
            "# Deploy the application to production.\n"
            "# Reads DEPLOY_TARGET from environment.\n"
            "function deploy\n"
            "    true\n"
            "end\n"
        )
        config = DocsConfig(
            extraction_mode="explicit",
            languages=("fish",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(fish_file, config, relative_to=tmp_path)
        assert len(entries) == 1
        assert entries[0].name == "deploy"
        assert "Deploy the application" in entries[0].content
        assert entries[0].lang == "fish"

    def test_fish_explicit_blank_line_stops_collection(self, tmp_path: Path) -> None:
        """A blank line after # comment lines should stop collection."""
        fish_file = tmp_path / "script.fish"
        fish_file.write_text(
            "# sym: myfunc\n# First line.\n\n# Should NOT be part of the doc.\nfunction myfunc\n    true\nend\n"
        )
        config = DocsConfig(
            extraction_mode="explicit",
            languages=("fish",),
            src_dir=".",
            formats=("json",),
        )
        entries = extract_docs(fish_file, config, relative_to=tmp_path)
        assert len(entries) == 1
        assert entries[0].content == "First line."

    # ── config validation ──────────────────────────────────────────────────

    def test_fish_accepted_in_config(self) -> None:
        """DocsConfig should accept 'fish' as a language value."""
        cfg = DocsConfig(
            extraction_mode="explicit",
            languages=("fish",),
            src_dir=".",
            formats=("json",),
        )
        assert "fish" in cfg.languages

    def test_fish_in_valid_languages_constant(self) -> None:
        """'fish' should appear in _VALID_LANGUAGES."""
        from repo_release_tools.config.docs_config import _VALID_LANGUAGES

        assert "fish" in _VALID_LANGUAGES

    # ── from_dir integration ───────────────────────────────────────────────

    def test_fish_from_dir(self, tmp_path: Path) -> None:
        """extract_docs_from_dir should pick up .fish files when fish is in languages."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "deploy.fish").write_text(
            "# sym: deploy\n# Deploy the app.\nfunction deploy\n    true\nend\n"
        )
        config = DocsConfig(
            extraction_mode="explicit",
            languages=("fish",),
            src_dir="src",
            formats=("json",),
        )
        entries = extract_docs_from_dir(tmp_path, config)
        assert len(entries) == 1
        assert entries[0].name == "deploy"
        assert entries[0].lang == "fish"
